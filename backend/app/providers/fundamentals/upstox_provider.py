"""
Upstox Fundamentals API provider.

Uses the Upstox v2 Fundamentals API with ISIN-based endpoints.
All 8 data types: profile, income-statement, balance-sheet, cash-flow,
key-ratios, share-holdings, corporate-actions, competitors.

Security: The access token is read from config (env var) and passed as a
Bearer token.  It is NEVER logged, returned in responses, or stored in the DB.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.config import get_upstox_config
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

# Rate-limit: be conservative with Upstox
_REQUEST_DELAY_S = 0.5
_MAX_RETRIES = 3
_TIMEOUT_S = 30.0


def _first_not_none(item: dict, *keys: str) -> Any:
    """Return the first value from item where key exists and value is not None."""
    for k in keys:
        val = item.get(k)
        if val is not None:
            return val
    return None


def _safe_float(value: Any) -> Optional[float]:
    """Convert a value to float, returning None on failure or if the value is missing."""
    if value is None or value == "" or value == "NA" or value == "N/A":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _safe_int(value: Any) -> Optional[int]:
    """Convert a value to int, returning None on failure."""
    if value is None or value == "" or value == "NA":
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


class UpstoxFundamentalProvider(FundamentalProvider):
    """Fetches fundamental data from the Upstox v2 API."""

    def source_label(self) -> FundamentalSource:
        return FundamentalSource.UPSTOX_API

    def is_available(self) -> bool:
        config = get_upstox_config()
        return config.is_configured

    def _get_headers(self) -> dict[str, str]:
        """Build auth headers.  Never logs the token."""
        config = get_upstox_config()
        return {
            "Authorization": f"Bearer {config.access_token}",
            "Accept": "application/json",
        }

    def _base_url(self) -> str:
        return get_upstox_config().api_base_url.rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Make an authenticated HTTP request with retries and rate-limit handling.
        Returns the JSON body or None on failure.
        """
        url = f"{self._base_url()}{path}"
        headers = self._get_headers()

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                    resp = await client.request(
                        method, url, headers=headers, params=params
                    )

                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 401:
                    logger.warning("Upstox 401: token may be invalid or expired")
                    return None
                elif resp.status_code == 429:
                    wait = min(2 ** attempt, 10)
                    logger.warning(
                        "Upstox 429 rate-limited, waiting %ds (attempt %d/%d)",
                        wait, attempt, _MAX_RETRIES,
                    )
                    await asyncio.sleep(wait)
                    continue
                else:
                    logger.warning(
                        "Upstox %d on %s (attempt %d/%d)",
                        resp.status_code, path, attempt, _MAX_RETRIES,
                    )
                    if attempt == _MAX_RETRIES:
                        return None
                    await asyncio.sleep(1)

            except httpx.TimeoutException:
                logger.warning(
                    "Upstox timeout on %s (attempt %d/%d)",
                    path, attempt, _MAX_RETRIES,
                )
                if attempt == _MAX_RETRIES:
                    return None
                await asyncio.sleep(1)
            except Exception:
                logger.exception(
                    "Upstox request error on %s (attempt %d/%d)",
                    path, attempt, _MAX_RETRIES,
                )
                if attempt == _MAX_RETRIES:
                    return None
                await asyncio.sleep(1)

        return None

    # ------------------------------------------------------------------
    # 1. Company Profile
    # ------------------------------------------------------------------

    async def fetch_profile(self, isin: str) -> Optional[CompanyProfile]:
        data = await self._request("GET", f"/v2/fundamentals/{isin}/profile")
        if not data:
            return None

        now = datetime.now(timezone.utc).isoformat()
        d = data.get("data", data)

        return CompanyProfile(
            symbol="",  # will be filled by manager
            isin=isin,
            company_name=_first_not_none(d, "company_name", "name"),
            industry=d.get("industry"),
            sector=d.get("sector"),
            exchange=d.get("exchange"),
            face_value=_safe_float(d.get("face_value")),
            market_cap_cr=_safe_float(d.get("market_cap")),
            year_of_incorporation=_safe_int(d.get("year_of_incorporation")),
            bse_code=_first_not_none(d, "bse_script_code", "bse_code"),
            nse_code=_first_not_none(d, "nse_script_code", "nse_code"),
            website=d.get("website"),
            description=_first_not_none(d, "about", "description"),
            source=FundamentalSource.UPSTOX_API,
            fetched_at=now,
        )

    # ------------------------------------------------------------------
    # 2. Income Statement
    # ------------------------------------------------------------------

    async def fetch_income_statements(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[IncomeStatement]:
        params: dict[str, str] = {
            "type": statement_type.value,
            "time_period": frequency.value,
        }
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/income-statement", params=params
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[IncomeStatement] = []
        for item in items:
            period = item.get("period", item.get("year", "unknown"))
            results.append(IncomeStatement(
                symbol="",
                isin=isin,
                period=str(period),
                statement_type=statement_type,
                frequency=frequency,
                revenue_cr=_safe_float(_first_not_none(item, "revenue", "total_revenue")),
                cost_of_revenue_cr=_safe_float(item.get("cost_of_revenue")),
                gross_profit_cr=_safe_float(item.get("gross_profit")),
                operating_expenses_cr=_safe_float(_first_not_none(item, "operating_expenses", "total_operating_expenses")),
                operating_profit_cr=_safe_float(_first_not_none(item, "operating_profit", "operating_income")),
                ebitda_cr=_safe_float(item.get("ebitda")),
                depreciation_cr=_safe_float(_first_not_none(item, "depreciation", "depreciation_and_amortization")),
                ebit_cr=_safe_float(item.get("ebit")),
                interest_expense_cr=_safe_float(_first_not_none(item, "interest_expense", "finance_costs")),
                profit_before_tax_cr=_safe_float(_first_not_none(item, "profit_before_tax", "income_before_tax")),
                tax_expense_cr=_safe_float(_first_not_none(item, "tax", "income_tax_expense")),
                net_profit_cr=_safe_float(_first_not_none(item, "net_profit", "net_income")),
                eps=_safe_float(_first_not_none(item, "eps", "basic_eps")),
                diluted_eps=_safe_float(item.get("diluted_eps")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 3. Balance Sheet
    # ------------------------------------------------------------------

    async def fetch_balance_sheets(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[BalanceSheet]:
        params: dict[str, str] = {
            "type": statement_type.value,
            "time_period": frequency.value,
        }
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/balance-sheet", params=params
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[BalanceSheet] = []
        for item in items:
            period = item.get("period", item.get("year", "unknown"))
            results.append(BalanceSheet(
                symbol="",
                isin=isin,
                period=str(period),
                statement_type=statement_type,
                frequency=frequency,
                total_assets_cr=_safe_float(item.get("total_assets")),
                current_assets_cr=_safe_float(_first_not_none(item, "current_assets", "total_current_assets")),
                non_current_assets_cr=_safe_float(_first_not_none(item, "non_current_assets", "total_non_current_assets")),
                total_liabilities_cr=_safe_float(item.get("total_liabilities")),
                current_liabilities_cr=_safe_float(_first_not_none(item, "current_liabilities", "total_current_liabilities")),
                non_current_liabilities_cr=_safe_float(_first_not_none(item, "non_current_liabilities", "total_non_current_liabilities")),
                total_equity_cr=_safe_float(_first_not_none(item, "total_equity", "shareholders_equity")),
                share_capital_cr=_safe_float(_first_not_none(item, "share_capital", "equity_share_capital")),
                reserves_cr=_safe_float(_first_not_none(item, "reserves", "reserves_and_surplus")),
                total_debt_cr=_safe_float(_first_not_none(item, "total_debt", "borrowings")),
                cash_and_equivalents_cr=_safe_float(_first_not_none(item, "cash_and_equivalents", "cash_and_cash_equivalents")),
                book_value_per_share=_safe_float(item.get("book_value_per_share")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 4. Cash Flow
    # ------------------------------------------------------------------

    async def fetch_cash_flows(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[CashFlow]:
        params: dict[str, str] = {
            "type": statement_type.value,
            "time_period": frequency.value,
        }
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/cash-flow", params=params
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[CashFlow] = []
        for item in items:
            period = item.get("period", item.get("year", "unknown"))
            operating = _safe_float(_first_not_none(item, "operating_cash_flow", "cash_from_operating_activities"))
            investing = _safe_float(_first_not_none(item, "investing_cash_flow", "cash_from_investing_activities"))
            financing = _safe_float(_first_not_none(item, "financing_cash_flow", "cash_from_financing_activities"))
            capex = _safe_float(_first_not_none(item, "capex", "capital_expenditure"))
            fcf = _safe_float(item.get("free_cash_flow"))
            if fcf is None and operating is not None and capex is not None:
                fcf = operating - abs(capex)
            net = _safe_float(item.get("net_cash_flow"))
            if net is None and all(v is not None for v in [operating, investing, financing]):
                net = operating + investing + financing  # type: ignore[operator]

            results.append(CashFlow(
                symbol="",
                isin=isin,
                period=str(period),
                statement_type=statement_type,
                frequency=frequency,
                operating_cash_flow_cr=operating,
                investing_cash_flow_cr=investing,
                financing_cash_flow_cr=financing,
                net_cash_flow_cr=net,
                capex_cr=capex,
                free_cash_flow_cr=fcf,
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 5. Key Ratios
    # ------------------------------------------------------------------

    async def fetch_ratios(
        self,
        isin: str,
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
    ) -> list[KeyRatios]:
        params: dict[str, str] = {
            "type": statement_type.value,
            "time_period": frequency.value,
        }
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/key-ratios", params=params
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[KeyRatios] = []
        for item in items:
            period = item.get("period", item.get("year", "unknown"))
            results.append(KeyRatios(
                symbol="",
                isin=isin,
                period=str(period),
                statement_type=statement_type,
                frequency=frequency,
                pe=_safe_float(_first_not_none(item, "pe", "price_to_earning")),
                pb=_safe_float(_first_not_none(item, "pb", "price_to_book")),
                ev_ebitda=_safe_float(_first_not_none(item, "ev_ebitda", "ev_to_ebitda")),
                roe=_safe_float(_first_not_none(item, "roe", "return_on_equity")),
                roce=_safe_float(_first_not_none(item, "roce", "return_on_capital_employed")),
                debt_equity=_safe_float(_first_not_none(item, "debt_equity", "debt_to_equity")),
                current_ratio=_safe_float(item.get("current_ratio")),
                quick_ratio=_safe_float(item.get("quick_ratio")),
                interest_coverage=_safe_float(_first_not_none(item, "interest_coverage", "interest_coverage_ratio")),
                dividend_yield=_safe_float(item.get("dividend_yield")),
                dividend_payout=_safe_float(_first_not_none(item, "dividend_payout", "dividend_payout_ratio")),
                opm_pct=_safe_float(_first_not_none(item, "operating_profit_margin", "opm")),
                npm_pct=_safe_float(_first_not_none(item, "net_profit_margin", "npm")),
                revenue_growth_pct=_safe_float(item.get("revenue_growth")),
                profit_growth_pct=_safe_float(_first_not_none(item, "profit_growth", "net_profit_growth")),
                asset_turnover=_safe_float(_first_not_none(item, "asset_turnover", "asset_turnover_ratio")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 6. Shareholding Pattern
    # ------------------------------------------------------------------

    async def fetch_shareholding(self, isin: str) -> list[ShareholdingPattern]:
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/share-holdings"
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[ShareholdingPattern] = []
        for item in items:
            period = item.get("period", item.get("quarter", "unknown"))
            results.append(ShareholdingPattern(
                symbol="",
                isin=isin,
                period=str(period),
                promoter_holding=_safe_float(_first_not_none(item, "promoter_holding", "promoters")),
                promoter_pledging=_safe_float(_first_not_none(item, "promoter_pledging", "pledged")),
                fii_holding=_safe_float(_first_not_none(item, "fii_holding", "fii", "foreign_institutions")),
                dii_holding=_safe_float(_first_not_none(item, "dii_holding", "dii", "domestic_institutions")),
                public_holding=_safe_float(_first_not_none(item, "public_holding", "public")),
                government_holding=_safe_float(_first_not_none(item, "government_holding", "government")),
                total_shares=_safe_int(item.get("total_shares")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 7. Corporate Actions
    # ------------------------------------------------------------------

    async def fetch_corporate_actions(self, isin: str) -> list[CorporateAction]:
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/corporate-actions"
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[CorporateAction] = []
        for item in items:
            results.append(CorporateAction(
                symbol="",
                isin=isin,
                action_type=_first_not_none(item, "action_type", "type") or "unknown",
                ex_date=item.get("ex_date"),
                record_date=item.get("record_date"),
                description=_first_not_none(item, "description", "subject"),
                value=_safe_float(_first_not_none(item, "value", "amount")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results

    # ------------------------------------------------------------------
    # 8. Competitors
    # ------------------------------------------------------------------

    async def fetch_competitors(self, isin: str) -> list[Competitor]:
        data = await self._request(
            "GET", f"/v2/fundamentals/{isin}/competitors"
        )
        if not data:
            return []

        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", [])
        if isinstance(items, dict):
            items = [items]

        results: list[Competitor] = []
        for item in items:
            results.append(Competitor(
                symbol="",
                isin=isin,
                competitor_name=_first_not_none(item, "company_name", "name"),
                competitor_isin=item.get("isin"),
                market_cap_cr=_safe_float(item.get("market_cap")),
                pe=_safe_float(item.get("pe")),
                revenue_cr=_safe_float(item.get("revenue")),
                net_profit_cr=_safe_float(item.get("net_profit")),
                raw_data=item,
                verification_status="verified",
                source=FundamentalSource.UPSTOX_API,
                fetched_at=now,
            ))
        return results
