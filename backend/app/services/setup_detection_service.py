"""
Rule-Based Setup Detection Engine.

Detects high-probability price action setups:
1. Order Block Retest (Bullish / Bearish)
2. Break of Structure (BOS) Breakout
3. Change of Character (CHoCH) Trend Reversal
4. Fair Value Gap (FVG) Retracement
5. Liquidity Sweep Reversal (PDH/PDL sweep + rejection)
6. High-Volume Breakout / Breakdown
7. Moving Average Pullback (EMA 20/50 test in trend)
8. Consolidation Box Breakout
9. Key Support / Resistance Level Rejection

Each setup includes concrete entry zones, invalidations, stops, 1:2 & 1:3 targets,
and calibrated confidence scores (zero inflated 99% scores).
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd

from app.services.indicators import calculate_all_indicators
from app.services.smc_service import analyze_smart_money_concepts
from app.services.trendline_level_service import analyze_trendlines_and_levels


def detect_all_setups(
    symbol: str,
    bars: list[dict[str, Any]],
    timeframe: str = "1D",
) -> list[dict[str, Any]]:
    """
    Scan a symbol's OHLCV series for all active, actionable trade setups.
    """
    if not bars or len(bars) < 25:
        return []

    # Calculate indicators, SMC components, and levels
    indicators = calculate_all_indicators(bars)
    smc = analyze_smart_money_concepts(symbol=symbol, bars=bars)
    levels_res = analyze_trendlines_and_levels(bars)

    close = indicators.get("close")
    if close is None:
        return []

    atr = indicators.get("atr_14") or (close * 0.015)
    rvol = indicators.get("relative_volume") or 1.0
    supertrend_dir = indicators.get("supertrend_dir")
    rsi = indicators.get("rsi") or 50.0
    ema_20 = indicators.get("ema_20")
    ema_50 = indicators.get("ema_50")

    setups: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    # 1. Order Block Retest Setup
    # -------------------------------------------------------------------------
    ob_dict = smc.get("order_blocks", {})
    obs = ob_dict.get("all_zones", []) if isinstance(ob_dict, dict) else []
    for ob in obs:
        if not isinstance(ob, dict):
            continue
        status = ob.get("status", "")
        if status in ("FRESH", "TESTED"):
            top = ob.get("zone_high", 0.0)
            bottom = ob.get("zone_low", 0.0)
            ob_dir = ob.get("direction", "")

            # Bullish OB Retest: Price currently within or slightly above top
            if ob_dir == "BULLISH" and (bottom * 0.995 <= close <= top * 1.025):
                is_inside = (bottom * 0.998 <= close <= top * 1.005)
                setup_status = "CONFIRMED" if is_inside else "DEVELOPING"
                is_actionable = bool(setup_status == "CONFIRMED")
                risk = max(atr, close - bottom + 0.1 * atr)
                sl = ob.get("invalidation_level", round(bottom - 0.2 * atr, 2))
                t1 = round(close + 2.0 * risk, 2)
                t2 = round(close + 3.0 * risk, 2)

                confluences = [f"Bullish Order Block ({status})"]
                score = 55.0 if setup_status == "CONFIRMED" else 45.0
                if rvol >= 1.2:
                    confluences.append(f"Elevated Volume (RVOL {rvol})")
                    score += 10.0
                if supertrend_dir == "up":
                    confluences.append("Supertrend Bullish")
                    score += 10.0
                if rsi >= 45.0:
                    confluences.append(f"RSI Constructive ({rsi})")
                    score += 5.0

                setups.append({
                    "id": f"setup_ob_bull_{symbol}_{ob.get('candle_index', 0)}",
                    "symbol": symbol,
                    "setup_type": "Order Block Retest",
                    "direction": "BULLISH",
                    "status": setup_status,
                    "is_actionable_entry": is_actionable,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(bottom, 2), "max": round(top, 2), "ideal_entry": round((top + bottom) / 2, 2)},
                    "stop_loss": sl,
                    "target_1": t1,
                    "target_2": t2,
                    "invalidation_level": sl,
                    "invalidation_condition": f"Close below Order Block low {sl:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": round(min(90.0, score), 1),
                    "confidence_score": round(min(90.0, score), 1),
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 55.0 if setup_status == "CONFIRMED" else 45.0,
                        "confluences": confluences,
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": confluences,
                    "summary": f"{'Confirmed' if is_actionable else 'Developing'}: Price testing {status} Bullish OB ({bottom:.2f} - {top:.2f}). Invalidation below {sl:.2f}.",
                })

            # Bearish OB Retest: Price currently within or slightly below bottom
            elif ob_dir == "BEARISH" and (bottom * 0.975 <= close <= top * 1.005):
                is_inside = (bottom * 0.995 <= close <= top * 1.002)
                setup_status = "CONFIRMED" if is_inside else "DEVELOPING"
                is_actionable = bool(setup_status == "CONFIRMED")
                risk = max(atr, top - close + 0.1 * atr)
                sl = ob.get("invalidation_level", round(top + 0.2 * atr, 2))
                t1 = round(close - 2.0 * risk, 2)
                t2 = round(close - 3.0 * risk, 2)

                confluences = [f"Bearish Order Block ({status})"]
                score = 55.0 if setup_status == "CONFIRMED" else 45.0
                if rvol >= 1.2:
                    confluences.append(f"Elevated Volume (RVOL {rvol})")
                    score += 10.0
                if supertrend_dir == "down":
                    confluences.append("Supertrend Bearish")
                    score += 10.0
                if rsi <= 55.0:
                    confluences.append(f"RSI Weakening ({rsi})")
                    score += 5.0

                setups.append({
                    "id": f"setup_ob_bear_{symbol}_{ob.get('candle_index', 0)}",
                    "symbol": symbol,
                    "setup_type": "Order Block Retest",
                    "direction": "BEARISH",
                    "status": setup_status,
                    "is_actionable_entry": is_actionable,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(bottom, 2), "max": round(top, 2), "ideal_entry": round((top + bottom) / 2, 2)},
                    "stop_loss": sl,
                    "target_1": t1,
                    "target_2": t2,
                    "invalidation_level": sl,
                    "invalidation_condition": f"Close above Order Block high {sl:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": round(min(90.0, score), 1),
                    "confidence_score": round(min(90.0, score), 1),
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 55.0 if setup_status == "CONFIRMED" else 45.0,
                        "confluences": confluences,
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": confluences,
                    "summary": f"{'Confirmed' if is_actionable else 'Developing'}: Price testing {status} Bearish OB ({bottom:.2f} - {top:.2f}). Invalidation above {sl:.2f}.",
                })

    # -------------------------------------------------------------------------
    # 2. Break of Structure (BOS) & CHoCH Reversal Setups
    # -------------------------------------------------------------------------
    ms = smc.get("market_structure", {})
    breaks = ms.get("breaks", []) if isinstance(ms, dict) else []
    recent_breaks = [b for b in breaks if b.get("bar_index", 0) >= len(bars) - 5]
    for b in recent_breaks:
        b_type = b.get("type", "BOS")
        b_dir = b.get("direction", "BULLISH")
        lvl = b.get("level", close)
        is_choch = (b_type == "CHoCH")

        if b_dir == "BULLISH" and close >= lvl:
            risk = max(atr, close - lvl + 0.5 * atr)
            sl = round(lvl - 0.75 * atr, 2)
            setup_name = "CHoCH Reversal" if is_choch else "BOS Breakout"
            is_actionable = bool(rvol >= 1.2 or supertrend_dir == "up")
            setup_status = "CONFIRMED" if is_actionable else "DEVELOPING"
            confluences = [f"Bullish {setup_name}"]
            score = 65.0 if setup_status == "CONFIRMED" else 50.0
            if rvol >= 1.5:
                confluences.append(f"Volume Expansion (RVOL {rvol})")
                score += 15.0
            if supertrend_dir == "up":
                confluences.append("Supertrend Bullish Alignment")
                score += 10.0

            calibrated_score = round(min(85.0, score), 1)
            ideal_entry = round(lvl + 0.2 * atr, 2)
            setups.append({
                "id": f"setup_{b_type.lower()}_bull_{symbol}_{b.get('bar_index')}",
                "symbol": symbol,
                "setup_type": setup_name,
                "direction": "BULLISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(lvl, 2), "max": round(close, 2), "ideal_entry": ideal_entry},
                "stop_loss": sl,
                "target_1": round(close + 2.0 * risk, 2),
                "target_2": round(close + 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Close below break origin / support {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 60.0 if setup_status == "CONFIRMED" else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} Bullish {setup_name} above {lvl:.2f}. Invalidation below {sl:.2f}.",
            })
        elif b_dir == "BEARISH" and close <= lvl:
            risk = max(atr, lvl - close + 0.5 * atr)
            sl = round(lvl + 0.75 * atr, 2)
            setup_name = "CHoCH Reversal" if is_choch else "BOS Breakdown"
            is_actionable = bool(rvol >= 1.2 or supertrend_dir == "down")
            setup_status = "CONFIRMED" if is_actionable else "DEVELOPING"
            confluences = [f"Bearish {setup_name}"]
            score = 60.0 if setup_status == "CONFIRMED" else 50.0
            if rvol >= 1.5:
                confluences.append(f"Volume Expansion (RVOL {rvol})")
                score += 15.0
            if supertrend_dir == "down":
                confluences.append("Supertrend Bearish Alignment")
                score += 10.0

            calibrated_score = round(min(85.0, score), 1)
            ideal_entry = round(lvl - 0.2 * atr, 2)
            setups.append({
                "id": f"setup_{b_type.lower()}_bear_{symbol}_{b.get('bar_index')}",
                "symbol": symbol,
                "setup_type": setup_name,
                "direction": "BEARISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(close, 2), "max": round(lvl, 2), "ideal_entry": ideal_entry},
                "stop_loss": sl,
                "target_1": round(close - 2.0 * risk, 2),
                "target_2": round(close - 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Close above breakdown resistance {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 60.0 if setup_status == "CONFIRMED" else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} Bearish {setup_name} below {lvl:.2f}. Invalidation above {sl:.2f}.",
            })

    # -------------------------------------------------------------------------
    # 3. Fair Value Gap (FVG) Retracement
    # -------------------------------------------------------------------------
    fvg_dict = smc.get("fair_value_gaps", {})
    fvgs = fvg_dict.get("gaps", []) if isinstance(fvg_dict, dict) else []
    for fvg in fvgs:
        if not fvg.get("is_filled", False):
            f_top = fvg.get("top", 0)
            f_bot = fvg.get("bottom", 0)
            f_type = fvg.get("type", "BULLISH")
            if f_type == "BULLISH" and (f_bot <= close <= f_top * 1.025):
                is_inside = (f_bot <= close <= f_top)
                setup_status = "CONFIRMED" if is_inside else "DEVELOPING"
                is_actionable = bool(setup_status == "CONFIRMED")
                risk = max(atr, close - f_bot + 0.2 * atr)
                sl = round(f_bot - 0.25 * atr, 2)
                fvg_score = 68.0 if is_inside else 52.0
                fvg_confluences = ["Unmitigated Bullish Imbalance", f"Status: {setup_status}"]
                if supertrend_dir == "up":
                    fvg_confluences.append("Trend Alignment")
                    fvg_score += 5.0
                calibrated_score = round(min(85.0, fvg_score), 1)
                ideal_entry = round((f_top + f_bot) / 2, 2)
                setups.append({
                    "id": f"setup_fvg_bull_{symbol}_{fvg.get('bar_index', 0)}",
                    "symbol": symbol,
                    "setup_type": "FVG Retracement",
                    "direction": "BULLISH",
                    "status": setup_status,
                    "is_actionable_entry": is_actionable,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(f_bot, 2), "max": round(f_top, 2), "ideal_entry": ideal_entry},
                    "stop_loss": sl,
                    "target_1": round(close + 2.0 * risk, 2),
                    "target_2": round(close + 3.0 * risk, 2),
                    "invalidation_level": sl,
                    "invalidation_condition": f"Close below FVG bottom {sl:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": calibrated_score,
                    "confidence_score": calibrated_score,
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 65.0 if is_inside else 50.0,
                        "confluences": fvg_confluences,
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": fvg_confluences,
                    "summary": f"{'Confirmed' if is_actionable else 'Developing'}: Price filling Bullish FVG ({f_bot:.2f} - {f_top:.2f}). Invalidation below {sl:.2f}.",
                })

    # -------------------------------------------------------------------------
    # 4. Liquidity Sweep Reversal Setup
    # -------------------------------------------------------------------------
    liq_dict = smc.get("liquidity", {})
    sweeps = liq_dict.get("sweeps", []) if isinstance(liq_dict, dict) else []
    recent_sweeps = [s for s in sweeps if s.get("bar_index", 0) >= len(bars) - 4]
    for sw in recent_sweeps:
        sdir = sw.get("direction", "")
        cleared = sw.get("level_price", close)
        is_reaction_conf = bool(sw.get("confirmation_index") is not None)
        setup_status = "CONFIRMED" if is_reaction_conf else "DEVELOPING"
        is_actionable = is_reaction_conf

        if "SELL-SIDE" in sdir:  # Swept lows and rebounded
            risk = max(atr, close - cleared + 0.5 * atr)
            sl = round(cleared - 0.3 * atr, 2)
            confluences = ["Sell-side Liquidity Cleaned", f"Reaction: {setup_status}"]
            sw_score = 75.0 if is_actionable else 55.0
            if rvol >= 1.2:
                confluences.append(f"Volume Surge (RVOL {rvol})")
                sw_score += 5.0
            calibrated_score = round(min(85.0, sw_score), 1)
            setups.append({
                "id": f"setup_sweep_bull_{symbol}_{sw.get('bar_index')}",
                "symbol": symbol,
                "setup_type": "Liquidity Sweep Reversal",
                "direction": "BULLISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(cleared, 2), "max": round(close, 2), "ideal_entry": round(close, 2)},
                "stop_loss": sl,
                "target_1": round(close + 2.0 * risk, 2),
                "target_2": round(close + 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Break and close below swept low {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 70.0 if is_actionable else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} sell-side sweep of {cleared:.2f}. Invalidation below {sl:.2f}.",
            })
        elif "BUY-SIDE" in sdir:  # Swept highs and rejected downward
            risk = max(atr, cleared - close + 0.5 * atr)
            sl = round(cleared + 0.3 * atr, 2)
            confluences = ["Buy-side Liquidity Cleaned", f"Reaction: {setup_status}"]
            sw_score = 75.0 if is_actionable else 55.0
            if rvol >= 1.2:
                confluences.append(f"Volume Surge (RVOL {rvol})")
                sw_score += 5.0
            calibrated_score = round(min(85.0, sw_score), 1)
            setups.append({
                "id": f"setup_sweep_bear_{symbol}_{sw.get('bar_index')}",
                "symbol": symbol,
                "setup_type": "Liquidity Sweep Reversal",
                "direction": "BEARISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(close, 2), "max": round(cleared, 2), "ideal_entry": round(close, 2)},
                "stop_loss": sl,
                "target_1": round(close - 2.0 * risk, 2),
                "target_2": round(close - 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Break and close above swept high {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 70.0 if is_actionable else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} buy-side sweep of {cleared:.2f}. Invalidation above {sl:.2f}.",
            })

    # -------------------------------------------------------------------------
    # 6. High-Volume Breakout / Breakdown
    # -------------------------------------------------------------------------
    if indicators.get("is_breakout"):
        b_type = indicators.get("breakout_type", "")
        if "Bullish" in b_type:
            res_lvl = indicators.get("consolidation_resistance", close)
            risk = max(atr, close - res_lvl + 0.3 * atr)
            sl = round(res_lvl - 0.5 * atr, 2)
            is_actionable = bool(rvol >= 1.4)
            setup_status = "CONFIRMED" if is_actionable else "DEVELOPING"
            confluences = [f"Breakout with RVOL {rvol}", "Consolidation Resistance Cleared"]
            hv_score = 75.0 if is_actionable else 55.0
            if rvol >= 2.0:
                confluences.append("Strong Volume Spike (RVOL >= 2.0)")
                hv_score += 5.0
            calibrated_score = round(min(85.0, hv_score), 1)
            setups.append({
                "id": f"setup_breakout_vol_bull_{symbol}",
                "symbol": symbol,
                "setup_type": "High-Volume Breakout",
                "direction": "BULLISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(res_lvl, 2), "max": round(close, 2), "ideal_entry": round(close, 2)},
                "stop_loss": sl,
                "target_1": round(close + 2.0 * risk, 2),
                "target_2": round(close + 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Close back below broken resistance {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 70.0 if is_actionable else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} breakout above resistance {res_lvl:.2f}. Invalidation below {sl:.2f}.",
            })
        elif "Bearish" in b_type:
            sup_lvl = indicators.get("consolidation_support", close)
            risk = max(atr, sup_lvl - close + 0.3 * atr)
            sl = round(sup_lvl + 0.5 * atr, 2)
            is_actionable = bool(rvol >= 1.4)
            setup_status = "CONFIRMED" if is_actionable else "DEVELOPING"
            confluences = [f"Breakdown with RVOL {rvol}", "Consolidation Support Broken"]
            hv_score = 75.0 if is_actionable else 55.0
            if rvol >= 2.0:
                confluences.append("Strong Volume Spike (RVOL >= 2.0)")
                hv_score += 5.0
            calibrated_score = round(min(85.0, hv_score), 1)
            setups.append({
                "id": f"setup_breakdown_vol_bear_{symbol}",
                "symbol": symbol,
                "setup_type": "High-Volume Breakdown",
                "direction": "BEARISH",
                "status": setup_status,
                "is_actionable_entry": is_actionable,
                "timeframe": timeframe,
                "entry_zone": {"min": round(close, 2), "max": round(sup_lvl, 2), "ideal_entry": round(close, 2)},
                "stop_loss": sl,
                "target_1": round(close - 2.0 * risk, 2),
                "target_2": round(close - 3.0 * risk, 2),
                "invalidation_level": sl,
                "invalidation_condition": f"Close back above broken support {sl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": calibrated_score,
                "confidence_score": calibrated_score,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 70.0 if is_actionable else 50.0,
                    "confluences": confluences,
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": confluences,
                "summary": f"{'Confirmed' if is_actionable else 'Developing'} breakdown below support {sup_lvl:.2f}. Invalidation above {sl:.2f}.",
            })

    # -------------------------------------------------------------------------
    # 7. EMA Pullback Setup (Trend Continuation)
    # -------------------------------------------------------------------------
    if ema_20 and ema_50:
        # Bullish EMA Pullback: Close near EMA 20 or EMA 50 in an uptrend
        if close > ema_50 and (abs(close - ema_20) <= 0.6 * atr or abs(close - ema_50) <= 0.6 * atr):
            if supertrend_dir == "up" and rsi >= 45.0:
                risk = max(atr, close - ema_50 + 0.2 * atr)
                sl = round(ema_50 - 0.4 * atr, 2)
                is_actionable = bool(abs(close - ema_20) <= 0.3 * atr or abs(close - ema_50) <= 0.3 * atr)
                setup_status = "CONFIRMED" if is_actionable else "DEVELOPING"
                confluences = ["Uptrend intact (Close > EMA 50)", "Testing EMA support zone", "Supertrend Bullish"]
                calibrated_score = 72.0 if is_actionable else 55.0
                setups.append({
                    "id": f"setup_ema_pullback_bull_{symbol}",
                    "symbol": symbol,
                    "setup_type": "EMA Pullback",
                    "direction": "BULLISH",
                    "status": setup_status,
                    "is_actionable_entry": is_actionable,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(ema_50, 2), "max": round(close, 2), "ideal_entry": round(close, 2)},
                    "stop_loss": sl,
                    "target_1": round(close + 2.0 * risk, 2),
                    "target_2": round(close + 3.0 * risk, 2),
                    "invalidation_level": sl,
                    "invalidation_condition": f"Trend loss: Close below EMA 50 {sl:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": calibrated_score,
                    "confidence_score": calibrated_score,
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 65.0 if is_actionable else 50.0,
                        "confluences": confluences,
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": confluences,
                    "summary": f"{'Confirmed' if is_actionable else 'Developing'} pullback testing dynamic EMA support ({ema_20:.2f} / {ema_50:.2f}). Invalidation below {sl:.2f}.",
                })

    # -------------------------------------------------------------------------
    # 8. Consolidation Box Breakout Setup
    # -------------------------------------------------------------------------
    cons_box = levels_res.get("consolidation_box")
    if cons_box and isinstance(cons_box, dict):
        c_sup = cons_box.get("support", 0.0)
        c_res = cons_box.get("resistance", 0.0)
        if c_sup > 0 and c_res > c_sup:
            # Bullish Box Breakout
            if close >= c_res:
                is_conf = bool(rvol >= 1.3 and close >= c_res + 0.05 * atr)
                status_box = "CONFIRMED" if is_conf else "DEVELOPING"
                sl_box = round(c_res - 0.5 * atr, 2)
                risk_box = max(atr, close - sl_box)
                setups.append({
                    "id": f"setup_box_break_bull_{symbol}",
                    "symbol": symbol,
                    "setup_type": "Consolidation Box Breakout",
                    "direction": "BULLISH",
                    "status": status_box,
                    "is_actionable_entry": is_conf,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(c_res, 2), "max": round(close, 2), "ideal_entry": round(c_res + 0.1 * atr, 2)},
                    "stop_loss": sl_box,
                    "target_1": round(close + 2.0 * risk_box, 2),
                    "target_2": round(close + 3.0 * risk_box, 2),
                    "invalidation_level": sl_box,
                    "invalidation_condition": f"Close back inside consolidation box below {sl_box:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": 78.0 if is_conf else 58.0,
                    "confidence_score": 78.0 if is_conf else 58.0,
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 60.0 if is_conf else 45.0,
                        "confluences": [f"Consolidation Box Breakout", f"RVOL {rvol}"],
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": [f"Consolidation Box {c_sup:.2f} - {c_res:.2f}", f"Status: {status_box}"],
                    "summary": f"{'Confirmed' if is_conf else 'Developing'} break of consolidation box ({c_sup:.2f} - {c_res:.2f}). Invalidation below {sl_box:.2f}.",
                })
            # Bearish Box Breakdown
            elif close <= c_sup:
                is_conf = bool(rvol >= 1.3 and close <= c_sup - 0.05 * atr)
                status_box = "CONFIRMED" if is_conf else "DEVELOPING"
                sl_box = round(c_sup + 0.5 * atr, 2)
                risk_box = max(atr, sl_box - close)
                setups.append({
                    "id": f"setup_box_break_bear_{symbol}",
                    "symbol": symbol,
                    "setup_type": "Consolidation Box Breakout",
                    "direction": "BEARISH",
                    "status": status_box,
                    "is_actionable_entry": is_conf,
                    "timeframe": timeframe,
                    "entry_zone": {"min": round(close, 2), "max": round(c_sup, 2), "ideal_entry": round(c_sup - 0.1 * atr, 2)},
                    "stop_loss": sl_box,
                    "target_1": round(close - 2.0 * risk_box, 2),
                    "target_2": round(close - 3.0 * risk_box, 2),
                    "invalidation_level": sl_box,
                    "invalidation_condition": f"Close back inside consolidation box above {sl_box:.2f}",
                    "risk_reward_ratio": 2.0,
                    "heuristic_technical_score": 78.0 if is_conf else 58.0,
                    "confidence_score": 78.0 if is_conf else 58.0,
                    "is_empirical_probability": False,
                    "score_breakdown": {
                        "base_score": 60.0 if is_conf else 45.0,
                        "confluences": [f"Consolidation Box Breakdown", f"RVOL {rvol}"],
                        "min_score": 0.0,
                        "max_score": 95.0,
                    },
                    "confluence_factors": [f"Consolidation Box {c_sup:.2f} - {c_res:.2f}", f"Status: {status_box}"],
                    "summary": f"{'Confirmed' if is_conf else 'Developing'} breakdown of consolidation box ({c_sup:.2f} - {c_res:.2f}). Invalidation above {sl_box:.2f}.",
                })

    # -------------------------------------------------------------------------
    # 9. Key Support / Resistance Level Rejection Setup
    # -------------------------------------------------------------------------
    k_levels = levels_res.get("key_levels", {})
    if k_levels and isinstance(k_levels, dict):
        pdl = k_levels.get("pdl")
        pdh = k_levels.get("pdh")
        last_open = bars[-1].get("open", close) if isinstance(bars[-1], dict) else close

        if pdl and abs(close - pdl) / close <= 0.015:
            is_bounce = bool(close >= pdl and close >= last_open)
            st_lvl = "CONFIRMED" if is_bounce else "DEVELOPING"
            sl_lvl = round(pdl - 0.4 * atr, 2)
            risk_lvl = max(atr, close - sl_lvl)
            setups.append({
                "id": f"setup_key_level_sup_{symbol}",
                "symbol": symbol,
                "setup_type": "Key Level Rejection",
                "direction": "BULLISH",
                "status": st_lvl,
                "is_actionable_entry": is_bounce,
                "timeframe": timeframe,
                "entry_zone": {"min": round(pdl, 2), "max": round(close, 2), "ideal_entry": round(pdl + 0.1 * atr, 2)},
                "stop_loss": sl_lvl,
                "target_1": round(close + 2.0 * risk_lvl, 2),
                "target_2": round(close + 3.0 * risk_lvl, 2),
                "invalidation_level": sl_lvl,
                "invalidation_condition": f"Break and close below PDL {sl_lvl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": 74.0 if is_bounce else 56.0,
                "confidence_score": 74.0 if is_bounce else 56.0,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 60.0 if is_bounce else 45.0,
                    "confluences": [f"PDL {pdl:.2f} Test", f"Bounce Confirmed: {is_bounce}"],
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": [f"Testing PDL {pdl:.2f}", f"Rejection Status: {st_lvl}"],
                "summary": f"{'Confirmed' if is_bounce else 'Developing'} Support Rejection at PDL ({pdl:.2f}). Invalidation below {sl_lvl:.2f}.",
            })
        elif pdh and abs(close - pdh) / close <= 0.015:
            is_reject = bool(close <= pdh and close <= last_open)
            st_lvl = "CONFIRMED" if is_reject else "DEVELOPING"
            sl_lvl = round(pdh + 0.4 * atr, 2)
            risk_lvl = max(atr, sl_lvl - close)
            setups.append({
                "id": f"setup_key_level_res_{symbol}",
                "symbol": symbol,
                "setup_type": "Key Level Rejection",
                "direction": "BEARISH",
                "status": st_lvl,
                "is_actionable_entry": is_reject,
                "timeframe": timeframe,
                "entry_zone": {"min": round(close, 2), "max": round(pdh, 2), "ideal_entry": round(pdh - 0.1 * atr, 2)},
                "stop_loss": sl_lvl,
                "target_1": round(close - 2.0 * risk_lvl, 2),
                "target_2": round(close - 3.0 * risk_lvl, 2),
                "invalidation_level": sl_lvl,
                "invalidation_condition": f"Break and close above PDH {sl_lvl:.2f}",
                "risk_reward_ratio": 2.0,
                "heuristic_technical_score": 74.0 if is_reject else 56.0,
                "confidence_score": 74.0 if is_reject else 56.0,
                "is_empirical_probability": False,
                "score_breakdown": {
                    "base_score": 60.0 if is_reject else 45.0,
                    "confluences": [f"PDH {pdh:.2f} Test", f"Rejection Confirmed: {is_reject}"],
                    "min_score": 0.0,
                    "max_score": 95.0,
                },
                "confluence_factors": [f"Testing PDH {pdh:.2f}", f"Rejection Status: {st_lvl}"],
                "summary": f"{'Confirmed' if is_reject else 'Developing'} Resistance Rejection at PDH ({pdh:.2f}). Invalidation above {sl_lvl:.2f}.",
            })

    # -------------------------------------------------------------------------
    # Deduplication & Bounding:
    # Deduplicate by (setup_type, direction, round(entry_ideal, 1)) keeping highest score
    # -------------------------------------------------------------------------
    deduped: dict[tuple[str, str, float], dict[str, Any]] = {}
    for s in setups:
        ideal_entry = s.get("entry_zone", {}).get("ideal_entry", 0.0)
        key = (s.get("setup_type", ""), s.get("direction", ""), round(float(ideal_entry), 1))
        current_score = s.get("heuristic_technical_score", 0.0)
        if key not in deduped or current_score > deduped[key].get("heuristic_technical_score", 0.0):
            deduped[key] = s

    final_setups = list(deduped.values())
    # Sort setups by heuristic_technical_score descending
    final_setups.sort(key=lambda s: s.get("heuristic_technical_score", 0.0), reverse=True)
    return final_setups
