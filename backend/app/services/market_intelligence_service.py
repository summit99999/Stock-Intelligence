"""
Professional Market Intelligence Service (Phase 11).

Provides:
1. Comprehensive Market Overview:
   - Benchmark Indices (NIFTY 50, NIFTY NEXT 50, NIFTY 500, BANK NIFTY, INDIA VIX)
   - Advance / Decline / Unchanged market breadth & Advance/Decline Ratio
   - 52-Week Highs and Lows (new records & near-record stocks within 3%)
   - Market Regime determination (Score 0-100, Regime classification, Volatility state)
   - Market Leaders, Laggards, and Volume Surge stocks
2. Sector Intelligence:
   - Sector performance rankings
   - Relative performance against benchmark
   - Sector breadth (advances / declines per sector)
   - Sector leaders and laggards
   - Sector rotation quadrant (Leading, Weakening, Lagging, Improving)
   - Breakout and breakdown counts per sector
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
import numpy as np

from app.database import get_bars, list_stocks
from app.services.data_quality_service import (
    DataMode,
    audit_universe_coverage,
    build_standard_metadata,
)

logger = logging.getLogger(__name__)

# In-memory TTL Cache
_MARKET_OVERVIEW_CACHE: dict[str, Any] = {}
_MARKET_OVERVIEW_CACHE_TS: float = 0.0
_SECTOR_INTEL_CACHE: dict[str, Any] = {}
_SECTOR_INTEL_CACHE_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0

# Canonical universe constituents tracking
NIFTY_50_CORE = {
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HINDUNILVR",
    "SUNPHARMA", "TATAMOTORS", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
    "SBIN", "ASIANPAINT", "AXISBANK", "MARUTI", "TITAN", "BAJFINANCE",
    "WIPRO", "HCLTECH", "NTPC", "ONGC", "POWERGRID", "ADANIENT",
    "JSWSTEEL", "COALINDIA", "TATASTEEL", "BPCL", "EICHERMOT",
}

BANKING_CORE = {"HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK"}


def get_market_overview(
    universe: str = "all",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Compute comprehensive Market Overview and Breadth metrics.
    """
    global _MARKET_OVERVIEW_CACHE, _MARKET_OVERVIEW_CACHE_TS

    now = time.time()
    cache_key = f"{universe.lower()}"
    if not force_refresh and cache_key in _MARKET_OVERVIEW_CACHE and (now - _MARKET_OVERVIEW_CACHE_TS < _CACHE_TTL_SECONDS):
        cached = dict(_MARKET_OVERVIEW_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {"error": "No stocks found in database."}

    # Filter stocks if universe specified
    univ = universe.lower()
    if univ == "nifty50":
        target_stocks = [s for s in all_stocks if s.get("symbol") in NIFTY_50_CORE]
        universe_label = "NIFTY 50"
        configured_count = 50
    elif univ in ("nifty100", "nifty500"):
        target_stocks = all_stocks
        universe_label = "NIFTY 500" if univ == "nifty500" else "NIFTY 100"
        configured_count = 500 if univ == "nifty500" else 100
    elif univ == "fno":
        target_stocks = all_stocks
        universe_label = "NSE F&O Stocks"
        configured_count = 180
    else:
        target_stocks = all_stocks
        universe_label = "All Tracked NSE Stocks"
        configured_count = len(all_stocks)

    # 1. Breadth Metrics
    advances: list[dict[str, Any]] = []
    declines: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    highs_52w: list[dict[str, Any]] = []
    lows_52w: list[dict[str, Any]] = []
    near_highs_52w: list[dict[str, Any]] = []
    near_lows_52w: list[dict[str, Any]] = []

    changes: list[float] = []
    rvols: list[float] = []
    volatility_estimates: list[float] = []

    last_candle_sample: Optional[str] = None

    for s in target_stocks:
        sym = s.get("symbol", "")
        close = float(s.get("close") or 0.0)
        daily_chg = float(s.get("daily_change_pct") or 0.0)
        rvol = float(s.get("relative_volume") or 1.0)
        w52_h = float(s.get("week_52_high") or close)
        w52_l = float(s.get("week_52_low") or close)
        last_up = s.get("updated_at")
        if last_up and not last_candle_sample:
            last_candle_sample = last_up

        changes.append(daily_chg)
        rvols.append(rvol)

        stock_summary = {
            "symbol": sym,
            "company_name": s.get("company_name", sym),
            "sector": s.get("sector") or "Diversified",
            "close": round(close, 2),
            "daily_change_pct": round(daily_chg, 2),
            "relative_volume": round(rvol, 2),
            "week_52_high": round(w52_h, 2),
            "week_52_low": round(w52_l, 2),
            "pe": round(float(s.get("pe")), 2) if s.get("pe") else None,
            "market_cap_cr": round(float(s.get("market_cap_cr")), 2) if s.get("market_cap_cr") else None,
        }

        # Breadth buckets
        if daily_chg > 0.05:
            advances.append(stock_summary)
        elif daily_chg < -0.05:
            declines.append(stock_summary)
        else:
            unchanged.append(stock_summary)

        # 52W Extremes
        if w52_h > 0:
            diff_from_high_pct = (w52_h - close) / w52_h * 100
            if diff_from_high_pct <= 0.5:
                highs_52w.append(stock_summary)
            elif diff_from_high_pct <= 3.0:
                near_highs_52w.append(stock_summary)

        if w52_l > 0:
            diff_from_low_pct = (close - w52_l) / w52_l * 100
            if diff_from_low_pct <= 0.5:
                lows_52w.append(stock_summary)
            elif diff_from_low_pct <= 3.0:
                near_lows_52w.append(stock_summary)

        # Volatility estimate based on 52W range spread
        if close > 0 and w52_l > 0:
            spread_pct = (w52_h - w52_l) / close * 100
            volatility_estimates.append(spread_pct)

    total_tracked = len(target_stocks)
    adv_count = len(advances)
    dec_count = len(declines)
    unc_count = len(unchanged)
    ad_ratio = round(adv_count / max(dec_count, 1), 2)
    breadth_pct = round(adv_count / max(total_tracked, 1) * 100, 1)

    avg_market_change = float(np.mean(changes)) if changes else 0.0
    avg_rvol = float(np.mean(rvols)) if rvols else 1.0

    # 2. Grounded Index Calculations
    # Base reference values for Indian Indices
    nifty_changes = [float(s.get("daily_change_pct") or 0.0) for s in target_stocks if s.get("symbol") in NIFTY_50_CORE]
    avg_nifty_change = float(np.mean(nifty_changes)) if nifty_changes else avg_market_change

    bank_changes = [float(s.get("daily_change_pct") or 0.0) for s in target_stocks if s.get("symbol") in BANKING_CORE]
    avg_bank_change = float(np.mean(bank_changes)) if bank_changes else avg_market_change

    # Synthesize realistic index values grounded in actual component changes
    base_nifty = 24850.0
    base_banknifty = 51200.0
    base_nifty500 = 23100.0
    base_midcap = 58200.0

    current_nifty = round(base_nifty * (1.0 + avg_nifty_change / 100.0), 2)
    current_banknifty = round(base_banknifty * (1.0 + avg_bank_change / 100.0), 2)
    current_nifty500 = round(base_nifty500 * (1.0 + avg_market_change / 100.0), 2)
    current_midcap = round(base_midcap * (1.0 + (avg_market_change * 1.1) / 100.0), 2)

    # Component dispersion proxy for volatility regime (NOT claimed as actual INDIA VIX)
    dispersion = float(np.std(changes)) if changes else 1.2

    # Standardized index representations with explicit ESTIMATED and UNAVAILABLE data modes
    indices = [
        {
            "name": "NIFTY 50",
            "symbol": "NIFTY 50",
            "value": f"{current_nifty:,.2f}",
            "numeric_value": current_nifty,
            "change_pct": round(avg_nifty_change, 2),
            "high": f"{round(current_nifty * 1.004, 2):,.2f}",
            "low": f"{round(current_nifty * 0.995, 2):,.2f}",
            "positive": avg_nifty_change >= 0,
            "data_mode": DataMode.ESTIMATED.value,
            "is_estimated": True,
            "status": "ESTIMATED",
            "source": "ESTIMATED_COMPONENT_WEIGHTED",
            "source_note": "Synthesized from tracked component equities; not a direct live exchange index feed.",
        },
        {
            "name": "BANK NIFTY",
            "symbol": "BANK NIFTY",
            "value": f"{current_banknifty:,.2f}",
            "numeric_value": current_banknifty,
            "change_pct": round(avg_bank_change, 2),
            "high": f"{round(current_banknifty * 1.006, 2):,.2f}",
            "low": f"{round(current_banknifty * 0.993, 2):,.2f}",
            "positive": avg_bank_change >= 0,
            "data_mode": DataMode.ESTIMATED.value,
            "is_estimated": True,
            "status": "ESTIMATED",
            "source": "ESTIMATED_COMPONENT_WEIGHTED",
            "source_note": "Synthesized from tracked component equities; not a direct live exchange index feed.",
        },
        {
            "name": "NIFTY 500",
            "symbol": "NIFTY 500",
            "value": f"{current_nifty500:,.2f}",
            "numeric_value": current_nifty500,
            "change_pct": round(avg_market_change, 2),
            "high": f"{round(current_nifty500 * 1.005, 2):,.2f}",
            "low": f"{round(current_nifty500 * 0.994, 2):,.2f}",
            "positive": avg_market_change >= 0,
            "data_mode": DataMode.ESTIMATED.value,
            "is_estimated": True,
            "status": "ESTIMATED",
            "source": "ESTIMATED_COMPONENT_WEIGHTED",
            "source_note": "Synthesized from tracked component equities; not a direct live exchange index feed.",
        },
        {
            "name": "NIFTY MIDCAP",
            "symbol": "NIFTY MIDCAP",
            "value": f"{current_midcap:,.2f}",
            "numeric_value": current_midcap,
            "change_pct": round(avg_market_change * 1.1, 2),
            "high": f"{round(current_midcap * 1.008, 2):,.2f}",
            "low": f"{round(current_midcap * 0.992, 2):,.2f}",
            "positive": avg_market_change >= 0,
            "data_mode": DataMode.ESTIMATED.value,
            "is_estimated": True,
            "status": "ESTIMATED",
            "source": "ESTIMATED_COMPONENT_WEIGHTED",
            "source_note": "Synthesized from tracked component equities; not a direct live exchange index feed.",
        },
        {
            "name": "INDIA VIX",
            "symbol": "INDIA VIX",
            "value": "UNAVAILABLE",
            "numeric_value": None,
            "change_pct": None,
            "high": "UNAVAILABLE",
            "low": "UNAVAILABLE",
            "positive": None,
            "data_mode": DataMode.UNAVAILABLE.value,
            "is_estimated": False,
            "status": "UNAVAILABLE",
            "source": "NSE_OPTIONS_IMPLIED_VOLATILITY_REQUIRED",
            "disclaimer": "Actual INDIA VIX requires official NSE options-implied volatility feed, which is currently unavailable. Stock dispersion formula cannot represent implied volatility.",
        },
    ]

    # 3. Market Regime Determination
    # Composite score 0 to 100 based on breadth, average change, and AD ratio
    score_breadth = breadth_pct * 0.5
    score_return = max(0.0, min(30.0, (avg_market_change + 2.0) / 4.0 * 30.0))
    score_ad = min(20.0, (ad_ratio / 2.0) * 20.0)
    regime_score = round(max(0.0, min(100.0, score_breadth + score_return + score_ad)), 1)

    if regime_score >= 70.0 and avg_market_change > 0.5:
        regime = "STRONG_BULLISH"
        regime_desc = "Broad-based institutional buying across sectors with positive market breadth."
    elif regime_score >= 55.0:
        regime = "MODERATE_BULLISH"
        regime_desc = "Selective accumulation with positive advance/decline bias."
    elif regime_score <= 30.0 and avg_market_change < -0.5:
        regime = "STRONG_BEARISH"
        regime_desc = "Widespread selling pressure with severe downside breadth dominance."
    elif regime_score <= 45.0:
        regime = "MODERATE_BEARISH"
        regime_desc = "Defensive distribution with declining issues exceeding advancing issues."
    else:
        regime = "NEUTRAL"
        regime_desc = "Balanced rotation and consolidation between leading sectors."

    volatility_regime = "LOW" if dispersion < 1.0 else ("NORMAL" if dispersion < 1.8 else ("ELEVATED" if dispersion < 2.5 else "HIGH"))

    # 4. Gainers, Losers, and Volume Surge
    sorted_by_change = sorted(target_stocks, key=lambda x: float(x.get("daily_change_pct") or 0.0), reverse=True)
    sorted_by_rvol = sorted(target_stocks, key=lambda x: float(x.get("relative_volume") or 1.0), reverse=True)

    def _fmt_item(item: dict) -> dict[str, Any]:
        return {
            "symbol": item.get("symbol"),
            "company_name": item.get("company_name"),
            "sector": item.get("sector") or "General",
            "close": round(float(item.get("close") or 0.0), 2),
            "daily_change_pct": round(float(item.get("daily_change_pct") or 0.0), 2),
            "relative_volume": round(float(item.get("relative_volume") or 1.0), 2),
            "pe": round(float(item.get("pe")), 2) if item.get("pe") else None,
        }

    top_gainers = [_fmt_item(x) for x in sorted_by_change[:6]]
    top_losers = [_fmt_item(x) for x in sorted_by_change[-6:][::-1]]
    top_volume_surge = [_fmt_item(x) for x in sorted_by_rvol[:6]]

    target_syms = {s.get("symbol") for s in target_stocks} if univ == "nifty50" else None
    coverage_audit = audit_universe_coverage(universe_name=universe, target_symbols=target_syms)

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY_INDEX_COMPOSITE",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    metadata["last_candle_timestamp"] = str(last_candle_sample) if last_candle_sample else None
    metadata["cache_ttl_seconds"] = int(_CACHE_TTL_SECONDS)
    metadata["is_cached"] = False

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "universe_label": universe_label,
        "configured_universe_count": coverage_audit["configured_instruments"],
        "scanned_count": coverage_audit["tracked_instruments"],
        "coverage_pct": coverage_audit["coverage_pct"],
        "coverage_note": coverage_audit["coverage_disclosure"],
        "coverage": coverage_audit,
        "metadata": metadata,
        "indices": indices,
        "breadth": {
            "advances": adv_count,
            "declines": dec_count,
            "unchanged": unc_count,
            "total_tracked": total_tracked,
            "sample_size": total_tracked,
            "advance_decline_ratio": ad_ratio,
            "breadth_pct": breadth_pct,
            "average_market_change": round(avg_market_change, 2),
            "average_relative_volume": round(avg_rvol, 2),
            "sample_disclosure": f"Breadth statistics calculated across {total_tracked} tracked NSE equities in database (sample subset of {universe_label}).",
        },
        "extremes_52w": {
            "highs_count": len(highs_52w),
            "lows_count": len(lows_52w),
            "near_highs_count": len(near_highs_52w),
            "near_lows_count": len(near_lows_52w),
            "new_highs": highs_52w,
            "new_lows": lows_52w,
            "near_highs": near_highs_52w[:10],
            "near_lows": near_lows_52w[:10],
        },
        "market_regime": {
            "regime": regime,
            "score": regime_score,
            "description": regime_desc,
            "volatility_regime": volatility_regime,
            "vix_value": "UNAVAILABLE",
            "vix_status": "UNAVAILABLE",
            "dispersion_std_pct": round(dispersion, 2),
            "vix_disclaimer": "Actual options-implied INDIA VIX feed unavailable. Volatility regime estimated from component return dispersion.",
        },
        "leaders": {
            "gainers": top_gainers,
            "losers": top_losers,
            "volume_surge": top_volume_surge,
        },
    }

    _MARKET_OVERVIEW_CACHE[cache_key] = result
    _MARKET_OVERVIEW_CACHE_TS = now
    return result


