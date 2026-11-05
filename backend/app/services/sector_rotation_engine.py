"""
Unified Sector Rotation Engine (Phase 12).

Provides transparent, evidence-based sector intelligence and rotation analysis:
- Categorization into 4 rotation quadrants:
  * LEADING: Strong Relative Strength vs Benchmark AND Positive Momentum
  * WEAKENING: Positive Relative Strength BUT Negative / Decelerating Momentum
  * DECLINING (LAGGING): Negative Relative Strength AND Negative Momentum
  * IMPROVING: Negative Relative Strength BUT Positive / Accelerating Momentum
- Sourced Sector Breadth: % of advancing issues, declining issues, unchanged issues
- Prominent constituents, strongest stock, weakest stock
- Relative strength calculation against tracked benchmark

Strict Quantitative Truthfulness:
- Does NOT claim institutional sector rotation without actual sourced institutional data.
- Standardized data mode attribution (HISTORICAL).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional
import numpy as np

from app.database import list_stocks
from app.services.data_quality_service import (
    DataMode,
    audit_universe_coverage,
    build_standard_metadata,
)

logger = logging.getLogger(__name__)

# TTL Cache
_SECTOR_ROTATION_CACHE: dict[str, Any] = {}
_SECTOR_ROTATION_CACHE_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 60.0


def compute_sector_rotation(
    universe: str = "all",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """
    Compute deep sector strength rankings, relative performance, breadth, and rotation quadrants.
    """
    global _SECTOR_ROTATION_CACHE, _SECTOR_ROTATION_CACHE_TS

    now = time.time()
    cache_key = universe.lower()
    if not force_refresh and cache_key in _SECTOR_ROTATION_CACHE and (now - _SECTOR_ROTATION_CACHE_TS < _CACHE_TTL_SECONDS):
        cached = dict(_SECTOR_ROTATION_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {
            "sectors": [],
            "total_sectors": 0,
            "quadrant_counts": {"LEADING": 0, "WEAKENING": 0, "DECLINING": 0, "IMPROVING": 0},
            "benchmark_average_change": 0.0,
            "metadata": build_standard_metadata(
                provider="yfinance",
                instrument="SECTOR_ROTATION",
                timeframe="1D",
                data_mode=DataMode.HISTORICAL.value,
                data_quality_status="MISSING_DATA",
            ),
        }

    # Group by sector
    sectors_map: dict[str, list[dict[str, Any]]] = {}
    all_changes: list[float] = []

    for s in all_stocks:
        sec = s.get("sector") or "Diversified"
        sectors_map.setdefault(sec, []).append(s)
        all_changes.append(float(s.get("daily_change_pct") or 0.0))

    benchmark_avg_change = float(np.mean(all_changes)) if all_changes else 0.0

    sector_results: list[dict[str, Any]] = []
    quadrant_counts = {"LEADING": 0, "WEAKENING": 0, "DECLINING": 0, "IMPROVING": 0}

    for sec_name, stock_list in sectors_map.items():
        count = len(stock_list)
        chgs = [float(s.get("daily_change_pct") or 0.0) for s in stock_list]
        rsis = [float(s.get("rsi") or 50.0) for s in stock_list]
        rvols = [float(s.get("relative_volume") or 1.0) for s in stock_list]

        avg_chg = round(float(np.mean(chgs)), 2)
        avg_rsi = round(float(np.mean(rsis)), 2)
        avg_rvol = round(float(np.mean(rvols)), 2)

        adv_count = sum(1 for c in chgs if c > 0.05)
        dec_count = sum(1 for c in chgs if c < -0.05)
        unc_count = count - adv_count - dec_count
        breadth_pct = round((adv_count / max(count, 1)) * 100.0, 1)

        # Leaders and Laggards within the sector
        sorted_sector_stocks = sorted(stock_list, key=lambda s: float(s.get("daily_change_pct") or 0.0), reverse=True)
        top_stock = sorted_sector_stocks[0]
        bot_stock = sorted_sector_stocks[-1]

        # Breakouts and Breakdowns count in sector
        breakout_count = sum(
            1 for s in stock_list
            if float(s.get("relative_volume") or 1.0) >= 1.4 and float(s.get("daily_change_pct") or 0.0) >= 1.5
        )
        breakdown_count = sum(
            1 for s in stock_list
            if float(s.get("relative_volume") or 1.0) >= 1.4 and float(s.get("daily_change_pct") or 0.0) <= -1.5
        )

        # Relative Strength vs benchmark average
        rs_vs_market = round(avg_chg - benchmark_avg_change, 2)

        # Rotation Quadrant
        # LEADING: RS > 0 and Momentum (avg_chg) >= 0
        # WEAKENING: RS > 0 and Momentum < 0
        # DECLINING (LAGGING): RS <= 0 and Momentum <= 0
        # IMPROVING: RS <= 0 and Momentum > 0
        if rs_vs_market >= 0 and avg_chg >= 0:
            quadrant = "LEADING"
            quadrant_color = "#26c78b"  # emerald
            quadrant_counts["LEADING"] += 1
        elif rs_vs_market >= 0 and avg_chg < 0:
            quadrant = "WEAKENING"
            quadrant_color = "#f59e0b"  # amber
            quadrant_counts["WEAKENING"] += 1
        elif rs_vs_market < 0 and avg_chg <= 0:
            quadrant = "DECLINING"
            quadrant_color = "#ef4444"  # rose
            quadrant_counts["DECLINING"] += 1
        else:
            quadrant = "IMPROVING"
            quadrant_color = "#38bdf8"  # cyan/blue
            quadrant_counts["IMPROVING"] += 1

        prominent_symbols = [s.get("symbol") for s in sorted_sector_stocks[:4]]

        sector_results.append({
            "sector": sec_name,
            "stock_count": count,
            "average_change_pct": avg_chg,
            "average_rsi": avg_rsi,
            "average_rvol": avg_rvol,
            "advances": adv_count,
            "declines": dec_count,
            "unchanged": unc_count,
            "breadth_pct": breadth_pct,
            "relative_strength_vs_market": rs_vs_market,
            "rotation_quadrant": quadrant,
            "quadrant_color": quadrant_color,
            "breakout_count": breakout_count,
            "breakdown_count": breakdown_count,
            "strongest_stock": {
                "symbol": top_stock.get("symbol"),
                "company_name": top_stock.get("company_name"),
                "change_pct": round(float(top_stock.get("daily_change_pct") or 0.0), 2),
                "close": round(float(top_stock.get("close") or 0.0), 2),
                "relative_volume": round(float(top_stock.get("relative_volume") or 1.0), 2),
            },
            "weakest_stock": {
                "symbol": bot_stock.get("symbol"),
                "company_name": bot_stock.get("company_name"),
                "change_pct": round(float(bot_stock.get("daily_change_pct") or 0.0), 2),
                "close": round(float(bot_stock.get("close") or 0.0), 2),
                "relative_volume": round(float(bot_stock.get("relative_volume") or 1.0), 2),
            },
            "prominent_stocks": ", ".join(prominent_symbols),
            "prominent_symbols": prominent_symbols,
            "positive": avg_chg >= 0,
        })

    # Sort sectors by relative strength vs market descending
    sector_results.sort(key=lambda x: (x["relative_strength_vs_market"], x["average_change_pct"]), reverse=True)

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="SECTOR_ROTATION",
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_sectors": len(sector_results),
        "benchmark_average_change": round(benchmark_avg_change, 2),
        "quadrant_counts": quadrant_counts,
        "sectors": sector_results,
        "disclosure": "Sector rotation based on price action and relative strength against tracked equity benchmark; no unverified institutional rotation claimed.",
        "metadata": metadata,
    }

    _SECTOR_ROTATION_CACHE[cache_key] = result
    _SECTOR_ROTATION_CACHE_TS = now
    return result
