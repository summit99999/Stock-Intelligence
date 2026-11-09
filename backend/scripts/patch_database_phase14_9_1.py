"""
Patch script for backend/app/database.py in Phase 14.9.1.
"""

def patch_database():
    path = "backend/app/database.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Update INSTRUMENTS_DDL
    old_ddl = """INSTRUMENTS_DDL = \"\"\"
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL,
    isin TEXT NOT NULL UNIQUE,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    security_type TEXT NOT NULL DEFAULT 'EQUITY',
    is_fo_eligible INTEGER NOT NULL DEFAULT 0,
    fo_effective_date TEXT,
    is_cas_eligible INTEGER NOT NULL DEFAULT 0,
    cas_effective_date TEXT,
    cas_schedule_version TEXT DEFAULT 'CAS_V1_HISTORICAL',
    historical_symbols TEXT,
    listing_date TEXT,
    delisting_date TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_verified_date TEXT NOT NULL,
    verification_source TEXT NOT NULL,
    verification_provenance TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
\"\"\""""

    new_ddl = """INSTRUMENTS_DDL = \"\"\"
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL,
    isin TEXT,
    historical_isin TEXT,
    effective_date TEXT,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    security_type TEXT NOT NULL DEFAULT 'EQUITY',
    is_fo_eligible INTEGER NOT NULL DEFAULT 0,
    fo_effective_date TEXT,
    is_cas_eligible INTEGER NOT NULL DEFAULT 0,
    cas_effective_date TEXT,
    cas_schedule_version TEXT DEFAULT 'CAS_V1_HISTORICAL',
    historical_symbols TEXT,
    listing_date TEXT,
    delisting_date TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    last_verified_date TEXT NOT NULL,
    verification_source TEXT NOT NULL,
    verification_provenance TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
\"\"\""""

    assert old_ddl in content, "old_ddl not found in database.py"
    content = content.replace(old_ddl, new_ddl)

    # 2. Update TABLE_PK_MAP
    old_pk = '    "instruments": (["instrument_id"], [\n        "symbol", "company_name", "isin", "exchange", "security_type",'
    new_pk = '    "instruments": (["instrument_id"], [\n        "symbol", "company_name", "isin", "historical_isin", "effective_date", "exchange", "security_type",'
    assert old_pk in content, "old_pk not found in database.py"
    content = content.replace(old_pk, new_pk)

    # 3. Update get_instrument to check historical_isin as well
    old_get_inst = """        # 2. Exact match on ISIN
        row = con.execute("SELECT * FROM instruments WHERE UPPER(isin) = ?", (raw,)).fetchone()
        if row:
            return dict(row)
        # 3. Exact match on current trading symbol"""

    new_get_inst = """        # 2. Exact match on ISIN
        row = con.execute("SELECT * FROM instruments WHERE UPPER(isin) = ?", (raw,)).fetchone()
        if row:
            return dict(row)
        # 3. Exact match on historical_isin
        row = con.execute("SELECT * FROM instruments WHERE UPPER(historical_isin) = ?", (raw,)).fetchone()
        if row:
            return dict(row)
        # 4. Exact match on current trading symbol"""

    assert old_get_inst in content, "old_get_inst not found in database.py"
    content = content.replace(old_get_inst, new_get_inst)

    # 4. Update upsert_instrument to include historical_isin and effective_date
    old_upsert = """    fields = [
        "instrument_id", "symbol", "company_name", "isin", "exchange",
        "security_type", "is_fo_eligible", "fo_effective_date", "is_cas_eligible",
        "cas_effective_date", "cas_schedule_version", "historical_symbols",
        "listing_date", "delisting_date", "status", "last_verified_date",
        "verification_source", "verification_provenance", "created_at", "updated_at"
    ]"""

    new_upsert = """    fields = [
        "instrument_id", "symbol", "company_name", "isin", "historical_isin",
        "effective_date", "exchange",
        "security_type", "is_fo_eligible", "fo_effective_date", "is_cas_eligible",
        "cas_effective_date", "cas_schedule_version", "historical_symbols",
        "listing_date", "delisting_date", "status", "last_verified_date",
        "verification_source", "verification_provenance", "created_at", "updated_at"
    ]"""

    assert old_upsert in content, "old_upsert not found in database.py"
    content = content.replace(old_upsert, new_upsert)

    old_upsert_do_update = """        company_name = excluded.company_name,
        isin = excluded.isin,
        exchange = excluded.exchange,"""

    new_upsert_do_update = """        company_name = excluded.company_name,
        isin = excluded.isin,
        historical_isin = excluded.historical_isin,
        effective_date = excluded.effective_date,
        exchange = excluded.exchange,"""

    assert old_upsert_do_update in content, "old_upsert_do_update not found in database.py"
    content = content.replace(old_upsert_do_update, new_upsert_do_update)

    # 5. Add partial unique index and historical_isin index in init_db
    old_idx = '        con.execute("CREATE INDEX IF NOT EXISTS idx_instruments_isin ON instruments (isin)")'
    new_idx = '''        con.execute("CREATE INDEX IF NOT EXISTS idx_instruments_isin ON instruments (isin)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_instruments_hist_isin ON instruments (historical_isin)")
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_instruments_active_isin ON instruments (isin) WHERE status = 'ACTIVE' AND isin IS NOT NULL")'''

    assert old_idx in content, "old_idx not found in database.py"
    content = content.replace(old_idx, new_idx)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("database.py successfully patched.")

if __name__ == "__main__":
    patch_database()
