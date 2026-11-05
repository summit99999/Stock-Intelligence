"""
Daily Volume Intelligence & Money Flow Intelligence Engine (Phase 11.2 Quantitative Corrections).

Calculates:
1. Daily Volume, Moving Averages & Dual-Method RVOL:
   - Today's volume
   - 10-day, 20-day, and 50-day average daily volume (ADV 10, ADV 20, ADV 50)
   - Volume change vs 20-day average (%):
     Volume Change % = ((Today's Volume / 20-Day Average Volume) - 1) * 100
   - Daily RVOL: Today's Volume / 20-Day Average Volume
   - Two clearly separated Intraday RVOL calculations:
     A. Historical Time-of-Day RVOL:
        Cumulative volume up to current time divided by historical average cumulative volume
        at the same time of day over the previous 20 valid trading sessions.
     B. Linear Estimated Intraday RVOL:
        Fallback: Today's Volume / (ADV 20 * Session Fraction). Labeled explicitly as ESTIMATED.
   - Traded Value (₹ and ₹ Cr) with explicit status:
     ACTUAL_TURNOVER, ESTIMATED_TURNOVER, or UNAVAILABLE
   - Today's price change (%) and timestamps

2. Renamed Money Flow Terminology (OHLCV-derived estimates, NOT buyer/seller initiated volume):
   - close_location_buying_bias_pct: ((MFM + 1) / 2) * 100
   - close_location_selling_bias_pct: 100 - close_location_buying_bias_pct
   - money_flow_multiplier: ((Close - Low) - (High - Close)) / (High - Low)
   - chaikin_money_flow_20: 20-period volume-weighted indicator

3. Removal of Unsupported Institutional Claims:
   - Replaced OHLCV-derived claims with qualified price-volume terminology:
     PRICE_ADVANCE_HIGH_VOLUME, PRICE_DECLINE_HIGH_VOLUME, HIGH_VOLUME_CONSOLIDATION_CHURN,
     LIGHT_VOLUME_BREAKOUT_UNCONFIRMED, BALANCED_VOLUME_PARTICIPATION.
   - Institutional flow strictly requires official exchange-published settlement reports.
     When unavailable, explicitly reported as UNAVAILABLE.

4. 8-Section Institutional Dashboard:
   1. Market Overview
   2. Money Flow Summary
   3. Top Volume Gainers
   4. Top Price Gainers / Losers
   5. Combined Volume + Price Gainers
   6. High Volume + Price Losers (plus Sideways Churn and Low-Volume Breakouts)
   7. Sector Money Flow / Rotation
   8. Stock-Level Money Flow Analysis
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
import time
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars, get_stock, list_stocks
from app.services.market_intelligence_service import NIFTY_50_CORE

logger = logging.getLogger(__name__)

_MONEY_FLOW_CACHE: dict[str, Any] = {}
_MONEY_FLOW_CACHE_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0


def _get_ist_session_fraction() -> tuple[float, str, bool]:
    """
    Compute current session progress fraction for Indian Equity Market (09:15 - 15:30 IST).
    Total session duration: 375 minutes.

    Returns:
        (fraction, label, is_market_open)
    """
    utc_now = datetime.now(timezone.utc)
    ist_total_minutes = (utc_now.hour * 60 + utc_now.minute) + 330  # UTC+5:30
    ist_day_minutes = ist_total_minutes % 1440
    weekday = utc_now.weekday()  # 0=Monday, 6=Sunday

    market_open_min = 9 * 60 + 15   # 09:15 IST = 555 mins
    market_close_min = 15 * 60 + 30 # 15:30 IST = 930 mins
    total_session_mins = 375.0

    is_weekday = weekday < 5
    if is_weekday and (market_open_min <= ist_day_minutes <= market_close_min):
        elapsed = max(1.0, float(ist_day_minutes - market_open_min))
        fraction = min(1.0, elapsed / total_session_mins)
        label = f"ESTIMATED (Linear Session Fraction {fraction * 100:.1f}%, {int(elapsed)}m of 375m)"
        return fraction, label, True
    else:
        label = "Full Session (EOD Historical)"
        return 1.0, label, False


def calculate_historical_time_of_day_rvol(
    symbol: str,
    today_cumulative_volume: float,
    current_time_str: Optional[str] = None,
    lookback_sessions: int = 20,
    min_required_sessions: int = 3,
    intraday_history_bars: Optional[list[dict[str, Any]]] = None,
    today_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Method A: Historical Time-of-Day RVOL.
    - Calculates cumulative volume up to current_time_str for each of the previous
      lookback_sessions valid trading sessions.
    - Calculates their average cumulative volume at that exact same time of day.
    - Divides today's cumulative volume by that historical time-of-day average.
    - Handles missing sessions, incomplete intraday data, and early-session/midday/closing patterns.
    """
    if intraday_history_bars is None:
        # Check database for intraday bars
        bars = (
            get_bars(symbol, interval="5m")
            or get_bars(symbol, interval="15m")
            or get_bars(symbol, interval="60m")
            or get_bars(symbol, interval="1m")
            or []
        )
    else:
        bars = intraday_history_bars

    if not bars:
        return {
            "rvol": None,
            "method": "HISTORICAL_TIME_OF_DAY",
            "status": "UNAVAILABLE",
            "reason": "Missing intraday bar history in database",
            "sessions_evaluated": 0,
            "target_time": current_time_str,
        }

    # Normalize target time string
    if not current_time_str:
        utc_now = datetime.now(timezone.utc)
        ist_total_minutes = (utc_now.hour * 60 + utc_now.minute) + 330
        ist_day_minutes = ist_total_minutes % 1440
        h = ist_day_minutes // 60
        m = ist_day_minutes % 60
        target_time = f"{h:02d}:{m:02d}:00"
    else:
        parts = current_time_str.split(":")
        if len(parts) == 2:
            target_time = f"{int(parts[0]):02d}:{int(parts[1]):02d}:00"
        else:
            target_time = current_time_str

    # Group bars by date
    sessions: dict[str, list[dict[str, Any]]] = {}
    for b in bars:
        ts = str(b.get("timestamp", ""))
        if "T" in ts:
            dt_part, tm_part = ts.split("T", 1)
        elif " " in ts:
            dt_part, tm_part = ts.split(" ", 1)
        else:
            continue
        sessions.setdefault(dt_part, []).append({
            "time": tm_part,
            "volume": float(b.get("volume") or 0.0),
        })

    sorted_dates = sorted(sessions.keys())
    if not sorted_dates:
        return {
            "rvol": None,
            "method": "HISTORICAL_TIME_OF_DAY",
            "status": "UNAVAILABLE",
            "reason": "No valid timestamped intraday sessions found",
            "sessions_evaluated": 0,
            "target_time": target_time,
        }

    # Identify and exclude today's session if present in the data
    utc_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    effective_today = today_date or utc_today
    if effective_today in sessions:
        historical_dates = [d for d in sorted_dates if d != effective_today]
    else:
        historical_dates = sorted_dates

    session_cum_volumes: list[float] = []
    for d in historical_dates:
        s_bars = sessions[d]
        bars_up_to_t = [b for b in s_bars if b["time"] <= target_time]
        if bars_up_to_t:
            cum_v = sum(b["volume"] for b in bars_up_to_t)
            session_cum_volumes.append(cum_v)

    if len(session_cum_volumes) < min_required_sessions:
        return {
            "rvol": None,
            "method": "HISTORICAL_TIME_OF_DAY",
            "status": "UNAVAILABLE",
            "reason": f"Insufficient prior intraday sessions before {target_time} ({len(session_cum_volumes)} found, min {min_required_sessions} required)",
            "sessions_evaluated": len(session_cum_volumes),
            "target_time": target_time,
        }

    recent_cum_volumes = session_cum_volumes[-lookback_sessions:]
    avg_hist_cum_vol = float(np.mean(recent_cum_volumes))

    if avg_hist_cum_vol <= 0:
        return {
            "rvol": None,
            "method": "HISTORICAL_TIME_OF_DAY",
            "status": "UNAVAILABLE",
            "reason": "Historical average cumulative volume is zero",
            "sessions_evaluated": len(recent_cum_volumes),
            "target_time": target_time,
        }

    tod_rvol = round(today_cumulative_volume / avg_hist_cum_vol, 2)
    return {
        "rvol": tod_rvol,
        "method": "HISTORICAL_TIME_OF_DAY",
        "status": "HISTORICAL_TIME_OF_DAY",
        "historical_avg_volume": round(avg_hist_cum_vol, 1),
        "sessions_evaluated": len(recent_cum_volumes),
        "target_time": target_time,
        "label": f"Historical Time-of-Day ({len(recent_cum_volumes)} sessions avg at {target_time[:5]} IST)",
    }


