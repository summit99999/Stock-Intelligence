"""
Database layer for Stock Intelligence.
Supports dual-mode execution:
1. SQLite (default local mode)
2. PostgreSQL (Supabase / Render cloud deployment)
Sample data is seeded only if no data exists yet; real data takes priority.
"""

from __future__ import annotations

import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "stock_intelligence.db"

# PostgreSQL / Supabase connection URL
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]


def is_postgres() -> bool:
    """Return True if PostgreSQL database URL is configured."""
    return bool(DATABASE_URL and DATABASE_URL.startswith("postgresql://"))


def get_database_mode() -> str:
    """Return current active database engine name."""
    return "postgresql" if is_postgres() else "sqlite"


# ---------------------------------------------------------------------------
# PostgreSQL Query & Row Adapters
# ---------------------------------------------------------------------------

class DbRow(dict):
    """
    Dictionary row subclass that supports both string key access (row['symbol']),
    dictionary conversion (dict(row)), and 0-based integer indexing (row[0]).
    Ensures identical compatibility across SQLite and PostgreSQL query consumers.
    """
    def __init__(self, data: Dict[str, Any], keys_list: Sequence[str]):
        super().__init__(data)
        self._keys_list = list(keys_list)

    def __getitem__(self, key: Union[str, int]) -> Any:
        if isinstance(key, int):
            return super().__getitem__(self._keys_list[key])
        return super().__getitem__(key)


TABLE_PK_MAP: Dict[str, Tuple[List[str], List[str]]] = {
    "stocks": (["symbol"], [
        "company_name", "exchange", "sector", "industry", "cap_category", "isin",
        "close", "daily_change_pct", "week_52_high", "week_52_low",
        "market_cap_cr", "pe", "pb", "roe", "roce", "debt_equity",
        "revenue_growth_pct", "profit_growth_pct", "opm_pct", "free_cash_flow_cr",
        "promoter_holding", "promoter_pledging", "fii_holding", "dii_holding",
        "rsi", "macd", "macd_signal", "adx", "supertrend", "supertrend_dir",
        "ema_20", "ema_50", "ema_100", "ema_200",
        "sma_20", "sma_50", "sma_100", "sma_200",
        "volume", "relative_volume",
        "return_1d_pct", "return_1w_pct", "return_1m_pct", "return_3m_pct", "return_6m_pct", "return_1y_pct",
        "data_source", "updated_at"
    ]),
    "ohlcv": (["symbol", "interval", "timestamp"], [
        "open", "high", "low", "close", "adj_close", "volume", "source"
    ]),
    "fundamental_company_profiles": (["isin", "source"], [
        "symbol", "company_name", "industry", "sector", "exchange", "face_value",
        "market_cap_cr", "year_of_incorporation", "bse_code", "nse_code", "website",
        "description", "fetched_at"
    ]),
    "fundamental_income_statements": (["isin", "period", "statement_type", "frequency", "source"], [
        "symbol", "revenue_cr", "other_income_cr", "cost_of_revenue_cr", "gross_profit_cr",
        "operating_expenses_cr", "operating_profit_cr", "ebitda_cr", "depreciation_cr",
        "ebit_cr", "interest_expense_cr", "profit_before_tax_cr", "tax_expense_cr",
        "net_profit_cr", "eps", "diluted_eps", "period_end_date", "verification_status",
        "raw_data", "fetched_at"
    ]),
    "fundamental_balance_sheets": (["isin", "period", "statement_type", "frequency", "source"], [
        "symbol", "total_assets_cr", "current_assets_cr", "non_current_assets_cr",
        "total_liabilities_cr", "current_liabilities_cr", "non_current_liabilities_cr",
        "total_equity_cr", "share_capital_cr", "reserves_cr", "borrowings_cr",
        "period_end_date", "verification_status", "raw_data", "fetched_at"
    ]),
    "fundamental_cash_flows": (["isin", "period", "statement_type", "frequency", "source"], [
        "symbol", "operating_cf_cr", "investing_cf_cr", "financing_cf_cr",
        "net_cf_cr", "capital_expenditure_cr", "free_cash_flow_cr",
        "period_end_date", "verification_status", "raw_data", "fetched_at"
    ]),
    "fundamental_ratios": (["isin", "period", "statement_type", "frequency", "source"], [
        "symbol", "pe_ratio", "pb_ratio", "ev_ebitda", "roe_pct", "roce_pct",
        "debt_to_equity", "interest_coverage", "current_ratio", "quick_ratio",
        "dividend_yield", "opm_pct", "npm_pct", "asset_turnover", "inventory_turnover",
        "period_end_date", "verification_status", "raw_data", "fetched_at"
    ]),
    "fundamental_shareholdings": (["isin", "period", "source"], [
        "symbol", "promoter_pct", "promoter_pledged_pct", "fii_pct", "dii_pct",
        "public_pct", "government_pct", "other_pct", "total_shareholders",
        "period_end_date", "verification_status", "raw_data", "fetched_at"
    ]),
    "fundamental_corporate_actions": (["isin", "action_type", "ex_date", "source"], [
        "symbol", "record_date", "ratio", "amount", "description", "fetched_at"
    ]),
    "fundamental_competitors": (["isin", "peer_symbol", "source"], [
        "symbol", "peer_name", "market_cap_cr", "pe_ratio", "roe_pct", "fetched_at"
    ]),
    "intraday_ingestion_runs": (["id"], [
        "symbol", "provider", "provider_symbol", "exchange", "segment", "interval",
        "start_date", "end_date", "bar_count", "retrieval_timestamp", "raw_response_hash",
        "transformation_version", "provenance_classification", "data_quality_status",
        "error_message", "created_at", "actual_start_date", "actual_end_date",
        "provider_metadata_json", "session_quality_json"
    ]),
    "bar_provenance": (["symbol", "interval", "timestamp"], [
        "provider", "provider_symbol", "exchange", "segment", "retrieval_timestamp",
        "ingestion_run_id", "raw_response_hash", "transformation_version",
        "provenance_classification", "data_quality_status"
    ]),
    "observed_intraday_ohlcv": (["symbol", "interval", "timestamp"], [
        "provider_timestamp", "open", "high", "low", "close", "adj_close", "volume",
        "source", "provider", "provider_symbol", "exchange", "retrieval_timestamp",
        "ingestion_run_id", "raw_response_hash", "provenance_classification",
        "data_quality_status"
    ]),
}

AUTO_INCREMENT_TABLES = {
    "saved_screeners", "saved_custom_scanners", "custom_watchlists",
    "market_alerts", "market_alert_history", "research_trade_plans", "research_notes"
}


def safe_replace_placeholders(sql: str) -> str:
    """
    Safely replace parameter placeholder '?' with '%s' in SQL statements,
    ignoring '?' that appears inside:
    - single-quoted string literals: 'text with ?'
    - double-quoted identifier literals: "col ? name"
    - single-line SQL comments: -- comment with ?
    - multi-line block comments: /* comment with ? */
    """
    res = []
    i = 0
    n = len(sql)
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_single_quote:
            res.append(c)
            if c == "'":
                if nxt == "'":  # escaped single quote ''
                    res.append(nxt)
                    i += 1
                else:
                    in_single_quote = False
        elif in_double_quote:
            res.append(c)
            if c == '"':
                if nxt == '"':  # escaped double quote ""
                    res.append(nxt)
                    i += 1
                else:
                    in_double_quote = False
        elif in_line_comment:
            res.append(c)
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            res.append(c)
            if c == "*" and nxt == "/":
                res.append(nxt)
                i += 1
                in_block_comment = False
        else:
            if c == "-" and nxt == "-":
                in_line_comment = True
                res.append(c)
                res.append(nxt)
                i += 1
            elif c == "/" and nxt == "*":
                in_block_comment = True
                res.append(c)
                res.append(nxt)
                i += 1
            elif c == "'":
                in_single_quote = True
                res.append(c)
            elif c == '"':
                in_double_quote = True
                res.append(c)
            elif c == "?":
                res.append("%s")
            else:
                res.append(c)
        i += 1

    return "".join(res)


def adapt_sql_for_postgres(sql: str) -> Tuple[str, bool]:
    """
    Translates an SQLite query to a PostgreSQL compatible query:
    1. Replaces ? parameter placeholders with %s safely (ignoring literals/comments).
    2. Replaces datetime('now') with NOW().
    3. Translates INSERT OR REPLACE INTO <table> (<cols>) VALUES (<vals>)
       to INSERT INTO <table> (<cols>) VALUES (<vals>) ON CONFLICT (<pk>) DO UPDATE SET ...
    4. Appends RETURNING id for auto-increment tables if not present.
    Returns: (adapted_sql, should_capture_id)
    """
    s = sql.strip()
    # Replace datetime('now')
    s = re.sub(r"datetime\s*\(\s*['\"]now['\"]\s*\)", "NOW()", s, flags=re.IGNORECASE)

    # Check for INSERT OR REPLACE
    m = re.match(r"^INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)", s, flags=re.IGNORECASE)
    if m:
        table_name = m.group(1).lower()
        cols = [c.strip() for c in m.group(2).split(",")]
        vals = m.group(3)
        if table_name in TABLE_PK_MAP:
            pk_cols, _ = TABLE_PK_MAP[table_name]
            pk_str = ", ".join(pk_cols)
            cols_to_update = [c for c in cols if c.lower() not in [p.lower() for p in pk_cols]]
            update_assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols_to_update)
            s = f"INSERT INTO {m.group(1)} ({m.group(2)}) VALUES ({vals}) ON CONFLICT ({pk_str}) DO UPDATE SET {update_assignments}"
        else:
            s = f"INSERT INTO {m.group(1)} ({m.group(2)}) VALUES ({vals})"

    # Check for AUTO_INCREMENT table insert where RETURNING id is needed for cur.lastrowid
    should_capture_id = False
    m_insert = re.match(r"^INSERT\s+INTO\s+(\w+)", s, flags=re.IGNORECASE)
    if m_insert:
        table_name = m_insert.group(1).lower()
        if table_name in AUTO_INCREMENT_TABLES and "RETURNING" not in s.upper():
            s = s.rstrip("; \t\n") + " RETURNING id"
            should_capture_id = True

    # Safely replace parameter placeholders ? with %s
    s = safe_replace_placeholders(s)
    return s, should_capture_id


