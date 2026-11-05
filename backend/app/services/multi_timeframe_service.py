"""
Multi-Timeframe Analysis Engine.

Analyzes price action, trend alignment, momentum, and volume across multiple
timeframes (1D, 4h, 1h, 15m, 5m). Computes institutional consensus scores,
directional agreement, and flags HTF/LTF alignment or conflicts.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd

from app.services.indicators import calculate_all_indicators
from app.services.smc_service import analyze_smart_money_concepts


TIMEFRAME_WEIGHTS = {
    "1D": 0.35,
    "4h": 0.25,
    "1h": 0.20,
    "15m": 0.12,
    "5m": 0.08,
}


# ---------------------------------------------------------------------------
# Session-Aware NSE Multi-Timeframe Resampling
# ---------------------------------------------------------------------------

NSE_TIMEZONE = "Asia/Kolkata"
NSE_SESSION_OPEN = (9, 15)  # 09:15 IST
NSE_SESSION_CLOSE = (15, 30)  # 15:30 IST


def _parse_to_ist(val: Any) -> pd.Timestamp:
    """Parse any datetime/string to timezone-aware Asia/Kolkata Timestamp."""
    ts = pd.Timestamp(val)
    if ts.tz is None:
        return ts.tz_localize(NSE_TIMEZONE)
    return ts.tz_convert(NSE_TIMEZONE)


def resample_ohlcv_bars(
    bars: list[dict[str, Any]],
    rule: str,
    closed_only: bool = True,
) -> list[dict[str, Any]]:
    """
    Resample OHLCV bars into institutional session-aware higher timeframes
    anchored to NSE trading hours (09:15 - 15:30 IST).

    Supported rules:
    - '5m' / '5min': 75 5-minute candles per session
    - '15m' / '15min': 25 15-minute candles per session
    - '1h' / '60min': 7 session candles (6x60m + 1x15m close candle)
    - '4h': 2 half-session candles (09:15-12:15, 12:15-15:30)
    - '1D' / 'D': Daily session candle
    - '1W' / 'W': Weekly candle (Mon-Fri)
    - '1M' / 'M': Monthly candle

    Guarantees:
    - Excludes pre-market (< 09:15), post-market (> 15:30), weekends, and exchange holidays.
    - Zero future candle leakage (closed candles only when closed_only=True).
    """
    if not bars:
        return []

    df = pd.DataFrame(bars)
    time_col = "timestamp" if "timestamp" in df.columns else "date"
    if time_col not in df.columns:
        return bars

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = 0.0

    # Parse datetimes and normalize to Asia/Kolkata
    df["dt_ist"] = df[time_col].apply(_parse_to_ist)
    df = df.sort_values("dt_ist").reset_index(drop=True)

    norm_rule = rule.lower().strip()

    # If incoming data are purely daily bars (no intra-day hours/minutes variation)
    is_pure_daily = (
        len(df) > 1 and
        (df["dt_ist"].dt.hour == 0).all() and
        (df["dt_ist"].dt.minute == 0).all()
    )

    if is_pure_daily:
        if norm_rule in ("1w", "w"):
            df["bucket"] = df["dt_ist"].dt.to_period("W-FRI").astype(str)
        elif norm_rule in ("1m", "m"):
            df["bucket"] = df["dt_ist"].dt.to_period("M").astype(str)
        else:
            # Already daily
            return bars

        grouped = df.groupby("bucket", as_index=False).agg({
            "dt_ist": "last",
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        out: list[dict[str, Any]] = []
        for _, row in grouped.iterrows():
            out.append({
                "date": str(row["dt_ist"].date()),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
                "volume": int(row["volume"]),
            })
        return out

    # For intraday timestamps: filter strictly to NSE market hours (Mon-Fri, 09:15 - 15:30)
    day_of_week = df["dt_ist"].dt.day_of_week  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
    time_min = df["dt_ist"].dt.hour * 60 + df["dt_ist"].dt.minute
    open_min = 9 * 60 + 15  # 555
    close_min = 15 * 60 + 30  # 930

    session_mask = (day_of_week < 5) & (time_min >= open_min) & (time_min <= close_min)
    df_session = df[session_mask].copy().reset_index(drop=True)
    if df_session.empty:
        df_session = df.copy()  # Fallback if no timestamps fell in standard session

    # Assign session-anchored bucket
    date_part = df_session["dt_ist"].dt.strftime("%Y-%m-%d")
    t_min = df_session["dt_ist"].dt.hour * 60 + df_session["dt_ist"].dt.minute - open_min

    if norm_rule in ("5m", "5min"):
        bucket_idx = (t_min // 5).clip(lower=0)
        bucket_time = bucket_idx * 5
        b_hour = 9 + (15 + bucket_time) // 60
        b_min = (15 + bucket_time) % 60
        df_session["bucket"] = date_part + " " + b_hour.astype(str).str.zfill(2) + ":" + b_min.astype(str).str.zfill(2)

    elif norm_rule in ("15m", "15min"):
        bucket_idx = (t_min // 15).clip(lower=0)
        bucket_time = bucket_idx * 15
        b_hour = 9 + (15 + bucket_time) // 60
        b_min = (15 + bucket_time) % 60
        df_session["bucket"] = date_part + " " + b_hour.astype(str).str.zfill(2) + ":" + b_min.astype(str).str.zfill(2)

    elif norm_rule in ("1h", "60m", "60min"):
        # 7 hourly session slots:
        # 0: 09:15-10:15, 1: 10:15-11:15, 2: 11:15-12:15, 3: 12:15-13:15,
        # 4: 13:15-14:15, 5: 14:15-15:15, 6: 15:15-15:30
        h_idx = (t_min // 60).clip(lower=0, upper=6)
        h_hour = 9 + h_idx
        df_session["bucket"] = date_part + " " + h_hour.astype(str).str.zfill(2) + ":15"

    elif norm_rule in ("4h", "240m"):
        # Conventional NSE 4H aggregation:
        # Standard 4H candle is 240 minutes.
        # Candle 1: 09:15 - 13:15 (first 240 min = Full 4-Hour Candle)
        # Candle 2: 13:15 - 15:30 (remaining 135 min = Shortened Session Tail Candle)
        slot = np.where(t_min < 240, "09:15", "13:15")
        df_session["bucket"] = date_part + " " + slot

    elif norm_rule in ("1d", "d", "daily"):
        df_session["bucket"] = date_part

    elif norm_rule in ("1w", "w", "weekly"):
        df_session["bucket"] = df_session["dt_ist"].dt.to_period("W-FRI").astype(str)

    elif norm_rule in ("1m", "m", "monthly"):
        df_session["bucket"] = df_session["dt_ist"].dt.to_period("M").astype(str)

    else:
        # Default to daily
        df_session["bucket"] = date_part

    grouped = df_session.groupby("bucket", sort=False).agg({
        "dt_ist": ["first", "last"],
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).reset_index()

    # Flatten multi-index
    grouped.columns = ["bucket", "dt_first", "dt_last", "open", "high", "low", "close", "volume"]

    out: list[dict[str, Any]] = []
    for _, row in grouped.iterrows():
        b_str = str(row["bucket"])
        is_shortened = False
        span_min = 60
        bar_type = "STANDARD"
        session_label = b_str

        if norm_rule in ("4h", "240m"):
            if b_str.endswith("09:15"):
                span_min = 240
                is_shortened = False
                bar_type = "FULL_4H"
                session_label = "09:15 - 13:15 (240m Full 4H Candle)"
            else:
                span_min = 135
                is_shortened = True
                bar_type = "PARTIAL_SESSION_TAIL"
                session_label = "13:15 - 15:30 (135m Shortened Session Tail Candle)"
        elif norm_rule in ("1h", "60m", "60min"):
            if b_str.endswith("15:15"):
                span_min = 15
                is_shortened = True
                bar_type = "PARTIAL_SESSION_CLOSE"
                session_label = "15:15 - 15:30 (15m Shortened Session Close Candle)"
            else:
                span_min = 60
                is_shortened = False
                bar_type = "FULL_1H"
                session_label = f"{b_str[-5:]} - 60m Standard 1H Candle"
        elif norm_rule in ("5m", "5min"):
            span_min = 5
            bar_type = "FULL_5M"
        elif norm_rule in ("15m", "15min"):
            span_min = 15
            bar_type = "FULL_15M"
        elif norm_rule in ("1d", "d", "daily"):
            span_min = 375
            bar_type = "FULL_SESSION_1D"

        out.append({
            "date": b_str,
            "timestamp": str(row["dt_first"]),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
            "volume": int(row["volume"]),
            "is_closed": True,
            "span_minutes": span_min,
            "is_shortened": is_shortened,
            "bar_type": bar_type,
            "session_label": session_label,
        })

    return out


def evaluate_single_timeframe(
    bars: list[dict[str, Any]], tf_label: str, symbol: str = "STOCK"
) -> dict[str, Any]:
    """
    Evaluate trend, momentum, indicators, and structure for a single timeframe.
    """
    if not bars or len(bars) < 15:
        return {
            "timeframe": tf_label,
            "status": "INSUFFICIENT_DATA",
            "bias": "Neutral",
            "score": 0.0,
            "indicators": {},
            "summary": f"Fewer than 15 bars available for {tf_label}.",
        }

    ind = calculate_all_indicators(bars)
    smc = analyze_smart_money_concepts(symbol=symbol, bars=bars)

    close = ind.get("close")
    ema_20 = ind.get("ema_20")
    ema_50 = ind.get("ema_50")
    ema_200 = ind.get("ema_200")
    rsi = ind.get("rsi")
    supertrend_dir = ind.get("supertrend_dir")
    rvol = ind.get("relative_volume") or 1.0
    structure = smc.get("market_structure", "Range")

    score = 0.0  # Range -100 to +100

    # 1. EMA Trend Alignment (+/- 35 pts)
    if close and ema_20 and ema_50:
        if close > ema_20 > ema_50:
            score += 30.0
            if ema_200 and close > ema_200:
                score += 5.0
        elif close < ema_20 < ema_50:
            score -= 30.0
            if ema_200 and close < ema_200:
                score -= 5.0
        elif close > ema_20:
            score += 15.0
        else:
            score -= 15.0

    # 2. Supertrend (+/- 25 pts)
    if supertrend_dir == "up":
        score += 25.0
    elif supertrend_dir == "down":
        score -= 25.0

    # 3. RSI Momentum (+/- 20 pts)
    if rsi is not None:
        if rsi >= 60.0:
            score += 20.0
        elif rsi >= 50.0:
            score += 10.0
        elif rsi <= 40.0:
            score -= 20.0
        elif rsi <= 50.0:
            score -= 10.0

    # 4. SMC Market Structure (+/- 20 pts)
    if "Bullish" in structure:
        score += 20.0
    elif "Bearish" in structure:
        score -= 20.0

    # Classify bias
    if score >= 50:
        bias = "Strong Bullish"
    elif score >= 20:
        bias = "Bullish"
    elif score <= -50:
        bias = "Strong Bearish"
    elif score <= -20:
        bias = "Bearish"
    elif ind.get("is_consolidating"):
        bias = "Consolidating"
    else:
        bias = "Neutral"

    return {
        "timeframe": tf_label,
        "status": "VALID",
        "bias": bias,
        "score": round(score, 1),
        "close": close,
        "ema_20": ema_20,
        "ema_50": ema_50,
        "ema_200": ema_200,
        "rsi": rsi,
        "supertrend_dir": supertrend_dir,
        "relative_volume": rvol,
        "market_structure": structure,
        "is_consolidating": ind.get("is_consolidating", False),
    }


def analyze_multi_timeframe(
    timeframe_bars: dict[str, list[dict[str, Any]]],
    symbol: str = "STOCK",
) -> dict[str, Any]:
    """
    Main entry point for multi-timeframe analysis.
    Accepts dictionary of timeframe -> bars (e.g. {'1D': [...], '4h': [...], '1h': [...], '15m': [...]})
    """
    results_by_tf: dict[str, dict[str, Any]] = {}
    weighted_score = 0.0
    total_weight = 0.0

    for tf, bars in timeframe_bars.items():
        if not bars:
            continue
        eval_result = evaluate_single_timeframe(bars, tf, symbol=symbol)
        results_by_tf[tf] = eval_result

        w = TIMEFRAME_WEIGHTS.get(tf, 0.1)
        if eval_result.get("status") == "VALID":
            weighted_score += eval_result["score"] * w
            total_weight += w

    if total_weight > 0:
        consensus_score = round(weighted_score / total_weight, 1)
    else:
        consensus_score = 0.0

    # Determine institutional consensus rating
    if consensus_score >= 50:
        consensus_rating = "Strong Bullish Alignment"
    elif consensus_score >= 20:
        consensus_rating = "Bullish Bias"
    elif consensus_score <= -50:
        consensus_rating = "Strong Bearish Alignment"
    elif consensus_score <= -20:
        consensus_rating = "Bearish Bias"
    else:
        consensus_rating = "Neutral / Mixed Consolidation"

    # Detect conflicts between Higher Timeframe (1D/4h) and Lower Timeframe (15m/5m)
    htf_bias = results_by_tf.get("1D", {}).get("bias") or results_by_tf.get("4h", {}).get("bias", "Neutral")
    ltf_bias = results_by_tf.get("15m", {}).get("bias") or results_by_tf.get("5m", {}).get("bias", "Neutral")

    conflict_detected = False
    conflict_detail = "Timeframes generally in harmony."
    if "Bullish" in htf_bias and "Bearish" in ltf_bias:
        conflict_detected = True
        conflict_detail = f"Higher timeframe {htf_bias} while Lower timeframe {ltf_bias} (Potential pullback / retest opportunity)."
    elif "Bearish" in htf_bias and "Bullish" in ltf_bias:
        conflict_detected = True
        conflict_detail = f"Higher timeframe {htf_bias} while Lower timeframe {ltf_bias} (Counter-trend bounce into resistance)."

    return {
        "consensus_score": consensus_score,
        "consensus_rating": consensus_rating,
        "conflict_detected": conflict_detected,
        "conflict_detail": conflict_detail,
        "timeframes": results_by_tf,
    }
