"""
NSE/BSE financial filing provider — interface/stub only.

This provider defines the structure for future integration with official
NSE and BSE financial filings.  No web scraping is performed.  This module
exists so the architecture is ready when a legitimate filing-data source
becomes available.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.providers.fundamentals.base import FundamentalProvider
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

logger = logging.getLogger(__name__)


class NseFilingProvider(FundamentalProvider):
    """
    Placeholder for official NSE/BSE filing data.

    Currently returns empty results for all queries.  When a legitimate
    data source (XBRL download, data vendor API, etc.) is available,
    the implementation can be filled in without changing the rest of the system.
    """

    def source_label(self) -> FundamentalSource:
        return FundamentalSource.NSE_FILING

    def is_available(self) -> bool:
        # Not yet implemented — always returns False
        return False

    async def fetch_profile(self, isin: str) -> Optional[CompanyProfile]:
        return None

    async def fetch_income_statements(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[IncomeStatement]:
        return []

    async def fetch_balance_sheets(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[BalanceSheet]:
        return []

    async def fetch_cash_flows(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[CashFlow]:
        return []

    async def fetch_ratios(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[KeyRatios]:
        return []

    async def fetch_shareholding(self, isin: str) -> list[ShareholdingPattern]:
        return []

    async def fetch_corporate_actions(self, isin: str) -> list[CorporateAction]:
        return []

    async def fetch_competitors(self, isin: str) -> list[Competitor]:
        return []
