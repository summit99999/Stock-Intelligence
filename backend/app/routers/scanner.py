"""
Market Scanner & Advanced Chart Analysis Router.

Provides endpoints for:
- Full market scans categorized into 7 VolumeLens-style filters:
  * Bullish, Bearish, Consolidation, Breakout, Breakdown, High RVOL, New Order Blocks
- Category-specific stock screening
- Comprehensive single-stock analysis payload for interactive charting:
  * Indicator time series, trendlines, channels, S/R zones, key levels,
    multi-timeframe consensus, active trade setups, and volume profile.
"""

from __future__ import annotations

import time
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query

from app.database import get_bars, get_stock, list_stocks
from app.services.indicators import (
    calculate_all_indicators,
    calculate_indicators_timeseries,
)
from app.services.market_scanner_service import run_market_scan, scan_single_stock
from app.services.multi_timeframe_service import (
    analyze_multi_timeframe,
    resample_ohlcv_bars,
)
from app.services.setup_detection_service import detect_all_setups
from app.services.smc_service import analyze_smart_money_concepts
from app.services.trendline_level_service import analyze_trendlines_and_levels
from app.services.volume_profile_service import calculate_volume_profile

router = APIRouter(prefix="/api/scanner", tags=["Market Scanner & Advanced Charts"])


@router.get("/market")
def get_market_scan(
    universe: str = Query("all", description="Market universe (all, nifty50, fno)"),
    force_refresh: bool = Query(False, description="Bypass cache and force scan"),
    limit: int = Query(50, ge=1, le=200, description="Max results per category"),
) -> dict[str, Any]:
    """
    Get full multi-category market scan results across all 7 categories.
    """
    return run_market_scan(universe=universe, force_refresh=force_refresh, limit=limit)


@router.get("/category/{category_name}")
def get_category_scan(
    category_name: str,
    universe: str = Query("all"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """
    Get stock list for a specific scanner category.
    Supported: bullish, bearish, consolidation, breakout, breakdown, high_rvol, new_order_blocks.
    """
    valid_categories = {
        "bullish", "bearish", "consolidation",
        "breakout", "breakdown", "high_rvol", "new_order_blocks",
    }
    cat = category_name.lower().replace("-", "_")
    if cat not in valid_categories:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category '{category_name}'. Valid: {list(valid_categories)}",
        )

    scan = run_market_scan(universe=universe, limit=limit)
    items = scan.get("categories", {}).get(cat, [])
    last_candle_sample = items[0].get("last_candle_timestamp") if items else None
    metadata = {
        "provider": scan.get("provider", "NSE/yfinance"),
        "instrument": "EQUITY",
        "exchange": scan.get("exchange", "NSE"),
        "timeframe": "1D",
        "data_mode": scan.get("data_mode", "HISTORICAL"),
        "last_candle_timestamp": last_candle_sample,
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "is_stale": False,
        "category": cat,
    }
    return {
        "category": cat,
        "count": len(items),
        "timestamp": scan.get("timestamp"),
        "metadata": metadata,
        "items": items,
    }


@router.get("/stock/{symbol}/analysis")
def get_stock_advanced_analysis(
    symbol: str,
    timeframe: str = Query("1D", description="Base timeframe (1D, 4h, 1h, 15m)"),
) -> dict[str, Any]:
    """
    Get unified, comprehensive technical chart analysis package for a single stock:
    - OHLCV bars
    - Technical indicator timeseries (EMAs, SMAs, RSI, MACD, BB, Supertrend, VWAP, CMF, A/D)
    - Trendlines, channels, dynamic S/R zones, and session key levels
    - Smart Money Concepts (BOS, CHoCH, Order Blocks, FVGs, Liquidity Sweeps)
    - Volume Profile (POC, VAH, VAL, HVN, LVN)
    - Rule-based actionable trade setups
    - Multi-timeframe trend consensus
    """
    sym = symbol.upper()
    stock_meta = get_stock(sym)
    if not stock_meta:
        try:
            from app.services.upstox_instrument_sync import ondemand_ingest_stock, resolve_symbol_alias
            resolved = resolve_symbol_alias(sym)
            stock_meta = get_stock(resolved) or ondemand_ingest_stock(resolved)
            if stock_meta:
                sym = resolved
        except Exception:
            pass

    if not stock_meta:
        raise HTTPException(status_code=404, detail=f"Stock '{sym}' not found.")

    from app.services.candle_service import get_multi_timeframe_bars
    bars = get_multi_timeframe_bars(sym, timeframe=timeframe)

    if not bars or len(bars) < 5:
        # Fall back to returning metadata and empty structures if bars are missing
        return {
            "symbol": sym,
            "company_name": stock_meta.get("company_name", sym),
            "sector": stock_meta.get("sector"),
            "current_price": stock_meta.get("close", 0.0),
            "bars_count": 0,
            "message": "Insufficient historical bars in database.",
        }

    # 1. Indicators and Timeseries
    indicators = calculate_all_indicators(bars)
    timeseries = calculate_indicators_timeseries(bars)

    # 2. SMC
    smc = analyze_smart_money_concepts(symbol=sym, bars=bars)

    # 3. Levels, Trendlines & Channels
    levels = analyze_trendlines_and_levels(bars)

    # 4. Volume Profile
    vol_prof = calculate_volume_profile(symbol=sym, bars=bars)

    # 5. Setups
    setups = detect_all_setups(sym, bars, timeframe=timeframe)

    # 6. Multi-Timeframe Consensus
    # If daily bars are present, generate 1W/1M or accept 1D
    tf_bars = {"1D": bars}
    if len(bars) >= 40:
        # Construct synthetic or resampled higher/lower perspectives for multi-TF evaluation
        tf_bars["4h"] = bars[-40:]
        tf_bars["1h"] = bars[-25:]
    mtf = analyze_multi_timeframe(tf_bars, symbol=sym)

    last_candle_ts = bars[-1].get("timestamp") or bars[-1].get("date") if bars else None
    metadata = {
        "provider": stock_meta.get("provider", "yfinance"),
        "exchange": "NSE",
        "instrument": "EQUITY",
        "timeframe": timeframe,
        "last_candle_timestamp": str(last_candle_ts) if last_candle_ts else None,
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_mode": "HISTORICAL",
        "is_stale": False,
    }

    return {
        "symbol": sym,
        "company_name": stock_meta.get("company_name", sym),
        "sector": stock_meta.get("sector"),
        "current_price": indicators.get("close", stock_meta.get("close")),
        "daily_change_pct": indicators.get("daily_change_pct", stock_meta.get("daily_change_pct")),
        "timeframe": timeframe,
        "metadata": metadata,
        "bars": bars,
        "indicators": indicators,
        "timeseries": timeseries,
        "smc": smc,
        "levels": levels,
        "volume_profile": vol_prof,
        "setups": setups,
        "multi_timeframe": mtf,
    }