class PostgresCursorWrapper:
    """Wraps psycopg2 cursor to mirror sqlite3.Cursor semantics."""
    def __init__(self, raw_cursor: Any):
        self._cursor = raw_cursor
        self.lastrowid: Optional[int] = None

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def execute(self, sql: str, params: Any = None) -> PostgresCursorWrapper:
        adapted_sql, should_capture_id = adapt_sql_for_postgres(sql)
        params_tuple = tuple(params) if params is not None else None
        self._cursor.execute(adapted_sql, params_tuple)
        if should_capture_id:
            try:
                row = self._cursor.fetchone()
                if row:
                    self.lastrowid = row[0] if isinstance(row, (tuple, list)) else row.get("id")
            except Exception:
                pass
        return self

    def executemany(self, sql: str, params_list: Sequence[Any]) -> PostgresCursorWrapper:
        adapted_sql, _ = adapt_sql_for_postgres(sql)
        self._cursor.executemany(adapted_sql, params_list)
        return self

    def fetchone(self) -> Optional[DbRow]:
        try:
            row = self._cursor.fetchone()
            if row is None:
                return None
            if self._cursor.description:
                col_names = [col.name for col in self._cursor.description]
                return DbRow(dict(row), col_names)
            return row
        except Exception:
            return None

    def fetchall(self) -> List[DbRow]:
        try:
            rows = self._cursor.fetchall()
            if self._cursor.description:
                col_names = [col.name for col in self._cursor.description]
                return [DbRow(dict(r), col_names) for r in rows]
            return rows
        except Exception:
            return []

    def close(self) -> None:
        self._cursor.close()


class PostgresConnectionWrapper:
    """Wraps psycopg2 connection to mirror sqlite3.Connection semantics and context management."""
    def __init__(self, raw_conn: Any):
        self._conn = raw_conn

    def cursor(self) -> PostgresCursorWrapper:
        import psycopg2.extras
        return PostgresCursorWrapper(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, sql: str, params: Any = None) -> PostgresCursorWrapper:
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql: str, params_list: Sequence[Any]) -> PostgresCursorWrapper:
        cur = self.cursor()
        cur.executemany(sql, params_list)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self) -> PostgresConnectionWrapper:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        try:
            if exc_type is not None:
                self.rollback()
            else:
                self.commit()
        finally:
            self.close()


def connect():
    """
    Connect to the database. Automatically connects to PostgreSQL if DATABASE_URL
    is configured, otherwise defaults to local SQLite database.
    """
    if is_postgres():
        import psycopg2
        raw_conn = psycopg2.connect(DATABASE_URL)
        return PostgresConnectionWrapper(raw_conn)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con



# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

STOCKS_DDL = """
CREATE TABLE IF NOT EXISTS stocks (
    symbol              TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    exchange            TEXT NOT NULL DEFAULT 'NSE',
    sector              TEXT,
    industry            TEXT,
    cap_category        TEXT,             -- large_cap / mid_cap / small_cap
    isin                TEXT,

    -- Price
    close               REAL,
    daily_change_pct    REAL,
    week_52_high        REAL,
    week_52_low         REAL,

    -- Fundamental
    market_cap_cr       REAL,
    pe                  REAL,
    pb                  REAL,
    roe                 REAL,
    roce                REAL,
    debt_equity         REAL,
    revenue_growth_pct  REAL,
    profit_growth_pct   REAL,
    opm_pct             REAL,             -- operating profit margin
    free_cash_flow_cr   REAL,
    promoter_holding    REAL,
    promoter_pledging   REAL,
    fii_holding         REAL,
    dii_holding         REAL,

    -- Technical (latest daily values)
    rsi                 REAL,
    macd                REAL,
    macd_signal         REAL,
    adx                 REAL,
    supertrend          REAL,
    supertrend_dir      TEXT,             -- 'up' or 'down'
    ema_20              REAL,
    ema_50              REAL,
    ema_100             REAL,
    ema_200             REAL,
    sma_20              REAL,
    sma_50              REAL,
    sma_100             REAL,
    sma_200             REAL,
    volume              INTEGER,
    relative_volume     REAL,
    return_1d_pct       REAL,
    return_1w_pct       REAL,
    return_1m_pct       REAL,
    return_3m_pct       REAL,
    return_6m_pct       REAL,
    return_1y_pct       REAL,

    -- Meta
    data_source         TEXT DEFAULT 'demo',
    updated_at          TEXT
)
"""

OHLCV_DDL = """
CREATE TABLE IF NOT EXISTS ohlcv (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    interval    TEXT NOT NULL DEFAULT 'daily',
    timestamp   TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    adj_close   REAL,
    volume      INTEGER,
    source      TEXT DEFAULT 'demo',
    UNIQUE(symbol, interval, timestamp)
)
"""

DATA_UPDATES_DDL = """
CREATE TABLE IF NOT EXISTS data_updates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    provider        TEXT NOT NULL DEFAULT 'yfinance',
    last_updated    TEXT,
    bars_count      INTEGER DEFAULT 0,
    period          TEXT,
    status          TEXT DEFAULT 'pending',
    error_message   TEXT,
    UNIQUE(symbol, provider)
)
"""

