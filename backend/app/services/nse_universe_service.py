"""
NSE & BSE Universe & Instrument Master Service — Phase 7B.

Provides:
1. Dynamic full NSE/BSE market coverage (~2,757 mainboard equities + SMEs + indices + options).
2. Suggested `market_instruments` canonical table with indexes on exchange, symbol, isin, type.
3. Fast prefix and ranked autocomplete search across symbols, company names, and ISINs.
4. Auto-seeding all eligible instruments into `stocks` table for full-market screener coverage.
5. Official NIFTY 50 Option Chain with dynamic expiries, strike filters, OI, Greeks, and Max Pain.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import math
import os
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "NSE.json.gz")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "stock_intelligence.db")

NIFTY_50_CONSTITUENTS = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL", "BHARTIARTL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL", "GRASIM", "HCLTECH", "HDFCBANK",
    "HDFCLIFE", "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC", "INDUSINDBK",
    "INFY", "JSWSTEEL", "KOTAKBANK", "LT", "LTIM", "M&M", "MARUTI", "NESTLEIND", "NTPC",
    "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN", "SUNPHARMA", "TCS",
    "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO"
}

BANK_NIFTY_CONSTITUENTS = {
    "HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "INDUSINDBK",
    "BANKBARODA", "PNB", "AUBANK", "FEDERALBNK", "IDFCFIRSTB", "BANDHANBNK"
}

BSE_SENSEX_CONSTITUENTS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT",
    "MARUTI", "TITAN", "SUNPHARMA", "ULTRACEMCO", "TATAMOTORS", "NESTLEIND",
    "NTPC", "POWERGRID", "M&M", "TATASTEEL", "JSWSTEEL", "BAJAJFINSV", "TECHM",
    "HCLTECH", "INDUSINDBK", "WIPRO"
}


def get_db_connection() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, timeout=20.0)
    con.row_factory = sqlite3.Row
    return con


def init_market_instruments_tables():
    """Ensure market_instruments and nse_instruments tables exist and are properly indexed."""
    with get_db_connection() as con:
        # 1. Canonical market_instruments table (Part 2.1)
        con.execute("""
            CREATE TABLE IF NOT EXISTS market_instruments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                trading_symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                segment TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                instrument_key TEXT NOT NULL,
                exchange_token TEXT,
                isin TEXT,
                company_name TEXT NOT NULL,
                lot_size INTEGER DEFAULT 1,
                tick_size REAL DEFAULT 0.05,
                expiry_date TEXT,
                strike_price REAL,
                option_type TEXT,
                is_active INTEGER DEFAULT 1,
                is_nifty50 INTEGER DEFAULT 0,
                is_nifty100 INTEGER DEFAULT 0,
                is_nifty500 INTEGER DEFAULT 0,
                is_fno INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT (datetime('now')),
                provider TEXT DEFAULT 'UPSTOX'
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_exch_sym ON market_instruments(exchange, symbol)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_symbol ON market_instruments(symbol)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_isin ON market_instruments(isin)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_type ON market_instruments(instrument_type)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_fno ON market_instruments(is_fno)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_mi_nifty50 ON market_instruments(is_nifty50)")

        # 2. Backward-compatible nse_instruments table
        con.execute("""
            CREATE TABLE IF NOT EXISTS nse_instruments (
                symbol TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                short_name TEXT,
                isin TEXT,
                instrument_key TEXT NOT NULL,
                exchange_token TEXT,
                segment TEXT NOT NULL,
                instrument_type TEXT NOT NULL,
                lot_size INTEGER DEFAULT 1,
                tick_size REAL DEFAULT 0.05,
                is_nifty50 INTEGER DEFAULT 0,
                is_fno INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_nse_inst_sym ON nse_instruments(symbol)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_nse_inst_co ON nse_instruments(company_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_nse_inst_isin ON nse_instruments(isin)")

        con.commit()


def sync_full_market_universe(force: bool = False) -> Dict[str, Any]:
    """
    Ingest full official Upstox instrument master:
    1. Populates `market_instruments` with NSE equities, indices, F&O options, and BSE indices.
    2. Populates `nse_instruments` table.
    3. Auto-populates `stocks` table with all 2,757 mainboard equities so screener sees full market.
    """
    init_market_instruments_tables()

    with get_db_connection() as con:
        cur_count = con.execute("SELECT COUNT(*) FROM market_instruments").fetchone()[0]
        if cur_count >= 3000 and not force:
            logger.info("market_instruments already populated (%d records). Skipping sync.", cur_count)
            return {"status": "already_populated", "total_instruments": cur_count}

    if not os.path.exists(CACHE_FILE_PATH):
        logger.warning("NSE.json.gz cache not found at %s. Sync deferred.", CACHE_FILE_PATH)
        return {"status": "cache_missing", "total_instruments": 0}

    logger.info("Ingesting full market instrument master from %s...", CACHE_FILE_PATH)
    with gzip.open(CACHE_FILE_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Discover active F&O underlyings
    fno_symbols = {
        d.get("asset_symbol")
        for d in data
        if d.get("segment") == "NSE_FO" and d.get("asset_symbol")
    }

    market_records = []
    nse_inst_records = []
    stock_records = []
    seen_symbols = set()

    for d in data:
        seg = d.get("segment")
        itype = d.get("instrument_type")
        sym = d.get("trading_symbol")

        if not seg or not itype or not sym:
            continue

        sym_clean = sym.strip().upper()
        cname = d.get("name") or sym_clean
        sname = d.get("short_name") or ""
        isin = d.get("isin") or ""
        ikey = d.get("instrument_key") or f"{seg}|{isin or sym_clean}"
        token = d.get("exchange_token") or ""
        lot = int(d.get("lot_size") or 1)
        tick = float(d.get("tick_size") or 0.05)
        exch = d.get("exchange") or "NSE"

        is_n50 = 1 if sym_clean in NIFTY_50_CONSTITUENTS else 0
        is_fno = 1 if sym_clean in fno_symbols else 0

        # Deriv fields
        exp_ms = d.get("expiry")
        exp_str = (
            datetime.datetime.fromtimestamp(exp_ms / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%d")
            if exp_ms
            else None
        )
        strike = float(d.get("strike_price") or 0.0) if d.get("strike_price") else None
        opt_type = itype if itype in ("CE", "PE") else None

        market_records.append((
            sym_clean, sym_clean, exch, seg, itype, ikey, token, isin,
            cname, lot, tick, exp_str, strike, opt_type, 1, is_n50, is_n50, is_n50, is_fno,
            datetime.datetime.now(datetime.timezone.utc).isoformat(), "UPSTOX"
        ))

        # Separate equities for stocks and nse_instruments
        if seg == "NSE_EQ" and itype in ("EQ", "BE", "SM", "BZ") and sym_clean not in seen_symbols:
            seen_symbols.add(sym_clean)
            nse_inst_records.append((
                sym_clean, cname, sname, isin, ikey, token, seg, itype,
                lot, tick, is_n50, is_fno, 1
            ))

            # Base stocks record for mainboard equities
            if itype == "EQ":
                stock_records.append((
                    sym_clean, cname, exch, "General", "General", "Mid" if not is_n50 else "Large",
                    isin, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 1.0, "nse_master_universe"
                ))

    # Add BSE Benchmark Indices
    bse_indices = [
        ("SENSEX", "BSE SENSEX", "BSE", "BSE_INDEX", "INDEX", "BSE_INDEX|SENSEX", "1", "", "BSE SENSEX 30 Benchmark", 1, 1.0, None, None, None, 1, 0, 0, 0, 0, datetime.datetime.now(datetime.timezone.utc).isoformat(), "BSE"),
        ("BANKEX", "BSE BANKEX", "BSE", "BSE_INDEX", "INDEX", "BSE_INDEX|BANKEX", "12", "", "BSE Banking Index", 1, 1.0, None, None, None, 1, 0, 0, 0, 0, datetime.datetime.now(datetime.timezone.utc).isoformat(), "BSE"),
    ]
    market_records.extend(bse_indices)

    with get_db_connection() as con:
        # Clear & insert market_instruments
        con.execute("DELETE FROM market_instruments")
        con.executemany("""
            INSERT INTO market_instruments (
                symbol, trading_symbol, exchange, segment, instrument_type,
                instrument_key, exchange_token, isin, company_name, lot_size,
                tick_size, expiry_date, strike_price, option_type, is_active,
                is_nifty50, is_nifty100, is_nifty500, is_fno, last_updated, provider
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, market_records)

        # Upsert nse_instruments
        con.executemany("""
            INSERT OR REPLACE INTO nse_instruments (
                symbol, company_name, short_name, isin, instrument_key,
                exchange_token, segment, instrument_type, lot_size, tick_size,
                is_nifty50, is_fno, is_active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, nse_inst_records)

        # Ingest stocks table: only INSERT OR IGNORE so existing prices/fundamentals are preserved!
        con.executemany("""
            INSERT OR IGNORE INTO stocks (
                symbol, company_name, exchange, sector, industry, cap_category,
                isin, close, daily_change_pct, week_52_high, week_52_low, market_cap_cr,
                pe, volume, relative_volume, data_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, stock_records)

        con.commit()

        total_market = con.execute("SELECT COUNT(*) FROM market_instruments").fetchone()[0]
        total_nse_eq = con.execute("SELECT COUNT(*) FROM nse_instruments").fetchone()[0]
        total_stocks = con.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]

    logger.info(
        "Successfully synced full market universe: %d instruments (%d NSE equities, %d total stocks)",
        total_market, total_nse_eq, total_stocks
    )

    return {
        "status": "success",
        "total_market_instruments": total_market,
        "total_nse_equities": total_nse_eq,
        "total_stocks_table": total_stocks,
        "nifty50_count": len(NIFTY_50_CONSTITUENTS),
        "fno_underlyings_count": len(fno_symbols),
    }


def search_market_universe(
    query: str,
    exchange: Optional[str] = None,
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    Search full market universe across symbols, company names, and ISINs.
    Supports filtering by exchange (NSE, BSE, or ALL).
    """
    init_market_instruments_tables()

    q = (query or "").strip().upper()
    prefix = f"{q}%"
    contains = f"%{q}%"

    sql = """
        SELECT symbol, trading_symbol, exchange, segment, instrument_type,
               instrument_key, exchange_token, isin, company_name, is_nifty50, is_fno,
               CASE
                   WHEN symbol = ? THEN 1
                   WHEN symbol LIKE ? THEN 2
                   WHEN symbol LIKE ? THEN 3
                   ELSE 4
               END AS rank
        FROM market_instruments
        WHERE (instrument_type IN ('EQ', 'INDEX', 'BE', 'SM'))
    """
    params: List[Any] = [q, prefix, contains]

    if exchange and exchange.upper() in ("NSE", "BSE"):
        sql += " AND exchange = ?"
        params.append(exchange.upper())

    if q:
        sql += " AND (symbol LIKE ? OR company_name LIKE ? OR isin = ?)"
        params.extend([contains, contains, q])
    else:
        # Default top NIFTY 50 liquid stocks
        sql += " AND is_nifty50 = 1"

    sql += " ORDER BY rank ASC, is_nifty50 DESC, is_fno DESC, symbol ASC LIMIT ?"
    params.append(limit)

    with get_db_connection() as con:
        # Check if table has data; if not, sync first
        cnt = con.execute("SELECT COUNT(*) FROM market_instruments").fetchone()[0]
        if cnt == 0:
            sync_full_market_universe()

        rows = con.execute(sql, params).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            d.pop("rank", None)
            results.append(d)
        return results


# Backward compatibility functions
def sync_nse_instruments_master(force: bool = False) -> int:
    res = sync_full_market_universe(force=force)
    return res.get("total_nse_equities", 0)


def search_nse_universe(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    return search_market_universe(query=query, exchange="NSE", limit=limit)


# Import Option Chain routines from earlier implementation
from app.services.nse_universe_service_options import (
    calculate_black_scholes_greeks,
    get_nifty_option_chain,
    get_nifty_option_expiries,
)
