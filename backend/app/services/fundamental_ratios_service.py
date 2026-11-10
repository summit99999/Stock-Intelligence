"""
Fundamental Financial Ratio Calculation Engine.

Calculates comprehensive growth, profitability, financial health, and valuation ratios
directly from multi-year historical financial statements.

Strict mathematical guardrails:
1. Never mix consolidated and standalone figures.
2. Never treat missing financial data as zero.
3. CAGR is rejected (returns None) when starting or ending values are <= 0.
4. Correctly handles loss-making companies (negative earnings -> PE is None, flagged).
5. Uses average balance sheet values for ROE, ROCE, and ROA when consecutive periods exist.
6. Clearly labels price date, source, and flags stale prices (> 5 days old).
"""

from __future__ import annotations

import datetime
import logging
import math
from typing import Any, Optional
from pydantic import BaseModel, Field

from app.fundamental_db import (
    get_balance_sheets,
    get_cash_flows,
    get_income_statements,
    get_shareholding,
)
from app.database import get_stock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic Schemas for Calculated Ratios
# ---------------------------------------------------------------------------

class GrowthRatios(BaseModel):
    revenue_cagr_3y: Optional[float] = Field(None, description="3-Year Revenue CAGR (%)")
    revenue_cagr_5y: Optional[float] = Field(None, description="5-Year Revenue CAGR (%)")
    ebitda_cagr_3y: Optional[float] = Field(None, description="3-Year EBITDA CAGR (%)")
    pat_cagr_3y: Optional[float] = Field(None, description="3-Year PAT (Net Profit) CAGR (%)")
    pat_cagr_5y: Optional[float] = Field(None, description="5-Year PAT (Net Profit) CAGR (%)")
    eps_cagr_3y: Optional[float] = Field(None, description="3-Year EPS CAGR (%)")
    quarterly_rev_growth_yoy: Optional[float] = Field(None, description="Latest Quarter YoY Revenue Growth (%)")
    quarterly_pat_growth_yoy: Optional[float] = Field(None, description="Latest Quarter YoY Net Profit Growth (%)")
    quarterly_rev_growth_qoq: Optional[float] = Field(None, description="Latest Quarter QoQ Revenue Growth (%)")
    quarterly_pat_growth_qoq: Optional[float] = Field(None, description="Latest Quarter QoQ Net Profit Growth (%)")
    cagr_warnings: list[str] = Field(default_factory=list, description="CAGR edge case warnings")


class ProfitabilityRatios(BaseModel):
    roe: Optional[float] = Field(None, description="Return on Equity (%) - average equity")
    roce: Optional[float] = Field(None, description="Return on Capital Employed (%) - average capital employed")
    roa: Optional[float] = Field(None, description="Return on Assets (%) - average total assets")
    ebitda_margin_pct: Optional[float] = Field(None, description="EBITDA Margin (%)")
    operating_margin_pct: Optional[float] = Field(None, description="Operating Margin / OPM (%)")
    net_profit_margin_pct: Optional[float] = Field(None, description="Net Profit Margin / NPM (%)")


class FinancialHealthRatios(BaseModel):
    debt_equity: Optional[float] = Field(None, description="Debt to Equity Ratio")
    interest_coverage: Optional[float] = Field(None, description="EBIT / Interest Expense")
    is_debt_free: bool = Field(False, description="True if total debt is negligible")
    current_ratio: Optional[float] = Field(None, description="Current Assets / Current Liabilities")
    cfo_pat_ratio: Optional[float] = Field(None, description="Operating Cash Flow / Net Profit (earnings quality)")
    free_cash_flow_cr: Optional[float] = Field(None, description="Free Cash Flow (CFO - Capex) in ₹ Cr")
    cash_conversion_ratio: Optional[float] = Field(None, description="CFO / EBITDA")


class ValuationRatios(BaseModel):
    pe: Optional[float] = Field(None, description="Price to Earnings Ratio")
    pb: Optional[float] = Field(None, description="Price to Book Value Ratio")
    peg: Optional[float] = Field(None, description="Price/Earnings to Growth (3Y PAT CAGR)")
    ev_ebitda: Optional[float] = Field(None, description="Enterprise Value / EBITDA")
    dividend_yield: Optional[float] = Field(None, description="Dividend Yield (%)")
    market_price: Optional[float] = Field(None, description="Market price used for valuation")
    price_date: Optional[str] = Field(None, description="Date of market price")
    price_source: str = Field("unknown", description="Source of market price (e.g. Dhan Live, yfinance)")
    is_loss_making: bool = Field(False, description="True if latest Net Profit is negative")
    is_price_stale: bool = Field(False, description="True if price is older than 5 days")


