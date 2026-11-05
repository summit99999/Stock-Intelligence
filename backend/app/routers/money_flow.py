"""
Money Flow & Daily Volume Intelligence API Router.

Endpoints:
- /api/money-flow/overview: Full 8-section Money Flow & Volume Intelligence dashboard
- /api/money-flow/stock/{symbol}: Deep-dive stock-level volume & money flow analysis
- /api/money-flow/scan: Filtered and sorted volume/money flow screening
"""

from __future__ import annotations

import math
import time
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_stock
from app.services.money_flow_service import (
    calculate_stock_volume_intelligence,
    get_money_flow_dashboard,
)

router = APIRouter(prefix="/api/money-flow", tags=["Money Flow & Volume Intelligence"])


class MoneyFlowFilterPayload(BaseModel):
    universe: str = Field("all", description="all, nifty50, nifty100, nifty500, fno")
    min_traded_value_cr: float = Field(0.0, ge=0.0)
    min_volume: int = Field(0, ge=0)
    min_rvol: Optional[float] = None
    category: Optional[str] = None
    sort_by: str = Field("daily_rvol", description="daily_rvol, daily_change_pct, traded_value_cr, buying_pressure_pct")
    sort_order: str = Field("desc", description="desc or asc")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


@router.get("/overview")
def get_money_flow_overview(
    universe: str = Query("all", description="all, nifty50, nifty100, nifty500, fno"),
    force_refresh: bool = Query(False, description="Bypass in-memory cache"),
    min_traded_value_cr: float = Query(0.0, ge=0.0, description="Minimum traded value in ₹ Cr"),
    min_volume: int = Query(0, ge=0, description="Minimum traded volume shares"),
) -> dict[str, Any]:
    """
    Get full Money Flow & Daily Volume Intelligence dashboard:
    1. Market Overview
    2. Money Flow Summary
    3. Top Volume Gainers
    4. Top Price Gainers / Losers
    5. Combined Volume + Price Intelligence Categories
    6. Sector Money Flow & Rotation
    """
    return get_money_flow_dashboard(
        universe=universe,
        force_refresh=force_refresh,
        min_traded_value_cr=min_traded_value_cr,
        min_volume=min_volume,
    )


@router.get("/stock/{symbol}")
def get_stock_money_flow_analysis(symbol: str) -> dict[str, Any]:
    """
    Get deep-dive volume metrics, moving averages (10D, 20D, 50D), daily & intraday RVOL,
    traded value, buying/selling pressure, CMF, and price-volume divergence for a single stock.
    """
    sym = symbol.upper()
    stock_meta = get_stock(sym)
    if not stock_meta:
        raise HTTPException(status_code=404, detail=f"Stock '{sym}' not found in database.")

    intel = calculate_stock_volume_intelligence(sym, stock_meta=stock_meta)
    metadata = {
        "provider": stock_meta.get("provider", "yfinance"),
        "instrument": "EQUITY",
        "exchange": "NSE",
        "timeframe": "1D",
        "data_mode": "HISTORICAL",
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "is_stale": False,
        "turnover_type": intel.get("turnover_type", "ESTIMATED_TURNOVER"),
        "intraday_rvol_method": intel.get("intraday_rvol_method", "LINEAR_ESTIMATED"),
        "institutional_flow_status": "UNAVAILABLE",
        "disclaimer": (
            "Traded volume represents total two-sided transactions. "
            "Close-location buying and selling biases are OHLCV-derived estimates from candle range, "
            "not actual order-book buyer-initiated or seller-initiated trade percentages. "
            "Institutional flow is UNAVAILABLE without official exchange-published settlement reports."
        ),
    }

    return {
        "symbol": sym,
        "analysis": intel,
        "metadata": metadata,
        "institutional_flow": intel.get("institutional_flow"),
    }


@router.post("/scan")
def scan_money_flow(payload: MoneyFlowFilterPayload) -> dict[str, Any]:
    """
    Filter, sort, and paginate stocks based on volume intelligence and money flow criteria.
    """
    overview = get_money_flow_dashboard(
        universe=payload.universe,
        min_traded_value_cr=payload.min_traded_value_cr,
        min_volume=payload.min_volume,
    )

    items: list[dict[str, Any]] = overview.get("volume_gainers", [])

    if payload.min_rvol is not None:
        items = [it for it in items if it.get("daily_rvol", 0.0) >= payload.min_rvol]

    if payload.category:
        cat = payload.category.lower()
        comb = overview.get("combined_categories", {})
        if cat in comb:
            items = comb[cat]

    reverse = payload.sort_order.lower() == "desc"
    active_sort = payload.sort_by

    def _sort_key(it: dict[str, Any]) -> Any:
        v = it.get(active_sort)
        if v is None:
            return -999999.0 if reverse else 999999.0
        return v

    items.sort(key=_sort_key, reverse=reverse)

    total_records = len(items)
    page_size = max(1, min(payload.page_size, 100))
    total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
    page = max(1, min(payload.page, total_pages))
    start_idx = (page - 1) * page_size
    paged_items = items[start_idx : start_idx + page_size]

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": payload.universe,
        "total": total_records,
        "total_records": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "items": paged_items,
        "metadata": overview.get("metadata"),
    }