INTRADAY_INGESTION_RUNS_DDL = """
CREATE TABLE IF NOT EXISTS intraday_ingestion_runs (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    segment TEXT NOT NULL DEFAULT 'EQUITY',
    interval TEXT NOT NULL DEFAULT '5m',
    start_date TEXT,
    end_date TEXT,
    bar_count INTEGER NOT NULL DEFAULT 0,
    retrieval_timestamp TEXT NOT NULL,
    raw_response_hash TEXT,
    transformation_version TEXT DEFAULT 'v1.0',
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    error_message TEXT,
    actual_start_date TEXT,
    actual_end_date TEXT,
    provider_metadata_json TEXT,
    session_quality_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

BAR_PROVENANCE_DDL = """
CREATE TABLE IF NOT EXISTS bar_provenance (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    segment TEXT NOT NULL DEFAULT 'EQUITY',
    retrieval_timestamp TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    raw_response_hash TEXT,
    transformation_version TEXT DEFAULT 'v1.0',
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    PRIMARY KEY(symbol, interval, timestamp)
)
"""

OBSERVED_INTRADAY_OHLCV_DDL = """
CREATE TABLE IF NOT EXISTS observed_intraday_ohlcv (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL DEFAULT '5m',
    timestamp TEXT NOT NULL,
    provider_timestamp TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    adj_close REAL,
    volume INTEGER NOT NULL CHECK (volume >= 0),
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    retrieval_timestamp TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    raw_response_hash TEXT NOT NULL,
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    PRIMARY KEY (symbol, interval, timestamp)
)
"""

SAVED_SCREENERS_DDL = """
CREATE TABLE IF NOT EXISTS saved_screeners (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT,
    name        TEXT NOT NULL,
    description TEXT,
    config_json TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
)
"""

SAVED_CUSTOM_SCANNERS_DDL = """
CREATE TABLE IF NOT EXISTS saved_custom_scanners (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT,
    name            TEXT NOT NULL,
    description     TEXT,
    universe        TEXT DEFAULT 'all',
    timeframe       TEXT DEFAULT '1D',
    logic_mode      TEXT DEFAULT 'AND',
    conditions_json TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""

CUSTOM_WATCHLISTS_DDL = """
CREATE TABLE IF NOT EXISTS custom_watchlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT,
    name            TEXT NOT NULL,
    description     TEXT,
    symbols_json    TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
)
"""

MARKET_ALERTS_DDL = """
CREATE TABLE IF NOT EXISTS market_alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT,
    symbol          TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    target_value    REAL,
    timeframe       TEXT DEFAULT '1D',
    note            TEXT,
    status          TEXT DEFAULT 'ACTIVE',
    created_at      TEXT DEFAULT (datetime('now')),
    last_triggered  TEXT,
    trigger_count   INTEGER DEFAULT 0
)
"""

MARKET_ALERT_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS market_alert_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT,
    alert_id        INTEGER,
    symbol          TEXT NOT NULL,
    alert_type      TEXT NOT NULL,
    condition       TEXT NOT NULL,
    triggered_value TEXT NOT NULL,
    message         TEXT,
    timestamp       TEXT DEFAULT (datetime('now'))
)
"""

RESEARCH_TRADE_PLANS_DDL = """
CREATE TABLE IF NOT EXISTS research_trade_plans (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 TEXT,
    symbol                  TEXT NOT NULL,
    exchange                TEXT NOT NULL DEFAULT 'NSE',
    setup_type              TEXT NOT NULL,
    direction               TEXT NOT NULL DEFAULT 'BULLISH',
    timeframe               TEXT NOT NULL DEFAULT '1D',
    reference_price         REAL NOT NULL,
    entry_zone_json         TEXT NOT NULL DEFAULT '{}',
    stop_loss               REAL NOT NULL,
    target_1                REAL NOT NULL,
    target_2                REAL NOT NULL,
    risk_reward_ratio       REAL NOT NULL,
    setup_score             REAL NOT NULL,
    position_size_qty       INTEGER NOT NULL DEFAULT 0,
    position_value          REAL NOT NULL DEFAULT 0.0,
    account_capital         REAL NOT NULL DEFAULT 100000.0,
    risk_pct                REAL NOT NULL DEFAULT 1.0,
    invalidation_condition  TEXT NOT NULL,
    evidence_json           TEXT NOT NULL DEFAULT '[]',
    risks_json              TEXT NOT NULL DEFAULT '[]',
    status                  TEXT NOT NULL DEFAULT 'MONITORING',
    notes                   TEXT,
    created_at              TEXT DEFAULT (datetime('now')),
    updated_at              TEXT DEFAULT (datetime('now'))
)
"""

RESEARCH_NOTES_DDL = """
CREATE TABLE IF NOT EXISTS research_notes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                 TEXT,
    symbol                  TEXT NOT NULL,
    title                   TEXT,
    note                    TEXT NOT NULL,
    tags                    TEXT,
    created_at              TEXT DEFAULT (datetime('now')),
    updated_at              TEXT DEFAULT (datetime('now'))
)
"""


# ---------------------------------------------------------------------------
# Sample data  —  ILLUSTRATIVE ONLY, not live exchange prices
# ---------------------------------------------------------------------------

SAMPLE_STOCKS = [
    # (symbol, company_name, exchange, sector, industry, cap_category, isin,
    #  close, daily_change_pct, week_52_high, week_52_low,
    #  market_cap_cr, pe, pb, roe, roce, debt_equity,
    #  revenue_growth_pct, profit_growth_pct, opm_pct, free_cash_flow_cr,
    #  promoter_holding, promoter_pledging, fii_holding, dii_holding,
    #  rsi, macd, macd_signal, adx, supertrend, supertrend_dir,
    #  ema_20, ema_50, ema_100, ema_200,
    #  sma_20, sma_50, sma_100, sma_200,
    #  volume, relative_volume,
    #  return_1d_pct, return_1w_pct, return_1m_pct, return_3m_pct, return_6m_pct, return_1y_pct,
    #  data_source, updated_at)

    ("RELIANCE", "Reliance Industries", "NSE", "Energy", "Oil & Gas", "large_cap", "INE002A01018",
     2480.0, 1.25, 2850.0, 2200.0,
     1680000, 24.5, 3.2, 10.8, 8.2, 0.42,
     12.5, 8.3, 15.2, 45000,
     50.3, 0.0, 23.1, 14.2,
     58.2, 12.5, 10.8, 28.0, 2420.0, "up",
     2455.0, 2430.0, 2390.0, 2350.0,
     2460.0, 2435.0, 2395.0, 2355.0,
     8500000, 1.2,
     1.25, 2.8, 5.1, 12.3, 8.5, 18.2,
     "demo", "2026-10-31T09:15:00"),

    ("TCS", "Tata Consultancy Services", "NSE", "IT", "IT Services", "large_cap", "INE467B01029",
     3890.0, -0.65, 4250.0, 3400.0,
     1420000, 28.1, 15.0, 51.2, 62.0, 0.08,
     8.2, 10.5, 26.4, 38000,
     72.3, 0.0, 11.5, 8.2,
     52.1, 8.3, 7.5, 22.0, 3820.0, "up",
     3870.0, 3845.0, 3810.0, 3760.0,
     3875.0, 3850.0, 3815.0, 3765.0,
     3200000, 0.9,
     -0.65, 1.2, 3.8, 8.5, 14.2, 22.0,
     "demo", "2026-10-31T09:15:00"),

    ("INFY", "Infosys", "NSE", "IT", "IT Services", "large_cap", "INE009A01021",
     1550.0, 1.82, 1780.0, 1350.0,
     645000, 25.2, 7.1, 31.0, 38.0, 0.10,
     6.8, 7.2, 22.8, 18500,
     15.1, 0.0, 34.2, 18.5,
     55.8, 6.2, 5.8, 20.0, 1520.0, "up",
     1535.0, 1510.0, 1480.0, 1440.0,
     1540.0, 1515.0, 1485.0, 1445.0,
     6800000, 1.1,
     1.82, 3.5, 6.2, 14.0, 10.8, 19.5,
     "demo", "2026-10-31T09:15:00"),

    ("HDFCBANK", "HDFC Bank", "NSE", "Banking", "Private Bank", "large_cap", "INE040A01034",
     1680.0, 0.45, 1880.0, 1430.0,
     1280000, 19.5, 2.9, 16.8, None, 0.0,
     22.5, 35.2, None, None,
     26.1, 0.0, 32.4, 25.8,
     48.5, 4.2, 3.8, 18.0, 1650.0, "up",
     1670.0, 1650.0, 1620.0, 1580.0,
     1675.0, 1655.0, 1625.0, 1585.0,
     12000000, 1.3,
     0.45, 1.8, 4.2, 9.8, 15.5, 24.0,
     "demo", "2026-10-31T09:15:00"),

    ("ICICIBANK", "ICICI Bank", "NSE", "Banking", "Private Bank", "large_cap", "INE090A01021",
     1280.0, 0.92, 1420.0, 1050.0,
     890000, 18.4, 3.1, 17.5, None, 0.0,
     18.2, 28.5, None, None,
     51.5, 0.0, 25.3, 22.1,
     56.2, 7.8, 6.9, 24.0, 1250.0, "up",
     1265.0, 1245.0, 1220.0, 1180.0,
     1270.0, 1250.0, 1225.0, 1185.0,
     9500000, 1.1,
     0.92, 2.5, 5.8, 13.2, 18.0, 28.5,
     "demo", "2026-10-31T09:15:00"),

    ("HINDUNILVR", "Hindustan Unilever", "NSE", "FMCG", "FMCG", "large_cap", "INE030A01027",
     2350.0, -0.35, 2750.0, 2150.0,
     552000, 55.2, 11.5, 120.0, 95.0, 0.0,
     2.1, -3.5, 24.8, 8200,
     61.9, 0.0, 15.2, 12.8,
     42.0, -5.2, -4.0, 15.0, 2380.0, "down",
     2365.0, 2390.0, 2420.0, 2480.0,
     2370.0, 2395.0, 2425.0, 2485.0,
     4200000, 0.8,
     -0.35, -1.2, -3.5, -8.2, -5.0, -2.8,
     "demo", "2026-10-31T09:15:00"),

    ("SUNPHARMA", "Sun Pharmaceutical", "NSE", "Pharma", "Pharmaceuticals", "large_cap", "INE044A01036",
     1710.0, 0.85, 1950.0, 1400.0,
     410000, 32.0, 5.4, 18.2, 21.0, 0.12,
     11.5, 15.8, 28.5, 6500,
     54.5, 0.0, 18.3, 14.2,
     61.5, 14.2, 12.5, 32.0, 1680.0, "up",
     1695.0, 1670.0, 1640.0, 1600.0,
     1700.0, 1675.0, 1645.0, 1605.0,
     5500000, 1.4,
     0.85, 3.2, 7.5, 18.5, 12.0, 25.0,
     "demo", "2026-10-31T09:15:00"),

    ("TATAMOTORS", "Tata Motors", "NSE", "Auto", "Automobiles", "large_cap", "INE155A01022",
     920.0, -2.35, 1100.0, 650.0,
     340000, 9.8, 2.2, 31.0, 19.0, 0.65,
     25.8, 48.2, 12.5, 12000,
     46.4, 2.8, 18.5, 16.2,
     64.5, 18.5, 16.2, 35.0, 890.0, "up",
     910.0, 880.0, 850.0, 780.0,
     915.0, 885.0, 855.0, 785.0,
     15000000, 2.2,
     -2.35, 4.5, 12.8, 28.5, 22.0, 35.0,
     "demo", "2026-10-31T09:15:00"),

    ("BHARTIARTL", "Bharti Airtel", "NSE", "Telecom", "Telecom Services", "large_cap", "INE397D01024",
     1580.0, 0.62, 1780.0, 1200.0,
     940000, 75.0, 8.5, 12.5, 10.8, 1.20,
     18.2, 52.0, 28.0, 15000,
     55.1, 0.0, 22.5, 12.8,
     54.0, 10.5, 9.2, 26.0, 1550.0, "up",
     1565.0, 1540.0, 1500.0, 1450.0,
     1570.0, 1545.0, 1505.0, 1455.0,
     7200000, 1.0,
     0.62, 2.0, 5.5, 15.0, 20.0, 32.0,
     "demo", "2026-10-31T09:15:00"),

    ("WIPRO", "Wipro", "NSE", "IT", "IT Services", "large_cap", "INE075A01022",
     465.0, -0.42, 550.0, 380.0,
     242000, 22.5, 3.8, 15.2, 18.0, 0.15,
     -2.5, 1.2, 18.5, 8500,
     73.0, 0.0, 9.8, 8.5,
     44.0, -2.5, -1.8, 14.0, 475.0, "down",
     470.0, 480.0, 490.0, 510.0,
     472.0, 482.0, 492.0, 512.0,
     8500000, 1.0,
     -0.42, -1.5, -4.2, -2.0, 5.0, 12.0,
     "demo", "2026-10-31T09:15:00"),

    ("BAJFINANCE", "Bajaj Finance", "NSE", "Financial Services", "NBFC", "large_cap", "INE296A01024",
     7250.0, 1.15, 8200.0, 6200.0,
     448000, 32.5, 7.2, 22.5, 4.5, 3.50,
     28.5, 22.0, None, None,
     55.0, 0.0, 18.2, 15.5,
     62.0, 22.5, 20.0, 30.0, 7100.0, "up",
     7180.0, 7050.0, 6900.0, 6700.0,
     7200.0, 7060.0, 6910.0, 6710.0,
     4500000, 1.5,
     1.15, 3.8, 8.5, 20.0, 12.0, 18.0,
     "demo", "2026-10-31T09:15:00"),

    ("LT", "Larsen & Toubro", "NSE", "Infrastructure", "Construction", "large_cap", "INE018A01030",
     3450.0, 0.78, 3900.0, 2900.0,
     475000, 33.5, 5.8, 15.8, 12.5, 0.85,
     15.2, 12.0, 11.5, 8500,
     52.5, 0.5, 22.0, 18.5,
     57.5, 12.0, 10.5, 28.0, 3400.0, "up",
     3430.0, 3380.0, 3320.0, 3250.0,
     3435.0, 3385.0, 3325.0, 3255.0,
     3800000, 1.2,
     0.78, 2.5, 6.0, 14.5, 10.0, 20.0,
     "demo", "2026-10-31T09:15:00"),

    ("MARUTI", "Maruti Suzuki", "NSE", "Auto", "Automobiles", "large_cap", "INE585B01010",
     12500.0, 0.55, 13800.0, 10500.0,
     392000, 28.0, 5.5, 18.5, 24.0, 0.02,
     14.5, 42.0, 12.8, 6200,
     56.2, 0.0, 18.5, 14.8,
     53.0, 8.5, 7.2, 22.0, 12300.0, "up",
     12420.0, 12300.0, 12100.0, 11800.0,
     12450.0, 12320.0, 12120.0, 11820.0,
     1200000, 0.9,
     0.55, 1.8, 5.5, 12.0, 15.5, 22.0,
     "demo", "2026-10-31T09:15:00"),

    ("ASIANPAINT", "Asian Paints", "NSE", "Consumer", "Paints", "large_cap", "INE021A01026",
     2850.0, -1.20, 3400.0, 2600.0,
     273000, 52.0, 15.2, 28.5, 35.0, 0.15,
     -1.5, -12.0, 18.5, 3500,
     52.6, 0.0, 18.5, 12.0,
     38.0, -8.5, -6.2, 12.0, 2900.0, "down",
     2880.0, 2920.0, 2980.0, 3050.0,
     2885.0, 2925.0, 2985.0, 3055.0,
     2200000, 0.7,
     -1.20, -3.5, -6.5, -10.0, -8.0, -5.0,
     "demo", "2026-10-31T09:15:00"),

    ("TITAN", "Titan Company", "NSE", "Consumer", "Jewellery", "large_cap", "INE280A01028",
     3250.0, 2.10, 3650.0, 2800.0,
     288000, 65.0, 16.5, 25.0, 30.0, 0.05,
     22.0, 18.5, 12.5, 2200,
     52.9, 0.0, 20.5, 15.8,
     68.0, 25.0, 22.0, 38.0, 3180.0, "up",
     3210.0, 3150.0, 3080.0, 3000.0,
     3220.0, 3160.0, 3090.0, 3010.0,
     3500000, 1.8,
     2.10, 5.5, 10.0, 22.0, 15.0, 28.0,
     "demo", "2026-10-31T09:15:00"),

    ("SBIN", "State Bank of India", "NSE", "Banking", "Public Bank", "large_cap", "INE062A01020",
     820.0, 0.30, 920.0, 680.0,
     732000, 10.5, 1.8, 18.2, None, 0.0,
     15.5, 22.0, None, None,
     57.5, 0.0, 10.5, 24.8,
     50.0, 3.5, 3.0, 18.0, 810.0, "up",
     815.0, 800.0, 785.0, 760.0,
     818.0, 805.0, 790.0, 765.0,
     25000000, 1.1,
     0.30, 1.5, 4.0, 10.0, 12.5, 20.0,
     "demo", "2026-10-31T09:15:00"),

    ("HCLTECH", "HCL Technologies", "NSE", "IT", "IT Services", "large_cap", "INE860A01027",
     1680.0, 0.95, 1900.0, 1400.0,
     456000, 24.8, 6.8, 24.5, 30.0, 0.08,
     7.5, 9.8, 24.0, 14000,
     60.8, 0.0, 18.2, 12.5,
     56.5, 8.8, 7.5, 24.0, 1650.0, "up",
     1665.0, 1640.0, 1610.0, 1570.0,
     1670.0, 1645.0, 1615.0, 1575.0,
     4500000, 1.0,
     0.95, 2.2, 5.8, 12.5, 10.0, 18.5,
     "demo", "2026-10-31T09:15:00"),

    ("ADANIENT", "Adani Enterprises", "NSE", "Diversified", "Conglomerate", "large_cap", "INE423A01024",
     2850.0, -1.50, 3500.0, 2200.0,
     325000, 68.0, 8.5, 12.0, 8.5, 0.95,
     32.5, 45.0, 5.5, -2500,
     72.6, 3.5, 8.5, 6.2,
     42.0, -12.0, -8.5, 15.0, 2920.0, "down",
     2900.0, 2950.0, 3020.0, 3100.0,
     2910.0, 2960.0, 3030.0, 3110.0,
     6500000, 1.8,
     -1.50, -4.0, -8.5, -12.0, 5.0, 15.0,
     "demo", "2026-10-31T09:15:00"),

    ("POWERGRID", "Power Grid Corp", "NSE", "Energy", "Power", "large_cap", "INE752E01010",
     310.0, 0.65, 350.0, 260.0,
     288000, 18.5, 3.2, 18.0, 12.5, 1.50,
     8.5, 12.0, 38.0, 8500,
     51.3, 0.0, 22.5, 18.2,
     52.0, 4.5, 3.8, 20.0, 305.0, "up",
     308.0, 302.0, 295.0, 285.0,
     309.0, 303.0, 296.0, 286.0,
     18000000, 1.0,
     0.65, 1.2, 3.5, 8.0, 10.0, 18.0,
     "demo", "2026-10-31T09:15:00"),

    ("TRENT", "Trent Limited", "NSE", "Consumer", "Retail", "large_cap", "INE849A01020",
     6245.0, 4.82, 7200.0, 3500.0,
     222000, 110.0, 42.0, 38.5, 42.0, 0.18,
     52.0, 65.0, 10.5, 850,
     37.0, 0.0, 28.5, 18.2,
     72.0, 35.0, 30.0, 45.0, 6050.0, "up",
     6100.0, 5800.0, 5400.0, 4800.0,
     6120.0, 5820.0, 5420.0, 4820.0,
     5200000, 2.5,
     4.82, 8.5, 18.0, 55.0, 45.0, 78.0,
     "demo", "2026-10-31T09:15:00"),

    ("BEL", "Bharat Electronics", "NSE", "Defence", "Electronics", "mid_cap", "INE263A01024",
     312.0, 3.65, 380.0, 180.0,
     76000, 42.0, 12.5, 28.5, 35.0, 0.02,
     35.0, 42.0, 22.5, 3200,
     51.1, 0.0, 18.5, 22.8,
     70.0, 18.5, 15.0, 42.0, 295.0, "up",
     305.0, 290.0, 265.0, 235.0,
     308.0, 292.0, 268.0, 238.0,
     35000000, 3.2,
     3.65, 8.2, 22.0, 55.0, 42.0, 72.0,
     "demo", "2026-10-31T09:15:00"),

    ("HAL", "Hindustan Aeronautics", "NSE", "Defence", "Aerospace", "large_cap", "INE066F01020",
     4120.0, 2.91, 5200.0, 2800.0,
     276000, 28.0, 8.5, 28.0, 32.0, 0.0,
     18.5, 22.0, 25.0, 5500,
     75.0, 0.0, 8.5, 12.2,
     66.0, 22.0, 18.5, 38.0, 4020.0, "up",
     4080.0, 3950.0, 3750.0, 3500.0,
     4090.0, 3960.0, 3760.0, 3510.0,
     4800000, 2.0,
     2.91, 6.5, 15.0, 35.0, 28.0, 48.0,
     "demo", "2026-10-31T09:15:00"),

    ("ONGC", "Oil & Natural Gas Corp", "NSE", "Energy", "Oil & Gas", "large_cap", "INE213A01029",
     268.0, -1.82, 320.0, 220.0,
     337000, 8.5, 1.2, 15.5, 18.0, 0.35,
     8.0, -5.0, 18.0, 12000,
     58.9, 0.0, 12.5, 18.8,
     44.0, -5.0, -3.5, 14.0, 275.0, "down",
     272.0, 278.0, 285.0, 295.0,
     274.0, 280.0, 287.0, 297.0,
     22000000, 0.9,
     -1.82, -3.5, -5.0, -8.0, -2.0, 5.0,
     "demo", "2026-10-31T09:15:00"),

    ("LTIM", "LTIMindtree", "NSE", "IT", "IT Services", "large_cap", "INE214T01019",
     5850.0, 1.20, 6500.0, 4800.0,
     173000, 35.0, 10.2, 28.0, 35.0, 0.05,
     5.5, 8.0, 22.0, 4200,
     68.6, 0.0, 12.8, 10.5,
     58.0, 12.0, 10.5, 28.0, 5750.0, "up",
     5800.0, 5720.0, 5600.0, 5450.0,
     5810.0, 5730.0, 5610.0, 5460.0,
     1500000, 1.1,
     1.20, 2.8, 6.5, 15.0, 12.0, 22.0,
     "demo", "2026-10-31T09:15:00"),

    ("COALINDIA", "Coal India", "NSE", "Mining", "Mining", "large_cap", "INE522F01014",
     485.0, -0.80, 550.0, 380.0,
     299000, 8.2, 4.5, 52.0, 58.0, 0.05,
     -5.0, -8.5, 32.0, 18000,
     63.1, 0.0, 8.5, 22.5,
     45.0, -3.5, -2.8, 16.0, 495.0, "down",
     490.0, 500.0, 510.0, 520.0,
     492.0, 502.0, 512.0, 522.0,
     12000000, 0.8,
     -0.80, -2.0, -5.5, -10.0, -3.0, 8.0,
     "demo", "2026-10-31T09:15:00"),

    # --- Mid caps ---
    ("POLYCAB", "Polycab India", "NSE", "Industrials", "Cables", "mid_cap", "INE455K01017",
     6800.0, 2.50, 7500.0, 4500.0,
     102000, 52.0, 12.5, 25.0, 30.0, 0.08,
     22.0, 28.0, 14.5, 1200,
     67.5, 0.0, 15.2, 12.0,
     65.0, 20.0, 17.5, 35.0, 6650.0, "up",
     6720.0, 6550.0, 6300.0, 5800.0,
     6740.0, 6570.0, 6320.0, 5820.0,
     850000, 1.8,
     2.50, 5.5, 12.0, 32.0, 25.0, 52.0,
     "demo", "2026-10-31T09:15:00"),

    ("DIXON", "Dixon Technologies", "NSE", "Industrials", "Electronics Manufacturing", "mid_cap", "INE935N01020",
     12800.0, 3.20, 15000.0, 7500.0,
     76000, 120.0, 35.0, 32.0, 38.0, 0.12,
     58.0, 72.0, 5.5, 450,
     34.2, 0.0, 32.5, 18.2,
     72.0, 28.0, 24.0, 42.0, 12400.0, "up",
     12600.0, 12200.0, 11500.0, 10200.0,
     12650.0, 12250.0, 11550.0, 10250.0,
     650000, 2.2,
     3.20, 7.0, 18.0, 42.0, 35.0, 68.0,
     "demo", "2026-10-31T09:15:00"),

    ("DEEPAKNTR", "Deepak Nitrite", "NSE", "Chemicals", "Specialty Chemicals", "mid_cap", "INE288B01029",
     2350.0, -0.50, 2800.0, 1800.0,
     32000, 35.0, 6.8, 20.0, 25.0, 0.18,
     -8.0, -15.0, 18.5, 800,
     48.2, 0.0, 18.5, 14.2,
     42.0, -5.0, -3.5, 15.0, 2400.0, "down",
     2380.0, 2420.0, 2480.0, 2550.0,
     2385.0, 2425.0, 2485.0, 2555.0,
     1200000, 0.9,
     -0.50, -2.0, -4.5, -8.0, 5.0, 15.0,
     "demo", "2026-10-31T09:15:00"),

    # --- Small caps ---
    ("CDSL", "Central Depository Services", "NSE", "Financial Services", "Capital Markets", "small_cap", "INE736A01011",
     1850.0, 2.80, 2200.0, 1200.0,
     19500, 55.0, 18.5, 35.0, 42.0, 0.0,
     28.0, 35.0, 65.0, 450,
     20.0, 0.0, 22.5, 28.5,
     68.0, 22.0, 18.5, 40.0, 1800.0, "up",
     1820.0, 1780.0, 1700.0, 1550.0,
     1830.0, 1790.0, 1710.0, 1560.0,
     2500000, 2.5,
     2.80, 6.5, 15.0, 38.0, 30.0, 55.0,
     "demo", "2026-10-31T09:15:00"),

    ("KPITTECH", "KPIT Technologies", "NSE", "IT", "IT Services", "small_cap", "INE524B01027",
     1450.0, 1.50, 1800.0, 900.0,
     39500, 72.0, 22.0, 30.0, 38.0, 0.05,
     42.0, 55.0, 18.5, 320,
     40.3, 0.0, 25.5, 15.8,
     66.0, 18.0, 15.5, 36.0, 1420.0, "up",
     1430.0, 1380.0, 1320.0, 1200.0,
     1435.0, 1385.0, 1325.0, 1205.0,
     3200000, 2.0,
     1.50, 4.5, 12.0, 30.0, 25.0, 60.0,
     "demo", "2026-10-31T09:15:00"),

    ("TATAELXSI", "Tata Elxsi", "NSE", "IT", "IT Services", "small_cap", "INE670A01012",
     6500.0, -1.80, 8500.0, 5800.0,
     40500, 48.0, 18.5, 35.0, 42.0, 0.0,
     12.0, 15.0, 28.5, 650,
     43.9, 0.0, 18.2, 12.5,
     40.0, -8.0, -6.0, 14.0, 6650.0, "down",
     6580.0, 6700.0, 6850.0, 7200.0,
     6600.0, 6720.0, 6870.0, 7220.0,
     450000, 0.7,
     -1.80, -4.0, -8.0, -12.0, -5.0, -18.0,
     "demo", "2026-10-31T09:15:00"),
]

# Column order for INSERT — must match SAMPLE_STOCKS tuple structure
_STOCK_COLUMNS = (
    "symbol", "company_name", "exchange", "sector", "industry", "cap_category", "isin",
    "close", "daily_change_pct", "week_52_high", "week_52_low",
    "market_cap_cr", "pe", "pb", "roe", "roce", "debt_equity",
    "revenue_growth_pct", "profit_growth_pct", "opm_pct", "free_cash_flow_cr",
    "promoter_holding", "promoter_pledging", "fii_holding", "dii_holding",
    "rsi", "macd", "macd_signal", "adx", "supertrend", "supertrend_dir",
    "ema_20", "ema_50", "ema_100", "ema_200",
    "sma_20", "sma_50", "sma_100", "sma_200",
    "volume", "relative_volume",
    "return_1d_pct", "return_1w_pct", "return_1m_pct", "return_3m_pct", "return_6m_pct", "return_1y_pct",
    "data_source", "updated_at",
)

_INSERT_SQL = (
    f"INSERT OR REPLACE INTO stocks ({', '.join(_STOCK_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _STOCK_COLUMNS)})"
)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _init_postgres_db():
    """Initialise PostgreSQL database using schema migrations and seed initial data if empty."""
    sql_path = Path(__file__).resolve().parents[2] / "database" / "supabase_migrations.sql"
    with connect() as con:
        if sql_path.exists():
            try:
                migration_sql = sql_path.read_text(encoding="utf-8")
                con.execute(migration_sql)
                con.commit()
                logger.info("PostgreSQL schema successfully initialized from supabase_migrations.sql")
            except Exception as e:
                logger.warning("Could not run full supabase_migrations.sql (may already exist or restricted): %s", e)
                con.rollback()
        con.execute(OBSERVED_INTRADAY_OHLCV_DDL)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_observed_intraday_run "
            "ON observed_intraday_ohlcv (ingestion_run_id)"
        )

        # Seed sample data ONLY when the stocks table is empty
        try:
            count_row = con.execute("SELECT COUNT(*) FROM stocks").fetchone()
            count = count_row[0] if count_row else 0
            if count == 0:
                con.executemany(_INSERT_SQL, SAMPLE_STOCKS)
                con.commit()
                logger.info("Seeded %d sample stocks into PostgreSQL database", len(SAMPLE_STOCKS))
        except Exception as e:
            logger.warning("Error checking or seeding PostgreSQL stocks: %s", e)

        # Seed initial custom watchlists if empty
        try:
            wl_row = con.execute("SELECT COUNT(*) FROM custom_watchlists").fetchone()
            wl_count = wl_row[0] if wl_row else 0
            if wl_count == 0:
                import json
                default_wl = [
                    ("Core NIFTY Leaders", "Large-cap compounders and market leaders", json.dumps(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "BHARTIARTL"])),
                    ("High Momentum & Breakouts", "Active breakout and high RVOL candidates", json.dumps(["TRENT", "TATAMOTORS", "SUNPHARMA", "LT"])),
                    ("Capital Goods & Defense", "Heavy engineering and defense focus", json.dumps(["LT", "NTPC", "POWERGRID", "JSWSTEEL"])),
                ]
                con.executemany(
                    "INSERT INTO custom_watchlists (name, description, symbols_json) VALUES (?, ?, ?)",
                    default_wl,
                )
                con.commit()
        except Exception as e:
            logger.warning("Error seeding watchlists: %s", e)


def init_db():
    if is_postgres():
        _init_postgres_db()
        # Initialise fundamental data tables (additive)
        try:
            from app.fundamental_db import init_fundamental_tables
            init_fundamental_tables()
            from app.services.fundamental_seeder import seed_fundamental_data
            seed_fundamental_data()
        except Exception as e:
            logger.warning("Could not initialise fundamental tables in postgres: %s", e)
        return

    with connect() as con:
        con.execute(STOCKS_DDL)
        con.execute(OHLCV_DDL)
        try:
            con.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_int_ts ON ohlcv (symbol, interval, timestamp)")
        except Exception:
            pass
        con.execute(SAVED_SCREENERS_DDL)
        con.execute(DATA_UPDATES_DDL)
        con.execute(SAVED_CUSTOM_SCANNERS_DDL)
        con.execute(CUSTOM_WATCHLISTS_DDL)
        con.execute(MARKET_ALERTS_DDL)
        con.execute(MARKET_ALERT_HISTORY_DDL)
        con.execute(RESEARCH_TRADE_PLANS_DDL)
        con.execute(RESEARCH_NOTES_DDL)
        con.execute(INTRADAY_INGESTION_RUNS_DDL)
        for column in ("actual_start_date", "actual_end_date", "provider_metadata_json", "session_quality_json"):
            try:
                con.execute(f"SELECT {column} FROM intraday_ingestion_runs LIMIT 1")
            except sqlite3.OperationalError:
                con.execute(f"ALTER TABLE intraday_ingestion_runs ADD COLUMN {column} TEXT")
        con.execute(BAR_PROVENANCE_DDL)
        con.execute(OBSERVED_INTRADAY_OHLCV_DDL)
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_observed_intraday_sym_int_ts "
            "ON observed_intraday_ohlcv (symbol, interval, timestamp)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_observed_intraday_run "
            "ON observed_intraday_ohlcv (ingestion_run_id)"
        )

        # Add adj_close column if upgrading from old schema
        try:
            con.execute("SELECT adj_close FROM ohlcv LIMIT 1")
        except sqlite3.OperationalError:
            con.execute("ALTER TABLE ohlcv ADD COLUMN adj_close REAL")

        # Add user_id column if upgrading from old SQLite schema
        user_tables = [
            "saved_screeners", "saved_custom_scanners", "custom_watchlists",
            "market_alerts", "market_alert_history", "research_trade_plans", "research_notes"
        ]
        for tbl in user_tables:
            try:
                con.execute(f"ALTER TABLE {tbl} ADD COLUMN user_id TEXT")
            except Exception:
                pass

        # Seed sample data ONLY when the stocks table is empty
        count = con.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        if count == 0:
            con.executemany(_INSERT_SQL, SAMPLE_STOCKS)

        # Seed VolumeLens 7-point breakout preset into saved_screeners if missing
        try:
            vl_check = con.execute("SELECT COUNT(*) FROM saved_screeners WHERE name LIKE 'VolumeLens%'").fetchone()[0]
            if vl_check == 0:
                import json
                vl_config = json.dumps({
                    "min_relative_volume": 1.5,
                    "min_rsi": 55.0,
                    "max_rsi": 70.0,
                    "max_debt_equity": 1.0,
                    "min_roe": 12.0,
                    "page_size": 50,
                })
                con.execute(
                    "INSERT INTO saved_screeners (name, description, config_json) VALUES (?, ?, ?)",
                    (
                        "VolumeLens 7-Point Breakout Strategy",
                        "Signature multi-factor setup: 20-day consolidation breakout, RVOL >= 1.5x, stacked MAs, RSI 55-70, D/E <= 1.0, ROE >= 12%.",
                        vl_config,
                    ),
                )
        except Exception:
            pass

        # Seed initial custom watchlists if empty
        try:
            wl_count = con.execute("SELECT COUNT(*) FROM custom_watchlists").fetchone()[0]
            if wl_count == 0:
                import json
                default_wl = [
                    ("Core NIFTY Leaders", "Large-cap compounders and market leaders", json.dumps(["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "BHARTIARTL"])),
                    ("High Momentum & Breakouts", "Active breakout and high RVOL candidates", json.dumps(["TRENT", "TATAMOTORS", "SUNPHARMA", "LT"])),
                    ("Capital Goods & Defense", "Heavy engineering and defense focus", json.dumps(["LT", "NTPC", "POWERGRID", "JSWSTEEL"])),
                ]
                con.executemany(
                    "INSERT INTO custom_watchlists (name, description, symbols_json) VALUES (?, ?, ?)",
                    default_wl,
                )
        except Exception:
            pass

        # Seed initial market alerts if empty
        try:
            alt_count = con.execute("SELECT COUNT(*) FROM market_alerts").fetchone()[0]
            if alt_count == 0:
                default_alerts = [
                    ("RELIANCE", "PRICE_ABOVE", 2500.0, "1D", "Key resistance breakout test", "ACTIVE", 0),
                    ("TCS", "RSI_BELOW", 35.0, "1D", "Potential mean reversion dip", "ACTIVE", 1),
                    ("TATAMOTORS", "VOLUME_SPIKE", 1.8, "1D", "Institutional volume absorption", "ACTIVE", 2),
                    ("HDFCBANK", "PRICE_BELOW", 1650.0, "1D", "Major swing support violation", "ACTIVE", 0),
                ]
                con.executemany(
                    "INSERT INTO market_alerts (symbol, alert_type, target_value, timeframe, note, status, trigger_count) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    default_alerts,
                )
        except Exception:
            pass

        con.commit()

    # Initialise fundamental data tables (additive)
    try:
        from app.fundamental_db import init_fundamental_tables
        init_fundamental_tables()
        from app.services.fundamental_seeder import seed_fundamental_data
        seed_fundamental_data()
    except Exception as e:
        logger.warning("Could not initialise fundamental tables: %s", e)



# ---------------------------------------------------------------------------
# Stock queries
# ---------------------------------------------------------------------------

def list_stocks(
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    cap_category: Optional[str] = None,
    search: Optional[str] = None,
):
    """Return stocks, optionally filtered by universe criteria."""
    clauses = []
    params: list = []
    if exchange:
        clauses.append("exchange = ?")
        params.append(exchange.upper())
    if sector:
        clauses.append("sector = ?")
        params.append(sector)
    if cap_category:
        clauses.append("cap_category = ?")
        params.append(cap_category)
    if search:
        clauses.append("(symbol LIKE ? OR company_name LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT * FROM stocks{where} ORDER BY market_cap_cr DESC"
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def get_stock(symbol: str):
    with connect() as con:
        row = con.execute("SELECT * FROM stocks WHERE symbol = ?", (symbol,)).fetchone()
        return dict(row) if row else None


def get_bars(symbol: str, interval: str = "daily", exclude_synthetic: bool = False):
    with connect() as con:
        if interval == "5m":
            query = """
                SELECT symbol, timestamp, open, high, low, close, volume, source, adj_close
                FROM observed_intraday_ohlcv
                WHERE symbol = ? AND interval = ?
                UNION ALL
                SELECT b.symbol, b.timestamp, b.open, b.high, b.low, b.close, b.volume, b.source, b.adj_close
                FROM ohlcv b
                WHERE b.symbol = ? AND b.interval = ?
                  AND NOT EXISTS (
                      SELECT 1 FROM observed_intraday_ohlcv o
                      WHERE o.symbol = b.symbol
                        AND o.interval = b.interval
                        AND substr(o.timestamp, 1, 10) = substr(b.timestamp, 1, 10)
                  )
            """
            params: list[Any] = [symbol, interval, symbol, interval]
            if exclude_synthetic:
                query = query.replace(
                    "WHERE symbol = ? AND interval = ?",
                    "WHERE symbol = ? AND interval = ? AND provenance_classification LIKE 'OBSERVED%'",
                    1,
                )
                query += (
                    " AND (b.source IS NULL OR (b.source NOT LIKE '%calibrated%' "
                    "AND b.source NOT LIKE '%synthetic%' AND b.source NOT LIKE '%mock%'))"
                )
            query += " ORDER BY timestamp"
            rows = con.execute(query, params).fetchall()
            return [dict(r) for r in rows]

        query = (
            "SELECT timestamp, open, high, low, close, volume, source, adj_close "
            "FROM ohlcv WHERE symbol = ? AND interval = ?"
        )
        params: list[Any] = [symbol, interval]
        if exclude_synthetic:
            query += " AND (source IS NULL OR (source NOT LIKE '%calibrated%' AND source NOT LIKE '%synthetic%' AND source NOT LIKE '%mock%'))"
        query += " ORDER BY timestamp"
        rows = con.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Intraday Provenance & Ingestion Run Helpers (Phase 14.4)
# ---------------------------------------------------------------------------

def record_ingestion_run(run_data: dict) -> str:
    """Record an intraday historical ingestion run for provenance tracking."""
    run_id = str(run_data.get("id") or uuid.uuid4())
    sql = (
        "INSERT INTO intraday_ingestion_runs "
        "(id, symbol, provider, provider_symbol, exchange, segment, interval, "
        "start_date, end_date, bar_count, retrieval_timestamp, raw_response_hash, "
        "transformation_version, provenance_classification, data_quality_status, error_message, "
        "actual_start_date, actual_end_date, provider_metadata_json, session_quality_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    with connect() as con:
        con.execute(sql, (
            run_id,
            run_data.get("symbol", "").upper(),
            run_data.get("provider", "unknown"),
            run_data.get("provider_symbol", ""),
            run_data.get("exchange", "NSE"),
            run_data.get("segment", "EQUITY"),
            run_data.get("interval", "5m"),
            run_data.get("start_date"),
            run_data.get("end_date"),
            int(run_data.get("bar_count", 0)),
            run_data.get("retrieval_timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            run_data.get("raw_response_hash"),
            run_data.get("transformation_version", "v1.0"),
            run_data.get("provenance_classification", "UNKNOWN"),
            run_data.get("data_quality_status", "UNKNOWN"),
            run_data.get("error_message"),
            run_data.get("actual_start_date"),
            run_data.get("actual_end_date"),
            run_data.get("provider_metadata_json"),
            run_data.get("session_quality_json"),
        ))
        con.commit()
    return run_id


def persist_intraday_ingestion(
    run_data: dict,
    bars: list[dict],
    provenance_records: list[dict],
) -> tuple[str, int]:
    """Atomically save one audited ingestion run and its validated observed bars."""
    run_id = str(run_data.get("id") or uuid.uuid4())
    retrieval_timestamp = run_data.get("retrieval_timestamp") or datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    run_sql = (
        "INSERT INTO intraday_ingestion_runs "
        "(id, symbol, provider, provider_symbol, exchange, segment, interval, "
        "start_date, end_date, bar_count, retrieval_timestamp, raw_response_hash, "
        "transformation_version, provenance_classification, data_quality_status, error_message, "
        "actual_start_date, actual_end_date, provider_metadata_json, session_quality_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    bar_sql = (
        "INSERT INTO observed_intraday_ohlcv "
        "(symbol, interval, timestamp, provider_timestamp, open, high, low, close, adj_close, "
        "volume, source, provider, provider_symbol, exchange, retrieval_timestamp, ingestion_run_id, "
        "raw_response_hash, provenance_classification, data_quality_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (symbol, interval, timestamp) DO NOTHING"
    )
    provenance_sql = (
        "INSERT INTO bar_provenance "
        "(symbol, interval, timestamp, provider, provider_symbol, exchange, segment, "
        "retrieval_timestamp, ingestion_run_id, raw_response_hash, transformation_version, "
        "provenance_classification, data_quality_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (symbol, interval, timestamp) DO NOTHING"
    )

    with connect() as con:
        con.execute(run_sql, (
            run_id,
            str(run_data.get("symbol", "")).upper(),
            run_data.get("provider", "unknown"),
            run_data.get("provider_symbol", ""),
            run_data.get("exchange", "NSE"),
            run_data.get("segment", "EQUITY"),
            run_data.get("interval", "5m"),
            run_data.get("start_date"),
            run_data.get("end_date"),
            int(run_data.get("bar_count", len(bars))),
            retrieval_timestamp,
            run_data.get("raw_response_hash"),
            run_data.get("transformation_version", "v1.0"),
            run_data.get("provenance_classification", "UNKNOWN"),
            run_data.get("data_quality_status", "UNKNOWN"),
            run_data.get("error_message"),
            run_data.get("actual_start_date"),
            run_data.get("actual_end_date"),
            run_data.get("provider_metadata_json"),
            run_data.get("session_quality_json"),
        ))

        if bars:
            cur = con.executemany(bar_sql, [
                (
                    str(bar.get("symbol", run_data.get("symbol", ""))).upper(),
                    bar.get("interval", run_data.get("interval", "5m")),
                    bar.get("timestamp"),
                    bar.get("provider_timestamp"),
                    bar.get("open"),
                    bar.get("high"),
                    bar.get("low"),
                    bar.get("close"),
                    bar.get("adj_close"),
                    bar.get("volume"),
                    bar.get("source"),
                    bar.get("provider", run_data.get("provider")),
                    bar.get("provider_symbol", run_data.get("provider_symbol")),
                    bar.get("exchange", run_data.get("exchange", "NSE")),
                    bar.get("retrieval_timestamp", retrieval_timestamp),
                    run_id,
                    bar.get("raw_response_hash", run_data.get("raw_response_hash")),
                    bar.get("provenance_classification", "UNKNOWN"),
                    bar.get("data_quality_status", "UNKNOWN"),
                )
                for bar in bars
            ])
            inserted_count = max(cur.rowcount, 0)
        else:
            inserted_count = 0

        if provenance_records:
            con.executemany(provenance_sql, [
                (
                    str(item.get("symbol", run_data.get("symbol", ""))).upper(),
                    item.get("interval", run_data.get("interval", "5m")),
                    item.get("timestamp"),
                    item.get("provider", run_data.get("provider", "unknown")),
                    item.get("provider_symbol", run_data.get("provider_symbol", "")),
                    item.get("exchange", run_data.get("exchange", "NSE")),
                    item.get("segment", "EQUITY"),
                    item.get("retrieval_timestamp", retrieval_timestamp),
                    run_id,
                    item.get("raw_response_hash", run_data.get("raw_response_hash")),
                    item.get("transformation_version", "v1.0"),
                    item.get("provenance_classification", "UNKNOWN"),
                    item.get("data_quality_status", "UNKNOWN"),
                )
                for item in provenance_records
            ])
    return run_id, inserted_count


def get_ingestion_run(run_id: str) -> Optional[dict]:
    """Retrieve details for a specific ingestion run."""
    with connect() as con:
        row = con.execute("SELECT * FROM intraday_ingestion_runs WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def list_ingestion_runs(symbol: Optional[str] = None, limit: int = 50) -> list[dict]:
    """List recent intraday ingestion runs, optionally filtered by symbol."""
    with connect() as con:
        if symbol:
            rows = con.execute(
                "SELECT * FROM intraday_ingestion_runs WHERE symbol = ? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper(), limit)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM intraday_ingestion_runs ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def record_bar_provenance_batch(records: list[dict]) -> int:
    """Record provenance metadata for a batch of ingested bars."""
    if not records:
        return 0
    sql = (
        "INSERT OR REPLACE INTO bar_provenance "
        "(symbol, interval, timestamp, provider, provider_symbol, exchange, segment, "
        "retrieval_timestamp, ingestion_run_id, raw_response_hash, transformation_version, "
        "provenance_classification, data_quality_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    rows = [
        (
            r.get("symbol", "").upper(),
            r.get("interval", "5m"),
            r.get("timestamp"),
            r.get("provider", "unknown"),
            r.get("provider_symbol", ""),
            r.get("exchange", "NSE"),
            r.get("segment", "EQUITY"),
            r.get("retrieval_timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            r.get("ingestion_run_id", ""),
            r.get("raw_response_hash"),
            r.get("transformation_version", "v1.0"),
            r.get("provenance_classification", "UNKNOWN"),
            r.get("data_quality_status", "UNKNOWN"),
        )
        for r in records
    ]
    with connect() as con:
        con.executemany(sql, rows)
        con.commit()
    return len(rows)


def get_bar_provenance(symbol: str, interval: str, timestamp: str) -> Optional[dict]:
    """Retrieve provenance record for a specific bar."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM bar_provenance WHERE symbol = ? AND interval = ? AND timestamp = ?",
            (symbol.upper(), interval, timestamp)
        ).fetchone()
        return dict(row) if row else None


