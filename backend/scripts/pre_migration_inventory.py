import hashlib
import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
con.row_factory = sqlite3.Row

tables = [
    "observed_intraday_ohlcv",
    "bar_provenance",
    "ohlcv",
    "stocks",
    "instruments",
    "instrument_provider_mappings",
    "instrument_corporate_actions",
    "saved_screeners",
    "custom_watchlists",
]

print("=== Pre-Migration Database Inventory & Checksums ===")
for tbl in tables:
    cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    # Calculate md5 of all rows ordered by primary key / columns
    rows = con.execute(f"SELECT * FROM {tbl}").fetchall()
    hasher = hashlib.sha256()
    for r in rows:
        hasher.update(str(tuple(r)).encode("utf-8"))
    print(f"Table: {tbl:<30} | Rows: {cnt:<6} | SHA256: {hasher.hexdigest()[:16]}")

print("\nIntegrity check:", con.execute("PRAGMA integrity_check").fetchall())
print("Foreign key check:", con.execute("PRAGMA foreign_key_check").fetchall())
