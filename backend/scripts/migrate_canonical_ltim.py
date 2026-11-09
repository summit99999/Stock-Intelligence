import sqlite3

con = sqlite3.connect("backend/data/stock_intelligence.db")
con.execute("PRAGMA foreign_keys = OFF")

# Update instruments
con.execute("UPDATE instruments SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")

# Update provider mappings
con.execute("UPDATE instrument_provider_mappings SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")

# Update corporate actions
con.execute("UPDATE instrument_corporate_actions SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
con.execute("UPDATE instrument_corporate_actions SET resulting_instrument_id = 'INST_NSE_LTIM' WHERE resulting_instrument_id = 'INST_NSE_LTM'")

con.commit()
con.execute("PRAGMA foreign_keys = ON")

fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
print(f"Foreign key check errors: {fk_errors}")
con.close()
print("Canonical INST_NSE_LTIM migration complete.")
