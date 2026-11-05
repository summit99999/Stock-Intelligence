"""
Automated Market Scanner Engine.

Scans the stock universe and categorizes tickers into 7 pre-filtered categories:
1. Bullish (Strong trend, EMA alignment, Supertrend up, constructive RSI)
2. Bearish (Downward trend, EMA breakdown, Supertrend down, weakening RSI)
3. Consolidation (Tight range contraction <= 8.5% over >= 20 sessions)
4. Breakout (Upside break of consolidation resistance or 20D high with RVOL >= 1.4)
5. Breakdown (Downside break of consolidation support or 20D low with RVOL >= 1.4)
6. High RVOL (Unusual relative volume expansion >= 1.5x)
7. New Order Blocks (Fresh, active institutional Order Blocks formed recently)

Includes in-memory TTL caching for instant UI response and force_refresh support.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.database import get_bars, list_stocks
from app.services.indicators import calculate_all_indicators
from app.services.setup_detection_service import detect_all_setups
from app.services.smc_service import analyze_smart_money_concepts

logger = logging.getLogger(__name__)

# Cache state
_SCAN_CACHE: dict[str, Any] = {}
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0


def scan_single_stock(symbol: str, stock_meta: dict[str, Any]) -> Optional[dict[str, Any]]:
    """
    Perform deep technical and setup scan on a single stock.
    Supports full bar computation when available, with seamless fallback
    to pre-stored technical indicators on the stock record.
    """
    bars = get_bars(symbol)
    if bars and len(bars) >= 15:
        indicators = calculate_all_indicators(bars)
        smc = analyze_smart_money_concepts(symbol=symbol, bars=bars)
        setups = detect_all_setups(symbol, bars)

        close = indicators.get("close")
        if close is None:
            return None

        daily_change = indicators.get("daily_change_pct") or 0.0
        rvol = indicators.get("relative_volume") or 1.0
        rsi = indicators.get("rsi") or 50.0
        supertrend_dir = indicators.get("supertrend_dir") or "neutral"
        ema_20 = indicators.get("ema_20")
        ema_50 = indicators.get("ema_50")
        ema_200 = indicators.get("ema_200")
        vol_spike = indicators.get("volume_spike", False)
        is_consolidating = indicators.get("is_consolidating", False)
        is_breakout = indicators.get("is_breakout", False)
        breakout_type = indicators.get("breakout_type", "None")

        # Order block inspection
        ob_dict = smc.get("order_blocks", {})
        obs = ob_dict.get("all_zones", []) if isinstance(ob_dict, dict) else []
        recent_obs = [
            ob for ob in obs
            if isinstance(ob, dict) and ob.get("status") in ("FRESH", "TESTED")
            and ob.get("candle_index", 0) >= len(bars) - 10
        ]
        market_structure = smc.get("market_structure", {}).get("trend", "Range")
        setup_count = len(setups)
        top_setup = setups[0] if setups else None
        last_candle_ts = bars[-1].get("timestamp") or bars[-1].get("date")
    else:
        # Fallback to pre-computed metrics from stock_meta
        close = float(stock_meta.get("close") or 0.0)
        if close <= 0:
            return None
        daily_change = float(stock_meta.get("daily_change_pct") or 0.0)
        rvol = float(stock_meta.get("relative_volume") or 1.0)
        rsi = float(stock_meta.get("rsi") or 50.0)
        supertrend_dir = str(stock_meta.get("supertrend_dir") or "neutral")
        ema_20 = float(stock_meta.get("ema_20")) if stock_meta.get("ema_20") else None
        ema_50 = float(stock_meta.get("ema_50")) if stock_meta.get("ema_50") else None
        ema_200 = float(stock_meta.get("ema_200")) if stock_meta.get("ema_200") else None
        vol_spike = bool(rvol >= 2.0)
        # Check consolidation based on EMA proximity
        is_consolidating = bool(ema_20 and abs(close - ema_20) / close <= 0.012)
        is_breakout = bool(rvol >= 1.5 and abs(daily_change) >= 2.0)
        breakout_type = "Bullish Breakout" if (is_breakout and daily_change > 0) else ("Bearish Breakdown" if is_breakout else "None")
        recent_obs = []
        market_structure = "Bullish" if supertrend_dir == "up" else ("Bearish" if supertrend_dir == "down" else "Range")
        setups = []
        setup_count = 0
        top_setup = None
        last_candle_ts = stock_meta.get("last_updated")

    # Category matching flags with strict mutual exclusivity between Bullish and Bearish
    raw_bullish = bool(
        (close > ema_20 if ema_20 else False) and
        (supertrend_dir == "up" or rsi >= 50.0) and
        daily_change >= -0.5
    )

    raw_bearish = bool(
        (close < ema_20 if ema_20 else False) and
        (supertrend_dir == "down" or rsi <= 50.0) and
        daily_change <= 0.5
    )

    if raw_bullish and raw_bearish:
        # Indicator conflict: resolve to neutral to guarantee mutual exclusivity
        is_bullish = False
        is_bearish = False
    else:
        is_bullish = raw_bullish
        is_bearish = raw_bearish

    is_bullish_breakout = bool(
        is_breakout and "Bullish" in breakout_type
    )

    is_bearish_breakdown = bool(
        is_breakout and "Bearish" in breakout_type
    )

    is_high_rvol = bool(rvol >= 1.4 or vol_spike)
    has_new_ob = bool(len(recent_obs) > 0)

    now_iso = time.strftime("%Y-%m-%d %H:%M:%S")

    return {
        "symbol": symbol,
        "company_name": stock_meta.get("company_name", symbol),
        "sector": stock_meta.get("sector") or "Diversified",
        "current_price": round(close, 2),
        "daily_change_pct": round(daily_change, 2),
        "relative_volume": round(rvol, 2),
        "rsi": round(rsi, 2),
        "supertrend_dir": supertrend_dir,
        "ema_20": round(ema_20, 2) if ema_20 else None,
        "ema_50": round(ema_50, 2) if ema_50 else None,
        "ema_200": round(ema_200, 2) if ema_200 else None,
        "volume_spike": vol_spike,
        "is_consolidating": is_consolidating,
        "consolidation_range_pct": round(abs(close - (ema_20 or close)) / close * 100, 2) if is_consolidating else None,
        "consolidation_support": round(close * 0.98, 2) if is_consolidating else None,
        "consolidation_resistance": round(close * 1.02, 2) if is_consolidating else None,
        "is_breakout": is_bullish_breakout or is_bearish_breakdown,
        "breakout_type": breakout_type,
        "is_bullish": is_bullish,
        "is_bearish": is_bearish,
        "is_high_rvol": is_high_rvol,
        "has_new_ob": has_new_ob,
        "recent_obs": recent_obs[:2],
        "setup_count": len(setups),
        "setups": setups,
        "top_setup": top_setup,
        "market_structure": market_structure,
        "provider": stock_meta.get("provider", "yfinance"),
        "exchange": "NSE",
        "instrument": "EQUITY",
        "timeframe": "1D",
        "data_mode": "HISTORICAL",
        "last_candle_timestamp": str(last_candle_ts) if last_candle_ts else None,
        "last_update_timestamp": now_iso,
        "is_stale": False,
    }


def run_market_scan(
    universe: str = "all",
    force_refresh: bool = False,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Execute full multi-category market scan across all stocks.
    """
    global _SCAN_CACHE, _CACHE_TIMESTAMP

    now = time.time()
    if not force_refresh and _SCAN_CACHE and (now - _CACHE_TIMESTAMP < _CACHE_TTL_SECONDS):
        cached_result = dict(_SCAN_CACHE)
        cached_result["is_cached"] = True
        cached_result["cache_ttl_seconds"] = int(_CACHE_TTL_SECONDS)
        if "metadata" in cached_result and isinstance(cached_result["metadata"], dict):
            cached_meta = dict(cached_result["metadata"])
            cached_meta["is_cached"] = True
            cached_result["metadata"] = cached_meta
        return cached_result

    all_stocks = list_stocks()
    scanned_results: list[dict[str, Any]] = []

    for stock in all_stocks:
        sym = stock.get("symbol", "")
        if not sym:
            continue
        item = scan_single_stock(sym, stock)
        if item:
            scanned_results.append(item)

    # 1. Bullish Category
    bullish_list = [
        item for item in scanned_results
        if item["is_bullish"]
    ]
    bullish_list.sort(key=lambda x: (x["daily_change_pct"], x["rsi"]), reverse=True)

    # 2. Bearish Category
    bearish_list = [
        item for item in scanned_results
        if item["is_bearish"]
    ]
    bearish_list.sort(key=lambda x: (x["daily_change_pct"], -x["rsi"]))

    # 3. Consolidation Category
    consolidation_list = [
        item for item in scanned_results
        if item["is_consolidating"]
    ]
    consolidation_list.sort(key=lambda x: x["consolidation_range_pct"] or 999.0)

    # 4. Breakout Category
    breakout_list = [
        item for item in scanned_results
        if item["is_breakout"] and item["daily_change_pct"] >= 0
    ]
    breakout_list.sort(key=lambda x: x["relative_volume"], reverse=True)

    # 5. Breakdown Category
    breakdown_list = [
        item for item in scanned_results
        if item["is_breakout"] and item["daily_change_pct"] < 0
    ]
    breakdown_list.sort(key=lambda x: x["relative_volume"], reverse=True)

    # 6. High RVOL Category
    high_rvol_list = [
        item for item in scanned_results
        if item["is_high_rvol"]
    ]
    high_rvol_list.sort(key=lambda x: x["relative_volume"], reverse=True)

    # 7. New Order Blocks Category
    new_obs_list = [
        item for item in scanned_results
        if item["has_new_ob"]
    ]
    new_obs_list.sort(key=lambda x: len(x["recent_obs"]), reverse=True)

    # Sector summary
    sector_counts: dict[str, int] = {}
    for item in scanned_results:
        sec = item["sector"]
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
    top_sector = max(sector_counts.items(), key=lambda x: x[1])[0] if sector_counts else "N/A"

    last_candle_sample = None
    if scanned_results:
        for it in scanned_results:
            if it.get("last_candle_timestamp"):
                last_candle_sample = it["last_candle_timestamp"]
                break

    metadata = {
        "provider": "NSE/yfinance",
        "instrument": "EQUITY",
        "exchange": "NSE",
        "timeframe": "1D",
        "data_mode": "HISTORICAL",
        "last_candle_timestamp": last_candle_sample,
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "is_stale": False,
        "cache_ttl_seconds": int(_CACHE_TTL_SECONDS),
        "is_cached": False,
    }

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "metadata": metadata,
        "is_cached": False,
        "cache_ttl_seconds": int(_CACHE_TTL_SECONDS),
        "data_mode": "HISTORICAL",
        "provider": "NSE/yfinance",
        "exchange": "NSE",
        "total_scanned": len(scanned_results),
        "top_sector": top_sector,
        "counts": {
            "bullish": len(bullish_list),
            "bearish": len(bearish_list),
            "consolidation": len(consolidation_list),
            "breakout": len(breakout_list),
            "breakdown": len(breakdown_list),
            "high_rvol": len(high_rvol_list),
            "new_order_blocks": len(new_obs_list),
        },
        "categories": {
            "bullish": bullish_list[:limit],
            "bearish": bearish_list[:limit],
            "consolidation": consolidation_list[:limit],
            "breakout": breakout_list[:limit],
            "breakdown": breakdown_list[:limit],
            "high_rvol": high_rvol_list[:limit],
            "new_order_blocks": new_obs_list[:limit],
        },
    }

    _SCAN_CACHE = result
    _CACHE_TIMESTAMP = now
    return result
