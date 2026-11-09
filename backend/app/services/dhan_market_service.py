"""Dhan REST Marketfeed Service.

Communicates with DhanHQ REST v2 endpoints:
- POST /v2/marketfeed/quote (Full quote + OHLC + Depth)
- POST /v2/marketfeed/ohlc  (OHLC snapshot)
- POST /v2/marketfeed/ltp   (LTP snapshot)

Normalizes quotes into standard LiveQuote schemas with source attribution.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional
import httpx

from app.config import get_dhan_config
from app.schemas.dhan_market import LiveQuote
from app.services.dhan_instrument_service import (
    DhanInstrument,
    get_instrument_service,
)
from app.services.token_store import get_token

logger = logging.getLogger(__name__)

DEFAULT_DHAN_API_BASE = "https://api.dhan.co/v2"


class DhanMarketService:
    """Service to interact with Dhan REST market feed APIs."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_DHAN_API_BASE).rstrip("/")
        self.instrument_service = get_instrument_service()
        self._quote_cache: dict[str, LiveQuote] = {}

    def _get_auth_headers(self) -> Optional[dict[str, str]]:
        """Retrieve authentication headers using secure token store and config."""
        stored = get_token()
        if not stored or not stored.access_token or stored.is_expired:
            logger.warning("Valid Dhan access token not available in TokenStore")
            return None

        cfg = get_dhan_config()
        if not cfg.client_id:
            logger.warning("Dhan client_id not configured")
            return None

        return {
            "access-token": stored.access_token,
            "client-id": cfg.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def fetch_quotes(
        self,
        symbols: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, LiveQuote]:
        """
        Fetch full quotes for the specified symbols (or benchmark set by default).
        Uses POST /v2/marketfeed/quote.
        """
        from app.services.dhan_ws_client import get_dhan_ws_client

        ws_client = get_dhan_ws_client()
        cfg = get_dhan_config()
        if not cfg.live_data_enabled and not getattr(ws_client, "_force_enabled", False):
            return self._get_cached_or_demo_quotes(symbols)

        headers = self._get_auth_headers()
        if not headers:
            logger.info("No Dhan authentication available; returning cached or demo quotes")
            return self._get_cached_or_demo_quotes(symbols)

        # Resolve instruments
        instruments: list[DhanInstrument] = []
        if symbols:
            for s in symbols:
                inst = self.instrument_service.get_instrument(s)
                if inst:
                    instruments.append(inst)
        else:
            instruments = self.instrument_service.get_benchmark_instruments()

        if not instruments:
            return {}

        payload = self.instrument_service.build_rest_payload(instruments)
        url = f"{self.base_url}/marketfeed/quote"

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0)
            close_client = True

        try:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                quotes = self._parse_rest_quotes(data, instruments)
                # Update cache
                self._quote_cache.update(quotes)
                return quotes
            elif resp.status_code == 429:
                logger.warning(
                    "Dhan marketfeed/quote API returned HTTP 429 (Rate Limit / Data API inactive). Returning cached or demo quotes."
                )
                return self._get_cached_or_demo_quotes(symbols)
            else:
                logger.error(
                    f"Dhan marketfeed/quote API returned HTTP {resp.status_code}: {resp.text[:200]}"
                )
                return self._get_cached_or_demo_quotes(symbols)
        except Exception as e:
            logger.error(f"Error calling Dhan marketfeed/quote: {e}")
            return self._get_cached_or_demo_quotes(symbols)
        finally:
            if close_client:
                await client.aclose()

    async def fetch_ltp(
        self,
        symbols: Optional[list[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> dict[str, float]:
        """Fetch latest traded price for specified symbols."""
        quotes = await self.fetch_quotes(symbols=symbols, client=client)
        return {sym: q.ltp for sym, q in quotes.items()}

    def _parse_rest_quotes(
        self,
        response_json: dict[str, Any],
        requested_instruments: list[DhanInstrument],
    ) -> dict[str, LiveQuote]:
        """Normalize Dhan's marketfeed response JSON into LiveQuote models."""
        quotes: dict[str, LiveQuote] = {}
        data = response_json.get("data", {})
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Build reverse lookup: (segment, sec_id) -> instrument
        inst_by_id = {
            (inst.exchange_segment, str(inst.security_id)): inst
            for inst in requested_instruments
        }

        for segment, sec_dict in data.items():
            if not isinstance(sec_dict, dict):
                continue
            for sec_id_str, quote_data in sec_dict.items():
                if not isinstance(quote_data, dict):
                    continue

                inst = inst_by_id.get((segment, str(sec_id_str)))
                symbol = inst.symbol if inst else f"{segment}_{sec_id_str}"

                ltp = float(quote_data.get("last_price", 0.0) or 0.0)
                open_val = quote_data.get("open")
                high_val = quote_data.get("high")
                low_val = quote_data.get("low")
                close_val = quote_data.get("close")
                volume_val = quote_data.get("volume")
                atp_val = quote_data.get("average_price")
                net_change = quote_data.get("net_change")

                # If net_change is missing, compute from close
                if net_change is None and close_val and float(close_val) > 0:
                    net_change = round(ltp - float(close_val), 2)

                change_pct = None
                if close_val and float(close_val) > 0 and net_change is not None:
                    change_pct = round((float(net_change) / float(close_val)) * 100, 2)

                quote = LiveQuote(
                    symbol=symbol,
                    security_id=str(sec_id_str),
                    exchange_segment=segment,
                    ltp=ltp,
                    open=float(open_val) if open_val is not None else None,
                    high=float(high_val) if high_val is not None else None,
                    low=float(low_val) if low_val is not None else None,
                    close=float(close_val) if close_val is not None else None,
                    change=float(net_change) if net_change is not None else None,
                    change_percent=change_pct,
                    volume=int(volume_val) if volume_val is not None else None,
                    atp=float(atp_val) if atp_val is not None else None,
                    ltt=quote_data.get("last_trade_time"),
                    source="LIVE",
                    updated_at=now_str,
                )
                quotes[symbol] = quote

        return quotes

    def update_from_packet(self, parsed_packet: dict[str, Any]) -> Optional[LiveQuote]:
        """Update live quote cache from a parsed WebSocket binary packet."""
        seg = parsed_packet.get("exchange_segment")
        sec_id = parsed_packet.get("security_id")
        if not seg or not sec_id:
            return None

        exchange = parsed_packet.get("exchange")
        if not exchange:
            segment_name = str(seg).upper()
            exchange = (
                "BSE" if segment_name.startswith("BSE")
                else "NSE" if segment_name.startswith("NSE")
                else None
            )
        inst = self.instrument_service.get_instrument(
            sec_id, exchange_segment=seg, exchange=exchange
        )
        symbol = inst.symbol if inst else f"{seg}_{sec_id}"
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        existing = self._quote_cache.get(symbol)
        ltp = parsed_packet.get("ltp", existing.ltp if existing else 0.0)
        open_val = parsed_packet.get("open", existing.open if existing else None)
        high_val = parsed_packet.get("high", existing.high if existing else None)
        low_val = parsed_packet.get("low", existing.low if existing else None)
        close_val = parsed_packet.get("close", existing.close if existing else None)
        vol_val = parsed_packet.get("volume", existing.volume if existing else None)
        atp_val = parsed_packet.get("atp", existing.atp if existing else None)
        ltt_val = parsed_packet.get("timestamp", existing.ltt if existing else None)

        change = parsed_packet.get("change")
        change_pct = parsed_packet.get("change_percent")

        if change is None and close_val and close_val > 0:
            change = round(ltp - close_val, 2)
            change_pct = round((change / close_val) * 100, 2)

        quote = LiveQuote(
            symbol=symbol,
            security_id=sec_id,
            exchange_segment=seg,
            ltp=ltp,
            open=open_val,
            high=high_val,
            low=low_val,
            close=close_val,
            change=change,
            change_percent=change_pct,
            volume=vol_val,
            atp=atp_val,
            ltt=ltt_val,
            source="LIVE",
            updated_at=now_str,
        )
        self._quote_cache[symbol] = quote
        return quote

    def get_cached_quote(self, symbol: str) -> Optional[LiveQuote]:
        """Return the latest cached quote for a symbol."""
        return self._quote_cache.get(symbol.upper())

    def get_all_cached_quotes(self) -> dict[str, LiveQuote]:
        """Return all quotes currently held in cache."""
        return dict(self._quote_cache)

    def _get_cached_or_demo_quotes(self, symbols: Optional[list[str]] = None) -> dict[str, LiveQuote]:
        """Fallback quotes marked explicitly as DEMO when live credentials are not active."""
        demo_map = {
            "RELIANCE": {"ltp": 1420.50, "close": 1403.00, "open": 1405.00, "high": 1428.00, "low": 1400.00, "vol": 1250000},
            "TCS": {"ltp": 3450.00, "close": 3472.60, "open": 3470.00, "high": 3485.00, "low": 3440.00, "vol": 780000},
            "HDFCBANK": {"ltp": 1820.00, "close": 1810.00, "open": 1812.00, "high": 1835.00, "low": 1805.00, "vol": 2100000},
            "NIFTY 50": {"ltp": 24850.50, "close": 24672.85, "open": 24700.00, "high": 24890.00, "low": 24680.00, "vol": 0},
            "NIFTY": {"ltp": 24850.50, "close": 24672.85, "open": 24700.00, "high": 24890.00, "low": 24680.00, "vol": 0},
            "BANK NIFTY": {"ltp": 56240.20, "close": 55988.25, "open": 56000.00, "high": 56350.00, "low": 55950.00, "vol": 0},
            "SENSEX": {"ltp": 81450.30, "close": 81597.20, "open": 81600.00, "high": 81750.00, "low": 81380.00, "vol": 0},
            "INDIA VIX": {"ltp": 14.25, "close": 14.56, "open": 14.50, "high": 14.80, "low": 14.10, "vol": 0},
        }
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        target_keys = symbols if symbols else list(demo_map.keys())

        result: dict[str, LiveQuote] = {}
        for s in target_keys:
            key = s.upper()
            if key in self._quote_cache:
                result[key] = self._quote_cache[key]
            elif key in demo_map:
                d = demo_map[key]
                change = round(d["ltp"] - d["close"], 2)
                change_pct = round((change / d["close"]) * 100, 2)
                inst = self.instrument_service.get_instrument(key)
                result[key] = LiveQuote(
                    symbol=key,
                    security_id=inst.security_id if inst else "0",
                    exchange_segment=inst.exchange_segment if inst else "NSE_EQ",
                    ltp=d["ltp"],
                    open=d["open"],
                    high=d["high"],
                    low=d["low"],
                    close=d["close"],
                    change=change,
                    change_percent=change_pct,
                    volume=d["vol"],
                    source="DEMO",
                    updated_at=now_str,
                )
        return result


# Singleton instance
_market_service: Optional[DhanMarketService] = None


def get_dhan_market_service() -> DhanMarketService:
    """Return the global DhanMarketService singleton."""
    global _market_service
    if _market_service is None:
        _market_service = DhanMarketService()
    return _market_service