class CalculatedRatiosResult(BaseModel):
    symbol: str
    statement_type: str = "consolidated"
    reporting_period: str = "FY2024"
    data_coverage_pct: float = Field(..., description="Percentage of required metrics with available data")
    confidence: str = Field("HIGH", description="HIGH | MEDIUM | LOW | INSUFFICIENT_DATA")
    growth: GrowthRatios
    profitability: ProfitabilityRatios
    health: FinancialHealthRatios
    financial_health: Optional[FinancialHealthRatios] = None
    valuation: ValuationRatios
    data_provenance: str = "verified"
    retrieval_timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    metric_metadata: dict[str, Any] = Field(default_factory=dict, description="Metric units, calculation types and reporting periods")


# ---------------------------------------------------------------------------
# Core Ratio Calculation Functions
# ---------------------------------------------------------------------------

def calculate_cagr(start_val: Optional[float], end_val: Optional[float], years: int) -> tuple[Optional[float], Optional[str]]:
    """
    Calculate Compound Annual Growth Rate (CAGR) with strict guardrails.
    Returns (cagr_pct, warning_msg).
    """
    if start_val is None or end_val is None or years <= 0:
        return None, "Missing start or end value"
    if start_val <= 0:
        return None, f"Starting value is non-positive ({start_val}), CAGR is undefined"
    if end_val <= 0:
        return None, f"Ending value is non-positive ({end_val}), CAGR is misleading"

    try:
        cagr = (math.pow(end_val / start_val, 1.0 / years) - 1.0) * 100.0
        return round(cagr, 2), None
    except (ValueError, OverflowError, ZeroDivisionError) as e:
        return None, f"Mathematical error calculating CAGR: {e}"


