"""
Abstract base class for fundamental-data providers.

Each provider (Upstox, NSE filing, Screener CSV) implements this interface
so the fundamental-data layer is vendor-agnostic.
"""

from __future__ import annotations

import abc
from typing import Optional

from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    Competitor,
    CorporateAction,
    FundamentalSource,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    ShareholdingPattern,
    StatementType,
)


class FundamentalProvider(abc.ABC):
    """Interface that every fundamental-data provider must implement."""

    @abc.abstractmethod
    def source_label(self) -> FundamentalSource:
        """Return the canonical source enum for this provider."""
        ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is ready (credentials ok, etc.)."""
        ...

    @abc.abstractmethod
    async def fetch_profile(self, isin: str) -> Optional[CompanyProfile]:
        """Fetch company profile for an ISIN."""
        ...

    @abc.abstractmethod
    async def fetch_income_statements(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[IncomeStatement]:
        """Fetch income-statement history."""
        ...

    @abc.abstractmethod
    async def fetch_balance_sheets(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[BalanceSheet]:
        """Fetch balance-sheet history."""
        ...

    @abc.abstractmethod
    async def fetch_cash_flows(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[CashFlow]:
        """Fetch cash-flow statement history."""
        ...

    @abc.abstractmethod
    async def fetch_ratios(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[KeyRatios]:
        """Fetch key financial ratios."""
        ...

    @abc.abstractmethod
    async def fetch_shareholding(
        self, isin: str
    ) -> list[ShareholdingPattern]:
        """Fetch shareholding pattern history."""
        ...

    @abc.abstractmethod
    async def fetch_corporate_actions(
        self, isin: str
    ) -> list[CorporateAction]:
        """Fetch corporate actions (dividends, splits, bonuses, etc.)."""
        ...

    @abc.abstractmethod
    async def fetch_competitors(
        self, isin: str
    ) -> list[Competitor]:
        """Fetch competitor comparison data."""
        ...
