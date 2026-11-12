"""
YFinance data provider — fetches historical OHLCV data from Yahoo Finance.

Important notes:
  * Yahoo Finance is **not** an exchange-authorised real-time feed.
  * Data retrieved is historical / delayed — never labelled as live.
  * yfinance is a community library; availability may change.
  * NSE tickers use the suffix ``.NS``, BSE use ``.BO``.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import pandas as pd

from app.providers.base import DataProvider, ProviderAttribution, StockInfo

logger = logging.getLogger(__name__)

# Rate-limit: minimum seconds between consecutive yfinance requests
_MIN_REQUEST_INTERVAL = 1.0
_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # exponential: 2s, 4s, 8s


def _yf_ticker(symbol: str, exchange: str = "NSE") -> str:
    """Convert a plain symbol to a Yahoo Finance ticker."""
    if symbol.startswith("^"):
        return symbol
    suffix = ".NS" if exchange.upper() == "NSE" else ".BO"
    return f"{symbol}{suffix}"


class YFinanceProvider(DataProvider):
    """Provider backed by the ``yfinance`` library."""

    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self._yf = None  # lazy import

    def _import_yf(self):
        """Lazy-import yfinance so the app starts even if it's missing."""
        if self._yf is None:
            try:
                import yfinance as yf
                self._yf = yf
            except ImportError:
                raise ImportError(
                    "yfinance is not installed. Run: pip install yfinance"
                )
        return self._yf

    # ----- rate limiting -----

    def _throttle(self) -> None:
        """Ensure at least ``_MIN_REQUEST_INTERVAL`` seconds between calls."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < _MIN_REQUEST_INTERVAL:
            time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.monotonic()

    # ----- DataProvider interface -----

    def get_attribution(self) -> ProviderAttribution:
        return ProviderAttribution(
            name="Yahoo Finance (via yfinance)",
            url="https://finance.yahoo.com",
            data_type="historical",
            note=(
                "Historical/delayed data retrieved via the yfinance library. "
                "Not an exchange-authorised real-time feed."
            ),
        )

    def is_available(self) -> bool:
        try:
            self._import_yf()
            return True
        except ImportError:
            return False

    def fetch_stock_info(
        self, symbol: str, exchange: str = "NSE"
    ) -> Optional[StockInfo]:
        yf = self._import_yf()
        ticker_str = _yf_ticker(symbol, exchange)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._throttle()
                ticker = yf.Ticker(ticker_str)
                info = ticker.info or {}

                if not info.get("regularMarketPrice") and not info.get("previousClose"):
                    logger.warning("No price data for %s — possibly invalid ticker", ticker_str)
                    return None

                # Convert market cap from INR to crores
                mkt_cap_inr = info.get("marketCap")
                mkt_cap_cr = round(mkt_cap_inr / 1e7, 2) if mkt_cap_inr else None

                return StockInfo(
                    symbol=symbol,
                    company_name=info.get("longName") or info.get("shortName") or symbol,
                    exchange=exchange,
                    sector=info.get("sector"),
                    industry=info.get("industry"),
                    isin=info.get("isin"),
                    market_cap_cr=mkt_cap_cr,
                    pe=info.get("trailingPE"),
                    pb=info.get("priceToBook"),
                    week_52_high=info.get("fiftyTwoWeekHigh"),
                    week_52_low=info.get("fiftyTwoWeekLow"),
                    provider="yfinance",
                )
            except Exception as e:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "fetch_stock_info(%s) attempt %d failed: %s — retrying in %ds",
                    ticker_str, attempt, e, wait,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)

        logger.error("fetch_stock_info(%s) failed after %d attempts", ticker_str, _MAX_RETRIES)
        return None

    def fetch_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        period: str = "1y",
        start_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        yf = self._import_yf()
        ticker_str = _yf_ticker(symbol, exchange)

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                self._throttle()
                ticker = yf.Ticker(ticker_str)

                kwargs: dict = {"auto_adjust": False}
                if start_date:
                    kwargs["start"] = start_date
                else:
                    kwargs["period"] = period

                df: pd.DataFrame = ticker.history(**kwargs)

                if df is None or df.empty:
                    logger.warning("No history for %s (period=%s)", ticker_str, period)
                    return None

                # Normalise column names
                df = df.reset_index()
                col_map = {
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Adj Close": "adj_close",
                    "Volume": "volume",
                }
                df = df.rename(columns=col_map)

                # Keep only the columns we need
                keep = [c for c in ["date", "open", "high", "low", "close", "adj_close", "volume"] if c in df.columns]
                df = df[keep].copy()

                # Ensure date is a string (ISO format)
                if "date" in df.columns:
                    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

                # Drop rows where close is NaN
                df = df.dropna(subset=["close"])

                logger.info(
                    "Fetched %d bars for %s (period=%s)", len(df), ticker_str, period
                )
                return df

            except Exception as e:
                wait = _BACKOFF_BASE ** attempt
                logger.warning(
                    "fetch_history(%s) attempt %d failed: %s — retrying in %ds",
                    ticker_str, attempt, e, wait,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(wait)

        logger.error("fetch_history(%s) failed after %d attempts", ticker_str, _MAX_RETRIES)
        return None
