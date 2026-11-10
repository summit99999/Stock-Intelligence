"""
Fundamental data API router.

Endpoints for company profiles, financial statements, ratios, shareholding,
corporate actions, provider status, sync orchestration, and Screener.in CSV import.
All mounted under /api/fundamentals.
"""

from __future__ import annotations

import email
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.config import get_upstox_config
from app.database import get_stock
from app.fundamental_db import (
    count_fundamental_records,
    get_balance_sheets,
    get_cash_flows,
    get_company_profile,
    get_competitors,
    get_corporate_actions,
    get_income_statements,
    get_ratios,
    get_shareholding,
    get_sync_history,
    get_sync_summary,
    has_verified_record,
    upsert_balance_sheet,
    upsert_cash_flow,
    upsert_company_profile,
    upsert_income_statement,
    upsert_key_ratios,
)
from app.providers.fundamentals.manager import get_fundamental_manager
from app.providers.fundamentals.screener_csv_provider import ScreenerCsvProvider
from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    FundamentalSource,
    FundamentalSyncRequest,
    FundamentalSyncResponse,
    FundamentalsStatusResponse,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    ScreenerCsvImportResponse,
    StatementType,
)
from app.services.fundamental_ratios_service import (
    CalculatedRatiosResult,
    compute_all_ratios,
)
from app.services.peer_comparison_service import (
    PeerComparisonResponse,
    compare_peers,
)
from app.services.quality_score_service import (
    QualityScoreResult,
    calculate_quality_score,
)
from app.services.equity_research_service import (
    calculate_1y_performance,
    calculate_relative_strength,
    calculate_dvm_scores,
    generate_fundamental_checklist_and_swot,
    get_sector_peer_comparison,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fundamentals", tags=["fundamentals"])


class PeerComparisonRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=5, description="List of 2 to 5 symbols to compare")
    target_symbol: Optional[str] = Field(None, description="Primary focus symbol")
    statement_type: StatementType = StatementType.CONSOLIDATED


class CompanyResearchDossier(BaseModel):
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    isin: Optional[str] = None
    market_cap_cr: Optional[float] = None
    current_price: Optional[float] = None
    close: Optional[float] = None
    daily_change_pct: Optional[float] = None
    week_52_high: Optional[float] = None
    week_52_low: Optional[float] = None
    profile: Optional[dict[str, Any]] = None
    annual_income_statements: list[dict[str, Any]] = Field(default_factory=list)
    quarterly_income_statements: list[dict[str, Any]] = Field(default_factory=list)
    balance_sheets: list[dict[str, Any]] = Field(default_factory=list)
    cash_flows: list[dict[str, Any]] = Field(default_factory=list)
    shareholding: list[dict[str, Any]] = Field(default_factory=list)
    stored_ratios: list[dict[str, Any]] = Field(default_factory=list)
    calculated_ratios: Optional[CalculatedRatiosResult] = None
    quality_score: Optional[QualityScoreResult] = None
    peers: Optional[PeerComparisonResponse] = None
    performance_1y: Optional[dict[str, Any]] = None
    relative_strength: Optional[dict[str, Any]] = None
    dvm_scores: Optional[dict[str, Any]] = None
    checklist_swot: Optional[dict[str, Any]] = None
    sector_peers: Optional[dict[str, Any]] = None
    corporate_actions: list[dict[str, Any]] = Field(default_factory=list)
    competitors: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=FundamentalsStatusResponse)
def get_fundamentals_status() -> FundamentalsStatusResponse:
    """
    Check configuration and availability of fundamental-data providers.
    Never exposes API tokens or secrets.
    """
    from app.database import connect

    upstox_cfg = get_upstox_config()
    mgr = get_fundamental_manager()

    with connect() as con:
        total_stocks = con.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        stocks_with_isin = con.execute(
            "SELECT COUNT(*) FROM stocks WHERE isin IS NOT NULL AND isin != ''"
        ).fetchone()[0]

    available_names = [p.source_label().value for p in mgr.available_providers]
    sync_summary = get_sync_summary()

    return FundamentalsStatusResponse(
        upstox_configured=upstox_cfg.is_configured,
        upstox_token_present=bool(upstox_cfg.access_token),
        total_stocks=total_stocks,
        stocks_with_isin=stocks_with_isin,
        providers_available=available_names,
        sync_summary=sync_summary,
    )


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------

