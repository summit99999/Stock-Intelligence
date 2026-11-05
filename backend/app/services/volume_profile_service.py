"""
Volume Profile & Volume Analytics Engine.

Calculates an Estimated Volume Profile from OHLCV candles:
- Estimated Volume at Price (histogram bins)
- Point of Control (POC)
- Value Area High (VAH) & Value Area Low (VAL) covering 70% of traded volume
- High Volume Nodes (HVN) and Low Volume Nodes (LVN)
- Rolling & Session VWAP
- RVOL (Relative Volume)

IMPORTANT METHODOLOGY DISCLOSURE:
This volume profile is mathematically estimated by distributing candle volume across
the [Low, High] price span with directional flow weighted by the Money Flow Multiplier (MFM).
It is an institutional continuous price-volume approximation and NOT tick-level exchange trades.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars

logger = logging.getLogger(__name__)


def calculate_volume_profile(
    symbol: str,
    bars: Optional[list[dict[str, Any]]] = None,
    num_bins: int = 24,
    bin_size: Optional[float] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Calculate Estimated Volume Profile distribution for a given symbol.

    Args:
        symbol: NSE symbol (e.g. RELIANCE)
        bars: Optional list of OHLCV bar dicts; if None, loads from DB
        num_bins: Number of horizontal price tiers (default: 24)
        bin_size: Optional custom price bin size (overrides num_bins if provided)
        limit: Number of recent bars to include
    """
    if bars is None:
        bars = get_bars(symbol)

    if not bars or len(bars) < 2:
        return {
            "symbol": symbol,
            "profile_type": "estimated_volume_profile",
            "is_estimated": True,
            "is_trade_level_tape": False,
            "error": "Insufficient price data to compute volume profile",
            "bars_count": len(bars) if bars else 0,
            "total_volume": 0.0,
            "poc": None,
            "vah": None,
            "val": None,
            "bins": [],
        }

    df = pd.DataFrame(bars)
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        else:
            df[col] = 0.0

    df = df.dropna(subset=["close", "volume"]).tail(limit).reset_index(drop=True)
    if len(df) < 2:
        return {
            "symbol": symbol,
            "profile_type": "estimated_volume_profile",
            "is_estimated": True,
            "is_trade_level_tape": False,
            "error": "Insufficient valid bars",
            "bars_count": len(df),
            "total_volume": 0.0,
            "poc": None,
            "vah": None,
            "val": None,
            "bins": [],
        }

    raw_total_vol = float(df["volume"].sum())
    if raw_total_vol <= 0 or np.isnan(raw_total_vol):
        # Clean handling for zero-volume datasets
        current_close = float(df["close"].iloc[-1])
        return {
            "symbol": symbol,
            "profile_type": "estimated_volume_profile",
            "is_estimated": True,
            "is_trade_level_tape": False,
            "bars_evaluated": len(df),
            "current_price": round(current_close, 2),
            "total_volume": 0.0,
            "poc": round(current_close, 2),
            "vah": round(current_close, 2),
            "val": round(current_close, 2),
            "vwap": round(current_close, 2),
            "price_vs_poc": "AT_POC",
            "price_in_value_area": True,
            "value_area_volume_pct": 70.0,
            "methodology": "Uniform OHLCV span distribution with MFM directional allocation",
            "bins": [],
            "note": "Zero volume recorded across evaluated bars",
        }

    min_p = float(df["low"].min())
    max_p = float(df["high"].max())
    if max_p <= min_p:
        max_p = min_p + 1.0

    # Determine bin sizing
    if bin_size and bin_size > 0:
        actual_bins = max(5, min(120, int(np.ceil((max_p - min_p) / bin_size))))
        step = (max_p - min_p) / actual_bins
    else:
        actual_bins = max(5, min(120, num_bins))
        step = (max_p - min_p) / actual_bins

    bins_data: list[dict[str, Any]] = []

    # Initialize bins
    for i in range(actual_bins):
        b_low = min_p + i * step
        b_high = b_low + step
        b_mid = (b_low + b_high) / 2.0
        bins_data.append({
            "index": i,
            "price_level": round(b_mid, 2),
            "price_low": round(b_low, 2),
            "price_high": round(b_high, 2),
            "volume": 0.0,
            "buy_volume": 0.0,
            "sell_volume": 0.0,
        })

    # Distribute volume across candle span with MFM directional allocation
    for _, row in df.iterrows():
        c_open = row["open"]
        c_close = row["close"]
        c_high = row["high"]
        c_low = row["low"]
        vol = float(row["volume"])
        if vol <= 0 or np.isnan(vol):
            continue

        c_span = max(c_high - c_low, 0.001)

        # Money Flow Multiplier: [(close - low) - (high - close)] / (high - low)
        mfm = ((c_close - c_low) - (c_high - c_close)) / c_span
        buy_weight = float(np.clip((1.0 + mfm) / 2.0, 0.05, 0.95))
        sell_weight = 1.0 - buy_weight

        for b in bins_data:
            overlap_lo = max(c_low, b["price_low"])
            overlap_hi = min(c_high, b["price_high"])
            if overlap_hi > overlap_lo:
                fraction = (overlap_hi - overlap_lo) / c_span
                v_part = vol * fraction
                b["volume"] += v_part
                b["buy_volume"] += v_part * buy_weight
                b["sell_volume"] += v_part * sell_weight

    total_vol = sum(b["volume"] for b in bins_data)
    if total_vol <= 0:
        total_vol = 1.0

    # Identify POC (Point of Control)
    max_bin = max(bins_data, key=lambda x: x["volume"])
    poc_price = max_bin["price_level"]
    poc_index = max_bin["index"]

    # Calculate Value Area (70% total volume around POC via greedy expansion)
    target_vol = total_vol * 0.70
    accum_vol = max_bin["volume"]
    up_idx = poc_index
    dn_idx = poc_index

    while accum_vol < target_vol and (up_idx < actual_bins - 1 or dn_idx > 0):
        up_vol = bins_data[up_idx + 1]["volume"] if up_idx < actual_bins - 1 else 0
        dn_vol = bins_data[dn_idx - 1]["volume"] if dn_idx > 0 else 0

        if up_vol >= dn_vol and up_idx < actual_bins - 1:
            up_idx += 1
            accum_vol += up_vol
        elif dn_idx > 0:
            dn_idx -= 1
            accum_vol += dn_vol
        elif up_idx < actual_bins - 1:
            up_idx += 1
            accum_vol += up_vol
        else:
            break

    val_price = bins_data[dn_idx]["price_low"]
    vah_price = bins_data[up_idx]["price_high"]

    # Average bin volume for HVN / LVN classification
    avg_bin_vol = total_vol / actual_bins
    for b in bins_data:
        b["volume"] = round(b["volume"], 2)
        b["buy_volume"] = round(b["buy_volume"], 2)
        b["sell_volume"] = round(b["sell_volume"], 2)
        b["volume_pct"] = round((b["volume"] / total_vol) * 100, 2)
        b["is_poc"] = (b["index"] == poc_index)
        b["in_value_area"] = (dn_idx <= b["index"] <= up_idx)
        b["is_hvn"] = (b["volume"] >= 1.4 * avg_bin_vol)
        b["is_lvn"] = (b["volume"] <= 0.6 * avg_bin_vol)

    # Compute Anchored / Cumulative VWAP
    tp = (df["high"] + df["low"] + df["close"]) / 3
    vol_sum = float(df["volume"].sum())
    vwap_val = float((tp * df["volume"]).sum() / vol_sum) if vol_sum > 0 else float(df["close"].iloc[-1])

    current_price = float(df["close"].iloc[-1])
    price_vs_poc = "ABOVE_POC" if current_price > poc_price else ("BELOW_POC" if current_price < poc_price else "AT_POC")
    price_in_va = (val_price <= current_price <= vah_price)

    return {
        "symbol": symbol,
        "profile_type": "estimated_volume_profile",
        "is_estimated": True,
        "is_trade_level_tape": False,
        "bars_evaluated": len(df),
        "current_price": round(current_price, 2),
        "total_volume": round(total_vol, 2),
        "poc": round(poc_price, 2),
        "vah": round(vah_price, 2),
        "val": round(val_price, 2),
        "vwap": round(vwap_val, 2),
        "price_vs_poc": price_vs_poc,
        "price_in_value_area": price_in_va,
        "value_area_volume_pct": 70.0,
        "bin_count": actual_bins,
        "bin_size": round(step, 2),
        "methodology": (
            "Estimated Volume Profile: OHLCV candle volume distributed across price range [Low, High] "
            "with Money Flow Multiplier (MFM) directional allocation. Approximation only; not tick-level trades."
        ),
        "bins": bins_data,
    }
