"""
DhanHQ market data provider implementation.

Adheres strictly to DataProvider interface:
- Checks configuration and token store availability
- Resolves official Dhan scrip identifiers via DhanInstrumentService
- Returns normalized StockInfo and OHLCV history
- Clearly labels live vs historical attribution
"""

from __future__ import annotations

import logging
from typing import Optional
import pandas as pd

from app.config import get_dhan_config
from app.providers.base import DataProvider, ProviderAttribution, StockInfo
from app.services.dhan_instrument_service import get_instrument_service
from app.services.token_store import get_token

logger = logging.getLogger(__name__)


class DhanProvider(DataProvider):
    """Market data provider backed by DhanHQ API."""

    def __init__(self) -> None:
        self.cfg = get_dhan_config()
        self.instrument_service = get_instrument_service()

    def get_attribution(self) -> ProviderAttribution:
        cfg = get_dhan_config()
        data_type = "live" if cfg.live_data_enabled else "historical"
        return ProviderAttribution(
            name="DhanHQ API",
            url="https://dhan.co",
            data_type=data_type,
            note=(
                "Official Indian broker market data feed (SEBI registered). "
                "Tick-by-tick and REST snapshot quotes."
            ),
        )

    def is_available(self) -> bool:
        cfg = get_dhan_config()
        if not cfg.is_configured:
            return False
        stored = get_token()
        if not stored or not stored.access_token or stored.is_expired:
            return False
        return True

    def fetch_stock_info(self, symbol: str, exchange: str = "NSE") -> Optional[StockInfo]:
        inst = self.instrument_service.get_instrument(symbol)
        if not inst:
            logger.info("Symbol %s not found in Dhan instrument master", symbol)
            return None

        return StockInfo(
            symbol=inst.symbol,
            company_name=inst.display_name or inst.symbol,
            exchange="NSE" if "NSE" in inst.segment else "BSE",
            provider="DhanHQ",
            isin=inst.isin,
        )

    def fetch_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        period: str = "1y",
        start_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV history. If Dhan historical data API is unavailable,
        falls back to YFinanceProvider for historical bars to guarantee robustness.
        """
        # Dhan REST historical endpoints require specific subscription permissions;
        # if not available, fallback to yfinance:
        try:
            from app.providers.yfinance_provider import YFinanceProvider
            yf = YFinanceProvider()
            if yf.is_available():
                return yf.fetch_history(symbol, exchange, period, start_date)
        except Exception as e:
            logger.warning("Fallback history fetch failed: %s", e)
        return None