@router.get("/company/{symbol}")
def get_profile(symbol: str):
    """Get the stored fundamental company profile for a stock."""
    symbol_upper = symbol.upper()
    profile = get_company_profile(symbol_upper)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company profile not found for {symbol_upper}. Try syncing first.",
        )
    return {"symbol": symbol_upper, "profile": profile}


@router.get("/company/{symbol}/income-statement")
def get_income_statement(
    symbol: str,
    statement_type: StatementType = StatementType.CONSOLIDATED,
    frequency: ReportingFrequency = ReportingFrequency.YEARLY,
):
    """Get stored income statements (annual or quarterly, consolidated or standalone)."""
    symbol_upper = symbol.upper()
    statements = get_income_statements(
        symbol_upper, statement_type=statement_type.value, frequency=frequency.value
    )
    return {
        "symbol": symbol_upper,
        "statement_type": statement_type.value,
        "frequency": frequency.value,
        "count": len(statements),
        "data": statements,
    }


@router.get("/company/{symbol}/balance-sheet")
def get_balance_sheet(
    symbol: str,
    statement_type: StatementType = StatementType.CONSOLIDATED,
    frequency: ReportingFrequency = ReportingFrequency.YEARLY,
):
    """Get stored balance sheets."""
    symbol_upper = symbol.upper()
    sheets = get_balance_sheets(
        symbol_upper, statement_type=statement_type.value, frequency=frequency.value
    )
    return {
        "symbol": symbol_upper,
        "statement_type": statement_type.value,
        "frequency": frequency.value,
        "count": len(sheets),
        "data": sheets,
    }


@router.get("/company/{symbol}/cash-flow")
def get_cash_flow(
    symbol: str,
    statement_type: StatementType = StatementType.CONSOLIDATED,
    frequency: ReportingFrequency = ReportingFrequency.YEARLY,
):
    """Get stored cash flow statements."""
    symbol_upper = symbol.upper()
    flows = get_cash_flows(
        symbol_upper, statement_type=statement_type.value, frequency=frequency.value
    )
    return {
        "symbol": symbol_upper,
        "statement_type": statement_type.value,
        "frequency": frequency.value,
        "count": len(flows),
        "data": flows,
    }


@router.get("/company/{symbol}/ratios")
def get_financial_ratios(
    symbol: str,
    statement_type: StatementType = StatementType.CONSOLIDATED,
    frequency: ReportingFrequency = ReportingFrequency.YEARLY,
):
    """Get stored key valuation and performance ratios."""
    symbol_upper = symbol.upper()
    ratios = get_ratios(
        symbol_upper, statement_type=statement_type.value, frequency=frequency.value
    )
    return {
        "symbol": symbol_upper,
        "statement_type": statement_type.value,
        "frequency": frequency.value,
        "count": len(ratios),
        "data": ratios,
    }


@router.get("/company/{symbol}/shareholding")
def get_shareholding_pattern(symbol: str):
    """Get stored shareholding patterns."""
    symbol_upper = symbol.upper()
    patterns = get_shareholding(symbol_upper)
    return {
        "symbol": symbol_upper,
        "count": len(patterns),
        "data": patterns,
    }


@router.get("/company/{symbol}/corporate-actions")
def get_actions(symbol: str):
    """Get corporate actions (dividends, splits, bonuses, rights)."""
    symbol_upper = symbol.upper()
    actions = get_corporate_actions(symbol_upper)
    return {
        "symbol": symbol_upper,
        "count": len(actions),
        "data": actions,
    }


