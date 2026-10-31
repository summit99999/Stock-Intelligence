"""
Abstract base class for market-data providers.

Every provider implements this interface so the rest of the application
never couples to a specific vendor (yfinance, Upstox, etc.).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class StockInfo:
    """Metadata returned by a provider for a single stock."""
    symbol: str
    company_name: str
    exchange: str = "NSE"
    sector: Optional[str] = None
    industry: Optional[str] = None
    isin: Optional[str] = None
    market_cap_cr: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    provider: str = "unknown"


@dataclass
class ProviderAttribution:
    """How to credit the data source."""
    name: str
    url: str
    data_type: str = "historical"   # historical | delayed | live
    note: str = ""


class DataProvider(abc.ABC):
    """Interface that every market-data provider must implement."""

    @abc.abstractmethod
    def get_attribution(self) -> ProviderAttribution:
        """Return source attribution metadata."""
        ...

    @abc.abstractmethod
    def fetch_stock_info(self, symbol: str, exchange: str = "NSE") -> Optional[StockInfo]:
        """
        Fetch metadata for a single stock.
        Returns None if the ticker is invalid / unavailable.
        """
        ...

    @abc.abstractmethod
    def fetch_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        period: str = "1y",
        start_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV history.

        Args:
            symbol:     NSE/BSE symbol (e.g. ``RELIANCE``).
            exchange:   ``NSE`` or ``BSE``.
            period:     yfinance-style period: 1mo, 3mo, 6mo, 1y, 2y, 5y, max.
            start_date: If provided, fetch from this date onward (ISO format).

        Returns:
            DataFrame with columns:
                date, open, high, low, close, adj_close, volume
            or None on failure.
        """
        ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider can be used (library installed, creds ok)."""
        ...
