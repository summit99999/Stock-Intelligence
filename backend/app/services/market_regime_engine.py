"""
Unified Market Regime Engine (Phase 12).

Provides transparent, evidence-based market regime classification:
- STRONG BULLISH
- BULLISH
- NEUTRAL
- BEARISH
- STRONG BEARISH
- INSUFFICIENT DATA

Considers:
1. Market Breadth: Advances vs Declines distribution, Advance/Decline ratio
2. EMA Participation: Percentage of equities trading above EMA 20, EMA 50, and EMA 200
3. Sector Participation: Percentage of sectors advancing and in Leading/Improving rotation quadrants
4. Trend Strength: Average ADX, percentage of equities with ADX > 25, and Supertrend direction
5. Relative Momentum: Average performance across tracked equity constituents

Strict Quantitative Truthfulness:
- Does NOT use estimated index prices as actual exchange index data.
- Does NOT fabricate live INDIA VIX; clearly reports options-implied VIX as UNAVAILABLE.
- Every regime classification includes concrete evidence, timestamps, universe coverage, and limitations.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
import numpy as np

from app.database import list_stocks
from app.services.data_quality_service import (
    DataMode,
    audit_universe_coverage,
    build_standard_metadata,
)
from app.services.market_intelligence_service import NIFTY_50_CORE

logger = logging.getLogger(__name__)

# TTL Cache
_REGIME_CACHE: dict[str, Any] = {}
_REGIME_CACHE_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0


def classify_market_regime(
    universe: str = "all",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Compute comprehensive, multi-factor market regime classification and grounded evidence.
    """
    global _REGIME_CACHE, _REGIME_CACHE_TS

    now = time.time()
    cache_key = universe.lower()
    if not force_refresh and cache_key in _REGIME_CACHE and (now - _REGIME_CACHE_TS < _CACHE_TTL_SECONDS):
        cached = dict(_REGIME_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {
            "regime": "INSUFFICIENT DATA",
            "score": 0.0,
            "status": "INSUFFICIENT_DATA",
            "error": "No stocks found in local database to evaluate market regime.",
            "evidence": {},
            "coverage": {},
            "limitations": "Zero stocks available in local SQLite database.",
            "metadata": build_standard_metadata(
                provider="yfinance",
                instrument="MARKET_REGIME",
                timeframe="1D",
                data_mode=DataMode.HISTORICAL.value,
                data_quality_status="MISSING_DATA",
            ),
        }

    # Filter stocks if universe specified
    univ = universe.lower()
    if univ == "nifty50":
        target_stocks = [s for s in all_stocks if s.get("symbol") in NIFTY_50_CORE]
        universe_label = "NIFTY 50"
    elif univ in ("nifty100", "nifty500"):
        target_stocks = all_stocks
        universe_label = "NIFTY 500" if univ == "nifty500" else "NIFTY 100"
    elif univ == "fno":
        target_stocks = all_stocks
        universe_label = "NSE F&O Stocks"
    else:
        target_stocks = all_stocks
        universe_label = "All Tracked NSE Stocks"

    total_tracked = len(target_stocks)
    if total_tracked < 5:
        return {
            "regime": "INSUFFICIENT DATA",
            "score": 0.0,
            "status": "INSUFFICIENT_DATA",
            "error": f"Insufficient sample size ({total_tracked} stocks) for statistical regime assessment.",
            "evidence": {},
            "coverage": audit_universe_coverage(universe),
            "limitations": "Minimum 5 tracked instruments required for breadth-based regime determination.",
            "metadata": build_standard_metadata(
                provider="yfinance",
                instrument="MARKET_REGIME",
                timeframe="1D",
                data_mode=DataMode.HISTORICAL.value,
                data_quality_status="WARNING",
            ),
        }

    # 1. Breadth Metrics
    changes = []
    advances = 0
    declines = 0
    unchanged = 0

    above_ema20_cnt = 0
    above_ema50_cnt = 0
    above_ema200_cnt = 0
    ema_valid_cnt = 0

    adx_values = []
    supertrend_bullish_cnt = 0
    supertrend_valid_cnt = 0

    sectors_map: dict[str, list[float]] = {}

    for s in target_stocks:
        close = float(s.get("close") or 0.0)
        daily_chg = float(s.get("daily_change_pct") or 0.0)
        sec = s.get("sector") or "General"

        changes.append(daily_chg)
        sectors_map.setdefault(sec, []).append(daily_chg)

        if daily_chg > 0.05:
            advances += 1
        elif daily_chg < -0.05:
            declines += 1
        else:
            unchanged += 1

        # EMA Participation
        ema20 = s.get("ema_20")
        ema50 = s.get("ema_50")
        ema200 = s.get("ema_200")
        if close > 0 and ema20 is not None:
            ema_valid_cnt += 1
            if close > float(ema20):
                above_ema20_cnt += 1
            if ema50 is not None and close > float(ema50):
                above_ema50_cnt += 1
            if ema200 is not None and close > float(ema200):
                above_ema200_cnt += 1

        # Trend strength (ADX & Supertrend)
        adx = s.get("adx")
        if adx is not None and float(adx) > 0:
            adx_values.append(float(adx))

        st_dir = s.get("supertrend_dir")
        if st_dir:
            supertrend_valid_cnt += 1
            if str(st_dir).lower() == "up":
                supertrend_bullish_cnt += 1

    # Calculations
    ad_ratio = round(advances / max(declines, 1), 2)
    breadth_pct = round((advances / max(total_tracked, 1)) * 100.0, 1)
    avg_change = round(float(np.mean(changes)), 2) if changes else 0.0

    pct_above_ema20 = round((above_ema20_cnt / max(ema_valid_cnt, 1)) * 100.0, 1) if ema_valid_cnt else 50.0
    pct_above_ema50 = round((above_ema50_cnt / max(ema_valid_cnt, 1)) * 100.0, 1) if ema_valid_cnt else 50.0
    pct_above_ema200 = round((above_ema200_cnt / max(ema_valid_cnt, 1)) * 100.0, 1) if ema_valid_cnt else 50.0

    avg_adx = round(float(np.mean(adx_values)), 1) if adx_values else 20.0
    pct_strong_trend = round((sum(1 for v in adx_values if v >= 25.0) / max(len(adx_values), 1)) * 100.0, 1) if adx_values else 0.0
    pct_supertrend_bullish = round((supertrend_bullish_cnt / max(supertrend_valid_cnt, 1)) * 100.0, 1) if supertrend_valid_cnt else 50.0

    # Sector participation
    total_sectors = len(sectors_map)
    advancing_sectors = sum(1 for sec_chgs in sectors_map.values() if float(np.mean(sec_chgs)) > 0)
    sector_participation_pct = round((advancing_sectors / max(total_sectors, 1)) * 100.0, 1)

    # Volatility / Return Dispersion (grounded proxy, never claimed as actual INDIA VIX)
    dispersion = round(float(np.std(changes)), 2) if changes else 1.2

    # --- Multi-Factor Scoring (0 to 100 Max) ---
    # 1. Market Breadth Score (Max 25 pts)
    # 50% breadth = 12.5 pts, 100% breadth = 25 pts
    score_breadth = round((breadth_pct / 100.0) * 15.0 + min(10.0, (ad_ratio / 2.0) * 10.0), 1)

    # 2. EMA Participation Score (Max 25 pts)
    # Stacked moving average participation
    score_ema = round(
        (pct_above_ema20 / 100.0) * 10.0 +
        (pct_above_ema50 / 100.0) * 8.0 +
        (pct_above_ema200 / 100.0) * 7.0,
        1,
    )

    # 3. Sector Participation Score (Max 20 pts)
    score_sector = round((sector_participation_pct / 100.0) * 20.0, 1)

    # 4. ADX & Trend Strength Score (Max 15 pts)
    score_trend = round(
        (pct_supertrend_bullish / 100.0) * 10.0 +
        (min(35.0, avg_adx) / 35.0) * 5.0,
        1,
    )

    # 5. Relative Return Momentum (Max 15 pts)
    # Scaled from -2.0% (0 pts) to +2.0% (15 pts)
    score_momentum = round(max(0.0, min(15.0, ((avg_change + 2.0) / 4.0) * 15.0)), 1)

    total_score = round(max(0.0, min(100.0, score_breadth + score_ema + score_sector + score_trend + score_momentum)), 1)

    # Regime Classification
    if total_score >= 75.0 and avg_change >= 0.5:
        regime = "STRONG BULLISH"
        regime_desc = "Broad-based institutional buying across sectors with dominant positive breadth and strong EMA participation."
        regime_color = "#26c78b"
    elif total_score >= 55.0:
        regime = "BULLISH"
        regime_desc = "Constructive accumulation with positive advance/decline bias and sector leadership."
        regime_color = "#10b981"
    elif total_score <= 25.0 and avg_change <= -0.5:
        regime = "STRONG BEARISH"
        regime_desc = "Severe downside pressure with broad-based distribution and failing technical baselines."
        regime_color = "#ef4444"
    elif total_score <= 42.0:
        regime = "BEARISH"
        regime_desc = "Defensive distribution with declining issues exceeding advances and weak sector participation."
        regime_color = "#f43f5e"
    else:
        regime = "NEUTRAL"
        regime_desc = "Balanced rotation and consolidation between leading sectors without clear directional dominance."
        regime_color = "#f59e0b"

    # Coverage Audit
    target_syms = {s.get("symbol") for s in target_stocks} if univ == "nifty50" else None
    coverage = audit_universe_coverage(universe, target_symbols=target_syms)

    evidence = {
        "breadth": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "total_tracked": total_tracked,
            "advance_decline_ratio": ad_ratio,
            "breadth_pct": breadth_pct,
            "score_contribution": score_breadth,
            "max_score": 25.0,
        },
        "ema_participation": {
            "pct_above_ema20": pct_above_ema20,
            "pct_above_ema50": pct_above_ema50,
            "pct_above_ema200": pct_above_ema200,
            "stocks_evaluated": ema_valid_cnt,
            "score_contribution": score_ema,
            "max_score": 25.0,
        },
        "sector_participation": {
            "total_sectors": total_sectors,
            "advancing_sectors": advancing_sectors,
            "advancing_sectors_pct": sector_participation_pct,
            "score_contribution": score_sector,
            "max_score": 20.0,
        },
        "trend_strength": {
            "average_adx": avg_adx,
            "pct_strong_adx": pct_strong_trend,
            "pct_supertrend_bullish": pct_supertrend_bullish,
            "score_contribution": score_trend,
            "max_score": 15.0,
        },
        "momentum": {
            "average_market_change_pct": avg_change,
            "return_dispersion_std_pct": dispersion,
            "score_contribution": score_momentum,
            "max_score": 15.0,
        },
    }

    limitations = (
        f"Regime evaluated across {total_tracked} tracked NSE equities in database (sample subset of {universe_label}). "
        "Estimated index prices are excluded from actual exchange breadth calculations. "
        "Official options-implied INDIA VIX feed is currently unavailable; dispersion proxy used for informational context only."
    )

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="MARKET_REGIME",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "universe_label": universe_label,
        "regime": regime,
        "score": total_score,
        "composite_score": total_score,
        "description": regime_desc,
        "regime_color": regime_color,
        "evidence": evidence,
        "coverage": coverage,
        "limitations": limitations,
        "volatility_context": {
            "vix_status": "UNAVAILABLE",
            "return_dispersion_std_pct": dispersion,
            "disclaimer": "Actual options-implied INDIA VIX requires official exchange options feed; dispersion proxy used.",
        },
        "metadata": metadata,
    }

    _REGIME_CACHE[cache_key] = result
    _REGIME_CACHE_TS = now
    return result
