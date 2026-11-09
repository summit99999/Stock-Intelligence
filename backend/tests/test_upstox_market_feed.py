"""
Unit and integration tests for Upstox Market Feed, WebSocket client, and instrument resolution.

Designed to execute completely offline without network access:
- Deterministic Upstox instrument key resolution (NSE_EQ|{ISIN} and NSE_INDEX)
- UpstoxMarketService quote cache and tick calculations
- UpstoxWebSocketClient state transitions and subscriptions
- Market feed router endpoints
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.upstox_market import LiveQuote
from app.services.upstox_instrument_service import get_upstox_instrument_service
from app.services.upstox_market_service import UpstoxMarketService
from app.services.upstox_ws_client import UpstoxWebSocketClient
from app.routers.market_feed import get_live_feed_status


class TestUpstoxInstrumentResolution:
    """Verifies symbol to Upstox instrument key resolution."""

    def test_equity_isin_mapping(self):
        inst_svc = get_upstox_instrument_service()

        rel_key = inst_svc.get_instrument_key("RELIANCE")
        assert rel_key == "NSE_EQ|INE002A01018"
        assert inst_svc.get_symbol_by_key(rel_key) == "RELIANCE"

        tcs_key = inst_svc.get_instrument_key("TCS")
        assert tcs_key == "NSE_EQ|INE467B01029"
        assert inst_svc.get_symbol_by_key(tcs_key) == "TCS"

        hdfc_key = inst_svc.get_instrument_key("HDFCBANK")
        assert hdfc_key == "NSE_EQ|INE040A01034"
        assert inst_svc.get_symbol_by_key(hdfc_key) == "HDFCBANK"

    def test_indices_mapping(self):
        inst_svc = get_upstox_instrument_service()

        nifty_key = inst_svc.get_instrument_key("NIFTY 50")
        assert nifty_key == "NSE_INDEX|Nifty 50"
        assert inst_svc.get_symbol_by_key(nifty_key) == "NIFTY 50"

        bank_key = inst_svc.get_instrument_key("NIFTY BANK")
        assert bank_key == "NSE_INDEX|Nifty Bank"

    def test_lineage_separation(self):
        """TMPV and TMCV must have distinct Upstox keys and separate ISINs."""
        inst_svc = get_upstox_instrument_service()
        tmpv_key = inst_svc.get_instrument_key("TMPV")
        tmcv_key = inst_svc.get_instrument_key("TMCV")

        assert tmpv_key is not None
        assert tmcv_key is not None
        assert tmpv_key != tmcv_key


class TestUpstoxMarketService:
    """Verifies quote cache, fallback quote generation, and tick updates."""

    def test_fallback_quotes_generation(self):
        svc = UpstoxMarketService()
        fallback = svc._generate_fallback_quotes(["RELIANCE", "TCS"])
        assert "RELIANCE" in fallback
        assert "TCS" in fallback

        rel = fallback["RELIANCE"]
        assert rel.symbol == "RELIANCE"
        assert rel.source == "DEMO"
        assert rel.ltp > 0
        assert rel.security_id == "NSE_EQ|INE002A01018"

    def test_tick_update_and_cache(self):
        svc = UpstoxMarketService()
        svc.update_cache_from_tick(
            symbol="INFY",
            ltp=1550.0,
            volume=500000,
            high=1560.0,
            low=1540.0,
            close=1520.0,
        )

        quote = svc.get_cached_quote("INFY")
        assert quote is not None
        assert quote.symbol == "INFY"
        assert quote.ltp == 1550.0
        assert quote.change == 30.0
        assert quote.source == "LIVE"
        assert quote.high == 1560.0
        assert quote.low == 1540.0

    def test_quote_cache_multi_symbol(self):
        svc = UpstoxMarketService()
        svc.update_cache_from_tick("TCS", 3500.0)
        svc.update_cache_from_tick("RELIANCE", 2900.0)

        all_quotes = svc.get_all_cached_quotes()
        assert "TCS" in all_quotes
        assert "RELIANCE" in all_quotes
        assert all_quotes["TCS"].ltp == 3500.0
        assert all_quotes["RELIANCE"].ltp == 2900.0


class TestUpstoxWebSocketClient:
    """Verifies client lifecycle and status tracking."""

    def test_initial_feed_status(self):
        client = UpstoxWebSocketClient()
        status = client.get_feed_status()
        assert status is not None
        assert isinstance(status.subscribed_symbols, list)
        assert status.connected_clients == 0

    def test_set_disabled(self):
        client = UpstoxWebSocketClient()
        client.set_disabled()
        assert client.status == "DISABLED"


class TestMarketFeedRouter:
    """Verifies market feed endpoints."""

    def test_live_feed_status_endpoint(self):
        st = get_live_feed_status()
        assert hasattr(st, "status")
        assert hasattr(st, "authenticated")
        assert hasattr(st, "subscribed_symbols")
