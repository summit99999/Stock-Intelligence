"""
Pydantic schemas for fundamental data.

Normalised models that store data from any provider (Upstox, NSE/BSE filings,
Screener.in CSV) in a uniform shape.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FundamentalSource(str, Enum):
    UPSTOX_API = "upstox_api"
    NSE_FILING = "nse_filing"
    BSE_FILING = "bse_filing"
    SCREENER_CSV = "screener_csv"
    DEMO = "demo"


class StatementType(str, Enum):
    CONSOLIDATED = "consolidated"
    STANDALONE = "standalone"


class ReportingFrequency(str, Enum):
    YEARLY = "yearly"
    QUARTERLY = "quarterly"


class SyncStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"


# ---------------------------------------------------------------------------
# Company Profile
# ---------------------------------------------------------------------------

class CompanyProfile(BaseModel):
    symbol: str
    isin: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    exchange: Optional[str] = None
    face_value: Optional[float] = None
    market_cap_cr: Optional[float] = None
    year_of_incorporation: Optional[int] = None
    bse_code: Optional[str] = None
    nse_code: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Financial Statements
# ---------------------------------------------------------------------------

class IncomeStatement(BaseModel):
    symbol: str
    isin: str
    period: str  # e.g. "FY2024", "Q1FY2025"
    statement_type: StatementType = StatementType.CONSOLIDATED
    frequency: ReportingFrequency = ReportingFrequency.YEARLY

    revenue_cr: Optional[float] = None
    other_income_cr: Optional[float] = None
    cost_of_revenue_cr: Optional[float] = None
    gross_profit_cr: Optional[float] = None
    operating_expenses_cr: Optional[float] = None
    operating_profit_cr: Optional[float] = None
    ebitda_cr: Optional[float] = None
    depreciation_cr: Optional[float] = None
    ebit_cr: Optional[float] = None
    interest_expense_cr: Optional[float] = None
    profit_before_tax_cr: Optional[float] = None
    tax_expense_cr: Optional[float] = None
    net_profit_cr: Optional[float] = None
    eps: Optional[float] = None
    diluted_eps: Optional[float] = None

    period_end_date: Optional[str] = None
    verification_status: str = "unverified"
    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


class BalanceSheet(BaseModel):
    symbol: str
    isin: str
    period: str
    statement_type: StatementType = StatementType.CONSOLIDATED
    frequency: ReportingFrequency = ReportingFrequency.YEARLY

    total_assets_cr: Optional[float] = None
    current_assets_cr: Optional[float] = None
    non_current_assets_cr: Optional[float] = None
    total_liabilities_cr: Optional[float] = None
    current_liabilities_cr: Optional[float] = None
    non_current_liabilities_cr: Optional[float] = None
    total_equity_cr: Optional[float] = None
    share_capital_cr: Optional[float] = None
    reserves_cr: Optional[float] = None
    total_debt_cr: Optional[float] = None
    borrowings_cr: Optional[float] = None
    cash_and_equivalents_cr: Optional[float] = None
    book_value_per_share: Optional[float] = None

    period_end_date: Optional[str] = None
    verification_status: str = "unverified"
    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


class CashFlow(BaseModel):
    symbol: str
    isin: str
    period: str
    statement_type: StatementType = StatementType.CONSOLIDATED
    frequency: ReportingFrequency = ReportingFrequency.YEARLY

    operating_cash_flow_cr: Optional[float] = None
    investing_cash_flow_cr: Optional[float] = None
    financing_cash_flow_cr: Optional[float] = None
    net_cash_flow_cr: Optional[float] = None
    capex_cr: Optional[float] = None
    free_cash_flow_cr: Optional[float] = None

    period_end_date: Optional[str] = None
    verification_status: str = "unverified"
    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Key Ratios
# ---------------------------------------------------------------------------

class KeyRatios(BaseModel):
    symbol: str
    isin: str
    period: str
    statement_type: StatementType = StatementType.CONSOLIDATED
    frequency: ReportingFrequency = ReportingFrequency.YEARLY

    pe: Optional[float] = None
    pb: Optional[float] = None
    ev_ebitda: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_equity: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    interest_coverage: Optional[float] = None
    dividend_yield: Optional[float] = None
    dividend_payout: Optional[float] = None
    opm_pct: Optional[float] = None
    npm_pct: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    profit_growth_pct: Optional[float] = None
    asset_turnover: Optional[float] = None

    period_end_date: Optional[str] = None
    verification_status: str = "unverified"
    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Shareholding
# ---------------------------------------------------------------------------

class ShareholdingPattern(BaseModel):
    symbol: str
    isin: str
    period: str  # e.g. "Q1FY2025"

    promoter_holding: Optional[float] = None
    promoter_pledging: Optional[float] = None
    fii_holding: Optional[float] = None
    dii_holding: Optional[float] = None
    public_holding: Optional[float] = None
    government_holding: Optional[float] = None
    total_shares: Optional[int] = None

    period_end_date: Optional[str] = None
    verification_status: str = "unverified"
    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None



# ---------------------------------------------------------------------------
# Corporate Actions
# ---------------------------------------------------------------------------

class CorporateAction(BaseModel):
    symbol: str
    isin: str
    action_type: str  # dividend, bonus, split, rights, buyback
    ex_date: Optional[str] = None
    record_date: Optional[str] = None
    description: Optional[str] = None
    value: Optional[float] = None  # e.g. dividend amount per share

    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Competitors
# ---------------------------------------------------------------------------

class Competitor(BaseModel):
    symbol: str
    isin: str
    competitor_name: Optional[str] = None
    competitor_isin: Optional[str] = None
    market_cap_cr: Optional[float] = None
    pe: Optional[float] = None
    revenue_cr: Optional[float] = None
    net_profit_cr: Optional[float] = None

    raw_data: Optional[dict[str, Any]] = None
    source: FundamentalSource = FundamentalSource.DEMO
    fetched_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Sync History
# ---------------------------------------------------------------------------

class SyncHistoryEntry(BaseModel):
    id: Optional[int] = None
    symbol: str
    isin: str
    provider: FundamentalSource
    data_type: str  # profile, income_statement, balance_sheet, etc.
    status: SyncStatus = SyncStatus.PENDING
    records_fetched: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# API Response Models
# ---------------------------------------------------------------------------

class FundamentalsStatusResponse(BaseModel):
    upstox_configured: bool
    upstox_token_present: bool  # never reveals the token itself
    total_stocks: int
    stocks_with_isin: int
    providers_available: list[str]
    sync_summary: dict[str, Any] = Field(default_factory=dict)


class FundamentalSyncRequest(BaseModel):
    data_types: list[str] = Field(
        default=["profile"],
        description="Types to sync: profile, income_statement, balance_sheet, "
                    "cash_flow, ratios, shareholding, corporate_actions, competitors",
    )
    statement_type: StatementType = StatementType.CONSOLIDATED
    frequency: ReportingFrequency = ReportingFrequency.YEARLY


class FundamentalSyncResponse(BaseModel):
    symbol: str
    status: str
    records_synced: int = 0
    errors: list[str] = Field(default_factory=list)


class ScreenerCsvImportResponse(BaseModel):
    status: str
    rows_imported: int = 0
    rows_skipped: int = 0
    unmapped_symbols: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    overwrite_verified: bool = False


class SourceConflict(BaseModel):
    field: str
    symbol: str
    source_a: str
    value_a: Any
    source_b: str
    value_b: Any
    discrepancy_pct: Optional[float] = None
