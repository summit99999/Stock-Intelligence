"""
SQLite to PostgreSQL / Supabase Migration Utility for Stock Intelligence Pro.
Migrates all reference data, OHLCV bars, fundamental records, and user assets
with automated pre-migration backup, schema validation, and row verification.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migration")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "backend" / "data" / "stock_intelligence.db"
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backups"
DEFAULT_MIGRATION_SQL = PROJECT_ROOT / "database" / "supabase_migrations.sql"

# Topological table order for clean migration
ALL_TABLES: List[str] = [
    # 1. Reference Data & OHLCV
    "stocks",
    "ohlcv",
    "data_updates",
    # 2. Fundamental Data Tables
    "fundamental_company_profiles",
    "fundamental_income_statements",
    "fundamental_balance_sheets",
    "fundamental_cash_flows",
    "fundamental_ratios",
    "fundamental_shareholdings",
    "fundamental_corporate_actions",
    "fundamental_competitors",
    "fundamental_sync_history",
    # 3. User-Scoped Research & Alert Assets
    "saved_screeners",
    "saved_custom_scanners",
    "custom_watchlists",
    "market_alerts",
    "market_alert_history",
    "research_trade_plans",
    "research_notes",
]

USER_SCOPED_TABLES = {
    "saved_screeners",
    "saved_custom_scanners",
    "custom_watchlists",
    "market_alerts",
    "market_alert_history",
    "research_trade_plans",
    "research_notes",
}


def backup_sqlite(sqlite_path: Path, backup_dir: Path) -> Path:
    """Create a safe timestamped copy of the SQLite database before running migration."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"stock_intelligence_backup_{timestamp}.db"
    shutil.copy2(sqlite_path, backup_file)
    logger.info("Created local SQLite backup at: %s", backup_file)
    return backup_file


def get_sqlite_table_columns(con: sqlite3.Connection, table_name: str) -> List[str]:
    """Retrieve column names for an SQLite table."""
    cur = con.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]


def get_postgres_table_columns(pg_cur: Any, table_name: str) -> List[str]:
    """Retrieve column names for a PostgreSQL table."""
    pg_cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table_name,),
    )
    return [r[0] for r in pg_cur.fetchall()]


def apply_migrations(pg_conn: Any, sql_path: Path) -> None:
    """Run Supabase / PostgreSQL DDL migration script to ensure schema is initialized."""
    if not sql_path.exists():
        logger.warning("Migration script %s not found; skipping DDL execution.", sql_path)
        return
    logger.info("Applying PostgreSQL schema migrations from: %s", sql_path)
    sql = sql_path.read_text(encoding="utf-8")
    with pg_conn.cursor() as cur:
        cur.execute(sql)
    pg_conn.commit()
    logger.info("Schema migrations applied successfully.")


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    table_name: str,
    user_id: Optional[str] = None,
    batch_size: int = 1000,
) -> Tuple[int, int]:
    """
    Migrate rows from SQLite table to PostgreSQL table.
    Returns (source_row_count, inserted_row_count).
    """
    # Check if table exists in SQLite
    sqlite_cur = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    if not sqlite_cur.fetchone():
        logger.info("Table '%s' does not exist in SQLite source. Skipping.", table_name)
        return (0, 0)

    sqlite_cols = get_sqlite_table_columns(sqlite_conn, table_name)
    with pg_conn.cursor() as pg_cur:
        pg_cols = get_postgres_table_columns(pg_cur, table_name)

    if not pg_cols:
        logger.warning("Table '%s' does not exist in PostgreSQL destination. Skipping.", table_name)
        return (0, 0)

    # Find common columns between source and destination
    common_cols = [c for c in sqlite_cols if c in pg_cols]
    if not common_cols:
        logger.warning("No overlapping columns for '%s'. Skipping.", table_name)
        return (0, 0)

    # Determine whether user_id can be attached if missing
    attach_user_id = bool(user_id and table_name in USER_SCOPED_TABLES and "user_id" in pg_cols and "user_id" not in common_cols)
    insert_cols = list(common_cols)
    if attach_user_id:
        insert_cols.append("user_id")

    user_id_col_idx = insert_cols.index("user_id") if (user_id and "user_id" in insert_cols) else -1

    col_names_str = ", ".join(insert_cols)
    placeholders_str = ", ".join(["%s"] * len(insert_cols))
    insert_sql = f"INSERT INTO {table_name} ({col_names_str}) VALUES ({placeholders_str}) ON CONFLICT DO NOTHING"

    # Fetch rows from SQLite
    select_sql = f"SELECT {', '.join(common_cols)} FROM {table_name}"
    cur = sqlite_conn.execute(select_sql)
    rows = cur.fetchall()
    total_source = len(rows)

    if total_source == 0:
        logger.info("Table '%s': 0 records in SQLite. Nothing to migrate.", table_name)
        return (0, 0)

    # Batch insert into Postgres
    inserted = 0
    with pg_conn.cursor() as pg_cur:
        batch = []
        for row in rows:
            row_vals = list(row)
            if attach_user_id:
                row_vals.append(user_id)
            elif user_id_col_idx >= 0:
                current_uid = row_vals[user_id_col_idx]
                if current_uid is None or current_uid in ("local-operator", "00000000-0000-0000-0000-000000000000"):
                    row_vals[user_id_col_idx] = user_id
            batch.append(tuple(row_vals))

            if len(batch) >= batch_size:
                pg_cur.executemany(insert_sql, batch)
                inserted += len(batch)
                batch = []

        if batch:
            pg_cur.executemany(insert_sql, batch)
            inserted += len(batch)

    pg_conn.commit()
    logger.info("Table '%s': migrated %d records from SQLite.", table_name, total_source)
    return (total_source, inserted)


