"""
Database migration script for Phase 14.9.1.
Updates the `instruments` table to:
1. Make `isin` nullable so historical/demerged entities don't hold fabricated ISINs.
2. Add `historical_isin` and `effective_date` columns.
3. Add partial unique index on `isin` for active securities only.
4. Preserve all 24,786 observed bars, 24,786 provenance records, and 46,500 synthetic bars.
"""

import sqlite3
import sys

def migrate(db_path: str = "backend/data/stock_intelligence.db"):
    print(f"Connecting to {db_path}...")
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    # Pre-checks
    obs_cnt = cur.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
    prov_cnt = cur.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
    ohlcv_cnt = cur.execute("SELECT count(*) FROM ohlcv").fetchone()[0]
    print(f"Pre-migration counts: observed={obs_cnt}, prov={prov_cnt}, ohlcv={ohlcv_cnt}")

    cols = [col[1] for col in cur.execute("PRAGMA table_info(instruments)").fetchall()]
    print(f"Existing instruments columns: {cols}")

    needs_migration = "historical_isin" not in cols

    if needs_migration:
        print("Migrating instruments table schema...")
        cur.execute("PRAGMA foreign_keys = OFF;")
        cur.execute("BEGIN TRANSACTION;")

        cur.execute("""
        CREATE TABLE instruments_new (
            instrument_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            company_name TEXT NOT NULL,
            isin TEXT,
            historical_isin TEXT,
            effective_date TEXT,
            exchange TEXT NOT NULL DEFAULT 'NSE',
            security_type TEXT NOT NULL DEFAULT 'EQUITY',
            is_fo_eligible INTEGER NOT NULL DEFAULT 0,
            fo_effective_date TEXT,
            is_cas_eligible INTEGER NOT NULL DEFAULT 0,
            cas_effective_date TEXT,
            cas_schedule_version TEXT DEFAULT 'CAS_V1_HISTORICAL',
            historical_symbols TEXT,
            listing_date TEXT,
            delisting_date TEXT,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            last_verified_date TEXT NOT NULL,
            verification_source TEXT NOT NULL,
            verification_provenance TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """)

        cur.execute("""
        INSERT INTO instruments_new (
            instrument_id, symbol, company_name, isin, historical_isin, effective_date,
            exchange, security_type, is_fo_eligible, fo_effective_date, is_cas_eligible,
            cas_effective_date, cas_schedule_version, historical_symbols, listing_date,
            delisting_date, status, last_verified_date, verification_source,
            verification_provenance, created_at, updated_at
        )
        SELECT
            instrument_id, symbol, company_name, isin, NULL, NULL,
            exchange, security_type, is_fo_eligible, fo_effective_date, is_cas_eligible,
            cas_effective_date, cas_schedule_version, historical_symbols, listing_date,
            delisting_date, status, last_verified_date, verification_source,
            verification_provenance, created_at, updated_at
        FROM instruments;
        """)

        cur.execute("DROP TABLE instruments;")
        cur.execute("ALTER TABLE instruments_new RENAME TO instruments;")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_symbol ON instruments (symbol);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_isin ON instruments (isin);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_instruments_hist_isin ON instruments (historical_isin);")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_instruments_active_isin ON instruments (isin) WHERE status = 'ACTIVE' AND isin IS NOT NULL;")

        con.commit()
        cur.execute("PRAGMA foreign_keys = ON;")
        print("Schema migration complete.")
    else:
        print("instruments table already has historical_isin. Skipping DDL change.")

    # Integrity check
    fk_errors = cur.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = cur.execute("PRAGMA integrity_check;").fetchall()
    print("Foreign key check:", fk_errors)
    print("Integrity check:", integrity)

    # Post-checks
    obs_cnt_post = cur.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
    prov_cnt_post = cur.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
    ohlcv_cnt_post = cur.execute("SELECT count(*) FROM ohlcv").fetchone()[0]
    print(f"Post-migration counts: observed={obs_cnt_post}, prov={prov_cnt_post}, ohlcv={ohlcv_cnt_post}")

    assert obs_cnt_post == obs_cnt, f"Observed count mismatch: {obs_cnt_post} != {obs_cnt}"
    assert prov_cnt_post == prov_cnt, f"Provenance count mismatch: {prov_cnt_post} != {prov_cnt}"
    assert ohlcv_cnt_post == ohlcv_cnt, f"OHLCV count mismatch: {ohlcv_cnt_post} != {ohlcv_cnt}"

    con.close()
    print("Migration finished successfully.")

if __name__ == "__main__":
    migrate()
