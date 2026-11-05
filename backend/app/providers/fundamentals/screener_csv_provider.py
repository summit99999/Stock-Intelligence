"""
Screener.in CSV import provider.

Parses a user-uploaded CSV export from Screener.in and maps values into
the normalised fundamental schema.  No web scraping — the user must export
the CSV file from Screener.in manually.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.providers.fundamentals.base import FundamentalProvider
from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    Competitor,
    CorporateAction,
    FundamentalSource,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    ShareholdingPattern,
    StatementType,
)

logger = logging.getLogger(__name__)


# Common Screener.in CSV column name variations (case-insensitive matching)
_COLUMN_MAP: dict[str, str] = {
    # Symbol mapping
    "name": "company_name",
    "company": "company_name",
    "symbol": "symbol",
    "ticker": "symbol",
    "nse code": "symbol",
    "bse code": "symbol",
    # Fundamentals
    "market capitalization": "market_cap_cr",
    "market cap": "market_cap_cr",
    "mar cap rs.cr.": "market_cap_cr",
    "price to earning": "pe",
    "p/e": "pe",
    "pe ratio": "pe",
    "price to book": "pb",
    "price to book value": "pb",
    "pb ratio": "pb",
    "p/b": "pb",
    "return on equity": "roe",
    "roe %": "roe",
    "return on capital employed": "roce",
    "roce %": "roce",
    "debt to equity": "debt_equity",
    "d/e": "debt_equity",
    "opm": "opm_pct",
    "opm %": "opm_pct",
    "operating profit margin": "opm_pct",
    "sales": "revenue_cr",
    "revenue": "revenue_cr",
    "sales rs.cr.": "revenue_cr",
    "net profit": "net_profit_cr",
    "profit": "net_profit_cr",
    "np qtr rs.cr.": "net_profit_cr",
    "sales growth": "revenue_growth_pct",
    "revenue growth": "revenue_growth_pct",
    "profit growth": "profit_growth_pct",
    "net profit growth": "profit_growth_pct",
    "promoter holding": "promoter_holding",
    "promoters": "promoter_holding",
    "pledged percentage": "promoter_pledging",
    "promoter pledging": "promoter_pledging",
    "fii holding": "fii_holding",
    "fii": "fii_holding",
    "dii holding": "dii_holding",
    "dii": "dii_holding",
    "free cash flow": "free_cash_flow_cr",
    "current price": "close",
    "cmp": "close",
    "cmp rs.": "close",
    "dividend yield": "dividend_yield",
    "div yld %": "dividend_yield",
    "interest coverage": "interest_coverage",
    "current ratio": "current_ratio",
    "peg": "peg",
    "peg ratio": "peg",
}


def _safe_float(value: Any) -> Optional[float]:
    if value is None or str(value).strip() in ("", "NA", "N/A", "-", "None"):
        return None
    try:
        clean = str(value).replace(",", "").replace("%", "").strip()
        return float(clean)
    except (ValueError, TypeError):
        return None


def _parse_period_header(col_name: str) -> tuple[Optional[str], Optional[str], ReportingFrequency]:
    """
    Parses period header like 'Mar 2024', 'Jun 2023', 'FY24' into:
    (standardized_period, period_end_date, frequency)
    """
    cleaned = col_name.strip()
    # Check for TTM
    if cleaned.upper() == "TTM":
        return "TTM", None, ReportingFrequency.YEARLY

    # Check for Month Year format e.g. "Mar 2024" or "Mar-24"
    month_match = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[ -]?(\d{2,4})$", cleaned, re.IGNORECASE)
    if month_match:
        month_str = month_match.group(1).title()
        year_str = month_match.group(2)
        year = int(year_str) if len(year_str) == 4 else 2000 + int(year_str)

        months = {
            "Jan": ("01", "31"), "Feb": ("02", "28"), "Mar": ("03", "31"),
            "Apr": ("04", "30"), "May": ("05", "31"), "Jun": ("06", "30"),
            "Jul": ("07", "31"), "Aug": ("08", "31"), "Sep": ("09", "30"),
            "Oct": ("10", "31"), "Nov": ("11", "30"), "Dec": ("12", "31"),
        }
        m_num, last_day = months.get(month_str, ("03", "31"))
        period_end = f"{year}-{m_num}-{last_day}"

        if month_str == "Mar":
            # March corresponds to FY end in India
            return f"FY{year}", period_end, ReportingFrequency.YEARLY
        elif month_str == "Jun":
            return f"Q1-FY{year + 1}", period_end, ReportingFrequency.QUARTERLY
        elif month_str == "Sep":
            return f"Q2-FY{year + 1}", period_end, ReportingFrequency.QUARTERLY
        elif month_str == "Dec":
            return f"Q3-FY{year + 1}", period_end, ReportingFrequency.QUARTERLY
        else:
            return f"{month_str}-{year}", period_end, ReportingFrequency.YEARLY

    # Check for FY format e.g. "FY2024" or "FY24"
    fy_match = re.match(r"^FY[ -]?(\d{2,4})$", cleaned, re.IGNORECASE)
    if fy_match:
        y_str = fy_match.group(1)
        year = int(y_str) if len(y_str) == 4 else 2000 + int(y_str)
        return f"FY{year}", f"{year}-03-31", ReportingFrequency.YEARLY

    return None, None, ReportingFrequency.YEARLY


class ScreenerCsvProvider(FundamentalProvider):
    """
    Imports fundamental data from Screener.in CSV exports.

    This is a manual, offline provider — the user uploads a CSV file.
    No network requests are made.
    """

    def source_label(self) -> FundamentalSource:
        return FundamentalSource.SCREENER_CSV

    def is_available(self) -> bool:
        # Always available — no credentials needed
        return True

    def parse_csv(
        self,
        csv_content: str,
        symbol_to_isin: dict[str, str],
    ) -> dict[str, dict[str, Any]]:
        """
        Parse a CSV string and return a dict mapping symbol → field values.

        Args:
            csv_content: Raw CSV text from Screener.in export.
            symbol_to_isin: Mapping of known symbols to ISINs.

        Returns:
            Dict of {symbol: {field: value, ...}}
            plus special keys "_unmapped" and "_errors".
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        if not reader.fieldnames:
            return {"_errors": ["CSV has no header row"]}

        # Build column mapping (case-insensitive)
        col_mapping: dict[str, str] = {}
        for csv_col in reader.fieldnames:
            lower = csv_col.strip().lower()
            if lower in _COLUMN_MAP:
                col_mapping[csv_col] = _COLUMN_MAP[lower]

        results: dict[str, dict[str, Any]] = {}
        unmapped: list[str] = []
        errors: list[str] = []

        # Also allow matching by company_name
        name_to_symbol: dict[str, str] = {}
        # Will be populated by caller if needed

        for row_num, row in enumerate(reader, start=2):
            # Try to find symbol
            symbol = None
            for csv_col, mapped in col_mapping.items():
                if mapped == "symbol" and row.get(csv_col):
                    candidate = row[csv_col].strip().upper()
                    if candidate in symbol_to_isin:
                        symbol = candidate
                    break

            # Fallback: try company_name match
            if not symbol:
                for csv_col, mapped in col_mapping.items():
                    if mapped == "company_name" and row.get(csv_col):
                        name = row[csv_col].strip()
                        # Exact match attempt — user can provide their own mapping
                        upper = name.upper()
                        if upper in symbol_to_isin:
                            symbol = upper
                        break

            if not symbol:
                name_val = ""
                for csv_col, mapped in col_mapping.items():
                    if mapped in ("symbol", "company_name") and row.get(csv_col):
                        name_val = row[csv_col].strip()
                        break
                if name_val:
                    unmapped.append(name_val)
                continue

            # Extract values
            fields: dict[str, Any] = {"symbol": symbol, "isin": symbol_to_isin.get(symbol, "")}
            for csv_col, mapped in col_mapping.items():
                if mapped in ("symbol", "company_name"):
                    fields[mapped] = row.get(csv_col, "").strip()
                    continue
                fields[mapped] = _safe_float(row.get(csv_col))

            results[symbol] = fields

        results["_unmapped"] = unmapped  # type: ignore[assignment]
        results["_errors"] = errors  # type: ignore[assignment]
        return results

    def detect_csv_format(self, csv_content: str) -> str:
        """
        Determines whether the CSV is a multi-company screen/watchlist export ('screen')
        or a single-company multi-period financial statement export ('statements').
        """
        reader = csv.reader(io.StringIO(csv_content))
        rows = [r for r in reader if any(cell.strip() for cell in r)]
        if not rows:
            return "screen"
        header = rows[0]
        period_cols = 0
        for col in header[1:]:
            p, _, _ = _parse_period_header(col)
            if p is not None:
                period_cols += 1
        if period_cols >= 1:
            return "statements"
        return "screen"

    def parse_financial_statements_csv(
        self,
        csv_content: str,
        symbol: str,
        isin: str = "",
        statement_type: StatementType = StatementType.CONSOLIDATED,
    ) -> dict[str, list[Any]]:
        """
        Parses a single-company multi-period financial statements CSV (Screener.in format)
        into normalized IncomeStatement, BalanceSheet, CashFlow, and KeyRatios instances.
        """
        reader = csv.reader(io.StringIO(csv_content))
        raw_rows = [r for r in reader if any(cell.strip() for cell in r)]
        if not raw_rows:
            return {"income_statements": [], "balance_sheets": [], "cash_flows": [], "ratios": []}

        header = raw_rows[0]
        # Map column index -> (period, period_end_date, frequency)
        col_periods: dict[int, tuple[str, Optional[str], ReportingFrequency]] = {}
        for idx in range(1, len(header)):
            col_name = header[idx]
            p, p_date, freq = _parse_period_header(col_name)
            if p is not None:
                col_periods[idx] = (p, p_date, freq)

        if not col_periods:
            return {"income_statements": [], "balance_sheets": [], "cash_flows": [], "ratios": []}

        # Dictionaries to aggregate metrics per period: period -> {field: value}
        income_by_period: dict[str, dict[str, Any]] = {}
        bs_by_period: dict[str, dict[str, Any]] = {}
        cf_by_period: dict[str, dict[str, Any]] = {}
        ratios_by_period: dict[str, dict[str, Any]] = {}

        now_str = datetime.now(timezone.utc).isoformat()

        # Helper to initialize period dict
        def _ensure_period(p_name: str, p_end: Optional[str], freq: ReportingFrequency):
            if p_name not in income_by_period:
                income_by_period[p_name] = {"period": p_name, "period_end_date": p_end, "freq": freq}
            if p_name not in bs_by_period:
                bs_by_period[p_name] = {"period": p_name, "period_end_date": p_end, "freq": freq}
            if p_name not in cf_by_period:
                cf_by_period[p_name] = {"period": p_name, "period_end_date": p_end, "freq": freq}
            if p_name not in ratios_by_period:
                ratios_by_period[p_name] = {"period": p_name, "period_end_date": p_end, "freq": freq}

        for idx, (p_name, p_end, freq) in col_periods.items():
            _ensure_period(p_name, p_end, freq)

        # Process each row
        for row in raw_rows[1:]:
            if not row:
                continue
            line_name = row[0].strip().lower()

            for idx, (p_name, _, _) in col_periods.items():
                if idx >= len(row):
                    continue
                val = _safe_float(row[idx])
                if val is None:
                    continue

                # Map line_name to statement models
                if line_name in ("sales", "revenue", "revenue from operations", "sales rs.cr."):
                    income_by_period[p_name]["revenue_cr"] = val
                elif line_name in ("expenses", "operating expenses", "total expenses"):
                    income_by_period[p_name]["operating_expenses_cr"] = val
                elif line_name in ("operating profit", "ebitda"):
                    income_by_period[p_name]["ebitda_cr"] = val
                    income_by_period[p_name]["operating_profit_cr"] = val
                elif line_name in ("opm %", "opm", "operating profit margin"):
                    income_by_period[p_name]["opm_pct"] = val
                    ratios_by_period[p_name]["opm_pct"] = val
                elif line_name in ("other income",):
                    income_by_period[p_name]["other_income_cr"] = val
                elif line_name in ("interest", "finance costs"):
                    income_by_period[p_name]["interest_expense_cr"] = val
                elif line_name in ("depreciation", "depreciation & amortization"):
                    income_by_period[p_name]["depreciation_cr"] = val
                elif line_name in ("profit before tax", "pbt"):
                    income_by_period[p_name]["profit_before_tax_cr"] = val
                elif line_name in ("tax %", "tax"):
                    income_by_period[p_name]["tax_expense_cr"] = val
                elif line_name in ("net profit", "pat", "profit after tax", "np qtr rs.cr."):
                    income_by_period[p_name]["net_profit_cr"] = val
                elif line_name in ("eps in rs", "eps"):
                    income_by_period[p_name]["eps"] = val

                # Balance sheet items
                elif line_name in ("equity capital", "share capital"):
                    bs_by_period[p_name]["share_capital_cr"] = val
                elif line_name in ("reserves", "other equity"):
                    bs_by_period[p_name]["reserves_cr"] = val
                elif line_name in ("borrowings", "total debt", "debt"):
                    bs_by_period[p_name]["borrowings_cr"] = val
                    bs_by_period[p_name]["total_debt_cr"] = val
                elif line_name in ("total liabilities",):
                    bs_by_period[p_name]["total_liabilities_cr"] = val
                elif line_name in ("fixed assets", "property, plant and equipment"):
                    bs_by_period[p_name]["non_current_assets_cr"] = val
                elif line_name in ("total assets",):
                    bs_by_period[p_name]["total_assets_cr"] = val

                # Cash flow items
                elif line_name in ("cash from operating activity", "operating cash flow", "cash flow from operations", "cfo"):
                    cf_by_period[p_name]["operating_cash_flow_cr"] = val
                elif line_name in ("cash from investing activity", "investing cash flow"):
                    cf_by_period[p_name]["investing_cash_flow_cr"] = val
                elif line_name in ("cash from financing activity", "financing cash flow"):
                    cf_by_period[p_name]["financing_cash_flow_cr"] = val
                elif line_name in ("net cash flow",):
                    cf_by_period[p_name]["net_cash_flow_cr"] = val
                elif line_name in ("free cash flow", "fcf"):
                    cf_by_period[p_name]["free_cash_flow_cr"] = val

                # Ratios
                elif line_name in ("roe %", "roe"):
                    ratios_by_period[p_name]["roe"] = val
                elif line_name in ("roce %", "roce"):
                    ratios_by_period[p_name]["roce"] = val
                elif line_name in ("debt to equity", "d/e"):
                    ratios_by_period[p_name]["debt_equity"] = val

        # Build instances
        incomes: list[IncomeStatement] = []
        for p_name, data in income_by_period.items():
            if any(k not in ("period", "period_end_date", "freq") for k in data):
                rev = data.get("revenue_cr")
                np_val = data.get("net_profit_cr")
                incomes.append(
                    IncomeStatement(
                        symbol=symbol,
                        isin=isin or symbol,
                        period=p_name,
                        statement_type=statement_type,
                        frequency=data["freq"],
                        revenue_cr=rev,
                        operating_expenses_cr=data.get("operating_expenses_cr"),
                        operating_profit_cr=data.get("operating_profit_cr"),
                        ebitda_cr=data.get("ebitda_cr"),
                        other_income_cr=data.get("other_income_cr"),
                        interest_expense_cr=data.get("interest_expense_cr"),
                        depreciation_cr=data.get("depreciation_cr"),
                        profit_before_tax_cr=data.get("profit_before_tax_cr"),
                        tax_expense_cr=data.get("tax_expense_cr"),
                        net_profit_cr=np_val,
                        eps=data.get("eps"),
                        period_end_date=data.get("period_end_date"),
                        verification_status="imported",
                        source=FundamentalSource.SCREENER_CSV,
                        fetched_at=now_str,
                    )
                )

        balance_sheets: list[BalanceSheet] = []
        for p_name, data in bs_by_period.items():
            if any(k not in ("period", "period_end_date", "freq") for k in data):
                sc = data.get("share_capital_cr")
                res = data.get("reserves_cr")
                tot_eq = (sc + res) if (sc is not None and res is not None) else None
                balance_sheets.append(
                    BalanceSheet(
                        symbol=symbol,
                        isin=isin or symbol,
                        period=p_name,
                        statement_type=statement_type,
                        frequency=data["freq"],
                        total_equity_cr=tot_eq,
                        share_capital_cr=sc,
                        reserves_cr=res,
                        total_debt_cr=data.get("total_debt_cr"),
                        borrowings_cr=data.get("borrowings_cr"),
                        total_assets_cr=data.get("total_assets_cr"),
                        non_current_assets_cr=data.get("non_current_assets_cr"),
                        total_liabilities_cr=data.get("total_liabilities_cr"),
                        period_end_date=data.get("period_end_date"),
                        verification_status="imported",
                        source=FundamentalSource.SCREENER_CSV,
                        fetched_at=now_str,
                    )
                )

        cash_flows: list[CashFlow] = []
        for p_name, data in cf_by_period.items():
            if any(k not in ("period", "period_end_date", "freq") for k in data):
                cash_flows.append(
                    CashFlow(
                        symbol=symbol,
                        isin=isin or symbol,
                        period=p_name,
                        statement_type=statement_type,
                        frequency=data["freq"],
                        operating_cash_flow_cr=data.get("operating_cash_flow_cr"),
                        investing_cash_flow_cr=data.get("investing_cash_flow_cr"),
                        financing_cash_flow_cr=data.get("financing_cash_flow_cr"),
                        net_cash_flow_cr=data.get("net_cash_flow_cr"),
                        free_cash_flow_cr=data.get("free_cash_flow_cr"),
                        period_end_date=data.get("period_end_date"),
                        verification_status="imported",
                        source=FundamentalSource.SCREENER_CSV,
                        fetched_at=now_str,
                    )
                )

        ratios_list: list[KeyRatios] = []
        for p_name, data in ratios_by_period.items():
            if any(k not in ("period", "period_end_date", "freq") for k in data):
                ratios_list.append(
                    KeyRatios(
                        symbol=symbol,
                        isin=isin or symbol,
                        period=p_name,
                        statement_type=statement_type,
                        frequency=data["freq"],
                        opm_pct=data.get("opm_pct"),
                        roe=data.get("roe"),
                        roce=data.get("roce"),
                        debt_equity=data.get("debt_equity"),
                        period_end_date=data.get("period_end_date"),
                        verification_status="imported",
                        source=FundamentalSource.SCREENER_CSV,
                        fetched_at=now_str,
                    )
                )

        return {
            "income_statements": incomes,
            "balance_sheets": balance_sheets,
            "cash_flows": cash_flows,
            "ratios": ratios_list,
        }

    # The remaining abstract methods return empty — CSV is a batch import, not per-ISIN fetch

    async def fetch_profile(self, isin: str) -> Optional[CompanyProfile]:
        return None

    async def fetch_income_statements(
        self, isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[IncomeStatement]:
        return []

    async def fetch_balance_sheets(
        self, isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[BalanceSheet]:
        return []

    async def fetch_cash_flows(
        self, isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[CashFlow]:
        return []

    async def fetch_ratios(
        self, isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[KeyRatios]:
        return []

    async def fetch_shareholding(self, isin: str) -> list[ShareholdingPattern]:
        return []

    async def fetch_corporate_actions(self, isin: str) -> list[CorporateAction]:
        return []

    async def fetch_competitors(self, isin: str) -> list[Competitor]:
        return []
