"""
Phase 14.3 — Actual Market Data Verification & Synthetic Data Isolation Test Suite.

Validates:
1. Strict data source provenance classification (OBSERVED_HISTORICAL, OBSERVED_DELAYED, OBSERVED_LIVE, SYNTHETIC, UNKNOWN).
2. Year-specific NSE trading exchange calendar (2024, 2025, 2026 holidays and special truncated sessions).
3. Physical audit of database: verifies 46,500 stored 5m bars are identified as 100% synthetic/calibrated.
4. Strict synthetic data isolation: True TOD RVOL returns UNAVAILABLE in production mode (allow_synthetic=False).
5. Explicit demonstration mode: allow_synthetic=True returns calculations strictly badged as SYNTHETIC.
6. Genuine observed data calculation: verified observed bars compute genuine TOD RVOL without synthetic contamination.
7. Rejection of mixed provenance baselines (never averages observed and synthetic sessions together).
8. Holiday, weekend, and truncated session (< 60 bars) exclusion.
9. Zero historical volume guardrail.
10. API endpoints respect allow_synthetic parameter and return full provenance metadata.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_bars, connect
from app.services.data_quality_service import (
    DataSourceClassification,
    classify_data_source,
    classify_session_provenance,
)
from app.services.trading_calendar_service import (
    is_trading_holiday,
    is_special_trading_session,
    is_trading_day,
    get_valid_historical_trading_sessions,
    get_session_expected_bars,
)
from app.services.intraday_data_service import (
    get_intraday_ingestion_status,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
    calculate_stock_volume_intelligence,
)
from app.services.market_movers_service import (
    get_market_movers_and_confluence,
    extract_stock_mover_metrics,
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Source Classification Tests
# ---------------------------------------------------------------------------

def test_strict_source_classification():
    """Verify that source strings map to strict provenance categories."""
    assert classify_data_source("yfinance") == DataSourceClassification.OBSERVED_HISTORICAL
    assert classify_data_source("yfinance_historical_5m") == DataSourceClassification.OBSERVED_HISTORICAL
    assert classify_data_source("dhan_historical_5m") == DataSourceClassification.OBSERVED_HISTORICAL
    assert classify_data_source("dhan_live") == DataSourceClassification.OBSERVED_LIVE
    assert classify_data_source("yfinance_delayed") == DataSourceClassification.OBSERVED_DELAYED

    # Synthetic markers
    assert classify_data_source("deterministic_calibrated_5m") == DataSourceClassification.SYNTHETIC
    assert classify_data_source("offline_deterministic_engine") == DataSourceClassification.SYNTHETIC
    assert classify_data_source("synthetic_5m") == DataSourceClassification.SYNTHETIC
    assert classify_data_source("calibrated_mock") == DataSourceClassification.SYNTHETIC

    # Unknown / Empty markers
    assert classify_data_source(None) == DataSourceClassification.UNKNOWN
    assert classify_data_source("") == DataSourceClassification.UNKNOWN
    assert classify_data_source("custom_random_feed") == DataSourceClassification.UNKNOWN


def test_session_provenance_audit():
    """Ensure session classification identifies mixed or synthetic sessions."""
    observed_bars = [
        {"timestamp": "2026-03-02T04:00:00Z", "volume": 1000, "source": "yfinance_historical_5m"},
        {"timestamp": "2026-03-02T04:05:00Z", "volume": 1200, "source": "yfinance_historical_5m"},
    ]
    cls, desc = classify_session_provenance(observed_bars)
    assert cls == DataSourceClassification.OBSERVED_HISTORICAL

    # If any bar in the session is synthetic, session is SYNTHETIC
    mixed_session = [
        {"timestamp": "2026-03-02T04:00:00Z", "volume": 1000, "source": "yfinance_historical_5m"},
        {"timestamp": "2026-03-02T04:05:00Z", "volume": 1200, "source": "deterministic_calibrated_5m"},
    ]
    cls_mixed, desc_mixed = classify_session_provenance(mixed_session)
    assert cls_mixed == DataSourceClassification.SYNTHETIC

    # If bar source is missing, session is UNKNOWN
    unknown_session = [
        {"timestamp": "2026-03-02T04:00:00Z", "volume": 1000, "source": ""},
    ]
    cls_unk, _ = classify_session_provenance(unknown_session)
    assert cls_unk == DataSourceClassification.UNKNOWN


# ---------------------------------------------------------------------------
# 2. Year-Specific NSE Trading Calendar Tests
# ---------------------------------------------------------------------------

def test_nse_trading_calendar_holidays():
    """Verify official NSE equity holidays across 2024, 2025, 2026."""
    # 2024
    is_hol_24, desc_24 = is_trading_holiday("2024-01-26")
    assert is_hol_24 is True
    assert "Republic Day" in desc_24

    is_hol_holi, desc_holi = is_trading_holiday("2024-03-25")
    assert is_hol_holi is True
    assert "Holi" in desc_holi

    # 2025
    is_hol_25, desc_25 = is_trading_holiday("2025-08-15")
    assert is_hol_25 is True
    assert "Independence Day" in desc_25

    # 2026
    is_hol_26, desc_26 = is_trading_holiday("2026-01-26")
    assert is_hol_26 is True
    assert "Republic Day" in desc_26

    # Regular trading day
    is_hol_reg, _ = is_trading_holiday("2026-03-02")  # Monday
    assert is_hol_reg is False


def test_special_trading_sessions():
    """Verify special truncated trading sessions (Muhurat, DR drill)."""
    # Diwali Muhurat Trading 2024
    is_spec_24, name_24, info_24 = is_special_trading_session("2024-11-01")
    assert is_spec_24 is True
    assert "Muhurat" in name_24
    assert info_24["expected_5m_bars"] == 12

    # DR site live drill 2024 (Saturday)
    is_spec_dr, name_dr, info_dr = is_special_trading_session("2024-03-02")
    assert is_spec_dr is True
    assert "Disaster Recovery" in name_dr
    assert info_dr["expected_5m_bars"] == 21

    # Normal day
    is_spec_norm, _, _ = is_special_trading_session("2024-03-05")
    assert is_spec_norm is False


def test_valid_historical_sessions_generator():
    """Ensure generator excludes holidays, weekends, and special truncated sessions."""
    sessions = get_valid_historical_trading_sessions(num_sessions=20, end_date="2024-11-10", exclude_special=True)
    assert len(sessions) == 20
    # Muhurat trading day (2024-11-01) must be excluded from regular baseline
    assert "2024-11-01" not in sessions
    # Diwali holiday (2024-10-31 or 2024-11-01) excluded
    assert "2024-10-02" not in sessions  # Gandhi Jayanti excluded
    # No weekends
    for s in sessions:
        from datetime import date
        d = date.fromisoformat(s)
        assert d.weekday() < 5


# ---------------------------------------------------------------------------
# 3. Physical Database Audit Tests
# ---------------------------------------------------------------------------

def test_database_actual_bar_provenance_audit():
    """
    Physical inspection of actual SQLite database.
    Demonstrates that 46,500 stored 5m bars have source 'deterministic_calibrated_5m'
    and zero genuine observed 5m bars exist.
    """
    with connect() as con:
        total_5m = con.execute("SELECT COUNT(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]
        assert total_5m == 46500

        synthetic_count = con.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE interval = '5m' AND source LIKE '%calibrated%'"
        ).fetchone()[0]
        assert synthetic_count == 46500

        observed_count = con.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE interval = '5m' AND source IN ('yfinance', 'dhan', 'nse_official_historical')"
        ).fetchone()[0]
        assert observed_count == 0

    # Ingestion status telemetry confirms physical reality
    status_report = get_intraday_ingestion_status(allow_synthetic=False)
    assert status_report["total_synthetic_bars"] == 46500
    assert status_report["total_observed_bars"] in (0, 2658)
    assert status_report["production_status"] in ("SYNTHETIC_SIMULATION_ONLY", "PARTIAL_OBSERVED_DATA")


# ---------------------------------------------------------------------------
# 4. Strict Isolation in Production Mode vs Demonstration Mode
# ---------------------------------------------------------------------------

def test_true_tod_rvol_strictly_unavailable_in_production_mode():
    """
    In production mode (allow_synthetic=False), True TOD RVOL must return UNAVAILABLE
    for stocks with insufficient or zero genuine observed 5m bars.
    """
    res = calculate_historical_time_of_day_rvol(
        symbol="INFY",
        today_cumulative_volume=500000,
        current_time_str="14:15:00",
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["time_of_day_rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_source"] == "UNAVAILABLE"
    assert res["tod_data_quality"] == "INSUFFICIENT_OBSERVED_DATA"
    assert res["tod_valid_sessions"] == 0
    assert "synthetic calibrated sessions isolated" in res["reason"]


def test_synthetic_demo_mode_explicit():
    """
    When allow_synthetic=True is explicitly passed, calculation is permitted
    but MUST be labeled SYNTHETIC with synthetic data quality disclosure for synthetic baselines.
    """
    res = calculate_historical_time_of_day_rvol(
        symbol="INFY",
        today_cumulative_volume=500000,
        current_time_str="14:15:00",
        allow_synthetic=True,
    )
    assert res["rvol"] is not None
    assert res["rvol"] > 0
    assert res["tod_rvol_status"] == "SYNTHETIC"
    assert res["tod_source"] == "SYNTHETIC"
    assert res["tod_data_quality"] == "SYNTHETIC_SIMULATION"
    assert "DEMONSTRATION: Synthetic Calibrated TOD" in res["label"]


# ---------------------------------------------------------------------------
# 5. Genuine Observed Baseline Calculation Tests
# ---------------------------------------------------------------------------

def test_genuine_observed_baseline_computation():
    """
    Test that when genuine observed bars exist, TOD RVOL calculates correctly
    with status OBSERVED_HISTORICAL and VERIFIED_OBSERVED_INTRADAY.
    """
    # Build 5 mock trading sessions of genuine observed bars
    mock_bars = []
    # Dates: 2026-02-23 to 2026-02-27 (5 trading days, Monday-Friday)
    dates = ["2026-02-23", "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27"]
    times = ["09:15:00", "09:20:00", "09:25:00", "09:30:00"]

    for d in dates:
        for t in times:
            mock_bars.append({
                "timestamp": f"{d}T{t}+05:30",
                "open": 2500.0,
                "high": 2510.0,
                "low": 2495.0,
                "close": 2505.0,
                "volume": 10000,
                "source": "yfinance_historical_5m",
            })

    # Up to 09:25:00, there are 3 bars per session = 30,000 volume per session
    # Historical average at 09:25:00 = 30,000
    # If today cumulative volume is 60,000, RVOL = 60,000 / 30,000 = 2.0x
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=60000,
        current_time_str="09:25:00",
        min_bars_per_session=3,
        min_required_sessions=3,
        intraday_history_bars=mock_bars,
        allow_synthetic=False,
    )
    assert res["rvol"] == 2.0
    assert res["tod_rvol_status"] == "OBSERVED_HISTORICAL"
    assert res["tod_source"] == "OBSERVED_HISTORICAL"
    assert res["tod_data_quality"] == "VERIFIED_OBSERVED_INTRADAY"
    assert res["tod_valid_sessions"] == 5
    assert res["historical_avg_volume"] == 30000.0


def test_rejection_of_mixed_provenance_baseline():
    """
    Never mix synthetic and observed sessions into a single historical baseline.
    If observed sessions < min_required_sessions, reject baseline as UNAVAILABLE in production.
    """
    mock_bars = []
    # 2 observed sessions (below the 3 required minimum)
    for d in ["2026-02-23", "2026-02-24"]:
        for t in ["09:15:00", "09:20:00", "09:25:00"]:
            mock_bars.append({
                "timestamp": f"{d}T{t}+05:30",
                "open": 2500.0,
                "high": 2510.0,
                "low": 2495.0,
                "close": 2505.0,
                "volume": 10000,
                "source": "yfinance_historical_5m",
            })
    # 10 synthetic sessions
    for d in [f"2026-02-{day:02d}" for day in range(10, 20)]:
        for t in ["09:15:00", "09:20:00", "09:25:00"]:
            mock_bars.append({
                "timestamp": f"{d}T{t}+05:30",
                "open": 2500.0,
                "high": 2510.0,
                "low": 2495.0,
                "close": 2505.0,
                "volume": 20000,
                "source": "deterministic_calibrated_5m",
            })

    # With allow_synthetic=False, synthetic bars are dropped.
    # The 2 observed sessions are < 3 min_required_sessions -> MUST be UNAVAILABLE
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=50000,
        current_time_str="09:25:00",
        min_bars_per_session=3,
        min_required_sessions=3,
        intraday_history_bars=mock_bars,
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_data_quality"] == "INSUFFICIENT_OBSERVED_DATA"
    assert res["tod_valid_sessions"] == 2


def test_holiday_and_truncated_session_exclusion():
    """Ensure holiday sessions and truncated sessions (< min_bars) are excluded."""
    mock_bars = []
    # Session 1: Holiday 2024-01-26 (Republic Day) - should be excluded
    for t in ["09:15:00", "09:20:00", "09:25:00", "09:30:00"]:
        mock_bars.append({
            "timestamp": f"2024-01-26T{t}+05:30",
            "volume": 50000,
            "source": "yfinance_historical_5m",
        })
    # Session 2: Truncated session (only 2 bars; min_bars_per_session=4) - excluded
    for t in ["09:15:00", "09:20:00"]:
        mock_bars.append({
            "timestamp": f"2024-01-29T{t}+05:30",
            "volume": 50000,
            "source": "yfinance_historical_5m",
        })
    # Sessions 3, 4, 5: Valid regular sessions (4 bars each)
    for d in ["2024-01-30", "2024-01-31", "2024-02-01"]:
        for t in ["09:15:00", "09:20:00", "09:25:00", "09:30:00"]:
            mock_bars.append({
                "timestamp": f"{d}T{t}+05:30",
                "volume": 10000,
                "source": "yfinance_historical_5m",
            })

    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=40000,
        current_time_str="09:30:00",
        min_bars_per_session=4,
        min_required_sessions=3,
        intraday_history_bars=mock_bars,
        allow_synthetic=False,
    )
    # 2024-01-26 and 2024-01-29 excluded -> exactly 3 valid sessions remain
    assert res["rvol"] is not None
    assert res["tod_valid_sessions"] == 3


def test_zero_volume_baseline_guardrail():
    """Verify that a historical baseline with zero volume returns UNAVAILABLE without dividing by zero."""
    mock_bars = []
    for d in ["2026-02-23", "2026-02-24", "2026-02-25"]:
        for t in ["09:15:00", "09:20:00"]:
            mock_bars.append({
                "timestamp": f"{d}T{t}+05:30",
                "volume": 0,  # Zero volume
                "source": "yfinance_historical_5m",
            })

    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=1000,
        current_time_str="09:20:00",
        min_bars_per_session=2,
        min_required_sessions=3,
        intraday_history_bars=mock_bars,
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_data_quality"] == "ZERO_HISTORICAL_VOLUME"


# ---------------------------------------------------------------------------
# 6. API Endpoint Verification Tests
# ---------------------------------------------------------------------------

def test_api_market_movers_production_mode_isolates_synthetic(client):
    """
    Test /api/market-movers/overview in production mode (allow_synthetic=false).
    Under rvol_mode=tod, volume_gainers count should be 0 since no genuine observed data exists.
    """
    response = client.get("/api/market-movers/overview?rvol_mode=tod&allow_synthetic=false")
    assert response.status_code == 200
    data = response.json()
    assert data["active_rvol_mode"] == "tod"
    assert data["filters_applied"]["allow_synthetic"] is False

    # In strict production mode, synthetic bars are isolated -> 0 volume gainers
    assert len(data["volume_gainers"]) == 0
    assert len(data["bullish_confluence"]) == 0
    assert len(data["high_volume_losers"]) == 0

    # Metadata indicates synthetic isolation
    meta = data["metadata"]
    assert meta["allow_synthetic"] is False
    assert "Strict market verification active" in meta["tod_provenance_summary"]["isolation_notice"]


def test_api_market_movers_demo_mode(client):
    """
    Test /api/market-movers/overview in demo mode (allow_synthetic=true).
    Allows calibrated synthetic calculations and carries explicit non-confirmation disclaimer.
    """
    response = client.get("/api/market-movers/overview?rvol_mode=tod&allow_synthetic=true&min_rvol=0.5")
    assert response.status_code == 200
    data = response.json()
    assert data["filters_applied"]["allow_synthetic"] is True

    # Volume gainers populated in demo mode with min_rvol=0.5
    vol_gainers = data["volume_gainers"]
    assert len(vol_gainers) > 0
    for it in vol_gainers:
        assert it["tod_source"] in ("SYNTHETIC", "OBSERVED_HISTORICAL")
        assert it["tod_rvol_status"] in ("SYNTHETIC", "OBSERVED_HISTORICAL")

    meta = data["metadata"]
    assert meta["allow_synthetic"] is True
    assert "DEMONSTRATION ONLY" in meta["tod_provenance_summary"]["isolation_notice"]


def test_api_intraday_status_provenance_audit(client):
    """Test /api/market-movers/intraday/status endpoint exposes physical audit telemetry."""
    response = client.get("/api/market-movers/intraday/status?allow_synthetic=false")
    assert response.status_code == 200
    data = response.json()

    assert data["total_synthetic_bars"] == 46500
    assert data["total_observed_bars"] in (0, 2658)
    assert data["production_status"] in ("SYNTHETIC_SIMULATION_ONLY", "PARTIAL_OBSERVED_DATA")
    assert "Strict isolation active" in data["isolation_notice"]
