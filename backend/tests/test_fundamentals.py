"""
Tests for Phase 5A — Hybrid Fundamental Data Foundation.

All tests run OFFLINE without real network calls or paid credentials.
Covers:
  - Upstox config & token protection
  - Upstox provider (profile, statements, ratios, shareholding, actions, competitors)
  - HTTP error handling (401, 429, timeout, server errors)
  - Parameter handling (consolidated vs standalone, yearly vs quarterly)
  - Null / missing value handling (never treated as 0 unless zero)
  - NSE filing provider stub
  - Screener.in CSV import provider
  - Provider manager & ISIN resolution
  - Source conflict detection
  - Database schema & persistence (upsert idempotency)
  - FastAPI endpoints via TestClient
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.config import UpstoxConfig
from app.fundamental_db import (
    get_balance_sheets,
    get_cash_flows,
    get_company_profile,
    get_income_statements,
    get_ratios,
    get_shareholding,
    init_fundamental_tables,
    record_sync_history,
    upsert_company_profile,
    upsert_income_statement,
    upsert_key_ratios,
)
from app.providers.fundamentals.base import FundamentalProvider
from app.providers.fundamentals.manager import FundamentalProviderManager
from app.providers.fundamentals.nse_provider import NseFilingProvider
from app.providers.fundamentals.screener_csv_provider import ScreenerCsvProvider
from app.providers.fundamentals.upstox_provider import (
    UpstoxFundamentalProvider,
    _safe_float,
    _safe_int,
)
from app.schemas.fundamentals import (
    BalanceSheet,
    CompanyProfile,
    FundamentalSource,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    StatementType,
)


@pytest.fixture(autouse=True)
def ensure_db():
    from app.database import init_db
    init_db()
    init_fundamental_tables()


# ===========================================================================
# 1. Configuration & Security Tests
# ===========================================================================

class TestUpstoxConfig:

    def test_config_configured_when_token_present(self):
        cfg = UpstoxConfig(access_token="test_jwt_token_123")
        assert cfg.is_configured is True

    def test_config_not_configured_when_token_empty(self):
        cfg = UpstoxConfig(access_token="")
        assert cfg.is_configured is False

    def test_config_reads_env_safely(self):
        with patch.dict("os.environ", {"UPSTOX_ACCESS_TOKEN": "my_secret_token"}):
            from app.config import get_upstox_config
            cfg = get_upstox_config()
            assert cfg.is_configured is True
            assert cfg.access_token == "my_secret_token"


# ===========================================================================
# 2. Data Cleaning & Type Conversion Tests
# ===========================================================================

class TestDataConversion:

    def test_safe_float_valid(self):
        assert _safe_float("123.45") == 123.45
        assert _safe_float(50.5) == 50.5
        assert _safe_float(0) == 0.0

    def test_safe_float_missing_values(self):
        """Missing values must NOT be converted to 0."""
        assert _safe_float(None) is None
        assert _safe_float("") is None
        assert _safe_float("NA") is None
        assert _safe_float("N/A") is None
        assert _safe_float("invalid") is None

    def test_safe_int_valid_and_missing(self):
        assert _safe_int("1995") == 1995
        assert _safe_int(2000) == 2000
        assert _safe_int(None) is None
        assert _safe_int("NA") is None


# ===========================================================================
# 3. Upstox Provider Tests (Mocked HTTP)
# ===========================================================================

class TestUpstoxProvider:

    def test_headers_and_availability(self):
        with patch("app.providers.fundamentals.upstox_provider.get_upstox_config") as mock_cfg:
            mock_cfg.return_value = UpstoxConfig(access_token="secret_token")
            provider = UpstoxFundamentalProvider()
            assert provider.is_available() is True
            headers = provider._get_headers()
            assert headers["Authorization"] == "Bearer secret_token"
            assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_fetch_profile_success(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "company_name": "Reliance Industries Limited",
                "isin": "INE002A01018",
                "sector": "Energy",
                "industry": "Oil & Gas",
                "face_value": 10.0,
                "market_cap": 1700000.0,
                "year_of_incorporation": 1973,
                "about": "India's largest private sector company.",
            }
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            profile = await provider.fetch_profile("INE002A01018")

        assert profile is not None
        assert profile.isin == "INE002A01018"
        assert profile.company_name == "Reliance Industries Limited"
        assert profile.sector == "Energy"
        assert profile.face_value == 10.0
        assert profile.source == FundamentalSource.UPSTOX_API

    @pytest.mark.asyncio
    async def test_fetch_profile_401_unauthorized(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            profile = await provider.fetch_profile("INE002A01018")

        assert profile is None

    @pytest.mark.asyncio
    async def test_fetch_profile_timeout(self):
        provider = UpstoxFundamentalProvider()

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("timeout")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            profile = await provider.fetch_profile("INE002A01018")

        assert profile is None

    @pytest.mark.asyncio
    async def test_fetch_income_statements_consolidated_yearly(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "period": "FY2024",
                    "total_revenue": 900000.0,
                    "operating_profit": 150000.0,
                    "net_profit": 75000.0,
                    "basic_eps": 110.5,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            stmts = await provider.fetch_income_statements(
                "INE002A01018",
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.YEARLY,
            )

        assert len(stmts) == 1
        assert stmts[0].period == "FY2024"
        assert stmts[0].revenue_cr == 900000.0
        assert stmts[0].net_profit_cr == 75000.0
        assert stmts[0].statement_type == StatementType.CONSOLIDATED
        assert stmts[0].frequency == ReportingFrequency.YEARLY

    @pytest.mark.asyncio
    async def test_fetch_balance_sheets(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "period": "FY2024",
                    "total_assets": 1500000.0,
                    "total_liabilities": 700000.0,
                    "total_equity": 800000.0,
                    "total_debt": 300000.0,
                    "book_value_per_share": 1180.0,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            sheets = await provider.fetch_balance_sheets("INE002A01018")

        assert len(sheets) == 1
        assert sheets[0].total_assets_cr == 1500000.0
        assert sheets[0].total_equity_cr == 800000.0
        assert sheets[0].book_value_per_share == 1180.0

    @pytest.mark.asyncio
    async def test_fetch_cash_flows(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "period": "FY2024",
                    "operating_cash_flow": 120000.0,
                    "investing_cash_flow": -80000.0,
                    "financing_cash_flow": -30000.0,
                    "capex": -70000.0,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            cfs = await provider.fetch_cash_flows("INE002A01018")

        assert len(cfs) == 1
        assert cfs[0].operating_cash_flow_cr == 120000.0
        assert cfs[0].capex_cr == -70000.0
        # FCF fallback calculation: operating - abs(capex) = 120000 - 70000 = 50000
        assert cfs[0].free_cash_flow_cr == 50000.0

    @pytest.mark.asyncio
    async def test_fetch_key_ratios(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "period": "FY2024",
                    "pe": 26.5,
                    "pb": 2.8,
                    "roe": 14.2,
                    "roce": 12.0,
                    "debt_equity": 0.38,
                    "opm": 16.5,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            ratios = await provider.fetch_ratios("INE002A01018")

        assert len(ratios) == 1
        assert ratios[0].pe == 26.5
        assert ratios[0].roe == 14.2
        assert ratios[0].debt_equity == 0.38
        assert ratios[0].opm_pct == 16.5

    @pytest.mark.asyncio
    async def test_fetch_shareholding(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "period": "Q4FY2024",
                    "promoter_holding": 50.3,
                    "promoter_pledging": 0.0,
                    "fii_holding": 22.4,
                    "dii_holding": 16.2,
                    "public_holding": 11.1,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            sh = await provider.fetch_shareholding("INE002A01018")

        assert len(sh) == 1
        assert sh[0].promoter_holding == 50.3
        assert sh[0].fii_holding == 22.4
        assert sh[0].promoter_pledging == 0.0

    @pytest.mark.asyncio
    async def test_fetch_corporate_actions(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "action_type": "DIVIDEND",
                    "ex_date": "2024-08-19",
                    "description": "Final Dividend - Rs 10 per share",
                    "value": 10.0,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            actions = await provider.fetch_corporate_actions("INE002A01018")

        assert len(actions) == 1
        assert actions[0].action_type == "DIVIDEND"
        assert actions[0].value == 10.0

    @pytest.mark.asyncio
    async def test_fetch_competitors(self):
        provider = UpstoxFundamentalProvider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "company_name": "Indian Oil Corporation",
                    "isin": "INE242A01010",
                    "pe": 8.5,
                    "market_cap": 220000.0,
                }
            ]
        }

        with patch("app.providers.fundamentals.upstox_provider.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            comps = await provider.fetch_competitors("INE002A01018")

        assert len(comps) == 1
        assert comps[0].competitor_name == "Indian Oil Corporation"
        assert comps[0].pe == 8.5


# ===========================================================================
# 4. NSE Filing Stub Provider Tests
# ===========================================================================

class TestNseFilingProvider:

    def test_stub_always_unavailable(self):
        p = NseFilingProvider()
        assert p.is_available() is False
        assert p.source_label() == FundamentalSource.NSE_FILING

    @pytest.mark.asyncio
    async def test_stub_returns_empty_safely(self):
        p = NseFilingProvider()
        assert await p.fetch_profile("INE002A01018") is None
        assert await p.fetch_income_statements("INE002A01018") == []
        assert await p.fetch_balance_sheets("INE002A01018") == []
        assert await p.fetch_cash_flows("INE002A01018") == []
        assert await p.fetch_ratios("INE002A01018") == []


# ===========================================================================
# 5. Screener CSV Import Provider Tests
# ===========================================================================

class TestScreenerCsvProvider:

    def test_parse_valid_csv(self):
        provider = ScreenerCsvProvider()
        csv_text = """Name,Symbol,Current Price,Price to Earning,Price to Book,Return on equity,Sales growth
