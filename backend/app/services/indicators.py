"""
Technical indicators engine — calculates all indicators from OHLCV data.

All calculations use pandas/numpy on actual price data.
Returns None for any indicator with insufficient historical data.
Never fills missing values with fabricated numbers.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def calculate_all_indicators(bars: list[dict]) -> dict:
    """
    Calculate all technical indicators from OHLCV bars.

    Args:
        bars: list of dicts with keys: date/timestamp, open, high, low, close, volume

    Returns:
        dict with all indicator values (None where insufficient data).
    """
    if not bars or len(bars) < 2:
        return {"error": "Insufficient data", "bars_count": len(bars) if bars else 0}

    df = _prepare_dataframe(bars)
    n = len(df)

    result: dict = {"bars_count": n}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # --- Moving averages ---
    for period in (20, 50, 100, 200):
        result[f"sma_{period}"] = _last_val(close.rolling(period).mean()) if n >= period else None
        result[f"ema_{period}"] = _last_val(close.ewm(span=period, adjust=False).mean()) if n >= period else None

    # --- RSI (14) — Wilder's smoothing ---
    result["rsi"] = _rsi(close, 14)

    # --- MACD (12, 26, 9) ---
    macd_line, signal, histogram = _macd(close, 12, 26, 9)
    result["macd"] = macd_line
    result["macd_signal"] = signal
    result["macd_histogram"] = histogram

    # --- ADX (14) ---
    result["adx"] = _adx(high, low, close, 14)

    # --- Supertrend ---
    st_val, st_dir = _supertrend(high, low, close, period=10, multiplier=3.0)
    result["supertrend"] = st_val
    result["supertrend_dir"] = st_dir

    # --- Volume indicators ---
    result["volume"] = int(volume.iloc[-1]) if pd.notna(volume.iloc[-1]) else None
    avg_vol_20 = volume.rolling(20).mean()
    if n >= 20 and pd.notna(avg_vol_20.iloc[-1]) and avg_vol_20.iloc[-1] > 0:
        result["avg_volume_20"] = _round(avg_vol_20.iloc[-1])
        result["relative_volume"] = _round(volume.iloc[-1] / avg_vol_20.iloc[-1])
    else:
        result["avg_volume_20"] = None
        result["relative_volume"] = None

    # --- 52-week high / low (252 trading days) ---
    if n >= 252:
        result["week_52_high"] = _round(high.iloc[-252:].max())
        result["week_52_low"] = _round(low.iloc[-252:].min())
    elif n >= 20:
        result["week_52_high"] = _round(high.max())
        result["week_52_low"] = _round(low.min())
    else:
        result["week_52_high"] = None
        result["week_52_low"] = None

    # --- Price ---
    result["close"] = _round(close.iloc[-1])
    if n >= 2 and pd.notna(close.iloc[-2]) and close.iloc[-2] != 0:
        result["daily_change_pct"] = _round(
            (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100
        )
    else:
        result["daily_change_pct"] = None

    # --- Returns ---
    result["return_1d_pct"] = _pct_return(close, 1)
    result["return_1w_pct"] = _pct_return(close, 5)
    result["return_1m_pct"] = _pct_return(close, 21)
    result["return_3m_pct"] = _pct_return(close, 63)
    result["return_6m_pct"] = _pct_return(close, 126)
    result["return_1y_pct"] = _pct_return(close, 252)

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prepare_dataframe(bars: list[dict]) -> pd.DataFrame:
    """Build a sorted, cleaned DataFrame from raw bar dicts."""
    df = pd.DataFrame(bars)

    # Normalise column names
    rename = {}
    if "timestamp" in df.columns and "date" not in df.columns:
        rename["timestamp"] = "date"
    df = df.rename(columns=rename)

    # Ensure numeric types
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Fill missing volume with 0
    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0)

    # Sort by date
    if "date" in df.columns:
        df = df.sort_values("date").reset_index(drop=True)

    return df


def _last_val(s: pd.Series) -> Optional[float]:
    """Return the last non-NaN value of a series, or None."""
    if s.empty:
        return None
    v = s.iloc[-1]
    return _round(v) if pd.notna(v) else None


def _round(v, decimals=2) -> Optional[float]:
    """Round a value, returning None for NaN/Inf."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return None
    return round(float(v), decimals)


def _pct_return(close: pd.Series, days: int) -> Optional[float]:
    """Percentage return over N trading days."""
    n = len(close)
    if n <= days:
        return None
    old = close.iloc[-(days + 1)]
    new = close.iloc[-1]
    if pd.isna(old) or pd.isna(new) or old == 0:
        return None
    return _round((new - old) / old * 100)


# ---------------------------------------------------------------------------
# RSI — Wilder's smoothing
# ---------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate RSI using Wilder's smoothing method."""
    if len(close) < period + 1:
        return None

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))

    # Wilder's smoothing: use ewm with alpha=1/period
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)

    return _last_val(rsi)


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def _macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Optional[float], Optional[float], Optional[float]]:
    """Calculate MACD line, signal line, and histogram."""
    if len(close) < slow + signal:
        return None, None, None

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return _last_val(macd_line), _last_val(signal_line), _last_val(histogram)


# ---------------------------------------------------------------------------
# ADX (Average Directional Index)
# ---------------------------------------------------------------------------

def _adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Optional[float]:
    """Calculate ADX using Wilder's smoothing."""
    n = len(close)
    if n < period * 2:
        return None

    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=high.index)

    # Wilder's smoothing
    alpha = 1 / period
    atr = tr.ewm(alpha=alpha, min_periods=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=alpha, min_periods=period, adjust=False).mean() / atr)

    # ADX
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx = dx.ewm(alpha=alpha, min_periods=period, adjust=False).mean()

    return _last_val(adx)


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------

def _supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[Optional[float], Optional[str]]:
    """
    Calculate Supertrend indicator.
    Returns (value, direction) where direction is 'up' or 'down'.
    """
    n = len(close)
    if n < period + 1:
        return None, None

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()

    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=close.index)
    direction = pd.Series(1, index=close.index)  # 1 = up, -1 = down

    for i in range(period, n):
        if pd.isna(upper_band.iloc[i]):
            continue

        if i == period:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1
            continue

        # Previous supertrend
        prev_st = supertrend.iloc[i - 1]
        prev_dir = direction.iloc[i - 1]

        if prev_dir == 1:  # was bullish
            if close.iloc[i] > prev_st:
                supertrend.iloc[i] = max(lower_band.iloc[i], prev_st)
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:  # was bearish
            if close.iloc[i] < prev_st:
                supertrend.iloc[i] = min(upper_band.iloc[i], prev_st)
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    last_st = _round(supertrend.iloc[-1])
    last_dir = "up" if direction.iloc[-1] == 1 else "down"

    return last_st, last_dir if last_st is not None else None
