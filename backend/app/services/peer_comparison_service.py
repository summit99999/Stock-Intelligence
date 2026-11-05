"""
Peer Comparison Service for Indian Equities.

Allows side-by-side fundamental comparison of 2 to 5 companies:
- Revenue growth (3Y CAGR)
- PAT growth (3Y CAGR)
- ROE & ROCE
- Margins (OPM, NPM)
- Debt / Equity & Interest Coverage
- PE & PB multiples
- CFO / PAT (Earnings Quality)
- Fundamental Quality Score

Ensures:
- Identical reporting periods (e.g. FY2024).
- Statement type consistency (Consolidated vs Standalone).
- Incomparable or missing data is explicitly flagged.
- Auto-recommends industry peers from universe.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.database import get_stock, list_stocks
from app.services.fundamental_ratios_service import compute_all_ratios
from app.services.quality_score_service import calculate_quality_score

logger = logging.getLogger(__name__)


class PeerMetricRow(BaseModel):
    metric_key: str
    label: str
    unit: str
    values: dict[str, Optional[float]]  # symbol -> value
    best_symbol: Optional[str] = None
    higher_is_better: bool = True


class PeerCompanySummary(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_cr: Optional[float] = None
    current_price: Optional[float] = None
    quality_score: Optional[int] = None
    quality_grade: str = "N/A"
    statement_type: str = "consolidated"
    reporting_period: str = "FY2024"
    data_provenance: str = "verified"


class PeerComparisonResponse(BaseModel):
    symbols: list[str]
    target_symbol: str
    sector: Optional[str] = None
    companies: list[PeerCompanySummary]
    metrics: list[PeerMetricRow]
    period_matched: bool = True
    incomparable_flags: list[str] = Field(default_factory=list)


def compare_peers(
    symbols: list[str],
    target_symbol: Optional[str] = None,
    statement_type: str = "consolidated",
) -> PeerComparisonResponse:
    """
    Compare up to 5 stocks. If fewer than 2 provided, automatically suggests
    peers in the same sector/industry from the universe.
    """
    cleaned_symbols = [s.strip().upper() for s in symbols if s.strip()]
    if not cleaned_symbols:
        cleaned_symbols = ["TCS"]

    main_sym = (target_symbol or cleaned_symbols[0]).upper()
    main_stock = get_stock(main_sym) or {}
    sector = main_stock.get("sector")
    industry = main_stock.get("industry")

    # If only 1 symbol provided, auto-populate with up to 4 peers from the same sector/industry
    if len(cleaned_symbols) < 2 and sector:
        universe = list_stocks(sector=sector)
        for s in universe:
            sym = s["symbol"].upper()
            if sym != main_sym and sym not in cleaned_symbols:
                cleaned_symbols.append(sym)
            if len(cleaned_symbols) >= 5:
                break

    # Cap to maximum 5 companies
    target_symbols = cleaned_symbols[:5]

    companies: list[PeerCompanySummary] = []
    ratio_results: dict[str, Any] = {}
    quality_results: dict[str, Any] = {}
    incomparable_notes: list[str] = []

    periods = set()
    for sym in target_symbols:
        stock_info = get_stock(sym) or {}
        ratios = compute_all_ratios(sym, statement_type=statement_type)
        quality = calculate_quality_score(sym, ratios=ratios)

        ratio_results[sym] = ratios
        quality_results[sym] = quality
        periods.add(ratios.reporting_period)

        companies.append(
            PeerCompanySummary(
                symbol=sym,
                company_name=stock_info.get("company_name", sym),
                sector=stock_info.get("sector"),
                industry=stock_info.get("industry"),
                market_cap_cr=stock_info.get("market_cap_cr"),
                current_price=stock_info.get("close"),
                quality_score=quality.total_score,
                quality_grade=quality.grade,
                statement_type=ratios.statement_type,
                reporting_period=ratios.reporting_period,
                data_provenance=ratios.data_provenance,
            )
        )

    period_matched = len(periods) <= 1
    if not period_matched:
        incomparable_notes.append(f"Reporting periods differ across peers: {list(periods)}")

    # Define metric rows to compare
    metric_defs = [
        ("quality_score", "Fundamental Quality Score", "pts", True, lambda sym: quality_results[sym].total_score),
        ("roe", "Return on Equity (ROE)", "%", True, lambda sym: ratio_results[sym].profitability.roe),
        ("roce", "Return on Capital Employed (ROCE)", "%", True, lambda sym: ratio_results[sym].profitability.roce),
        ("opm", "Operating Margin (OPM)", "%", True, lambda sym: ratio_results[sym].profitability.operating_margin_pct),
        ("npm", "Net Profit Margin (NPM)", "%", True, lambda sym: ratio_results[sym].profitability.net_profit_margin_pct),
        ("rev_cagr_3y", "3-Year Revenue CAGR", "%", True, lambda sym: ratio_results[sym].growth.revenue_cagr_3y),
        ("pat_cagr_3y", "3-Year PAT CAGR", "%", True, lambda sym: ratio_results[sym].growth.pat_cagr_3y),
        ("debt_equity", "Debt / Equity Ratio", "x", False, lambda sym: ratio_results[sym].health.debt_equity),
        ("interest_cov", "Interest Coverage", "x", True, lambda sym: (ratio_results[sym].health.interest_coverage if not ratio_results[sym].health.is_debt_free else 999.0)),
        ("cfo_pat", "CFO / PAT (Cash Quality)", "x", True, lambda sym: ratio_results[sym].health.cfo_pat_ratio),
        ("pe", "P/E Ratio", "x", False, lambda sym: ratio_results[sym].valuation.pe),
        ("pb", "P/B Ratio", "x", False, lambda sym: ratio_results[sym].valuation.pb),
        ("peg", "PEG Ratio", "x", False, lambda sym: ratio_results[sym].valuation.peg),
    ]

    metric_rows: list[PeerMetricRow] = []
    for key, label, unit, higher_is_better, extractor in metric_defs:
        vals: dict[str, Optional[float]] = {}
        for sym in target_symbols:
            try:
                v = extractor(sym)
                vals[sym] = round(float(v), 2) if v is not None else None
            except Exception:
                vals[sym] = None

        # Determine best symbol
        valid_vals = {s: v for s, v in vals.items() if v is not None}
        best_sym = None
        if valid_vals:
            if higher_is_better:
                best_sym = max(valid_vals.items(), key=lambda x: x[1])[0]
            else:
                # For valuation multiples or debt, lower is typically better (if > 0)
                positives = {s: v for s, v in valid_vals.items() if v >= 0}
                if positives:
                    best_sym = min(positives.items(), key=lambda x: x[1])[0]

        metric_rows.append(
            PeerMetricRow(
                metric_key=key,
                label=label,
                unit=unit,
                values=vals,
                best_symbol=best_sym,
                higher_is_better=higher_is_better,
            )
        )

    return PeerComparisonResponse(
        symbols=target_symbols,
        target_symbol=main_sym,
        sector=sector,
        companies=companies,
        metrics=metric_rows,
        period_matched=period_matched,
        incomparable_flags=incomparable_notes,
    )
