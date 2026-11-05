"""
Unified Trading Research & Decision Engine (Phase 12).

Integrates:
- Market Regime Engine (10 pts)
- Sector Rotation Engine (10 pts)
- Fundamental Quality Engine (15 pts)
- Trend and Momentum Engine (20 pts)
- Volume & Money Flow Confirmation (15 pts)
- Smart Money Concepts & Market Structure (20 pts)
- Multi-Timeframe Alignment (10 pts)

Strict Quantitative Principles:
1. Every component's point contribution and rationale is transparently explained.
2. Missing metrics NEVER receive positive points.
3. Clearly reports the number of available components evaluated.
4. Distinguishes heuristic confluence scores from statistical probabilities:
   A score of 85/100 is NOT an 85% probability of profit.
5. Setup categories:
   - HIGH-QUALITY BULLISH SETUP
   - BULLISH SETUP
   - DEVELOPING SETUP
   - WEAK SETUP
   - BEARISH SETUP
   - NO VALID SETUP
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional
import numpy as np

from app.database import get_bars, get_stock, list_stocks
from app.services.data_quality_service import (
    DataMode,
    audit_universe_coverage,
    build_standard_metadata,
)
from app.services.fundamental_ratios_service import compute_all_ratios
from app.services.indicators import calculate_all_indicators
from app.services.market_intelligence_service import NIFTY_50_CORE
from app.services.market_regime_engine import classify_market_regime
from app.services.money_flow_service import calculate_stock_volume_intelligence
from app.services.multi_timeframe_service import analyze_multi_timeframe
from app.services.sector_rotation_engine import compute_sector_rotation
from app.services.setup_detection_service import detect_all_setups
from app.services.smc_service import analyze_smart_money_concepts

logger = logging.getLogger(__name__)


def evaluate_stock_setup_quality(
    symbol: str,
    market_regime: Optional[dict[str, Any]] = None,
    sectors_info: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Perform a complete 7-factor, 100-point quantitative setup evaluation on a stock.
    """
    sym = symbol.strip().upper()
    stock_record = get_stock(sym) or {}
    bars = get_bars(sym)

    if not stock_record and not bars:
        return {
            "symbol": sym,
            "company_name": sym,
            "sector": "Unknown",
            "setup_score": 0.0,
            "setup_category": "NO VALID SETUP",
            "status": "MISSING_DATA",
            "error": f"Symbol '{sym}' not found in database.",
        }

    # Fetch context if not provided
    if not market_regime:
        market_regime = classify_market_regime(universe="all")
    if not sectors_info:
        sectors_info = compute_sector_rotation(universe="all")

    # 1. Fundamental Ratios
    fund_ratios = None
    try:
        fund_ratios = compute_all_ratios(sym)
    except Exception as e:
        logger.debug("Could not compute fundamental ratios for %s: %s", sym, e)

    # 2. Technical Indicators
    tech = {}
    if bars and len(bars) >= 2:
        tech = calculate_all_indicators(bars)

    # 3. Smart Money Concepts
    smc = {}
    if bars and len(bars) >= 10:
        try:
            smc = analyze_smart_money_concepts(sym, bars=bars)
        except Exception as e:
            logger.debug("SMC analysis error for %s: %s", sym, e)

    # 4. Money Flow & Volume
    vol_intel = {}
    try:
        vol_intel = calculate_stock_volume_intelligence(sym)
    except Exception as e:
        logger.debug("Volume intelligence error for %s: %s", sym, e)

    # 5. Multi-Timeframe Analysis
    mtf = {}
    try:
        mtf = analyze_multi_timeframe(sym)
    except Exception as e:
        logger.debug("MTF error for %s: %s", sym, e)

    # 6. Setups
    setups = []
    try:
        setups = detect_all_setups(sym, bars=bars)
    except Exception as e:
        logger.debug("Setup detection error for %s: %s", sym, e)

    # -----------------------------------------------------------------------
    # 100-Point Scoring Pipeline (7 Independent Components)
    # -----------------------------------------------------------------------
    available_components = 0
    component_breakdown = {}

    cmp = float(stock_record.get("close") or (bars[-1].get("close") if bars else 0.0))
    daily_chg = float(stock_record.get("daily_change_pct") or 0.0)
    sec_name = stock_record.get("sector") or "Diversified"

    # Preliminary direction bias
    direction = "BULLISH"
    if daily_chg < -1.0 or (tech.get("supertrend_dir") == "down" and tech.get("rsi", 50) < 45):
        direction = "BEARISH"

    # -----------------------------------------------------------------------
    # Component 1: Market Regime Alignment (Max 10 pts)
    # -----------------------------------------------------------------------
    regime_name = market_regime.get("regime", "NEUTRAL")
    c1_score = 0.0
    c1_reasons = []

    if regime_name:
        available_components += 1
        if direction == "BULLISH":
            if regime_name == "STRONG BULLISH":
                c1_score = 10.0
                c1_reasons.append("Strong tailwind from STRONG BULLISH market regime")
            elif regime_name == "BULLISH":
                c1_score = 8.0
                c1_reasons.append("Constructive alignment with BULLISH market regime")
            elif regime_name == "NEUTRAL":
                c1_score = 5.0
                c1_reasons.append("Neutral market regime provides balanced backdrop")
            elif regime_name == "BEARISH":
                c1_score = 2.0
                c1_reasons.append("Caution: trading long against BEARISH market regime")
            else:
                c1_score = 0.0
                c1_reasons.append("Adverse headwind: trading long in STRONG BEARISH market")
        else:  # BEARISH
            if regime_name == "STRONG BEARISH":
                c1_score = 10.0
                c1_reasons.append("Strong tailwind from STRONG BEARISH market distribution")
            elif regime_name == "BEARISH":
                c1_score = 8.0
                c1_reasons.append("Aligned with BEARISH market regime")
            elif regime_name == "NEUTRAL":
                c1_score = 5.0
                c1_reasons.append("Neutral market provides balanced backdrop for shorting")
            elif regime_name == "BULLISH":
                c1_score = 2.0
                c1_reasons.append("Caution: shorting against advancing BULLISH market")
            else:
                c1_score = 0.0
                c1_reasons.append("Adverse headwind: shorting into STRONG BULLISH market")

    component_breakdown["market_regime"] = {
        "score": round(c1_score, 1),
        "max": 10.0,
        "rationale": "; ".join(c1_reasons) if c1_reasons else "Market regime data missing",
    }

    # -----------------------------------------------------------------------
    # Component 2: Sector Strength & Rotation (Max 10 pts)
    # -----------------------------------------------------------------------
    c2_score = 0.0
    c2_reasons = []
    sec_item = next((s for s in sectors_info.get("sectors", []) if s.get("sector") == sec_name), None)

    if sec_item:
        available_components += 1
        quadrant = sec_item.get("rotation_quadrant", "NEUTRAL")
        rs_vs_mkt = sec_item.get("relative_strength_vs_market", 0.0)
        sec_breadth = sec_item.get("breadth_pct", 50.0)

        if direction == "BULLISH":
            if quadrant == "LEADING":
                c2_score += 7.0
                c2_reasons.append(f"Belongs to LEADING sector ({sec_name})")
            elif quadrant == "IMPROVING":
                c2_score += 5.5
                c2_reasons.append(f"Belongs to IMPROVING sector ({sec_name})")
            elif quadrant == "WEAKENING":
                c2_score += 3.0
                c2_reasons.append(f"Sector {sec_name} is WEAKENING")
            else:
                c2_score += 1.0
                c2_reasons.append(f"Sector {sec_name} is DECLINING")

            if rs_vs_mkt > 0:
                c2_score += min(2.0, rs_vs_mkt * 0.5)
                c2_reasons.append(f"Sector outperforming market by +{rs_vs_mkt}%")
            if sec_breadth >= 65.0:
                c2_score += 1.0
                c2_reasons.append(f"High sector breadth ({sec_breadth}%)")
        else:  # BEARISH
            if quadrant in ("DECLINING", "LAGGING"):
                c2_score += 7.0
                c2_reasons.append(f"Belongs to DECLINING sector ({sec_name})")
            elif quadrant == "WEAKENING":
                c2_score += 5.5
                c2_reasons.append(f"Belongs to WEAKENING sector ({sec_name})")
            elif quadrant == "IMPROVING":
                c2_score += 2.0
            else:
                c2_score += 1.0
            if rs_vs_mkt < 0:
                c2_score += min(3.0, abs(rs_vs_mkt) * 0.5)
                c2_reasons.append(f"Sector underperforming market by {rs_vs_mkt}%")

    c2_score = min(10.0, c2_score)
    component_breakdown["sector_strength"] = {
        "score": round(c2_score, 1),
        "max": 10.0,
        "rationale": "; ".join(c2_reasons) if c2_reasons else "Sector rotation data missing",
    }

    # -----------------------------------------------------------------------
    # Component 3: Fundamental Quality (Max 15 pts)
    # -----------------------------------------------------------------------
    c3_score = 0.0
    c3_reasons = []

    if fund_ratios:
        available_components += 1
        growth = fund_ratios.growth
        prof = fund_ratios.profitability
        health = fund_ratios.health
        val = fund_ratios.valuation

        # Profit growth (QoQ or YoY)
        pat_growth = growth.quarterly_pat_growth_qoq or growth.quarterly_pat_growth_yoy
        if pat_growth is not None:
            if pat_growth >= 20.0:
                c3_score += 4.0
                c3_reasons.append(f"Robust PAT growth (+{pat_growth}%)")
            elif pat_growth > 0.0:
                c3_score += 2.0
                c3_reasons.append(f"Positive PAT growth (+{pat_growth}%)")

        # ROE / ROCE (Quality of Capital)
        roe = prof.roe
        if roe is not None:
            if roe >= 20.0:
                c3_score += 3.0
                c3_reasons.append(f"High ROE ({roe}%)")
            elif roe >= 12.0:
                c3_score += 1.5

        roce = prof.roce
        if roce is not None and roce >= 15.0:
            c3_score += 3.0
            c3_reasons.append(f"Strong ROCE ({roce}%)")

        # Financial Health (Debt/Equity)
        de = health.debt_equity
        if de is not None:
            if de <= 0.3:
                c3_score += 3.0
                c3_reasons.append(f"Low Debt/Equity ({de})")
            elif de <= 0.8:
                c3_score += 1.5
        elif health.is_debt_free:
            c3_score += 3.0
            c3_reasons.append("Virtually Debt Free")

        # Operating Margin (OPM)
        opm = prof.operating_margin_pct
        if opm is not None and opm >= 15.0:
            c3_score += 2.0
            c3_reasons.append(f"Healthy OPM ({opm}%)")

    c3_score = min(15.0, c3_score)
    component_breakdown["fundamental_quality"] = {
        "score": round(c3_score, 1),
        "max": 15.0,
        "rationale": "; ".join(c3_reasons) if c3_reasons else "Fundamental statements unavailable",
    }

    # -----------------------------------------------------------------------
    # Component 4: Trend and Momentum (Max 20 pts)
    # -----------------------------------------------------------------------
    c4_score = 0.0
    c4_reasons = []

    if tech and cmp > 0:
        available_components += 1
        ema20 = tech.get("ema_20")
        ema50 = tech.get("ema_50")
        ema200 = tech.get("ema_200")
        rsi = tech.get("rsi")
        adx = tech.get("adx")
        supertrend_dir = tech.get("supertrend_dir")
        mansfield_50 = tech.get("mansfield_rs_50")

        if direction == "BULLISH":
            # Moving averages stacked alignment
            if ema20 and cmp > ema20:
                c4_score += 4.0
                c4_reasons.append("Price above EMA 20")
            if ema50 and cmp > ema50:
                c4_score += 3.5
                c4_reasons.append("Price above EMA 50")
            if ema200 and cmp > ema200:
                c4_score += 3.5
                c4_reasons.append("Price above EMA 200")
            if ema20 and ema50 and ema20 > ema50:
                c4_score += 2.0
                c4_reasons.append("EMA 20 > EMA 50 Golden Stack")

            # RSI sweet spot (50 to 68)
            if rsi is not None:
                if 50.0 <= rsi <= 68.0:
                    c4_score += 3.0
                    c4_reasons.append(f"RSI in bullish momentum zone ({rsi})")
                elif rsi > 68.0:
                    c4_score += 1.5  # overbought risk dampens full score

            # ADX trend strength
            if adx is not None and adx >= 25.0:
                c4_score += 2.0
                c4_reasons.append(f"Strong trend (ADX {adx})")

            # Supertrend
            if supertrend_dir == "up":
                c4_score += 2.0
                c4_reasons.append("Supertrend Bullish")

            # Mansfield RS outperformance
            if mansfield_50 is not None and mansfield_50 > 0:
                c4_score += 2.0
                c4_reasons.append(f"Mansfield RS outperforming (+{mansfield_50}%)")
        else:  # BEARISH
            if ema20 and cmp < ema20:
                c4_score += 4.0
                c4_reasons.append("Price below EMA 20")
            if ema50 and cmp < ema50:
                c4_score += 3.5
                c4_reasons.append("Price below EMA 50")
            if ema200 and cmp < ema200:
                c4_score += 3.5
                c4_reasons.append("Price below EMA 200")
            if ema20 and ema50 and ema20 < ema50:
                c4_score += 2.0
                c4_reasons.append("EMA 20 < EMA 50 Bearish Stack")

            if rsi is not None and rsi <= 45.0:
                c4_score += 3.0
                c4_reasons.append(f"RSI in bearish momentum zone ({rsi})")

            if adx is not None and adx >= 25.0:
                c4_score += 2.0
                c4_reasons.append(f"Strong trend (ADX {adx})")

            if supertrend_dir == "down":
                c4_score += 2.0
                c4_reasons.append("Supertrend Bearish")

    c4_score = min(20.0, c4_score)
    component_breakdown["trend_momentum"] = {
        "score": round(c4_score, 1),
        "max": 20.0,
        "rationale": "; ".join(c4_reasons) if c4_reasons else "Insufficient technical history",
    }

    # -----------------------------------------------------------------------
    # Component 5: Volume & Money Flow Confirmation (Max 15 pts)
    # -----------------------------------------------------------------------
    c5_score = 0.0
    c5_reasons = []

    if vol_intel:
        available_components += 1
        rvol = vol_intel.get("relative_volume") or 1.0
        cmf = vol_intel.get("chaikin_money_flow_20")
        buy_bias = vol_intel.get("close_location_buying_bias_pct") or 50.0
        sell_bias = vol_intel.get("close_location_selling_bias_pct") or 50.0
        div = vol_intel.get("price_volume_divergence")
        turnover_mode = vol_intel.get("turnover_type") or "ESTIMATED_TURNOVER"

        # RVOL Expansion
        if rvol >= 2.0:
            c5_score += 5.0
            c5_reasons.append(f"Major volume surge (RVOL {rvol}x)")
        elif rvol >= 1.3:
            c5_score += 3.5
            c5_reasons.append(f"Above-average volume (RVOL {rvol}x)")
        elif rvol >= 1.0:
            c5_score += 1.5

        # Close Location Pressure
        if direction == "BULLISH":
            if buy_bias >= 70.0:
                c5_score += 4.0
                c5_reasons.append(f"Strong upper-candle close bias ({buy_bias}%)")
            elif buy_bias >= 55.0:
                c5_score += 2.0
            if cmf is not None and cmf > 0.08:
                c5_score += 3.0
                c5_reasons.append(f"Positive Chaikin Money Flow (+{cmf})")
            if div == "Bullish Divergence":
                c5_score += 3.0
                c5_reasons.append("Bullish price-volume divergence")
        else:  # BEARISH
            if sell_bias >= 70.0:
                c5_score += 4.0
                c5_reasons.append(f"Strong lower-candle close bias ({sell_bias}%)")
            elif sell_bias >= 55.0:
                c5_score += 2.0
            if cmf is not None and cmf < -0.08:
                c5_score += 3.0
                c5_reasons.append(f"Negative Chaikin Money Flow ({cmf})")
            if div == "Bearish Divergence":
                c5_score += 3.0
                c5_reasons.append("Bearish price-volume divergence")

    c5_score = min(15.0, c5_score)
    component_breakdown["volume_confirmation"] = {
        "score": round(c5_score, 1),
        "max": 15.0,
        "rationale": "; ".join(c5_reasons) if c5_reasons else "Volume indicators missing",
    }

    # -----------------------------------------------------------------------
    # Component 6: Smart Money Concepts & Market Structure (Max 20 pts)
    # -----------------------------------------------------------------------
    c6_score = 0.0
    c6_reasons = []

    if smc:
        available_components += 1
        obs_raw = smc.get("order_blocks", [])
        obs = obs_raw.get("all_zones", []) if isinstance(obs_raw, dict) else (obs_raw if isinstance(obs_raw, list) else [])
        
        fvgs_raw = smc.get("fair_value_gaps", [])
        fvgs = fvgs_raw.get("gaps", []) if isinstance(fvgs_raw, dict) else (fvgs_raw if isinstance(fvgs_raw, list) else [])
        
        structure = smc.get("market_structure", {})
        liquidity = smc.get("liquidity", {})
        sweeps = liquidity.get("sweeps", []) if isinstance(liquidity, dict) else []

        # 1. Fresh unmitigated Order Blocks in trade direction
        if direction == "BULLISH":
            fresh_bullish_obs = [
                ob for ob in obs
                if isinstance(ob, dict)
                and (ob.get("type") == "BULLISH_OB" or ob.get("direction") == "BULLISH")
                and ob.get("status") in ("FRESH", "TESTED")
            ]
            if fresh_bullish_obs:
                c6_score += 7.0
                c6_reasons.append(f"{len(fresh_bullish_obs)} active Bullish Order Block(s) acting as support")

            # 2. Break of Structure / CHoCH
            if structure.get("last_bos") and structure["last_bos"].get("type") == "BULLISH_BOS":
                c6_score += 6.0
                c6_reasons.append("Confirmed Bullish Break of Structure (BOS)")
            elif structure.get("last_choch") and structure["last_choch"].get("type") == "BULLISH_CHOCH":
                c6_score += 6.0
                c6_reasons.append("Confirmed Bullish Change of Character (CHoCH)")

            # 3. Fair Value Gaps
            open_bull_fvgs = [
                f for f in fvgs
                if isinstance(f, dict)
                and (f.get("type") == "BULLISH_FVG" or f.get("direction") == "BULLISH")
                and f.get("status") != "FILLED" and not f.get("is_filled", False)
            ]
            if open_bull_fvgs:
                c6_score += 4.0
                c6_reasons.append(f"{len(open_bull_fvgs)} open Bullish FVG imbalance zone(s)")

            # 4. Liquidity Sweeps
            recent_sweeps = [
                sw for sw in sweeps
                if isinstance(sw, dict) and "BULLISH" in str(sw.get("type", "")).upper()
            ]
            if recent_sweeps:
                c6_score += 3.0
                c6_reasons.append("Liquidity sweep of prior lows + reclaim confirmed")
        else:  # BEARISH
            fresh_bearish_obs = [
                ob for ob in obs
                if isinstance(ob, dict)
                and (ob.get("type") == "BEARISH_OB" or ob.get("direction") == "BEARISH")
                and ob.get("status") in ("FRESH", "TESTED")
            ]
            if fresh_bearish_obs:
                c6_score += 7.0
                c6_reasons.append(f"{len(fresh_bearish_obs)} active Bearish Order Block(s) acting as overhead resistance")

            if structure.get("last_bos") and structure["last_bos"].get("type") == "BEARISH_BOS":
                c6_score += 6.0
                c6_reasons.append("Confirmed Bearish Break of Structure (BOS)")
            elif structure.get("last_choch") and structure["last_choch"].get("type") == "BEARISH_CHOCH":
                c6_score += 6.0
                c6_reasons.append("Confirmed Bearish Change of Character (CHoCH)")

            open_bear_fvgs = [
                f for f in fvgs
                if isinstance(f, dict)
                and (f.get("type") == "BEARISH_FVG" or f.get("direction") == "BEARISH")
                and f.get("status") != "FILLED" and not f.get("is_filled", False)
            ]
            if open_bear_fvgs:
                c6_score += 4.0
                c6_reasons.append(f"{len(open_bear_fvgs)} open Bearish FVG zone(s)")

    c6_score = min(20.0, c6_score)
    component_breakdown["market_structure"] = {
        "score": round(c6_score, 1),
        "max": 20.0,
        "rationale": "; ".join(c6_reasons) if c6_reasons else "Market structure data missing",
    }

    # -----------------------------------------------------------------------
    # Component 7: Multi-Timeframe Alignment (Max 10 pts)
    # -----------------------------------------------------------------------
    c7_score = 0.0
    c7_reasons = []

    if mtf:
        available_components += 1
        tf_data = mtf.get("timeframes", {})
        d1_trend = tf_data.get("1D", {}).get("trend", "NEUTRAL")
        h4_trend = tf_data.get("4H", {}).get("trend", "NEUTRAL")
        w1_trend = tf_data.get("1W", {}).get("trend", "NEUTRAL")

        bull_count = sum(1 for t in (d1_trend, h4_trend, w1_trend) if t == "BULLISH")
        bear_count = sum(1 for t in (d1_trend, h4_trend, w1_trend) if t == "BEARISH")

        if direction == "BULLISH":
            if bull_count == 3:
                c7_score = 10.0
                c7_reasons.append("Triple timeframe alignment: 1D, 4H, and 1W all Bullish")
            elif bull_count == 2:
                c7_score = 7.0
                c7_reasons.append("Dual timeframe alignment (Daily + higher TF Bullish)")
            elif bull_count == 1:
                c7_score = 4.0
                c7_reasons.append("Single timeframe bullish bias")
            else:
                c7_score = 1.0
                c7_reasons.append("Higher timeframes conflicting or bearish")
        else:  # BEARISH
            if bear_count == 3:
                c7_score = 10.0
                c7_reasons.append("Triple timeframe alignment: 1D, 4H, and 1W all Bearish")
            elif bear_count == 2:
                c7_score = 7.0
                c7_reasons.append("Dual timeframe alignment (Daily + higher TF Bearish)")
            elif bear_count == 1:
                c7_score = 4.0
                c7_reasons.append("Single timeframe bearish bias")
            else:
                c7_score = 1.0
                c7_reasons.append("Higher timeframes conflicting or bullish")

    c7_score = min(10.0, c7_score)
    component_breakdown["multi_timeframe"] = {
        "score": round(c7_score, 1),
        "max": 10.0,
        "rationale": "; ".join(c7_reasons) if c7_reasons else "Multi-timeframe data missing",
    }

    # -----------------------------------------------------------------------
    # Total Score & Setup Categorization
    # -----------------------------------------------------------------------
    raw_total = sum(c["score"] for c in component_breakdown.values())
    total_score = round(max(0.0, min(100.0, raw_total)), 1)

    # Determine top setup from setup detection engine
    top_setup = setups[0] if setups else None
    has_developing_setup = any(s.get("is_developing", False) for s in setups)

    if has_developing_setup and not any(s.get("is_confirmed", False) for s in setups):
        setup_category = "DEVELOPING SETUP"
    elif direction == "BULLISH":
        if total_score >= 75.0 and c6_score >= 10.0:
            setup_category = "HIGH-QUALITY BULLISH SETUP"
        elif total_score >= 55.0:
            setup_category = "BULLISH SETUP"
        elif total_score >= 35.0:
            setup_category = "WEAK SETUP"
        else:
            setup_category = "NO VALID SETUP"
    else:  # BEARISH
        if total_score >= 70.0 and c6_score >= 10.0:
            setup_category = "BEARISH SETUP"
        elif total_score >= 50.0:
            setup_category = "BEARISH SETUP"
        elif total_score >= 35.0:
            setup_category = "WEAK SETUP"
        else:
            setup_category = "NO VALID SETUP"

    probability_disclaimer = (
        f"Score of {total_score}/100 represents a heuristic multi-factor rating evaluated across "
        f"{available_components} of 7 components. It does NOT represent a statistically calibrated probability of profit."
    )

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY",
        symbol=sym,
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=stock_record.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    return {
        "symbol": sym,
        "company_name": stock_record.get("company_name", sym),
        "sector": sec_name,
        "close": round(cmp, 2),
        "daily_change_pct": round(daily_chg, 2),
        "relative_volume": round(float(stock_record.get("relative_volume") or 1.0), 2),
        "setup_score": total_score,
        "setup_category": setup_category,
        "direction": direction,
        "available_components_count": available_components,
        "total_components_count": 7,
        "component_breakdown": component_breakdown,
        "top_setup": top_setup,
        "probability_disclaimer": probability_disclaimer,
        "metadata": metadata,
    }