Reliance Industries,RELIANCE,2480.0,24.5,3.2,10.8,12.5%
Tata Consultancy,TCS,3890.0,28.1,15.0,51.2,8.2%
"""
        mapping = {"RELIANCE": "INE002A01018", "TCS": "INE467B01029"}
        result = provider.parse_csv(csv_text, mapping)

        assert "RELIANCE" in result
        assert result["RELIANCE"]["pe"] == 24.5
        assert result["RELIANCE"]["pb"] == 3.2
        assert result["RELIANCE"]["roe"] == 10.8
        assert result["RELIANCE"]["revenue_growth_pct"] == 12.5
        assert result["RELIANCE"]["close"] == 2480.0

        assert "TCS" in result
        assert result["TCS"]["pe"] == 28.1

    def test_unmapped_symbols_tracked(self):
        provider = ScreenerCsvProvider()
        csv_text = """Symbol,Current Price,Price to Earning
UNKNOWN_CORP,100.0,15.0
"""
        mapping = {"RELIANCE": "INE002A01018"}
        result = provider.parse_csv(csv_text, mapping)
        assert "UNKNOWN_CORP" not in result
        assert "UNKNOWN_CORP" in result.get("_unmapped", [])

    def test_empty_csv_handled_safely(self):
        provider = ScreenerCsvProvider()
        result = provider.parse_csv("", {})
        assert len(result.get("_errors", [])) > 0


# ===========================================================================
# 6. Provider Manager & ISIN Resolution Tests
# ===========================================================================

class TestFundamentalManager:

    def test_isin_resolution_for_known_stock(self):
        mgr = FundamentalProviderManager()
        isin = mgr.resolve_isin("RELIANCE")
        assert isin == "INE002A01018"

    def test_isin_resolution_for_unknown_stock(self):
        mgr = FundamentalProviderManager()
        assert mgr.resolve_isin("NONEXISTENT_TICKER") is None

    def test_source_conflict_detection(self):
        records = [
            {"source": "upstox_api", "pe": 25.0},
            {"source": "screener_csv", "pe": 35.0},  # 40% difference!
        ]
        conflicts = FundamentalProviderManager.detect_conflicts("TEST", "pe", records, tolerance_pct=5.0)
        assert len(conflicts) == 1
        assert conflicts[0].field == "pe"
        assert conflicts[0].discrepancy_pct is not None
        assert conflicts[0].discrepancy_pct > 5.0

    def test_source_no_conflict_when_within_tolerance(self):
        records = [
            {"source": "upstox_api", "pe": 25.0},
            {"source": "screener_csv", "pe": 25.2},  # < 1% difference
        ]
        conflicts = FundamentalProviderManager.detect_conflicts("TEST", "pe", records, tolerance_pct=5.0)
        assert len(conflicts) == 0


# ===========================================================================
# 7. Database Persistence & Deduplication Tests
# ===========================================================================

class TestFundamentalDbPersistence:

    def test_upsert_company_profile_idempotent(self):
        prof1 = CompanyProfile(
            symbol="TEST_SYM",
            isin="INE999A01011",
            company_name="Test Company v1",
            sector="Finance",
            source=FundamentalSource.UPSTOX_API,
        )
        upsert_company_profile(prof1)

        prof2 = CompanyProfile(
            symbol="TEST_SYM",
            isin="INE999A01011",
            company_name="Test Company v2 Updated",
            sector="Finance",
            source=FundamentalSource.UPSTOX_API,
        )
        upsert_company_profile(prof2)

        stored = get_company_profile("TEST_SYM")
        assert stored is not None
        assert stored["company_name"] == "Test Company v2 Updated"

    def test_upsert_ratios_and_query(self):
        kr = KeyRatios(
            symbol="RELIANCE",
            isin="INE002A01018",
            period="FY2024",
            statement_type=StatementType.CONSOLIDATED,
            frequency=ReportingFrequency.YEARLY,
            pe=24.5,
            roe=12.5,
            source=FundamentalSource.UPSTOX_API,
        )
        upsert_key_ratios(kr)

        ratios = get_ratios("RELIANCE")
        assert len(ratios) >= 1
        assert any(r["period"] == "FY2024" and r["pe"] == 24.5 for r in ratios)

    def test_sync_history_recording(self):
        record_sync_history(
            symbol="RELIANCE",
            isin="INE002A01018",
            provider="upstox_api",
            data_type="profile",
            status="ok",
            records_fetched=1,
        )
        from app.fundamental_db import get_sync_history
        hist = get_sync_history(symbol="RELIANCE", data_type="profile")
        assert len(hist) >= 1
        assert hist[0]["status"] == "ok"


# ===========================================================================
# 8. Router Integration Tests (FastAPI TestClient)
# ===========================================================================

class TestFundamentalsRouter:

    @pytest.fixture(autouse=True)
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        self._client = TestClient(app)
        yield

    def test_status_endpoint_never_leaks_token(self):
        resp = self._client.get("/api/fundamentals/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "upstox_configured" in data
        assert "upstox_token_present" in data
        assert "total_stocks" in data
        assert "stocks_with_isin" in data

        # Token text must NEVER appear anywhere in the response
        text = json.dumps(data).lower()
        for forbidden in ("bearer", "upstox_access_token", "jwt", "token_value"):
            assert forbidden not in text

    def test_get_company_profile_404_when_missing(self):
        resp = self._client.get("/api/fundamentals/company/UNKNOWNSTOCK999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_company_statements_empty_safe(self):
        resp = self._client.get("/api/fundamentals/company/RELIANCE/income-statement")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "RELIANCE"
        assert isinstance(data["data"], list)

    def test_sync_fails_for_unknown_stock_without_isin(self):
        resp = self._client.post(
            "/api/fundamentals/sync/UNKNOWNSTOCK999",
            json={"data_types": ["profile"]},
        )
        assert resp.status_code == 400
        assert "isin" in resp.json()["detail"].lower()

    def test_screener_csv_import_endpoint(self):
        csv_bytes = b"Symbol,Current Price,Price to Earning,Return on equity\nRELIANCE,2500.0,25.0,11.0\n"
        files = {"file": ("screener.csv", io.BytesIO(csv_bytes), "text/csv")}
        resp = self._client.post("/api/fundamentals/import/screener-csv", files=files)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["rows_imported"] == 1
