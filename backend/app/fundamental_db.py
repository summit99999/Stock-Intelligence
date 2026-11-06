"""
Fundamental data database layer.

Separate module from database.py to keep Phase 5A additive.
Uses the same SQLite database but creates new tables for fundamental data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.database import connect, is_postgres
from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    Competitor,
    CorporateAction,
    IncomeStatement,
    KeyRatios,
    ShareholdingPattern,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DDL — new tables (additive, never modifies existing tables)
# ---------------------------------------------------------------------------

FUNDAMENTAL_PROFILES_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_company_profiles (
    symbol          TEXT NOT NULL,
    isin            TEXT NOT NULL,
    company_name    TEXT,
    industry        TEXT,
    sector          TEXT,
    exchange        TEXT,
    face_value      REAL,
    market_cap_cr   REAL,
    year_of_incorporation INTEGER,
    bse_code        TEXT,
    nse_code        TEXT,
    website         TEXT,
    description     TEXT,
    source          TEXT NOT NULL DEFAULT 'demo',
    fetched_at      TEXT,
    PRIMARY KEY (isin, source)
)
"""

FUNDAMENTAL_INCOME_STATEMENTS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_income_statements (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    revenue_cr          REAL,
    other_income_cr     REAL,
    cost_of_revenue_cr  REAL,
    gross_profit_cr     REAL,
    operating_expenses_cr REAL,
    operating_profit_cr REAL,
    ebitda_cr           REAL,
    depreciation_cr     REAL,
    ebit_cr             REAL,
    interest_expense_cr REAL,
    profit_before_tax_cr REAL,
    tax_expense_cr      REAL,
    net_profit_cr       REAL,
    eps                 REAL,
    diluted_eps         REAL,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TEXT,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
)
"""

FUNDAMENTAL_BALANCE_SHEETS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_balance_sheets (
    symbol                  TEXT NOT NULL,
    isin                    TEXT NOT NULL,
    period                  TEXT NOT NULL,
    statement_type          TEXT NOT NULL DEFAULT 'consolidated',
    frequency               TEXT NOT NULL DEFAULT 'yearly',
    total_assets_cr         REAL,
    current_assets_cr       REAL,
    non_current_assets_cr   REAL,
    total_liabilities_cr    REAL,
    current_liabilities_cr  REAL,
    non_current_liabilities_cr REAL,
    total_equity_cr         REAL,
    share_capital_cr        REAL,
    reserves_cr             REAL,
    total_debt_cr           REAL,
    borrowings_cr           REAL,
    cash_and_equivalents_cr REAL,
    book_value_per_share    REAL,
    period_end_date         TEXT,
    verification_status     TEXT DEFAULT 'unverified',
    raw_data                TEXT,
    source                  TEXT NOT NULL DEFAULT 'demo',
    fetched_at              TEXT,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
)
"""

FUNDAMENTAL_CASH_FLOWS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_cash_flows (
    symbol                  TEXT NOT NULL,
    isin                    TEXT NOT NULL,
    period                  TEXT NOT NULL,
    statement_type          TEXT NOT NULL DEFAULT 'consolidated',
    frequency               TEXT NOT NULL DEFAULT 'yearly',
    operating_cash_flow_cr  REAL,
    investing_cash_flow_cr  REAL,
    financing_cash_flow_cr  REAL,
    net_cash_flow_cr        REAL,
    capex_cr                REAL,
    free_cash_flow_cr       REAL,
    period_end_date         TEXT,
    verification_status     TEXT DEFAULT 'unverified',
    raw_data                TEXT,
    source                  TEXT NOT NULL DEFAULT 'demo',
    fetched_at              TEXT,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
)
"""

FUNDAMENTAL_RATIOS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_ratios (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    pe                  REAL,
    pb                  REAL,
    ev_ebitda           REAL,
    roe                 REAL,
    roce                REAL,
    debt_equity         REAL,
    current_ratio       REAL,
    quick_ratio         REAL,
    interest_coverage   REAL,
    dividend_yield      REAL,
    dividend_payout     REAL,
    opm_pct             REAL,
    npm_pct             REAL,
    revenue_growth_pct  REAL,
    profit_growth_pct   REAL,
    asset_turnover      REAL,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TEXT,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
)
"""

