"""
Transactional SQLite migration for backend/data/stock_intelligence.db:
1. Re-key INST_NSE_TATAMOTORS_HIST -> INST_NSE_TATAMOTORS
2. Clear provider_security_id from all Yahoo Finance provider mappings (sets to NULL)
3. Validate foreign keys, integrity check, and data preservation
"""
import hashlib
import json
import os
import shutil
import sqlite3
import sys

def apply_migration(db_path: str = "backend/data/stock_intelligence.db"):
    # 1. Create timestamped backup
    backup_path = "backend/data/stock_intelligence_backup_phase14_9_3_live.db"
    shutil.copy2(db_path, backup_path)
    print(f"Created live backup at {backup_path}")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    # Snapshot protected tables before
    protected_tables = ["ohlcv", "observed_intraday_ohlcv", "bar_provenance", "stocks"]
    snapshots_before = {}
    for tbl in protected_tables:
        cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        rows = con.execute(f"SELECT * FROM {tbl}").fetchall()
        hasher = hashlib.sha256()
        for r in rows:
            hasher.update(str(tuple(r)).encode("utf-8"))
        snapshots_before[tbl] = (cnt, hasher.hexdigest())

    try:
        con.execute("PRAGMA foreign_keys = OFF")
        cursor = con.cursor()

        # Step A: Update instrument_provider_mappings
        cursor.execute("""
            UPDATE instrument_provider_mappings
            SET instrument_id = 'INST_NSE_TATAMOTORS'
            WHERE instrument_id = 'INST_NSE_TATAMOTORS_HIST'
        """)

        # Step B: Update instrument_corporate_actions
        cursor.execute("""
            UPDATE instrument_corporate_actions
            SET instrument_id = 'INST_NSE_TATAMOTORS'
            WHERE instrument_id = 'INST_NSE_TATAMOTORS_HIST'
        """)

        # Step C: Update instruments
        cursor.execute("""
            UPDATE instruments
            SET instrument_id = 'INST_NSE_TATAMOTORS',
                verification_source = 'NSE_OFFICIAL_CIRCULARS_AND_DHAN_SCRIP_MASTER',
                verification_provenance = 'SCRIP_MASTER_RECORD_MATCH_AND_YFINANCE_EMPIRICAL_PROBE',
                updated_at = datetime('now')
            WHERE instrument_id = 'INST_NSE_TATAMOTORS_HIST'
        """)

        # Step D: Clear provider_security_id for ALL Yahoo Finance mappings
        cursor.execute("""
            UPDATE instrument_provider_mappings
            SET provider_security_id = NULL
            WHERE LOWER(provider) = 'yfinance'
        """)

        con.commit()
        con.execute("PRAGMA foreign_keys = ON")

        # Step E: Validation checks
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key violations found: {fk_errors}")

        integrity = con.execute("PRAGMA integrity_check").fetchall()
        if [r[0] for r in integrity] != ["ok"]:
            raise RuntimeError(f"Integrity check failed: {integrity}")

        # Check protected tables unchanged
        for tbl in protected_tables:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            rows = con.execute(f"SELECT * FROM {tbl}").fetchall()
            hasher = hashlib.sha256()
            for r in rows:
                hasher.update(str(tuple(r)).encode("utf-8"))
            snap_after = (cnt, hasher.hexdigest())
            if snap_after != snapshots_before[tbl]:
                raise RuntimeError(f"Protected table {tbl} was altered! Before: {snapshots_before[tbl]}, After: {snap_after}")

        # Check zero yfinance provider_security_id
        yf_bad = con.execute("""
            SELECT COUNT(*) FROM instrument_provider_mappings
            WHERE LOWER(provider) = 'yfinance' AND provider_security_id IS NOT NULL
        """).fetchone()[0]
        if yf_bad > 0:
            raise RuntimeError(f"{yf_bad} yfinance mappings still have provider_security_id!")

        print("Migration applied successfully with full integrity and preservation verification!")

    except Exception as e:
        con.rollback()
        print(f"Migration failed: {e}")
        con.close()
        shutil.copy2(backup_path, db_path)
        print("Restored original database from backup.")
        sys.exit(1)
    finally:
        con.close()

if __name__ == "__main__":
    apply_migration()
