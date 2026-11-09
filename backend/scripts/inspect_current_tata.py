import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
con.row_factory = sqlite3.Row

print("=== Current Instruments for Tata Motors ===")
for r in con.execute("SELECT * FROM instruments WHERE symbol IN ('TATAMOTORS', 'TMPV', 'TMCV') OR instrument_id LIKE '%TATA%' OR instrument_id LIKE '%TM%'").fetchall():
    print(dict(r))

print("\n=== Current Provider Mappings for Tata Motors ===")
for r in con.execute("SELECT * FROM instrument_provider_mappings WHERE instrument_id LIKE '%TATA%' OR instrument_id LIKE '%TM%'").fetchall():
    print(dict(r))

print("\n=== Current Corporate Actions for Tata Motors ===")
for r in con.execute("SELECT * FROM instrument_corporate_actions WHERE instrument_id LIKE '%TATA%' OR instrument_id LIKE '%TM%'").fetchall():
    print(dict(r))