def verify_counts(sqlite_conn: sqlite3.Connection, pg_conn: Any) -> Dict[str, Dict[str, Any]]:
    """Compare row counts across SQLite and PostgreSQL for verification."""
    results = {}
    with pg_conn.cursor() as pg_cur:
        for table in ALL_TABLES:
            # SQLite count
            try:
                sq_row = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                sq_count = sq_row[0] if sq_row else 0
            except sqlite3.OperationalError:
                sq_count = 0

            # Postgres count
            try:
                pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
                pg_row = pg_cur.fetchone()
                pg_count = pg_row[0] if pg_row else 0
            except Exception:
                pg_count = -1

            results[table] = {
                "sqlite_count": sq_count,
                "postgres_count": pg_count,
                "synced": (sq_count <= pg_count if pg_count >= 0 else False),
            }
    return results


def run_migration(
    sqlite_path: Path,
    database_url: str,
    dry_run: bool = False,
    verify_only: bool = False,
    user_id: Optional[str] = None,
) -> None:
    """Execute complete migration journey."""
    if not sqlite_path.exists():
        logger.error("Source SQLite database not found at %s", sqlite_path)
        return

    # Connect to SQLite source first
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = None
    try:
        # Pre-migration backup
        backup_sqlite(sqlite_path, DEFAULT_BACKUP_DIR)

        # Inspect source
        logger.info("Inspecting source SQLite database...")
        source_counts = {}
        for tbl in ALL_TABLES:
            try:
                c = sqlite_conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                source_counts[tbl] = c
            except sqlite3.OperationalError:
                source_counts[tbl] = 0

        total_source_records = sum(source_counts.values())
        logger.info("Source database contains %d total records across %d tables.", total_source_records, len(ALL_TABLES))

        if dry_run:
            print("\n" + "=" * 55)
            print(f"{'Table Name':<35} | {'Records':<12}")
            print("-" * 55)
            for tbl, count in source_counts.items():
                print(f"{tbl:<35} | {count:>7} rows")
            print("=" * 55)
            print(f"Total: {total_source_records} rows ready to migrate to PostgreSQL.")
            print("[DRY RUN] Inspection complete. No changes made to PostgreSQL.\n")
            return

        if not database_url:
            logger.error("DATABASE_URL is required when not running in dry-run mode.")
            return

        # Normalize database URL
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]

        logger.info("Connecting to target PostgreSQL: %s", database_url.split("@")[-1] if "@" in database_url else "configured host")
        pg_conn = psycopg2.connect(database_url)

        if verify_only:
            logger.info("Running verification check...")
            results = verify_counts(sqlite_conn, pg_conn)
            print_verification_report(results)
            return

        # Apply DDL migrations
        apply_migrations(pg_conn, DEFAULT_MIGRATION_SQL)

        # Migrate each table
        logger.info("Starting table migration...")
        for tbl in ALL_TABLES:
            migrate_table(sqlite_conn, pg_conn, tbl, user_id=user_id)

        # Verify
        logger.info("Verifying destination counts...")
        results = verify_counts(sqlite_conn, pg_conn)
        print_verification_report(results)

    finally:
        sqlite_conn.close()
        if pg_conn:
            pg_conn.close()


def print_verification_report(results: Dict[str, Dict[str, Any]]) -> None:
    """Print formatted summary table of row count verifications."""
    print("\n" + "=" * 70)
    print(f"{'Table Name':<34} | {'SQLite':<8} | {'Postgres':<8} | {'Status'}")
    print("-" * 70)
    all_ok = True
    for tbl, data in results.items():
        sq = data["sqlite_count"]
        pg = data["postgres_count"]
        status = "[OK]" if data["synced"] else "[DIFF]"
        if not data["synced"]:
            all_ok = False
        print(f"{tbl:<34} | {sq:<8} | {pg:<8} | {status}")
    print("=" * 70)
    if all_ok:
        print("[SUCCESS] All tables successfully verified in PostgreSQL destination.\n")
    else:
        print("[WARNING] Some tables have count discrepancies. Check detailed logs above.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Intelligence Pro: SQLite to Supabase PostgreSQL Migration")
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH, help="Path to source SQLite file")
    parser.add_argument("--database-url", type=str, default=os.getenv("DATABASE_URL", ""), help="Target PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Inspect source records without migrating")
    parser.add_argument("--verify", action="store_true", help="Only verify row counts between SQLite and Postgres")
    parser.add_argument("--user-id", type=str, default=None, help="Target Supabase user UUID to attach to user-scoped records")

    args = parser.parse_args()

    if not args.dry_run and not args.database_url:
        logger.error("DATABASE_URL environment variable or --database-url argument is required.")
        return

    run_migration(
        sqlite_path=args.sqlite_path,
        database_url=args.database_url,
        dry_run=args.dry_run,
        verify_only=args.verify,
        user_id=args.user_id,
    )


if __name__ == "__main__":
    main()
