"""
Tests for Upstox Market Data Diagnostics and Market Hours Intelligence (Phase 8 & 10).
"""

from __future__ import annotations

import datetime

from app.routers.market_feed import get_market_data_health
from app.services.upstox_ws_client import (
    get_market_hours_status,
    get_upstox_ws_client,
    IST_TZ,
)
from app.schemas.upstox_market import MarketDataHealthDiagnostics


class TestMarketHoursStatus:
    """Test NSE market hours and calendar logic."""

    def test_market_open_weekday_trading_hours(self):
        """During 09:15 to 15:30 IST on a Tuesday, market status should be OPEN."""
        # Tuesday 2026-11-10 11:30:00 IST
        mock_dt = datetime.datetime(2026, 11, 10, 11, 30, 0, tzinfo=IST_TZ)
        status, note, freshness = get_market_hours_status(now_dt=mock_dt)
        assert status == "OPEN"
        assert "open" in note.lower() or "trading" in note.lower()
        assert freshness in ("FRESH", "STALE")

    def test_market_pre_open_weekday(self):
        """Between 09:00 and 09:15 IST on a weekday, market status should be PRE_OPEN."""
        # Tuesday 2026-11-10 09:08:00 IST
        mock_dt = datetime.datetime(2026, 11, 10, 9, 8, 0, tzinfo=IST_TZ)
        status, note, freshness = get_market_hours_status(now_dt=mock_dt)
        assert status == "PRE_OPEN"
        assert "pre-open" in note.lower()

    def test_market_closed_weekday_evening(self):
        """After 15:30 IST on a weekday, market status should be CLOSED (showing session close)."""
        # Tuesday 2026-11-10 16:45:00 IST
        mock_dt = datetime.datetime(2026, 11, 10, 16, 45, 0, tzinfo=IST_TZ)
        status, note, freshness = get_market_hours_status(now_dt=mock_dt)
        assert status == "CLOSED"
        assert freshness == "SESSION_CLOSE"
        assert "closed" in note.lower()

    def test_market_closed_weekend(self):
        """On Saturday or Sunday, market status should be CLOSED (weekend)."""
        # Sunday 2026-11-08 12:00:00 IST
        mock_dt = datetime.datetime(2026, 11, 8, 12, 0, 0, tzinfo=IST_TZ)
        status, note, freshness = get_market_hours_status(now_dt=mock_dt)
        assert status == "CLOSED"
        assert "weekend" in note.lower()
        assert freshness == "SESSION_CLOSE"


class TestMarketDataHealthEndpoint:
    """Test the /api/health/market-data endpoint logic and schema."""

    def test_health_market_data_endpoint_structure(self):
        """Endpoint should conform to MarketDataHealthDiagnostics schema."""
        data = get_market_data_health()
        assert isinstance(data, MarketDataHealthDiagnostics)

        assert data.status in ("healthy", "degraded", "unhealthy")
        assert data.backend_status == "connected"
        assert data.upstox_authentication in ("AUTHENTICATED", "AUTHENTICATION_REQUIRED", "EXPIRED")
        assert data.upstox_websocket in ("CONNECTED", "CONNECTING", "DISCONNECTED", "DISABLED")
        assert data.protobuf_decoder in ("SUCCESS", "IDLE", "ERROR")
        assert data.subscription_status in ("ACTIVE", "EMPTY")
        assert isinstance(data.subscribed_instruments, int)
        assert isinstance(data.subscribed_symbols, list)
        assert data.market_status in ("OPEN", "CLOSED", "PRE_OPEN")
        assert data.server_time_ist.endswith("IST")
        assert data.database_persisted is True

    def test_health_market_data_diagnostics_method(self):
        """Direct call to UpstoxWebSocketClient.get_diagnostics() returns valid pydantic model."""
        ws_client = get_upstox_ws_client()
        diag = ws_client.get_diagnostics()
        assert isinstance(diag, MarketDataHealthDiagnostics)
        assert diag.backend_status == "connected"
        assert diag.protobuf_decoder in ("SUCCESS", "IDLE", "ERROR")
