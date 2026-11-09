with open("backend/app/services/instrument_master_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old_block = """        # 1. Clean up legacy INST_NSE_LTM if present before upserting canonical INST_NSE_LTIM
        with connect() as con:
            legacy_ltm = con.execute("SELECT instrument_id FROM instruments WHERE instrument_id = 'INST_NSE_LTM'").fetchone()
            if legacy_ltm:
                con.execute("UPDATE instrument_provider_mappings SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
                con.execute("UPDATE instrument_corporate_actions SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
                con.execute("UPDATE instrument_corporate_actions SET resulting_instrument_id = 'INST_NSE_LTIM' WHERE resulting_instrument_id = 'INST_NSE_LTM'")
                con.execute("DELETE FROM instruments WHERE instrument_id = 'INST_NSE_LTM'")
                con.commit()"""

new_block = """        # 1. Clean up legacy INST_NSE_LTM if present before upserting canonical INST_NSE_LTIM
        with connect() as con:
            con.execute("PRAGMA foreign_keys = OFF")
            con.execute("UPDATE instruments SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
            con.execute("UPDATE instrument_provider_mappings SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
            con.execute("UPDATE instrument_corporate_actions SET instrument_id = 'INST_NSE_LTIM' WHERE instrument_id = 'INST_NSE_LTM'")
            con.execute("UPDATE instrument_corporate_actions SET resulting_instrument_id = 'INST_NSE_LTIM' WHERE resulting_instrument_id = 'INST_NSE_LTM'")
            con.commit()
            con.execute("PRAGMA foreign_keys = ON")"""

assert old_block in content, "old_block not found"
content = content.replace(old_block, new_block, 1)

with open("backend/app/services/instrument_master_service.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated seed_authoritative_universe in instrument_master_service.py")