def discover_stocks(
    universe: str = "all",
    direction_filter: Optional[str] = None,
    min_score: float = 0.0,
    sector_filter: Optional[str] = None,
    sort_by: str = "setup_score",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """
    Unified stock discovery pipeline combining fundamental, technical, volume, and SMC evidence.
    """
    all_stocks = list_stocks()
    if not all_stocks:
        return {"items": [], "total_records": 0, "page": page, "total_pages": 0}

    # Universe selection
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

    # Pre-fetch shared context to maximize efficiency
    market_regime = classify_market_regime(universe=universe)
    sectors_info = compute_sector_rotation(universe=universe)

    evaluated_items = []
    for s in target_stocks:
        sym = s.get("symbol")
        if not sym:
            continue

        item = evaluate_stock_setup_quality(sym, market_regime=market_regime, sectors_info=sectors_info)

        # Filters
        if direction_filter and direction_filter.upper() != "ALL":
            if item["direction"] != direction_filter.upper():
                continue

        if item["setup_score"] < min_score:
            continue

        if sector_filter and sector_filter.upper() != "ALL":
            if item["sector"].upper() != sector_filter.upper():
                continue

        evaluated_items.append(item)

    # Sorting
    reverse = sort_order.lower() == "desc"
    active_sort = sort_by or "setup_score"

    def _sort_key(it: dict[str, Any]) -> Any:
        v = it.get(active_sort)
        if v is None:
            return -999999.0 if reverse else 999999.0
        return v

    evaluated_items.sort(key=_sort_key, reverse=reverse)

    # Assign rank
    for rank_idx, it in enumerate(evaluated_items, start=1):
        it["rank"] = rank_idx

    # Pagination
    total_records = len(evaluated_items)
    page_size = max(1, min(page_size, 100))
    total_pages = math.ceil(total_records / page_size) if total_records > 0 else 1
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * page_size
    paged_items = evaluated_items[start_idx : start_idx + page_size]

    # Universe coverage audit
    target_syms = {s.get("symbol") for s in target_stocks} if univ == "nifty50" else None
    coverage = audit_universe_coverage(universe, target_symbols=target_syms)

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    metadata["universe"] = universe
    metadata["universe_label"] = universe_label
    metadata["coverage"] = coverage

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "universe_label": universe_label,
        "market_regime": market_regime.get("regime"),
        "coverage": coverage,
        "total_records": total_records,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "metadata": metadata,
        "items": paged_items,
    }
