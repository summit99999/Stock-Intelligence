with open("backend/app/database.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update INSTRUMENT_PROVIDER_MAPPINGS_DDL to include capability flags
old_ddl = """    notes TEXT,
    effective_from TEXT,
    effective_to TEXT,
    created_at TEXT DEFAULT (datetime('now')),"""

new_ddl = """    notes TEXT,
    effective_from TEXT,
    effective_to TEXT,
    quote_endpoint_verified INTEGER NOT NULL DEFAULT 0,
    daily_history_verified INTEGER NOT NULL DEFAULT 0,
    intraday_history_verified INTEGER NOT NULL DEFAULT 0,
    live_feed_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),"""

assert old_ddl in content, "old_ddl not found in database.py"
content = content.replace(old_ddl, new_ddl, 1)

# 2. Update init_db() migration check
old_init_check = """        for column in ("effective_from", "effective_to"):
            try:
                con.execute(f"SELECT {column} FROM instrument_provider_mappings LIMIT 1")
            except sqlite3.OperationalError:
                con.execute(f"ALTER TABLE instrument_provider_mappings ADD COLUMN {column} TEXT")"""

new_init_check = """        for column in (
            "effective_from", "effective_to",
            "quote_endpoint_verified", "daily_history_verified",
            "intraday_history_verified", "live_feed_verified"
        ):
            try:
                con.execute(f"SELECT {column} FROM instrument_provider_mappings LIMIT 1")
            except sqlite3.OperationalError:
                col_type = "INTEGER DEFAULT 0" if "verified" in column else "TEXT"
                con.execute(f"ALTER TABLE instrument_provider_mappings ADD COLUMN {column} {col_type}")"""

assert old_init_check in content, "old_init_check not found in database.py"
content = content.replace(old_init_check, new_init_check, 1)

# 3. Also update _init_postgres_db if present
if "for column in (\"effective_from\", \"effective_to\"):" in content:
    content = content.replace("for column in (\"effective_from\", \"effective_to\"):", "for column in (\n            \"effective_from\", \"effective_to\",\n            \"quote_endpoint_verified\", \"daily_history_verified\",\n            \"intraday_history_verified\", \"live_feed_verified\"\n        ):")

# 4. Update upsert_provider_mapping fields and updates
old_fields = """"notes",
        "effective_from", "effective_to",
        "created_at", "updated_at\""""

new_fields = """"notes",
        "effective_from", "effective_to",
        "quote_endpoint_verified", "daily_history_verified",
        "intraday_history_verified", "live_feed_verified",
        "created_at", "updated_at\""""

assert old_fields in content, "old_fields not found in database.py"
content = content.replace(old_fields, new_fields, 1)

old_update = """        notes = excluded.notes,
        effective_from = excluded.effective_from,
        effective_to = excluded.effective_to,
        updated_at = excluded.updated_at"""

new_update = """        notes = excluded.notes,
        effective_from = excluded.effective_from,
        effective_to = excluded.effective_to,
        quote_endpoint_verified = excluded.quote_endpoint_verified,
        daily_history_verified = excluded.daily_history_verified,
        intraday_history_verified = excluded.intraday_history_verified,
        live_feed_verified = excluded.live_feed_verified,
        updated_at = excluded.updated_at"""

assert old_update in content, "old_update not found in database.py"
content = content.replace(old_update, new_update, 1)

with open("backend/app/database.py", "w", encoding="utf-8") as f:
    f.write(content)

print("backend/app/database.py successfully updated for Phase 14.9.3 capability flags.")
