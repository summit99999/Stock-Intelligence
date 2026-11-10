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

def calculate_all_indicators(
    bars: list[dict],
    nifty_bars: Optional[list[dict]] = None,
) -> dict:
    """
    Calculate all technical indicators from OHLCV bars.

    Args:
        bars: list of dicts with keys: date/timestamp, open, high, low, close, volume
        nifty_bars: optional list of benchmark OHLCV bars for relative strength

    Returns:
        dict with all indicator values (None where insufficient data).
    """
    if not bars or len(bars) < 2:
        return {"error": "Insufficient data", "bars_count": len(bars) if bars else 0}

    df = _prepare_dataframe(bars)
    n = len(df)

    nifty_close = None
    if nifty_bars and len(nifty_bars) >= 2:
        nifty_df = _prepare_dataframe(nifty_bars)
        if "close" in nifty_df.columns:
            nifty_close = nifty_df["close"]

    result: dict = {"bars_count": n}

    close = df["close"]
    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # --- Moving averages ---
    result["ema_9"] = _last_val(close.ewm(span=9, adjust=False).mean()) if n >= 9 else None
    for period in (20, 50, 100, 200):
        result[f"sma_{period}"] = _last_val(close.rolling(period).mean()) if n >= period else None
        result[f"ema_{period}"] = _last_val(close.ewm(span=period, adjust=False).mean()) if n >= period else None

    # --- RSI (14) — Wilder's smoothing ---
    rsi_s = _rsi_series(close, 14)
    result["rsi"] = _last_val(rsi_s)

    # --- Stochastic RSI (14, 3, 3) ---
    stoch_k, stoch_d = _stoch_rsi(rsi_s, 14, 3, 3)
    result["stoch_rsi_k"] = stoch_k
    result["stoch_rsi_d"] = stoch_d

    # --- MACD (12, 26, 9) ---
    macd_line, signal, histogram = _macd(close, 12, 26, 9)
    result["macd"] = macd_line
    result["macd_signal"] = signal
    result["macd_histogram"] = histogram

    # --- ADX (14) ---
    result["adx"] = _adx(high, low, close, 14)

    # --- ATR (14) ---
    result["atr_14"] = _atr(high, low, close, 14)

    # --- Bollinger Bands (20, 2.0) ---
    bb_up, bb_mid, bb_lo, bb_width, bb_b = _bollinger_bands(close, 20, 2.0)
    result["bb_upper"] = bb_up
    result["bb_middle"] = bb_mid
    result["bb_lower"] = bb_lo
    result["bb_bandwidth"] = bb_width
    result["bb_pct_b"] = bb_b

    # --- VWAP (Volume-Weighted Average Price) ---
    result["vwap"] = _vwap(high, low, close, volume)

    # --- Volume Indicators ---
    result["volume"] = int(volume.iloc[-1]) if pd.notna(volume.iloc[-1]) else None
    avg_vol_20 = volume.rolling(20).mean()
    if n >= 20 and pd.notna(avg_vol_20.iloc[-1]) and avg_vol_20.iloc[-1] > 0:
        result["avg_volume_20"] = _round(avg_vol_20.iloc[-1])
        result["relative_volume"] = _round(volume.iloc[-1] / avg_vol_20.iloc[-1])
    else:
        result["avg_volume_20"] = None
        result["relative_volume"] = None

    # --- On-Balance Volume (OBV) ---
    result["obv"] = _obv(close, volume)

    # --- Accumulation / Distribution (A/D) ---
    result["ad_line"] = _ad_line(high, low, close, volume)
    result["accumulation_distribution"] = result["ad_line"]

    # --- Chaikin Money Flow (CMF 20) ---
    result["cmf_20"] = _cmf(high, low, close, volume, 20)

    # --- Volume Spikes and Contractions ---
    result["volume_spike"] = _is_volume_spike(volume, 20, 2.0)
    result["volume_contraction"] = _is_volume_contraction(volume, 20, 0.6)

    # --- Conventional Mansfield Relative Strength (Stan Weinstein formulation) ---
    result["mansfield_rs_50"] = (
        _mansfield_rs(close, nifty_close, 50) if nifty_close is not None else None
    )
    result["mansfield_rs_20"] = (
        _mansfield_rs(close, nifty_close, 20) if nifty_close is not None else None
    )

    # --- Relative Performance vs Benchmark (dual-period rate-of-return ratio) ---
    result["relative_performance_vs_benchmark_20"] = (
        _relative_performance_vs_benchmark(close, nifty_close, 20) if nifty_close is not None else None
    )
    result["relative_performance_vs_benchmark_50"] = (
        _relative_performance_vs_benchmark(close, nifty_close, 50) if nifty_close is not None else None
    )
    result["rs_nifty_20"] = result["relative_performance_vs_benchmark_20"]
    result["rs_nifty_50"] = result["relative_performance_vs_benchmark_50"]

    # --- Money Flow Index (MFI 14) ---
    result["mfi_14"] = _mfi(high, low, close, volume, 14)

    # --- Rate of Change (ROC 10) ---
    result["roc_10"] = _roc(close, 10)

    # --- Commodity Channel Index (CCI 20) ---
    result["cci_20"] = _cci(high, low, close, 20)

    # --- Supertrend (10, 3.0) ---
    st_val, st_dir = _supertrend(high, low, close, period=10, multiplier=3.0)
    result["supertrend"] = st_val
    result["supertrend_dir"] = st_dir

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

    # --- Price & Daily Changes ---
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

    # --- Consolidation & Breakout Detection ---
    cons = _detect_consolidation_and_breakout(df, result.get("relative_volume"))
    result.update(cons)

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
    if s is None or s.empty:
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
# Wilder's Smoothing (ta.rma) - Exact TradingView Pine Script Parity
# ---------------------------------------------------------------------------

