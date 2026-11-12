"""
Consolidation Breakout Strategy Engine (Phase 3).

Strict, mathematically rigorous point-in-time implementation of the daily
NSE equity consolidation breakout strategy.

Rules & Invariants:
1. Consolidation Lookback: 20 completed sessions (bars t-20 to t-1).
2. Resistance: max(High[t-20 : t-1]). Bar t is strictly excluded.
3. Support: min(Low[t-20 : t-1]). Bar t is strictly excluded.
4. Range: ((Resistance - Support) / Support) * 100 <= max_consolidation_pct (default 8.0%).
5. Trend Filter: Close[t] > SMA20[t] and Close[t] > SMA50[t].
6. Volume Contraction: During consolidation, 5-bar average volume < 20-bar average volume
   (VolSMA5[t-1] < VolSMA20[t-1]) or negative volume trend.
7. Breakout Trigger: Close[t] > Resistance.
8. Volume Confirmation: Volume[t] >= breakout_vol_mult * VolSMA20[t-1] (default 1.5x).
9. Signal emitted at close of bar t for execution on Open of bar t+1.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


@dataclass
class BreakoutSignal:
    symbol: str
    signal_date: str          # Date on which the breakout closed (session t)
    execution_date: str       # Next regular trading session (session t+1)
    close_price: float        # Breakout close price
    resistance: float         # 20-session resistance (excluding breakout candle)
    support: float            # 20-session support (excluding breakout candle)
    consolidation_range_pct: float
    breakout_volume: int
    avg_volume_20: float
    volume_ratio: float
    stop_loss_level: float    # Support level (or buffer below support)
    profit_target_multiple: float  # e.g. 2.0 (2:1 R:R)
    sma_20: float
    sma_50: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StrategyParameters:
    consolidation_lookback: int = 20
    max_consolidation_range_pct: float = 8.0
    uptrend_sma_fast: int = 20
    uptrend_sma_slow: int = 50
    breakout_volume_multiplier: float = 1.5
    stop_buffer_pct: float = 0.2  # 0.2% below consolidation low
    reward_to_risk_ratio: float = 2.0
    use_trailing_stop: bool = True
    trailing_stop_sma: int = 20
    use_profit_target: bool = True
    use_max_holding_period: bool = True
    max_holding_period_sessions: int = 20
    slippage_bps: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_volume_contraction(
    volume_series: pd.Series,
    end_idx: int,
    lookback: int = 20,
) -> bool:
    """
    Evaluates whether volume showed contraction during the consolidation window.
    Criteria:
    1. VolSMA5 at end of consolidation < VolSMA20 at end of consolidation, OR
    2. Linear regression slope of volume over the consolidation window is negative.
    """
    if end_idx < lookback:
        return False

    v_window = volume_series.iloc[end_idx - lookback : end_idx]
    if len(v_window) < lookback or v_window.isnull().any():
        return False

    # 1. Moving average contraction
    sma5 = v_window.tail(5).mean()
    sma20 = v_window.mean()
    if sma20 > 0 and sma5 < sma20:
        return True

    # 2. Linear slope of volume across window
    x = np.arange(len(v_window))
    y = v_window.values
    if len(y) >= 10:
        slope, _ = np.polyfit(x, y, 1)
        if slope < 0:
            return True

    return False


def scan_consolidation_breakouts(
    symbol: str,
    df: pd.DataFrame,
    params: Optional[StrategyParameters] = None,
) -> List[BreakoutSignal]:
    """
    Scan chronological OHLCV dataframe for consolidation breakout signals.
    Guarantees:
    - Zero look-ahead: bar t only uses information up to and including bar t.
    - Resistance and Support strictly computed from bars [t - lookback : t - 1].
    - Signals identify the execution date as session t+1.
    """
    if df.empty or len(df) < 55:
        return []

    p = params or StrategyParameters()
    lookback = p.consolidation_lookback
    max_range = p.max_consolidation_range_pct
    vol_mult = p.breakout_volume_multiplier

    signals: List[BreakoutSignal] = []

    # Ensure required indicator columns exist
    df = df.copy()
    if f"sma_{p.uptrend_sma_fast}" not in df.columns:
        df[f"sma_{p.uptrend_sma_fast}"] = df["close"].rolling(p.uptrend_sma_fast).mean()
    if f"sma_{p.uptrend_sma_slow}" not in df.columns:
        df[f"sma_{p.uptrend_sma_slow}"] = df["close"].rolling(p.uptrend_sma_slow).mean()
    if "vol_sma_20" not in df.columns:
        df["vol_sma_20"] = df["volume"].rolling(20).mean()

    n = len(df)
    fast_sma_col = f"sma_{p.uptrend_sma_fast}"
    slow_sma_col = f"sma_{p.uptrend_sma_slow}"

    # Minimum warmup required for SMA50 + lookback
    min_idx = max(p.uptrend_sma_slow, lookback)

    for t in range(min_idx, n - 1):
        # We need session t+1 to exist for execution
        exec_date = df["date"].iloc[t + 1]

        close_t = float(df["close"].iloc[t])
        vol_t = float(df["volume"].iloc[t])
        date_t = str(df["date"].iloc[t])

        sma_fast_t = float(df[fast_sma_col].iloc[t])
        sma_slow_t = float(df[slow_sma_col].iloc[t])

        # 1. Uptrend Filter: Close > SMA20 and Close > SMA50
        if np.isnan(sma_fast_t) or np.isnan(sma_slow_t):
            continue
        if close_t <= sma_fast_t or close_t <= sma_slow_t:
            continue

        # 2. Consolidation window: strictly [t - lookback : t] (excluding t)
        cons_highs = df["high"].iloc[t - lookback : t]
        cons_lows = df["low"].iloc[t - lookback : t]

        resistance = float(cons_highs.max())
        support = float(cons_lows.min())

        if support <= 0.0 or resistance <= support:
            continue

        range_pct = ((resistance - support) / support) * 100.0

        # 3. Maximum consolidation range check (default <= 8%)
        if range_pct > max_range:
            continue

        # 4. Volume contraction during consolidation (prior to breakout day)
        vol_contracted = calculate_volume_contraction(df["volume"], end_idx=t, lookback=lookback)
        if not vol_contracted:
            continue

        # 5. Breakout condition: Close[t] > Resistance
        if close_t <= resistance:
            continue

        # 6. Breakout volume confirmation: Volume[t] >= 1.5 * VolSMA20[t-1]
        vol_sma_prev = float(df["vol_sma_20"].iloc[t - 1])
        if np.isnan(vol_sma_prev) or vol_sma_prev <= 0.0:
            continue

        if vol_t < (vol_mult * vol_sma_prev):
            continue

        vol_ratio = round(vol_t / vol_sma_prev, 2)

        # 7. Initial stop loss: below consolidation support
        stop_buffer = (p.stop_buffer_pct / 100.0) * support
        stop_loss = round(support - stop_buffer, 2)

        signals.append(
            BreakoutSignal(
                symbol=symbol,
                signal_date=date_t,
                execution_date=str(exec_date),
                close_price=round(close_t, 2),
                resistance=round(resistance, 2),
                support=round(support, 2),
                consolidation_range_pct=round(range_pct, 2),
                breakout_volume=int(vol_t),
                avg_volume_20=round(vol_sma_prev, 0),
                volume_ratio=vol_ratio,
                stop_loss_level=stop_loss,
                profit_target_multiple=p.reward_to_risk_ratio,
                sma_20=round(sma_fast_t, 2),
                sma_50=round(sma_slow_t, 2),
            )
        )

    return signals