def get_bars_provenance_map(symbol: str, interval: str = "5m") -> dict[str, dict]:
    """Retrieve mapping of timestamp -> provenance dict for all bars of a symbol/interval."""
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM bar_provenance WHERE symbol = ? AND interval = ?",
            (symbol.upper(), interval)
        ).fetchall()
        return {r["timestamp"]: dict(r) for r in rows}


def get_sectors():
    """Return distinct sectors."""
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT sector FROM stocks WHERE sector IS NOT NULL ORDER BY sector"
        ).fetchall()
        return [r["sector"] for r in rows]


def get_exchanges():
    """Return distinct exchanges."""
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT exchange FROM stocks WHERE exchange IS NOT NULL ORDER BY exchange"
        ).fetchall()
        return [r["exchange"] for r in rows]


# ---------------------------------------------------------------------------
# Saved screeners
# ---------------------------------------------------------------------------

def _build_user_filter(user_id: Optional[str], table_prefix: str = "") -> Tuple[str, list]:
    """Helper to build consistent tenant-isolated user_id SQL clauses."""
    prefix = f"{table_prefix}." if table_prefix else ""
    local_ids = {"local-operator", "00000000-0000-0000-0000-000000000000"}
    if user_id in local_ids:
        return f"({prefix}user_id = ? OR {prefix}user_id IS NULL)", [user_id]
    elif user_id:
        return f"{prefix}user_id = ?", [user_id]
    return "", []