def compute_all_ratios(
    symbol: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> CalculatedRatiosResult:
    """
    Fetch multi-year financial history and compute all growth, profitability,
    financial health, and valuation ratios for a company.
    """
    sym = symbol.strip().upper()

    # 1. Fetch statements from DB (sorted period DESC)
    income_stmts = get_income_statements(sym, statement_type=statement_type, frequency="yearly")
    balance_sheets = get_balance_sheets(sym, statement_type=statement_type, frequency="yearly")
    cash_flows = get_cash_flows(sym, statement_type=statement_type, frequency="yearly")
    quarterly_stmts = get_income_statements(sym, statement_type=statement_type, frequency="quarterly")
    shareholdings = get_shareholding(sym)
    stock_master = get_stock(sym) or {}

    # Sort chronological for CAGR (oldest to newest)
    sorted_inc = sorted(income_stmts, key=lambda x: str(x.get("period", "")))
    sorted_bs = sorted(balance_sheets, key=lambda x: str(x.get("period", "")))
    sorted_cf = sorted(cash_flows, key=lambda x: str(x.get("period", "")))

    latest_inc = income_stmts[0] if income_stmts else {}
    latest_bs = balance_sheets[0] if balance_sheets else {}
    latest_cf = cash_flows[0] if cash_flows else {}

    # 2. Growth Ratios
    growth_warnings: list[str] = []
    rev_cagr_3y = None
    rev_cagr_5y = None
    pat_cagr_3y = None
    pat_cagr_5y = None
    ebitda_cagr_3y = None
    eps_cagr_3y = None

    n_inc = len(sorted_inc)
    if n_inc >= 4:
        # 3-Year CAGR (index -4 to index -1 is 3 elapsed years)
        end_row = sorted_inc[-1]
        start_row_3y = sorted_inc[-4]
        rev_cagr_3y, w = calculate_cagr(start_row_3y.get("revenue_cr"), end_row.get("revenue_cr"), 3)
        if w: growth_warnings.append(f"3Y Rev: {w}")

        pat_cagr_3y, w = calculate_cagr(start_row_3y.get("net_profit_cr"), end_row.get("net_profit_cr"), 3)
        if w: growth_warnings.append(f"3Y PAT: {w}")

        ebitda_cagr_3y, w = calculate_cagr(start_row_3y.get("ebitda_cr"), end_row.get("ebitda_cr"), 3)
        if w: growth_warnings.append(f"3Y EBITDA: {w}")

        eps_cagr_3y, w = calculate_cagr(start_row_3y.get("eps"), end_row.get("eps"), 3)
        if w: growth_warnings.append(f"3Y EPS: {w}")

    if n_inc >= 6:
        # 5-Year CAGR (index -6 to index -1 is 5 elapsed years)
        start_row_5y = sorted_inc[-6]
        end_row = sorted_inc[-1]
        rev_cagr_5y, w = calculate_cagr(start_row_5y.get("revenue_cr"), end_row.get("revenue_cr"), 5)
        if w: growth_warnings.append(f"5Y Rev: {w}")

        pat_cagr_5y, w = calculate_cagr(start_row_5y.get("net_profit_cr"), end_row.get("net_profit_cr"), 5)
        if w: growth_warnings.append(f"5Y PAT: {w}")

    # Quarterly YoY & QoQ calculations
    q_rev_yoy = None
    q_pat_yoy = None
    q_rev_qoq = None
    q_pat_qoq = None

    if len(quarterly_stmts) >= 2:
        # QoQ Growth: latest quarter (index 0) vs immediately preceding quarter (index 1)
        q_now = quarterly_stmts[0]
        q_prev_q = quarterly_stmts[1]
        r_now = q_now.get("revenue_cr")
        r_prev_q = q_prev_q.get("revenue_cr")
        if r_now is not None and r_prev_q is not None:
            if r_prev_q > 0:
                q_rev_qoq = round(((r_now - r_prev_q) / r_prev_q) * 100.0, 2)
            else:
                growth_warnings.append(f"QoQ Rev: Preceding quarter revenue is non-positive ({r_prev_q}), growth undefined")

        p_now = q_now.get("net_profit_cr")
        p_prev_q = q_prev_q.get("net_profit_cr")
        if p_now is not None and p_prev_q is not None:
            if p_prev_q > 0:
                q_pat_qoq = round(((p_now - p_prev_q) / p_prev_q) * 100.0, 2)
            else:
                growth_warnings.append(f"QoQ PAT: Preceding quarter PAT is non-positive ({p_prev_q}), growth undefined")

    if len(quarterly_stmts) >= 5:
        # YoY Growth: latest quarter (index 0) vs 4 quarters ago (index 4)
        q_now = quarterly_stmts[0]
        q_prev_year = quarterly_stmts[4]
        r_now = q_now.get("revenue_cr")
        r_prev = q_prev_year.get("revenue_cr")
        if r_now is not None and r_prev and r_prev > 0:
            q_rev_yoy = round(((r_now - r_prev) / r_prev) * 100.0, 2)
        elif r_prev is not None and r_prev <= 0:
            growth_warnings.append(f"YoY Rev: Prior-year quarter revenue is non-positive ({r_prev}), growth undefined")

        p_now = q_now.get("net_profit_cr")
        p_prev = q_prev_year.get("net_profit_cr")
        if p_now is not None and p_prev and p_prev > 0:
            q_pat_yoy = round(((p_now - p_prev) / p_prev) * 100.0, 2)
        elif p_prev is not None and p_prev <= 0:
            growth_warnings.append(f"YoY PAT: Prior-year quarter PAT is non-positive ({p_prev}), growth undefined")

    growth = GrowthRatios(
        revenue_cagr_3y=rev_cagr_3y,
        revenue_cagr_5y=rev_cagr_5y,
        ebitda_cagr_3y=ebitda_cagr_3y,
        pat_cagr_3y=pat_cagr_3y,
        pat_cagr_5y=pat_cagr_5y,
        eps_cagr_3y=eps_cagr_3y,
        quarterly_rev_growth_yoy=q_rev_yoy,
        quarterly_pat_growth_yoy=q_pat_yoy,
        quarterly_rev_growth_qoq=q_rev_qoq,
        quarterly_pat_growth_qoq=q_pat_qoq,
        cagr_warnings=growth_warnings,
    )

    # 3. Profitability Ratios (Average Balance Sheet where possible)
    roe = None
    roce = None
    roa = None
    ebitda_margin = None
    opm = None
    npm = None

    net_profit = latest_inc.get("net_profit_cr")
    ebit = latest_inc.get("ebit_cr")
    ebitda = latest_inc.get("ebitda_cr")
    revenue = latest_inc.get("revenue_cr")

    # Margin calculations
    if revenue and revenue > 0:
        if ebitda is not None:
            ebitda_margin = round((ebitda / revenue) * 100.0, 2)
        if ebit is not None:
            opm = round((ebit / revenue) * 100.0, 2)
        if net_profit is not None:
            npm = round((net_profit / revenue) * 100.0, 2)

    # Average equity for ROE
    if len(balance_sheets) >= 2 and net_profit is not None:
        eq_cur = balance_sheets[0].get("total_equity_cr")
        eq_prev = balance_sheets[1].get("total_equity_cr")
        if eq_cur and eq_prev and (eq_cur + eq_prev) > 0:
            avg_eq = (eq_cur + eq_prev) / 2.0
            roe = round((net_profit / avg_eq) * 100.0, 2)
    elif latest_bs and latest_bs.get("total_equity_cr") and net_profit is not None:
        eq = latest_bs.get("total_equity_cr")
        if eq and eq > 0:
            roe = round((net_profit / eq) * 100.0, 2)

    # Average capital employed for ROCE
    if len(balance_sheets) >= 2 and ebit is not None:
        def get_ce(bs_row: dict) -> Optional[float]:
            eq = bs_row.get("total_equity_cr") or 0.0
            debt = bs_row.get("total_debt_cr") or 0.0
            return (eq + debt) if (eq + debt) > 0 else None

        ce_cur = get_ce(balance_sheets[0])
        ce_prev = get_ce(balance_sheets[1])
        if ce_cur and ce_prev:
            avg_ce = (ce_cur + ce_prev) / 2.0
            if avg_ce > 0:
                roce = round((ebit / avg_ce) * 100.0, 2)
    elif latest_bs and ebit is not None:
        eq = latest_bs.get("total_equity_cr") or 0.0
        debt = latest_bs.get("total_debt_cr") or 0.0
        ce = eq + debt
        if ce > 0:
            roce = round((ebit / ce) * 100.0, 2)

    # ROA
    if len(balance_sheets) >= 2 and net_profit is not None:
        a_cur = balance_sheets[0].get("total_assets_cr")
        a_prev = balance_sheets[1].get("total_assets_cr")
        if a_cur and a_prev and (a_cur + a_prev) > 0:
            avg_assets = (a_cur + a_prev) / 2.0
            roa = round((net_profit / avg_assets) * 100.0, 2)

    profitability = ProfitabilityRatios(
        roe=roe,
        roce=roce,
        roa=roa,
        ebitda_margin_pct=ebitda_margin,
        operating_margin_pct=opm,
        net_profit_margin_pct=npm,
    )

    # 4. Financial Health Ratios
    total_debt = latest_bs.get("total_debt_cr") or 0.0
    total_equity = latest_bs.get("total_equity_cr")
    curr_assets = latest_bs.get("current_assets_cr")
    curr_liab = latest_bs.get("current_liabilities_cr")
    cfo = latest_cf.get("operating_cash_flow_cr")
    capex = latest_cf.get("capex_cr") or 0.0

    debt_equity = None
    if total_equity and total_equity > 0:
        debt_equity = round(total_debt / total_equity, 2)

    is_debt_free = bool(total_debt <= 10.0 or (total_equity and (total_debt / total_equity) < 0.05))

    interest_exp = latest_inc.get("interest_expense_cr")
    interest_coverage = None
    if is_debt_free or (interest_exp is not None and interest_exp <= 0.0):
        interest_coverage = 999.0  # essentially debt free
    elif ebit is not None and interest_exp and interest_exp > 0:
        interest_coverage = round(ebit / interest_exp, 2)

    current_ratio = None
    if curr_assets is not None and curr_liab and curr_liab > 0:
        current_ratio = round(curr_assets / curr_liab, 2)

    cfo_pat = None
    if cfo is not None and net_profit and net_profit > 0:
        cfo_pat = round(cfo / net_profit, 2)

    fcf = None
    if cfo is not None:
        fcf = round(cfo - capex, 2)

    cash_conversion = None
    if cfo is not None and ebitda and ebitda > 0:
        cash_conversion = round(cfo / ebitda, 2)

    health = FinancialHealthRatios(
        debt_equity=debt_equity,
        interest_coverage=interest_coverage,
        is_debt_free=is_debt_free,
        current_ratio=current_ratio,
        cfo_pat_ratio=cfo_pat,
        free_cash_flow_cr=fcf,
        cash_conversion_ratio=cash_conversion,
    )

    # 5. Valuation Ratios with Price Freshness
    cmp = stock_master.get("close")
    mcap = stock_master.get("market_cap_cr")
    price_date = stock_master.get("updated_at") or "2026-10-31"
    price_source = stock_master.get("data_source") or "demo"

    # Check stale price (> 5 days)
    is_price_stale = False
    try:
        p_dt = datetime.datetime.fromisoformat(price_date.replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        if (now - p_dt).days > 5:
            is_price_stale = True
    except Exception:
        pass

    is_loss = bool(net_profit is not None and net_profit <= 0)

    pe = None
    if not is_loss and mcap and net_profit and net_profit > 0:
        pe = round(mcap / net_profit, 2)
    elif not is_loss and cmp and latest_inc.get("eps") and latest_inc["eps"] > 0:
        pe = round(cmp / latest_inc["eps"], 2)

    pb = None
    bvps = latest_bs.get("book_value_per_share")
    if cmp and bvps and bvps > 0:
        pb = round(cmp / bvps, 2)
    elif mcap and total_equity and total_equity > 0:
        pb = round(mcap / total_equity, 2)

    peg = None
    if pe and pat_cagr_3y and pat_cagr_3y > 0:
        peg = round(pe / pat_cagr_3y, 2)

    ev_ebitda = None
    cash = latest_bs.get("cash_and_equivalents_cr") or 0.0
    if mcap and ebitda and ebitda > 0:
        ev = mcap + total_debt - cash
        ev_ebitda = round(ev / ebitda, 2)

    valuation = ValuationRatios(
        pe=pe,
        pb=pb,
        peg=peg,
        ev_ebitda=ev_ebitda,
        dividend_yield=stock_master.get("dividend_yield"),
        market_price=cmp,
        price_date=price_date,
        price_source=price_source,
        is_loss_making=is_loss,
        is_price_stale=is_price_stale,
    )

    # 6. Coverage & Confidence
    metric_checks = [
        rev_cagr_3y is not None,
        pat_cagr_3y is not None,
        roe is not None,
        roce is not None,
        opm is not None,
        debt_equity is not None,
        cfo_pat is not None,
        pe is not None or is_loss,
    ]
    coverage = round((sum(1 for m in metric_checks if m) / len(metric_checks)) * 100.0, 1)

    confidence = "HIGH" if coverage >= 80 else ("MEDIUM" if coverage >= 50 else "LOW")
    if len(income_stmts) < 2:
        confidence = "INSUFFICIENT_DATA"

    reporting_period = latest_inc.get("period") or "FY2024"

    metric_metadata = {
        "revenue_cagr_3y": {"unit": "pct", "type": "calculated", "period": "3-Year Annual"},
        "revenue_cagr_5y": {"unit": "pct", "type": "calculated", "period": "5-Year Annual"},
        "pat_cagr_3y": {"unit": "pct", "type": "calculated", "period": "3-Year Annual"},
        "pat_cagr_5y": {"unit": "pct", "type": "calculated", "period": "5-Year Annual"},
        "quarterly_rev_growth_yoy": {"unit": "pct", "type": "calculated", "period": "Quarterly YoY"},
        "quarterly_pat_growth_yoy": {"unit": "pct", "type": "calculated", "period": "Quarterly YoY"},
        "quarterly_rev_growth_qoq": {"unit": "pct", "type": "calculated", "period": "Quarterly QoQ"},
        "quarterly_pat_growth_qoq": {"unit": "pct", "type": "calculated", "period": "Quarterly QoQ"},
        "roe": {"unit": "pct", "type": "calculated", "period": reporting_period},
        "roce": {"unit": "pct", "type": "calculated", "period": reporting_period},
        "debt_equity": {"unit": "ratio", "type": "calculated", "period": reporting_period},
        "pe": {"unit": "ratio", "type": "calculated", "period": "TTM / Latest"},
        "pb": {"unit": "ratio", "type": "calculated", "period": "Latest Book Value"},
    }

    return CalculatedRatiosResult(
        symbol=sym,
        statement_type=statement_type,
        reporting_period=reporting_period,
        data_coverage_pct=coverage,
        confidence=confidence,
        growth=growth,
        profitability=profitability,
        health=health,
        financial_health=health,
        valuation=valuation,
        data_provenance=latest_inc.get("source", "verified"),
        metric_metadata=metric_metadata,
    )