@router.get("/company/{symbol}/competitors")
def get_stock_competitors(symbol: str):
    """Get competitor analysis records."""
    symbol_upper = symbol.upper()
    comps = get_competitors(symbol_upper)
    return {
        "symbol": symbol_upper,
        "count": len(comps),
        "data": comps,
    }


# ---------------------------------------------------------------------------
# Fundamental Engine: Ratios, Scoring, Research Dossier & Peer Comparison
# ---------------------------------------------------------------------------

@router.get("/company/{symbol}/calculated-ratios", response_model=CalculatedRatiosResult)
def get_calculated_ratios(
    symbol: str,
    statement_type: StatementType = StatementType.CONSOLIDATED,
) -> CalculatedRatiosResult:
    """
    Computes institutional-grade financial ratios (CAGRs, average-balance ROE/ROCE,
    margins, cash conversion, and valuation multiples) directly from historical statements.
    """
    symbol_upper = symbol.upper()
    try:
        return compute_all_ratios(symbol_upper, statement_type=statement_type.value)
    except Exception as exc:
        logger.exception("Failed to compute ratios for %s: %s", symbol_upper, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute ratios for {symbol_upper}: {exc}",
        )


@router.get("/company/{symbol}/quality-score", response_model=QualityScoreResult)
def get_quality_score(symbol: str) -> QualityScoreResult:
    """
    Calculates 100-point fundamental quality score across 6 weighted categories
    with itemized score audit and deduction rationale.
    """
    symbol_upper = symbol.upper()
    try:
        return calculate_quality_score(symbol_upper)
    except Exception as exc:
        logger.exception("Failed to compute quality score for %s: %s", symbol_upper, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute quality score for {symbol_upper}: {exc}",
        )


@router.post("/peers/compare", response_model=PeerComparisonResponse)
def compare_peer_companies(body: PeerComparisonRequest) -> PeerComparisonResponse:
    """
    Compares 2-5 companies across 13 standardized fundamental metrics
    ensuring period and statement-type alignment.
    """
    try:
        return compare_peers(
            symbols=body.symbols,
            target_symbol=body.target_symbol,
            statement_type=body.statement_type.value,
        )
    except Exception as exc:
        logger.exception("Peer comparison failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Peer comparison failed: {exc}",
        )


