"""Upstox REST Market Data Service.

Communicates with Upstox v2 Market Quote APIs:
- GET /v2/market-quote/quotes?instrument_key=... (Full quote + OHLC + Depth)
- GET /v2/market-quote/ohlc?instrument_key=... (OHLC snapshot)
- GET /v2/market-quote/ltp?instrument_key=...  (LTP snapshot)

Normalizes quotes into standard LiveQuote schemas with source attribution.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.config import get_upstox_config
from app.schemas.upstox_market import LiveQuote
from app.services.token_store import get_upstox_token
from app.services.upstox_instrument_service import get_upstox_instrument_service

logger = logging.getLogger(__name__)

DEFAULT_UPSTOX_API_BASE = "https://api.upstox.com/v2"
DEFAULT_BENCHMARK_SYMBOLS = ["NIFTY 50", "NIFTY BANK", "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK"]
_TIMEOUT = 15.0


class UpstoxMarketService:
    """Service to interact with Upstox REST market quote APIs and maintain quote cache."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_UPSTOX_API_BASE).rstrip("/")
        self.instrument_service = get_upstox_instrument_service()
        self._quote_cache: Dict[str, LiveQuote] = {}

    def _get_auth_headers(self) -> Optional[dict[str, str]]:
        """Retrieve authentication headers using Upstox token store."""
        stored = get_upstox_token()
        if not stored or not stored.access_token or stored.is_expired:
            return None

        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {stored.access_token}",
        }

    async def fetch_quotes(
        self,
        symbols: Optional[List[str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Dict[str, LiveQuote]:
        """
        Fetch full quotes for the specified symbols (or benchmark set by default).
        Uses GET /v2/market-quote/quotes.
        """
        target_symbols = symbols or DEFAULT_BENCHMARK_SYMBOLS
        headers = self._get_auth_headers()
        cfg = get_upstox_config()

        # If live credentials not configured or live data disabled, return demo quotes
        if not headers or not cfg.live_data_enabled:
            return self._generate_fallback_quotes(target_symbols)

        # Map symbols to Upstox instrument keys
        symbol_to_key: Dict[str, str] = {}
        key_to_symbol: Dict[str, str] = {}
        for s in target_symbols:
            key = self.instrument_service.get_instrument_key(s)
            if key:
                symbol_to_key[s] = key
                key_to_symbol[key] = s

        if not symbol_to_key:
            return self._generate_fallback_quotes(target_symbols)

        instrument_keys_param = ",".join(symbol_to_key.values())
        url = f"{self.base_url}/market-quote/quotes?instrument_key={instrument_keys_param}"

        try:
            close_client = False
            if client is None:
                client = httpx.AsyncClient(timeout=_TIMEOUT)
                close_client = True

            try:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    body = res.json()
                    data = body.get("data", {})
                    results: Dict[str, LiveQuote] = {}
                    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

                    for upstox_key, q_data in data.items():
                        # Extract or match symbol
                        symbol = q_data.get("symbol")
                        if not symbol:
                            # Try resolving from instrument_token or reverse map
                            inst_token = q_data.get("instrument_token", "")
                            symbol = key_to_symbol.get(inst_token, "")
                        if not symbol and ":" in upstox_key:
                            symbol = upstox_key.split(":")[-1]

                        if not symbol:
                            continue

                        symbol_upper = symbol.upper()
                        ohlc = q_data.get("ohlc", {}) or {}
                        ltp = float(q_data.get("last_price", 0.0) or 0.0)
                        open_p = float(ohlc.get("open", 0.0) or 0.0) if ohlc.get("open") else None
                        high_p = float(ohlc.get("high", 0.0) or 0.0) if ohlc.get("high") else None
                        low_p = float(ohlc.get("low", 0.0) or 0.0) if ohlc.get("low") else None
                        close_p = float(ohlc.get("close", 0.0) or 0.0) if ohlc.get("close") else None
                        net_change = float(q_data.get("net_change", 0.0) or 0.0)
                        change_pct = (net_change / close_p * 100) if (close_p and close_p > 0) else None

                        quote = LiveQuote(
                            symbol=symbol_upper,
                            security_id=q_data.get("instrument_token", upstox_key),
                            exchange_segment="NSE_EQ",
                            ltp=ltp,
                            open=open_p,
                            high=high_p,
                            low=low_p,
                            close=close_p,
                            change=net_change,
                            change_percent=change_pct,
                            volume=int(q_data.get("volume", 0) or 0),
                            atp=float(q_data.get("average_price", 0.0) or 0.0) if q_data.get("average_price") else None,
                            ltt=q_data.get("timestamp"),
                            source="LIVE",
                            updated_at=now_str,
                        )
                        results[symbol_upper] = quote
                        self._quote_cache[symbol_upper] = quote

                    return results
                else:
                    logger.warning("Upstox market quote HTTP %s: %s", res.status_code, res.text[:100])
                    return self._generate_fallback_quotes(target_symbols)
            finally:
                if close_client:
                    await client.aclose()
        except Exception as e:
            logger.exception("Error fetching Upstox market quotes: %s", e)
            return self._generate_fallback_quotes(target_symbols)

    def _generate_fallback_quotes(self, symbols: List[str]) -> Dict[str, LiveQuote]:
        """Generate demo quotes for offline/unconfigured environments."""
        from app.database import get_stock

        quotes: Dict[str, LiveQuote] = {}
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for s in symbols:
            sym_upper = s.upper()
            st = get_stock(sym_upper)
            close = float(st.get("close", 1000.0)) if st else 1000.0
            change_pct = float(st.get("daily_change_pct", 0.0)) if st else 0.5
            change = close * (change_pct / 100)

            quotes[sym_upper] = LiveQuote(
                symbol=sym_upper,
                security_id=self.instrument_service.get_instrument_key(sym_upper) or f"NSE_EQ|{sym_upper}",
                exchange_segment="NSE_EQ",
                ltp=round(close, 2),
                open=round(close - change * 0.5, 2),
                high=round(close + abs(change) * 0.8, 2),
                low=round(close - abs(change) * 0.8, 2),
                close=round(close - change, 2),
                change=round(change, 2),
                change_percent=round(change_pct, 2),
                volume=int(st.get("volume", 250000)) if st else 250000,
                atp=round(close, 2),
                ltt=now_str,
                source="DEMO",
                updated_at=now_str,
            )

        return quotes

    def get_cached_quote(self, symbol: str) -> Optional[LiveQuote]:
        """Return the latest cached quote for a symbol."""
        return self._quote_cache.get(symbol.strip().upper())

    def get_all_cached_quotes(self) -> Dict[str, LiveQuote]:
        """Return all current cached quotes."""
        return dict(self._quote_cache)

    def update_cache_from_tick(
        self,
        symbol: str,
        ltp: float,
        volume: Optional[int] = None,
        high: Optional[float] = None,
        low: Optional[float] = None,
        open_p: Optional[float] = None,
        close: Optional[float] = None,
        ltt: Optional[str] = None,
    ):
        """Update the quote cache with an incoming real-time WebSocket tick."""
        sym = symbol.strip().upper()
        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        existing = self._quote_cache.get(sym)

        if existing:
            chg = (ltp - existing.close) if existing.close else existing.change
            chg_pct = (chg / existing.close * 100) if (existing.close and existing.close > 0) else existing.change_percent

            updated = LiveQuote(
                symbol=sym,
                security_id=existing.security_id,
                exchange_segment=existing.exchange_segment,
                ltp=round(ltp, 2),
                open=open_p or existing.open,
                high=max(high or ltp, existing.high or ltp),
                low=min(low or ltp, existing.low or ltp),
                close=close or existing.close,
                change=round(chg, 2) if chg is not None else None,
                change_percent=round(chg_pct, 2) if chg_pct is not None else None,
                volume=volume or existing.volume,
                atp=existing.atp,
                ltt=ltt or now_str,
                source="LIVE",
                updated_at=now_str,
            )
            self._quote_cache[sym] = updated
        else:
            chg = round(ltp - close, 2) if (close and close > 0) else 0.0
            chg_pct = round((chg / close * 100), 2) if (close and close > 0) else 0.0
            self._quote_cache[sym] = LiveQuote(
                symbol=sym,
                security_id=self.instrument_service.get_instrument_key(sym) or f"NSE_EQ|{sym}",
                exchange_segment="NSE_EQ",
                ltp=round(ltp, 2),
                open=open_p or ltp,
                high=max(high or ltp, ltp),
                low=min(low or ltp, ltp),
                close=close or ltp,
                change=chg,
                change_percent=chg_pct,
                volume=volume or 0,
                ltt=ltt or now_str,
                source="LIVE",
                updated_at=now_str,
            )


_market_service_instance: Optional[UpstoxMarketService] = None


def get_upstox_market_service() -> UpstoxMarketService:
    global _market_service_instance
    if _market_service_instance is None:
        _market_service_instance = UpstoxMarketService()
    return _market_service_instance
