"""Upstox market data provider implementation.

Adheres strictly to DataProvider interface:
- Checks configuration and token store availability
- Resolves official Upstox instrument keys via UpstoxInstrumentService
- Returns normalized StockInfo and OHLCV history
- Clearly labels live vs historical attribution
"""

from __future__ import annotations

import logging
from typing import Optional
import pandas as pd
import httpx

from app.config import get_upstox_config
from app.providers.base import DataProvider, ProviderAttribution, StockInfo
from app.services.token_store import get_upstox_token
from app.services.upstox_instrument_service import get_upstox_instrument_service

logger = logging.getLogger(__name__)


class UpstoxProvider(DataProvider):
    """Market data provider backed by Upstox v2 API."""

    def __init__(self) -> None:
        self.cfg = get_upstox_config()
        self.instrument_service = get_upstox_instrument_service()

    def get_attribution(self) -> ProviderAttribution:
        cfg = get_upstox_config()
        data_type = "live" if cfg.live_data_enabled else "historical"
        return ProviderAttribution(
            name="Upstox API v2",
            url="https://upstox.com",
            data_type=data_type,
            note=(
                "Official Indian broker market data feed (SEBI registered). "
                "Tick-by-tick and REST snapshot quotes."
            ),
        )

    def is_available(self) -> bool:
        cfg = get_upstox_config()
        if not cfg.is_configured:
            return False
        stored = get_upstox_token()
        if not stored or not stored.access_token or stored.is_expired:
            return False
        return True

    def fetch_stock_info(self, symbol: str, exchange: str = "NSE") -> Optional[StockInfo]:
        inst = self.instrument_service.get_instrument(symbol)
        if not inst:
            logger.info("Symbol %s not found in Upstox instrument master", symbol)
            return None

        return StockInfo(
            symbol=inst.symbol,
            company_name=inst.company_name,
            exchange="NSE",
            isin=inst.isin,
            provider="upstox",
        )

    def fetch_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        period: str = "1y",
        start_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """Fetch historical candle bars from Upstox or fallback to YFinance."""
        key = self.instrument_service.get_instrument_key(symbol)
        stored = get_upstox_token()

        if key:
            import urllib.parse
            import datetime

            days_map = {
                "1d": 2,
                "5d": 8,
                "1mo": 35,
                "1m": 35,
                "3mo": 100,
                "3m": 100,
                "6mo": 200,
                "6m": 200,
                "1y": 380,
                "2y": 750,
                "3y": 1150,
                "5y": 1900,
                "10y": 3800,
                "max": 3800,
            }
            days_back = days_map.get(period.lower(), 380)
            today = datetime.date.today()
            to_date = today.strftime("%Y-%m-%d")
            from_date = (today - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")

            quoted_key = urllib.parse.quote(key, safe="")
            url = f"https://api.upstox.com/v2/historical-candle/{quoted_key}/day/{to_date}/{from_date}"
            headers = {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            if stored and stored.access_token:
                headers["Authorization"] = f"Bearer {stored.access_token}"

            try:
                with httpx.Client(timeout=15.0) as client:
                    res = client.get(url, headers=headers)
                    if res.status_code == 200:
                        data = res.json().get("data", {}).get("candles", [])
                        if data:
                            # Upstox candles: [timestamp, open, high, low, close, volume, open_interest]
                            df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])
                            df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
                            df["adj_close"] = df["close"]
                            df = df.sort_values("date").reset_index(drop=True)
                            logger.info("Successfully fetched %d daily candles from Upstox for %s", len(df), symbol)
                            return df[["date", "open", "high", "low", "close", "adj_close", "volume"]]
                    else:
                        logger.warning("Upstox historical candle returned HTTP %d for %s: %s", res.status_code, symbol, res.text[:120])
            except Exception as e:
                logger.warning("Could not fetch historical candles from Upstox for %s: %s", symbol, e)

        # Fallback to YFinance for historical consistency
        try:
            from app.providers.yfinance_provider import YFinanceProvider
            yf = YFinanceProvider()
            if yf.is_available():
                return yf.fetch_history(symbol, exchange, period, start_date)
        except Exception as e:
            logger.warning("Fallback history fetch failed: %s", e)

        return None