@router.get("/company/{symbol}/research", response_model=CompanyResearchDossier)
def get_company_research(symbol: str) -> CompanyResearchDossier:
    """
    Get full company research dossier including multi-year statements,
    quarterly results, calculated ratios, 100-point quality score, and peer comparison.
    """
    symbol_upper = symbol.upper()
    stock = get_stock(symbol_upper)
    if not stock:
        ann_inc = get_income_statements(symbol_upper, frequency="yearly")
        if not ann_inc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Stock {symbol_upper} not found in database.",
            )
        stock_dict = {"symbol": symbol_upper, "company_name": symbol_upper}
    else:
        stock_dict = dict(stock)

    profile = get_company_profile(symbol_upper)
    ann_income = get_income_statements(symbol_upper, frequency="yearly")
    qtr_income = get_income_statements(symbol_upper, frequency="quarterly")
    b_sheets = get_balance_sheets(symbol_upper, frequency="yearly")
    c_flows = get_cash_flows(symbol_upper, frequency="yearly")
    s_patterns = get_shareholding(symbol_upper)
    r_stored = get_ratios(symbol_upper)
    c_actions = get_corporate_actions(symbol_upper)
    comps = get_competitors(symbol_upper)

    calc_ratios = None
    try:
        calc_ratios = compute_all_ratios(symbol_upper)
    except Exception as exc:
        logger.warning("Could not compute ratios for research dossier %s: %s", symbol_upper, exc)

    q_score = None
    try:
        q_score = calculate_quality_score(symbol_upper)
    except Exception as exc:
        logger.warning("Could not compute quality score for research dossier %s: %s", symbol_upper, exc)

    peers = None
    try:
        peers = compare_peers([symbol_upper], target_symbol=symbol_upper)
    except Exception as exc:
        logger.warning("Could not compute peers for research dossier %s: %s", symbol_upper, exc)

    primary_src = stock_dict.get("data_source", "demo")
    ver_status = "unverified"
    if ann_income:
        ver_status = ann_income[0].get("verification_status", "unverified")

    is_price_stale = False
    price_date = None
    if calc_ratios and calc_ratios.valuation:
        is_price_stale = calc_ratios.valuation.is_price_stale
        price_date = calc_ratios.valuation.price_date

    perf_1y = None
    try:
        perf_1y = calculate_1y_performance(symbol_upper)
    except Exception as exc:
        logger.warning("Could not calculate 1y performance for %s: %s", symbol_upper, exc)

    rs_data = None
    try:
        rs_data = calculate_relative_strength(symbol_upper)
    except Exception as exc:
        logger.warning("Could not calculate relative strength for %s: %s", symbol_upper, exc)

    dvm_data = None
    try:
        dvm_data = calculate_dvm_scores(symbol_upper)
    except Exception as exc:
        logger.warning("Could not calculate DVM scores for %s: %s", symbol_upper, exc)

    swot_data = None
    try:
        swot_data = generate_fundamental_checklist_and_swot(symbol_upper)
    except Exception as exc:
        logger.warning("Could not generate checklist and swot for %s: %s", symbol_upper, exc)

    sector_peers_data = None
    try:
        sector_peers_data = get_sector_peer_comparison(symbol_upper)
    except Exception as exc:
        logger.warning("Could not get sector peers for %s: %s", symbol_upper, exc)

    provenance = {
        "primary_source": primary_src,
        "verification_status": ver_status,
        "is_price_stale": is_price_stale,
        "price_date": price_date,
        "statement_count": len(ann_income) + len(qtr_income) + len(b_sheets) + len(c_flows),
    }

    return CompanyResearchDossier(
        symbol=symbol_upper,
        company_name=stock_dict.get("company_name", symbol_upper),
        sector=stock_dict.get("sector"),
        industry=stock_dict.get("industry"),
        isin=stock_dict.get("isin"),
        market_cap_cr=stock_dict.get("market_cap_cr"),
        current_price=stock_dict.get("close"),
        close=stock_dict.get("close"),
        daily_change_pct=stock_dict.get("daily_change_pct"),
        week_52_high=stock_dict.get("week_52_high"),
        week_52_low=stock_dict.get("week_52_low"),
        profile=profile,
        annual_income_statements=ann_income,
        quarterly_income_statements=qtr_income,
        balance_sheets=b_sheets,
        cash_flows=c_flows,
        shareholding=s_patterns,
        stored_ratios=r_stored,
        calculated_ratios=calc_ratios,
        quality_score=q_score,
        peers=peers,
        performance_1y=perf_1y,
        relative_strength=rs_data,
        dvm_scores=dvm_data,
        checklist_swot=swot_data,
        sector_peers=sector_peers_data,
        corporate_actions=c_actions,
        competitors=comps,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Advanced Equity Research Endpoints (1Y Perf, RS, DVM, SWOT, Sector Peers)
# ---------------------------------------------------------------------------

@router.get("/company/{symbol}/performance-1y")
def get_company_performance_1y(symbol: str) -> dict[str, Any]:
    """Retrieve 1-year historical price performance, start/end prices, % return and 52W range."""
    return calculate_1y_performance(symbol)


@router.get("/company/{symbol}/relative-strength")
def get_company_relative_strength(
    symbol: str,
    benchmark: str = Query("NIFTY 50", description="Benchmark symbol (default: NIFTY 50)")
) -> dict[str, Any]:
    """Retrieve Relative Strength (0-100) and 1M/3M/6M/12M relative returns vs benchmark."""
    return calculate_relative_strength(symbol, benchmark=benchmark)


@router.get("/company/{symbol}/dvm")
def get_company_dvm_scores(symbol: str) -> dict[str, Any]:
    """Retrieve 0-100 Durability, Valuation, Momentum, and Overall DVM scores with methodology audit."""
    return calculate_dvm_scores(symbol)


@router.get("/company/{symbol}/checklist-swot")
def get_company_checklist_swot(symbol: str) -> dict[str, Any]:
    """Retrieve 9-point fundamental checklist and 4-quadrant SWOT grounded in financial data."""
    return generate_fundamental_checklist_and_swot(symbol)


@router.get("/company/{symbol}/sector-peers")
def get_company_sector_peers(symbol: str) -> dict[str, Any]:
    """Retrieve sector-aware peer comparison matrix with valuation, growth, margins and DVM scores."""
    return get_sector_peer_comparison(symbol)


# ---------------------------------------------------------------------------
# Screener CSV Import
# ---------------------------------------------------------------------------

@router.post("/import/screener-csv", response_model=ScreenerCsvImportResponse)
async def import_screener_csv(
    request: Request,
    symbol: Optional[str] = Query(None, description="Explicit symbol if importing single company financial statements"),
    overwrite_verified: bool = Query(False, description="If false, skips overwriting verified official records"),
) -> ScreenerCsvImportResponse:
    """
    Import fundamental indicators or multi-period financial statements from a Screener.in CSV export.
    Does NOT scrape Screener.in.
    Applies overwrite protection: existing records with verification_status='verified'
    are preserved unless overwrite_verified=True.
    Tags imported data with source='screener_csv' and verification_status='imported'.
    """
    from app.database import update_stock_fields

    mgr = get_fundamental_manager()
    csv_provider = ScreenerCsvProvider()

    content_type = request.headers.get("content-type", "")
    raw = await request.body()
    text = ""

    if "multipart/form-data" in content_type:
        msg = email.message_from_bytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + raw)
        for part in msg.walk():
            cd = part.get("Content-Disposition", "")
            if 'name="symbol"' in cd and not symbol:
                payload = part.get_payload(decode=True)
                if payload:
                    symbol = payload.decode().strip()
            elif 'name="overwrite_verified"' in cd:
                payload = part.get_payload(decode=True)
                if payload:
                    overwrite_verified = payload.decode().strip().lower() in ("true", "1", "yes")
            elif part.get_filename() or part.get_content_type() in ("text/csv", "text/plain", "application/octet-stream"):
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        text = payload.decode("utf-8-sig")
                    except UnicodeDecodeError:
                        text = payload.decode("latin-1")
        if not text:
            try:
                decoded = raw.decode("utf-8-sig", errors="ignore")
                clean = [l for l in decoded.splitlines() if not l.startswith("--") and not l.lower().startswith("content-")]
                text = "\n".join(clean).strip()
            except Exception:
                text = ""
    else:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        if "application/json" in content_type or text.strip().startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    if "csv_content" in data:
                        text = data.get("csv_content", text)
                    if "symbol" in data and not symbol:
                        symbol = data.get("symbol")
                    if "overwrite_verified" in data:
                        overwrite_verified = bool(data.get("overwrite_verified"))
            except Exception:
                pass

    if not text.strip():
        return ScreenerCsvImportResponse(
            status="error",
            rows_imported=0,
            rows_skipped=0,
            errors=["Uploaded CSV content is empty or unreadable."],
            warnings=[],
            overwrite_verified=overwrite_verified,
        )

    csv_format = csv_provider.detect_csv_format(text)
    symbol_to_isin = mgr.get_symbol_isin_map()
    warnings: list[str] = []
    errors: list[str] = []
    imported_count = 0
    skipped_count = 0
    unmapped: list[str] = []

    if csv_format == "statements":
        target_symbol = symbol.upper() if symbol else None
        if not target_symbol:
            for line in text.splitlines()[:5]:
                for word in line.replace(",", " ").split():
                    w = word.strip().upper()
                    if w in symbol_to_isin:
                        target_symbol = w
                        break
                if target_symbol:
                    break

        if not target_symbol:
            return ScreenerCsvImportResponse(
                status="error",
                rows_imported=0,
                rows_skipped=0,
                errors=["Could not determine company symbol for financial statements CSV. Please pass ?symbol=TCS."],
                warnings=warnings,
                overwrite_verified=overwrite_verified,
            )

        isin = symbol_to_isin.get(target_symbol, target_symbol)
        parsed_data = csv_provider.parse_financial_statements_csv(
            text, symbol=target_symbol, isin=isin
        )

        for inc in parsed_data.get("income_statements", []):
            if not overwrite_verified and has_verified_record(
                "fundamental_income_statements", isin, inc.period, inc.statement_type.value, inc.frequency.value
            ):
                skipped_count += 1
                warnings.append(f"Skipped {inc.period} income statement: verified record already exists.")
            else:
                upsert_income_statement(inc)
                imported_count += 1

        for bs in parsed_data.get("balance_sheets", []):
            if not overwrite_verified and has_verified_record(
                "fundamental_balance_sheets", isin, bs.period, bs.statement_type.value, bs.frequency.value
            ):
                skipped_count += 1
                warnings.append(f"Skipped {bs.period} balance sheet: verified record already exists.")
            else:
                upsert_balance_sheet(bs)
                imported_count += 1

        for cf in parsed_data.get("cash_flows", []):
            if not overwrite_verified and has_verified_record(
                "fundamental_cash_flows", isin, cf.period, cf.statement_type.value, cf.frequency.value
            ):
                skipped_count += 1
                warnings.append(f"Skipped {cf.period} cash flow: verified record already exists.")
            else:
                upsert_cash_flow(cf)
                imported_count += 1

        for kr in parsed_data.get("ratios", []):
            if not overwrite_verified and has_verified_record(
                "fundamental_ratios", isin, kr.period, kr.statement_type.value, kr.frequency.value
            ):
                skipped_count += 1
                warnings.append(f"Skipped {kr.period} ratios: verified record already exists.")
            else:
                upsert_key_ratios(kr)
                imported_count += 1

    else:
        parsed = csv_provider.parse_csv(text, symbol_to_isin)
        unmapped = parsed.pop("_unmapped", [])  # type: ignore[call-overload]
        errors.extend(parsed.pop("_errors", []))  # type: ignore[call-overload]

        for sym, row in parsed.items():
            if not isinstance(row, dict):
                continue
            isin = row.get("isin", "")

            existing_stock = get_stock(sym)
            is_stock_verified = existing_stock and existing_stock.get("data_source") in ("upstox", "dhan")

            fields_to_update = {}
            for col in [
                "pe", "pb", "roe", "roce", "debt_equity",
                "revenue_growth_pct", "profit_growth_pct", "opm_pct",
                "promoter_holding", "promoter_pledging", "fii_holding", "dii_holding",
                "market_cap_cr", "free_cash_flow_cr",
            ]:
                if row.get(col) is not None:
                    if is_stock_verified and not overwrite_verified:
                        if existing_stock.get(col) in (None, 0):
                            fields_to_update[col] = row[col]
                    else:
                        fields_to_update[col] = row[col]

            if is_stock_verified and not overwrite_verified:
                warnings.append(f"Preserved verified market metrics for {sym} (overwrite_verified=false)")

            if fields_to_update:
                update_stock_fields(sym, fields_to_update)

            if not overwrite_verified and has_verified_record("fundamental_ratios", isin or sym, "Latest-ScreenerCSV"):
                skipped_count += 1
                warnings.append(f"Skipped Latest-ScreenerCSV ratios for {sym}: verified record exists.")
            else:
                kr = KeyRatios(
                    symbol=sym,
                    isin=isin or sym,
                    period="Latest-ScreenerCSV",
                    statement_type=StatementType.CONSOLIDATED,
                    frequency=ReportingFrequency.YEARLY,
                    pe=row.get("pe"),
                    pb=row.get("pb"),
                    roe=row.get("roe"),
                    roce=row.get("roce"),
                    debt_equity=row.get("debt_equity"),
                    opm_pct=row.get("opm_pct"),
                    revenue_growth_pct=row.get("revenue_growth_pct"),
                    profit_growth_pct=row.get("profit_growth_pct"),
                    raw_data=row,
                    source=FundamentalSource.SCREENER_CSV,
                    verification_status="imported",
                )
                upsert_key_ratios(kr)
                imported_count += 1

    return ScreenerCsvImportResponse(
        status="ok" if imported_count > 0 else ("no_data" if not errors else "error"),
        rows_imported=imported_count,
        rows_skipped=skipped_count + len(unmapped),
        unmapped_symbols=unmapped,
        errors=errors,
        warnings=warnings,
        overwrite_verified=overwrite_verified,
    )


