"""
Volume Analytics and Order Flow API Router.

Exposes endpoints for:
- Volume Profile (POC, VAH, VAL, bins distribution)
- Rolling & Session VWAP
- Multi-tier Bid x Ask Footprint
- Cumulative Volume Delta (CVD)
"""

from __future__ import annotations

import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.database import get_stock
from app.services.order_flow_service import calculate_footprint_data
from app.services.volume_profile_service import calculate_volume_profile

router = APIRouter(prefix="/api", tags=["volume-analytics"])


@router.get("/volume/profile/{symbol}")
def get_volume_profile_endpoint(
    symbol: str,
    bins: int = Query(24, ge=10, le=100, description="Number of price bins"),
    limit: int = Query(100, ge=10, le=500, description="Number of historical bars to evaluate"),
):
    """
    Get Volume Profile for a specific stock:
    Returns POC, Value Area High (VAH), Value Area Low (VAL), and price bin distributions.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    res = calculate_volume_profile(symbol.upper(), num_bins=bins, limit=limit)
    stk_provider = stk.get("provider", "yfinance")
    last_candle_ts = stk.get("last_updated")
    res["metadata"] = {
        "provider": stk_provider,
        "instrument": "EQUITY",
        "exchange": "NSE",
        "timeframe": "1D",
        "data_mode": "HISTORICAL",
        "last_candle_timestamp": str(last_candle_ts) if last_candle_ts else None,
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "is_stale": False,
    }
    return res


@router.get("/volume/vwap/{symbol}")
def get_vwap_endpoint(
    symbol: str,
    limit: int = Query(100, ge=10, le=500),
):
    """
    Get Volume-Weighted Average Price metrics for a stock.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    res = calculate_volume_profile(symbol.upper(), num_bins=12, limit=limit)
    stk_provider = stk.get("provider", "yfinance")
    last_candle_ts = stk.get("last_updated")
    return {
        "symbol": symbol.upper(),
        "vwap": res.get("vwap"),
        "current_price": res.get("current_price"),
        "poc": res.get("poc"),
        "vah": res.get("vah"),
        "val": res.get("val"),
        "price_vs_poc": res.get("price_vs_poc"),
        "metadata": {
            "provider": stk_provider,
            "instrument": "EQUITY",
            "exchange": "NSE",
            "timeframe": "1D",
            "data_mode": "HISTORICAL",
            "last_candle_timestamp": str(last_candle_ts) if last_candle_ts else None,
            "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "is_stale": False,
        },
    }


@router.get("/orderflow/footprint/{symbol}")
def get_footprint_endpoint(
    symbol: str,
    limit: int = Query(30, ge=5, le=100, description="Number of bars to return footprint for"),
    levels: int = Query(6, ge=4, le=16, description="Price levels per candle"),
):
    """
    Get multi-tier Bid x Ask footprint candles with volume imbalances and delta.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    res = calculate_footprint_data(symbol.upper(), limit=limit, price_levels_per_bar=levels)
    return res


@router.get("/orderflow/cvd/{symbol}")
def get_cvd_endpoint(
    symbol: str,
    limit: int = Query(60, ge=10, le=200, description="Number of bars for CVD series"),
):
    """
    Get Cumulative Volume Delta (CVD) series for a stock.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    res = calculate_footprint_data(symbol.upper(), limit=limit)
    return {
        "symbol": symbol.upper(),
        "bars_count": res.get("bars_count"),
        "current_cvd": res.get("current_cvd"),
        "recent_delta_state": res.get("recent_delta_state"),
        "is_estimated": res.get("is_estimated"),
        "methodology": res.get("methodology"),
        "cvd_series": res.get("cvd_series"),
    }
