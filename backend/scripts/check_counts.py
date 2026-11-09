import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
tables = [
    "observed_intraday_ohlcv",
    "bar_provenance",
    "ohlcv",
    "instruments",
    "instrument_provider_mappings",
    "instrument_corporate_actions",
]
for tbl in tables:
    cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    print(f"{tbl}: {cnt}")
