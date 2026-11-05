"""
Pydantic models for the Stock Screener.

Supports:
  - Flat min/max filters (simple mode)
  - Advanced AND/OR condition groups
  - Pagination, sorting, search
  - Saved screener presets
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Operator(str, Enum):
    GT  = ">"
    GTE = ">="
    LT  = "<"
    LTE = "<="
    EQ  = "=="
    NEQ = "!="
    BETWEEN = "between"


class LogicOp(str, Enum):
    AND = "AND"
    OR  = "OR"


class SortOrder(str, Enum):
    ASC  = "asc"
    DESC = "desc"


# ---------------------------------------------------------------------------
# Advanced filter condition
# ---------------------------------------------------------------------------

class FilterCondition(BaseModel):
    """A single screening condition, e.g. 'market_cap_cr >= 2000'."""
    field: str = Field(..., description="Column name, e.g. 'market_cap_cr', 'roe', 'rsi'")
    operator: Operator = Operator.GTE
    value: float = Field(..., description="Threshold value")
    value2: Optional[float] = Field(None, description="Upper bound for 'between' operator")


class ConditionGroup(BaseModel):
    """A group of conditions joined by AND or OR."""
    logic: LogicOp = LogicOp.AND
    conditions: list[FilterCondition] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main screen request
# ---------------------------------------------------------------------------

class ScreenRequest(BaseModel):
    """Full screening request supporting both simple and advanced modes."""

    # --- Stock universe filters ---
    exchange: Optional[str] = Field(None, description="NSE or BSE")
    sector: Optional[str] = Field(None, description="Filter by sector")
    cap_category: Optional[str] = Field(None, description="large_cap, mid_cap, or small_cap")
    search: Optional[str] = Field(None, description="Company name or symbol search")

    # --- Simple min/max filters (quick mode) ---
    min_market_cap_cr: Optional[float] = None
    max_market_cap_cr: Optional[float] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_pe: Optional[float] = None
    max_pe: Optional[float] = None
    min_pb: Optional[float] = None
    max_pb: Optional[float] = None
    min_roe: Optional[float] = None
    max_roe: Optional[float] = None
    min_roce: Optional[float] = None
    max_roce: Optional[float] = None
    min_debt_equity: Optional[float] = None
    max_debt_equity: Optional[float] = None
    min_revenue_growth: Optional[float] = None
    max_revenue_growth: Optional[float] = None
    min_profit_growth: Optional[float] = None
    max_profit_growth: Optional[float] = None
    min_opm: Optional[float] = None
    max_opm: Optional[float] = None
    min_promoter_holding: Optional[float] = None
    max_promoter_pledging: Optional[float] = None
    min_fii_holding: Optional[float] = None
    min_dii_holding: Optional[float] = None
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    min_adx: Optional[float] = None
    min_relative_volume: Optional[float] = None
    max_relative_volume: Optional[float] = None
    min_return_1m: Optional[float] = None
    max_return_1m: Optional[float] = None
    min_return_3m: Optional[float] = None
    max_return_3m: Optional[float] = None
    min_return_1y: Optional[float] = None
    max_return_1y: Optional[float] = None

    # --- Phase 6 Advanced Fundamental Metrics ---
    min_revenue_cagr_3y: Optional[float] = None
    max_revenue_cagr_3y: Optional[float] = None
    min_pat_cagr_3y: Optional[float] = None
    max_pat_cagr_3y: Optional[float] = None
    min_interest_coverage: Optional[float] = None
    max_interest_coverage: Optional[float] = None
    min_cfo_pat_ratio: Optional[float] = None
    max_cfo_pat_ratio: Optional[float] = None
    min_peg: Optional[float] = None
    max_peg: Optional[float] = None
    min_quality_score: Optional[float] = None
    max_quality_score: Optional[float] = None
    min_free_cash_flow_cr: Optional[float] = None
    max_free_cash_flow_cr: Optional[float] = None

    # --- VolumeLens Expanded Indicators ---
    min_ema_9: Optional[float] = None
    max_ema_9: Optional[float] = None
    min_atr: Optional[float] = None
    max_atr: Optional[float] = None
    min_mfi: Optional[float] = None
    max_mfi: Optional[float] = None
    min_bb_bandwidth: Optional[float] = None
    max_bb_bandwidth: Optional[float] = None
    min_vwap: Optional[float] = None
    max_vwap: Optional[float] = None

    # --- Advanced filter builder (AND/OR groups) ---
    condition_groups: Optional[list[ConditionGroup]] = Field(
        None,
        description="Advanced filter: list of condition groups. "
                    "Groups are joined by AND. Within each group, "
                    "conditions are joined by the group's logic (AND/OR)."
    )

    # --- Pagination / sorting ---
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=200)
    sort_by: str = Field("market_cap_cr", description="Column to sort by")
    sort_order: SortOrder = SortOrder.DESC


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class StockResult(BaseModel):
    symbol: str
    company_name: str
    exchange: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    cap_category: Optional[str] = None
    close: Optional[float] = None
    daily_change_pct: Optional[float] = None
    market_cap_cr: Optional[float] = None
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    roce: Optional[float] = None
    debt_equity: Optional[float] = None
    revenue_growth_pct: Optional[float] = None
    profit_growth_pct: Optional[float] = None
    opm_pct: Optional[float] = None
    rsi: Optional[float] = None
    relative_volume: Optional[float] = None
    return_1m_pct: Optional[float] = None
    return_3m_pct: Optional[float] = None
    return_1y_pct: Optional[float] = None
    promoter_holding: Optional[float] = None
    fii_holding: Optional[float] = None
    dii_holding: Optional[float] = None
    volume: Optional[int] = None
    # Phase 6 Fundamental metrics
    revenue_cagr_3y: Optional[float] = None
    pat_cagr_3y: Optional[float] = None
    interest_coverage: Optional[float] = None
    cfo_pat_ratio: Optional[float] = None
    peg: Optional[float] = None
    quality_score: Optional[int] = None
    free_cash_flow_cr: Optional[float] = None


class ScreenResponse(BaseModel):
    items: list[StockResult]
    total: int
    page: int
    page_size: int
    total_pages: int
    data_mode: str = "demo"
    notice: str = "Illustrative sample universe — not an exchange-wide scan."


# ---------------------------------------------------------------------------
# Saved screener & preset models
# ---------------------------------------------------------------------------

class DefaultPresetStrategy(BaseModel):
    id: str
    name: str
    description: str
    rationale: str
    filters: ScreenRequest


class SaveScreenerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    config: ScreenRequest


class SavedScreenerResponse(BaseModel):
    id: int
    name: str
    description: str
    config_json: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
