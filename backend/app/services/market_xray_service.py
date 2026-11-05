"""
Market X-Ray Engine — Market-Wide Directional Stock Ranking Dashboard.

Features:
- Two independent ranking boards:
  * BULLISH BOARD (ranked by positive directional strength)
  * BEARISH BOARD (ranked by negative directional strength)
- Normalized Strength Score:
  * Movement from session open normalized against 50-day Average Daily Range (ADR)
  * Directional momentum and MA consistency
  * Relative volume expansion (RVOL)
  * Choppiness penalty (large wick vs small body)
- Sector Relative Strength matrix
- Market Breadth metrics
- Order Block Proximity & Liquidity Sweep indicators
"""

from __future__ import annotations

import logging
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars, list_stocks
from app.services.indicators import calculate_all_indicators
from app.services.smc_service import analyze_smart_money_concepts

logger = logging.getLogger(__name__)


def compute_stock_xray(symbol: str, stock_meta: dict) -> dict:
    """
    Calculate Market X-Ray metrics and normalized directional strength scores for a stock.
    """
    sym = symbol.upper()
    bars = get_bars(sym)

    if not bars or len(bars) < 10:
        return {
            "symbol": sym,
            "company_name": stock_meta.get("company_name", sym),
            "sector": stock_meta.get("sector", "General"),
            "price": float(stock_meta.get("close", 0.0)),
            "change_pct": float(stock_meta.get("daily_change_pct", 0.0)),
            "bullish_score": 0.0,
            "bearish_score": 0.0,
            "net_directional_strength": 0.0,
            "is_choppy": False,
            "rvol": 1.0,
            "adr_50": 0.0,
            "ob_proximity": "FAR",
            "sweep_status": "NONE",
        }

    df = pd.DataFrame(bars)
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"]).reset_index(drop=True)
    n = len(df)

    latest_bar = df.iloc[-1]
    o = float(latest_bar["open"])
    h = float(latest_bar["high"])
    l = float(latest_bar["low"])
    c = float(latest_bar["close"])
    v = float(latest_bar["volume"])

    # 1. Calculate 50-day Average Daily Range (ADR)
    adr_bars = df.tail(min(50, n))
    daily_ranges = adr_bars["high"] - adr_bars["low"]
    adr_50 = float(daily_ranges.mean()) if not daily_ranges.empty and daily_ranges.mean() > 0 else 10.0

    # 2. Movement from open normalized against ADR
    move_from_open = c - o
    norm_move = (move_from_open / adr_50) * 100.0  # e.g., +80% of ADR or -60% of ADR

    # 3. Relative Volume (RVOL)
    avg_vol_20 = float(df["volume"].tail(20).mean()) if n >= 20 else v
    rvol = float(v / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # 4. Choppiness Detection (Total day span vs Net move)
    day_span = max(h - l, 0.01)
    net_body = abs(move_from_open)
    choppiness_ratio = day_span / max(net_body, 0.01)
    is_choppy = bool(choppiness_ratio >= 3.2 and day_span > (0.4 * adr_50))

    # 5. Momentum & Moving Average Consistency
    ema_9 = float(df["close"].ewm(span=9, adjust=False).mean().iloc[-1]) if n >= 9 else c
    ema_20 = float(df["close"].ewm(span=20, adjust=False).mean().iloc[-1]) if n >= 20 else c

    bullish_ma_align = (c > ema_9 > ema_20)
    bearish_ma_align = (c < ema_9 < ema_20)

    # 6. SMC Order Block Proximity and Liquidity Sweep checks
    ob_proximity = "NORMAL"
    sweep_status = "NONE"

    # Fast SMC check on recent candles
    recent_swings_high = float(df["high"].iloc[-20:-1].max()) if n >= 21 else h
    recent_swings_low = float(df["low"].iloc[-20:-1].min()) if n >= 21 else l

    # Check sweep
    if h > recent_swings_high and c <= recent_swings_high:
        sweep_status = "BEARISH_SWEEP (BUY-SIDE LIQUIDITY TAKEN)"
    elif l < recent_swings_low and c >= recent_swings_low:
        sweep_status = "BULLISH_SWEEP (SELL-SIDE LIQUIDITY TAKEN)"

    # Check OB Proximity
    if abs(c - recent_swings_low) / c * 100 <= 2.0:
        ob_proximity = "AT_DEMAND_OB"
    elif abs(c - recent_swings_high) / c * 100 <= 2.0:
        ob_proximity = "AT_SUPPLY_OB"

    # 7. Normalized Bullish Strength Score (0 to 100)
    # Move factor (0-40)
    bull_move_factor = max(0.0, min(40.0, (norm_move / 100.0) * 40.0)) if norm_move > 0 else 0.0
    # RVOL factor (0-20)
    vol_factor = max(0.0, min(20.0, (rvol / 2.0) * 20.0))
    # MA momentum factor (0-25)
    bull_ma_factor = 25.0 if bullish_ma_align else (12.0 if c > ema_20 else 0.0)
    # SMC bonus (0-15)
    bull_smc_factor = 15.0 if sweep_status.startswith("BULLISH") or ob_proximity == "AT_DEMAND_OB" else 5.0

    raw_bull_score = bull_move_factor + vol_factor + bull_ma_factor + bull_smc_factor
    if is_choppy:
        raw_bull_score *= 0.65  # 35% choppiness penalty

    # 8. Normalized Bearish Strength Score (0 to 100)
    bear_move_factor = max(0.0, min(40.0, (abs(norm_move) / 100.0) * 40.0)) if norm_move < 0 else 0.0
    bear_ma_factor = 25.0 if bearish_ma_align else (12.0 if c < ema_20 else 0.0)
    bear_smc_factor = 15.0 if sweep_status.startswith("BEARISH") or ob_proximity == "AT_SUPPLY_OB" else 5.0

    raw_bear_score = bear_move_factor + vol_factor + bear_ma_factor + bear_smc_factor
    if is_choppy:
        raw_bear_score *= 0.65

    bullish_score = round(max(0.0, min(100.0, raw_bull_score)), 1)
    bearish_score = round(max(0.0, min(100.0, raw_bear_score)), 1)

    daily_change_pct = round(((c - o) / o * 100), 2) if o > 0 else 0.0

    return {
        "symbol": sym,
        "company_name": stock_meta.get("company_name", sym),
        "sector": stock_meta.get("sector", "General"),
        "price": round(c, 2),
        "change_pct": daily_change_pct,
        "bullish_score": bullish_score,
        "bearish_score": bearish_score,
        "net_directional_strength": round(bullish_score - bearish_score, 1),
        "rvol": round(rvol, 2),
        "adr_50": round(adr_50, 2),
        "norm_adr_move": round(norm_move, 1),
        "is_choppy": is_choppy,
        "choppiness_ratio": round(choppiness_ratio, 2),
        "ob_proximity": ob_proximity,
        "sweep_status": sweep_status,
        "score_components": {
            "move_from_open": round(move_from_open, 2),
            "norm_adr_move_pct": round(norm_move, 1),
            "rvol": round(rvol, 2),
            "is_choppy": is_choppy,
            "bullish_ma_align": bullish_ma_align,
            "bearish_ma_align": bearish_ma_align,
        },
    }


def generate_market_xray_dashboard(limit_universe: int = 50) -> dict:
    """
    Generate the complete Market X-Ray dashboard across the stock universe:
    - Bullish Board (sorted by bullish strength)
    - Bearish Board (sorted by bearish strength)
    - Choppy Stocks list
    - Sector Strength ranking
    - Market Breadth
    """
    stocks = list_stocks()[:limit_universe]
    xray_items = []

    for s in stocks:
        try:
            item = compute_stock_xray(s["symbol"], s)
            xray_items.append(item)
        except Exception as e:
            logger.warning("Error computing X-Ray for %s: %s", s.get("symbol"), e)

    # 1. Independent Bullish Board
    bullish_board = sorted(
        [item for item in xray_items if not item["is_choppy"]],
        key=lambda x: x["bullish_score"],
        reverse=True,
    )[:20]

    # 2. Independent Bearish Board
    bearish_board = sorted(
        [item for item in xray_items if not item["is_choppy"]],
        key=lambda x: x["bearish_score"],
        reverse=True,
    )[:20]

    # 3. Choppy / Rangebound Stocks
    choppy_stocks = [item for item in xray_items if item["is_choppy"]]

    # 4. Sector Strength Ranking
    sector_map: dict[str, list[float]] = {}
    for item in xray_items:
        sec = item.get("sector") or "General"
        sector_map.setdefault(sec, []).append(item["net_directional_strength"])

    sector_rankings = []
    for sec, scores in sector_map.items():
        avg_score = sum(scores) / len(scores) if scores else 0.0
        sector_rankings.append({
            "sector": sec,
            "average_net_strength": round(avg_score, 1),
            "stock_count": len(scores),
            "bias": "BULLISH" if avg_score > 5 else ("BEARISH" if avg_score < -5 else "NEUTRAL"),
        })

    sector_rankings = sorted(sector_rankings, key=lambda x: x["average_net_strength"], reverse=True)

    # 5. Market Breadth
    advances = sum(1 for item in xray_items if item["change_pct"] > 0)
    declines = sum(1 for item in xray_items if item["change_pct"] < 0)
    unchanged = sum(1 for item in xray_items if item["change_pct"] == 0)

    avg_market_score = sum(item["net_directional_strength"] for item in xray_items) / len(xray_items) if xray_items else 0.0

    return {
        "universe_evaluated": len(xray_items),
        "market_breadth": {
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "average_net_score": round(avg_market_score, 1),
            "overall_regime": "BULLISH EXPANSION" if avg_market_score > 10 else ("BEARISH CONTRACTION" if avg_market_score < -10 else "CHOPPY / MIXED"),
        },
        "bullish_board": bullish_board,
        "bearish_board": bearish_board,
        "choppy_stocks": choppy_stocks,
        "sector_rankings": sector_rankings,
    }
