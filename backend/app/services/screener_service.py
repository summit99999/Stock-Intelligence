"""
Stock screening engine.

Key design decisions:
  1. Filter parameter names (e.g. min_market_cap_cr) are mapped to the
     correct stock column (market_cap_cr) before comparison.  The stock
     value is compared against the threshold — never against the filter name.
  2. Missing (None) values in stock data cause that stock to fail the filter
     rather than being treated as zero.
  3. Supports both simple flat filters and advanced AND/OR condition groups.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from app.schemas.screener import (
    ConditionGroup,
    FilterCondition,
    LogicOp,
    Operator,
    ScreenRequest,
    SortOrder,
)


# ---------------------------------------------------------------------------
# Field mapping: simple filter param -> (stock column, comparison direction)
# ---------------------------------------------------------------------------
# "min_" prefix → stock value must be >= threshold
# "max_" prefix → stock value must be <= threshold

SIMPLE_FILTER_MAP: dict[str, tuple[str, str]] = {
    # Fundamental
    "min_market_cap_cr":   ("market_cap_cr",       "gte"),
    "max_market_cap_cr":   ("market_cap_cr",       "lte"),
    "min_price":           ("close",               "gte"),
    "max_price":           ("close",               "lte"),
    "min_pe":              ("pe",                  "gte"),
    "max_pe":              ("pe",                  "lte"),
    "min_pb":              ("pb",                  "gte"),
    "max_pb":              ("pb",                  "lte"),
    "min_roe":             ("roe",                 "gte"),
    "max_roe":             ("roe",                 "lte"),
    "min_roce":            ("roce",                "gte"),
    "max_roce":            ("roce",                "lte"),
    "min_debt_equity":     ("debt_equity",         "gte"),
    "max_debt_equity":     ("debt_equity",         "lte"),
    "min_revenue_growth":  ("revenue_growth_pct",  "gte"),
    "max_revenue_growth":  ("revenue_growth_pct",  "lte"),
    "min_profit_growth":   ("profit_growth_pct",   "gte"),
    "max_profit_growth":   ("profit_growth_pct",   "lte"),
    "min_opm":             ("opm_pct",             "gte"),
    "max_opm":             ("opm_pct",             "lte"),
    "min_promoter_holding":("promoter_holding",    "gte"),
    "max_promoter_pledging":("promoter_pledging",  "lte"),
    "min_fii_holding":     ("fii_holding",         "gte"),
    "min_dii_holding":     ("dii_holding",         "gte"),
    # Technical
    "min_rsi":             ("rsi",                 "gte"),
    "max_rsi":             ("rsi",                 "lte"),
    "min_adx":             ("adx",                 "gte"),
    "min_relative_volume": ("relative_volume",     "gte"),
    "max_relative_volume": ("relative_volume",     "lte"),
    "min_return_1m":       ("return_1m_pct",       "gte"),
    "max_return_1m":       ("return_1m_pct",       "lte"),
    "min_return_3m":       ("return_3m_pct",       "gte"),
    "max_return_3m":       ("return_3m_pct",       "lte"),
    "min_return_1y":       ("return_1y_pct",       "gte"),
    "max_return_1y":       ("return_1y_pct",       "lte"),
    # VolumeLens Expanded Indicators
    "min_ema_9":           ("ema_9",               "gte"),
    "max_ema_9":           ("ema_9",               "lte"),
    "min_atr":             ("atr_14",              "gte"),
    "max_atr":             ("atr_14",              "lte"),
    "min_mfi":             ("mfi_14",              "gte"),
    "max_mfi":             ("mfi_14",              "lte"),
    "min_bb_bandwidth":    ("bb_bandwidth",        "gte"),
    "max_bb_bandwidth":    ("bb_bandwidth",        "lte"),
    "min_vwap":            ("vwap",                "gte"),
    "max_vwap":            ("vwap",                "lte"),
    # Phase 6 Advanced Fundamentals
    "min_revenue_cagr_3y": ("revenue_cagr_3y",     "gte"),
    "max_revenue_cagr_3y": ("revenue_cagr_3y",     "lte"),
    "min_pat_cagr_3y":     ("pat_cagr_3y",         "gte"),
    "max_pat_cagr_3y":     ("pat_cagr_3y",         "lte"),
    "min_interest_coverage": ("interest_coverage", "gte"),
    "max_interest_coverage": ("interest_coverage", "lte"),
    "min_cfo_pat_ratio":   ("cfo_pat_ratio",       "gte"),
    "max_cfo_pat_ratio":   ("cfo_pat_ratio",       "lte"),
    "min_peg":             ("peg",                 "gte"),
    "max_peg":             ("peg",                 "lte"),
    "min_quality_score":   ("quality_score",       "gte"),
    "max_quality_score":   ("quality_score",       "lte"),
    "min_free_cash_flow_cr": ("free_cash_flow_cr", "gte"),
    "max_free_cash_flow_cr": ("free_cash_flow_cr", "lte"),
}



def _safe_float(value: Any) -> Optional[float]:
    """Extract a numeric value, returning None for missing / non-numeric."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _compare(stock_value: Optional[float], op: str, threshold: float, threshold2: Optional[float] = None) -> bool:
    """
    Compare a stock's numeric field against a threshold.
    Returns False if the stock value is missing (None).
    """
    if stock_value is None:
        return False

    if op in ("gte", ">="):
        return stock_value >= threshold
    if op in ("lte", "<="):
        return stock_value <= threshold
    if op in ("gt", ">"):
        return stock_value > threshold
    if op in ("lt", "<"):
        return stock_value < threshold
    if op in ("eq", "=="):
        return abs(stock_value - threshold) < 1e-9
    if op in ("neq", "!="):
        return abs(stock_value - threshold) >= 1e-9
    if op == "between":
        if threshold2 is None:
            return stock_value >= threshold
        lo, hi = min(threshold, threshold2), max(threshold, threshold2)
        return lo <= stock_value <= hi

    return False