def get_sector_intelligence(
    universe: str = "all",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Compute deep sector strength, relative performance, breadth, and rotation quadrants.
    """
    global _SECTOR_INTEL_CACHE, _SECTOR_INTEL_CACHE_TS

    now = time.time()
    cache_key = f"{universe.lower()}"
    if not force_refresh and cache_key in _SECTOR_INTEL_CACHE and (now - _SECTOR_INTEL_CACHE_TS < _CACHE_TTL_SECONDS):
        cached = dict(_SECTOR_INTEL_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {"error": "No stocks found in database."}

    # Group by sector
    sectors_map: dict[str, list[dict[str, Any]]] = {}
    all_changes: list[float] = []

    for s in all_stocks:
        sec = s.get("sector") or "Diversified"
        sectors_map.setdefault(sec, []).append(s)
        all_changes.append(float(s.get("daily_change_pct") or 0.0))

    benchmark_avg_change = float(np.mean(all_changes)) if all_changes else 0.0

    sector_results: list[dict[str, Any]] = []

    for sec_name, stock_list in sectors_map.items():
        count = len(stock_list)
        chgs = [float(s.get("daily_change_pct") or 0.0) for s in stock_list]
        rsis = [float(s.get("rsi") or 50.0) for s in stock_list]
        rvols = [float(s.get("relative_volume") or 1.0) for s in stock_list]

        avg_chg = round(float(np.mean(chgs)), 2)
        avg_rsi = round(float(np.mean(rsis)), 2)
        avg_rvol = round(float(np.mean(rvols)), 2)

        adv_count = sum(1 for c in chgs if c > 0.05)
        dec_count = sum(1 for c in chgs if c < -0.05)
        unc_count = count - adv_count - dec_count
        breadth_pct = round(adv_count / max(count, 1) * 100, 1)

        # Leaders and Laggards
        sorted_sector_stocks = sorted(stock_list, key=lambda s: float(s.get("daily_change_pct") or 0.0), reverse=True)
        top_stock = sorted_sector_stocks[0]
        bot_stock = sorted_sector_stocks[-1]

        # Breakouts and Breakdowns
        breakout_count = sum(1 for s in stock_list if float(s.get("relative_volume") or 1.0) >= 1.4 and float(s.get("daily_change_pct") or 0.0) >= 1.5)
        breakdown_count = sum(1 for s in stock_list if float(s.get("relative_volume") or 1.0) >= 1.4 and float(s.get("daily_change_pct") or 0.0) <= -1.5)

        # Relative Strength vs benchmark
        rs_vs_market = round(avg_chg - benchmark_avg_change, 2)

        # Rotation Quadrant
        # LEADING: RS > 0 and Momentum (avg_chg) > 0
        # WEAKENING: RS > 0 and Momentum <= 0
        # LAGGING: RS <= 0 and Momentum <= 0
        # IMPROVING: RS <= 0 and Momentum > 0
        if rs_vs_market >= 0 and avg_chg >= 0:
            quadrant = "LEADING"
            quadrant_color = "emerald"
        elif rs_vs_market >= 0 and avg_chg < 0:
            quadrant = "WEAKENING"
            quadrant_color = "amber"
        elif rs_vs_market < 0 and avg_chg <= 0:
            quadrant = "LAGGING"
            quadrant_color = "rose"
        else:
            quadrant = "IMPROVING"
            quadrant_color = "blue"

        # Prominent constituents string
        leaders_str = ", ".join(s.get("symbol") for s in sorted_sector_stocks[:3])

        sector_results.append({
            "sector": sec_name,
            "stock_count": count,
            "average_change_pct": avg_chg,
            "average_rsi": avg_rsi,
            "average_rvol": avg_rvol,
            "advances": adv_count,
            "declines": dec_count,
            "unchanged": unc_count,
            "breadth_pct": breadth_pct,
            "relative_strength_vs_market": rs_vs_market,
            "rotation_quadrant": quadrant,
            "quadrant_color": quadrant_color,
            "breakout_count": breakout_count,
            "breakdown_count": breakdown_count,
            "strongest_stock": {
                "symbol": top_stock.get("symbol"),
                "company_name": top_stock.get("company_name"),
                "change_pct": round(float(top_stock.get("daily_change_pct") or 0.0), 2),
                "close": round(float(top_stock.get("close") or 0.0), 2),
            },
            "weakest_stock": {
                "symbol": bot_stock.get("symbol"),
                "company_name": bot_stock.get("company_name"),
                "change_pct": round(float(bot_stock.get("daily_change_pct") or 0.0), 2),
                "close": round(float(bot_stock.get("close") or 0.0), 2),
            },
            "prominent_stocks": leaders_str,
            "positive": avg_chg >= 0,
        })

    # Sort sectors by performance descending
    sector_results.sort(key=lambda x: x["average_change_pct"], reverse=True)

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="SECTOR_COMPOSITE",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    metadata["cache_ttl_seconds"] = int(_CACHE_TTL_SECONDS)
    metadata["is_cached"] = False

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_sectors": len(sector_results),
        "benchmark_average_change": round(benchmark_avg_change, 2),
        "metadata": metadata,
        "sectors": sector_results,
    }

    _SECTOR_INTEL_CACHE[cache_key] = result
    _SECTOR_INTEL_CACHE_TS = now
    return result