def calculate_rma(series: pd.Series, length: int) -> pd.Series:
    """
    Calculate Wilder's smoothed moving average (ta.rma) identical to TradingView Pine Script.
    - Bars 0 .. length-2 are NaN
    - Bar length-1 is seeded with the Simple Moving Average (SMA) of the first length bars
    - All subsequent bars: RMA[i] = alpha * series[i] + (1 - alpha) * RMA[i-1] where alpha = 1 / length
    """
    if len(series) < length:
        return pd.Series(np.nan, index=series.index)

    values = series.to_numpy(dtype=float)
    rma = np.full(len(values), np.nan)
    rma[length - 1] = np.nanmean(values[:length])
    alpha = 1.0 / length
    one_minus_alpha = 1.0 - alpha

    for i in range(length, len(values)):
        v = values[i]
        p = rma[i - 1]
        if np.isnan(p):
            rma[i] = v
        elif np.isnan(v):
            rma[i] = p
        else:
            rma[i] = alpha * v + one_minus_alpha * p

    return pd.Series(rma, index=series.index)


# ---------------------------------------------------------------------------
# RSI — Wilder's smoothing (TradingView Pine Script Parity)
# ---------------------------------------------------------------------------

def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """Calculate full RSI series using exact TradingView Wilder's smoothing method."""
    if len(close) < period + 1:
        return pd.Series(dtype=float)

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta.clip(upper=0))

    avg_gain = calculate_rma(gain, period)
    avg_loss = calculate_rma(loss, period)

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    rsi[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return rsi


def _rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate RSI scalar using Wilder's smoothing method."""
    s = _rsi_series(close, period)
    return _last_val(s)


# ---------------------------------------------------------------------------
# Stochastic RSI
# ---------------------------------------------------------------------------

def _stoch_rsi(
    rsi_s: pd.Series, period: int = 14, k_period: int = 3, d_period: int = 3
) -> tuple[Optional[float], Optional[float]]:
    """Calculate Stochastic RSI %K and %D."""
    if rsi_s.empty or len(rsi_s) < period + k_period:
        return None, None

    rsi_min = rsi_s.rolling(period).min()
    rsi_max = rsi_s.rolling(period).max()
    denom = (rsi_max - rsi_min).replace(0, np.nan)

    stoch = 100 * (rsi_s - rsi_min) / denom
    stoch_k = stoch.rolling(k_period).mean()
    stoch_d = stoch_k.rolling(d_period).mean()

    return _last_val(stoch_k), _last_val(stoch_d)


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
# ATR (Average True Range) - TradingView Wilder's RMA Parity
# ---------------------------------------------------------------------------

def _atr_series(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Calculate Average True Range series using exact TradingView Wilder's smoothing."""
    if len(close) < period + 1:
        return pd.Series(np.nan, index=close.index)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return calculate_rma(tr, period)


def _atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Optional[float]:
    """Calculate Average True Range scalar using Wilder's smoothing."""
    atr_s = _atr_series(high, low, close, period)
    return _last_val(atr_s)


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def _bollinger_bands(
    close: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Calculate Bollinger Bands (Upper, Middle, Lower, Bandwidth %, %B)."""
    if len(close) < period:
        return None, None, None, None, None

    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std

    bandwidth = (upper - lower) / middle.replace(0, np.nan) * 100
    pct_b = (close - lower) / (upper - lower).replace(0, np.nan)

    return (
        _last_val(upper),
        _last_val(middle),
        _last_val(lower),
        _last_val(bandwidth),
        _last_val(pct_b),
    )


# ---------------------------------------------------------------------------
# VWAP (Volume-Weighted Average Price)
# ---------------------------------------------------------------------------

def _vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> Optional[float]:
    """Calculate Volume-Weighted Average Price across bars."""
    if close.empty or volume.empty or volume.sum() == 0:
        return None

    typical_price = (high + low + close) / 3
    cum_pv = (typical_price * volume).cumsum()
    cum_vol = volume.cumsum().replace(0, np.nan)
    vwap = cum_pv / cum_vol

    return _last_val(vwap)


# ---------------------------------------------------------------------------
# OBV (On-Balance Volume)
# ---------------------------------------------------------------------------

def _obv(close: pd.Series, volume: pd.Series) -> Optional[int]:
    """Calculate On-Balance Volume."""
    if len(close) < 2:
        return None

    direction = np.sign(close.diff().fillna(0))
    obv_series = (direction * volume).cumsum()
    val = obv_series.iloc[-1]
    return int(val) if pd.notna(val) else None


# ---------------------------------------------------------------------------
# Accumulation / Distribution (A/D) Line
# ---------------------------------------------------------------------------

def _ad_series(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> pd.Series:
    """Calculate Accumulation/Distribution Line series."""
    denom = high - low
    mfm = pd.Series(0.0, index=close.index)
    valid = (denom > 0) & denom.notna()
    mfm[valid] = ((close[valid] - low[valid]) - (high[valid] - close[valid])) / denom[valid]
    mfv = mfm * volume.fillna(0)
    ad = mfv.cumsum()
    return ad


def _ad_line(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series
) -> Optional[float]:
    """Calculate last value of Accumulation/Distribution Line."""
    if close.empty or volume.empty:
        return None
    s = _ad_series(high, low, close, volume)
    return _last_val(s)


# ---------------------------------------------------------------------------
# Chaikin Money Flow (CMF 20)
# ---------------------------------------------------------------------------

def _cmf_series(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20
) -> pd.Series:
    """Calculate Chaikin Money Flow series."""
    if len(close) < period:
        return pd.Series(np.nan, index=close.index)
    denom = high - low
    mfm = pd.Series(0.0, index=close.index)
    valid = (denom > 0) & denom.notna()
    mfm[valid] = ((close[valid] - low[valid]) - (high[valid] - close[valid])) / denom[valid]
    mfv = mfm * volume.fillna(0)
    roll_mfv = mfv.rolling(period).sum()
    roll_vol = volume.rolling(period).sum().replace(0, np.nan)
    cmf = roll_mfv / roll_vol
    return cmf


def _cmf(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 20
) -> Optional[float]:
    """Calculate Chaikin Money Flow (CMF)."""
    if len(close) < period:
        return None
    s = _cmf_series(high, low, close, volume, period)
    return _last_val(s)


# ---------------------------------------------------------------------------
# Volume Spikes and Contractions
# ---------------------------------------------------------------------------

def _is_volume_spike(
    volume: pd.Series, period: int = 20, threshold: float = 2.0
) -> bool:
    """True if latest volume >= threshold * rolling 20-bar average."""
    if len(volume) < period + 1:
        return False
    # Use average of preceding 20 bars (excluding latest bar for unbiased baseline)
    baseline = volume.iloc[-(period + 1):-1].mean()
    if pd.isna(baseline) or baseline <= 0:
        return False
    latest_vol = volume.iloc[-1]
    return bool(latest_vol >= threshold * baseline)


def _is_volume_contraction(
    volume: pd.Series, period: int = 20, threshold: float = 0.6
) -> bool:
    """True if latest volume <= threshold * rolling 20-bar average."""
    if len(volume) < period + 1:
        return False
    baseline = volume.iloc[-(period + 1):-1].mean()
    if pd.isna(baseline) or baseline <= 0:
        return False
    latest_vol = volume.iloc[-1]
    return bool(latest_vol <= threshold * baseline)


# ---------------------------------------------------------------------------
# Mansfield Relative Strength (Conventional Stan Weinstein Formulation)
# ---------------------------------------------------------------------------

def _mansfield_rs_series(
    close: pd.Series, benchmark_close: pd.Series, period: int = 50
) -> pd.Series:
    """
    Conventional Mansfield Relative Strength series:
    Ratio_t = Close_stock_t / Close_bench_t
    BaseMA_t = SMA(Ratio, period)
    Mansfield RS_t = ((Ratio_t / BaseMA_t) - 1.0) * 100
    """
    if len(close) < period or len(benchmark_close) < period:
        return pd.Series(np.nan, index=close.index)

    bench_clean = benchmark_close.replace(0, np.nan)
    ratio = close / bench_clean
    base_ma = ratio.rolling(period).mean().replace(0, np.nan)
    mrs = ((ratio / base_ma) - 1.0) * 100.0
    return mrs


def _mansfield_rs(
    close: pd.Series, benchmark_close: Optional[pd.Series], period: int = 50
) -> Optional[float]:
    """Calculate last value of conventional Mansfield Relative Strength."""
    if benchmark_close is None or len(close) < period or len(benchmark_close) < period:
        return None
    s = _mansfield_rs_series(close, benchmark_close, period)
    return _last_val(s)


# ---------------------------------------------------------------------------
# Relative Performance vs Benchmark (Dual-Period Return Ratio)
# ---------------------------------------------------------------------------

def _relative_performance_vs_benchmark(
    close: pd.Series, benchmark_close: Optional[pd.Series], period: int = 20
) -> Optional[float]:
    """
    Relative performance vs benchmark percentage outperformance:
    ((P_stock_t / P_stock_{t-N}) / (P_bench_t / P_bench_{t-N}) - 1) * 100
    """
    if benchmark_close is None or len(close) <= period or len(benchmark_close) <= period:
        return None
    s_curr = close.iloc[-1]
    s_prev = close.iloc[-(period + 1)]
    b_curr = benchmark_close.iloc[-1]
    b_prev = benchmark_close.iloc[-(period + 1)]
    if pd.isna(s_curr) or pd.isna(s_prev) or s_prev <= 0:
        return None
    if pd.isna(b_curr) or pd.isna(b_prev) or b_prev <= 0:
        return None
    stock_ratio = s_curr / s_prev
    bench_ratio = b_curr / b_prev
    if bench_ratio == 0:
        return None
    rs = (stock_ratio / bench_ratio - 1.0) * 100.0
    return _round(rs)


_relative_strength = _relative_performance_vs_benchmark


# ---------------------------------------------------------------------------
# Money Flow Index (MFI 14)
# ---------------------------------------------------------------------------

def _mfi(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14
) -> Optional[float]:
    """Calculate Money Flow Index (14)."""
    if len(close) < period + 1:
        return None

    tp = (high + low + close) / 3
    rmf = tp * volume
    tp_diff = tp.diff()

    pos_mf = pd.Series(np.where(tp_diff > 0, rmf, 0), index=close.index).rolling(period).sum()
    neg_mf = pd.Series(np.where(tp_diff < 0, rmf, 0), index=close.index).rolling(period).sum()

    mfi = pd.Series(50.0, index=close.index)
    pos_only = (pos_mf > 0) & (neg_mf == 0)
    neg_only = (pos_mf == 0) & (neg_mf > 0)
    normal = (neg_mf > 0)

    mfi[pos_only] = 100.0
    mfi[neg_only] = 0.0

    mfr = pos_mf[normal] / neg_mf[normal]
    mfi[normal] = 100.0 - (100.0 / (1.0 + mfr))

    # Mask initial periods before rolling window is full
    mfi.iloc[:period] = np.nan

    return _last_val(mfi)


# ---------------------------------------------------------------------------
# Rate of Change (ROC 10)
# ---------------------------------------------------------------------------

def _roc(close: pd.Series, period: int = 10) -> Optional[float]:
    """Calculate Rate of Change (% change over N bars)."""
    if len(close) <= period:
        return None

    prev = close.shift(period).replace(0, np.nan)
    roc = (close - prev) / prev * 100
    return _last_val(roc)


# ---------------------------------------------------------------------------
# Commodity Channel Index (CCI 20)
# ---------------------------------------------------------------------------

def _cci(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20
) -> Optional[float]:
    """Calculate Commodity Channel Index (20)."""
    if len(close) < period:
        return None

    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()

    # Mean Absolute Deviation
    def calc_mad(window):
        return np.mean(np.abs(window - np.mean(window)))

    mad = tp.rolling(period).apply(calc_mad, raw=True).replace(0, np.nan)
    cci = (tp - sma_tp) / (0.015 * mad)

    return _last_val(cci)


# ---------------------------------------------------------------------------
# Supertrend - TradingView Pine Script ta.supertrend Parity
# ---------------------------------------------------------------------------

def _supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0,
) -> tuple[Optional[float], Optional[str]]:
    """
    Calculate Supertrend indicator using exact TradingView Pine Script ta.supertrend() logic.
    Returns (value, direction) where direction is 'up' or 'down'.
    """
    n = len(close)
    if n < period + 1:
        return None, None

    # Exact Wilder's RMA ATR as defined in TradingView ta.atr()
    atr = _atr_series(high, low, close, period)

    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = np.zeros(n)
    final_lower = np.zeros(n)
    supertrend = np.full(n, np.nan)
    direction = np.ones(n, dtype=int)  # 1 = up (bullish), -1 = down (bearish)

    c_vals = close.to_numpy(dtype=float)
    bu_vals = basic_upper.to_numpy(dtype=float)
    bl_vals = basic_lower.to_numpy(dtype=float)

    for i in range(period, n):
        if np.isnan(bu_vals[i]) or np.isnan(bl_vals[i]):
            continue

        # Trailing lower band
        if bl_vals[i] > final_lower[i - 1] or c_vals[i - 1] < final_lower[i - 1]:
            final_lower[i] = bl_vals[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trailing upper band
        if bu_vals[i] < final_upper[i - 1] or c_vals[i - 1] > final_upper[i - 1]:
            final_upper[i] = bu_vals[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Direction flip logic
        prev_dir = direction[i - 1]
        if prev_dir == 1:
            if c_vals[i] < final_lower[i]:
                direction[i] = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i] = 1
                supertrend[i] = final_lower[i]
        else:
            if c_vals[i] > final_upper[i]:
                direction[i] = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i] = -1
                supertrend[i] = final_upper[i]

    last_st = _round(supertrend[-1])
    last_dir = "up" if direction[-1] == 1 else "down"

    return last_st, last_dir if last_st is not None else None


# ---------------------------------------------------------------------------
# Consolidation & Breakout Detection
# ---------------------------------------------------------------------------

def _detect_consolidation_and_breakout(
    df: pd.DataFrame, relative_vol: Optional[float]
) -> dict:
    """
    Detect price consolidation (range contraction <= 8.5% over >= 20 sessions)
    and high-volume breakout triggers.
    """
    n = len(df)
    if n < 20:
        return {
            "is_consolidating": False,
            "consolidation_length": 0,
            "consolidation_range_pct": None,
            "consolidation_support": None,
            "consolidation_resistance": None,
            "is_breakout": False,
            "breakout_volume_ratio": None,
            "breakout_type": "None",
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Window of preceding 20 bars prior to the latest bar
    window_high = high.iloc[-21:-1].max() if n >= 21 else high.iloc[:-1].max()
    window_low = low.iloc[-21:-1].min() if n >= 21 else low.iloc[:-1].min()
    window_mean = close.iloc[-21:-1].mean() if n >= 21 else close.iloc[:-1].mean()

    range_pct = _round((window_high - window_low) / window_mean * 100) if window_mean > 0 else None
    is_consolidating = bool(range_pct is not None and range_pct <= 8.5)

    latest_close = close.iloc[-1]
    rvol = relative_vol or 1.0

    is_bullish_breakout = bool(
        latest_close > window_high and rvol >= 1.5
    )
    is_bearish_breakdown = bool(
        latest_close < window_low and rvol >= 1.5
    )

    breakout_type = "None"
    if is_bullish_breakout:
        breakout_type = "Bullish Breakout"
    elif is_bearish_breakdown:
        breakout_type = "Bearish Breakdown"

    return {
        "is_consolidating": is_consolidating,
        "consolidation_length": 20 if is_consolidating else 0,
        "consolidation_range_pct": range_pct,
        "consolidation_support": _round(window_low),
        "consolidation_resistance": _round(window_high),
        "is_breakout": is_bullish_breakout or is_bearish_breakdown,
        "breakout_volume_ratio": _round(rvol),
        "breakout_type": breakout_type,
    }


# ---------------------------------------------------------------------------
# Indicator Timeseries for Charting
# ---------------------------------------------------------------------------

def calculate_indicators_timeseries(bars: list[dict]) -> dict:
    """
    Calculate full indicator time-series aligned with bar timestamps
    for interactive charting overlays and indicator sub-panes.
    """
    if not bars:
        return {"error": "No bars provided", "dates": []}

    df = _prepare_dataframe(bars)
    n = len(df)
    if n == 0:
        return {"error": "Empty dataframe", "dates": []}

    dates = (
        df["date"].astype(str).tolist()
        if "date" in df.columns
        else [str(i) for i in range(n)]
    )
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving averages
    ema_9 = close.ewm(span=9, adjust=False).mean()
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    ema_200 = close.ewm(span=200, adjust=False).mean()
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()

    # RSI
    rsi_s = _rsi_series(close, 14)

    # MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    # Bollinger Bands
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2.0 * bb_std
    bb_lower = bb_mid - 2.0 * bb_std

    # VWAP
    tp = (high + low + close) / 3
    cum_pv = (tp * volume).cumsum()
    cum_vol = volume.cumsum().replace(0, np.nan)
    vwap = cum_pv / cum_vol

    # CMF & A/D
    cmf_s = _cmf_series(high, low, close, volume, 20)
    ad_s = _ad_series(high, low, close, volume)

    def _to_clean_list(series: pd.Series) -> list[Optional[float]]:
        return [
            None if (pd.isna(x) or np.isinf(x)) else round(float(x), 2)
            for x in series
        ]

    return {
        "dates": dates,
        "ema_9": _to_clean_list(ema_9),
        "ema_20": _to_clean_list(ema_20),
        "ema_50": _to_clean_list(ema_50),
        "ema_200": _to_clean_list(ema_200),
        "sma_20": _to_clean_list(sma_20),
        "sma_50": _to_clean_list(sma_50),
        "sma_200": _to_clean_list(sma_200),
        "rsi_14": _to_clean_list(rsi_s),
        "macd": {
            "macd": _to_clean_list(macd_line),
            "signal": _to_clean_list(signal_line),
            "histogram": _to_clean_list(macd_hist),
        },
        "bollinger": {
            "upper": _to_clean_list(bb_upper),
            "middle": _to_clean_list(bb_mid),
            "lower": _to_clean_list(bb_lower),
        },
        "vwap": _to_clean_list(vwap),
        "cmf_20": _to_clean_list(cmf_s),
        "ad_line": _to_clean_list(ad_s),
    }