# ---------------------------------------------------------------------------
# Simple (flat) filter evaluation
# ---------------------------------------------------------------------------

def _passes_simple_filters(stock: dict, request: ScreenRequest) -> bool:
    """Check whether a stock passes all non-None simple min/max filters."""
    dump = request.model_dump(exclude_none=True)

    for param_name, (stock_column, direction) in SIMPLE_FILTER_MAP.items():
        threshold = dump.get(param_name)
        if threshold is None:
            continue
        stock_value = _safe_float(stock.get(stock_column))
        if not _compare(stock_value, direction, threshold):
            return False

    return True


# ---------------------------------------------------------------------------
# Advanced condition group evaluation
# ---------------------------------------------------------------------------

def _evaluate_condition(stock: dict, cond: FilterCondition) -> bool:
    """Evaluate a single FilterCondition against a stock."""
    stock_value = _safe_float(stock.get(cond.field))
    return _compare(stock_value, cond.operator.value, cond.value, cond.value2)


def _evaluate_group(stock: dict, group: ConditionGroup) -> bool:
    """Evaluate a condition group (AND/OR) against a stock."""
    if not group.conditions:
        return True  # empty group passes

    if group.logic == LogicOp.AND:
        return all(_evaluate_condition(stock, c) for c in group.conditions)
    else:  # OR
        return any(_evaluate_condition(stock, c) for c in group.conditions)


def _passes_advanced_filters(stock: dict, groups: list[ConditionGroup]) -> bool:
    """All groups must pass (groups are always AND-joined)."""
    return all(_evaluate_group(stock, g) for g in groups)


def _enrich_stock_fundamentals(stock: dict) -> dict:
    """Enrich stock dictionary with calculated fundamental metrics if available."""
    sym = stock.get("symbol", "").upper()
    try:
        from app.services.fundamental_ratios_service import compute_all_ratios
        from app.services.quality_score_service import calculate_quality_score

        ratios = compute_all_ratios(sym)
        quality = calculate_quality_score(sym, ratios=ratios)

        enriched = dict(stock)
        if ratios.growth.revenue_cagr_3y is not None:
            enriched["revenue_cagr_3y"] = ratios.growth.revenue_cagr_3y
        if ratios.growth.pat_cagr_3y is not None:
            enriched["pat_cagr_3y"] = ratios.growth.pat_cagr_3y
        if ratios.health.interest_coverage is not None:
            enriched["interest_coverage"] = ratios.health.interest_coverage
        if ratios.health.cfo_pat_ratio is not None:
            enriched["cfo_pat_ratio"] = ratios.health.cfo_pat_ratio
        if ratios.valuation.peg is not None:
            enriched["peg"] = ratios.valuation.peg
        if quality.total_score is not None:
            enriched["quality_score"] = quality.total_score
        if ratios.health.free_cash_flow_cr is not None:
            enriched["free_cash_flow_cr"] = ratios.health.free_cash_flow_cr
        return enriched
    except Exception:
        return stock


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_screen(stocks: list[dict], request: ScreenRequest) -> tuple[list[dict], int]:
    """
    Run the screening engine.

    Returns (paginated_results, total_matching_count).
    """
    filtered: list[dict] = []

    for stock in stocks:
        enriched_stock = _enrich_stock_fundamentals(stock)

        # 1. Simple flat filters
        if not _passes_simple_filters(enriched_stock, request):
            continue

        # 2. Advanced condition groups (if provided)
        if request.condition_groups:
            if not _passes_advanced_filters(enriched_stock, request.condition_groups):
                continue

        filtered.append(enriched_stock)


    # Sort
    sort_col = request.sort_by
    reverse = request.sort_order == SortOrder.DESC

    def sort_key(s: dict):
        v = s.get(sort_col)
        if v is None:
            return (1, 0)  # push nulls to end
        if isinstance(v, (int, float)):
            return (0, v)
        return (0, str(v).lower())

    filtered.sort(key=sort_key, reverse=reverse)

    total = len(filtered)

    # Paginate
    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    page_items = filtered[start:end]

    return page_items, total
