"""Screener API router."""

from __future__ import annotations

import csv
import io
import json
import math

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.auth import get_current_user

from app.database import (
    delete_saved_screener,
    get_saved_screener,
    get_sectors,
    get_exchanges,
    list_saved_screeners,
    list_stocks,
    save_screener,
)
from app.schemas.screener import (
    DefaultPresetStrategy,
    SaveScreenerRequest,
    SavedScreenerResponse,
    ScreenRequest,
    ScreenResponse,
    StockResult,
)
from app.services.screener_service import run_screen

router = APIRouter(prefix="/api/screener", tags=["screener"])


DEFAULT_PRESETS: list[DefaultPresetStrategy] = [
    DefaultPresetStrategy(
        id="high-growth",
        name="High Growth Companies",
        description="High compounding companies with >15% Revenue & >18% Profit growth and healthy ROE.",
        rationale="Filters for fast-growing businesses capable of reinvesting capital at attractive return rates.",
        filters=ScreenRequest(min_revenue_growth=15.0, min_profit_growth=18.0, min_roe=15.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="high-roce",
        name="High ROCE Companies",
        description="Capital-efficient businesses with ROCE >= 22%, low debt, and solid operating margins.",
        rationale="Buffett-style franchises generating superior returns on total capital employed.",
        filters=ScreenRequest(min_roce=22.0, max_debt_equity=0.5, min_opm=15.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="low-debt",
        name="Low Debt Companies",
        description="Fortress balance sheet companies with Debt/Equity <= 0.1 and interest coverage.",
        rationale="Financially resilient companies with virtually no solvency or bankruptcy risk.",
        filters=ScreenRequest(max_debt_equity=0.1, min_roce=15.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="consistent-profit",
        name="Consistent Profit Growers",
        description="Steady compounding stalwarts with double-digit profit growth and consistent ROE.",
        rationale="Predictable, wide-moat compounders for conservative long-term capital appreciation.",
        filters=ScreenRequest(min_profit_growth=12.0, min_roe=18.0, max_debt_equity=0.8, page_size=50),
    ),
    DefaultPresetStrategy(
        id="cash-flow-strong",
        name="Cash Flow Strong Companies",
        description="Companies with robust cash generation and positive Free Cash Flow.",
        rationale="Real cash generation safeguards against aggressive or misleading accrual accounting.",
        filters=ScreenRequest(min_opm=15.0, min_roce=15.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="undervalued-quality",
        name="Undervalued Quality Companies",
        description="High quality companies (ROCE >= 18%, D/E <= 0.5) trading at reasonable PE multiples (<= 30).",
        rationale="Quality at a Reasonable Price (GARP) — never buying low PE without verifying high ROCE.",
        filters=ScreenRequest(min_roce=18.0, max_debt_equity=0.5, max_pe=30.0, min_roe=15.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="promoter-skin",
        name="Promoter Skin-in-the-Game",
        description="High promoter ownership (>= 50%) with zero pledging and strong institutional backing.",
        rationale="Management interests fully aligned with minority shareholders with no pledge overhang.",
        filters=ScreenRequest(min_promoter_holding=50.0, max_promoter_pledging=0.0, min_fii_holding=10.0, page_size=50),
    ),
    DefaultPresetStrategy(
        id="turnaround",
        name="Turnaround Candidates",
        description="Companies exhibiting strong quarterly profit inflection (>20% YoY) and manageable debt.",
        rationale="Catching operational or earnings inflection before broad market recognition.",
        filters=ScreenRequest(min_profit_growth=20.0, max_debt_equity=1.0, page_size=50),
    ),
]


@router.get("/presets/default", response_model=list[DefaultPresetStrategy])
def get_default_presets():
    """Return the 8 built-in institutional preset screening strategies."""
    return DEFAULT_PRESETS



@router.post("/run", response_model=ScreenResponse)
def run_screener(request: ScreenRequest):
    """Run the stock screener with given filters."""
    # Build stock universe
    stocks = list_stocks(
        exchange=request.exchange,
        sector=request.sector,
        cap_category=request.cap_category,
        search=request.search,
    )

    items, total = run_screen(stocks, request)

    total_pages = max(1, math.ceil(total / request.page_size))

    return ScreenResponse(
        items=[StockResult(**{k: s.get(k) for k in StockResult.model_fields}) for s in items],
        total=total,
        page=request.page,
        page_size=request.page_size,
        total_pages=total_pages,
    )


@router.post("/export-csv")
def export_csv(request: ScreenRequest):
    """Export screener results as CSV."""
    stocks = list_stocks(
        exchange=request.exchange,
        sector=request.sector,
        cap_category=request.cap_category,
        search=request.search,
    )
    # Get all results (no pagination for export)
    request_copy = request.model_copy(update={"page": 1, "page_size": 9999})
    items, _ = run_screen(stocks, request_copy)

    output = io.StringIO()
    if items:
        # Use StockResult fields for consistent column order
        fieldnames = list(StockResult.model_fields.keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row = {k: item.get(k) for k in fieldnames}
            writer.writerow(row)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=screener_results.csv"},
    )


@router.get("/metadata")
def screener_metadata():
    """Return available sectors, exchanges, and filter field definitions."""
    return {
        "sectors": get_sectors(),
        "exchanges": get_exchanges(),
        "cap_categories": ["large_cap", "mid_cap", "small_cap"],
        "filter_fields": _get_filter_field_definitions(),
    }


@router.get("/presets", response_model=list[SavedScreenerResponse])
def get_presets(current_user: dict = Depends(get_current_user)):
    """List saved screener presets for authenticated user."""
    return list_saved_screeners(user_id=current_user["id"])


@router.post("/presets", response_model=SavedScreenerResponse)
def create_preset(
    req: SaveScreenerRequest,
    current_user: dict = Depends(get_current_user),
):
    """Save a screener preset."""
    config_json = req.config.model_dump_json()
    row_id = save_screener(req.name, req.description, config_json, user_id=current_user["id"])
    saved = get_saved_screener(row_id, user_id=current_user["id"])
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to save screener")
    return saved


@router.get("/presets/{preset_id}", response_model=SavedScreenerResponse)
def get_preset(
    preset_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get a single saved preset for authenticated user."""
    saved = get_saved_screener(preset_id, user_id=current_user["id"])
    if not saved:
        raise HTTPException(status_code=404, detail="Preset not found")
    return saved


@router.delete("/presets/{preset_id}")
def remove_preset(
    preset_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a saved preset."""
    if not delete_saved_screener(preset_id, user_id=current_user["id"]):
        raise HTTPException(status_code=404, detail="Preset not found")
    return {"status": "deleted"}


# ---------------------------------------------------------------------------
# Helper: field definitions for the frontend filter builder
# ---------------------------------------------------------------------------

def _get_filter_field_definitions():
    """Return a structured list of all filterable fields with metadata."""
    return {
        "fundamental": [
            {"field": "market_cap_cr", "label": "Market Cap (₹ Cr)", "type": "range"},
            {"field": "close", "label": "Current Price (₹)", "type": "range"},
            {"field": "pe", "label": "P/E Ratio", "type": "range"},
            {"field": "pb", "label": "P/B Ratio", "type": "range"},
            {"field": "peg", "label": "PEG Ratio", "type": "range"},
            {"field": "roe", "label": "ROE (%)", "type": "range"},
            {"field": "roce", "label": "ROCE (%)", "type": "range"},
            {"field": "debt_equity", "label": "Debt/Equity", "type": "range"},
            {"field": "interest_coverage", "label": "Interest Coverage (x)", "type": "range"},
            {"field": "revenue_growth_pct", "label": "Revenue Growth (%)", "type": "range"},
            {"field": "profit_growth_pct", "label": "Profit Growth (%)", "type": "range"},
            {"field": "revenue_cagr_3y", "label": "3Y Revenue CAGR (%)", "type": "range"},
            {"field": "pat_cagr_3y", "label": "3Y PAT CAGR (%)", "type": "range"},
            {"field": "opm_pct", "label": "Operating Profit Margin (%)", "type": "range"},
            {"field": "cfo_pat_ratio", "label": "CFO / PAT (Cash Quality)", "type": "range"},
            {"field": "free_cash_flow_cr", "label": "Free Cash Flow (₹ Cr)", "type": "range"},
            {"field": "quality_score", "label": "Quality Score (0-100)", "type": "range"},
            {"field": "promoter_holding", "label": "Promoter Holding (%)", "type": "range"},
            {"field": "promoter_pledging", "label": "Promoter Pledging (%)", "type": "range"},
            {"field": "fii_holding", "label": "FII Holding (%)", "type": "range"},
            {"field": "dii_holding", "label": "DII Holding (%)", "type": "range"},
        ],

        "technical": [
            {"field": "rsi", "label": "RSI (14)", "type": "range"},
            {"field": "macd", "label": "MACD", "type": "range"},
            {"field": "macd_signal", "label": "MACD Signal", "type": "range"},
            {"field": "adx", "label": "ADX", "type": "range"},
            {"field": "ema_20", "label": "EMA 20", "type": "range"},
            {"field": "ema_50", "label": "EMA 50", "type": "range"},
            {"field": "ema_100", "label": "EMA 100", "type": "range"},
            {"field": "ema_200", "label": "EMA 200", "type": "range"},
            {"field": "sma_20", "label": "SMA 20", "type": "range"},
            {"field": "sma_50", "label": "SMA 50", "type": "range"},
            {"field": "sma_100", "label": "SMA 100", "type": "range"},
            {"field": "sma_200", "label": "SMA 200", "type": "range"},
            {"field": "volume", "label": "Volume", "type": "range"},
            {"field": "relative_volume", "label": "Relative Volume", "type": "range"},
            {"field": "return_1d_pct", "label": "Daily Return (%)", "type": "range"},
            {"field": "return_1w_pct", "label": "Weekly Return (%)", "type": "range"},
            {"field": "return_1m_pct", "label": "Monthly Return (%)", "type": "range"},
            {"field": "return_3m_pct", "label": "3-Month Return (%)", "type": "range"},
            {"field": "return_6m_pct", "label": "6-Month Return (%)", "type": "range"},
            {"field": "return_1y_pct", "label": "1-Year Return (%)", "type": "range"},
        ],
    }
