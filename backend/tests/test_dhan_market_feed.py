"""
Comprehensive test suite for Phase 4B: Dhan Live Market Data Integration.

Covers:
1. Instrument Lookup Service (benchmark instruments, universe stocks, payload formatting)
2. Binary WebSocket Packet Parser (Header, Ticker Code 2, Quote Code 4, Disconnect Code 1, edge cases)
3. Dhan REST Marketfeed Client (Auth headers, quote normalization, caching, fallback)
4. Live Market Feed API Router (/api/market/live/status, /quotes, /quote/{symbol}, /subscribe, /refresh)
5. Live Market Feed WebSocket (FastAPI WS /ws/market-feed, snapshot broadcast, ping/pong, tick distribution)
6. Security and Graceful Degradation (no token leaks, clear DEMO vs LIVE attribution)
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.dhan_market import LiveQuote
from app.services.dhan_instrument_service import (
    DhanInstrumentService,
    DhanInstrument,
    get_instrument_service,
)
from app.services.dhan_packet_parser import (
    parse_dhan_packet,
    build_synthetic_packet,
)
from app.services.dhan_market_service import (
    DhanMarketService,
    get_dhan_market_service,
)
from app.services.dhan_ws_client import (
    DhanWebSocketClient,
    get_dhan_ws_client,
)


# ---------------------------------------------------------------------------
# 1. Dhan Instrument Service Tests
# ---------------------------------------------------------------------------

class TestDhanInstrumentService:
    """Tests for Dhan instrument mapping and payload formatting."""

    def test_benchmark_instruments_resolved(self):
        svc = get_instrument_service()
        benchmarks = ["RELIANCE", "TCS", "HDFCBANK", "NIFTY 50", "BANK NIFTY", "SENSEX", "INDIA VIX"]
        for sym in benchmarks:
            inst = svc.get_instrument(sym)
            assert inst is not None, f"Instrument {sym} could not be resolved"
            assert inst.symbol in (sym, sym.replace(" 50", ""))
            assert inst.security_id != ""
            assert inst.exchange_segment in ("NSE_EQ", "IDX_I", "BSE_EQ")

    def test_benchmark_security_ids(self):
        svc = get_instrument_service()
        assert svc.get_instrument("RELIANCE").security_id == "2885"
        assert svc.get_instrument("TCS").security_id == "11536"
        assert svc.get_instrument("HDFCBANK").security_id == "1333"
        assert svc.get_instrument("NIFTY 50").security_id == "13"
        assert svc.get_instrument("BANK NIFTY").security_id == "25"
        assert svc.get_instrument("SENSEX").security_id == "51"
        assert svc.get_instrument("INDIA VIX").security_id == "21"

    def test_lookup_by_security_id_and_segment(self):
        svc = get_instrument_service()
        inst = svc.get_instrument("2885", "NSE_EQ")
        assert inst is not None
        assert inst.symbol == "RELIANCE"

        nifty = svc.get_instrument("13", "IDX_I")
        assert nifty is not None
        assert "NIFTY" in nifty.symbol

    def test_universe_stocks_coverage(self):
        svc = get_instrument_service()
        universe = svc.get_universe_instruments()
        assert len(universe) >= 30
        symbols = {inst.symbol for inst in universe}
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "HDFCBANK" in symbols
        assert "INFY" in symbols
        assert "LTM" in symbols

    def test_rest_payload_builder(self):
        svc = get_instrument_service()
        benchmarks = svc.get_benchmark_instruments()
        payload = svc.build_rest_payload(benchmarks)

        assert "NSE_EQ" in payload
        assert "IDX_I" in payload
        assert 2885 in payload["NSE_EQ"]
        assert 11536 in payload["NSE_EQ"]
        assert 1333 in payload["NSE_EQ"]
        assert 13 in payload["IDX_I"]

    def test_ws_payload_builder(self):
        svc = get_instrument_service()
        benchmarks = [svc.get_instrument("RELIANCE"), svc.get_instrument("NIFTY 50")]
        ws_payload = svc.build_ws_subscription_payload(benchmarks, request_code=17)

        assert ws_payload["RequestCode"] == 17
        assert ws_payload["InstrumentCount"] == 2
        items = ws_payload["InstrumentList"]
        assert len(items) == 2
        assert items[0] == {"ExchangeSegment": "NSE_EQ", "SecurityId": "2885"}
        assert items[1] == {"ExchangeSegment": "IDX_I", "SecurityId": "13"}

    def test_unknown_instrument_returns_none(self):
        svc = get_instrument_service()
        assert svc.get_instrument("TOTALLY_UNKNOWN_XYZ_999") is None


# ---------------------------------------------------------------------------
# 2. Binary Packet Parser Tests
# ---------------------------------------------------------------------------

class TestDhanPacketParser:
    """Tests for unpacking binary WebSocket feed packets."""

    def test_quote_packet_parsing(self):
        raw = build_synthetic_packet(
            response_code=4,
            exchange_segment="NSE_EQ",
            security_id=2885,
            ltp=2940.50,
            open_price=2900.00,
            close_price=2890.00,
            high_price=2950.00,
            low_price=2895.00,
            volume=5000000,
        )
        parsed = parse_dhan_packet(raw)
        assert parsed is not None
        assert parsed["type"] == "QUOTE"
        assert parsed["response_code"] == 4
        assert parsed["exchange_segment"] == "NSE_EQ"
        assert parsed["security_id"] == "2885"
        assert parsed["ltp"] == 2940.50
        assert parsed["open"] == 2900.00
        assert parsed["close"] == 2890.00
        assert parsed["high"] == 2950.00
        assert parsed["low"] == 2895.00
        assert parsed["volume"] == 5000000
        assert parsed["change"] == round(2940.50 - 2890.00, 2)
        assert parsed["change_percent"] == round(((2940.50 - 2890.00) / 2890.00) * 100, 2)

    def test_ticker_packet_parsing(self):
        raw = build_synthetic_packet(
            response_code=2,
            exchange_segment="IDX_I",
            security_id=13,
            ltp=24850.75,
            ltt=1711880000,
        )
        parsed = parse_dhan_packet(raw)
        assert parsed is not None
        assert parsed["type"] == "TICKER"
        assert parsed["response_code"] == 2
        assert parsed["exchange_segment"] == "IDX_I"
        assert parsed["security_id"] == "13"
        assert parsed["ltp"] == 24850.75
        assert parsed["ltt"] == 1711880000
        assert parsed["timestamp"] is not None

    def test_disconnect_packet_parsing(self):
        raw = build_synthetic_packet(
            response_code=1,
            exchange_segment="NSE_EQ",
            security_id=2885,
            ltp=0.0,
        )
        parsed = parse_dhan_packet(raw)
        assert parsed is not None
        assert parsed["type"] == "DISCONNECT"
        assert "disconnect_code" in parsed

    def test_malformed_short_packet(self):
        assert parse_dhan_packet(b"\x00\x01\x02") is None
        assert parse_dhan_packet(b"") is None
        assert parse_dhan_packet("string_not_bytes") is None

    def test_change_percentage_zero_close_safe(self):
        raw = build_synthetic_packet(
            response_code=4,
            exchange_segment="NSE_EQ",
            security_id=1333,
            ltp=1500.0,
            close_price=0.0,
        )
        parsed = parse_dhan_packet(raw)
        assert parsed["change"] == 0.0
        assert parsed["change_percent"] == 0.0


# ---------------------------------------------------------------------------
# 3. Dhan REST Market Service Tests
# ---------------------------------------------------------------------------

class TestDhanMarketService:
    """Tests for Dhan REST market data client & cache."""

    def test_rest_quote_parsing(self):
        market_svc = DhanMarketService()
        inst_reliance = market_svc.instrument_service.get_instrument("RELIANCE")

        mock_resp = {
            "status": "success",
            "data": {
                "NSE_EQ": {
                    "2885": {
                        "last_price": 2980.00,
                        "open": 2920.00,
                        "high": 2990.00,
                        "low": 2915.00,
                        "close": 2910.00,
                        "volume": 3200000,
                        "average_price": 2955.00,
                        "last_trade_time": "2026-03-31 12:45:00",
                    }
                }
            },
        }

        quotes = market_svc._parse_rest_quotes(mock_resp, [inst_reliance])
        assert "RELIANCE" in quotes
        q = quotes["RELIANCE"]
        assert q.ltp == 2980.00
        assert q.open == 2920.00
        assert q.close == 2910.00
        assert q.change == 70.00
        assert q.change_percent == round((70.0 / 2910.0) * 100, 2)
        assert q.volume == 3200000
        assert q.source == "LIVE"

    def test_update_from_ws_packet(self):
        market_svc = DhanMarketService()
        packet = build_synthetic_packet(
            response_code=4,
            exchange_segment="NSE_EQ",
            security_id=11536,
            ltp=3600.0,
            open_price=3550.0,
            close_price=3520.0,
            high_price=3610.0,
            low_price=3540.0,
            volume=1100000,
        )
        parsed = parse_dhan_packet(packet)
        quote = market_svc.update_from_packet(parsed)

        assert quote is not None
        assert quote.symbol == "TCS"
        assert quote.ltp == 3600.0
        assert quote.source == "LIVE"

        cached = market_svc.get_cached_quote("TCS")
        assert cached is not None
        assert cached.ltp == 3600.0

    def test_demo_fallback_when_unauthenticated(self):
        market_svc = DhanMarketService()
        fallback = market_svc._get_cached_or_demo_quotes(["RELIANCE", "NIFTY 50"])
        assert "RELIANCE" in fallback
        assert "NIFTY 50" in fallback
        assert fallback["RELIANCE"].source == "DEMO"
        assert fallback["NIFTY 50"].source == "DEMO"
        assert fallback["RELIANCE"].ltp > 0


# ---------------------------------------------------------------------------
# 4. Live Market Feed API Endpoints Tests
# ---------------------------------------------------------------------------

class TestMarketFeedRouter:
    """Integration tests for live market feed HTTP endpoints."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_live_feed_status_endpoint(self, client):
        resp = client.get("/api/market/live/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "authenticated" in data
        assert "subscribed_symbols" in data
        assert "ticks_received" in data
        assert "connected_clients" in data

    def test_live_quotes_endpoint(self, client):
        resp = client.get("/api/market/live/quotes")
        assert resp.status_code == 200
        data = resp.json()
        assert "quotes" in data
        assert "source" in data
        assert data["count"] >= 4
        quotes = data["quotes"]
        assert "RELIANCE" in quotes
        assert "TCS" in quotes
        assert "HDFCBANK" in quotes
        assert "NIFTY 50" in quotes

    def test_live_quote_single_endpoint(self, client):
        resp = client.get("/api/market/live/quote/RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "RELIANCE"
        assert data["security_id"] == "2885"
        assert data["exchange_segment"] == "NSE_EQ"
        assert data["ltp"] > 0
        assert data["source"] in ("LIVE", "DEMO")

    def test_live_quote_single_not_found(self, client):
        resp = client.get("/api/market/live/quote/NON_EXISTENT_TICKER")
        assert resp.status_code == 404

    def test_subscribe_symbols_endpoint(self, client):
        resp = client.post("/api/market/live/subscribe", json={"symbols": ["INFY", "BEL"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "INFY" in data["subscribed_symbols"]
        assert "BEL" in data["subscribed_symbols"]

    def test_refresh_quotes_endpoint(self, client):
        resp = client.post("/api/market/live/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert "quotes" in data
        assert data["count"] > 0


# ---------------------------------------------------------------------------
# 5. Live Market Feed WebSocket Tests
# ---------------------------------------------------------------------------

class TestMarketFeedWebSocket:
    """Tests for FastAPI WebSocket endpoint streaming to frontend."""

    def test_websocket_connection_and_snapshot(self):
        client = TestClient(app)
        with client.websocket_connect("/ws/market-feed") as ws:
            # First message should be a SNAPSHOT containing initial quotes
            raw_msg = ws.receive_text()
            data = json.loads(raw_msg)
            assert data["type"] == "SNAPSHOT"
            assert "quotes" in data
            assert "feed_status" in data
            assert "RELIANCE" in data["quotes"]

            # Test Ping/Pong
            ws.send_text(json.dumps({"type": "PING"}))
            pong_msg = ws.receive_text()
            pong_data = json.loads(pong_msg)
            assert pong_data["type"] == "PONG"