FUNDAMENTAL_SHAREHOLDINGS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_shareholdings (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    promoter_holding    REAL,
    promoter_pledging   REAL,
    fii_holding         REAL,
    dii_holding         REAL,
    public_holding      REAL,
    government_holding  REAL,
    total_shares        INTEGER,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TEXT,
    PRIMARY KEY (isin, period, source)
)
"""

FUNDAMENTAL_CORPORATE_ACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_corporate_actions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    isin            TEXT NOT NULL,
    action_type     TEXT NOT NULL,
    ex_date         TEXT,
    record_date     TEXT,
    description     TEXT,
    value           REAL,
    raw_data        TEXT,
    source          TEXT NOT NULL DEFAULT 'demo',
    fetched_at      TEXT,
    UNIQUE(isin, action_type, ex_date, source)
)
"""

FUNDAMENTAL_COMPETITORS_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_competitors (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    competitor_name     TEXT,
    competitor_isin     TEXT,
    market_cap_cr       REAL,
    pe                  REAL,
    revenue_cr          REAL,
    net_profit_cr       REAL,
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TEXT,
    UNIQUE(isin, competitor_isin, source)
)
"""

FUNDAMENTAL_SYNC_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS fundamental_sync_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    isin            TEXT NOT NULL,
    provider        TEXT NOT NULL,
    data_type       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    records_fetched INTEGER DEFAULT 0,
    started_at      TEXT,
    completed_at    TEXT,
    error_message   TEXT
)
"""

# Index for faster sync-history lookups
SYNC_HISTORY_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_sync_history_symbol
    ON fundamental_sync_history (symbol, data_type, provider)