# ---------------------------------------------------------------------------
# Sync endpoints
# ---------------------------------------------------------------------------

@router.post("/sync/{symbol}", response_model=FundamentalSyncResponse)
async def sync_stock_fundamentals(
    symbol: str,
    body: FundamentalSyncRequest,
) -> FundamentalSyncResponse:
    """
    Fetch and store fundamental data from the primary provider for a stock.
    Requires an ISIN in the stocks master table.
    """
    symbol_upper = symbol.upper()
    mgr = get_fundamental_manager()

    isin = mgr.resolve_isin(symbol_upper)
    if not isin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Stock {symbol_upper} does not have an ISIN mapped in the universe.",
        )

    if not mgr.primary_provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fundamental data provider is configured or available. Check UPSTOX_ACCESS_TOKEN.",
        )

    res = await mgr.sync_financial_data(
        symbol=symbol_upper,
        data_types=body.data_types,
        statement_type=body.statement_type,
        frequency=body.frequency,
    )

    total_records = sum(res.values())
    errors = [f"Failed to fetch {dt}" for dt, cnt in res.items() if cnt == 0]

    return FundamentalSyncResponse(
        symbol=symbol_upper,
        status="ok" if total_records > 0 else "no_data",
        records_synced=total_records,
        errors=errors,
    )


