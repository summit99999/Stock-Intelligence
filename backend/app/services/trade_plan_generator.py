"""
Trade Plan Generator (Phase 12 - Research Only).

Generates evidence-based, quantitative hypothetical trade plans:
- Direction: LONG or SHORT
- Entry Type: LIMIT (retest/pullback) or STOP (breakout confirmation)
- Entry Zone: [min_price, max_price] with ideal entry price
- Stop-Loss: Structural level (below swing low, order block low, or breakout bar)
- Invalidation Condition: Specific price and event that cancels the setup
- Target 1 (T1): Next major liquidity level or conservative R-multiple
- Target 2 (T2): Extended structural target or higher R-multiple
- Risk-Reward Ratios (T1 and T2)
- Suggested Position Sizing based on:
  * User-specified account capital (default: ₹1,00,000)
  * User-specified risk per trade % (default: 1.0%)
  * Absolute risk amount (₹)
  * Quantity = floor(risk_amount / stop_distance)
  * Capital allocated = quantity * ideal_entry
  * Portfolio heat = capital allocated / account capital
- Invalidation guardrail: If stop distance <= 0 or stop-loss is placed on the
  wrong side of entry, quantity is set to 0 with an explicit risk warning.
- Failure risk factors: Explicit structural and market vulnerabilities.
- Evidence list: Confluence factors with scoring weights.
- Mandatory research disclosure: Strictly for analysis, no orders placed.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Optional

from app.database import get_bars, get_stock
from app.services.data_quality_service import DataMode, build_standard_metadata
from app.services.smc_service import analyze_smart_money_concepts
from app.services.unified_research_engine import evaluate_stock_setup_quality

logger = logging.getLogger(__name__)


def generate_trade_plan(
    symbol: str,
    account_capital: float = 100000.0,
    risk_pct: float = 1.0,
    target_rr: float = 2.0,
    direction_override: Optional[str] = None,
) -> dict[str, Any]:
    """
    Generate a complete, quantitative trade plan for a given symbol.
    """
    sym = symbol.strip().upper()
    stock_record = get_stock(sym) or {}
    bars = get_bars(sym)

    if not stock_record and not bars:
        return {
            "symbol": sym,
            "status": "ERROR",
            "error": f"Symbol '{sym}' not found in database.",
        }

    cmp = float(stock_record.get("close") or (bars[-1].get("close") if bars else 0.0))
    if cmp <= 0.0:
        return {
            "symbol": sym,
            "status": "ERROR",
            "error": f"Invalid market price (₹{cmp}) for symbol '{sym}'.",
        }

    # 1. Setup Quality Evaluation
    eval_result = evaluate_stock_setup_quality(sym)
    setup_score = eval_result.get("setup_score", 50.0)
    setup_category = eval_result.get("setup_category", "DEVELOPING SETUP")
    inferred_direction = eval_result.get("direction", "BULLISH")
    direction = (direction_override or ("LONG" if inferred_direction == "BULLISH" else "SHORT")).upper()
    if direction not in ("LONG", "SHORT"):
        direction = "LONG" if inferred_direction == "BULLISH" else "SHORT"

    # 2. SMC & Structural Levels
    smc = {}
    if bars and len(bars) >= 10:
        try:
            smc = analyze_smart_money_concepts(sym, bars=bars)
        except Exception as e:
            logger.debug("SMC analysis error in trade plan generator for %s: %s", sym, e)

    obs_raw = smc.get("order_blocks", [])
    obs = obs_raw.get("all_zones", []) if isinstance(obs_raw, dict) else (obs_raw if isinstance(obs_raw, list) else [])

    fvgs_raw = smc.get("fair_value_gaps", [])
    fvgs = fvgs_raw.get("gaps", []) if isinstance(fvgs_raw, dict) else (fvgs_raw if isinstance(fvgs_raw, list) else [])

    structure = smc.get("market_structure", {})
    swings = structure.get("swings", []) if isinstance(structure, dict) else []
    swing_highs = [s for s in swings if isinstance(s, dict) and s.get("type") == "SWING_HIGH"]
    swing_lows = [s for s in swings if isinstance(s, dict) and s.get("type") == "SWING_LOW"]

    # Recent high / low from bars (last 20 bars)
    recent_bars = bars[-20:] if len(bars) >= 20 else bars
    recent_high = max((b["high"] for b in recent_bars), default=cmp * 1.05)
    recent_low = min((b["low"] for b in recent_bars), default=cmp * 0.95)

    # 3. Derive Entry Zone and Ideal Entry
    if direction == "LONG":
        # Look for fresh Bullish OB below or at CMP
        bullish_obs = [
            ob for ob in obs
            if isinstance(ob, dict)
            and (ob.get("type") == "BULLISH_OB" or ob.get("direction") == "BULLISH")
            and ob.get("zone_high", 0) <= cmp * 1.02
        ]
        if bullish_obs:
            nearest_ob = max(bullish_obs, key=lambda x: x.get("zone_high", 0))
            ideal_entry = round(min(cmp, nearest_ob.get("zone_high", cmp)), 2)
            entry_type = "LIMIT (Order Block pullback / retest)"
            zone_low = round(max(nearest_ob.get("zone_low", ideal_entry * 0.98), ideal_entry * 0.985), 2)
            zone_high = round(ideal_entry * 1.005, 2)
        else:
            ideal_entry = round(cmp, 2)
            entry_type = "LIMIT (pullback to value)" if cmp < recent_high else "STOP (breakout confirmation)"
            zone_low = round(cmp * 0.992, 2)
            zone_high = round(cmp * 1.008, 2)
    else:  # SHORT
        bearish_obs = [
            ob for ob in obs
            if isinstance(ob, dict)
            and (ob.get("type") == "BEARISH_OB" or ob.get("direction") == "BEARISH")
            and ob.get("zone_low", 999999) >= cmp * 0.98
        ]
        if bearish_obs:
            nearest_ob = min(bearish_obs, key=lambda x: x.get("zone_low", 999999))
            ideal_entry = round(max(cmp, nearest_ob.get("zone_low", cmp)), 2)
            entry_type = "LIMIT (Order Block pullback / retest)"
            zone_low = round(ideal_entry * 0.995, 2)
            zone_high = round(min(nearest_ob.get("zone_high", ideal_entry * 1.02), ideal_entry * 1.015), 2)
        else:
            ideal_entry = round(cmp, 2)
            entry_type = "LIMIT (pullback to resistance)" if cmp > recent_low else "STOP (breakdown confirmation)"
            zone_low = round(cmp * 0.992, 2)
            zone_high = round(cmp * 1.008, 2)

    # 4. Stop-Loss & Invalidation Level
    guardrail_warnings = []
    if direction == "LONG":
        # Find structural support: lowest of nearby swing low or bullish OB bottom
        candidate_stops = []
        for sl in swing_lows:
            p = float(sl.get("price", 0))
            if 0 < p < ideal_entry:
                candidate_stops.append(p)
        for ob in obs:
            if ob.get("type") == "BULLISH_OB":
                p = float(ob.get("zone_low", 0))
                if 0 < p < ideal_entry:
                    candidate_stops.append(p)

        if candidate_stops:
            best_stop = max(candidate_stops)  # Closest structural support below entry
            stop_loss = round(best_stop * 0.995, 2)  # 0.5% buffer below structure
            stop_reason = f"Structural support below recent swing low/OB (₹{best_stop:.2f}) minus 0.5% buffer"
        else:
            stop_loss = round(ideal_entry * 0.97, 2)  # Default 3% risk
            stop_reason = "Default 3.0% risk buffer below entry (no clear structural swing low identified)"

        # Invalidation condition
        invalidation_condition = (
            f"Daily candle close below ₹{stop_loss:.2f} or decisive breakdown below "
            f"key support level immediately invalidates the bullish thesis."
        )

        # Check guardrail: Stop must be strictly less than ideal entry
        if stop_loss >= ideal_entry:
            guardrail_warnings.append("Guardrail Triggered: Stop-loss is at or above ideal entry for LONG setup.")
            stop_distance = 0.0
        else:
            stop_distance = round(ideal_entry - stop_loss, 2)

    else:  # SHORT
        candidate_stops = []
        for sh in swing_highs:
            p = float(sh.get("price", 0))
            if p > ideal_entry:
                candidate_stops.append(p)
        for ob in obs:
            if ob.get("type") == "BEARISH_OB":
                p = float(ob.get("zone_high", 0))
                if p > ideal_entry:
                    candidate_stops.append(p)

        if candidate_stops:
            best_stop = min(candidate_stops)  # Closest structural resistance above entry
            stop_loss = round(best_stop * 1.005, 2)  # 0.5% buffer above structure
            stop_reason = f"Structural resistance above recent swing high/OB (₹{best_stop:.2f}) plus 0.5% buffer"
        else:
            stop_loss = round(ideal_entry * 1.03, 2)  # Default 3% risk
            stop_reason = "Default 3.0% risk buffer above entry (no clear structural swing high identified)"

        invalidation_condition = (
            f"Daily candle close above ₹{stop_loss:.2f} or decisive breakout above "
            f"overhead supply level immediately invalidates the bearish thesis."
        )

        if stop_loss <= ideal_entry:
            guardrail_warnings.append("Guardrail Triggered: Stop-loss is at or below ideal entry for SHORT setup.")
            stop_distance = 0.0
        else:
            stop_distance = round(stop_loss - ideal_entry, 2)

    # 5. Targets (T1 and T2) & Risk-Reward
    if direction == "LONG":
        t1_dist = max(stop_distance * 1.5, ideal_entry * 0.02)
        t2_dist = max(stop_distance * max(2.5, target_rr), ideal_entry * 0.04)
        target_1 = round(ideal_entry + t1_dist, 2)
        target_2 = round(ideal_entry + t2_dist, 2)
        t1_note = "Next key liquidity level / structural resistance (1.5R)"
        t2_note = f"Extended structural target / major liquidity pool ({max(2.5, target_rr):.1f}R)"
    else:  # SHORT
        t1_dist = max(stop_distance * 1.5, ideal_entry * 0.02)
        t2_dist = max(stop_distance * max(2.5, target_rr), ideal_entry * 0.04)
        target_1 = round(max(1.0, ideal_entry - t1_dist), 2)
        target_2 = round(max(1.0, ideal_entry - t2_dist), 2)
        t1_note = "Next key liquidity pool / prior demand level (1.5R)"
        t2_note = f"Extended structural swing low target ({max(2.5, target_rr):.1f}R)"

    if stop_distance > 0:
        rr_t1 = round(abs(target_1 - ideal_entry) / stop_distance, 2)
        rr_t2 = round(abs(target_2 - ideal_entry) / stop_distance, 2)
    else:
        rr_t1 = 0.0
        rr_t2 = 0.0

    # 6. Position Sizing
    safe_capital = max(1000.0, float(account_capital))
    safe_risk_pct = max(0.1, min(10.0, float(risk_pct)))
    risk_amount = round(safe_capital * (safe_risk_pct / 100.0), 2)

    if stop_distance > 0.05:
        shares = int(math.floor(risk_amount / stop_distance))
        shares = max(0, shares)
        capital_allocated = round(shares * ideal_entry, 2)
        portfolio_heat_pct = round((capital_allocated / safe_capital) * 100.0, 2)
    else:
        shares = 0
        capital_allocated = 0.0
        portfolio_heat_pct = 0.0
        guardrail_warnings.append("Insufficient stop distance to calculate safe position size. Quantity set to 0.")

    # 7. What Would Make This Trade Fail (Explicit Risk Factors)
    risk_factors = [
        f"Broader market regime transition away from {eval_result.get('direction', 'current')} posture.",
        "Slippage during opening gap-down/up across weekend or after market news.",
        "Liquidity vacuum or sudden volume dry-up before reaching Target 1.",
        "Sector rotation capital outflow towards alternative high-momentum sectors.",
    ]
    if eval_result.get("available_components_count", 0) < 5:
        risk_factors.append("Incomplete data coverage: fewer than 5 of 7 components available for this stock.")

    # 8. Evidence List Supporting the Trade
    evidence_list = []
    cb = eval_result.get("component_breakdown", {})
    for comp_name, comp_info in cb.items():
        score = comp_info.get("score", 0.0)
        max_s = comp_info.get("max", 0.0)
        rationale = comp_info.get("rationale", "")
        if score > 0:
            evidence_list.append({
                "component": comp_name.replace("_", " ").title(),
                "score": score,
                "max": max_s,
                "weight_pct": round((score / max_s) * 100.0 if max_s > 0 else 0.0, 1),
                "rationale": rationale,
            })

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY",
        symbol=sym,
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=stock_record.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    disclaimer = (
        "Hypothetical trade plan for research and analysis only. "
        "Not an order instruction. No orders will be placed."
    )

    return {
        "symbol": sym,
        "company_name": stock_record.get("company_name", sym),
        "sector": stock_record.get("sector", "Diversified"),
        "status": "READY",
        "direction": direction,
        "setup_score": setup_score,
        "setup_category": setup_category,
        "current_market_price": cmp,
        "entry_plan": {
            "entry_type": entry_type,
            "ideal_entry": ideal_entry,
            "entry_zone_min": zone_low,
            "entry_zone_max": zone_high,
        },
        "exit_plan": {
            "stop_loss": stop_loss,
            "stop_distance": stop_distance,
            "stop_reason": stop_reason,
            "invalidation_condition": invalidation_condition,
            "target_1": {
                "price": target_1,
                "risk_reward_ratio": rr_t1,
                "description": t1_note,
            },
            "target_2": {
                "price": target_2,
                "risk_reward_ratio": rr_t2,
                "description": t2_note,
            },
        },
        "position_sizing": {
            "account_capital": safe_capital,
            "risk_per_trade_pct": safe_risk_pct,
            "risk_amount_inr": risk_amount,
            "recommended_shares": shares,
            "capital_allocated_inr": capital_allocated,
            "portfolio_heat_pct": portfolio_heat_pct,
        },
        "guardrail_warnings": guardrail_warnings,
        "risk_factors": risk_factors,
        "evidence_list": evidence_list,
        "disclaimer": disclaimer,
        "metadata": metadata,
    }
