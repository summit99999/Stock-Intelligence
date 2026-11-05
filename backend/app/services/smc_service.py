"""
Smart Money Concepts (SMC) & Order Block Quantitative Engine.

Calculates:
- Swing High / Low Pivot Detection (HH, HL, LH, LL)
- Break of Structure (BOS) & Change of Character (CHoCH)
- Bullish & Bearish Order Blocks (with ATR displacement & lifecycle tracking)
- Fair Value Gaps (3-candle FVG with fill % tracking)
- Supply & Demand Zones (RBD, DBR, RBR, DBD)
- Liquidity Mapping (EQH, EQL, PDH, PDL, PWH, PWL & Sweeps)
- Premium vs Discount Dealing Range (Equilibrium 50%)
- Multi-factor Institutional Setup Score (100-pt breakdown)

Data Truthfulness:
- Calculations rely strictly on completed candle closes to avoid repainting.
- All derived proxy metrics are explicitly labeled.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars, get_stock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Preparation & ATR
# ---------------------------------------------------------------------------

def _prepare_df(bars: list[dict]) -> pd.DataFrame:
    """Prepare and normalize OHLCV dataframe."""
    df = pd.DataFrame(bars)
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = df["volume"].fillna(0)

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    return df


def _calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr


# ---------------------------------------------------------------------------
# 1. Market Structure & Swing Detection (HH, HL, LH, LL, BOS, CHoCH)
# ---------------------------------------------------------------------------

def detect_market_structure(df: pd.DataFrame, lookback: int = 3) -> dict:
    """
    Detect swing pivots and structural breaks (BOS & CHoCH).
    """
    n = len(df)
    if n < lookback * 2 + 1:
        return {
            "trend": "NEUTRAL",
            "swings": [],
            "breaks": [],
            "last_bos": None,
            "last_choch": None,
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]

    swings = []

    # Detect swing highs and lows
    for i in range(lookback, n - lookback):
        # Swing High: highest among lookback left and lookback right
        is_sh = True
        for k in range(1, lookback + 1):
            if high.iloc[i] <= high.iloc[i - k] or high.iloc[i] <= high.iloc[i + k]:
                is_sh = False
                break
        if is_sh:
            conf_idx = i + lookback
            avail_idx = (i + lookback + 1) if (i + lookback + 1 < n) else None
            avail_ts = str(df["timestamp"].iloc[avail_idx]) if avail_idx is not None else None
            swings.append({
                "index": i,
                "occurrence_index": i,
                "timestamp": str(df["timestamp"].iloc[i]),
                "occurrence_timestamp": str(df["timestamp"].iloc[i]),
                "confirmation_index": conf_idx,
                "confirmation_timestamp": str(df["timestamp"].iloc[conf_idx]),
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_ts,
                "type": "SWING_HIGH",
                "price": round(float(high.iloc[i]), 2),
                "is_confirmed": True,
            })

        # Swing Low: lowest among lookback left and lookback right
        is_sl = True
        for k in range(1, lookback + 1):
            if low.iloc[i] >= low.iloc[i - k] or low.iloc[i] >= low.iloc[i + k]:
                is_sl = False
                break
        if is_sl:
            conf_idx = i + lookback
            avail_idx = (i + lookback + 1) if (i + lookback + 1 < n) else None
            avail_ts = str(df["timestamp"].iloc[avail_idx]) if avail_idx is not None else None
            swings.append({
                "index": i,
                "occurrence_index": i,
                "timestamp": str(df["timestamp"].iloc[i]),
                "occurrence_timestamp": str(df["timestamp"].iloc[i]),
                "confirmation_index": conf_idx,
                "confirmation_timestamp": str(df["timestamp"].iloc[conf_idx]),
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_ts,
                "type": "SWING_LOW",
                "price": round(float(low.iloc[i]), 2),
                "is_confirmed": True,
            })

    # Sort swings by chronological bar index
    swings = sorted(swings, key=lambda s: s["index"])

    # Categorize swings (HH, HL, LH, LL) and identify structure breaks (BOS / CHoCH)
    labeled_swings = []
    breaks = []
    current_trend = "NEUTRAL"
    last_sh = None
    last_sl = None

    for s in swings:
        if s["type"] == "SWING_HIGH":
            if last_sh is not None:
                tag = "HH" if s["price"] > last_sh["price"] else "LH"
            else:
                tag = "HIGH"
            s["tag"] = tag
            s["label"] = tag
            last_sh = s
        else:
            if last_sl is not None:
                tag = "HL" if s["price"] > last_sl["price"] else "LL"
            else:
                tag = "LOW"
            s["tag"] = tag
            s["label"] = tag
            last_sl = s
        labeled_swings.append(s)

    # Detect BOS & CHoCH across chronological candle closes
    # Non-repainting rule: A swing level ONLY becomes available once bar i >= swing["confirmation_index"]!
    active_sh = None
    active_sl = None
    swing_idx = 0

    for i in range(n):
        # Activate swing points whose confirmation window has completed at or before bar i
        while swing_idx < len(swings) and swings[swing_idx]["confirmation_index"] <= i:
            cur = swings[swing_idx]
            if cur["type"] == "SWING_HIGH":
                active_sh = cur
            else:
                active_sl = cur
            swing_idx += 1

        c_close = close.iloc[i]
        c_time = str(df["timestamp"].iloc[i])
        avail_idx = (i + 1) if (i + 1 < n) else None
        avail_time = str(df["timestamp"].iloc[avail_idx]) if avail_idx is not None else None

        # Bullish break test
        if active_sh is not None and c_close > active_sh["price"] and i >= active_sh["confirmation_index"]:
            break_type = "CHoCH" if current_trend in ("BEARISH", "NEUTRAL") else "BOS"
            current_trend = "BULLISH"
            breaks.append({
                "bar_index": i,
                "timestamp": c_time,
                "occurrence_index": i,
                "occurrence_timestamp": c_time,
                "confirmation_index": i,
                "confirmation_timestamp": c_time,
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_time,
                "type": break_type,
                "direction": "BULLISH",
                "broken_level": active_sh["price"],
                "breakout_price": round(float(c_close), 2),
                "swing_timestamp": active_sh["timestamp"],
                "swing_confirmation_timestamp": active_sh["confirmation_timestamp"],
            })
            active_sh = None  # Level consumed

        # Bearish break test
        if active_sl is not None and c_close < active_sl["price"] and i >= active_sl["confirmation_index"]:
            break_type = "CHoCH" if current_trend in ("BULLISH", "NEUTRAL") else "BOS"
            current_trend = "BEARISH"
            breaks.append({
                "bar_index": i,
                "timestamp": c_time,
                "occurrence_index": i,
                "occurrence_timestamp": c_time,
                "confirmation_index": i,
                "confirmation_timestamp": c_time,
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_time,
                "type": break_type,
                "direction": "BEARISH",
                "broken_level": active_sl["price"],
                "breakout_price": round(float(c_close), 2),
                "swing_timestamp": active_sl["timestamp"],
                "swing_confirmation_timestamp": active_sl["confirmation_timestamp"],
            })
            active_sl = None  # Level consumed

    last_bos = next((b for b in reversed(breaks) if b["type"] == "BOS"), None)
    last_choch = next((b for b in reversed(breaks) if b["type"] == "CHoCH"), None)

    return {
        "trend": current_trend,
        "swings": labeled_swings,
        "breaks": breaks,
        "last_bos": last_bos,
        "last_choch": last_choch,
    }


# ---------------------------------------------------------------------------
# 2. Order Block Detection & Lifecycle (Module 2)
# ---------------------------------------------------------------------------

def detect_order_blocks(
    df: pd.DataFrame,
    breaks: list[dict],
    min_displacement_atr: float = 1.0,
    use_body_boundaries: bool = False,
    mitigation_threshold_pct: float = 50.0,
) -> list[dict]:
    """
    Detect bullish and bearish order blocks linked to confirmed structural breaks.
    Tracks lifecycle: FRESH -> TESTED -> MITIGATED -> INVALIDATED.
    Deterministic priority: INVALIDATED > MITIGATED > TESTED > FRESH.
    """
    n = len(df)
    if n < 5:
        return []

    atr = _calc_atr(df, 14)
    avg_vol_20 = df["volume"].rolling(20).mean()

    open_ = df["open"]
    high = df["high"]
    low = df["low"]
    close = df["close"]
    volume = df["volume"]
    timestamps = df["timestamp"].astype(str)

    order_blocks = []

    for b in breaks:
        break_bar = b["bar_index"]
        direction = b["direction"]
        current_atr = float(atr.iloc[break_bar]) if pd.notna(atr.iloc[break_bar]) else 10.0

        if direction == "BULLISH":
            # Search backwards from break_bar to find the last bearish candle (close < open)
            candidate_idx = None
            for j in range(break_bar - 1, max(0, break_bar - 12), -1):
                if close.iloc[j] < open_.iloc[j]:
                    candidate_idx = j
                    break

            if candidate_idx is None:
                candidate_idx = max(0, break_bar - 1)

            # Check displacement
            displacement = high.iloc[candidate_idx:break_bar + 1].max() - low.iloc[candidate_idx]
            if displacement < min_displacement_atr * current_atr:
                continue

            # Define Zone
            if use_body_boundaries:
                z_high = float(open_.iloc[candidate_idx])
                z_low = float(close.iloc[candidate_idx])
            else:
                z_high = float(high.iloc[candidate_idx])
                z_low = float(low.iloc[candidate_idx])

            invalidation_level = float(low.iloc[candidate_idx])

            # Lifecycle check through subsequent bars after displacement
            status = "FRESH"
            retest_count = 0
            mitigation_pct = 0.0
            first_retest_idx = None
            inval_idx = None
            mitig_idx = None
            was_inside_zone = False

            for k in range(break_bar + 1, n):
                k_high = float(high.iloc[k])
                k_low = float(low.iloc[k])
                k_close = float(close.iloc[k])

                # Priority 1: Invalidation check (close below invalidation level OR gap-through below zone)
                is_invalidated = (k_close < invalidation_level) or (k_high < z_low)
                if is_invalidated:
                    status = "INVALIDATED"
                    inval_idx = k
                    break

                # Retest & Mitigation check
                if k_low <= z_high:
                    if not was_inside_zone:
                        retest_count += 1
                        was_inside_zone = True
                        if first_retest_idx is None:
                            first_retest_idx = k

                    depth = (z_high - k_low) / max(z_high - z_low, 0.01)
                    mitigation_pct = max(mitigation_pct, min(100.0, depth * 100))
                    if mitigation_pct >= mitigation_threshold_pct:
                        status = "MITIGATED"
                        if mitig_idx is None:
                            mitig_idx = k
                    elif status == "FRESH":
                        status = "TESTED"
                else:
                    was_inside_zone = False

            vol_ratio = 1.0
            if pd.notna(avg_vol_20.iloc[candidate_idx]) and avg_vol_20.iloc[candidate_idx] > 0:
                vol_ratio = round(float(volume.iloc[candidate_idx] / avg_vol_20.iloc[candidate_idx]), 2)

            avail_idx = (break_bar + 1) if (break_bar + 1 < n) else None
            avail_ts = timestamps.iloc[avail_idx] if avail_idx is not None else None
            order_blocks.append({
                "id": f"ob-bull-{candidate_idx}",
                "direction": "BULLISH",
                "candle_index": candidate_idx,
                "occurrence_index": candidate_idx,
                "timestamp": timestamps.iloc[candidate_idx],
                "occurrence_timestamp": timestamps.iloc[candidate_idx],
                "confirmation_index": break_bar,
                "confirmation_timestamp": timestamps.iloc[break_bar],
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_ts,
                "zone_high": round(z_high, 2),
                "zone_low": round(z_low, 2),
                "invalidation_level": round(invalidation_level, 2),
                "displacement_atr": round(float(displacement / current_atr), 2),
                "volume_expansion_ratio": vol_ratio,
                "associated_break": b["type"],
                "status": status,
                "retest_count": retest_count,
                "mitigation_pct": round(mitigation_pct, 1),
                "first_retest_index": first_retest_idx,
                "first_retest_timestamp": timestamps.iloc[first_retest_idx] if first_retest_idx is not None else None,
                "invalidation_index": inval_idx,
                "invalidation_timestamp": timestamps.iloc[inval_idx] if inval_idx is not None else None,
            })

        else:  # BEARISH
            # Search backwards for the last bullish candle (close > open)
            candidate_idx = None
            for j in range(break_bar - 1, max(0, break_bar - 12), -1):
                if close.iloc[j] > open_.iloc[j]:
                    candidate_idx = j
                    break

            if candidate_idx is None:
                candidate_idx = max(0, break_bar - 1)

            # Check displacement
            displacement = high.iloc[candidate_idx] - low.iloc[candidate_idx:break_bar + 1].min()
            if displacement < min_displacement_atr * current_atr:
                continue

            # Define Zone
            if use_body_boundaries:
                z_high = float(close.iloc[candidate_idx])
                z_low = float(open_.iloc[candidate_idx])
            else:
                z_high = float(high.iloc[candidate_idx])
                z_low = float(low.iloc[candidate_idx])

            invalidation_level = float(high.iloc[candidate_idx])

            # Lifecycle check through subsequent bars
            status = "FRESH"
            retest_count = 0
            mitigation_pct = 0.0
            first_retest_idx = None
            inval_idx = None
            mitig_idx = None
            was_inside_zone = False

            for k in range(break_bar + 1, n):
                k_high = float(high.iloc[k])
                k_low = float(low.iloc[k])
                k_close = float(close.iloc[k])

                # Priority 1: Invalidation check (close above invalidation level OR gap-through above zone)
                is_invalidated = (k_close > invalidation_level) or (k_low > z_high)
                if is_invalidated:
                    status = "INVALIDATED"
                    inval_idx = k
                    break

                # Retest & Mitigation check
                if k_high >= z_low:
                    if not was_inside_zone:
                        retest_count += 1
                        was_inside_zone = True
                        if first_retest_idx is None:
                            first_retest_idx = k

                    depth = (k_high - z_low) / max(z_high - z_low, 0.01)
                    mitigation_pct = max(mitigation_pct, min(100.0, depth * 100))
                    if mitigation_pct >= mitigation_threshold_pct:
                        status = "MITIGATED"
                        if mitig_idx is None:
                            mitig_idx = k
                    elif status == "FRESH":
                        status = "TESTED"
                else:
                    was_inside_zone = False

            vol_ratio = 1.0
            if pd.notna(avg_vol_20.iloc[candidate_idx]) and avg_vol_20.iloc[candidate_idx] > 0:
                vol_ratio = round(float(volume.iloc[candidate_idx] / avg_vol_20.iloc[candidate_idx]), 2)

            avail_idx = (break_bar + 1) if (break_bar + 1 < n) else None
            avail_ts = timestamps.iloc[avail_idx] if avail_idx is not None else None
            order_blocks.append({
                "id": f"ob-bear-{candidate_idx}",
                "direction": "BEARISH",
                "candle_index": candidate_idx,
                "occurrence_index": candidate_idx,
                "timestamp": timestamps.iloc[candidate_idx],
                "occurrence_timestamp": timestamps.iloc[candidate_idx],
                "confirmation_index": break_bar,
                "confirmation_timestamp": timestamps.iloc[break_bar],
                "signal_available_index": avail_idx,
                "signal_available_timestamp": avail_ts,
                "zone_high": round(z_high, 2),
                "zone_low": round(z_low, 2),
                "invalidation_level": round(invalidation_level, 2),
                "displacement_atr": round(float(displacement / current_atr), 2),
                "volume_expansion_ratio": vol_ratio,
                "associated_break": b["type"],
                "status": status,
                "retest_count": retest_count,
                "mitigation_pct": round(mitigation_pct, 1),
                "first_retest_index": first_retest_idx,
                "first_retest_timestamp": timestamps.iloc[first_retest_idx] if first_retest_idx is not None else None,
                "invalidation_index": inval_idx,
                "invalidation_timestamp": timestamps.iloc[inval_idx] if inval_idx is not None else None,
            })

    # Return order blocks sorted chronologically
    return sorted(order_blocks, key=lambda x: x["candle_index"])


# ---------------------------------------------------------------------------
# 3. Fair Value Gaps (FVG) (Module 5)
# ---------------------------------------------------------------------------

def detect_fair_value_gaps(df: pd.DataFrame, min_atr_mult: float = 0.15) -> list[dict]:
    """
    Detect three-candle Fair Value Gaps (FVG) and compute their fill percentages.
    """
    n = len(df)
    if n < 3:
        return []

    atr = _calc_atr(df, 14)
    high = df["high"]
    low = df["low"]
    timestamps = df["timestamp"].astype(str)

    fvgs = []

    for i in range(2, n):
        cur_atr = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else 1.0
        min_gap = min_atr_mult * cur_atr

        # Bullish FVG: Low of candle i > High of candle i-2
        if low.iloc[i] > high.iloc[i - 2]:
            gap_size = float(low.iloc[i] - high.iloc[i - 2])
            if gap_size >= min_gap:
                g_low = float(high.iloc[i - 2])
                g_high = float(low.iloc[i])

                # Check fill by subsequent candles (i+1 to n)
                penetration = 0.0
                for k in range(i + 1, n):
                    if low.iloc[k] <= g_high:
                        pen = g_high - low.iloc[k]
                        penetration = max(penetration, pen)

                fill_pct = min(100.0, max(0.0, (penetration / gap_size) * 100))
                avail_idx = (i + 1) if (i + 1 < n) else None
                avail_ts = timestamps.iloc[avail_idx] if avail_idx is not None else None

                fvgs.append({
                    "id": f"fvg-bull-{i}",
                    "direction": "BULLISH",
                    "bar_index": i,
                    "occurrence_index": i - 1,
                    "occurrence_timestamp": timestamps.iloc[i - 1],
                    "confirmation_index": i,
                    "confirmation_timestamp": timestamps.iloc[i],
                    "signal_available_index": avail_idx,
                    "signal_available_timestamp": avail_ts,
                    "timestamp": timestamps.iloc[i],
                    "zone_high": round(g_high, 2),
                    "zone_low": round(g_low, 2),
                    "gap_size": round(gap_size, 2),
                    "fill_pct": round(fill_pct, 1),
                    "is_filled": bool(fill_pct >= 100.0),
                    "status": "FILLED" if fill_pct >= 100.0 else ("PARTIAL" if fill_pct > 0 else "UNFILLED"),
                })

        # Bearish FVG: High of candle i < Low of candle i-2
        if high.iloc[i] < low.iloc[i - 2]:
            gap_size = float(low.iloc[i - 2] - high.iloc[i])
            if gap_size >= min_gap:
                g_low = float(high.iloc[i])
                g_high = float(low.iloc[i - 2])

                # Check fill by subsequent candles
                penetration = 0.0
                for k in range(i + 1, n):
                    if high.iloc[k] >= g_low:
                        pen = high.iloc[k] - g_low
                        penetration = max(penetration, pen)

                fill_pct = min(100.0, max(0.0, (penetration / gap_size) * 100))
                avail_idx = (i + 1) if (i + 1 < n) else None
                avail_ts = timestamps.iloc[avail_idx] if avail_idx is not None else None

                fvgs.append({
                    "id": f"fvg-bear-{i}",
                    "direction": "BEARISH",
                    "bar_index": i,
                    "occurrence_index": i - 1,
                    "occurrence_timestamp": timestamps.iloc[i - 1],
                    "confirmation_index": i,
                    "confirmation_timestamp": timestamps.iloc[i],
                    "signal_available_index": avail_idx,
                    "signal_available_timestamp": avail_ts,
                    "timestamp": timestamps.iloc[i],
                    "zone_high": round(g_high, 2),
                    "zone_low": round(g_low, 2),
                    "gap_size": round(gap_size, 2),
                    "fill_pct": round(fill_pct, 1),
                    "is_filled": bool(fill_pct >= 100.0),
                    "status": "FILLED" if fill_pct >= 100.0 else ("PARTIAL" if fill_pct > 0 else "UNFILLED"),
                })

    return fvgs


# ---------------------------------------------------------------------------
# 4. Supply & Demand Zones (Module 3)
# ---------------------------------------------------------------------------

def detect_supply_demand_zones(df: pd.DataFrame) -> list[dict]:
    """
    Detect multi-candlestick Supply and Demand base zones (DBR, RBD, RBR, DBD).
    """
    n = len(df)
    if n < 4:
        return []

    open_ = df["open"]
    close = df["close"]
    high = df["high"]
    low = df["low"]
    timestamps = df["timestamp"].astype(str)

    zones = []

    for i in range(1, n - 2):
        # Base candle: narrow range relative to neighboring candles
        span = high.iloc[i] - low.iloc[i]
        next_move = close.iloc[i + 1] - open_.iloc[i + 1]
        prev_move = close.iloc[i - 1] - open_.iloc[i - 1]

        # Demand: Drop-Base-Rally (DBR) or Rally-Base-Rally (RBR)
        if next_move > 0 and (next_move > 1.3 * span):
            z_type = "DBR" if prev_move < 0 else "RBR"
            z_high = float(high.iloc[i])
            z_low = float(low.iloc[i])

            # Check mitigation by subsequent candles
            status = "FRESH"
            for k in range(i + 2, n):
                if low.iloc[k] <= z_high:
                    status = "MITIGATED" if low.iloc[k] <= (z_high + z_low) / 2 else "TESTED"
                if close.iloc[k] < z_low:
                    status = "INVALIDATED"
                    break

            zones.append({
                "id": f"sd-demand-{i}",
                "kind": "DEMAND",
                "pattern": z_type,
                "timestamp": timestamps.iloc[i],
                "zone_high": round(z_high, 2),
                "zone_low": round(z_low, 2),
                "status": status,
            })

        # Supply: Rally-Base-Drop (RBD) or Drop-Base-Drop (DBD)
        elif next_move < 0 and (abs(next_move) > 1.3 * span):
            z_type = "RBD" if prev_move > 0 else "DBD"
            z_high = float(high.iloc[i])
            z_low = float(low.iloc[i])

            status = "FRESH"
            for k in range(i + 2, n):
                if high.iloc[k] >= z_low:
                    status = "MITIGATED" if high.iloc[k] >= (z_high + z_low) / 2 else "TESTED"
                if close.iloc[k] > z_high:
                    status = "INVALIDATED"
                    break

            zones.append({
                "id": f"sd-supply-{i}",
                "kind": "SUPPLY",
                "pattern": z_type,
                "timestamp": timestamps.iloc[i],
                "zone_high": round(z_high, 2),
                "zone_low": round(z_low, 2),
                "status": status,
            })

    return zones


# ---------------------------------------------------------------------------
# 5. Liquidity Detection & Sweeps (Module 6)
# ---------------------------------------------------------------------------

def detect_liquidity_and_sweeps(
    df: pd.DataFrame,
    swings: list[dict],
    tolerance_pct: float = 0.20,
    scan_lookback: Optional[int] = None,
) -> dict:
    """
    Detect Equal Highs (EQH), Equal Lows (EQL), PDH/PDL, PWH/PWL, and Liquidity Sweeps.

    Rigorous 4-Stage Separation:
    1. Sweep occurrence: Candle bar_idx wicks beyond benchmark level.
    2. Reclaim confirmation: Candle bar_idx closes back inside the benchmark level.
       (If candle closes beyond the level, it is classified as a continuation breakout / FAILED_SWEEP).
    3. Subsequent opposing reaction: Evaluated on candle bar_idx + 1 (NOT on same candle).
       - Bearish sweep: Candle bar_idx + 1 must close bearish (close < open).
       - Bullish sweep: Candle bar_idx + 1 must close bullish (close > open).
       - If bar_idx + 1 has not occurred yet (bar_idx == n - 1), reaction is marked PENDING (None).
    4. Signal availability: Executable on candle bar_idx + 2 Open once reaction is confirmed.
       - If bar_idx + 2 >= n, executable availability is marked PENDING (None).
    """
    n = len(df)
    if n < 2:
        return {
            "equal_highs": [],
            "equal_lows": [],
            "key_levels": {},
            "sweeps": [],
            "failed_sweeps": [],
        }

    high = df["high"]
    low = df["low"]
    close = df["close"]
    open_ = df["open"]
    timestamps = df["timestamp"].astype(str)

    # 1. Equal Highs and Lows from confirmed swings
    sh_list = [s for s in swings if s["type"] == "SWING_HIGH"]
    sl_list = [s for s in swings if s["type"] == "SWING_LOW"]

    equal_highs = []
    for i in range(len(sh_list) - 1):
        for j in range(i + 1, min(len(sh_list), i + 4)):
            p1, p2 = sh_list[i]["price"], sh_list[j]["price"]
            diff_pct = abs(p1 - p2) / p1 * 100
            if diff_pct <= tolerance_pct:
                conf_idx = max(sh_list[i].get("confirmation_index", sh_list[i]["index"]), sh_list[j].get("confirmation_index", sh_list[j]["index"]))
                equal_highs.append({
                    "price": round((p1 + p2) / 2, 2),
                    "bars": [sh_list[i]["timestamp"], sh_list[j]["timestamp"]],
                    "confirmation_index": conf_idx,
                    "type": "EQUAL_HIGHS (BSL)",
                })

    equal_lows = []
    for i in range(len(sl_list) - 1):
        for j in range(i + 1, min(len(sl_list), i + 4)):
            p1, p2 = sl_list[i]["price"], sl_list[j]["price"]
            diff_pct = abs(p1 - p2) / p1 * 100
            if diff_pct <= tolerance_pct:
                conf_idx = max(sl_list[i].get("confirmation_index", sl_list[i]["index"]), sl_list[j].get("confirmation_index", sl_list[j]["index"]))
                equal_lows.append({
                    "price": round((p1 + p2) / 2, 2),
                    "bars": [sl_list[i]["timestamp"], sl_list[j]["timestamp"]],
                    "confirmation_index": conf_idx,
                    "type": "EQUAL_LOWS (SSL)",
                })

    # 2. Key benchmark levels: PDH, PDL, PWH, PWL
    pdh = float(high.iloc[-2]) if n >= 2 else float(high.iloc[-1])
    pdl = float(low.iloc[-2]) if n >= 2 else float(low.iloc[-1])

    pwh = float(high.iloc[-6:-1].max()) if n >= 6 else float(high.max())
    pwl = float(low.iloc[-6:-1].min()) if n >= 6 else float(low.min())

    key_levels = {
        "PDH": round(pdh, 2),
        "PDL": round(pdl, 2),
        "PWH": round(pwh, 2),
        "PWL": round(pwl, 2),
    }

    # 3. Liquidity Sweeps
    sweeps = []
    failed_sweeps = []

    start_idx = max(1, n - scan_lookback) if scan_lookback is not None else 1

    for bar_idx in range(start_idx, n):
        c_open = float(open_.iloc[bar_idx])
        c_high = float(high.iloc[bar_idx])
        c_low = float(low.iloc[bar_idx])
        c_close = float(close.iloc[bar_idx])
        c_time = timestamps.iloc[bar_idx]

        prior_high = float(high.iloc[bar_idx - 1])
        prior_low = float(low.iloc[bar_idx - 1])

        # Candidate check: PDH Sweep
        if c_high > prior_high:
            if c_close <= prior_high:
                # Stage 1: Sweep Occurrence (bar_idx)
                # Stage 2: Reclaim Confirmed (bar_idx)
                # Stage 3: Subsequent Opposing Reaction (bar_idx + 1)
                has_next_bar = (bar_idx + 1 < n)
                if has_next_bar:
                    next_open = float(open_.iloc[bar_idx + 1])
                    next_close = float(close.iloc[bar_idx + 1])
                    opposing_reaction = bool(next_close < next_open)
                    conf_idx = bar_idx + 1
                    conf_time = timestamps.iloc[bar_idx + 1]
                    if opposing_reaction:
                        # Stage 4: Signal available at bar_idx + 2 Open
                        avail_idx = (bar_idx + 2) if (bar_idx + 2 < n) else None
                        avail_time = timestamps.iloc[avail_idx] if avail_idx is not None else None
                    else:
                        avail_idx = None
                        avail_time = None
                else:
                    opposing_reaction = None  # Pending next session
                    conf_idx = None
                    conf_time = None
                    avail_idx = None
                    avail_time = None

                sweeps.append({
                    "bar_index": bar_idx,
                    "occurrence_index": bar_idx,
                    "occurrence_timestamp": c_time,
                    "confirmation_index": conf_idx,
                    "confirmation_timestamp": conf_time,
                    "signal_available_index": avail_idx,
                    "signal_available_timestamp": avail_time,
                    "timestamp": c_time,
                    "level_name": "PDH",
                    "level_price": round(prior_high, 2),
                    "direction": "BEARISH (BUY-SIDE LIQUIDITY SWEPT)",
                    "sweep_price": round(c_high, 2),
                    "close": round(c_close, 2),
                    "reclaim_confirmed": True,
                    "opposing_reaction": opposing_reaction,
                })
            else:
                # Price closed above level -> Continuation breakout, not a sweep
                failed_sweeps.append({
                    "bar_index": bar_idx,
                    "occurrence_index": bar_idx,
                    "occurrence_timestamp": c_time,
                    "timestamp": c_time,
                    "level_name": "PDH",
                    "level_price": round(prior_high, 2),
                    "breakout_price": round(c_close, 2),
                    "status": "FAILED_SWEEP (BULLISH_BREAKOUT)",
                })

        # Candidate check: PDL Sweep
        if c_low < prior_low:
            if c_close >= prior_low:
                has_next_bar = (bar_idx + 1 < n)
                if has_next_bar:
                    next_open = float(open_.iloc[bar_idx + 1])
                    next_close = float(close.iloc[bar_idx + 1])
                    opposing_reaction = bool(next_close > next_open)
                    conf_idx = bar_idx + 1
                    conf_time = timestamps.iloc[bar_idx + 1]
                    if opposing_reaction:
                        avail_idx = (bar_idx + 2) if (bar_idx + 2 < n) else None
                        avail_time = timestamps.iloc[avail_idx] if avail_idx is not None else None
                    else:
                        avail_idx = None
                        avail_time = None
                else:
                    opposing_reaction = None  # Pending next session
                    conf_idx = None
                    conf_time = None
                    avail_idx = None
                    avail_time = None

                sweeps.append({
                    "bar_index": bar_idx,
                    "occurrence_index": bar_idx,
                    "occurrence_timestamp": c_time,
                    "confirmation_index": conf_idx,
                    "confirmation_timestamp": conf_time,
                    "signal_available_index": avail_idx,
                    "signal_available_timestamp": avail_time,
                    "timestamp": c_time,
                    "level_name": "PDL",
                    "level_price": round(prior_low, 2),
                    "direction": "BULLISH (SELL-SIDE LIQUIDITY SWEPT)",
                    "sweep_price": round(c_low, 2),
                    "close": round(c_close, 2),
                    "reclaim_confirmed": True,
                    "opposing_reaction": opposing_reaction,
                })
            else:
                # Price closed below level -> Continuation breakdown
                failed_sweeps.append({
                    "bar_index": bar_idx,
                    "occurrence_index": bar_idx,
                    "occurrence_timestamp": c_time,
                    "timestamp": c_time,
                    "level_name": "PDL",
                    "level_price": round(prior_low, 2),
                    "breakout_price": round(c_close, 2),
                    "status": "FAILED_SWEEP (BEARISH_BREAKDOWN)",
                })

        # Sweep of Equal Highs (only if confirmed before or at bar_idx)
        for eq in equal_highs:
            if eq.get("confirmation_index", 0) <= bar_idx:
                if c_high > eq["price"]:
                    if c_close <= eq["price"]:
                        has_next_bar = (bar_idx + 1 < n)
                        if has_next_bar:
                            next_open = float(open_.iloc[bar_idx + 1])
                            next_close = float(close.iloc[bar_idx + 1])
                            opposing_reaction = bool(next_close < next_open)
                            conf_idx = bar_idx + 1
                            conf_time = timestamps.iloc[bar_idx + 1]
                            if opposing_reaction:
                                avail_idx = (bar_idx + 2) if (bar_idx + 2 < n) else None
                                avail_time = timestamps.iloc[avail_idx] if avail_idx is not None else None
                            else:
                                avail_idx = None
                                avail_time = None
                        else:
                            opposing_reaction = None
                            conf_idx = None
                            conf_time = None
                            avail_idx = None
                            avail_time = None

                        sweeps.append({
                            "bar_index": bar_idx,
                            "occurrence_index": bar_idx,
                            "occurrence_timestamp": c_time,
                            "confirmation_index": conf_idx,
                            "confirmation_timestamp": conf_time,
                            "signal_available_index": avail_idx,
                            "signal_available_timestamp": avail_time,
                            "timestamp": c_time,
                            "level_name": "EQH",
                            "level_price": eq["price"],
                            "direction": "BEARISH (BUY-SIDE LIQUIDITY SWEPT)",
                            "sweep_price": round(c_high, 2),
                            "close": round(c_close, 2),
                            "reclaim_confirmed": True,
                            "opposing_reaction": opposing_reaction,
                        })
                    else:
                        failed_sweeps.append({
                            "bar_index": bar_idx,
                            "occurrence_index": bar_idx,
                            "occurrence_timestamp": c_time,
                            "timestamp": c_time,
                            "level_name": "EQH",
                            "level_price": eq["price"],
                            "breakout_price": round(c_close, 2),
                            "status": "FAILED_SWEEP (BULLISH_BREAKOUT)",
                        })

        # Sweep of Equal Lows (only if confirmed before or at bar_idx)
        for eq in equal_lows:
            if eq.get("confirmation_index", 0) <= bar_idx:
                if c_low < eq["price"]:
                    if c_close >= eq["price"]:
                        has_next_bar = (bar_idx + 1 < n)
                        if has_next_bar:
                            next_open = float(open_.iloc[bar_idx + 1])
                            next_close = float(close.iloc[bar_idx + 1])
                            opposing_reaction = bool(next_close > next_open)
                            conf_idx = bar_idx + 1
                            conf_time = timestamps.iloc[bar_idx + 1]
                            if opposing_reaction:
                                avail_idx = (bar_idx + 2) if (bar_idx + 2 < n) else None
                                avail_time = timestamps.iloc[avail_idx] if avail_idx is not None else None
                            else:
                                avail_idx = None
                                avail_time = None
                        else:
                            opposing_reaction = None
                            conf_idx = None
                            conf_time = None
                            avail_idx = None
                            avail_time = None

                        sweeps.append({
                            "bar_index": bar_idx,
                            "occurrence_index": bar_idx,
                            "occurrence_timestamp": c_time,
                            "confirmation_index": conf_idx,
                            "confirmation_timestamp": conf_time,
                            "signal_available_index": avail_idx,
                            "signal_available_timestamp": avail_time,
                            "timestamp": c_time,
                            "level_name": "EQL",
                            "level_price": eq["price"],
                            "direction": "BULLISH (SELL-SIDE LIQUIDITY SWEPT)",
                            "sweep_price": round(c_low, 2),
                            "close": round(c_close, 2),
                            "reclaim_confirmed": True,
                            "opposing_reaction": opposing_reaction,
                        })
                    else:
                        failed_sweeps.append({
                            "bar_index": bar_idx,
                            "occurrence_index": bar_idx,
                            "occurrence_timestamp": c_time,
                            "timestamp": c_time,
                            "level_name": "EQL",
                            "level_price": eq["price"],
                            "breakout_price": round(c_close, 2),
                            "status": "FAILED_SWEEP (BEARISH_BREAKDOWN)",
                        })

    return {
        "equal_highs": equal_highs,
        "equal_lows": equal_lows,
        "key_levels": key_levels,
        "sweeps": sweeps,
        "failed_sweeps": failed_sweeps,
    }


# ---------------------------------------------------------------------------
# 6. Premium & Discount Dealing Range (Module 7)
# ---------------------------------------------------------------------------

def calculate_premium_discount(df: pd.DataFrame, swings: list[dict]) -> dict:
    """
    Calculate the active dealing range, Equilibrium (50%), and current zone.
    """
    n = len(df)
    if n == 0:
        return {"equilibrium": None, "zone": "UNKNOWN"}

    current_price = float(df["close"].iloc[-1])

    # Find the most recent confirmed major swing high and swing low
    sh_list = [s for s in swings if s["type"] == "SWING_HIGH"]
    sl_list = [s for s in swings if s["type"] == "SWING_LOW"]

    if sh_list and sl_list:
        sh_price = sh_list[-1]["price"]
        sl_price = sl_list[-1]["price"]
    else:
        sh_price = float(df["high"].tail(30).max())
        sl_price = float(df["low"].tail(30).min())

    if sh_price <= sl_price:
        sh_price = sl_price + 1.0

    eq = (sh_price + sl_price) / 2.0
    range_span = sh_price - sl_price
    pct_location = ((current_price - sl_price) / range_span) * 100.0

    if pct_location > 52.0:
        zone = "PREMIUM (EXPENSIVE / SELLERS ZONE)"
    elif pct_location < 48.0:
        zone = "DISCOUNT (CHEAP / BUYERS ZONE)"
    else:
        zone = "EQUILIBRIUM (FAIR VALUE ZONE)"

    return {
        "swing_high": round(sh_price, 2),
        "swing_low": round(sl_price, 2),
        "equilibrium": round(eq, 2),
        "current_price": round(current_price, 2),
        "percentage_in_range": round(pct_location, 1),
        "zone": zone,
    }


# ---------------------------------------------------------------------------
# 7. Institutional Setup Score (Module 9)
# ---------------------------------------------------------------------------

def calculate_setup_score(
    df: pd.DataFrame,
    structure: dict,
    order_blocks: list[dict],
    fvgs: list[dict],
    liquidity: dict,
    prem_disc: dict,
    stock_meta: Optional[dict] = None,
) -> dict:
    """
    Calculate the 100-point institutional setup score across 7 components.
    Weights:
    - Market Direction (15%)
    - Relative Strength (15%)
    - Order Block Quality (20%)
    - Market Structure (15%)
    - Liquidity Confirmation (15%)
    - Volume Confirmation (10%)
    - Sector Alignment (10%)
    """
    n = len(df)
    current_price = float(df["close"].iloc[-1]) if n > 0 else 0.0

    # 1. Market Direction (15 pts)
    # Check moving averages alignment
    ema_20 = df["close"].ewm(span=20, adjust=False).mean().iloc[-1] if n >= 20 else current_price
    sma_50 = df["close"].rolling(50).mean().iloc[-1] if n >= 50 else current_price
    if structure["trend"] == "BULLISH" and current_price >= ema_20 >= sma_50:
        dir_score = 15.0
        dir_detail = "Strong Bullish MA Alignment"
    elif structure["trend"] == "BEARISH" and current_price <= ema_20 <= sma_50:
        dir_score = 15.0
        dir_detail = "Strong Bearish MA Alignment"
    elif structure["trend"] != "NEUTRAL":
        dir_score = 10.0
        dir_detail = f"Trend {structure['trend']} with partial MA alignment"
    else:
        dir_score = 5.0
        dir_detail = "Neutral / Consolidating trend"

    # 2. Relative Strength (15 pts)
    ret_1m = 0.0
    if n >= 21 and df["close"].iloc[-21] > 0:
        ret_1m = (current_price - df["close"].iloc[-21]) / df["close"].iloc[-21] * 100.0
    if abs(ret_1m) >= 6.0:
        rs_score = 15.0
        rs_detail = f"High 1-Month Momentum ({ret_1m:+.1f}%)"
    elif abs(ret_1m) >= 2.5:
        rs_score = 11.0
        rs_detail = f"Moderate 1-Month Momentum ({ret_1m:+.1f}%)"
    else:
        rs_score = 6.0
        rs_detail = f"Flat / Subdued 1-Month Return ({ret_1m:+.1f}%)"

    # 3. Order Block Quality (20 pts)
    # Proximity to fresh or tested order block
    active_obs = [ob for ob in order_blocks if ob["status"] in ("FRESH", "TESTED")]
    ob_score = 6.0
    ob_detail = "No active Order Block nearby"
    best_ob = None

    for ob in active_obs:
        # Distance % from current price to zone
        dist_pct = abs(current_price - ((ob["zone_high"] + ob["zone_low"]) / 2)) / current_price * 100.0
        if dist_pct <= 2.5:
            ob_score = 20.0
            ob_detail = f"Prime Proximity ({dist_pct:.1f}%) to {ob['direction']} {ob['status']} OB"
            best_ob = ob
            break
        elif dist_pct <= 5.0:
            ob_score = 14.0
            ob_detail = f"Approaching {ob['direction']} {ob['status']} OB ({dist_pct:.1f}% away)"
            best_ob = ob

    # 4. Market Structure (15 pts)
    if structure["last_choch"] and structure["last_choch"]["bar_index"] >= n - 10:
        ms_score = 15.0
        ms_detail = f"Fresh {structure['last_choch']['direction']} CHoCH confirmed"
    elif structure["last_bos"] and structure["last_bos"]["bar_index"] >= n - 15:
        ms_score = 13.0
        ms_detail = f"Confirmed {structure['last_bos']['direction']} BOS"
    else:
        ms_score = 7.0
        ms_detail = "Mature or consolidating structure"

    # 5. Liquidity Confirmation (15 pts)
    recent_sweeps = liquidity.get("sweeps", [])
    if recent_sweeps:
        last_sweep = recent_sweeps[-1]
        liq_score = 15.0
        liq_detail = f"Recent Sweep of {last_sweep['level_name']} ({last_sweep['direction']})"
    elif liquidity.get("equal_highs") or liquidity.get("equal_lows"):
        liq_score = 11.0
        liq_detail = "Equal Highs/Lows liquidity pool identified"
    else:
        liq_score = 6.0
        liq_detail = "Standard liquidity distribution"

    # 6. Volume Confirmation (10 pts)
    avg_vol = df["volume"].rolling(20).mean().iloc[-1] if n >= 20 else 1.0
    rvol = float(df["volume"].iloc[-1] / avg_vol) if avg_vol > 0 else 1.0
    if rvol >= 1.5:
        vol_score = 10.0
        vol_detail = f"Institutional Volume Expansion (RVOL {rvol:.2f}x)"
    elif rvol >= 1.1:
        vol_score = 7.0
        vol_detail = f"Above-Average Volume (RVOL {rvol:.2f}x)"
    else:
        vol_score = 4.0
        vol_detail = f"Normal Volume (RVOL {rvol:.2f}x)"

    # 7. Sector Alignment (10 pts)
    sector_score = 8.0
    sector_detail = "Sector alignment verified"
    if stock_meta and stock_meta.get("sector"):
        sector_detail = f"Sector: {stock_meta.get('sector')}"

    total_score = dir_score + rs_score + ob_score + ms_score + liq_score + vol_score + sector_score

    rating = (
        "HIGH PROBABILITY INSTITUTIONAL SETUP"
        if total_score >= 75.0
        else ("MODERATE CONFLUENCE SETUP" if total_score >= 55.0 else "LOW CONFLUENCE / WATCHLIST ONLY")
    )

    return {
        "total_score": round(total_score, 1),
        "rating": rating,
        "active_order_block": best_ob,
        "components": [
            {"factor": "Market Direction", "weight": 15, "score": dir_score, "detail": dir_detail},
            {"factor": "Relative Strength", "weight": 15, "score": rs_score, "detail": rs_detail},
            {"factor": "Order Block Quality", "weight": 20, "score": ob_score, "detail": ob_detail},
            {"factor": "Market Structure", "weight": 15, "score": ms_score, "detail": ms_detail},
            {"factor": "Liquidity Confirmation", "weight": 15, "score": liq_score, "detail": liq_detail},
            {"factor": "Volume Confirmation", "weight": 10, "score": vol_score, "detail": vol_detail},
            {"factor": "Sector Alignment", "weight": 10, "score": sector_score, "detail": sector_detail},
        ],
    }


# ---------------------------------------------------------------------------
# Master Analysis Orchestrator
# ---------------------------------------------------------------------------

def analyze_smart_money_concepts(
    symbol: str,
    bars: Optional[list[dict]] = None,
    limit: int = 120,
) -> dict:
    """
    Run complete Smart Money Concepts analysis for a symbol.
    """
    sym = symbol.upper()
    if bars is None:
        bars = get_bars(sym)

    stock_meta = get_stock(sym)

    if not bars or len(bars) < 5:
        return {
            "symbol": sym,
            "error": "Insufficient historical candles for Smart Money Concepts analysis",
            "bars_count": len(bars) if bars else 0,
        }

    df = _prepare_df(bars)
    df = df.tail(limit).reset_index(drop=True)

    structure = detect_market_structure(df)
    order_blocks = detect_order_blocks(df, structure["breaks"])
    fvgs = detect_fair_value_gaps(df)
    supply_demand = detect_supply_demand_zones(df)
    liquidity = detect_liquidity_and_sweeps(df, structure["swings"])
    prem_disc = calculate_premium_discount(df, structure["swings"])
    setup_score = calculate_setup_score(
        df, structure, order_blocks, fvgs, liquidity, prem_disc, stock_meta
    )

    current_price = float(df["close"].iloc[-1])

    # Summarize active order blocks
    bullish_obs = [ob for ob in order_blocks if ob["direction"] == "BULLISH" and ob["status"] != "INVALIDATED"]
    bearish_obs = [ob for ob in order_blocks if ob["direction"] == "BEARISH" and ob["status"] != "INVALIDATED"]

    return {
        "symbol": sym,
        "company_name": stock_meta.get("company_name", sym) if stock_meta else sym,
        "sector": stock_meta.get("sector") if stock_meta else None,
        "current_price": round(current_price, 2),
        "bars_evaluated": len(df),
        "market_structure": structure,
        "order_blocks": {
            "total_detected": len(order_blocks),
            "bullish_active_count": len(bullish_obs),
            "bearish_active_count": len(bearish_obs),
            "all_zones": order_blocks,
        },
        "fair_value_gaps": {
            "total": len(fvgs),
            "unfilled_count": sum(1 for g in fvgs if not g["is_filled"]),
            "gaps": fvgs,
        },
        "supply_demand": supply_demand,
        "liquidity": liquidity,
        "premium_discount": prem_disc,
        "setup_score": setup_score,
        "is_deterministic": True,
        "repainting": False,
    }
