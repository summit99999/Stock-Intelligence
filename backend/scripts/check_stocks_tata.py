import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
con.row_factory = sqlite3.Row
rows = con.execute("SELECT symbol, company_name, isin FROM stocks WHERE symbol LIKE '%TATA%' OR symbol IN ('TMPV', 'TMCV')").fetchall()
for r in rows:
    print(dict(r))
