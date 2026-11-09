from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from app import database
from app.services.dhan_instrument_service import DhanInstrumentService
from app.services.instrument_master_service import (
    InstrumentMasterService,
    MappingStatus,
    PriceAdjustmentPolicy,
)
from scripts.migrate_phase14_9_3_tata_lineage import (
    _table_snapshot,
    migrate,
    restore_backup,
)


@pytest.fixture
def isolated_instrument_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "instrument-test.db")
    database.init_db()
    service = InstrumentMasterService()
    service.seed_authoritative_universe()
    yield service


def _create_migration_fixture(path: Path, *, already_collapsed: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE instruments (
            instrument_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, company_name TEXT NOT NULL,
            isin TEXT, historical_isin TEXT, effective_date TEXT, exchange TEXT NOT NULL,
            security_type TEXT NOT NULL, is_fo_eligible INTEGER NOT NULL, fo_effective_date TEXT,
            is_cas_eligible INTEGER NOT NULL, cas_effective_date TEXT, cas_schedule_version TEXT,
            historical_symbols TEXT, listing_date TEXT, delisting_date TEXT, status TEXT NOT NULL,
            last_verified_date TEXT NOT NULL, verification_source TEXT NOT NULL,
            verification_provenance TEXT NOT NULL, created_at TEXT, updated_at TEXT
        );
        CREATE UNIQUE INDEX uq_active_isin ON instruments(isin)
            WHERE status = 'ACTIVE' AND isin IS NOT NULL;
        CREATE TABLE instrument_provider_mappings (
            mapping_id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
            provider TEXT NOT NULL, provider_symbol TEXT NOT NULL, provider_security_id TEXT,
            exchange_segment TEXT, mapping_status TEXT NOT NULL, is_primary INTEGER NOT NULL,
            verification_date TEXT NOT NULL, verification_method TEXT NOT NULL, notes TEXT,
            effective_from TEXT, effective_to TEXT,
            UNIQUE(instrument_id, provider, exchange_segment)
        );
        CREATE TABLE instrument_corporate_actions (
            action_id TEXT PRIMARY KEY,
            instrument_id TEXT NOT NULL REFERENCES instruments(instrument_id),
            action_type TEXT NOT NULL, ex_date TEXT NOT NULL, record_date TEXT, ratio TEXT,
            pre_action_symbol TEXT, post_action_symbol TEXT, resulting_instrument_id TEXT,
            historical_adjustment_factor REAL, adjustment_treatment TEXT NOT NULL,
            description TEXT NOT NULL, circular_reference TEXT, verified_at TEXT NOT NULL,
            created_at TEXT
        );
        CREATE TABLE stocks(symbol TEXT PRIMARY KEY);
        CREATE TABLE ohlcv(id INTEGER PRIMARY KEY, symbol TEXT, interval TEXT, timestamp TEXT, close REAL);
        CREATE TABLE fundamentals(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE shareholding(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE observed_intraday_ohlcv(
            id INTEGER PRIMARY KEY, symbol TEXT, interval TEXT, timestamp TEXT, close REAL
        );
        CREATE TABLE bar_provenance(id INTEGER PRIMARY KEY, symbol TEXT, provider_symbol TEXT);
        CREATE TABLE intraday_ingestion_runs(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE custom_watchlists(id INTEGER PRIMARY KEY, symbols_json TEXT);
        CREATE TABLE market_alerts(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE market_alert_history(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE saved_screeners(id INTEGER PRIMARY KEY, config_json TEXT);
        CREATE TABLE saved_custom_scanners(id INTEGER PRIMARY KEY, universe TEXT, conditions_json TEXT);
        CREATE TABLE research_trade_plans(id INTEGER PRIMARY KEY, symbol TEXT);
        CREATE TABLE research_notes(id INTEGER PRIMARY KEY, symbol TEXT);
        """
    )
    instruments = (
        (
            (
                "INST_NSE_TATAMOTORS", "TMPV",
                "Tata Motors Passenger Vehicles Limited", "INE155A01022", None, "ACTIVE",
            ),
            ("INST_NSE_TMCV", "TMCV", "Tata Motors Limited (Commercial Vehicles)", "INE1TAE01010", None, "ACTIVE"),
        )
        if already_collapsed
        else (
            ("INST_NSE_TATAMOTORS_HIST", "TATAMOTORS", "Tata Motors Limited", None, "INE155A01022", "DEMERGED"),
            ("INST_NSE_TMPV", "TMPV", "Tata Motors Passenger Vehicles Limited", "INE155A01022", None, "ACTIVE"),
            ("INST_NSE_TMCV", "TMCV", "Tata Motors Limited (Commercial Vehicles)", "INE1TAE01010", None, "ACTIVE"),
        )
    )
    for instrument_id, symbol, company_name, isin, historical_isin, status in instruments:
        connection.execute(
            """
            INSERT INTO instruments (
                instrument_id, symbol, company_name, isin, historical_isin, exchange,
                security_type, is_fo_eligible, is_cas_eligible, status, last_verified_date,
                verification_source, verification_provenance
            ) VALUES (?, ?, ?, ?, ?, 'NSE', 'EQUITY', 1, 1, ?, '2026-11-06', 'test', 'test')
            """,
            (instrument_id, symbol, company_name, isin, historical_isin, status),
        )
    predecessor_id = "INST_NSE_TATAMOTORS" if already_collapsed else "INST_NSE_TATAMOTORS_HIST"
    passenger_id = "INST_NSE_TATAMOTORS" if already_collapsed else "INST_NSE_TMPV"
    mappings = (
        ("MAP_TATAMOTORS_YF", predecessor_id, "yfinance", "TATAMOTORS.NS", "3456", "NSE_EQ_HISTORICAL"),
        ("MAP_TATAMOTORS_DHAN", predecessor_id, "dhan", "TATAMOTORS", "3456", "NSE_EQ_HISTORICAL"),
        ("MAP_TMPV_YF", passenger_id, "yfinance", "TMPV.NS", "3456", "NSE_EQ"),
        ("MAP_TMPV_DHAN", passenger_id, "dhan", "TMPV", "3456", "NSE_EQ"),
        ("MAP_TMCV_YF", "INST_NSE_TMCV", "yfinance", "TMCV.NS", "759782", "NSE_EQ"),
        ("MAP_TMCV_DHAN", "INST_NSE_TMCV", "dhan", "TMCV", "759782", "NSE_EQ"),
    )
    for mapping_id, instrument_id, provider, provider_symbol, security_id, segment in mappings:
        connection.execute(
            """
            INSERT INTO instrument_provider_mappings (
                mapping_id, instrument_id, provider, provider_symbol, provider_security_id,
                exchange_segment, mapping_status, is_primary, verification_date,
                verification_method, effective_from, effective_to
            ) VALUES (?, ?, ?, ?, ?, ?, 'VERIFIED', 1, '2026-11-06', 'fixture', NULL, NULL)
            """,
            (mapping_id, instrument_id, provider, provider_symbol, security_id, segment),
        )
    connection.execute(
        """
        INSERT INTO instrument_corporate_actions (
            action_id, instrument_id, action_type, ex_date, ratio, pre_action_symbol,
            post_action_symbol, resulting_instrument_id, historical_adjustment_factor,
            adjustment_treatment, description, verified_at
        ) VALUES (
            'CA_TATAMOTORS_DEMERGER_2025', ?, 'DEMERGER',
            '2025-10-24', '1:1', 'TATAMOTORS', 'TMPV', 'INST_NSE_TMCV', 1.0,
            'UNADJUSTED', 'fixture', '2026-11-06'
        )
        """,
        (predecessor_id,),
    )
    for table, symbol in (
        ("stocks", "TATAMOTORS"),
        ("ohlcv", "TATAMOTORS"),
        ("fundamentals", "TMPV"),
        ("shareholding", "TMCV"),
        ("observed_intraday_ohlcv", "TATAMOTORS"),
        ("bar_provenance", "TATAMOTORS"),
        ("intraday_ingestion_runs", "TMPV"),
        ("market_alerts", "TATAMOTORS"),
        ("market_alert_history", "TATAMOTORS"),
        ("research_trade_plans", "TMCV"),
        ("research_notes", "TATAMOTORS"),
    ):
        connection.execute(f"INSERT INTO {table}(symbol) VALUES (?)", (symbol,))
    connection.execute(
        "INSERT INTO custom_watchlists(symbols_json) VALUES (?)",
        (json.dumps(["TATAMOTORS", "TMPV", "TMCV"]),),
    )
    connection.execute(
        "INSERT INTO saved_screeners(config_json) VALUES (?)",
        (json.dumps({"symbols": ["TATAMOTORS", "TMPV", "TMCV"]}),),
    )
    connection.execute(
        "INSERT INTO saved_custom_scanners(universe, conditions_json) VALUES (?, ?)",
        ("TATAMOTORS", json.dumps({"symbol": "TMPV"})),
    )
    connection.execute("INSERT INTO ohlcv(symbol, interval, timestamp, close) VALUES ('TATAMOTORS','1D','2025-10-23',100)")
    connection.execute("INSERT INTO observed_intraday_ohlcv(symbol, interval, timestamp, close) VALUES ('TATAMOTORS','5m','2025-10-23T09:15:00',100)")
    connection.execute("INSERT INTO bar_provenance(symbol, provider_symbol) VALUES ('TATAMOTORS','TATAMOTORS.NS')")
    connection.commit()
    connection.close()


def test_tata_identity_resolution_and_repeat_seed(isolated_instrument_db):
    service = isolated_instrument_db
    expected_count = len(database.get_instruments())

    predecessor = service.resolve_instrument("TATAMOTORS")
    assert predecessor["instrument_id"] == "INST_NSE_TATAMOTORS"
    assert predecessor["status"] == "DEMERGED"
    assert service.resolve_instrument("INST_NSE_TATAMOTORS_HIST")["instrument_id"] == "INST_NSE_TATAMOTORS"
    assert service.resolve_instrument("TMPV")["instrument_id"] == "INST_NSE_TMPV"
    assert service.resolve_instrument("TMCV")["instrument_id"] == "INST_NSE_TMCV"
    assert service.resolve_instrument("TMPV")["instrument_id"] != service.resolve_instrument("TMCV")["instrument_id"]

    assert service.resolve_symbol_for_date("TATAMOTORS", "2025-10-23") is None
    assert service.resolve_symbol_for_date("TATAMOTORS", "2025-10-24") is None
    assert service.resolve_symbol_for_date("TMPV", "2025-10-23") is None
    assert service.resolve_symbol_for_date("TMPV", "2026-03-01") is None
    assert service.resolve_provider_security_id("dhan", "3456")["symbol"] == "TMPV"
    assert service.resolve_provider_security_id("dhan", "3456", query_date="2025-05-15") is None
    assert service.resolve_provider_security_id("dhan", "3456", query_date="2026-03-01") is None
    assert service.resolve_provider_security_id(
        "dhan", "3456", exchange="BSE", exchange_segment="NSE_EQ", instrument_type="EQUITY"
    ) is None
    assert service.get_dhan_security_id("TATAMOTORS") is None

    service.seed_authoritative_universe()
    service.seed_authoritative_universe()
    instruments = database.get_instruments()
    mappings = database.get_provider_mappings()
    assert len(instruments) == expected_count
    assert not any(row["instrument_id"] == "INST_NSE_TATAMOTORS_HIST" for row in instruments)
    assert not any(row["instrument_id"] == "INST_NSE_TMPV_HIST" for row in instruments)
    assert all(
        row["provider_security_id"] is None
        for row in mappings
        if row["provider"] == "yfinance"
    )
    assert all(
        not row["quote_endpoint_verified"]
        and not row["daily_history_verified"]
        and not row["intraday_history_verified"]
        and not row["live_feed_verified"]
        for row in mappings
    )
    tmpv_capabilities = service.get_provider_capabilities("TMPV", "dhan")
    assert tmpv_capabilities["identity_verified"]
    assert not tmpv_capabilities["quote_endpoint_verified"]
    assert not tmpv_capabilities["daily_history_verified"]
    assert not tmpv_capabilities["intraday_history_verified"]
    assert not tmpv_capabilities["live_feed_verified"]


def test_legacy_tata_instrument_row_is_rejected_without_mutation(isolated_instrument_db):
    with database.connect() as connection:
        columns = [
            row[1] for row in connection.execute("PRAGMA table_info(instruments)").fetchall()
        ]
        predecessor = connection.execute(
            "SELECT * FROM instruments WHERE instrument_id = 'INST_NSE_TATAMOTORS'"
        ).fetchone()
        assert predecessor is not None
        legacy_row = list(predecessor)
        legacy_row[columns.index("instrument_id")] = "INST_NSE_TATAMOTORS_HIST"
        legacy_row[columns.index("isin")] = None
        legacy_row[columns.index("status")] = "DEMERGED"
        connection.execute(
            "INSERT INTO instruments ("
            + ", ".join(f'"{column}"' for column in columns)
            + ") VALUES ("
            + ", ".join("?" for _ in columns)
            + ")",
            legacy_row,
        )
        before_count = connection.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]

    service = InstrumentMasterService()
    with pytest.raises(RuntimeError, match="Legacy INST_NSE_TATAMOTORS_HIST row found"):
        service.ensure_seeded()

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM instruments").fetchone()[0] == before_count
        assert connection.execute(
            "SELECT 1 FROM instruments WHERE instrument_id = 'INST_NSE_TATAMOTORS_HIST'"
        ).fetchone() is not None


def test_tax_allocation_is_not_a_price_adjustment(isolated_instrument_db):
    service = isolated_instrument_db
    with pytest.raises(ValueError, match="accounting metadata"):
        service.get_price_continuity_series(
            "TMPV", "2025-01-01", "2025-11-01", "COST_APPORTIONMENT"
        )
    result = service.get_price_continuity_series(
        "TMPV", "2025-01-01", "2025-11-01", PriceAdjustmentPolicy.RAW_ONLY
    )
    assert result["status"] == "EFFECTIVE_DATE_UNVERIFIED"
    assert result["predecessor_data_status"] == "UNKNOWN_EFFECTIVE_DATE"
    assert "adjustment_factor_applied" not in result
    assert "tax_cost_allocation_metadata" not in result
    assert service.get_tax_cost_allocation_metadata("TMPV")["allocation_pct"] == 68.85
    assert service.get_tax_cost_allocation_metadata("TMCV")["allocation_pct"] == 31.15


def test_dhan_lookup_requires_matching_exchange_segment_and_type(tmp_path: Path):
    service = DhanInstrumentService(scrip_csv_path=str(tmp_path / "missing.csv"))
    assert service.get_instrument("3456").symbol == "TMPV"
    assert service.get_instrument("3456", exchange_segment="NSE_EQ", exchange="NSE").symbol == "TMPV"
    assert service.get_instrument(
        "3456", exchange_segment="NSE_FNO", exchange="NSE", instrument_type="EQUITY"
    ) is None
    assert service.get_instrument(
        "3456", exchange_segment="NSE_EQ", exchange="BSE", instrument_type="EQUITY"
    ) is None
    assert service.get_instrument(
        "3456", exchange_segment="NSE_EQ", exchange="NSE", instrument_type="INDEX"
    ) is None
    assert service.get_instrument(
        "3456", exchange_segment="NSE_EQ", exchange="NSE", instrument_type="EQUITY",
        query_date="2025-10-23",
    ) is None
    assert service.get_instrument(
        "3456", exchange_segment="NSE_EQ", exchange="NSE", instrument_type="EQUITY",
        query_date="2025-10-24",
    ) is None


def test_migration_dry_run_apply_backup_restore_and_idempotence(tmp_path: Path):
    source = tmp_path / "lineage.db"
    _create_migration_fixture(source)
    before_connection = sqlite3.connect(source)
    before = _table_snapshot(before_connection)
    before_connection.close()

    preview = migrate(source)
    assert preview["dry_run"] is True
    assert preview["source_unchanged"] is True
    assert preview["protected_tables_unchanged"] is True

    after_dry_connection = sqlite3.connect(source)
    assert _table_snapshot(after_dry_connection) == before
    after_dry_connection.close()

    backup = tmp_path / "lineage-before.db"
    result = migrate(source, apply=True, backup_path=backup)
    assert result["dry_run"] is False
    assert result["backup"] == str(backup)
    assert result["protected_tables_unchanged"] is True
    assert result["validation"]["foreign_key_errors"] == 0
    assert result["validation"]["integrity_check"] == "ok"
    assert result["row_counts_before"] == result["row_counts_after"]

    migrated = sqlite3.connect(source)
    migrated.row_factory = sqlite3.Row
    assert migrated.execute(
        "SELECT instrument_id, symbol FROM instruments WHERE instrument_id = 'INST_NSE_TATAMOTORS'"
    ).fetchone()["symbol"] == "TATAMOTORS"
    assert migrated.execute(
        "SELECT resulting_instrument_ids FROM instrument_corporate_actions "
        "WHERE action_id = 'CA_TATAMOTORS_DEMERGER_2025'"
    ).fetchone()[0] == json.dumps(["INST_NSE_TMPV", "INST_NSE_TMCV"])
    assert migrated.execute(
        "SELECT date_verification_status FROM instrument_corporate_actions "
        "WHERE action_id = 'CA_TATAMOTORS_DEMERGER_2025'"
    ).fetchone()[0] == "UNVERIFIED"
    migrated.close()

    restored = tmp_path / "restored.db"
    restore_backup(backup, restored)
    restored_connection = sqlite3.connect(restored)
    assert _table_snapshot(restored_connection) == before
    restored_connection.close()
    with pytest.raises(FileExistsError):
        restore_backup(backup, restored)

    second_backup = tmp_path / "lineage-after-first-apply.db"
    repeated = migrate(source, apply=True, backup_path=second_backup)
    assert repeated["row_counts_before"] == repeated["row_counts_after"]
    assert repeated["changed_tables"] == []


def test_migration_rolls_back_after_deliberate_validation_failure(tmp_path: Path):
    source = tmp_path / "rollback.db"
    _create_migration_fixture(source)
    before_connection = sqlite3.connect(source)
    before = _table_snapshot(before_connection)
    before_connection.close()

    with pytest.raises(RuntimeError, match="Deliberate validation failure"):
        migrate(
            source,
            apply=True,
            fail_after_validation=True,
            backup_path=tmp_path / "rollback-backup.db",
        )

    after_connection = sqlite3.connect(source)
    assert _table_snapshot(after_connection) == before
    assert after_connection.execute("PRAGMA foreign_key_check").fetchall() == []
    after_connection.close()


def test_migration_repairs_previously_collapsed_predecessor_without_deleting_rows(tmp_path: Path):
    source = tmp_path / "previously-collapsed.db"
    _create_migration_fixture(source, already_collapsed=True)
    before_connection = sqlite3.connect(source)
    before = _table_snapshot(before_connection)
    before_connection.close()

    result = migrate(
        source,
        apply=True,
        backup_path=tmp_path / "previously-collapsed-backup.db",
    )
    assert result["row_counts_after"]["instruments"] == (
        result["row_counts_before"]["instruments"] + 1
    )
    assert result["protected_tables_unchanged"] is True
    connection = sqlite3.connect(source)
    ids = {
        row[0] for row in connection.execute(
            "SELECT instrument_id FROM instruments"
        )
    }
    assert {"INST_NSE_TATAMOTORS", "INST_NSE_TMPV", "INST_NSE_TMCV"}.issubset(ids)
    assert "INST_NSE_TATAMOTORS_HIST" not in ids
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
