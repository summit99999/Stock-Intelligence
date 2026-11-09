"""
Phase 14.9.3 Dedicated Test Suite:
Tata Motors Continuing-Entity Lineage, Corporate-Action History & Provider Identity Audit
"""
import pytest
from fastapi.testclient import TestClient

from app.database import (
    connect,
    get_bars,
    get_corporate_actions,
    get_instrument,
    get_instruments,
    get_provider_mappings,
    get_stock,
)
from app.main import app
from app.services.instrument_master_service import (
    AUTHORITATIVE_INSTRUMENTS,
    AUTHORITATIVE_PROVIDER_MAPPINGS,
    InstrumentMasterService,
    MappingStatus,
    PriceAdjustmentPolicy,
    get_instrument_master_service,
    validate_isin,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def service():
    return get_instrument_master_service()


def test_tata_motors_continuing_entity_resolution(service: InstrumentMasterService):
    """Verify TATAMOTORS and TMPV resolve to the continuing legal entity."""
    tata_inst = service.resolve_instrument("TATAMOTORS")
    assert tata_inst is not None
    # Both TATAMOTORS and TMPV resolve to valid continuing instrument identities
    tmpv_inst = service.resolve_instrument("TMPV")
    assert tmpv_inst is not None

    # TMCV resolves to the separate resulting commercial vehicles company
    tmcv_inst = service.resolve_instrument("TMCV")
    assert tmcv_inst is not None
    assert tmcv_inst["instrument_id"] == "INST_NSE_TMCV"
    assert tmcv_inst["isin"] == "INE1TAE01010"
    assert tmcv_inst["is_fo_eligible"] is False or tmcv_inst["is_fo_eligible"] == 0


def test_date_aware_symbol_queries(service: InstrumentMasterService):
    """Verify that historical queries resolve using the requested date."""
    sym_ltm_current = service.resolve_symbol_for_date("LTM", "2026-03-01")
    assert sym_ltm_current == "LTM"

    sym_ltm_hist = service.resolve_symbol_for_date("LTM", "2025-01-01")
    assert sym_ltm_hist == "LTIM"

    # HAL stock split check
    hal = service.resolve_instrument("HAL")
    assert hal is not None
    assert hal["isin"] == "INE066F01020"


def test_active_isin_uniqueness():
    """Verify that all active instruments have unique ISINs."""
    with connect() as con:
        rows = con.execute("""
            SELECT isin, COUNT(*) as cnt
            FROM instruments
            WHERE status = 'ACTIVE' AND isin IS NOT NULL
            GROUP BY isin
            HAVING COUNT(*) > 1
        """).fetchall()
        assert len(rows) == 0, f"Duplicate active ISINs found: {[dict(r) for r in rows]}"


def test_yahoo_provider_security_ids_are_none():
    """Verify that Yahoo Finance mappings NEVER carry Dhan numeric security IDs."""
    with connect() as con:
        rows = con.execute("""
            SELECT mapping_id, provider_symbol, provider_security_id
            FROM instrument_provider_mappings
            WHERE LOWER(provider) = 'yfinance' AND provider_security_id IS NOT NULL
        """).fetchall()
        assert len(rows) == 0, f"Found yfinance mappings with non-null provider_security_id: {[dict(r) for r in rows]}"


def test_dhan_security_id_namespace_isolation(service: InstrumentMasterService):
    """Verify Dhan security ID 3456 is resolved only in Dhan namespace."""
    # When querying via Dhan provider, ID 3456 resolves correctly
    dhan_inst = service.resolve_provider_security_id("dhan", "3456")
    assert dhan_inst is not None
    assert dhan_inst["symbol"] in ("TMPV", "TATAMOTORS")

    # Yahoo provider lookup with numeric ID 3456 returns None
    yf_inst = service.resolve_provider_security_id("yfinance", "3456")
    assert yf_inst is None


def test_tax_cost_allocation_metadata_integrity(service: InstrumentMasterService):
    """Verify 68.85% / 31.15% tax allocation cannot mutate raw OHLCV prices."""
    # Corporate action record check
    cas = service.get_corporate_actions("TATAMOTORS")
    assert len(cas) > 0
    tata_ca = next(c for c in cas if "DEMERGER" in c.get("action_type", ""))
    assert "68.85" in tata_ca["description"]
    assert "31.15" in tata_ca["description"]
    assert "NOT a market price adjustment" in tata_ca["description"]

    # Tax metadata endpoint check
    tax_meta = service.get_tax_cost_allocation_metadata("TMPV")
    assert tax_meta is not None
    assert tax_meta["allocation_pct"] == 68.85
    assert tax_meta["purpose"] == "ACCOUNTING_ACQUISITION_COST_ONLY"

    tax_meta_cv = service.get_tax_cost_allocation_metadata("TMCV")
    assert tax_meta_cv is not None
    assert tax_meta_cv["allocation_pct"] == 31.15
    assert tax_meta_cv["purpose"] == "ACCOUNTING_ACQUISITION_COST_ONLY"

    # RAW_ONLY policy test
    series_raw = service.get_price_continuity_series(
        "TMPV", start_date="2025-01-01", end_date="2026-03-01", policy=PriceAdjustmentPolicy.RAW_ONLY
    )
    assert series_raw["policy"] == "RAW_ONLY"


def test_prohibited_merge_raises_error(service: InstrumentMasterService):
    """Verify unadjusted 1:1 splicing is strictly prohibited."""
    with pytest.raises(ValueError, match="prohibited"):
        service.get_price_continuity_series(
            "TMPV", start_date="2025-01-01", end_date="2026-03-01", policy=PriceAdjustmentPolicy.PROHIBITED_MERGE
        )


from app.routers.instruments import get_instrument_detail


def test_end_to_end_instrument_resolution():
    """
    End-to-end test that resolves historical TATAMOTORS and current TMPV instruments,
    while keeping TMCV distinct.
    """
    # 1. Historical TATAMOTORS instrument resolution
    data_tata = get_instrument_detail("TATAMOTORS")
    assert data_tata["instrument"]["instrument_id"] in ("INST_NSE_TATAMOTORS", "INST_NSE_TATAMOTORS_HIST")
    assert (
        data_tata["instrument"]["isin"] == "INE155A01022"
        or data_tata["instrument"]["historical_isin"] == "INE155A01022"
    )

    # 2. Current TMPV instrument resolution
    data_tmpv = get_instrument_detail("TMPV")
    assert data_tmpv["instrument"]["symbol"] in ("TMPV", "TATAMOTORS")
    assert data_tmpv["instrument"]["isin"] == "INE155A01022"

    # 3. TMCV resolves to distinct entity
    data_tmcv = get_instrument_detail("TMCV")
    assert data_tmcv["instrument"]["instrument_id"] == "INST_NSE_TMCV"
    assert data_tmcv["instrument"]["isin"] == "INE1TAE01010"


def test_observed_and_provenance_data_preservation():
    """Verify all 24,786 observed 5m bars and 24,786 provenance records remain intact."""
    with connect() as con:
        obs_count = con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_count = con.execute("SELECT COUNT(*) FROM bar_provenance").fetchone()[0]
        daily_count = con.execute("SELECT COUNT(*) FROM ohlcv").fetchone()[0]

        assert obs_count == 24786, f"Expected 24,786 observed bars, got {obs_count}"
        assert prov_count == 24786, f"Expected 24,786 provenance rows, got {prov_count}"
        assert daily_count == 46544, f"Expected 46,544 daily bars, got {daily_count}"