@router.post("/sync/universe")
async def sync_universe_fundamentals(
    body: FundamentalSyncRequest,
    limit: int = Query(10, ge=1, le=50),
):
    """
    Batch sync fundamental data for stocks with ISINs.
    Limits batch size to avoid provider rate limiting.
    """
    mgr = get_fundamental_manager()
    if not mgr.primary_provider:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fundamental data provider is configured or available.",
        )

    mapping = mgr.get_symbol_isin_map()
    symbols = list(mapping.keys())[:limit]

    summary: dict[str, int] = {}
    for sym in symbols:
        res = await mgr.sync_financial_data(
            symbol=sym,
            data_types=body.data_types,
            statement_type=body.statement_type,
            frequency=body.frequency,
        )
        summary[sym] = sum(res.values())

    return {
        "total_requested": len(symbols),
        "synced_stocks": summary,
        "total_records": sum(summary.values()),
    }


# ---------------------------------------------------------------------------
# Diagnostics & History
# ---------------------------------------------------------------------------

@router.get("/sync/history")
def get_history(
    symbol: Optional[str] = None,
    data_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieve audit history of sync runs."""
    hist = get_sync_history(
        symbol=symbol.upper() if symbol else None,
        data_type=data_type,
        limit=limit,
    )
    return {"count": len(hist), "items": hist}


@router.get("/metrics/counts")
def get_table_counts():
    """Retrieve row counts across all fundamental tables."""
    return {"counts": count_fundamental_records()}
