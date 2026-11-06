"""
Watchlists & Alert Rule Evaluation Engine (Phase 11).

Provides:
1. Multi-Watchlist Management:
   - Full enriched stock quotes for watchlists
   - Add, edit, remove symbols, create & delete watchlists
2. Automated Alert Evaluation Engine:
   - Evaluates active rules against latest technical & SMC metrics:
     * PRICE_ABOVE, PRICE_BELOW
     * RSI_ABOVE, RSI_BELOW
     * VOLUME_SPIKE
     * BREAKOUT_52W
     * EMA_CROSSOVER
     * OB_RETEST
     * FVG_RETEST
   - Records trigger history in SQLite database
   - Updates trigger counter and timestamps
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from app.database import (
    add_symbol_to_watchlist,
    create_custom_watchlist,
    delete_custom_watchlist,
    get_bars,
    get_custom_watchlist,
    get_market_alert,
    get_market_alert_history,
    get_stock,
    list_custom_watchlists,
    list_market_alerts,
    record_market_alert_trigger,
    remove_symbol_from_watchlist,
    update_custom_watchlist,
    update_market_alert,
)
from app.services.indicators import calculate_all_indicators
from app.services.smc_service import analyze_smart_money_concepts

logger = logging.getLogger(__name__)


def get_enriched_watchlist(watchlist_id: int, user_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    """
    Retrieve a watchlist by ID and enrich all symbols with current market data.
    """
    wl = get_custom_watchlist(watchlist_id, user_id=user_id)
    if not wl:
        return None

    try:
        symbols = json.loads(wl.get("symbols_json", "[]"))
    except Exception:
        symbols = []

    enriched_items = []
    for sym in symbols:
        stock = get_stock(sym)
        if stock:
            enriched_items.append({
                "symbol": sym,
                "name": stock.get("company_name", sym),
                "price": round(float(stock.get("close") or 0.0), 2),
                "change": round(float(stock.get("daily_change_pct") or 0.0), 2),
                "changePercent": round(float(stock.get("daily_change_pct") or 0.0), 2),
                "high52": round(float(stock.get("week_52_high") or 0.0), 2),
                "low52": round(float(stock.get("week_52_low") or 0.0), 2),
                "volume": f"{(float(stock.get('volume') or 0)/100000):.1f}L" if stock.get("volume") else "N/A",
                "sector": stock.get("sector") or "General",
                "rsi": round(float(stock.get("rsi") or 50.0), 1),
                "relative_volume": round(float(stock.get("relative_volume") or 1.0), 2),
                "pe": round(float(stock.get("pe")), 2) if stock.get("pe") else None,
                "source": "DATABASE",
            })
        else:
            enriched_items.append({
                "symbol": sym,
                "name": sym,
                "price": 0.0,
                "change": 0.0,
                "changePercent": 0.0,
                "high52": 0.0,
                "low52": 0.0,
                "volume": "0.0L",
                "sector": "General",
                "rsi": 50.0,
                "relative_volume": 1.0,
                "pe": None,
                "source": "UNKNOWN",
            })

    return {
        "id": wl["id"],
        "name": wl["name"],
        "description": wl.get("description", ""),
        "created_at": wl.get("created_at"),
        "updated_at": wl.get("updated_at"),
        "items": enriched_items,
        "count": len(enriched_items),
    }


def evaluate_active_alerts() -> list[dict[str, Any]]:
    """
    Evaluate all ACTIVE alert rules against current stock prices, technical indicators, and SMC levels.
    Records triggers in history and updates alert counters.
    """
    active_alerts = list_market_alerts(status="ACTIVE")
    triggered_events: list[dict[str, Any]] = []

    for alert in active_alerts:
        alert_id = alert["id"]
        sym = alert["symbol"]
        alert_type = alert["alert_type"].upper()
        target = float(alert["target_value"]) if alert.get("target_value") is not None else None

        stock = get_stock(sym)
        if not stock:
            continue

        close = float(stock.get("close") or 0.0)
        rsi = float(stock.get("rsi") or 50.0)
        rvol = float(stock.get("relative_volume") or 1.0)
        w52_h = float(stock.get("week_52_high") or close)
        ema_20 = float(stock.get("ema_20")) if stock.get("ema_20") else None

        condition_met = False
        condition_str = ""
        val_str = ""
        message = ""

        if alert_type == "PRICE_ABOVE" and target is not None:
            if close >= target:
                condition_met = True
                condition_str = f"PRICE_ABOVE (>= ₹{target:,.2f})"
                val_str = f"₹{close:,.2f}"
                message = f"{sym} reached ₹{close:,.2f}, crossing above ₹{target:,.2f} threshold."

        elif alert_type == "PRICE_BELOW" and target is not None:
            if close <= target:
                condition_met = True
                condition_str = f"PRICE_BELOW (<= ₹{target:,.2f})"
                val_str = f"₹{close:,.2f}"
                message = f"{sym} declined to ₹{close:,.2f}, breaking below ₹{target:,.2f} threshold."

        elif alert_type == "RSI_ABOVE" and target is not None:
            if rsi >= target:
                condition_met = True
                condition_str = f"RSI_ABOVE (>= {target})"
                val_str = f"RSI {rsi:.1f}"
                message = f"{sym} RSI rose to {rsi:.1f}, entering overbought/momentum territory."

        elif alert_type == "RSI_BELOW" and target is not None:
            if rsi <= target:
                condition_met = True
                condition_str = f"RSI_BELOW (<= {target})"
                val_str = f"RSI {rsi:.1f}"
                message = f"{sym} RSI fell to {rsi:.1f}, entering oversold territory."

        elif alert_type == "VOLUME_SPIKE" and target is not None:
            if rvol >= target:
                condition_met = True
                condition_str = f"VOLUME_SPIKE (>= {target}x)"
                val_str = f"RVOL {rvol:.2f}x"
                message = f"{sym} volume surge detected with {rvol:.2f}x 20-day average volume."

        elif alert_type == "BREAKOUT_52W":
            if w52_h > 0 and close >= (w52_h * 0.99):
                condition_met = True
                condition_str = f"BREAKOUT_52W (Near/At ₹{w52_h:,.2f})"
                val_str = f"₹{close:,.2f} (52W: ₹{w52_h:,.2f})"
                message = f"{sym} testing or breaking new 52-week high at ₹{close:,.2f}."

        elif alert_type == "EMA_CROSSOVER":
            if ema_20 and close >= ema_20:
                condition_met = True
                condition_str = f"EMA20_CROSSOVER (Above ₹{ema_20:,.2f})"
                val_str = f"₹{close:,.2f} vs EMA20 ₹{ema_20:,.2f}"
                message = f"{sym} closed above 20 EMA key dynamic baseline."

        elif alert_type in ("OB_RETEST", "FVG_RETEST"):
            bars = get_bars(sym)
            if bars and len(bars) >= 15:
                smc = analyze_smart_money_concepts(sym, bars)
                if alert_type == "OB_RETEST":
                    obs = smc.get("order_blocks", {}).get("all_zones", [])
                    retested = [ob for ob in obs if ob.get("status") in ("TESTED", "FRESH") and abs(close - ob.get("mid", close)) / close <= 0.02]
                    if retested:
                        condition_met = True
                        ob_type = retested[0].get("type", "Demand")
                        condition_str = f"OB_RETEST (2% Proximity to {ob_type} OB)"
                        val_str = f"₹{close:,.2f}"
                        message = f"{sym} retesting active institutional {ob_type} Order Block zone."
                else:
                    fvgs = smc.get("fair_value_gaps", {}).get("all_fvgs", [])
                    retested_fvg = [f for f in fvgs if f.get("status") == "UNFILLED" and abs(close - f.get("mid", close)) / close <= 0.025]
                    if retested_fvg:
                        condition_met = True
                        f_type = retested_fvg[0].get("type", "Bullish")
                        condition_str = f"FVG_RETEST (Inside {f_type} Imbalance)"
                        val_str = f"₹{close:,.2f}"
                        message = f"{sym} retracing into unfilled {f_type} Fair Value Gap."

        if condition_met:
            hist_id = record_market_alert_trigger(
                alert_id=alert_id,
                symbol=sym,
                alert_type=alert_type,
                condition=condition_str,
                triggered_value=val_str,
                message=message,
            )
            triggered_events.append({
                "id": str(hist_id),
                "alertId": f"alert-{alert_id}",
                "symbol": sym,
                "condition": condition_str,
                "triggeredValue": val_str,
                "message": message,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    return triggered_events