"""


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------

def _migrate_fundamental_columns(con) -> None:
    """Safely apply additive column migrations for existing SQLite databases."""
    migrations = [
        ("fundamental_income_statements", "other_income_cr", "REAL"),
        ("fundamental_income_statements", "period_end_date", "TEXT"),
        ("fundamental_income_statements", "verification_status", "TEXT DEFAULT 'unverified'"),
        ("fundamental_balance_sheets", "borrowings_cr", "REAL"),
        ("fundamental_balance_sheets", "period_end_date", "TEXT"),
        ("fundamental_balance_sheets", "verification_status", "TEXT DEFAULT 'unverified'"),
        ("fundamental_cash_flows", "period_end_date", "TEXT"),
        ("fundamental_cash_flows", "verification_status", "TEXT DEFAULT 'unverified'"),
        ("fundamental_ratios", "period_end_date", "TEXT"),
        ("fundamental_ratios", "verification_status", "TEXT DEFAULT 'unverified'"),
        ("fundamental_shareholdings", "period_end_date", "TEXT"),
        ("fundamental_shareholdings", "verification_status", "TEXT DEFAULT 'unverified'"),
    ]
    for table, col, col_type in migrations:
        try:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
        except Exception:
            pass  # Already present or table created anew with full DDL


def init_fundamental_tables() -> None:
    """Create all fundamental tables and apply migrations. Safe to call multiple times."""
    if is_postgres():
        logger.info("Fundamental tables verified for PostgreSQL mode")
        return
    with connect() as con:
        con.execute(FUNDAMENTAL_PROFILES_DDL)
        con.execute(FUNDAMENTAL_INCOME_STATEMENTS_DDL)
        con.execute(FUNDAMENTAL_BALANCE_SHEETS_DDL)
        con.execute(FUNDAMENTAL_CASH_FLOWS_DDL)
        con.execute(FUNDAMENTAL_RATIOS_DDL)
        con.execute(FUNDAMENTAL_SHAREHOLDINGS_DDL)
        con.execute(FUNDAMENTAL_CORPORATE_ACTIONS_DDL)
        con.execute(FUNDAMENTAL_COMPETITORS_DDL)
        con.execute(FUNDAMENTAL_SYNC_HISTORY_DDL)
        con.execute(SYNC_HISTORY_INDEX_DDL)
        _migrate_fundamental_columns(con)
        con.commit()
    logger.info("Fundamental tables initialised and migrated")


# ---------------------------------------------------------------------------
# Upsert helpers  (INSERT OR REPLACE on composite PK)
# ---------------------------------------------------------------------------

def _to_json(data: Any) -> Optional[str]:
    if data is None:
        return None
    return json.dumps(data, default=str)


def upsert_company_profile(profile: CompanyProfile) -> None:
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_company_profiles
               (symbol, isin, company_name, industry, sector, exchange,
                face_value, market_cap_cr, year_of_incorporation,
                bse_code, nse_code, website, description,
                source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.symbol, profile.isin, profile.company_name,
                profile.industry, profile.sector, profile.exchange,
                profile.face_value, profile.market_cap_cr,
                profile.year_of_incorporation,
                profile.bse_code, profile.nse_code,
                profile.website, profile.description,
                profile.source.value, profile.fetched_at,
            ),
        )
        con.commit()


def upsert_income_statement(stmt: IncomeStatement) -> None:
    ver_status = getattr(stmt, "verification_status", "unverified") or "unverified"
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_income_statements
               (symbol, isin, period, statement_type, frequency,
                revenue_cr, other_income_cr, cost_of_revenue_cr, gross_profit_cr,
                operating_expenses_cr, operating_profit_cr, ebitda_cr,
                depreciation_cr, ebit_cr, interest_expense_cr,
                profit_before_tax_cr, tax_expense_cr, net_profit_cr,
                eps, diluted_eps, period_end_date, verification_status,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                stmt.symbol, stmt.isin, stmt.period,
                stmt.statement_type.value, stmt.frequency.value,
                stmt.revenue_cr, stmt.other_income_cr, stmt.cost_of_revenue_cr, stmt.gross_profit_cr,
                stmt.operating_expenses_cr, stmt.operating_profit_cr, stmt.ebitda_cr,
                stmt.depreciation_cr, stmt.ebit_cr, stmt.interest_expense_cr,
                stmt.profit_before_tax_cr, stmt.tax_expense_cr, stmt.net_profit_cr,
                stmt.eps, stmt.diluted_eps, stmt.period_end_date, ver_status,
                _to_json(stmt.raw_data),
                stmt.source.value, stmt.fetched_at,
            ),
        )
        con.commit()


def upsert_balance_sheet(bs: BalanceSheet) -> None:
    ver_status = getattr(bs, "verification_status", "unverified") or "unverified"
    borrowings = getattr(bs, "borrowings_cr", None)
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_balance_sheets
               (symbol, isin, period, statement_type, frequency,
                total_assets_cr, current_assets_cr, non_current_assets_cr,
                total_liabilities_cr, current_liabilities_cr, non_current_liabilities_cr,
                total_equity_cr, share_capital_cr, reserves_cr,
                total_debt_cr, borrowings_cr, cash_and_equivalents_cr, book_value_per_share,
                period_end_date, verification_status,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                bs.symbol, bs.isin, bs.period,
                bs.statement_type.value, bs.frequency.value,
                bs.total_assets_cr, bs.current_assets_cr, bs.non_current_assets_cr,
                bs.total_liabilities_cr, bs.current_liabilities_cr, bs.non_current_liabilities_cr,
                bs.total_equity_cr, bs.share_capital_cr, bs.reserves_cr,
                bs.total_debt_cr, borrowings, bs.cash_and_equivalents_cr, bs.book_value_per_share,
                bs.period_end_date, ver_status,
                _to_json(bs.raw_data), bs.source.value, bs.fetched_at,
            ),
        )
        con.commit()


def upsert_cash_flow(cf: CashFlow) -> None:
    ver_status = getattr(cf, "verification_status", "unverified") or "unverified"
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_cash_flows
               (symbol, isin, period, statement_type, frequency,
                operating_cash_flow_cr, investing_cash_flow_cr, financing_cash_flow_cr,
                net_cash_flow_cr, capex_cr, free_cash_flow_cr,
                period_end_date, verification_status,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cf.symbol, cf.isin, cf.period,
                cf.statement_type.value, cf.frequency.value,
                cf.operating_cash_flow_cr, cf.investing_cash_flow_cr,
                cf.financing_cash_flow_cr, cf.net_cash_flow_cr,
                cf.capex_cr, cf.free_cash_flow_cr,
                cf.period_end_date, ver_status,
                _to_json(cf.raw_data), cf.source.value, cf.fetched_at,
            ),
        )
        con.commit()


def upsert_key_ratios(kr: KeyRatios) -> None:
    ver_status = getattr(kr, "verification_status", "unverified") or "unverified"
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_ratios
               (symbol, isin, period, statement_type, frequency,
                pe, pb, ev_ebitda, roe, roce, debt_equity,
                current_ratio, quick_ratio, interest_coverage,
                dividend_yield, dividend_payout, opm_pct, npm_pct,
                revenue_growth_pct, profit_growth_pct, asset_turnover,
                period_end_date, verification_status,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                kr.symbol, kr.isin, kr.period,
                kr.statement_type.value, kr.frequency.value,
                kr.pe, kr.pb, kr.ev_ebitda, kr.roe, kr.roce, kr.debt_equity,
                kr.current_ratio, kr.quick_ratio, kr.interest_coverage,
                kr.dividend_yield, kr.dividend_payout, kr.opm_pct, kr.npm_pct,
                kr.revenue_growth_pct, kr.profit_growth_pct, kr.asset_turnover,
                kr.period_end_date, ver_status,
                _to_json(kr.raw_data), kr.source.value, kr.fetched_at,
            ),
        )
        con.commit()


def upsert_shareholding(sh: ShareholdingPattern) -> None:
    ver_status = getattr(sh, "verification_status", "unverified") or "unverified"
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_shareholdings
               (symbol, isin, period, promoter_holding, promoter_pledging,
                fii_holding, dii_holding, public_holding, government_holding,
                total_shares, period_end_date, verification_status,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sh.symbol, sh.isin, sh.period,
                sh.promoter_holding, sh.promoter_pledging,
                sh.fii_holding, sh.dii_holding,
                sh.public_holding, sh.government_holding,
                sh.total_shares,
                sh.period_end_date, ver_status,
                _to_json(sh.raw_data), sh.source.value, sh.fetched_at,
            ),
        )
        con.commit()




def upsert_corporate_action(ca: CorporateAction) -> None:
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_corporate_actions
               (symbol, isin, action_type, ex_date, record_date,
                description, value, raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ca.symbol, ca.isin, ca.action_type,
                ca.ex_date, ca.record_date,
                ca.description, ca.value,
                _to_json(ca.raw_data), ca.source.value, ca.fetched_at,
            ),
        )
        con.commit()


def upsert_competitor(comp: Competitor) -> None:
    with connect() as con:
        con.execute(
            """INSERT OR REPLACE INTO fundamental_competitors
               (symbol, isin, competitor_name, competitor_isin,
                market_cap_cr, pe, revenue_cr, net_profit_cr,
                raw_data, source, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                comp.symbol, comp.isin, comp.competitor_name,
                comp.competitor_isin, comp.market_cap_cr, comp.pe,
                comp.revenue_cr, comp.net_profit_cr,
                _to_json(comp.raw_data), comp.source.value, comp.fetched_at,
            ),
        )
        con.commit()