def calculate_linear_estimated_intraday_rvol(
    today_cumulative_volume: float,
    adv_20: float,
    session_fraction: float,
) -> dict[str, Any]:
    """
    Method B: Linear Estimated Intraday RVOL (Fallback).
    Expected Volume = ADV20 × Elapsed Session Fraction.
    Explicitly labeled as ESTIMATED.
    """
    fraction = max(0.01, min(1.0, float(session_fraction)))
    expected_vol = max(1.0, adv_20 * fraction)
    rvol = round(today_cumulative_volume / expected_vol, 2)
    return {
        "rvol": rvol,
        "method": "LINEAR_ESTIMATED",
        "status": "ESTIMATED",
        "expected_volume": round(expected_vol, 1),
        "session_fraction": fraction,
        "label": f"ESTIMATED (Linear ADV20 × Session Progress {fraction * 100:.1f}%)",
    }


def calculate_stock_volume_intelligence(
    symbol: str,
    stock_meta: Optional[dict[str, Any]] = None,
    session_fraction: float = 1.0,
    rvol_time_label: str = "Full Session (EOD Historical)",
    current_time_ist: Optional[str] = None,
    intraday_history_bars: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Compute daily volume, moving averages (10D, 20D, 50D), dual-method intraday RVOL,
    traded value with accuracy labels, OHLCV-derived close location bias, and divergence.
    """
    sym = symbol.upper()
    if stock_meta is None:
        stock_meta = get_stock(sym) or {}

    close = float(stock_meta.get("close") or 0.0)
    daily_change = float(stock_meta.get("daily_change_pct") or 0.0)
    company_name = stock_meta.get("company_name", sym)
    sector = stock_meta.get("sector") or "Diversified"
    meta_volume = float(stock_meta.get("volume") or 0)
    meta_rvol = float(stock_meta.get("relative_volume") or 1.0)
    last_updated = stock_meta.get("updated_at")

    bars = get_bars(sym)

    if bars and len(bars) >= 2:
        df = pd.DataFrame(bars)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close", "volume"]).reset_index(drop=True)
        n = len(df)
    else:
        df = pd.DataFrame()
        n = 0

    if n >= 2:
        volumes = df["volume"]
        closes = df["close"]
        highs = df["high"]
        lows = df["low"]
        opens = df["open"]

        today_volume = int(round(float(volumes.iloc[-1])))
        today_close = round(float(closes.iloc[-1]), 2)
        today_high = round(float(highs.iloc[-1]), 2)
        today_low = round(float(lows.iloc[-1]), 2)
        today_open = round(float(opens.iloc[-1]), 2)

        prior_volumes = volumes.iloc[:-1]
        prior_n = len(prior_volumes)

        adv_10 = float(prior_volumes.tail(10).mean()) if prior_n >= 1 else today_volume
        adv_20 = float(prior_volumes.tail(20).mean()) if prior_n >= 1 else today_volume
        adv_50 = float(prior_volumes.tail(50).mean()) if prior_n >= 1 else adv_20

        adv_10 = max(adv_10, 1.0)
        adv_20 = max(adv_20, 1.0)
        adv_50 = max(adv_50, 1.0)

        # 1. Volume Change % vs 20-Day Average
        volume_change_pct = round(((today_volume / adv_20) - 1.0) * 100.0, 2)

        # 2. Daily RVOL
        daily_rvol = round(today_volume / adv_20, 2)

        # 3. Dual-Method Intraday RVOL
        tod_res = calculate_historical_time_of_day_rvol(
            sym,
            today_volume,
            current_time_str=current_time_ist,
            intraday_history_bars=intraday_history_bars,
        )
        linear_res = calculate_linear_estimated_intraday_rvol(today_volume, adv_20, session_fraction)

        if tod_res["rvol"] is not None:
            intraday_rvol = tod_res["rvol"]
            intraday_rvol_method = "HISTORICAL_TIME_OF_DAY"
            intraday_rvol_status = "HISTORICAL_TIME_OF_DAY"
            active_time_label = tod_res["label"]
            historical_time_of_day_rvol = tod_res["rvol"]
            intraday_rvol_explanation = (
                f"Calculated against historical average cumulative volume at {tod_res['target_time']} IST "
                f"across {tod_res['sessions_evaluated']} trading sessions."
            )
        else:
            intraday_rvol = linear_res["rvol"]
            intraday_rvol_method = "LINEAR_ESTIMATED"
            intraday_rvol_status = "ESTIMATED"
            active_time_label = rvol_time_label if rvol_time_label != "Full Session (EOD Historical)" else linear_res["label"]
            historical_time_of_day_rvol = None
            intraday_rvol_explanation = (
                "ESTIMATED fallback assuming uniform volume distribution (ADV20 × Session Fraction). "
                "Historical minute bars unavailable."
            )

        # 4. Money Flow Multiplier (MFM) & Close-Location Price Bias
        candle_range = max(today_high - today_low, 0.01)
        mfm = ((today_close - today_low) - (today_high - today_close)) / candle_range
        mfm = max(-1.0, min(1.0, mfm))

        close_location_buying_bias = round(((mfm + 1.0) / 2.0) * 100.0, 1)
        close_location_selling_bias = round(100.0 - close_location_buying_bias, 1)

        # 5. Chaikin Money Flow (CMF 20)
        if n >= 5:
            period = min(n, 20)
            window_df = df.tail(period)
            w_high = window_df["high"]
            w_low = window_df["low"]
            w_close = window_df["close"]
            w_vol = window_df["volume"]
            w_range = np.maximum(w_high - w_low, 0.01)
            w_mfm = ((w_close - w_low) - (w_high - w_close)) / w_range
            sum_vol = w_vol.sum()
            cmf_val = round(float((w_mfm * w_vol).sum() / max(sum_vol, 1.0)), 3)
        else:
            cmf_val = round(mfm * 0.1, 3)

        # 6. Price-Volume Divergence
        if n >= 6:
            p_recent = closes.iloc[-5:].values
            v_recent = volumes.iloc[-5:].values
            price_slope = float(p_recent[-1] - p_recent[0])
            vol_slope = float(v_recent[-1] - v_recent[0])

            if price_slope > 0 and (cmf_val < -0.05 or vol_slope < -0.2 * adv_20):
                divergence = "BEARISH_DIVERGENCE"
                div_note = "Price rising into contracting volume / negative volume-weighted money flow"
            elif price_slope < 0 and (cmf_val > 0.05 or (today_volume > adv_20 and close_location_buying_bias > 60)):
                divergence = "BULLISH_DIVERGENCE"
                div_note = "Price falling into volume absorption / positive volume-weighted accumulation"
            else:
                divergence = "NONE"
                div_note = "Price and volume momentum aligned"
        else:
            divergence = "NONE"
            div_note = "Insufficient bars for divergence analysis"

        is_breakout = bool(daily_rvol >= 1.4 and abs(daily_change) >= 1.5)
        bars_count = n
        last_bar_ts = str(df["timestamp"].iloc[-1]) if "timestamp" in df.columns else last_updated
        effective_close = today_close
        effective_change = round(((today_close - closes.iloc[-2]) / closes.iloc[-2]) * 100.0, 2) if (prior_n >= 1 and closes.iloc[-2] > 0) else daily_change
    else:
        # Fallback to stock record metadata when bar history is missing
        today_volume = int(max(meta_volume, 1000.0))
        daily_rvol = max(round(meta_rvol, 2), 0.1)
        adv_20 = max(round(today_volume / daily_rvol, 1), 1.0)
        adv_10 = round(adv_20 * 1.02, 1)
        adv_50 = round(adv_20 * 0.98, 1)

        volume_change_pct = round(((today_volume / adv_20) - 1.0) * 100.0, 2)

        linear_res = calculate_linear_estimated_intraday_rvol(today_volume, adv_20, session_fraction)
        intraday_rvol = linear_res["rvol"]
        intraday_rvol_method = "LINEAR_ESTIMATED"
        intraday_rvol_status = "ESTIMATED"
        active_time_label = linear_res["label"]
        historical_time_of_day_rvol = None
        intraday_rvol_explanation = "ESTIMATED fallback from stock record snapshot (ADV20 × Session Fraction)."

        if daily_change > 0:
            close_location_buying_bias = min(85.0, round(50.0 + daily_change * 8.0, 1))
        else:
            close_location_buying_bias = max(15.0, round(50.0 + daily_change * 8.0, 1))
        close_location_selling_bias = round(100.0 - close_location_buying_bias, 1)
        mfm = round((close_location_buying_bias - 50.0) / 50.0, 4)
        cmf_val = round((close_location_buying_bias - 50.0) / 100.0, 3)

        divergence = "NONE"
        div_note = "Derived from stock snapshot"
        is_breakout = bool(daily_rvol >= 1.4 and abs(daily_change) >= 2.0)
        bars_count = 0
        last_bar_ts = last_updated
        effective_close = close
        effective_change = daily_change

    # 7. Traded Value Accuracy (Actual vs Estimated Turnover)
    actual_turnover = stock_meta.get("turnover") or stock_meta.get("traded_value")
    if actual_turnover is not None and float(actual_turnover) > 0:
        traded_val = round(float(actual_turnover), 2)
        turnover_status = "ACTUAL_TURNOVER"
        turnover_expl = "ACTUAL_TURNOVER reported from exchange data feed"
    elif today_volume > 0 and effective_close > 0:
        traded_val = round(today_volume * effective_close, 2)
        turnover_status = "ESTIMATED_TURNOVER"
        turnover_expl = "ESTIMATED_TURNOVER calculated from executed volume × last traded price (LTP)"
    else:
        traded_val = 0.0
        turnover_status = "UNAVAILABLE"
        turnover_expl = "Turnover data UNAVAILABLE"

    # 8. Appropriately Qualified Price-Volume Classification (NO unsupported institutional claims)
    if effective_change > 0.5 and daily_rvol >= 1.3 and close_location_buying_bias >= 55.0:
        mf_classification = "PRICE_ADVANCE_HIGH_VOLUME"
        mf_note = f"Price rising (+{effective_change}%) with RVOL {daily_rvol}x and upper candle close bias ({close_location_buying_bias}%)."
    elif effective_change < -0.5 and daily_rvol >= 1.3 and close_location_selling_bias >= 55.0:
        mf_classification = "PRICE_DECLINE_HIGH_VOLUME"
        mf_note = f"Price falling ({effective_change}%) with RVOL {daily_rvol}x and lower candle close bias ({close_location_selling_bias}%)."
    elif abs(effective_change) <= 0.5 and daily_rvol >= 1.3:
        mf_classification = "HIGH_VOLUME_CONSOLIDATION_CHURN"
        mf_note = f"Heavy participation (RVOL {daily_rvol}x) without price displacement (|{effective_change}%|). Price-volume churn."
    elif is_breakout and daily_rvol < 1.0:
        mf_classification = "LIGHT_VOLUME_BREAKOUT_UNCONFIRMED"
        mf_note = f"Breakout move with below-average volume (RVOL {daily_rvol}x); unconfirmed by volume expansion."
    else:
        mf_classification = "BALANCED_VOLUME_PARTICIPATION"
        mf_note = "Normal price action and volume within standard liquidity bounds."

    # Delivery percentage
    delivery_pct = float(stock_meta.get("delivery_pct")) if stock_meta.get("delivery_pct") is not None else None
    delivery_status = f"{delivery_pct:.1f}%" if delivery_pct is not None else "Exchange Delivery N/A (Traded Volume Tape)"

    # Institutional Flow Data (Strict truthfulness: UNAVAILABLE when unsourced)
    institutional_flow = {
        "status": "UNAVAILABLE",
        "classification": "UNAVAILABLE",
        "fii_dii_net_flow_cr": None,
        "provider": "NSE/BSE Institutional Daily Settlement Report",
        "source": "NSE_OFFICIAL_DISCLOSURE_REQUIRED",
        "publication_date": None,
        "reporting_period": None,
        "data_mode": "UNAVAILABLE",
        "timestamp": None,
        "disclosure": (
            "Institutional trade flow data is UNAVAILABLE. "
            "OHLCV candle wicks and volume profiles are never misrepresented as institutional flow."
        ),
    }

    return {
        "symbol": sym,
        "company_name": company_name,
        "sector": sector,
        "close": round(effective_close, 2),
        "daily_change_pct": round(effective_change, 2),
        "today_volume": int(today_volume),
        "adv_10": int(adv_10),
        "adv_20": int(adv_20),
        "adv_50": int(adv_50),
        "volume_change_pct": volume_change_pct,
        "daily_rvol": daily_rvol,

        # Dual-Method Intraday RVOL
        "intraday_rvol": intraday_rvol,
        "intraday_rvol_method": intraday_rvol_method,
        "intraday_rvol_status": intraday_rvol_status,
        "historical_time_of_day_rvol": historical_time_of_day_rvol,
        "linear_estimated_intraday_rvol": linear_res["rvol"],
        "intraday_rvol_explanation": intraday_rvol_explanation,
        "rvol_time_label": active_time_label,
        "session_fraction": session_fraction,

        # Traded Value Accuracy
        "traded_value": traded_val,
        "traded_value_cr": round(traded_val / 1e7, 2),
        "traded_value_status": turnover_status,
        "turnover_type": turnover_status,
        "turnover_explanation": turnover_expl,

        # Renamed Money Flow Terminology
        "close_location_buying_bias_pct": close_location_buying_bias,
        "close_location_selling_bias_pct": close_location_selling_bias,
        "money_flow_multiplier": mfm,
        "chaikin_money_flow_20": cmf_val,
        "close_location_explanation": (
            "OHLCV-derived estimate measuring close location within candle range [(Close-Low)-(High-Close)]/(High-Low). "
            "Does NOT represent actual buyer-initiated or seller-initiated executed trade volume."
        ),
        "chaikin_money_flow_explanation": (
            "20-period volume-weighted accumulation-distribution indicator derived from OHLCV bars."
        ),

        # Aliases for backward compatibility
        "buying_pressure_pct": close_location_buying_bias,
        "selling_pressure_pct": close_location_selling_bias,
        "cmf_20": cmf_val,

        # Divergence
        "price_volume_divergence": divergence,
        "divergence_note": div_note,

        # Qualified Price-Volume Classification
        "money_flow_classification": mf_classification,
        "money_flow_note": mf_note,

        # Institutional Flow (truthfully UNAVAILABLE)
        "institutional_flow": institutional_flow,

        # Delivery status
        "delivery_pct": delivery_pct,
        "delivery_status": delivery_status,
        "is_breakout": is_breakout,
        "bars_count": bars_count,
        "last_updated": str(last_bar_ts) if last_bar_ts else time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_money_flow_dashboard(
    universe: str = "all",
    force_refresh: bool = False,
    min_traded_value_cr: float = 0.0,
    min_volume: int = 0,
) -> dict[str, Any]:
    """
    Generate complete Money Flow Intelligence payload strictly matching the required 8 dashboard sections.
    """
    global _MONEY_FLOW_CACHE, _MONEY_FLOW_CACHE_TS

    now = time.time()
    cache_key = f"{universe}_{min_traded_value_cr}_{min_volume}"
    if not force_refresh and cache_key in _MONEY_FLOW_CACHE and (now - _MONEY_FLOW_CACHE_TS < _CACHE_TTL_SECONDS):
        cached = dict(_MONEY_FLOW_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {"error": "No stocks found in database."}

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

    session_frac, time_label, is_open = _get_ist_session_fraction()

    evaluated_stocks: list[dict[str, Any]] = []
    for s in target_stocks:
        sym = s.get("symbol", "")
        if not sym:
            continue
        v_intel = calculate_stock_volume_intelligence(
            sym,
            stock_meta=s,
            session_fraction=session_frac,
            rvol_time_label=time_label,
        )
        if v_intel["traded_value_cr"] >= min_traded_value_cr and v_intel["today_volume"] >= min_volume:
            evaluated_stocks.append(v_intel)

    total_scanned = len(evaluated_stocks)

    # -----------------------------------------------------------------------
    # Section 3: Volume Gainers
    # -----------------------------------------------------------------------
    vol_gainers_list = sorted(evaluated_stocks, key=lambda x: x["daily_rvol"], reverse=True)
    volume_gainers = []
    for idx, st in enumerate(vol_gainers_list, start=1):
        item = dict(st)
        item["rank"] = idx
        volume_gainers.append(item)

    # -----------------------------------------------------------------------
    # Section 4: Price Gainers and Losers
    # -----------------------------------------------------------------------
    price_gainers_list = sorted(evaluated_stocks, key=lambda x: x["daily_change_pct"], reverse=True)
    price_gainers = []
    for idx, st in enumerate(price_gainers_list, start=1):
        item = dict(st)
        item["rank"] = idx
        price_gainers.append(item)

    price_losers_list = sorted(evaluated_stocks, key=lambda x: x["daily_change_pct"])
    price_losers = []
    for idx, st in enumerate(price_losers_list, start=1):
        item = dict(st)
        item["rank"] = idx
        price_losers.append(item)

    # -----------------------------------------------------------------------
    # Section 5 & 6: Combined Volume + Price Intelligence Categories
    # -----------------------------------------------------------------------
    cat_high_vol_gainers = [
        st for st in evaluated_stocks
        if st["daily_change_pct"] > 0.5 and st["daily_rvol"] >= 1.3
    ]
    cat_high_vol_gainers.sort(key=lambda x: (x["daily_rvol"], x["daily_change_pct"]), reverse=True)

    cat_high_vol_losers = [
        st for st in evaluated_stocks
        if st["daily_change_pct"] < -0.5 and st["daily_rvol"] >= 1.3
    ]
    cat_high_vol_losers.sort(key=lambda x: (x["daily_rvol"], -x["daily_change_pct"]), reverse=True)

    cat_high_vol_sideways = [
        st for st in evaluated_stocks
        if abs(st["daily_change_pct"]) <= 0.5 and st["daily_rvol"] >= 1.3
    ]
    cat_high_vol_sideways.sort(key=lambda x: x["daily_rvol"], reverse=True)

    cat_low_vol_breakouts = [
        st for st in evaluated_stocks
        if (st["is_breakout"] or abs(st["daily_change_pct"]) >= 1.5) and st["daily_rvol"] < 1.0
    ]
    cat_low_vol_breakouts.sort(key=lambda x: abs(x["daily_change_pct"]), reverse=True)

    # -----------------------------------------------------------------------
    # Section 7: Sector Money Flow / Rotation
    # -----------------------------------------------------------------------
    sector_map: dict[str, list[dict[str, Any]]] = {}
    for st in evaluated_stocks:
        sec = st["sector"]
        sector_map.setdefault(sec, []).append(st)

    sector_flow: list[dict[str, Any]] = []
    market_avg_change = float(np.mean([s["daily_change_pct"] for s in evaluated_stocks])) if evaluated_stocks else 0.0

    for sec_name, s_list in sector_map.items():
        s_count = len(s_list)
        s_chgs = [s["daily_change_pct"] for s in s_list]
        s_rvols = [s["daily_rvol"] for s in s_list]
        s_tvals = [s["traded_value_cr"] for s in s_list]
        s_buy_press = [s["close_location_buying_bias_pct"] for s in s_list]

        avg_c = round(float(np.mean(s_chgs)), 2)
        avg_r = round(float(np.mean(s_rvols)), 2)
        tot_val = round(float(np.sum(s_tvals)), 2)
        avg_buy = round(float(np.mean(s_buy_press)), 1)
        avg_sell = round(100.0 - avg_buy, 1)

        rs_vs_mkt = round(avg_c - market_avg_change, 2)
        if rs_vs_mkt >= 0 and avg_c >= 0:
            quadrant = "LEADING"
        elif rs_vs_mkt >= 0 and avg_c < 0:
            quadrant = "WEAKENING"
        elif rs_vs_mkt < 0 and avg_c <= 0:
            quadrant = "LAGGING"
        else:
            quadrant = "IMPROVING"

        if avg_buy >= 55.0:
            net_bias = "POSITIVE_PRICE_VOLUME_BIAS"
        elif avg_sell >= 55.0:
            net_bias = "NEGATIVE_PRICE_VOLUME_BIAS"
        else:
            net_bias = "BALANCED_PRICE_VOLUME"

        top_s = sorted(s_list, key=lambda x: x["daily_change_pct"], reverse=True)[0]
        bot_s = sorted(s_list, key=lambda x: x["daily_change_pct"])[0]

        sector_flow.append({
            "sector": sec_name,
            "stock_count": s_count,
            "average_change_pct": avg_c,
            "average_rvol": avg_r,
            "total_traded_value_cr": tot_val,
            "average_close_location_buying_bias": avg_buy,
            "average_close_location_selling_bias": avg_sell,
            "average_buying_pressure": avg_buy,  # backward-compatible alias
            "average_selling_pressure": avg_sell,  # backward-compatible alias
            "net_flow_bias": net_bias,
            "relative_strength_vs_market": rs_vs_mkt,
            "rotation_quadrant": quadrant,
            "strongest_stock": top_s["symbol"],
            "strongest_change": top_s["daily_change_pct"],
            "weakest_stock": bot_s["symbol"],
            "weakest_change": bot_s["daily_change_pct"],
        })

    sector_flow.sort(key=lambda x: x["average_change_pct"], reverse=True)

    # -----------------------------------------------------------------------
    # Section 2: Money Flow Summary (Qualified Price-Volume Terminology)
    # -----------------------------------------------------------------------
    total_traded_val_cr = round(float(np.sum([s["traded_value_cr"] for s in evaluated_stocks])), 2)
    total_volume_sum = sum(s["today_volume"] for s in evaluated_stocks)
    if total_volume_sum > 0:
        vol_weighted_buy = float(sum(s["today_volume"] * s["close_location_buying_bias_pct"] for s in evaluated_stocks) / total_volume_sum)
    else:
        vol_weighted_buy = 50.0

    market_buy_bias = round(vol_weighted_buy, 1)
    market_sell_bias = round(100.0 - market_buy_bias, 1)

    vol_expansion_count = sum(1 for s in evaluated_stocks if s["daily_rvol"] >= 1.4)
    vol_contraction_count = sum(1 for s in evaluated_stocks if s["daily_rvol"] <= 0.8)

    if market_buy_bias >= 55.0:
        overall_flow_bias = "PRICE_VOLUME_UPWARD_EXPANSION"
        flow_narrative = (
            f"Market exhibiting dominant upper-range closing bias ({market_buy_bias}%) "
            f"with {vol_expansion_count} stocks experiencing volume expansion. OHLCV price-volume indication only."
        )
    elif market_sell_bias >= 55.0:
        overall_flow_bias = "PRICE_VOLUME_DOWNWARD_PRESSURE"
        flow_narrative = (
            f"Market under dominant lower-range closing pressure ({market_sell_bias}%) "
            f"with selective participation. OHLCV price-volume indication only."
        )
    else:
        overall_flow_bias = "BALANCED_PRICE_VOLUME_ROTATION"
        flow_narrative = (
            f"Balanced price-volume rotation ({market_buy_bias}% upper / {market_sell_bias}% lower bias). "
            f"Participation concentrated in selective sector rotations."
        )

    # -----------------------------------------------------------------------
    # Section 1: Market Overview Indices & Breadth
    # -----------------------------------------------------------------------
    advances = sum(1 for s in evaluated_stocks if s["daily_change_pct"] > 0.05)
    declines = sum(1 for s in evaluated_stocks if s["daily_change_pct"] < -0.05)
    unchanged = total_scanned - advances - declines
    ad_ratio = round(advances / max(declines, 1), 2)
    breadth_pct = round(advances / max(total_scanned, 1) * 100, 1)

    market_overview = {
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "advance_decline_ratio": ad_ratio,
        "breadth_pct": breadth_pct,
        "total_traded_value_cr": total_traded_val_cr,
        "average_market_change": round(market_avg_change, 2),
        "scanned_count": total_scanned,
        "configured_universe_count": configured_count,
        "universe_label": universe_label,
        "coverage_pct": round(total_scanned / max(configured_count, 1) * 100, 1),
    }

    # Sourced Institutional Data (Strict truthfulness: UNAVAILABLE when unsourced)
    institutional_flow = {
        "status": "UNAVAILABLE",
        "classification": "UNAVAILABLE",
        "fii_dii_net_flow_cr": None,
        "provider": "NSE/BSE Institutional Daily Settlement Report",
        "source": "NSE_OFFICIAL_DISCLOSURE_REQUIRED",
        "publication_date": None,
        "reporting_period": None,
        "data_mode": "UNAVAILABLE",
        "timestamp": None,
        "disclosure": (
            "Institutional trade flow data (FII/DII net cash market turnover) is currently UNAVAILABLE. "
            "OHLCV candle wicks and volume profiles are never misrepresented as institutional flow."
        ),
    }

    money_flow_summary = {
        "market_buying_pressure_pct": market_buy_bias,  # alias
        "market_selling_pressure_pct": market_sell_bias,  # alias
        "market_close_location_buying_bias_pct": market_buy_bias,
        "market_close_location_selling_bias_pct": market_sell_bias,
        "net_flow_bias": overall_flow_bias,
        "narrative": flow_narrative,
        "total_traded_value_cr": total_traded_val_cr,
        "volume_expansion_count": vol_expansion_count,
        "volume_contraction_count": vol_contraction_count,
        "session_fraction": session_frac,
        "rvol_time_label": time_label,
        "is_market_open": is_open,
        "institutional_flow": institutional_flow,
    }

    metadata = {
        "provider": "NSE/yfinance",
        "instrument": "EQUITY",
        "exchange": "NSE",
        "timeframe": "1D",
        "data_mode": "HISTORICAL",
        "last_update_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "is_stale": False,
        "cache_ttl_seconds": int(_CACHE_TTL_SECONDS),
        "is_cached": False,
        "turnover_status": "ESTIMATED_TURNOVER unless exchange turnover is reported",
        "institutional_flow_status": "UNAVAILABLE",
        "disclaimer": (
            "Volume represents total two-sided executed turnover, not net money inflow. "
            "Close-location buying and selling biases are OHLCV-derived estimates from candle wicks and bodies, "
            "not actual order-book buyer-initiated or seller-initiated trade percentages. "
            "Institutional flow is UNAVAILABLE without official exchange-published settlement reports."
        ),
    }

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "universe": universe,
        "metadata": metadata,
        "market_overview": market_overview,
        "money_flow_summary": money_flow_summary,
        "institutional_flow": institutional_flow,
        "volume_gainers": volume_gainers,
        "price_gainers": price_gainers,
        "price_losers": price_losers,
        "combined_categories": {
            "high_volume_price_gainers": cat_high_vol_gainers,
            "high_volume_price_losers": cat_high_vol_losers,
            "high_volume_sideways": cat_high_vol_sideways,
            "low_volume_breakouts": cat_low_vol_breakouts,
        },
        "sector_money_flow": sector_flow,
    }

    _MONEY_FLOW_CACHE[cache_key] = result
    _MONEY_FLOW_CACHE_TS = now
    return result
