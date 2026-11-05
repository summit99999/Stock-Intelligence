"""
Fundamental Quality Scoring Engine (100-Point System).

Provides a transparent, institutional-grade quality evaluation of Indian equities
based on 6 distinct pillars:
- Growth: 25 points
- Profitability: 25 points
- Financial Health: 20 points
- Cash Flow Quality: 15 points
- Shareholding Quality: 10 points
- Valuation Sanity: 5 points

Features:
- Full itemized score breakdown for each category.
- Explicit list of deductions and economic reasons.
- Strict refusal to score when critical data is missing.
- Configurable category weightings.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.fundamental_db import get_shareholding
from app.services.fundamental_ratios_service import (
    CalculatedRatiosResult,
    compute_all_ratios,
)

logger = logging.getLogger(__name__)


class CategoryScore(BaseModel):
    category: str
    points_awarded: float
    max_points: float
    percentage: float
    description: str


class DeductionDetail(BaseModel):
    category: str
    metric: str
    points_lost: float
    reason: str


class QualityScoreResult(BaseModel):
    symbol: str
    total_score: Optional[int] = Field(None, description="0 to 100 quality score, None if insufficient data")
    grade: str = Field("N/A", description="A+ (Excellent) | A (Strong) | B (Average) | C (Weak) | D (Poor) | INSUFFICIENT_DATA")
    data_coverage_pct: float
    confidence: str = Field("HIGH", description="HIGH | MEDIUM | LOW | INSUFFICIENT_DATA")
    category_scores: dict[str, CategoryScore]
    deductions: list[DeductionDetail]
    summary_verdict: str
    reporting_period: str


def calculate_quality_score(
    symbol: str,
    ratios: Optional[CalculatedRatiosResult] = None,
    weights: Optional[dict[str, float]] = None,
) -> QualityScoreResult:
    """
    Calculate the 100-point fundamental quality score for a stock.
    """
    sym = symbol.strip().upper()

    if ratios is None:
        ratios = compute_all_ratios(sym)

    # If confidence is insufficient, return cleanly without inventing a score
    if ratios.confidence == "INSUFFICIENT_DATA":
        return QualityScoreResult(
            symbol=sym,
            total_score=None,
            grade="INSUFFICIENT_DATA",
            data_coverage_pct=ratios.data_coverage_pct,
            confidence="INSUFFICIENT_DATA",
            category_scores={},
            deductions=[
                DeductionDetail(
                    category="System",
                    metric="History",
                    points_lost=0,
                    reason="Insufficient financial statement history (< 2 consecutive annual reports)",
                )
            ],
            summary_verdict="Cannot compute quality score: Insufficient financial statement history.",
            reporting_period=ratios.reporting_period,
        )

    deductions: list[DeductionDetail] = []
    g = ratios.growth
    p = ratios.profitability
    h = ratios.health
    v = ratios.valuation

    # Shareholding data
    sh_list = get_shareholding(sym)
    latest_sh = sh_list[0] if sh_list else {}
    promoter_h = latest_sh.get("promoter_holding")
    promoter_pledge = latest_sh.get("promoter_pledging") or 0.0
    fii_h = latest_sh.get("fii_holding") or 0.0
    dii_h = latest_sh.get("dii_holding") or 0.0
    inst_h = fii_h + dii_h

    # -----------------------------------------------------------------------
    # 1. Growth (Max 25 points)
    # -----------------------------------------------------------------------
    growth_pts = 0.0
    max_growth = 25.0

    # 3Y Revenue CAGR (8 pts)
    if g.revenue_cagr_3y is not None:
        if g.revenue_cagr_3y >= 15.0:
            growth_pts += 8.0
        elif g.revenue_cagr_3y >= 10.0:
            growth_pts += 5.0
            deductions.append(DeductionDetail(category="Growth", metric="3Y Rev CAGR", points_lost=3.0, reason=f"Moderate 3Y revenue growth ({g.revenue_cagr_3y}% vs target >=15%)"))
        elif g.revenue_cagr_3y >= 5.0:
            growth_pts += 3.0
            deductions.append(DeductionDetail(category="Growth", metric="3Y Rev CAGR", points_lost=5.0, reason=f"Low 3Y revenue growth ({g.revenue_cagr_3y}% vs target >=15%)"))
        else:
            deductions.append(DeductionDetail(category="Growth", metric="3Y Rev CAGR", points_lost=8.0, reason=f"Sluggish 3Y revenue growth ({g.revenue_cagr_3y}% < 5%)"))
    else:
        deductions.append(DeductionDetail(category="Growth", metric="3Y Rev CAGR", points_lost=8.0, reason="3Y Revenue CAGR unavailable or negative base year"))

    # 3Y PAT CAGR (8 pts)
    if g.pat_cagr_3y is not None:
        if g.pat_cagr_3y >= 18.0:
            growth_pts += 8.0
        elif g.pat_cagr_3y >= 10.0:
            growth_pts += 5.0
            deductions.append(DeductionDetail(category="Growth", metric="3Y PAT CAGR", points_lost=3.0, reason=f"Moderate 3Y profit growth ({g.pat_cagr_3y}% vs target >=18%)"))
        elif g.pat_cagr_3y >= 5.0:
            growth_pts += 3.0
            deductions.append(DeductionDetail(category="Growth", metric="3Y PAT CAGR", points_lost=5.0, reason=f"Low 3Y profit growth ({g.pat_cagr_3y}% vs target >=18%)"))
        else:
            deductions.append(DeductionDetail(category="Growth", metric="3Y PAT CAGR", points_lost=8.0, reason=f"Sluggish 3Y profit growth ({g.pat_cagr_3y}% < 5%)"))
    else:
        deductions.append(DeductionDetail(category="Growth", metric="3Y PAT CAGR", points_lost=8.0, reason="3Y Net Profit CAGR unavailable or negative base year"))

    # Quarterly Revenue YoY (5 pts)
    if g.quarterly_rev_growth_yoy is not None:
        if g.quarterly_rev_growth_yoy >= 10.0:
            growth_pts += 5.0
        elif g.quarterly_rev_growth_yoy >= 0.0:
            growth_pts += 3.0
            deductions.append(DeductionDetail(category="Growth", metric="Quarterly Rev YoY", points_lost=2.0, reason=f"Modest latest quarter revenue growth ({g.quarterly_rev_growth_yoy}%)"))
        else:
            deductions.append(DeductionDetail(category="Growth", metric="Quarterly Rev YoY", points_lost=5.0, reason=f"Quarterly revenue de-growth ({g.quarterly_rev_growth_yoy}%)"))
    else:
        growth_pts += 3.0  # neutral fallback if quarterly missing

    # Quarterly PAT YoY (4 pts)
    if g.quarterly_pat_growth_yoy is not None:
        if g.quarterly_pat_growth_yoy >= 12.0:
            growth_pts += 4.0
        elif g.quarterly_pat_growth_yoy >= 0.0:
            growth_pts += 2.0
            deductions.append(DeductionDetail(category="Growth", metric="Quarterly PAT YoY", points_lost=2.0, reason=f"Modest quarterly profit growth ({g.quarterly_pat_growth_yoy}%)"))
        else:
            deductions.append(DeductionDetail(category="Growth", metric="Quarterly PAT YoY", points_lost=4.0, reason=f"Quarterly profit de-growth ({g.quarterly_pat_growth_yoy}%)"))
    else:
        growth_pts += 2.0

    # -----------------------------------------------------------------------
    # 2. Profitability (Max 25 points)
    # -----------------------------------------------------------------------
    profit_pts = 0.0
    max_profit = 25.0

    # ROCE (10 pts)
    if p.roce is not None:
        if p.roce >= 22.0:
            profit_pts += 10.0
        elif p.roce >= 15.0:
            profit_pts += 7.0
            deductions.append(DeductionDetail(category="Profitability", metric="ROCE", points_lost=3.0, reason=f"Decent ROCE ({p.roce}% vs elite target >=22%)"))
        elif p.roce >= 10.0:
            profit_pts += 4.0
            deductions.append(DeductionDetail(category="Profitability", metric="ROCE", points_lost=6.0, reason=f"Sub-par ROCE ({p.roce}% vs >=22%)"))
        else:
            deductions.append(DeductionDetail(category="Profitability", metric="ROCE", points_lost=10.0, reason=f"Poor capital efficiency (ROCE {p.roce}% < 10%)"))
    else:
        deductions.append(DeductionDetail(category="Profitability", metric="ROCE", points_lost=10.0, reason="ROCE data unavailable"))

    # ROE (8 pts)
    if p.roe is not None:
        if p.roe >= 18.0:
            profit_pts += 8.0
        elif p.roe >= 12.0:
            profit_pts += 5.0
            deductions.append(DeductionDetail(category="Profitability", metric="ROE", points_lost=3.0, reason=f"Moderate ROE ({p.roe}% vs elite target >=18%)"))
        elif p.roe >= 8.0:
            profit_pts += 3.0
            deductions.append(DeductionDetail(category="Profitability", metric="ROE", points_lost=5.0, reason=f"Low ROE ({p.roe}% vs >=18%)"))
        else:
            deductions.append(DeductionDetail(category="Profitability", metric="ROE", points_lost=8.0, reason=f"Sub-par equity return (ROE {p.roe}% < 8%)"))
    else:
        deductions.append(DeductionDetail(category="Profitability", metric="ROE", points_lost=8.0, reason="ROE data unavailable"))

    # Operating Margin (OPM) (7 pts)
    if p.operating_margin_pct is not None:
        if p.operating_margin_pct >= 18.0:
            profit_pts += 7.0
        elif p.operating_margin_pct >= 12.0:
            profit_pts += 5.0
            deductions.append(DeductionDetail(category="Profitability", metric="OPM", points_lost=2.0, reason=f"Moderate operating margin ({p.operating_margin_pct}%)"))
        elif p.operating_margin_pct >= 7.0:
            profit_pts += 3.0
            deductions.append(DeductionDetail(category="Profitability", metric="OPM", points_lost=4.0, reason=f"Thin operating margin ({p.operating_margin_pct}%)"))
        else:
            deductions.append(DeductionDetail(category="Profitability", metric="OPM", points_lost=7.0, reason=f"Very low operating margin ({p.operating_margin_pct}% < 7%)"))
    else:
        deductions.append(DeductionDetail(category="Profitability", metric="OPM", points_lost=7.0, reason="Operating margin unavailable"))

    # -----------------------------------------------------------------------
    # 3. Financial Health (Max 20 points)
    # -----------------------------------------------------------------------
    health_pts = 0.0
    max_health = 20.0

    # Debt / Equity (8 pts)
    if h.is_debt_free or (h.debt_equity is not None and h.debt_equity <= 0.1):
        health_pts += 8.0
    elif h.debt_equity is not None:
        if h.debt_equity <= 0.5:
            health_pts += 6.0
            deductions.append(DeductionDetail(category="Financial Health", metric="Debt/Equity", points_lost=2.0, reason=f"Low to moderate leverage (Debt/Equity {h.debt_equity})"))
        elif h.debt_equity <= 1.0:
            health_pts += 3.0
            deductions.append(DeductionDetail(category="Financial Health", metric="Debt/Equity", points_lost=5.0, reason=f"Moderate to high leverage (Debt/Equity {h.debt_equity})"))
        else:
            deductions.append(DeductionDetail(category="Financial Health", metric="Debt/Equity", points_lost=8.0, reason=f"Heavy debt burden (Debt/Equity {h.debt_equity} > 1.0)"))
    else:
        health_pts += 4.0  # conservative assumption

    # Interest Coverage (7 pts)
    if h.is_debt_free or (h.interest_coverage is not None and h.interest_coverage >= 6.0):
        health_pts += 7.0
    elif h.interest_coverage is not None:
        if h.interest_coverage >= 3.0:
            health_pts += 4.0
            deductions.append(DeductionDetail(category="Financial Health", metric="Interest Coverage", points_lost=3.0, reason=f"Moderate interest coverage ({h.interest_coverage}x)"))
        else:
            deductions.append(DeductionDetail(category="Financial Health", metric="Interest Coverage", points_lost=7.0, reason=f"Vulnerable interest coverage ({h.interest_coverage}x < 3.0x)"))
    else:
        health_pts += 4.0

    # Current Ratio (5 pts)
    if h.current_ratio is not None:
        if h.current_ratio >= 1.5:
            health_pts += 5.0
        elif h.current_ratio >= 1.0:
            health_pts += 3.0
            deductions.append(DeductionDetail(category="Financial Health", metric="Current Ratio", points_lost=2.0, reason=f"Tight liquidity buffer (Current Ratio {h.current_ratio})"))
        else:
            deductions.append(DeductionDetail(category="Financial Health", metric="Current Ratio", points_lost=5.0, reason=f"Negative working capital risk (Current Ratio {h.current_ratio} < 1.0)"))
    else:
        health_pts += 3.0

    # -----------------------------------------------------------------------
    # 4. Cash Flow Quality (Max 15 points)
    # -----------------------------------------------------------------------
    cash_pts = 0.0
    max_cash = 15.0

    # CFO / PAT (7 pts)
    if h.cfo_pat_ratio is not None:
        if h.cfo_pat_ratio >= 0.9:
            cash_pts += 7.0
        elif h.cfo_pat_ratio >= 0.7:
            cash_pts += 4.0
            deductions.append(DeductionDetail(category="Cash Flow", metric="CFO/PAT", points_lost=3.0, reason=f"Moderate cash conversion from accounting profits (CFO/PAT {h.cfo_pat_ratio})"))
        else:
            deductions.append(DeductionDetail(category="Cash Flow", metric="CFO/PAT", points_lost=7.0, reason=f"Poor cash conversion (CFO/PAT {h.cfo_pat_ratio} < 0.7; profits locked in working capital)"))
    else:
        deductions.append(DeductionDetail(category="Cash Flow", metric="CFO/PAT", points_lost=7.0, reason="Operating cash flow or net profit unavailable"))

    # Free Cash Flow (5 pts)
    if h.free_cash_flow_cr is not None:
        if h.free_cash_flow_cr > 0:
            cash_pts += 5.0
        else:
            deductions.append(DeductionDetail(category="Cash Flow", metric="Free Cash Flow", points_lost=5.0, reason=f"Negative Free Cash Flow (₹{h.free_cash_flow_cr} Cr due to capex / working capital)"))
    else:
        deductions.append(DeductionDetail(category="Cash Flow", metric="Free Cash Flow", points_lost=5.0, reason="Free Cash Flow data unavailable"))

    # Cash Conversion Ratio (CFO / EBITDA) (3 pts)
    if h.cash_conversion_ratio is not None:
        if h.cash_conversion_ratio >= 0.7:
            cash_pts += 3.0
        else:
            deductions.append(DeductionDetail(category="Cash Flow", metric="Cash Conversion", points_lost=3.0, reason=f"CFO / EBITDA below 0.7 ({h.cash_conversion_ratio})"))
    else:
        cash_pts += 1.0

    # -----------------------------------------------------------------------
    # 5. Shareholding Quality (Max 10 points)
    # -----------------------------------------------------------------------
    sh_pts = 0.0
    max_sh = 10.0

    # Promoter Holding (4 pts)
    if promoter_h is not None:
        if promoter_h >= 50.0:
            sh_pts += 4.0
        elif promoter_h >= 35.0:
            sh_pts += 2.0
            deductions.append(DeductionDetail(category="Shareholding", metric="Promoter Holding", points_lost=2.0, reason=f"Moderate promoter stake ({promoter_h}%)"))
        elif promoter_h == 0.0:
            # Professionally managed (like HDFCBANK or ICICIBANK) with high institutional holding
            if inst_h >= 60.0:
                sh_pts += 4.0
            else:
                sh_pts += 1.0
                deductions.append(DeductionDetail(category="Shareholding", metric="Promoter Holding", points_lost=3.0, reason="Zero promoter holding with moderate institutional stake"))
        else:
            sh_pts += 1.0
            deductions.append(DeductionDetail(category="Shareholding", metric="Promoter Holding", points_lost=3.0, reason=f"Low promoter stake ({promoter_h}% < 35%)"))
    else:
        sh_pts += 2.0

    # Promoter Pledge (4 pts)
    if promoter_pledge == 0.0:
        sh_pts += 4.0
    elif promoter_pledge <= 5.0:
        sh_pts += 2.0
        deductions.append(DeductionDetail(category="Shareholding", metric="Promoter Pledge", points_lost=2.0, reason=f"Minor promoter pledge ({promoter_pledge}%)"))
    else:
        deductions.append(DeductionDetail(category="Shareholding", metric="Promoter Pledge", points_lost=4.0, reason=f"High promoter pledge ({promoter_pledge}% >= 5%)"))

    # Institutional Holding (FII + DII) (2 pts)
    if inst_h >= 25.0:
        sh_pts += 2.0
    elif inst_h >= 15.0:
        sh_pts += 1.0
        deductions.append(DeductionDetail(category="Shareholding", metric="Institutional Stake", points_lost=1.0, reason=f"Modest institutional backing ({round(inst_h, 1)}%)"))
    else:
        deductions.append(DeductionDetail(category="Shareholding", metric="Institutional Stake", points_lost=2.0, reason=f"Low institutional interest ({round(inst_h, 1)}% < 15%)"))

    # -----------------------------------------------------------------------
    # 6. Valuation Sanity (Max 5 points)
    # -----------------------------------------------------------------------
    val_pts = 0.0
    max_val = 5.0

    if v.is_loss_making:
        deductions.append(DeductionDetail(category="Valuation", metric="Earnings", points_lost=5.0, reason="Loss-making company; negative net profits"))
    elif v.peg is not None and 0.0 < v.peg <= 1.5:
        val_pts += 5.0
    elif v.pe is not None and v.pe <= 30.0:
        val_pts += 4.0
    elif v.pe is not None and v.pe <= 50.0:
        val_pts += 2.0
        deductions.append(DeductionDetail(category="Valuation", metric="P/E", points_lost=3.0, reason=f"Premium valuation (P/E {v.pe}x)"))
    elif v.pe is not None:
        val_pts += 1.0
        deductions.append(DeductionDetail(category="Valuation", metric="P/E", points_lost=4.0, reason=f"Very rich valuation (P/E {v.pe}x > 50x)"))
    else:
        val_pts += 2.0

    # -----------------------------------------------------------------------
    # Aggregate and Finalize
    # -----------------------------------------------------------------------
    total_raw = growth_pts + profit_pts + health_pts + cash_pts + sh_pts + val_pts
    final_score = int(min(100, max(0, round(total_raw))))

    if final_score >= 80:
        grade = "A+ (Excellent Quality)"
        verdict = f"{sym} demonstrates top-tier financial strength, robust return ratios, and clean cash-flow realization."
    elif final_score >= 68:
        grade = "A (Strong Quality)"
        verdict = f"{sym} possesses strong fundamentals with minor deductions in growth rate or valuation multiples."
    elif final_score >= 52:
        grade = "B (Average Quality)"
        verdict = f"{sym} exhibits balanced fundamentals with average capital efficiency or moderate leverage."
    elif final_score >= 35:
        grade = "C (Weak Quality)"
        verdict = f"{sym} shows fundamental vulnerabilities such as high debt, thin margins, or negative cash flows."
    else:
        grade = "D (Poor Quality)"
        verdict = f"{sym} is fundamentally distressed or loss-making with weak balance sheet buffers."

    category_scores = {
        "growth": CategoryScore(
            category="Growth",
            points_awarded=round(growth_pts, 1),
            max_points=max_growth,
            percentage=round((growth_pts / max_growth) * 100.0, 1),
            description="3Y/5Y revenue & profit CAGR, quarterly YoY momentum",
        ),
        "profitability": CategoryScore(
            category="Profitability",
            points_awarded=round(profit_pts, 1),
            max_points=max_profit,
            percentage=round((profit_pts / max_profit) * 100.0, 1),
            description="ROCE, ROE, operating margin and capital efficiency",
        ),
        "financial_health": CategoryScore(
            category="Financial Health",
            points_awarded=round(health_pts, 1),
            max_points=max_health,
            percentage=round((health_pts / max_health) * 100.0, 1),
            description="Debt-to-equity leverage, interest coverage, liquidity",
        ),
        "cash_flow": CategoryScore(
            category="Cash Flow Quality",
            points_awarded=round(cash_pts, 1),
            max_points=max_cash,
            percentage=round((cash_pts / max_cash) * 100.0, 1),
            description="CFO to PAT conversion, Free Cash Flow, cash generation",
        ),
        "shareholding": CategoryScore(
            category="Shareholding Quality",
            points_awarded=round(sh_pts, 1),
            max_points=max_sh,
            percentage=round((sh_pts / max_sh) * 100.0, 1),
            description="Promoter alignment, zero pledging, institutional presence",
        ),
        "valuation": CategoryScore(
            category="Valuation Sanity",
            points_awarded=round(val_pts, 1),
            max_points=max_val,
            percentage=round((val_pts / max_val) * 100.0, 1),
            description="Price reasonableness, PEG ratio, earnings profitability",
        ),
    }

    return QualityScoreResult(
        symbol=sym,
        total_score=final_score,
        grade=grade,
        data_coverage_pct=ratios.data_coverage_pct,
        confidence=ratios.confidence,
        category_scores=category_scores,
        deductions=deductions,
        summary_verdict=verdict,
        reporting_period=ratios.reporting_period,
    )
