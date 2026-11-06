# Stock Intelligence Pro — PostgreSQL & Cloud Compatibility Audit
**Phase 13.1 Pre-Deployment Security Audit & Cloud Integration Validation**  
**Audit Date:** 2026-11-06  
**Scope:** PostgreSQL 15+ (Supabase) / SQLite 3 Dual-Engine Compatibility  

---

## 1. Executive Summary

Stock Intelligence Pro has been architected to run seamlessly in both **Local Offline Mode** (using SQLite 3) and **Zero-Cost Cloud Mode** (using Supabase PostgreSQL via connection pooling and Render Free backend hosting).

This audit documents the technical mechanics, database privilege models, query translation correctness, transaction boundaries, and the defense-in-depth isolation strategy implemented in the database access layer (`backend/app/database.py`).

---

## 2. PostgreSQL RLS vs. Direct Connection Pooling: The Reality Check

### The Core Architectural Misconception
A common security pitfall in cloud-native applications using Supabase is assuming that enabling Row-Level Security (`ENABLE ROW LEVEL SECURITY`) on PostgreSQL tables automatically protects backend queries made via a standard PostgreSQL connection pooler (e.g., PgBouncer / Supabase port `6543` / `5432` with `DATABASE_URL`).

**This assumption is FALSE without transaction-scoped context:**
1. When a FastAPI backend connects to PostgreSQL using `DATABASE_URL`, it connects under a superuser or privileged administrative database user (typically `postgres`).
2. By default in PostgreSQL:
   - Superuser connections and database owners **bypass RLS policies completely** unless `FORCE ROW LEVEL SECURITY` is set on the table.
   - Even if RLS is forced, PostgreSQL's `auth.uid()` function evaluates to `NULL` unless the application explicitly runs `SET LOCAL request.jwt.claim.sub = '...'` and `SET LOCAL ROLE authenticated` inside every transaction.
   - If `auth.uid()` evaluates to `NULL`, queries relying solely on `USING (auth.uid() = user_id)` would return zero rows for all queries, breaking backend functionality!

### The Defense-in-Depth Solution Implemented
To guarantee complete tenant isolation without fragile database role switching on pooled connections, Stock Intelligence Pro implements **Defense in Depth**:

```
+-------------------------------------------------------------------+
|                        INCOMING HTTP REQUEST                      |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                  LAYER 1: AUTHENTICATION ENGINE                   |
| - Verifies JWT signature (JWKS or HS256)                          |
| - Validates audience ('authenticated'), issuer, and expiration    |
| - Extracts verified subject: current_user["id"] (UUID)            |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                  LAYER 2: APPLICATION FILTERING                   |
| - Backend parameterizes every user SQL query:                     |
|   WHERE user_id = ? (PostgreSQL: %s)                              |
| - Cross-tenant mutations affect 0 rows -> HTTP 404/403            |
+-------------------------------------------------------------------+
                                  |
                                  v
+-------------------------------------------------------------------+
|                   LAYER 3: DATABASE ENGINE (RLS)                  |
| - PostgreSQL RLS policies defined on all 7 user-scoped tables     |
| - Protects against direct browser client access via Supabase REST |
|   PostgREST APIs (where auth.uid() is automatically injected)     |
+-------------------------------------------------------------------+
```

---

## 3. SQL Adapter & Query Translation Audit

In `backend/app/database.py`, the `adapt_sql_for_postgres` engine translates SQLite queries to PostgreSQL dialect at execution time:

### A. Safe Parameter Placeholder Replacement (`safe_replace_placeholders`)
**Vulnerability Identified & Remediated**: Naive `sql.replace("?", "%s")` corrupts queries that contain question marks within string literals (e.g. `WHERE title = 'Is this a breakout?'`) or comments (e.g. `-- Is this active?`).
**Remediation**: Implemented a stateful character-by-character SQL tokenizer (`safe_replace_placeholders`) that tracks:
- Single-quoted string literals (`'...'`), including escaped quotes (`''`)
- Double-quoted identifier literals (`"..."`)
- Single-line SQL comments (`-- ...\n`)
- Multi-line block comments (`/* ... */`)

Only question mark tokens appearing in raw SQL syntax outside quotes and comments are converted to `%s`. Verified by `test_sql_adapter_safe_placeholder_replacement`.

### B. Dialect Translations
1. **Timestamp Functions**:
   `datetime('now')` is translated via regular expression to standard PostgreSQL `NOW()`.
2. **Upsert Logic (`INSERT OR REPLACE`)**:
   SQLite's `INSERT OR REPLACE INTO <table> (<cols>) VALUES (<vals>)` is translated to PostgreSQL's standard:
   `INSERT INTO <table> (<cols>) VALUES (<vals>) ON CONFLICT (<pk>) DO UPDATE SET <col> = EXCLUDED.<col>, ...`
   Lookup table `TABLE_PK_MAP` maps all 19 tables to their primary key columns.
3. **Auto-Increment Primary Key Return (`RETURNING id`)**:
   In SQLite, `cursor.lastrowid` retrieves the auto-generated primary key after an insert. In PostgreSQL with `psycopg2`, auto-increment sequences (`BIGSERIAL`) require `RETURNING id`.
   `adapt_sql_for_postgres` automatically appends `RETURNING id` for all auto-increment tables (`saved_screeners`, `saved_custom_scanners`, `custom_watchlists`, `market_alerts`, `market_alert_history`, `research_trade_plans`, `research_notes`), and `PostgresCursorWrapper` intercepts the returned row and populates `cur.lastrowid`.

---

## 4. Connection Pooling & Transaction Management

1. **Context Manager Pattern**:
   All database access is routed through the `connect()` context manager:
   ```python
   with connect() as con:
       row = con.execute("SELECT ...", params).fetchone()
   ```
2. **Transaction Scoping**:
   - For write operations, `con.commit()` commits the transaction.
   - On unhandled exception, the context manager closes the connection/cursor, triggering automatic rollback in PostgreSQL.
   - Connections retrieved from `ThreadedConnectionPool` (pool min: 1, max: 10) are returned to the pool via `_pg_pool.putconn(conn)` in `finally` blocks, preventing connection leaks.

---

## 5. Migration Utility Audit (`backend/app/migrate_to_postgres.py`)

1. **Automated Pre-Migration Backup**:
   The migration utility always creates a timestamped copy of the local SQLite database in `backups/stock_intelligence_backup_YYYYMMDD_HHMMSS.db` before reading any table data.
2. **Topological Order**:
   Tables are migrated in strict dependency order:
   - Primary reference: `stocks`, `ohlcv`, `data_updates`
   - Fundamental records: `fundamental_company_profiles` followed by statements, balance sheets, cash flows, and ratios
   - User assets: `saved_screeners`, `saved_custom_scanners`, `custom_watchlists`, `market_alerts`, `market_alert_history`, `research_trade_plans`, `research_notes`
3. **User Ownership Backfill**:
   When migrating user-scoped tables with `--user-id <uuid>`, any legacy row where `user_id IS NULL` or equals the local mock operator is automatically backfilled with the operator's real Supabase user UUID.
4. **Idempotency**:
   All insert statements utilize `ON CONFLICT DO NOTHING`, ensuring that partial runs can be safely resumed without duplicate key violations or data loss.
5. **Credential Masking**:
   Database URLs are sanitized in logs to display only the host portion (`db.<project-ref>.supabase.co`), preventing credentials from leaking into log aggregators.
