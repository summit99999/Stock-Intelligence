"""
Advanced Multi-Condition Stock Scanner & 7-System Ranking Engine (Phase 11).

Provides:
- Universe filtering with transparent coverage disclosures:
  * all, nifty50, nifty100, nifty500, fno
- Multi-condition technical filters with AND / OR evaluation logic:
  * Price vs EMA 20/50/100/200
  * RSI range filters
  * MACD crossover states
  * ADX trend strength
  * Supertrend direction
  * Relative Volume (RVOL) thresholds & volume expansion/contraction
  * Bollinger Band squeeze & ATR expansion
  * Mansfield Relative Strength
  * Consolidation & breakout metrics
  * Smart Money Concepts (Order Block retest, BOS/CHoCH, FVG retracement)
- Fundamental screening integration:
  * Profit, Revenue, EPS growth
  * ROE, ROCE, Debt/Equity, OPM
  * Promoter holding and pledging
  * Valuation (P/E, P/B)
- 7 Dedicated Transparent Ranking Systems:
  1. Bullish Opportunity Ranking
  2. Bearish Weakness Ranking
  3. Breakout Candidates
  4. Breakdown Candidates
  5. High Relative Strength Stocks
  6. High-Volume Accumulation Candidates
  7. Consolidation Candidates
- Full pagination (page, page_size, total_pages, total_records) and CSV export.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import time
from typing import Any, Optional
import numpy as np

from app.database import get_bars, list_stocks
from app.services.data_quality_service import (
    DataMode,
    audit_universe_coverage,
    build_standard_metadata,
)
from app.services.indicators import calculate_all_indicators
from app.services.market_intelligence_service import NIFTY_50_CORE
from app.services.setup_detection_service import detect_all_setups
from app.services.smc_service import analyze_smart_money_concepts

logger = logging.getLogger(__name__)

# Ranking Preset Keys
RANKING_PRESETS = {
    "BULLISH_OPPORTUNITY",
    "BEARISH_WEAKNESS",
    "BREAKOUT_CANDIDATES",
    "BREAKDOWN_CANDIDATES",
    "HIGH_RELATIVE_STRENGTH",
    "HIGH_VOLUME_ACCUMULATION",
    "CONSOLIDATION_CANDIDATES",
}


def _evaluate_stock_technicals(symbol: str, meta: dict[str, Any]) -> dict[str, Any]:
    """
    Extract or calculate technical indicators, SMC signals, and fundamental ratios.
    """
    close = float(meta.get("close") or 0.0)
    daily_change = float(meta.get("daily_change_pct") or 0.0)
    rvol = float(meta.get("relative_volume") or 1.0)
    rsi = float(meta.get("rsi") or 50.0)
    supertrend_dir = str(meta.get("supertrend_dir") or "neutral").lower()

    ema_20 = float(meta.get("ema_20")) if meta.get("ema_20") else None
    ema_50 = float(meta.get("ema_50")) if meta.get("ema_50") else None
    ema_100 = float(meta.get("ema_100")) if meta.get("ema_100") else None
    ema_200 = float(meta.get("ema_200")) if meta.get("ema_200") else None

    macd = float(meta.get("macd")) if meta.get("macd") is not None else 0.0
    macd_signal = float(meta.get("macd_signal")) if meta.get("macd_signal") is not None else 0.0
    macd_hist = macd - macd_signal
    adx = float(meta.get("adx")) if meta.get("adx") is not None else 20.0

    w52_high = float(meta.get("week_52_high") or close)
    w52_low = float(meta.get("week_52_low") or close)

    # Defaults
    is_consolidating = False
    consolidation_range_pct = 0.0
    is_breakout = False
    breakout_type = "None"
    bb_bandwidth = 10.0
    atr_pct = 2.0
    mansfield_rs_50 = 0.0
    has_fresh_ob = False
    has_fvg = False
    structure_trend = "Range"
    recent_obs: list[dict[str, Any]] = []

    bars = get_bars(symbol)
    if bars and len(bars) >= 15:
        inds = calculate_all_indicators(bars)
        smc = analyze_smart_money_concepts(symbol=symbol, bars=bars)

        if inds.get("close"):
            close = float(inds["close"])
        if inds.get("daily_change_pct") is not None:
            daily_change = float(inds["daily_change_pct"])
        if inds.get("relative_volume") is not None:
            rvol = float(inds["relative_volume"])
        if inds.get("rsi") is not None:
            rsi = float(inds["rsi"])
        if inds.get("supertrend_dir"):
            supertrend_dir = str(inds["supertrend_dir"]).lower()

        ema_20 = inds.get("ema_20", ema_20)
        ema_50 = inds.get("ema_50", ema_50)
        ema_100 = inds.get("ema_100", ema_100)
        ema_200 = inds.get("ema_200", ema_200)

        macd = float(inds.get("macd") or 0.0)
        macd_signal = float(inds.get("macd_signal") or 0.0)
        macd_hist = float(inds.get("macd_histogram") or (macd - macd_signal))
        adx = float(inds.get("adx") or 20.0)

        is_consolidating = bool(inds.get("is_consolidating", False))
        is_breakout = bool(inds.get("is_breakout", False))
        breakout_type = inds.get("breakout_type", "None")
        bb_bandwidth = float(inds.get("bb_bandwidth") or 10.0)

        atr_val = float(inds.get("atr_14") or (close * 0.02))
        atr_pct = round((atr_val / max(close, 1e-4)) * 100, 2)

        mansfield_rs_50 = float(inds.get("mansfield_rs_50") or (daily_change * 1.5))

        # SMC data
        ob_dict = smc.get("order_blocks", {})
        obs = ob_dict.get("all_zones", []) if isinstance(ob_dict, dict) else []
        recent_obs = [
            ob for ob in obs
            if isinstance(ob, dict) and ob.get("status") in ("FRESH", "TESTED")
        ]
        has_fresh_ob = any(ob.get("status") == "FRESH" for ob in recent_obs)

        fvgs = smc.get("fair_value_gaps", {}).get("all_fvgs", [])
        has_fvg = len(fvgs) > 0
        structure_trend = smc.get("market_structure", {}).get("trend", "Range")
    else:
        # Fallback estimation from metadata
        if ema_20:
            is_consolidating = abs(close - ema_20) / close <= 0.015
            consolidation_range_pct = round(abs(close - ema_20) / close * 100, 2)
        if rvol >= 1.5 and abs(daily_change) >= 2.0:
            is_breakout = True
            breakout_type = "Bullish Breakout" if daily_change > 0 else "Bearish Breakdown"
        structure_trend = "Bullish" if supertrend_dir == "up" else ("Bearish" if supertrend_dir == "down" else "Range")
        mansfield_rs_50 = round(daily_change * 1.2, 2)

    # Fundamental fields from stock record
    pe = float(meta.get("pe")) if meta.get("pe") is not None else None
    pb = float(meta.get("pb")) if meta.get("pb") is not None else None
    roe = float(meta.get("roe")) if meta.get("roe") is not None else None
    roce = float(meta.get("roce")) if meta.get("roce") is not None else None
    debt_equity = float(meta.get("debt_equity")) if meta.get("debt_equity") is not None else None
    revenue_growth_pct = float(meta.get("revenue_growth_pct")) if meta.get("revenue_growth_pct") is not None else None
    profit_growth_pct = float(meta.get("profit_growth_pct")) if meta.get("profit_growth_pct") is not None else None
    opm_pct = float(meta.get("opm_pct")) if meta.get("opm_pct") is not None else None
    promoter_holding = float(meta.get("promoter_holding")) if meta.get("promoter_holding") is not None else None
    promoter_pledging = float(meta.get("promoter_pledging")) if meta.get("promoter_pledging") is not None else None
    market_cap_cr = float(meta.get("market_cap_cr")) if meta.get("market_cap_cr") is not None else None

    return {
        "symbol": symbol,
        "company_name": meta.get("company_name", symbol),
        "sector": meta.get("sector") or "Diversified",
        "industry": meta.get("industry") or "General",
        "cap_category": meta.get("cap_category") or "large_cap",
        "close": round(close, 2),
        "daily_change_pct": round(daily_change, 2),
        "relative_volume": round(rvol, 2),
        "rsi": round(rsi, 2),
        "supertrend_dir": supertrend_dir,
        "ema_20": round(ema_20, 2) if ema_20 else None,
        "ema_50": round(ema_50, 2) if ema_50 else None,
        "ema_100": round(ema_100, 2) if ema_100 else None,
        "ema_200": round(ema_200, 2) if ema_200 else None,
        "macd": round(macd, 2),
        "macd_signal": round(macd_signal, 2),
        "macd_histogram": round(macd_hist, 2),
        "adx": round(adx, 2),
        "bb_bandwidth": round(bb_bandwidth, 2),
        "atr_pct": round(atr_pct, 2),
        "mansfield_rs_50": round(mansfield_rs_50, 2),
        "is_consolidating": is_consolidating,
        "consolidation_range_pct": consolidation_range_pct,
        "is_breakout": is_breakout,
        "breakout_type": breakout_type,
        "has_fresh_ob": has_fresh_ob,
        "has_fvg": has_fvg,
        "structure_trend": structure_trend,
        "week_52_high": round(w52_high, 2),
        "week_52_low": round(w52_low, 2),
        # Fundamental
        "market_cap_cr": round(market_cap_cr, 2) if market_cap_cr else None,
        "pe": round(pe, 2) if pe else None,
        "pb": round(pb, 2) if pb else None,
        "roe": round(roe, 2) if roe else None,
        "roce": round(roce, 2) if roce else None,
        "debt_equity": round(debt_equity, 2) if debt_equity else None,
        "revenue_growth_pct": round(revenue_growth_pct, 2) if revenue_growth_pct else None,
        "profit_growth_pct": round(profit_growth_pct, 2) if profit_growth_pct else None,
        "opm_pct": round(opm_pct, 2) if opm_pct else None,
        "promoter_holding": round(promoter_holding, 2) if promoter_holding else None,
        "promoter_pledging": round(promoter_pledging, 2) if promoter_pledging else None,
    }


def _matches_filters(item: dict[str, Any], filters: dict[str, Any], logic_mode: str = "AND") -> bool:
    """
    Evaluate technical and fundamental filter conditions with AND / OR combination logic.
    """
    if not filters:
        return True

    condition_results: list[bool] = []
    close = item["close"]

    # Technical Checks
    if filters.get("price_above_ema20") is not None:
        passed = bool(item["ema_20"] and close > item["ema_20"])
        condition_results.append(passed)

    if filters.get("price_below_ema20") is not None:
        passed = bool(item["ema_20"] and close < item["ema_20"])
        condition_results.append(passed)

    if filters.get("price_above_ema50") is not None:
        passed = bool(item["ema_50"] and close > item["ema_50"])
        condition_results.append(passed)

    if filters.get("price_below_ema50") is not None:
        passed = bool(item["ema_50"] and close < item["ema_50"])
        condition_results.append(passed)

    if filters.get("price_above_ema200") is not None:
        passed = bool(item["ema_200"] and close > item["ema_200"])
        condition_results.append(passed)

    if filters.get("price_below_ema200") is not None:
        passed = bool(item["ema_200"] and close < item["ema_200"])
        condition_results.append(passed)

    if filters.get("ema20_above_ema50") is not None:
        passed = bool(item["ema_20"] and item["ema_50"] and item["ema_20"] > item["ema_50"])
        condition_results.append(passed)

    if filters.get("min_rsi") is not None:
        passed = bool(item["rsi"] >= float(filters["min_rsi"]))
        condition_results.append(passed)

    if filters.get("max_rsi") is not None:
        passed = bool(item["rsi"] <= float(filters["max_rsi"]))
        condition_results.append(passed)

    if filters.get("macd_bullish_cross") is not None:
        passed = bool(item["macd"] > item["macd_signal"] and item["macd_histogram"] > 0)
        condition_results.append(passed)

    if filters.get("macd_bearish_cross") is not None:
        passed = bool(item["macd"] < item["macd_signal"] and item["macd_histogram"] < 0)
        condition_results.append(passed)

    if filters.get("min_adx") is not None:
        passed = bool(item["adx"] >= float(filters["min_adx"]))
        condition_results.append(passed)

    if filters.get("supertrend_dir") is not None:
        expected = str(filters["supertrend_dir"]).lower()
        passed = bool(item["supertrend_dir"] == expected)
        condition_results.append(passed)

    if filters.get("min_rvol") is not None:
        passed = bool(item["relative_volume"] >= float(filters["min_rvol"]))
        condition_results.append(passed)

    if filters.get("volume_expansion") is True:
        passed = bool(item["relative_volume"] >= 1.4)
        condition_results.append(passed)

    if filters.get("volume_contraction") is True:
        passed = bool(item["relative_volume"] <= 0.8)
        condition_results.append(passed)

    if filters.get("bb_squeeze") is True:
        passed = bool(item["bb_bandwidth"] <= 8.0)
        condition_results.append(passed)

    if filters.get("min_atr_pct") is not None:
        passed = bool(item["atr_pct"] >= float(filters["min_atr_pct"]))
        condition_results.append(passed)

    if filters.get("mansfield_rs_positive") is True:
        passed = bool(item["mansfield_rs_50"] > 0)
        condition_results.append(passed)

    if filters.get("is_consolidating") is not None:
        passed = bool(item["is_consolidating"] == filters["is_consolidating"])
        condition_results.append(passed)

    if filters.get("is_breakout") is not None:
        passed = bool(item["is_breakout"] == filters["is_breakout"])
        condition_results.append(passed)

    if filters.get("has_fresh_ob") is not None:
        passed = bool(item["has_fresh_ob"] == filters["has_fresh_ob"])
        condition_results.append(passed)

    if filters.get("has_fvg") is not None:
        passed = bool(item["has_fvg"] == filters["has_fvg"])
        condition_results.append(passed)

    if filters.get("structure_trend") is not None:
        passed = bool(item["structure_trend"].lower() == str(filters["structure_trend"]).lower())
        condition_results.append(passed)

    # Fundamental Checks
    if filters.get("min_profit_growth") is not None:
        val = item["profit_growth_pct"]
        passed = bool(val is not None and val >= float(filters["min_profit_growth"]))
        condition_results.append(passed)

    if filters.get("min_revenue_growth") is not None:
        val = item["revenue_growth_pct"]
        passed = bool(val is not None and val >= float(filters["min_revenue_growth"]))
        condition_results.append(passed)

    if filters.get("min_roe") is not None:
        val = item["roe"]
        passed = bool(val is not None and val >= float(filters["min_roe"]))
        condition_results.append(passed)

    if filters.get("min_roce") is not None:
        val = item["roce"]
        passed = bool(val is not None and val >= float(filters["min_roce"]))
        condition_results.append(passed)

    if filters.get("max_debt_equity") is not None:
        val = item["debt_equity"]
        passed = bool(val is not None and val <= float(filters["max_debt_equity"]))
        condition_results.append(passed)

    if filters.get("min_opm") is not None:
        val = item["opm_pct"]
        passed = bool(val is not None and val >= float(filters["min_opm"]))
        condition_results.append(passed)

    if filters.get("min_promoter_holding") is not None:
        val = item["promoter_holding"]
        passed = bool(val is not None and val >= float(filters["min_promoter_holding"]))
        condition_results.append(passed)

    if filters.get("max_promoter_pledging") is not None:
        val = item["promoter_pledging"]
        passed = bool(val is not None and val <= float(filters["max_promoter_pledging"]))
        condition_results.append(passed)

    if filters.get("min_pe") is not None:
        val = item["pe"]
        passed = bool(val is not None and val >= float(filters["min_pe"]))
        condition_results.append(passed)

    if filters.get("max_pe") is not None:
        val = item["pe"]
        passed = bool(val is not None and val <= float(filters["max_pe"]))
        condition_results.append(passed)

    if filters.get("min_market_cap_cr") is not None:
        val = item["market_cap_cr"]
        passed = bool(val is not None and val >= float(filters["min_market_cap_cr"]))
        condition_results.append(passed)

    if not condition_results:
        return True

    if logic_mode.upper() == "OR":
        return any(condition_results)
    return all(condition_results)


def _compute_ranking_score(item: dict[str, Any], ranking_preset: str) -> tuple[float, str]:
    """
    Compute transparent rank score (0-100) and rationale for each of the 7 ranking systems.
    """
    close = item["close"]
    daily_change = item["daily_change_pct"]
    rvol = item["relative_volume"]
    rsi = item["rsi"]
    supertrend_dir = item["supertrend_dir"]
    ema_20 = item["ema_20"]
    ema_50 = item["ema_50"]
    ema_200 = item["ema_200"]
    mansfield_rs = item["mansfield_rs_50"]

    if ranking_preset == "BULLISH_OPPORTUNITY":
        score = 0.0
        reasons = []
        if ema_20 and close > ema_20:
            score += 20.0
            reasons.append("Above EMA20")
        if ema_50 and close > ema_50:
            score += 15.0
            reasons.append("Above EMA50")
        if ema_20 and ema_50 and ema_20 > ema_50:
            score += 15.0
            reasons.append("EMA20>50")
        if supertrend_dir == "up":
            score += 20.0
            reasons.append("Supertrend Bullish")
        if 50.0 <= rsi <= 68.0:
            score += 15.0
            reasons.append(f"RSI in sweet spot ({rsi})")
        elif rsi > 68.0:
            score += 10.0
        if daily_change > 0:
            score += min(10.0, daily_change * 3.0)
            reasons.append(f"+{daily_change}% gain")
        if rvol >= 1.2:
            score += min(10.0, (rvol - 1.0) * 10.0)
            reasons.append(f"RVOL {rvol}x")
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Bullish bias"

    elif ranking_preset == "BEARISH_WEAKNESS":
        score = 0.0
        reasons = []
        if ema_20 and close < ema_20:
            score += 25.0
            reasons.append("Below EMA20")
        if ema_50 and close < ema_50:
            score += 20.0
            reasons.append("Below EMA50")
        if supertrend_dir == "down":
            score += 25.0
            reasons.append("Supertrend Bearish")
        if rsi < 45.0:
            score += 15.0
            reasons.append(f"Weak RSI ({rsi})")
        if daily_change < 0:
            score += min(15.0, abs(daily_change) * 3.0)
            reasons.append(f"{daily_change}% loss")
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Bearish bias"

    elif ranking_preset == "BREAKOUT_CANDIDATES":
        score = 0.0
        reasons = []
        if item["is_breakout"] and "Bullish" in item["breakout_type"]:
            score += 40.0
            reasons.append("Confirmed Upside Breakout")
        elif daily_change >= 1.5:
            score += 25.0
            reasons.append("Strong Daily Impulsive Move")
        if rvol >= 1.5:
            score += min(30.0, rvol * 15.0)
            reasons.append(f"High RVOL ({rvol}x)")
        if daily_change > 0:
            score += min(20.0, daily_change * 4.0)
        if item["has_fresh_ob"]:
            score += 10.0
            reasons.append("Fresh Institutional OB")
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Breakout candidate"

    elif ranking_preset == "BREAKDOWN_CANDIDATES":
        score = 0.0
        reasons = []
        if item["is_breakout"] and "Bearish" in item["breakout_type"]:
            score += 40.0
            reasons.append("Confirmed Downside Breakdown")
        elif daily_change <= -1.5:
            score += 25.0
            reasons.append("Severe Impulsive Drop")
        if rvol >= 1.4:
            score += min(30.0, rvol * 15.0)
            reasons.append(f"Volume Expansion on Decline ({rvol}x)")
        if supertrend_dir == "down":
            score += 15.0
            reasons.append("Supertrend Down")
        if daily_change < 0:
            score += min(15.0, abs(daily_change) * 3.0)
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Breakdown candidate"

    elif ranking_preset == "HIGH_RELATIVE_STRENGTH":
        score = 0.0
        reasons = []
        if mansfield_rs > 0:
            score += min(40.0, 20.0 + mansfield_rs * 4.0)
            reasons.append(f"Outperforming NIFTY (RS {mansfield_rs})")
        if 55.0 <= rsi <= 75.0:
            score += 25.0
            reasons.append(f"Bullish RSI Momentum ({rsi})")
        if ema_200 and close > ema_200:
            score += 20.0
            reasons.append("Above 200 EMA")
        if daily_change > 0:
            score += min(15.0, daily_change * 3.0)
            reasons.append(f"+{daily_change}% Session Gain")
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "High RS leader"

    elif ranking_preset == "HIGH_VOLUME_ACCUMULATION":
        score = 0.0
        reasons = []
        if rvol >= 1.4:
            score += min(45.0, rvol * 22.0)
            reasons.append(f"Heavy RVOL Surge ({rvol}x)")
        if daily_change >= 0.5:
            score += min(30.0, daily_change * 8.0)
            reasons.append("Constructive Price Absorption")
        elif daily_change >= 0:
            score += 15.0
        if item["has_fresh_ob"]:
            score += 15.0
            reasons.append("Fresh Demand Block Formed")
        if rsi >= 50:
            score += 10.0
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Accumulation signal"

    elif ranking_preset == "CONSOLIDATION_CANDIDATES":
        score = 0.0
        reasons = []
        if item["is_consolidating"]:
            score += 45.0
            reasons.append("Multi-Session Range Compression")
        if item["bb_bandwidth"] <= 7.0:
            score += 25.0
            reasons.append(f"Bollinger Squeeze ({item['bb_bandwidth']}%)")
        elif item["bb_bandwidth"] <= 10.0:
            score += 15.0
        if rvol <= 0.9:
            score += 20.0
            reasons.append(f"Volume Dry-up ({rvol}x)")
        if ema_20 and abs(close - ema_20) / close <= 0.01:
            score += 10.0
            reasons.append("Hugging EMA20 Baseline")
        return round(min(100.0, score), 1), "; ".join(reasons) if reasons else "Consolidation base"

    # Default sort score based on daily change
    return round(daily_change, 2), "Daily Performance"


def run_advanced_scan(
    universe: str = "all",
    ranking_preset: Optional[str] = None,
    logic_mode: str = "AND",
    filters: Optional[dict[str, Any]] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    Execute full advanced screening across technical, fundamental, and ranking systems.
    """
    filters = filters or {}
    all_stocks = list_stocks()
    if not all_stocks:
        return {"items": [], "total_records": 0, "page": page, "total_pages": 0}

    # Universe Selection
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

    # 1. Evaluate indicators and filter
    evaluated_items: list[dict[str, Any]] = []
    for s in target_stocks:
        sym = s.get("symbol", "")
        if not sym:
            continue
        eval_item = _evaluate_stock_technicals(sym, s)

        # Apply filters
        if _matches_filters(eval_item, filters, logic_mode=logic_mode):
            # Compute ranking score if preset chosen
            if ranking_preset and ranking_preset.upper() in RANKING_PRESETS:
                score, reason = _compute_ranking_score(eval_item, ranking_preset.upper())
                eval_item["rank_score"] = score
                eval_item["rank_reason"] = reason
            else:
                eval_item["rank_score"] = eval_item["daily_change_pct"]
                eval_item["rank_reason"] = f"{eval_item['daily_change_pct']}% daily change"

            evaluated_items.append(eval_item)

    # 2. Sort results
    reverse = sort_order.lower() == "desc"
    active_sort = sort_by or ("rank_score" if ranking_preset else "daily_change_pct")

    def _sort_key(item: dict[str, Any]) -> Any:
        val = item.get(active_sort)
        if val is None:
            return -999999.0 if reverse else 999999.0
        return val

    evaluated_items.sort(key=_sort_key, reverse=reverse)

    # Assign rank numbers
    for idx, item in enumerate(evaluated_items, start=1):
        item["rank"] = idx

    # 3. Pagination
    total_records = len(evaluated_items)
    page_size = max(1, min(page_size, 100))
    total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * page_size
    paged_items = evaluated_items[start_idx : start_idx + page_size]

    last_candle_sample = paged_items[0].get("last_candle_timestamp") if paged_items else None

    target_syms = {s.get("symbol") for s in target_stocks} if univ == "nifty50" else None
    coverage = audit_universe_coverage(universe_name=universe, target_symbols=target_syms)

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    metadata["last_candle_timestamp"] = last_candle_sample
    metadata["universe"] = universe
    metadata["universe_label"] = universe_label
    metadata["scanned_count"] = coverage["tracked_instruments"]
    metadata["configured_universe_count"] = coverage["configured_instruments"]
    metadata["coverage_pct"] = coverage["coverage_pct"]
    metadata["coverage_disclosure"] = coverage["coverage_disclosure"]

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "universe_label": universe_label,
        "configured_universe_count": coverage["configured_instruments"],
        "scanned_count": coverage["tracked_instruments"],
        "coverage_pct": coverage["coverage_pct"],
        "coverage_note": coverage["coverage_disclosure"],
        "coverage": coverage,
        "ranking_preset": ranking_preset,
        "logic_mode": logic_mode,
        "applied_filters": filters,
        "total_records": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "metadata": metadata,
        "items": paged_items,
    }


def export_scan_to_csv(scan_result: dict[str, Any]) -> str:
    """
    Format scan items into standard RFC 4180 CSV string.
    """
    items = scan_result.get("items", [])
    if not items:
        return "Rank,Symbol,Company,Sector,Price,Change%,RVOL,RSI,Supertrend,RankScore,Rationale\n"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Rank", "Symbol", "Company", "Sector", "Price", "Change%",
        "RVOL", "RSI", "Supertrend", "EMA20", "EMA50", "EMA200",
        "PE", "ROE%", "Debt/Equity", "RankScore", "Rationale"
    ])

    for it in items:
        writer.writerow([
            it.get("rank", ""),
            it.get("symbol", ""),
            it.get("company_name", ""),
            it.get("sector", ""),
            it.get("close", ""),
            it.get("daily_change_pct", ""),
            it.get("relative_volume", ""),
            it.get("rsi", ""),
            it.get("supertrend_dir", ""),
            it.get("ema_20", ""),
            it.get("ema_50", ""),
            it.get("ema_200", ""),
            it.get("pe", ""),
            it.get("roe", ""),
            it.get("debt_equity", ""),
            it.get("rank_score", ""),
            it.get("rank_reason", ""),
        ])

    return output.getvalue()
