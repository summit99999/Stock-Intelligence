from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from app import database
from app.services import instrument_master_service


@pytest.fixture(scope="module")
def prepared_current_instrument_database(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[instrument_master_service.InstrumentMasterService]:
    """Provide canonical instruments on a private pre-14.9 market-data copy."""
    source_db = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "stock_intelligence_backup_phase14_8_20261106_pre14_9.db"
    )
    if not source_db.is_file():
        raise FileNotFoundError(f"Instrument test baseline does not exist: {source_db}")

    original_db_path = database.DB_PATH
    original_database_url = database.DATABASE_URL
    original_service = instrument_master_service._service_instance

    test_db = tmp_path_factory.mktemp("current-instrument-state") / "current-instruments.db"
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    destination = sqlite3.connect(test_db)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    try:
        database.DB_PATH = test_db
        database.DATABASE_URL = ""
        instrument_master_service._service_instance = None

        def row_counts(tables: tuple[str, ...]) -> dict[str, int]:
            with database.connect() as connection:
                return {
                    table: int(
                        connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    )
                    for table in tables
                }

        protected_tables = ("ohlcv", "observed_intraday_ohlcv", "bar_provenance")
        before = row_counts(protected_tables)
        database.init_db()

        service = instrument_master_service.get_instrument_master_service()
        current_counts = row_counts(
            ("instruments", "instrument_provider_mappings", "instrument_corporate_actions")
        )
        instrument_master_service.InstrumentMasterService().ensure_seeded()
        if row_counts(
            ("instruments", "instrument_provider_mappings", "instrument_corporate_actions")
        ) != current_counts:
            raise AssertionError("Repeated instrument seeding changed canonical master row counts")
        if row_counts(protected_tables) != before:
            raise AssertionError("Preparing current instrument state changed protected market data")

        yield service
    finally:
        instrument_master_service._service_instance = original_service
        database.DB_PATH = original_db_path
        database.DATABASE_URL = original_database_url
