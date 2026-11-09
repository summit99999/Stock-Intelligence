with open("backend/app/database.py", "r", encoding="utf-8") as f:
    content = f.read()

target = """        con.execute(INSTRUMENT_PROVIDER_MAPPINGS_DDL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_inst_prov ON instrument_provider_mappings (instrument_id, provider)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_prov_sym ON instrument_provider_mappings (provider, provider_symbol)")"""

replacement = """        con.execute(INSTRUMENT_PROVIDER_MAPPINGS_DDL)
        for column in ("effective_from", "effective_to"):
            try:
                con.execute(f"SELECT {column} FROM instrument_provider_mappings LIMIT 1")
            except sqlite3.OperationalError:
                con.execute(f"ALTER TABLE instrument_provider_mappings ADD COLUMN {column} TEXT")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_inst_prov ON instrument_provider_mappings (instrument_id, provider)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_prov_sym ON instrument_provider_mappings (provider, provider_symbol)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_sec_id ON instrument_provider_mappings (provider, provider_security_id)")"""

assert target in content, "target not found in database.py"
content = content.replace(target, replacement, 1)

with open("backend/app/database.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated init_db in database.py")
