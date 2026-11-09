import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

print("Searching for LTM / LTIM across database tables...")
for tbl in tables:
    for col_info in con.execute(f"PRAGMA table_info({tbl})").fetchall():
        col = col_info[1]
        try:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl} WHERE cast({col} as text) LIKE '%LTM%' OR cast({col} as text) LIKE '%LTIM%'").fetchone()[0]
            if cnt > 0:
                print(f"  {tbl}.{col}: {cnt} rows")
        except Exception:
            pass