def save_screener(name: str, description: str, config_json: str, user_id: Optional[str] = None) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO saved_screeners (name, description, config_json, user_id) VALUES (?, ?, ?, ?)",
            (name, description, config_json, user_id),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def list_saved_screeners(user_id: Optional[str] = None):
    clause, params = _build_user_filter(user_id)
    where = f" WHERE {clause}" if clause else ""
    with connect() as con:
        rows = con.execute(
            f"SELECT id, name, description, config_json, created_at, updated_at "
            f"FROM saved_screeners{where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_saved_screener(screener_id: int, user_id: Optional[str] = None):
    clause, params = _build_user_filter(user_id)
    sql = "SELECT id, name, description, config_json, created_at, updated_at FROM saved_screeners WHERE id = ?"
    all_params = [screener_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        row = con.execute(sql, all_params).fetchone()
        return dict(row) if row else None


def delete_saved_screener(screener_id: int, user_id: Optional[str] = None) -> bool:
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM saved_screeners WHERE id = ?"
    all_params = [screener_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Saved Custom Scanners (Phase 11)
# ---------------------------------------------------------------------------

def save_custom_scanner(
    name: str,
    description: str,
    universe: str,
    timeframe: str,
    logic_mode: str,
    conditions_json: str,
    user_id: Optional[str] = None,
) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO saved_custom_scanners (name, description, universe, timeframe, logic_mode, conditions_json, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (name, description, universe, timeframe, logic_mode, conditions_json, user_id),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def list_custom_scanners(user_id: Optional[str] = None) -> list[dict]:
    clause, params = _build_user_filter(user_id)
    where = f" WHERE {clause}" if clause else ""
    with connect() as con:
        rows = con.execute(
            f"SELECT id, name, description, universe, timeframe, logic_mode, conditions_json, created_at, updated_at "
            f"FROM saved_custom_scanners{where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_custom_scanner(scanner_id: int, user_id: Optional[str] = None) -> Optional[dict]:
    clause, params = _build_user_filter(user_id)
    sql = "SELECT id, name, description, universe, timeframe, logic_mode, conditions_json, created_at, updated_at FROM saved_custom_scanners WHERE id = ?"
    all_params = [scanner_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        row = con.execute(sql, all_params).fetchone()
        return dict(row) if row else None


def update_custom_scanner(
    scanner_id: int,
    name: str,
    description: str,
    universe: str,
    timeframe: str,
    logic_mode: str,
    conditions_json: str,
    user_id: Optional[str] = None,
) -> bool:
    clause, params = _build_user_filter(user_id)
    sql = (
        "UPDATE saved_custom_scanners SET name = ?, description = ?, universe = ?, timeframe = ?, "
        "logic_mode = ?, conditions_json = ?, updated_at = datetime('now') WHERE id = ?"
    )
    all_params = [name, description, universe, timeframe, logic_mode, conditions_json, scanner_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


def delete_custom_scanner(scanner_id: int, user_id: Optional[str] = None) -> bool:
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM saved_custom_scanners WHERE id = ?"
    all_params = [scanner_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Custom Watchlists (Phase 11)
# ---------------------------------------------------------------------------

def list_custom_watchlists(user_id: Optional[str] = None) -> list[dict]:
    clause, params = _build_user_filter(user_id)
    where = f" WHERE {clause}" if clause else ""
    with connect() as con:
        rows = con.execute(
            f"SELECT id, name, description, symbols_json, created_at, updated_at "
            f"FROM custom_watchlists{where} ORDER BY updated_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def get_custom_watchlist(watchlist_id: int, user_id: Optional[str] = None) -> Optional[dict]:
    clause, params = _build_user_filter(user_id)
    sql = "SELECT id, name, description, symbols_json, created_at, updated_at FROM custom_watchlists WHERE id = ?"
    all_params = [watchlist_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        row = con.execute(sql, all_params).fetchone()
        return dict(row) if row else None


def create_custom_watchlist(name: str, description: str = "", symbols: Optional[list[str]] = None, user_id: Optional[str] = None) -> int:
    import json
    symbols_json = json.dumps([s.upper() for s in (symbols or [])])
    with connect() as con:
        cur = con.execute(
            "INSERT INTO custom_watchlists (name, description, symbols_json, user_id) VALUES (?, ?, ?, ?)",
            (name, description, symbols_json, user_id),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def update_custom_watchlist(
    watchlist_id: int,
    name: str,
    description: str = "",
    symbols: Optional[list[str]] = None,
    user_id: Optional[str] = None,
) -> bool:
    import json
    symbols_json = json.dumps([s.upper() for s in (symbols or [])])
    clause, params = _build_user_filter(user_id)
    sql = (
        "UPDATE custom_watchlists SET name = ?, description = ?, symbols_json = ?, updated_at = datetime('now') "
        "WHERE id = ?"
    )
    all_params = [name, description, symbols_json, watchlist_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


def delete_custom_watchlist(watchlist_id: int, user_id: Optional[str] = None) -> bool:
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM custom_watchlists WHERE id = ?"
    all_params = [watchlist_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


def add_symbol_to_watchlist(watchlist_id: int, symbol: str, user_id: Optional[str] = None) -> bool:
    import json
    sym = symbol.upper()
    wl = get_custom_watchlist(watchlist_id, user_id=user_id)
    if not wl:
        return False
    try:
        symbols = json.loads(wl.get("symbols_json", "[]"))
    except Exception:
        symbols = []
    if sym not in symbols:
        symbols.append(sym)
        return update_custom_watchlist(
            watchlist_id=watchlist_id,
            name=wl["name"],
            description=wl.get("description", ""),
            symbols=symbols,
            user_id=user_id,
        )
    return True


def remove_symbol_from_watchlist(watchlist_id: int, symbol: str, user_id: Optional[str] = None) -> bool:
    import json
    sym = symbol.upper()
    wl = get_custom_watchlist(watchlist_id, user_id=user_id)
    if not wl:
        return False
    try:
        symbols = json.loads(wl.get("symbols_json", "[]"))
    except Exception:
        symbols = []
    if sym in symbols:
        symbols = [s for s in symbols if s != sym]
        return update_custom_watchlist(
            watchlist_id=watchlist_id,
            name=wl["name"],
            description=wl.get("description", ""),
            symbols=symbols,
            user_id=user_id,
        )
    return True


# ---------------------------------------------------------------------------
# Market Alerts & History (Phase 11)
# ---------------------------------------------------------------------------

def list_market_alerts(status: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
    clauses = []
    params = []
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    u_clause, u_params = _build_user_filter(user_id)
    if u_clause:
        clauses.append(u_clause)
        params.extend(u_params)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as con:
        rows = con.execute(f"SELECT * FROM market_alerts{where} ORDER BY created_at DESC", params).fetchall()
        return [dict(r) for r in rows]


def get_market_alert(alert_id: int, user_id: Optional[str] = None) -> Optional[dict]:
    clause, params = _build_user_filter(user_id)
    sql = "SELECT * FROM market_alerts WHERE id = ?"
    all_params = [alert_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        row = con.execute(sql, all_params).fetchone()
        return dict(row) if row else None


def create_market_alert(
    symbol: str,
    alert_type: str,
    target_value: Optional[float] = None,
    timeframe: str = "1D",
    note: str = "",
    user_id: Optional[str] = None,
) -> int:
    with connect() as con:
        cur = con.execute(
            "INSERT INTO market_alerts (symbol, alert_type, target_value, timeframe, note, status, user_id) "
            "VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?)",
            (symbol.upper(), alert_type.upper(), target_value, timeframe, note, user_id),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def update_market_alert(
    alert_id: int,
    status: Optional[str] = None,
    target_value: Optional[float] = None,
    note: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    fields = []
    params = []
    if status is not None:
        fields.append("status = ?")
        params.append(status.upper())
    if target_value is not None:
        fields.append("target_value = ?")
        params.append(target_value)
    if note is not None:
        fields.append("note = ?")
        params.append(note)
    if not fields:
        return False
    params.append(alert_id)
    clause, u_params = _build_user_filter(user_id)
    sql = f"UPDATE market_alerts SET {', '.join(fields)} WHERE id = ?"
    if clause:
        sql += f" AND {clause}"
        params.extend(u_params)
    with connect() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount > 0


def delete_market_alert(alert_id: int, user_id: Optional[str] = None) -> bool:
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM market_alerts WHERE id = ?"
    all_params = [alert_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


def record_market_alert_trigger(
    alert_id: int,
    symbol: str,
    alert_type: str,
    condition: str,
    triggered_value: str,
    message: str = "",
    user_id: Optional[str] = None,
) -> int:
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as con:
        cur = con.execute(
            "INSERT INTO market_alert_history (alert_id, symbol, alert_type, condition, triggered_value, message, timestamp, user_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (alert_id, symbol.upper(), alert_type.upper(), condition, triggered_value, message, now_iso, user_id),
        )
        con.execute(
            "UPDATE market_alerts SET last_triggered = ?, trigger_count = trigger_count + 1 WHERE id = ?",
            (now_iso, alert_id),
        )
        con.commit()
        return cur.lastrowid  # type: ignore[return-value]


def get_market_alert_history(limit: int = 50, user_id: Optional[str] = None) -> list[dict]:
    clause, params = _build_user_filter(user_id)
    where = f" WHERE {clause}" if clause else ""
    with connect() as con:
        rows = con.execute(
            f"SELECT * FROM market_alert_history{where} ORDER BY id DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]


def clear_market_alert_history(user_id: Optional[str] = None) -> int:
    clause, params = _build_user_filter(user_id)
    where = f" WHERE {clause}" if clause else ""
    with connect() as con:
        cur = con.execute(f"DELETE FROM market_alert_history{where}", params)
        con.commit()
        return cur.rowcount



# ---------------------------------------------------------------------------
# OHLCV — upsert price bars
# ---------------------------------------------------------------------------

def upsert_ohlcv(
    symbol: str,
    bars: list[dict],
    interval: str = "daily",
    source: str = "yfinance",
) -> int:
    """
    Insert or replace OHLCV bars for a symbol.  Returns the number of rows written.

    Each dict in ``bars`` should have keys:
        date, open, high, low, close, adj_close (optional), volume
    """
    if not bars:
        return 0
    sql = (
        "INSERT OR REPLACE INTO ohlcv "
        "(symbol, interval, timestamp, open, high, low, close, adj_close, volume, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    rows = [
        (
            symbol,
            interval,
            b.get("timestamp") or b.get("date"),
            b.get("open"),
            b.get("high"),
            b.get("low"),
            b.get("close"),
            b.get("adj_close"),
            b.get("volume"),
            source,
        )
        for b in bars
    ]
    with connect() as con:
        con.executemany(sql, rows)
        con.commit()
    return len(rows)


def get_latest_bar_date(symbol: str, interval: str = "daily") -> Optional[str]:
    """Return the latest timestamp string for a symbol, or None if no data."""
    with connect() as con:
        row = con.execute(
            "SELECT MAX(timestamp) AS latest FROM ohlcv WHERE symbol = ? AND interval = ?",
            (symbol, interval),
        ).fetchone()
        return row["latest"] if row and row["latest"] else None


def get_ohlcv_count(symbol: str, interval: str = "daily") -> int:
    """Return the number of bars stored for a symbol."""
    with connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS cnt FROM ohlcv WHERE symbol = ? AND interval = ?",
            (symbol, interval),
        ).fetchone()
        return row["cnt"] if row else 0


# ---------------------------------------------------------------------------
# Data-update tracking
# ---------------------------------------------------------------------------

def upsert_data_update(
    symbol: str,
    provider: str = "yfinance",
    bars_count: int = 0,
    period: Optional[str] = None,
    status: str = "ok",
    error_message: Optional[str] = None,
) -> None:
    """Insert or update the data_updates status row for a symbol."""
    now = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        con.execute(
            "INSERT INTO data_updates (symbol, provider, last_updated, bars_count, period, status, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(symbol, provider) DO UPDATE SET "
            "last_updated=excluded.last_updated, bars_count=excluded.bars_count, "
            "period=excluded.period, status=excluded.status, error_message=excluded.error_message",
            (symbol, provider, now, bars_count, period, status, error_message),
        )
        con.commit()


def get_data_update(symbol: str, provider: str = "yfinance") -> Optional[dict]:
    """Get the data-update status for a symbol."""
    with connect() as con:
        row = con.execute(
            "SELECT * FROM data_updates WHERE symbol = ? AND provider = ?",
            (symbol, provider),
        ).fetchone()
        return dict(row) if row else None


def list_data_updates() -> list[dict]:
    """Return all data-update status rows."""
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM data_updates ORDER BY last_updated DESC"
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stock-record updates (merge real data into the stocks table)
# ---------------------------------------------------------------------------

def update_stock_fields(symbol: str, fields: dict) -> bool:
    """
    Update specific columns for a stock.
    Only non-None values in ``fields`` are written.
    Returns True if a row was updated.
    """
    if not fields:
        return False
    set_clauses = []
    params = []
    for key, val in fields.items():
        if val is not None:
            set_clauses.append(f"{key} = ?")
            params.append(val)
    if not set_clauses:
        return False
    params.append(symbol)
    sql = f"UPDATE stocks SET {', '.join(set_clauses)} WHERE symbol = ?"
    with connect() as con:
        cur = con.execute(sql, params)
        con.commit()
        return cur.rowcount > 0


def get_all_symbols() -> list[str]:
    """Return all stock symbols from the master table."""
    with connect() as con:
        rows = con.execute("SELECT symbol FROM stocks ORDER BY symbol").fetchall()
        return [r["symbol"] for r in rows]


# ---------------------------------------------------------------------------
# Research Trade Plans & Notes Persistence (Phase 12)
# ---------------------------------------------------------------------------

def save_research_trade_plan(plan_data: dict, user_id: Optional[str] = None) -> dict:
    """Save or create a research trade plan in the database."""
    import json
    u_id = user_id or plan_data.get("user_id")
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO research_trade_plans (
                symbol, exchange, setup_type, direction, timeframe,
                reference_price, entry_zone_json, stop_loss, target_1, target_2,
                risk_reward_ratio, setup_score, position_size_qty, position_value,
                account_capital, risk_pct, invalidation_condition, evidence_json,
                risks_json, status, notes, user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(plan_data.get("symbol", "")).upper(),
                str(plan_data.get("exchange", "NSE")).upper(),
                str(plan_data.get("setup_type", "CUSTOM")),
                str(plan_data.get("direction", "BULLISH")).upper(),
                str(plan_data.get("timeframe", "1D")),
                float(plan_data.get("reference_price", 0.0)),
                json.dumps(plan_data.get("entry_zone", {})),
                float(plan_data.get("stop_loss", 0.0)),
                float(plan_data.get("target_1", 0.0)),
                float(plan_data.get("target_2", 0.0)),
                float(plan_data.get("risk_reward_ratio", 0.0)),
                float(plan_data.get("setup_score", 0.0)),
                int(plan_data.get("position_size_qty", 0)),
                float(plan_data.get("position_value", 0.0)),
                float(plan_data.get("account_capital", 100000.0)),
                float(plan_data.get("risk_pct", 1.0)),
                str(plan_data.get("invalidation_condition", "")),
                json.dumps(plan_data.get("evidence", [])),
                json.dumps(plan_data.get("risks", [])),
                str(plan_data.get("status", "MONITORING")).upper(),
                plan_data.get("notes"),
                u_id,
            ),
        )
        plan_id = cur.lastrowid
        con.commit()
        return get_research_trade_plan(plan_id) or {}


def get_research_trade_plan(plan_id: int, user_id: Optional[str] = None) -> Optional[dict]:
    """Retrieve a single research trade plan by ID."""
    import json
    clause, params = _build_user_filter(user_id)
    sql = "SELECT * FROM research_trade_plans WHERE id = ?"
    all_params = [plan_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        row = con.execute(sql, all_params).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["entry_zone"] = json.loads(d.get("entry_zone_json") or "{}")
            d["evidence"] = json.loads(d.get("evidence_json") or "[]")
            d["risks"] = json.loads(d.get("risks_json") or "[]")
        except Exception:
            pass
        return d


def list_research_trade_plans(symbol: Optional[str] = None, status: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
    """List research trade plans optionally filtered by symbol, status, or user."""
    import json
    query = "SELECT * FROM research_trade_plans"
    params = []
    clauses = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    if status:
        clauses.append("status = ?")
        params.append(status.upper())
    u_clause, u_params = _build_user_filter(user_id)
    if u_clause:
        clauses.append(u_clause)
        params.extend(u_params)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY created_at DESC"

    with connect() as con:
        rows = con.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["entry_zone"] = json.loads(d.get("entry_zone_json") or "{}")
                d["evidence"] = json.loads(d.get("evidence_json") or "[]")
                d["risks"] = json.loads(d.get("risks_json") or "[]")
            except Exception:
                pass
            result.append(d)
        return result


def update_research_trade_plan(plan_id: int, updates: dict, user_id: Optional[str] = None) -> Optional[dict]:
    """Update status, notes, or execution review of a research trade plan."""
    allowed = {"status", "notes"}
    clauses = []
    params = []
    for k, v in updates.items():
        if k in allowed and v is not None:
            clauses.append(f"{k} = ?")
            params.append(v)
    if not clauses:
        return get_research_trade_plan(plan_id, user_id=user_id)
    clauses.append("updated_at = datetime('now')")
    params.append(plan_id)
    sql = f"UPDATE research_trade_plans SET {', '.join(clauses)} WHERE id = ?"
    u_clause, u_params = _build_user_filter(user_id)
    if u_clause:
        sql += f" AND {u_clause}"
        params.extend(u_params)
    with connect() as con:
        cur = con.execute(sql, params)
        con.commit()
        if cur.rowcount > 0:
            return get_research_trade_plan(plan_id, user_id=user_id)
        return None


def delete_research_trade_plan(plan_id: int, user_id: Optional[str] = None) -> bool:
    """Delete a research trade plan by ID."""
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM research_trade_plans WHERE id = ?"
    all_params = [plan_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0


def save_research_note(symbol: str, note: str, title: Optional[str] = None, tags: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """Save a manual qualitative research note for a stock."""
    with connect() as con:
        cur = con.execute(
            "INSERT INTO research_notes (symbol, title, note, tags, user_id) VALUES (?, ?, ?, ?, ?)",
            (symbol.upper(), title, note, tags, user_id),
        )
        note_id = cur.lastrowid
        con.commit()
        clause, params = _build_user_filter(user_id)
        sql = "SELECT * FROM research_notes WHERE id = ?"
        all_params = [note_id]
        if clause:
            sql += f" AND {clause}"
            all_params.extend(params)
        row = con.execute(sql, all_params).fetchone()
        return dict(row) if row else {}


def list_research_notes(symbol: Optional[str] = None, user_id: Optional[str] = None) -> list[dict]:
    """List research notes optionally filtered by symbol or user."""
    clauses = []
    params = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    u_clause, u_params = _build_user_filter(user_id)
    if u_clause:
        clauses.append(u_clause)
        params.extend(u_params)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as con:
        rows = con.execute(f"SELECT * FROM research_notes{where} ORDER BY created_at DESC", params).fetchall()
        return [dict(r) for r in rows]


def delete_research_note(note_id: int, user_id: Optional[str] = None) -> bool:
    """Delete a research note by ID."""
    clause, params = _build_user_filter(user_id)
    sql = "DELETE FROM research_notes WHERE id = ?"
    all_params = [note_id]
    if clause:
        sql += f" AND {clause}"
        all_params.extend(params)
    with connect() as con:
        cur = con.execute(sql, all_params)
        con.commit()
        return cur.rowcount > 0
