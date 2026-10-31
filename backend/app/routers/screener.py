"""Screener API router."""

from __future__ import annotations

import csv
import io
import json
import math

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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
    SaveScreenerRequest,
    SavedScreenerResponse,
    ScreenRequest,
    ScreenResponse,
    StockResult,
)
from app.services.screener_service import run_screen

router = APIRouter(prefix="/api/screener", tags=["screener"])


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
def get_presets():
    """List saved screener presets."""
    return list_saved_screeners()


@router.post("/presets", response_model=SavedScreenerResponse)
def create_preset(req: SaveScreenerRequest):
    """Save a screener preset."""
    config_json = req.config.model_dump_json()
    row_id = save_screener(req.name, req.description, config_json)
    saved = get_saved_screener(row_id)
    if not saved:
        raise HTTPException(status_code=500, detail="Failed to save screener")
    return saved


@router.get("/presets/{preset_id}", response_model=SavedScreenerResponse)
def get_preset(preset_id: int):
    """Get a single saved preset."""
    saved = get_saved_screener(preset_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Preset not found")
    return saved


@router.delete("/presets/{preset_id}")
def remove_preset(preset_id: int):
    """Delete a saved preset."""
    if not delete_saved_screener(preset_id):
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
            {"field": "roe", "label": "ROE (%)", "type": "range"},
            {"field": "roce", "label": "ROCE (%)", "type": "range"},
            {"field": "debt_equity", "label": "Debt/Equity", "type": "range"},
            {"field": "revenue_growth_pct", "label": "Revenue Growth (%)", "type": "range"},
            {"field": "profit_growth_pct", "label": "Profit Growth (%)", "type": "range"},
            {"field": "opm_pct", "label": "Operating Profit Margin (%)", "type": "range"},
            {"field": "free_cash_flow_cr", "label": "Free Cash Flow (₹ Cr)", "type": "range"},
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
