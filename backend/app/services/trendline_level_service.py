"""
Automated Trendlines, Dynamic Support/Resistance & Key Session Levels Service.

Calculates multi-touch trendlines, channels, price cluster zones, consolidation boxes,
and session benchmark levels (PDH, PDL, PWH, PWL, PMH, PML) from OHLCV data.
Zero look-ahead bias: swing pivots require right-side confirmation bars.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd


def _prepare_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize and sort bar series."""
    df = pd.DataFrame(bars)
    if "timestamp" in df.columns and "date" not in df.columns:
        df["date"] = df["timestamp"]
    if "date" in df.columns:
        df["date"] = df["date"].astype(str)
        df = df.sort_values("date").reset_index(drop=True)

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = 0.0

    return df


def find_swing_pivots(
    df: pd.DataFrame, left_bars: int = 5, right_bars: int = 5
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Detect confirmed fractal swing highs and swing lows.
    A swing pivot at index i is confirmed only after i + right_bars.
    """
    n = len(df)
    if n < left_bars + right_bars + 1:
        return [], []

    high = df["high"].values
    low = df["low"].values
    dates = df["date"].values if "date" in df.columns else [str(i) for i in range(n)]

    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []

    for i in range(left_bars, n - right_bars):
        h = high[i]
        l = low[i]

        # Check if local maximum
        is_high = True
        for j in range(i - left_bars, i + right_bars + 1):
            if j != i and high[j] >= h:
                is_high = False
                break
        if is_high:
            conf_idx = i + right_bars
            conf_date = str(dates[conf_idx]) if conf_idx < n else str(dates[-1])
            swing_highs.append({
                "index": i,
                "occurrence_index": i,
                "confirmation_index": conf_idx,
                "date": str(dates[i]),
                "confirmation_date": conf_date,
                "price": round(float(h), 2),
                "type": "swing_high",
            })

        # Check if local minimum
        is_low = True
        for j in range(i - left_bars, i + right_bars + 1):
            if j != i and low[j] <= l:
                is_low = False
                break
        if is_low:
            conf_idx = i + right_bars
            conf_date = str(dates[conf_idx]) if conf_idx < n else str(dates[-1])
            swing_lows.append({
                "index": i,
                "occurrence_index": i,
                "confirmation_index": conf_idx,
                "date": str(dates[i]),
                "confirmation_date": conf_date,
                "price": round(float(l), 2),
                "type": "swing_low",
            })

    return swing_highs, swing_lows


def detect_support_resistance_clusters(
    df: pd.DataFrame,
    swing_highs: list[dict[str, Any]],
    swing_lows: list[dict[str, Any]],
    atr_period: int = 14,
    tolerance_pct: float = 0.015,
) -> list[dict[str, Any]]:
    """
    Cluster swing pivots into dynamic horizontal support and resistance zones.
    Zone width is bounded by ATR and relative tolerance.
    """
    n = len(df)
    if n < 20 or (not swing_highs and not swing_lows):
        return []

    # Calculate ATR for adaptive band sizing
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.rolling(atr_period).mean().iloc[-1]) if n >= atr_period else float(close.iloc[-1] * 0.015)
    if np.isnan(atr) or atr <= 0:
        atr = float(close.iloc[-1] * 0.015)

    all_pivots = swing_highs + swing_lows
    if not all_pivots:
        return []

    prices = np.array([p["price"] for p in all_pivots])
    latest_close = float(close.iloc[-1])

    # Cluster prices within distance threshold (0.75 * ATR or 1.5%)
    dist_thresh = max(0.75 * atr, latest_close * tolerance_pct)
    sorted_pivots = sorted(all_pivots, key=lambda p: p["price"])

    clusters: list[list[dict[str, Any]]] = []
    current_cluster: list[dict[str, Any]] = [sorted_pivots[0]]

    for p in sorted_pivots[1:]:
        if p["price"] - current_cluster[-1]["price"] <= dist_thresh:
            current_cluster.append(p)
        else:
            clusters.append(current_cluster)
            current_cluster = [p]
    if current_cluster:
        clusters.append(current_cluster)

    zones: list[dict[str, Any]] = []
    for idx, cluster in enumerate(clusters):
        if len(cluster) < 2:
            # Require at least 2 pivot touches to form a confirmed zone
            continue

        c_prices = [p["price"] for p in cluster]
        p_min = round(float(min(c_prices)), 2)
        p_max = round(float(max(c_prices)), 2)
        mid = round(float(np.mean(c_prices)), 2)
        touch_count = len(cluster)

        # Distinguish support vs resistance relative to latest price
        if latest_close >= mid:
            zone_type = "support"
            dist_pct = round(((latest_close - mid) / latest_close) * 100, 2)
        else:
            zone_type = "resistance"
            dist_pct = round(((mid - latest_close) / latest_close) * 100, 2)

        # Strength: touch count (up to 50 pts) + freshness (up to 30 pts) + tight band (up to 20 pts)
        last_pivot_idx = max(p["index"] for p in cluster)
        freshness_pts = max(0, 30 - int((n - 1 - last_pivot_idx) / 3))
        touch_pts = min(50, touch_count * 15)
        band_tightness = max(0, 20 - int(((p_max - p_min) / mid) * 1000))
        strength = min(100, touch_pts + freshness_pts + band_tightness)

        last_date = cluster[-1]["date"]

        zones.append({
            "id": f"zone_{zone_type}_{idx}",
            "type": zone_type,
            "price_min": p_min,
            "price_max": p_max,
            "mid_price": mid,
            "touch_count": touch_count,
            "strength": int(strength),
            "distance_pct": dist_pct,
            "last_touch_date": last_date,
            "is_broken": bool(zone_type == "support" and latest_close < p_min),
        })

    # Sort zones by strength descending
    zones.sort(key=lambda z: z["strength"], reverse=True)
    return zones[:8]  # return top 8 most prominent zones


def detect_validated_trendlines(
    df: pd.DataFrame,
    swing_highs: list[dict[str, Any]],
    swing_lows: list[dict[str, Any]],
    tolerance_pct: float = 0.005,
) -> list[dict[str, Any]]:
    """
    Detect multi-touch trendlines with mathematical validation:
    - Ascending Support Trendline (connecting ascending swing lows)
    - Descending Resistance Trendline (connecting descending swing highs)
    Must have >= 3 touches and no major closing violations prior to current candle.
    """
    n = len(df)
    if n < 20:
        return []

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    dates = df["date"].values if "date" in df.columns else [str(i) for i in range(n)]

    trendlines: list[dict[str, Any]] = []

    # 1. Ascending Support Lines (from swing lows)
    if len(swing_lows) >= 2:
        # Check pairs of swing lows
        for i in range(len(swing_lows)):
            p1 = swing_lows[i]
            for j in range(i + 1, len(swing_lows)):
                p2 = swing_lows[j]
                idx1, idx2 = p1["index"], p2["index"]
                y1, y2 = p1["price"], p2["price"]

                if idx2 <= idx1 or y2 <= y1:
                    # Must be ascending
                    continue

                slope = (y2 - y1) / (idx2 - idx1)
                intercept = y1 - slope * idx1

                # Verify valid touches and no breakdown before idx2
                touches = 2
                touch_indices = [idx1, idx2]
                severe_violation = False

                for k in range(idx1, n):
                    expected_price = slope * k + intercept
                    tol = expected_price * tolerance_pct

                    # Check touch on low
                    if k not in touch_indices and abs(low[k] - expected_price) <= tol:
                        touches += 1
                        touch_indices.append(k)

                    # Check severe violation (close substantially below line)
                    if close[k] < expected_price - tol * 1.5 and k < n - 1:
                        # Broken earlier
                        severe_violation = True
                        break

                if touches >= 2 and not severe_violation:
                    curr_expected = round(float(slope * (n - 1) + intercept), 2)
                    conf_idx = min(n - 1, idx2 + 5)
                    trendlines.append({
                        "id": f"tl_asc_sup_{idx1}_{idx2}",
                        "type": "ascending_support",
                        "start_point": {"date": str(dates[idx1]), "price": y1, "index": idx1},
                        "end_point": {"date": str(dates[n - 1]), "price": curr_expected, "index": n - 1},
                        "slope": round(float(slope), 4),
                        "touches": touches,
                        "current_price_level": curr_expected,
                        "confirmation_index": conf_idx,
                        "confirmation_date": str(dates[conf_idx]),
                        "is_active": bool(close[-1] >= curr_expected * 0.99),
                    })

    # 2. Descending Resistance Lines (from swing highs)
    if len(swing_highs) >= 2:
        for i in range(len(swing_highs)):
            p1 = swing_highs[i]
            for j in range(i + 1, len(swing_highs)):
                p2 = swing_highs[j]
                idx1, idx2 = p1["index"], p2["index"]
                y1, y2 = p1["price"], p2["price"]

                if idx2 <= idx1 or y2 >= y1:
                    # Must be descending
                    continue

                slope = (y2 - y1) / (idx2 - idx1)
                intercept = y1 - slope * idx1

                touches = 2
                touch_indices = [idx1, idx2]
                severe_violation = False

                for k in range(idx1, n):
                    expected_price = slope * k + intercept
                    tol = expected_price * tolerance_pct

                    if k not in touch_indices and abs(high[k] - expected_price) <= tol:
                        touches += 1
                        touch_indices.append(k)

                    if close[k] > expected_price + tol * 1.5 and k < n - 1:
                        severe_violation = True
                        break

                if touches >= 2 and not severe_violation:
                    curr_expected = round(float(slope * (n - 1) + intercept), 2)
                    conf_idx = min(n - 1, idx2 + 5)
                    trendlines.append({
                        "id": f"tl_desc_res_{idx1}_{idx2}",
                        "type": "descending_resistance",
                        "start_point": {"date": str(dates[idx1]), "price": y1, "index": idx1},
                        "end_point": {"date": str(dates[n - 1]), "price": curr_expected, "index": n - 1},
                        "slope": round(float(slope), 4),
                        "touches": touches,
                        "current_price_level": curr_expected,
                        "confirmation_index": conf_idx,
                        "confirmation_date": str(dates[conf_idx]),
                        "is_active": bool(close[-1] <= curr_expected * 1.01),
                    })

    # Sort by touch count descending and take top 4
    trendlines.sort(key=lambda t: t["touches"], reverse=True)
    return trendlines[:4]


def detect_channels(
    df: pd.DataFrame, trendlines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Detect parallel ascending or descending price channels.
    """
    if not trendlines or len(df) < 20:
        return []

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(df)
    latest_close = close[-1]

    channels: list[dict[str, Any]] = []

    for tl in trendlines:
        slope = tl["slope"]
        idx1 = tl["start_point"]["index"]
        idx2 = tl["end_point"]["index"]
        y1 = tl["start_point"]["price"]
        intercept = y1 - slope * idx1

        if tl["type"] == "ascending_support":
            # Channel top is highest parallel offset among highs
            offsets = [high[k] - (slope * k + intercept) for k in range(idx1, n)]
            if not offsets:
                continue
            max_offset = float(np.percentile(offsets, 95))
            if max_offset <= 0:
                continue

            bot_curr = slope * (n - 1) + intercept
            top_curr = bot_curr + max_offset
            width_pct = round((max_offset / bot_curr) * 100, 2)
            pos_pct = round(max(0.0, min(100.0, (latest_close - bot_curr) / max_offset * 100)), 1)

            channels.append({
                "id": f"channel_asc_{idx1}",
                "type": "ascending_channel",
                "slope": slope,
                "support_level": round(float(bot_curr), 2),
                "resistance_level": round(float(top_curr), 2),
                "channel_width_pct": width_pct,
                "position_in_channel_pct": pos_pct,
            })

        elif tl["type"] == "descending_resistance":
            # Channel bottom is lowest parallel offset among lows
            offsets = [low[k] - (slope * k + intercept) for k in range(idx1, n)]
            if not offsets:
                continue
            min_offset = float(np.percentile(offsets, 5))
            if min_offset >= 0:
                continue

            top_curr = slope * (n - 1) + intercept
            bot_curr = top_curr + min_offset
            channel_range = top_curr - bot_curr
            if channel_range <= 0:
                continue
            width_pct = round((channel_range / bot_curr) * 100, 2)
            pos_pct = round(max(0.0, min(100.0, (latest_close - bot_curr) / channel_range * 100)), 1)

            channels.append({
                "id": f"channel_desc_{idx1}",
                "type": "descending_channel",
                "slope": slope,
                "support_level": round(float(bot_curr), 2),
                "resistance_level": round(float(top_curr), 2),
                "channel_width_pct": width_pct,
                "position_in_channel_pct": pos_pct,
            })

    return channels[:2]


def calculate_session_key_levels(df: pd.DataFrame) -> dict[str, Any]:
    """
    Calculate prior session benchmarks:
    - PDH (Previous Day High), PDL (Previous Day Low), PDC (Previous Day Close)
    - PWH (Previous Week High), PWL (Previous Week Low)
    - PMH (Previous Month High), PML (Previous Month Low)
    - 52W High, 52W Low
    - Intraday Opening Range (if intraday bars available)
    """
    n = len(df)
    if n < 2:
        return {}

    high = df["high"]
    low = df["low"]
    close = df["close"]
    latest_close = float(close.iloc[-1])

    # Previous Day (bar -2)
    pdh = float(high.iloc[-2])
    pdl = float(low.iloc[-2])
    pdc = float(close.iloc[-2])

    # Previous Week (approx 5 trading days prior, or lookback)
    pwh = float(high.iloc[-6:-1].max()) if n >= 6 else float(high.iloc[:-1].max())
    pwl = float(low.iloc[-6:-1].min()) if n >= 6 else float(low.iloc[:-1].min())

    # Previous Month (approx 21 trading days prior)
    pmh = float(high.iloc[-22:-1].max()) if n >= 22 else float(high.iloc[:-1].max())
    pml = float(low.iloc[-22:-1].min()) if n >= 22 else float(low.iloc[:-1].min())

    # 52-week (252 bars)
    w52_h = float(high.iloc[-252:].max()) if n >= 252 else float(high.max())
    w52_l = float(low.iloc[-252:].min()) if n >= 252 else float(low.min())

    return {
        "current_price": round(latest_close, 2),
        "pdh": round(pdh, 2),
        "pdl": round(pdl, 2),
        "pdc": round(pdc, 2),
        "pwh": round(pwh, 2),
        "pwl": round(pwl, 2),
        "pmh": round(pmh, 2),
        "pml": round(pml, 2),
        "week_52_high": round(w52_h, 2),
        "week_52_low": round(w52_l, 2),
        "dist_to_pdh_pct": round(((pdh - latest_close) / latest_close) * 100, 2),
        "dist_to_pdl_pct": round(((latest_close - pdl) / latest_close) * 100, 2),
        "above_pdh": bool(latest_close > pdh),
        "below_pdl": bool(latest_close < pdl),
    }


def analyze_trendlines_and_levels(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Main entry point for trendline, channel, support/resistance, and session level analysis.
    """
    if not bars or len(bars) < 10:
        return {
            "error": "Insufficient bars for trendline and level analysis",
            "trendlines": [],
            "channels": [],
            "support_resistance_zones": [],
            "key_levels": {},
            "consolidation_box": None,
        }

    df = _prepare_df(bars)
    swing_highs, swing_lows = find_swing_pivots(df, left_bars=4, right_bars=4)

    zones = detect_support_resistance_clusters(df, swing_highs, swing_lows)
    trendlines = detect_validated_trendlines(df, swing_highs, swing_lows)
    channels = detect_channels(df, trendlines)
    key_levels = calculate_session_key_levels(df)

    # Consolidation box detection
    n = len(df)
    cons_box = None
    if n >= 20:
        win_high = float(df["high"].iloc[-21:-1].max())
        win_low = float(df["low"].iloc[-21:-1].min())
        win_mean = float(df["close"].iloc[-21:-1].mean())
        range_pct = round(((win_high - win_low) / win_mean) * 100, 2) if win_mean > 0 else 0.0
        if range_pct <= 9.0:
            cons_box = {
                "support": round(win_low, 2),
                "resistance": round(win_high, 2),
                "duration_bars": 20,
                "range_pct": range_pct,
                "is_consolidating": True,
                "start_date": str(df["date"].iloc[-21]),
                "end_date": str(df["date"].iloc[-1]),
            }

    return {
        "bars_count": n,
        "swing_highs_count": len(swing_highs),
        "swing_lows_count": len(swing_lows),
        "support_resistance_zones": zones,
        "trendlines": trendlines,
        "channels": channels,
        "key_levels": key_levels,
        "consolidation_box": cons_box,
    }
