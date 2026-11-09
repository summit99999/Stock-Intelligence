"""Fail-closed, transactional SQLite repair for Tata Motors instrument lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_TATA_ID = "INST_NSE_TATAMOTORS_HIST"
TATA_ID = "INST_NSE_TATAMOTORS"
TMPV_ID = "INST_NSE_TMPV"
TMCV_ID = "INST_NSE_TMCV"

CAPABILITY_COLUMNS = {
    "identity_status": "TEXT NOT NULL DEFAULT 'UNVERIFIED'",
    "quote_endpoint_verified": "INTEGER NOT NULL DEFAULT 0",
    "daily_history_verified": "INTEGER NOT NULL DEFAULT 0",
    "intraday_history_verified": "INTEGER NOT NULL DEFAULT 0",
    "live_feed_verified": "INTEGER NOT NULL DEFAULT 0",
    "effective_from": "TEXT",
    "effective_to": "TEXT",
}

PROTECTED_TABLES = {
    "ohlcv",
    "observed_intraday_ohlcv",
    "bar_provenance",
    "intraday_ingestion_runs",
    "custom_watchlists",
    "market_alerts",
    "market_alert_history",
    "saved_screeners",
    "saved_custom_scanners",
    "research_trade_plans",
    "research_notes",
}

REFERENCE_COLUMNS = {
    "stocks": ("symbol",),
    "ohlcv": ("symbol",),
    "fundamentals": ("symbol",),
    "shareholding": ("symbol",),
    "observed_intraday_ohlcv": ("symbol",),
    "bar_provenance": ("symbol",),
    "intraday_ingestion_runs": ("symbol",),
    "custom_watchlists": ("symbols_json",),
    "market_alerts": ("symbol",),
    "market_alert_history": ("symbol",),
    "saved_screeners": ("config_json",),
    "saved_custom_scanners": ("universe", "conditions_json"),
    "research_trade_plans": ("symbol",),
    "research_notes": ("symbol",),
}

TATA_PREDECESSOR = {
    "instrument_id": TATA_ID,
    "symbol": "TATAMOTORS",
    "company_name": "Tata Motors Limited (Pre-Demerger Unified Entity)",
    "isin": None,
    "historical_isin": "INE155A01022",
    "effective_date": None,
    "exchange": "NSE",
    "security_type": "EQUITY",
    "is_fo_eligible": 1,
    "fo_effective_date": None,
    "is_cas_eligible": 1,
    "cas_effective_date": None,
    "cas_schedule_version": "CAS_V1_HISTORICAL",
    "historical_symbols": json.dumps(
        [{"symbol": "TELCO", "note": "Historical alias; effective dates not established"}]
    ),
    "listing_date": None,
    "delisting_date": None,
    "status": "DEMERGED",
    "last_verified_date": "2026-11-06",
    "verification_source": "PHASE14_9_4_LINEAGE_RECONCILIATION",
    "verification_provenance": "PRIMARY_EXCHANGE_EVIDENCE_REQUIRED",
}

TATA_SYMBOLS = {"TATAMOTORS", "TMPV", "TMCV", "TELCO"}
TATA_ID_ALIASES = {LEGACY_TATA_ID, TATA_ID, TMPV_ID, TMCV_ID}


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _tables(connection: sqlite3.Connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    return value


def _table_snapshot(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for table in _tables(connection):
        columns = [
            row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
        ]
        if not columns:
            continue
        order = ", ".join(_quote(column) for column in columns)
        cursor = connection.execute(
            f"SELECT * FROM {_quote(table)} ORDER BY {order}"
        )
        digest = hashlib.sha256()
        count = 0
        while rows := cursor.fetchmany(1000):
            for row in rows:
                encoded = json.dumps(
                    [_json_value(value) for value in row],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
                digest.update(len(encoded).to_bytes(8, "big"))
                digest.update(encoded)
                count += 1
        snapshot[table] = {"row_count": count, "sha256": digest.hexdigest()}
    return snapshot


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row[1] for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    }


def _ensure_schema(connection: sqlite3.Connection) -> None:
    required = {
        "instruments",
        "instrument_provider_mappings",
        "instrument_corporate_actions",
    }
    missing = required - set(_tables(connection))
    if missing:
        raise RuntimeError(f"Required instrument tables are missing: {sorted(missing)}")

    mappings = _columns(connection, "instrument_provider_mappings")
    for column, definition in CAPABILITY_COLUMNS.items():
        if column not in mappings:
            connection.execute(
                f"ALTER TABLE instrument_provider_mappings "
                f"ADD COLUMN {_quote(column)} {definition}"
            )

    actions = _columns(connection, "instrument_corporate_actions")
    if "date_verification_status" not in actions:
        connection.execute(
            "ALTER TABLE instrument_corporate_actions ADD COLUMN "
            "date_verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED'"
        )
        actions.add("date_verification_status")
    if "resulting_instrument_ids" not in actions:
        connection.execute(
            "ALTER TABLE instrument_corporate_actions "
            "ADD COLUMN resulting_instrument_ids TEXT"
        )


def _instrument(connection: sqlite3.Connection, instrument_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM instruments WHERE instrument_id = ?", (instrument_id,)
    ).fetchone()
    return dict(row) if row else None


def _rekey_instrument(
    connection: sqlite3.Connection, old_id: str, new_id: str
) -> None:
    if old_id == new_id:
        return
    if _instrument(connection, new_id):
        raise RuntimeError(f"Cannot safely re-key {old_id}: {new_id} already exists")
    for table in _tables(connection):
        for foreign_key in connection.execute(
            f"PRAGMA foreign_key_list({_quote(table)})"
        ):
            referenced_table = foreign_key[2]
            source_column = foreign_key[3]
            target_column = foreign_key[4]
            if referenced_table == "instruments" and target_column == "instrument_id":
                connection.execute(
                    f"UPDATE {_quote(table)} SET {_quote(source_column)} = ? "
                    f"WHERE {_quote(source_column)} = ?",
                    (new_id, old_id),
                )
    connection.execute(
        "UPDATE instrument_corporate_actions "
        "SET resulting_instrument_id = ? WHERE resulting_instrument_id = ?",
        (new_id, old_id),
    )
    action_columns = _columns(connection, "instrument_corporate_actions")
    if "resulting_instrument_ids" in action_columns:
        rows = connection.execute(
            "SELECT action_id, resulting_instrument_ids "
            "FROM instrument_corporate_actions WHERE resulting_instrument_ids IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                values = json.loads(row[1])
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Invalid resulting_instrument_ids JSON on {row[0]}"
                ) from exc
            if not isinstance(values, list):
                raise RuntimeError(f"Expected a JSON array on action {row[0]}")
            updated = [new_id if value == old_id else value for value in values]
            if updated != values:
                connection.execute(
                    "UPDATE instrument_corporate_actions SET resulting_instrument_ids = ? "
                    "WHERE action_id = ?",
                    (json.dumps(updated), row[0]),
                )
    connection.execute(
        "UPDATE instruments SET instrument_id = ? WHERE instrument_id = ?",
        (new_id, old_id),
    )


def _insert_predecessor(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "instruments")
    values = dict(TATA_PREDECESSOR)
    now = datetime.now(timezone.utc).isoformat()
    values.update(created_at=now, updated_at=now)
    selected = [column for column in values if column in columns]
    connection.execute(
        f"INSERT INTO instruments ({', '.join(_quote(c) for c in selected)}) "
        f"VALUES ({', '.join('?' for _ in selected)})",
        [values[column] for column in selected],
    )


def _repair_instrument_identity(connection: sqlite3.Connection) -> None:
    legacy = _instrument(connection, LEGACY_TATA_ID)
    canonical = _instrument(connection, TATA_ID)
    tmpv = _instrument(connection, TMPV_ID)

    if canonical and canonical.get("symbol") == "TMPV":
        if tmpv:
            raise RuntimeError(
                "Both INST_NSE_TATAMOTORS and INST_NSE_TMPV claim TMPV; refusing to merge."
            )
        _rekey_instrument(connection, TATA_ID, TMPV_ID)
        canonical = None
        tmpv = _instrument(connection, TMPV_ID)

    if legacy:
        if canonical:
            raise RuntimeError(
                "Both canonical and legacy predecessor rows exist; manual lineage review required."
            )
        _rekey_instrument(connection, LEGACY_TATA_ID, TATA_ID)
        canonical = _instrument(connection, TATA_ID)
    elif not canonical:
        _insert_predecessor(connection)
        canonical = _instrument(connection, TATA_ID)

    if not canonical or canonical.get("symbol") != "TATAMOTORS":
        raise RuntimeError("Canonical Tata predecessor identity did not validate.")

    connection.execute(
        """
        UPDATE instruments SET
            company_name = ?,
            symbol = 'TATAMOTORS',
            isin = NULL,
            historical_isin = 'INE155A01022',
            effective_date = NULL,
            listing_date = NULL,
            delisting_date = NULL,
            historical_symbols = ?,
            status = 'DEMERGED',
            verification_source = 'PHASE14_9_4_LINEAGE_RECONCILIATION',
            verification_provenance = 'PRIMARY_EXCHANGE_EVIDENCE_REQUIRED'
        WHERE instrument_id = ?
        """,
        (
            TATA_PREDECESSOR["company_name"],
            TATA_PREDECESSOR["historical_symbols"],
            TATA_ID,
        ),
    )

    if not _instrument(connection, TMPV_ID) or not _instrument(connection, TMCV_ID):
        raise RuntimeError(
            "Both successor instrument rows (TMPV and TMCV) must exist before migration."
        )
    connection.execute(
        "UPDATE instruments SET symbol = 'TMPV', effective_date = NULL, listing_date = NULL "
        "WHERE instrument_id = ?",
        (TMPV_ID,),
    )
    connection.execute(
        "UPDATE instruments SET effective_date = NULL, listing_date = NULL "
        "WHERE instrument_id = ?",
        (TMCV_ID,),
    )


def _update_mapping(
    connection: sqlite3.Connection,
    mapping_id: str,
    *,
    instrument_id: str,
    provider_symbol: str,
    provider_security_id: str | None,
    identity_status: str,
    mapping_status: str,
    is_primary: int,
    effective_from: str | None,
    effective_to: str | None,
    exchange_segment: str = "NSE_EQ",
) -> None:
    connection.execute(
        """
        UPDATE instrument_provider_mappings SET
            instrument_id = ?,
            provider_symbol = ?,
            provider_security_id = ?,
            exchange_segment = ?,
            identity_status = ?,
            mapping_status = ?,
            is_primary = ?,
            effective_from = ?,
            effective_to = ?,
            quote_endpoint_verified = 0,
            daily_history_verified = 0,
            intraday_history_verified = 0,
            live_feed_verified = 0,
            notes = COALESCE(notes, '')
        WHERE mapping_id = ?
        """,
        (
            instrument_id,
            provider_symbol,
            provider_security_id,
            exchange_segment,
            identity_status,
            mapping_status,
            is_primary,
            effective_from,
            effective_to,
            mapping_id,
        ),
    )


def _repair_mappings(connection: sqlite3.Connection) -> None:
    connection.execute(
        "UPDATE instrument_provider_mappings SET provider_security_id = NULL "
        "WHERE LOWER(provider) = 'yfinance'"
    )
    connection.execute(
        """
        UPDATE instrument_provider_mappings SET
            identity_status = CASE
                WHEN UPPER(mapping_status) = 'VERIFIED' THEN 'VERIFIED'
                ELSE 'UNVERIFIED'
            END,
            quote_endpoint_verified = 0,
            daily_history_verified = 0,
            intraday_history_verified = 0,
            live_feed_verified = 0
        """
    )

    definitions = (
        ("MAP_TATAMOTORS_YF", TATA_ID, "TATAMOTORS.NS", None, "UNVERIFIED", "UNAVAILABLE", 0, None, None),
        ("MAP_TATAMOTORS_DHAN", TATA_ID, "TATAMOTORS", "3456", "UNVERIFIED", "UNAVAILABLE", 0, None, None),
        ("MAP_TMPV_YF", TMPV_ID, "TMPV.NS", None, "VERIFIED", "VERIFIED", 1, None, None),
        ("MAP_TMPV_DHAN", TMPV_ID, "TMPV", "3456", "VERIFIED", "VERIFIED", 1, None, None),
        ("MAP_TMCV_YF", TMCV_ID, "TMCV.NS", None, "VERIFIED", "VERIFIED", 1, None, None),
        ("MAP_TMCV_DHAN", TMCV_ID, "TMCV", "759782", "VERIFIED", "VERIFIED", 1, None, None),
    )
    for (
        mapping_id,
        instrument_id,
        provider_symbol,
        security_id,
        identity_status,
        mapping_status,
        is_primary,
        effective_from,
        effective_to,
    ) in definitions:
        _update_mapping(
            connection,
            mapping_id,
            instrument_id=instrument_id,
            provider_symbol=provider_symbol,
            provider_security_id=security_id,
            identity_status=identity_status,
            mapping_status=mapping_status,
            is_primary=is_primary,
            effective_from=effective_from,
            effective_to=effective_to,
        )


def _repair_corporate_action(connection: sqlite3.Connection) -> None:
    columns = _columns(connection, "instrument_corporate_actions")
    assignments = {
        "instrument_id": TATA_ID,
        "pre_action_symbol": "TATAMOTORS",
        "post_action_symbol": "TMPV",
        "resulting_instrument_id": TMCV_ID,
        "resulting_instrument_ids": json.dumps([TMPV_ID, TMCV_ID]),
        "date_verification_status": "UNVERIFIED",
        "historical_adjustment_factor": None,
        "adjustment_treatment": "SEPARATE_SERIES_NO_PRICE_ADJUSTMENT",
    }
    selected = {key: value for key, value in assignments.items() if key in columns}
    if not selected:
        raise RuntimeError("Corporate-action schema cannot represent Tata lineage.")
    cursor = connection.execute(
        f"UPDATE instrument_corporate_actions SET "
        f"{', '.join(f'{_quote(key)} = ?' for key in selected)} "
        "WHERE action_id = 'CA_TATAMOTORS_DEMERGER_2025'",
        list(selected.values()),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("Expected exactly one Tata Motors demerger corporate-action row.")


def _nested_strings(value: Any):
    if isinstance(value, str):
        yield value
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return
        if parsed != value:
            yield from _nested_strings(parsed)
    elif isinstance(value, dict):
        for nested in value.values():
            yield from _nested_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _nested_strings(nested)


def _validate_symbol_references(connection: sqlite3.Connection) -> dict[str, int]:
    expected_symbols = {
        "TATAMOTORS": TATA_ID,
        "TMPV": TMPV_ID,
        "TMCV": TMCV_ID,
        "TELCO": TATA_ID,
        LEGACY_TATA_ID: TATA_ID,
    }
    resolved = {
        row["symbol"].upper(): row["instrument_id"]
        for row in connection.execute(
            "SELECT symbol, instrument_id FROM instruments "
            "WHERE instrument_id IN (?, ?, ?)",
            (TATA_ID, TMPV_ID, TMCV_ID),
        )
    }
    for symbol in ("TATAMOTORS", "TMPV", "TMCV"):
        if resolved.get(symbol) != expected_symbols[symbol]:
            raise RuntimeError(f"Symbol {symbol} does not resolve to its expected identity.")

    counts: dict[str, int] = {}
    tables = set(_tables(connection))
    for table, columns in REFERENCE_COLUMNS.items():
        if table not in tables:
            continue
        available = _columns(connection, table)
        for column in columns:
            if column not in available:
                continue
            count = 0
            for row in connection.execute(
                f"SELECT {_quote(column)} FROM {_quote(table)} "
                f"WHERE {_quote(column)} IS NOT NULL"
            ):
                for text in _nested_strings(row[0]):
                    normalized = text.strip().upper()
                    if normalized in expected_symbols:
                        if normalized in ("TATAMOTORS", "TMPV", "TMCV", "TELCO"):
                            target_id = expected_symbols[normalized]
                            if not _instrument(connection, target_id):
                                raise RuntimeError(
                                    f"{table}.{column} contains unresolved {normalized} reference."
                                )
                        count += 1
            counts[f"{table}.{column}"] = count
    return counts


def _validate(connection: sqlite3.Connection) -> dict[str, Any]:
    foreign_key_errors = [
        tuple(row) for row in connection.execute("PRAGMA foreign_key_check")
    ]
    if foreign_key_errors:
        raise RuntimeError(f"Foreign-key validation failed: {foreign_key_errors[:10]}")
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise RuntimeError(f"SQLite integrity check failed: {integrity}")
    duplicate_isins = connection.execute(
        """
        SELECT isin, COUNT(*) FROM instruments
        WHERE status = 'ACTIVE' AND isin IS NOT NULL
        GROUP BY isin HAVING COUNT(*) > 1
        """
    ).fetchall()
    if duplicate_isins:
        raise RuntimeError(f"Duplicate active ISINs found: {[tuple(r) for r in duplicate_isins]}")
    references = _validate_symbol_references(connection)
    return {
        "foreign_key_errors": 0,
        "integrity_check": "ok",
        "duplicate_active_isins": 0,
        "symbol_reference_counts": references,
    }


def _run_transaction(
    database_path: Path, *, fail_after_validation: bool = False
) -> dict[str, Any]:
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    before: dict[str, dict[str, Any]] = {}
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("PRAGMA defer_foreign_keys = ON")
        before = _table_snapshot(connection)
        _ensure_schema(connection)

        _repair_instrument_identity(connection)
        _repair_mappings(connection)
        _repair_corporate_action(connection)
        validation = _validate(connection)
        after = _table_snapshot(connection)

        deleted_rows = {
            table: (state["row_count"], after.get(table, {}).get("row_count", 0))
            for table, state in before.items()
            if after.get(table, {}).get("row_count", 0) < state["row_count"]
        }
        if deleted_rows:
            raise RuntimeError(f"Migration would delete rows: {deleted_rows}")
        protected_changes = {
            table: {
                "before": before[table],
                "after": after[table],
            }
            for table in PROTECTED_TABLES
            if table in before
            and before[table] != after.get(table)
        }
        if protected_changes:
            raise RuntimeError(
                f"Protected price or symbol-reference data changed: {protected_changes}"
            )
        if fail_after_validation:
            raise RuntimeError("Deliberate validation failure requested by test.")

        connection.commit()
        return {
            "row_counts_before": {k: v["row_count"] for k, v in before.items()},
            "row_counts_after": {k: v["row_count"] for k, v in after.items()},
            "checksums_before": {k: v["sha256"] for k, v in before.items()},
            "checksums_after": {k: v["sha256"] for k, v in after.items()},
            "changed_tables": sorted(
                table for table in before if before[table] != after.get(table)
            ),
            "protected_tables_unchanged": True,
            "validation": validation,
        }
    except Exception:
        connection.rollback()
        rolled_back = _table_snapshot(connection)
        if before and rolled_back != before:
            connection.close()
            raise RuntimeError("Rollback failed to restore the complete pre-migration snapshot.")
        raise
    finally:
        connection.close()


def _backup_database(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_connection = sqlite3.connect(str(target))
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()


def restore_backup(backup_path: str | Path, restored_path: str | Path) -> None:
    """Restore a backup to a new path; existing files are never overwritten."""
    backup = Path(backup_path).resolve()
    restored = Path(restored_path).resolve()
    if restored.exists():
        raise FileExistsError(f"Refusing to overwrite restore target: {restored}")
    _backup_database(backup, restored)


def _assert_not_application_database(database_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    protected = {
        (root / "backend" / "data" / "stock_intelligence.db").resolve(),
        (root / "backend" / "stock_intelligence.db").resolve(),
    }
    if database_path.resolve() in protected:
        raise RuntimeError("The active application database is prohibited for this migration.")


def migrate(
    db_path: str | Path,
    *,
    apply: bool = False,
    fail_after_validation: bool = False,
    backup_path: str | Path | None = None,
) -> dict[str, Any]:
    """Dry-run on a private copy by default; apply only to an explicit isolated DB."""
    source = Path(db_path).resolve()
    _assert_not_application_database(source)
    if not source.is_file():
        raise FileNotFoundError(f"Database file does not exist: {source}")

    if not apply:
        before_source = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            source_snapshot = _table_snapshot(before_source)
        finally:
            before_source.close()
        with tempfile.TemporaryDirectory(prefix="phase14_9_4_dryrun_") as folder:
            clone = Path(folder) / "dryrun.db"
            _backup_database(source, clone)
            result = _run_transaction(clone, fail_after_validation=fail_after_validation)
        after_source = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
        try:
            source_unchanged = source_snapshot == _table_snapshot(after_source)
        finally:
            after_source.close()
        if not source_unchanged:
            raise RuntimeError("Dry-run unexpectedly changed the source database.")
        return {"dry_run": True, "source_unchanged": True, **result}

    if backup_path is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = source.with_name(f"{source.stem}.pre_phase14_9_4_{stamp}.db")
    else:
        backup = Path(backup_path).resolve()
    _backup_database(source, backup)
    return {
        "dry_run": False,
        "backup": str(backup),
        **_run_transaction(source, fail_after_validation=fail_after_validation),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Explicit isolated SQLite database path")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply transactionally (default is a temporary-copy dry run)",
    )
    args = parser.parse_args()
    result = migrate(args.database, apply=args.apply)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