# ---------------------------------------------------------------------------
# Sync history
# ---------------------------------------------------------------------------

def has_verified_record(
    table: str,
    isin: str,
    period: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> bool:
    """Check if an authoritative verified record already exists for the given period."""
    allowed_tables = {
        "fundamental_income_statements",
        "fundamental_balance_sheets",
        "fundamental_cash_flows",
        "fundamental_ratios",
        "fundamental_shareholdings",
    }
    if table not in allowed_tables:
        return False
    with connect() as con:
        if table == "fundamental_shareholdings":
            row = con.execute(
                f"SELECT 1 FROM {table} WHERE isin = ? AND period = ? AND verification_status = 'verified' LIMIT 1",
                (isin, period),
            ).fetchone()
        else:
            row = con.execute(
                f"SELECT 1 FROM {table} WHERE isin = ? AND period = ? AND statement_type = ? AND frequency = ? AND verification_status = 'verified' LIMIT 1",
                (isin, period, statement_type, frequency),
            ).fetchone()
        return bool(row)


def record_sync_history(
    symbol: str,
    isin: str,
    provider: str,
    data_type: str,
    status: str,
    records_fetched: int = 0,
    error_message: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            """INSERT INTO fundamental_sync_history
               (symbol, isin, provider, data_type, status,
                records_fetched, started_at, completed_at, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (symbol, isin, provider, data_type, status,
             records_fetched, now, now, error_message),
        )
        con.commit()


def get_sync_history(
    symbol: Optional[str] = None,
    data_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol)
    if data_type:
        clauses.append("data_type = ?")
        params.append(data_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with connect() as con:
        rows = con.execute(
            f"SELECT * FROM fundamental_sync_history{where} ORDER BY completed_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_sync_summary() -> dict[str, Any]:
    """Return aggregate sync counts by data_type and status."""
    with connect() as con:
        rows = con.execute(
            "SELECT data_type, status, COUNT(*) as cnt "
            "FROM fundamental_sync_history GROUP BY data_type, status"
        ).fetchall()
        summary: dict[str, Any] = {}
        for r in rows:
            dt = r["data_type"]
            if dt not in summary:
                summary[dt] = {}
            summary[dt][r["status"]] = r["cnt"]
        return summary


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_company_profile(symbol: str) -> Optional[dict]:
    with connect() as con:
        row = con.execute(
            "SELECT * FROM fundamental_company_profiles WHERE symbol = ? ORDER BY fetched_at DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return dict(row) if row else None


def get_income_statements(
    symbol: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_income_statements "
            "WHERE symbol = ? AND statement_type = ? AND frequency = ? "
            "ORDER BY period DESC, CASE source WHEN 'upstox_api' THEN 1 WHEN 'dhan' THEN 2 WHEN 'screener_csv' THEN 3 ELSE 4 END ASC, CASE verification_status WHEN 'verified' THEN 1 WHEN 'imported' THEN 2 ELSE 3 END ASC",
            (symbol, statement_type, frequency),
        ).fetchall()
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = dict(r)
            p = str(d.get("period", ""))
            if p not in seen:
                seen.add(p)
                deduped.append(d)
        return deduped


def get_balance_sheets(
    symbol: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_balance_sheets "
            "WHERE symbol = ? AND statement_type = ? AND frequency = ? "
            "ORDER BY period DESC, CASE source WHEN 'upstox_api' THEN 1 WHEN 'dhan' THEN 2 WHEN 'screener_csv' THEN 3 ELSE 4 END ASC, CASE verification_status WHEN 'verified' THEN 1 WHEN 'imported' THEN 2 ELSE 3 END ASC",
            (symbol, statement_type, frequency),
        ).fetchall()
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = dict(r)
            p = str(d.get("period", ""))
            if p not in seen:
                seen.add(p)
                deduped.append(d)
        return deduped


def get_cash_flows(
    symbol: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_cash_flows "
            "WHERE symbol = ? AND statement_type = ? AND frequency = ? "
            "ORDER BY period DESC, CASE source WHEN 'upstox_api' THEN 1 WHEN 'dhan' THEN 2 WHEN 'screener_csv' THEN 3 ELSE 4 END ASC, CASE verification_status WHEN 'verified' THEN 1 WHEN 'imported' THEN 2 ELSE 3 END ASC",
            (symbol, statement_type, frequency),
        ).fetchall()
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = dict(r)
            p = str(d.get("period", ""))
            if p not in seen:
                seen.add(p)
                deduped.append(d)
        return deduped


def get_ratios(
    symbol: str,
    statement_type: str = "consolidated",
    frequency: str = "yearly",
) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_ratios "
            "WHERE symbol = ? AND statement_type = ? AND frequency = ? "
            "ORDER BY period DESC, CASE source WHEN 'upstox_api' THEN 1 WHEN 'dhan' THEN 2 WHEN 'screener_csv' THEN 3 ELSE 4 END ASC, CASE verification_status WHEN 'verified' THEN 1 WHEN 'imported' THEN 2 ELSE 3 END ASC",
            (symbol, statement_type, frequency),
        ).fetchall()
        seen: set[str] = set()
        deduped: list[dict] = []
        for r in rows:
            d = dict(r)
            p = str(d.get("period", ""))
            if p not in seen:
                seen.add(p)
                deduped.append(d)
        return deduped


def get_shareholding(symbol: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_shareholdings "
            "WHERE symbol = ? ORDER BY period DESC",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_corporate_actions(symbol: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_corporate_actions "
            "WHERE symbol = ? ORDER BY ex_date DESC",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_competitors(symbol: str) -> list[dict]:
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM fundamental_competitors WHERE symbol = ?",
            (symbol,),
        ).fetchall()
        return [dict(r) for r in rows]


def count_fundamental_records() -> dict[str, int]:
    """Return row counts for each fundamental table."""
    tables = [
        "fundamental_company_profiles",
        "fundamental_income_statements",
        "fundamental_balance_sheets",
        "fundamental_cash_flows",
        "fundamental_ratios",
        "fundamental_shareholdings",
        "fundamental_corporate_actions",
        "fundamental_competitors",
        "fundamental_sync_history",
    ]
    counts: dict[str, int] = {}
    with connect() as con:
        for tbl in tables:
            try:
                row = con.execute(f"SELECT COUNT(*) AS cnt FROM {tbl}").fetchone()
                counts[tbl] = row["cnt"] if row else 0
            except Exception:
                counts[tbl] = 0
    return counts
