"""
Data provider manager — registry + orchestration.

Provides a single entry point for the rest of the application to fetch
market data without coupling to a specific vendor.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.providers.base import DataProvider, ProviderAttribution, StockInfo

logger = logging.getLogger(__name__)


@dataclass
class UpdateJob:
    """Tracks the status of a background data-update job."""
    job_id: str
    status: str = "pending"          # pending | running | completed | failed
    total: int = 0
    completed_count: int = 0
    failed_count: int = 0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    symbols_done: list[str] = field(default_factory=list)


class ProviderManager:
    """
    Manages registered data providers and orchestrates data fetching.

    Usage::

        mgr = ProviderManager()
        mgr.register(YFinanceProvider())
        df = mgr.fetch_history("RELIANCE", exchange="NSE", period="1y")
    """

    def __init__(self) -> None:
        self._providers: list[DataProvider] = []
        self._jobs: dict[str, UpdateJob] = {}
        self._job_counter = 0
        self._lock = threading.Lock()

    # ----- registration -----

    def register(self, provider: DataProvider) -> None:
        self._providers.append(provider)
        logger.info("Registered provider: %s", provider.get_attribution().name)

    @property
    def active_provider(self) -> Optional[DataProvider]:
        """Return the first available provider, or None."""
        for p in self._providers:
            if p.is_available():
                return p
        return None

    def get_attribution(self) -> Optional[ProviderAttribution]:
        p = self.active_provider
        return p.get_attribution() if p else None

    # ----- single-symbol operations -----

    def fetch_stock_info(self, symbol: str, exchange: str = "NSE") -> Optional[StockInfo]:
        p = self.active_provider
        if not p:
            logger.error("No data provider available")
            return None
        return p.fetch_stock_info(symbol, exchange)

    def fetch_history(
        self,
        symbol: str,
        exchange: str = "NSE",
        period: str = "1y",
        start_date: Optional[str] = None,
    ) -> Optional[pd.DataFrame]:
        p = self.active_provider
        if not p:
            logger.error("No data provider available")
            return None
        return p.fetch_history(symbol, exchange, period, start_date)

    # ----- background batch updates -----

    def create_job(self, symbols: list[str]) -> str:
        """Create a job entry and return its ID."""
        with self._lock:
            self._job_counter += 1
            job_id = f"job-{self._job_counter}"
            self._jobs[job_id] = UpdateJob(
                job_id=job_id,
                total=len(symbols),
            )
        return job_id

    def get_job(self, job_id: str) -> Optional[UpdateJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[UpdateJob]:
        return list(self._jobs.values())

    def update_job(self, job_id: str, **kwargs) -> None:
        job = self._jobs.get(job_id)
        if job:
            for k, v in kwargs.items():
                setattr(job, k, v)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_manager: Optional[ProviderManager] = None


def get_provider_manager() -> ProviderManager:
    """Return the global ProviderManager, creating it on first call."""
    global _manager
    if _manager is None:
        import os
        _manager = ProviderManager()
        pref = os.getenv("MARKET_DATA_PROVIDER", "yfinance").strip().lower()

        if pref == "dhan":
            # Prefer Dhan, fallback to YFinance
            try:
                from app.providers.dhan_provider import DhanProvider
                dp = DhanProvider()
                if dp.is_available():
                    _manager.register(dp)
            except Exception as e:
                logger.warning("Could not register Dhan provider: %s", e)

            try:
                from app.providers.yfinance_provider import YFinanceProvider
                yf = YFinanceProvider()
                if yf.is_available():
                    _manager.register(yf)
            except Exception as e:
                logger.warning("Could not register YFinance fallback provider: %s", e)
        else:
            # Default: Prefer YFinance, fallback to Dhan
            try:
                from app.providers.yfinance_provider import YFinanceProvider
                yf = YFinanceProvider()
                if yf.is_available():
                    _manager.register(yf)
            except Exception as e:
                logger.warning("Could not register YFinance provider: %s", e)

            try:
                from app.providers.dhan_provider import DhanProvider
                dp = DhanProvider()
                if dp.is_available():
                    _manager.register(dp)
            except Exception as e:
                logger.warning("Could not register Dhan provider: %s", e)

    return _manager
