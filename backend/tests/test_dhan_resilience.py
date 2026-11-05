"""
Comprehensive test suite for Dhan WebSocket Reconnection Loop Fix, HTTP 429 Handling,
and Fundamental Screening Preservation.

Covers:
1. Live data disabled at startup (DHAN_LIVE_DATA_ENABLED=false).
2. No WebSocket connection established when disabled.
3. HTTP 429 detection and RATE_LIMITED status handling.
4. Exponential backoff with jitter and Retry-After header parsing.
5. Consecutive 429 threshold pausing aggressive reconnect loops.
6. Manual reconnect mechanism (POST /api/market/live/reconnect and client.manual_reconnect).
7. Complete Fundamental API and Stock Screener availability when Dhan live feed is disabled.
8. Accurate LIVE / DEMO / DISABLED / RATE_LIMITED status reporting.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.config import DhanConfig, get_dhan_config
from app.main import app
from app.schemas.dhan_market import LiveFeedStatus
from app.services.dhan_ws_client import DhanWebSocketClient, get_dhan_ws_client


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Configuration & Startup Tests
# ---------------------------------------------------------------------------

class TestDhanLiveDataConfig:
    """Tests for DHAN_LIVE_DATA_ENABLED configuration."""

    def test_live_data_disabled_by_default(self):
        cfg = DhanConfig(client_id="id", api_key="k", api_secret="s")
        assert cfg.live_data_enabled is False

    def test_live_data_enabled_flag(self):
        cfg = DhanConfig(client_id="id", api_key="k", api_secret="s", live_data_enabled=True)
        assert cfg.live_data_enabled is True

    def test_get_dhan_config_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "false")
        cfg = get_dhan_config()
        assert cfg.live_data_enabled is False

        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "true")
        cfg_enabled = get_dhan_config()
        assert cfg_enabled.live_data_enabled is True

    def test_live_data_disabled_at_startup_sets_disabled_status(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "false")
        ws_client = DhanWebSocketClient()
        ws_client.start()

        assert ws_client.status == "DISABLED"
        assert ws_client.is_connected is False
        feed_st = ws_client.get_feed_status()
        assert feed_st.status == "DISABLED"
        assert feed_st.live_data_enabled is False


# ---------------------------------------------------------------------------
# 2. No Connection When Disabled
# ---------------------------------------------------------------------------

class TestNoConnectionWhenDisabled:
    """Verifies no network/WebSocket calls are initiated when disabled."""

    @pytest.mark.asyncio
    async def test_no_websocket_connect_called_when_disabled(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "false")
        ws_client = DhanWebSocketClient()

        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            ws_client.start()
            # Allow brief asyncio cycle
            await asyncio.sleep(0.05)

            mock_connect.assert_not_called()
            assert ws_client.status == "DISABLED"
            await ws_client.stop()


# ---------------------------------------------------------------------------
# 3. HTTP 429 Handling & Exponential Backoff
# ---------------------------------------------------------------------------

class TestHttp429AndBackoff:
    """Tests for HTTP 429 Rate Limit detection, status update, and backoff."""

    @pytest.mark.asyncio
    async def test_http_429_sets_rate_limited_status(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "true")
        ws_client = DhanWebSocketClient()
        ws_client._running = True

        mock_token = MagicMock()
        mock_token.access_token = "valid_token"
        mock_token.is_expired = False

        class Mock429Exception(Exception):
            status_code = 429

        async def stop_after_sleep(sec):
            ws_client._running = False

        with patch("app.services.dhan_ws_client.get_token", return_value=mock_token), \
             patch("app.services.token_store.get_token", return_value=mock_token), \
             patch("app.services.dhan_ws_client.get_dhan_config", return_value=DhanConfig(client_id="123", live_data_enabled=True)), \
             patch("websockets.connect", side_effect=Mock429Exception("server rejected WebSocket connection: HTTP 429")), \
             patch("asyncio.sleep", side_effect=stop_after_sleep) as mock_sleep:

            task = asyncio.create_task(ws_client._run_loop())
            await task

            assert ws_client.status == "RATE_LIMITED"
            assert "429" in (ws_client._last_error or "")
            assert ws_client._consecutive_429 >= 1
            assert ws_client._retry_in_seconds is not None
            assert ws_client._retry_in_seconds >= 30.0

            assert mock_sleep.called
            slept_seconds = mock_sleep.call_args[0][0]
            assert slept_seconds >= 30.0

    @pytest.mark.asyncio
    async def test_http_429_respects_retry_after_header(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "true")
        ws_client = DhanWebSocketClient()
        ws_client._running = True

        mock_token = MagicMock()
        mock_token.access_token = "valid_token"
        mock_token.is_expired = False

        class MockResponse:
            status_code = 429
            headers = {"Retry-After": "45"}

        class MockExceptionWithResp(Exception):
            response = MockResponse()

        async def stop_after_sleep(sec):
            ws_client._running = False

        with patch("app.services.dhan_ws_client.get_token", return_value=mock_token), \
             patch("app.services.token_store.get_token", return_value=mock_token), \
             patch("app.services.dhan_ws_client.get_dhan_config", return_value=DhanConfig(client_id="123", live_data_enabled=True)), \
             patch("websockets.connect", side_effect=MockExceptionWithResp("HTTP 429")), \
             patch("asyncio.sleep", side_effect=stop_after_sleep) as mock_sleep:

            task = asyncio.create_task(ws_client._run_loop())
            await task

            assert ws_client.status == "RATE_LIMITED"
            assert ws_client._retry_in_seconds == 45.0
            mock_sleep.assert_called_with(45.0)

    @pytest.mark.asyncio
    async def test_consecutive_429_pauses_aggressive_reconnects(self, monkeypatch):
        monkeypatch.setenv("DHAN_LIVE_DATA_ENABLED", "true")
        ws_client = DhanWebSocketClient()
        ws_client._running = True
        ws_client._consecutive_429 = 4  # Reached max consecutive

        mock_token = MagicMock()
        mock_token.access_token = "valid_token"
        mock_token.is_expired = False

        async def stop_after_sleep(sec):
            ws_client._running = False

        with patch("app.services.dhan_ws_client.get_token", return_value=mock_token), \
             patch("app.services.token_store.get_token", return_value=mock_token), \
             patch("app.services.dhan_ws_client.get_dhan_config", return_value=DhanConfig(client_id="123", live_data_enabled=True)), \
             patch("websockets.connect", new_callable=AsyncMock) as mock_connect, \
             patch("asyncio.sleep", side_effect=stop_after_sleep) as mock_sleep:

            task = asyncio.create_task(ws_client._run_loop())
            await task

            # websockets.connect should NOT have been called because consecutive >= 4
            mock_connect.assert_not_called()
            assert ws_client.status == "RATE_LIMITED"
            assert "Automatic retries paused" in ws_client._last_error
            # Backed off for max_rate_limit_backoff (300s)
            mock_sleep.assert_called_with(300.0)


# ---------------------------------------------------------------------------
# 4. Manual Reconnection
# ---------------------------------------------------------------------------

class TestManualReconnection:
    """Tests manual reconnect triggers and state resetting."""

    @pytest.mark.asyncio
    async def test_manual_reconnect_resets_counters_and_retries(self):
        ws_client = DhanWebSocketClient()
        ws_client._status = "RATE_LIMITED"
        ws_client._consecutive_429 = 5
        ws_client._retry_in_seconds = 120.0
        ws_client._last_error = "Server 429"

        with patch.object(ws_client, "start") as mock_start:
            st = await ws_client.manual_reconnect(force=True, enable=True)

            assert ws_client._consecutive_429 == 0
            assert ws_client._retry_in_seconds is None
            assert ws_client._last_error is None
            assert ws_client._force_enabled is True
            mock_start.assert_called_with(force=True)

    def test_api_reconnect_endpoint(self, client):
        resp = client.post("/api/market/live/reconnect?force=true&enable=true")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "authenticated" in data
        assert "live_data_enabled" in data


# ---------------------------------------------------------------------------
# 5. Status Diagnostics & REST Endpoints
# ---------------------------------------------------------------------------

class TestStatusAndRestAccuracy:
    """Verifies LIVE / DEMO / DISABLED status reporting accuracy."""

    def test_status_endpoint_reports_disabled_accurately(self, client, monkeypatch):
        ws_client = get_dhan_ws_client()
        ws_client.set_disabled()

        resp = client.get("/api/market/live/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "DISABLED"
        assert data["live_data_enabled"] is False

    def test_quotes_endpoint_reports_demo_when_disabled(self, client):
        ws_client = get_dhan_ws_client()
        ws_client.set_disabled()

        resp = client.get("/api/market/live/quotes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] in ("DEMO", "HISTORICAL")
        for sym, q in data["quotes"].items():
            assert q["source"] in ("DEMO", "HISTORICAL")


# ---------------------------------------------------------------------------
# 6. Fundamental Screening Preservation
# ---------------------------------------------------------------------------

class TestFundamentalScreeningPreservedWhenDisabled:
    """Verifies that all fundamental analysis, screening, and dossiers remain operational."""

    def test_company_research_tcs_available(self, client):
        resp = client.get("/api/fundamentals/company/TCS/research")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "TCS"
        assert data["quality_score"] is not None
        assert data["quality_score"]["total_score"] > 0
        assert len(data["annual_income_statements"]) >= 3

    def test_screener_presets_available(self, client):
        resp = client.get("/api/screener/presets/default")
        assert resp.status_code == 200
        presets = resp.json()
        assert len(presets) == 8

    def test_screener_run_available(self, client):
        resp = client.post("/api/screener/run", json={"page_size": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) > 0

    def test_stock_master_list_available(self, client):
        resp = client.get("/api/stocks")
        assert resp.status_code == 200
        stocks = resp.json()
        items = stocks.get("items", [])
        assert len(items) >= 30
