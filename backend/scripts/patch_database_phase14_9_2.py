with open("backend/app/database.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update INSTRUMENT_PROVIDER_MAPPINGS_DDL
old_ddl = """    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),"""
new_ddl = """    notes TEXT,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT DEFAULT (datetime('now')),"""
assert old_ddl in content, "old_ddl not found"
content = content.replace(old_ddl, new_ddl, 1)

# 2. Update init_db()
old_init = """        con.execute(INSTRUMENT_PROVIDER_MAPPINGS_DDL)
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_inst_prov ON instrument_provider_mappings (instrument_id, provider)")"""
new_init = """        con.execute(INSTRUMENT_PROVIDER_MAPPINGS_DDL)
        for column in ("effective_from", "effective_to"):
            try:
                con.execute(f"SELECT {column} FROM instrument_provider_mappings LIMIT 1")
            except sqlite3.OperationalError:
                con.execute(f"ALTER TABLE instrument_provider_mappings ADD COLUMN {column} TEXT")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_inst_prov ON instrument_provider_mappings (instrument_id, provider)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_prov_map_sec_id ON instrument_provider_mappings (provider, provider_security_id)")"""
assert old_init in content, "old_init not found"
content = content.replace(old_init, new_init, 1)

# 3. Update upsert_provider_mapping
old_fields = """"is_primary", "verification_date", "verification_method", "notes",
        "created_at", "updated_at\""""
new_fields = """"is_primary", "verification_date", "verification_method", "notes",
        "effective_from", "effective_to",
        "created_at", "updated_at\""""
assert old_fields in content, "old_fields not found"
content = content.replace(old_fields, new_fields, 1)

old_update = """        verification_method = excluded.verification_method,
        notes = excluded.notes,
        updated_at = excluded.updated_at"""
new_update = """        instrument_id = excluded.instrument_id,
        verification_method = excluded.verification_method,
        notes = excluded.notes,
        effective_from = excluded.effective_from,
        effective_to = excluded.effective_to,
        updated_at = excluded.updated_at"""
assert old_update in content, "old_update not found"
content = content.replace(old_update, new_update, 1)

with open("backend/app/database.py", "w", encoding="utf-8") as f:
    f.write(content)

print("backend/app/database.py successfully patched.")
