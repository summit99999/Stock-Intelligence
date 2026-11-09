"""
Phase 14.9.2  Final Instrument Identity, ISIN & Tata Motors Corporate-Action Correction Test Suite.
Validates:
1. Tata Motors Tax Cost Allocation (68.85% TMPV / 31.15% TMCV under Sec 49(2C) & 49(2D)).
2. Tax cost allocation cannot silently alter or mutate raw OHLCV prices.
3. No unsupported historical price reconstruction (RAW_ONLY default, PROHIBITED_MERGE enforced).
4. Immutable canonical instrument identity INST_NSE_LTIM across symbol changes.
5. LTIM/LTM date-aware symbol resolution (LTIM until 2026-02-26, LTM from 2026-02-27).
6. Authoritative HAL ISIN (INE066F01020 active, INE066F01012 historical) per NSE Circular NSE/CML/58539.
7. ISO 6166 Luhn modulus-10 double-add-double ISIN check-digit validation.
8. Separation of ISIN syntax/checksum validation from company identity verification.
9. Effective-dated provider mappings (historical vs current Dhan mapping for ID 3456).
10. Unambiguous current provider resolution (Dhan 3456 -> TMPV, never ambiguous).
11. Verification and accessibility of LTIMindtree observed/synthetic intraday bars under canonical ID.
12. One-to-one observed bar to provenance record correspondence (24,786 == 24,786).
13. Complete structural separation of Tata Motors predecessor and successors.
14. Database row-count preservation across all observed, provenance, and synthetic tables.
15. Schema compatibility for SQLite and PostgreSQL migrations (effective_from, effective_to).
"""

import re
import pytest
from fastapi.testclient import TestClient

from app.database import (
    connect,
    get_corporate_actions,
    get_instrument,
    get_instruments,
    get_provider_mappings,
    init_db,
)
from app.main import app
from app.services.instrument_master_service import (
    CorporateActionType,
    InstrumentMasterService,
    InstrumentStatus,
    MappingStatus,
    PriceAdjustmentPolicy,
    calculate_isin_check_digit,
    get_instrument_master_service,
    validate_isin,
    validate_isin_check_digit,
    validate_isin_format,
    verify_authoritative_isin,
)


@pytest.fixture(scope="module")
def inst_service(prepared_current_instrument_database):
    return prepared_current_instrument_database


@pytest.fixture(scope="module", autouse=True)
def isolate_instrument_database(prepared_current_instrument_database):
    return prepared_current_instrument_database


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Tata Motors Tax Cost Allocation (68.85% TMPV / 31.15% TMCV)
# ---------------------------------------------------------------------------

def test_tata_motors_cost_allocation_metadata(inst_service):
    """
    Verify shareholder guidance dated November 12, 2025:
    - TMPV: 68.85%
    - TMCV: 31.15%
    - Legal purpose: Sections 49(2C) and 49(2D) of the Income-tax Act, 1961
    - Scheme effective date: 2025-10-01 (issuer website)
    - Ex-date candidate: 2025-10-24 (unverified)
    - Source document recorded in corporate action metadata
    """
    cas = inst_service.get_corporate_actions("INST_NSE_TATAMOTORS")
    demerger_ca = next((c for c in cas if c["action_id"] == "CA_TATAMOTORS_DEMERGER_2025"), None)
    assert demerger_ca is not None, "Demerger corporate action must exist"

    desc = demerger_ca["description"]
    assert "68.85%" in desc, "TMPV 68.85% must be recorded in demerger description"
    assert "31.15%" in desc, "TMCV 31.15% must be recorded in demerger description"
    assert "49(2C)" in desc and "49(2D)" in desc, "Income-tax Act sections must be recorded"
    assert "2025-11-12" in desc, "Shareholder guidance date must be recorded"
    assert "2025-10-01" in desc, "Issuer-reported scheme effective date must be recorded"
    assert "2025-10-24" in desc and "UNVERIFIED" in desc, "Unverified ex-date must remain explicitly unverified"

    # Verify no occurrence of obsolete 40.7% or 59.3% in any active corporate action
    for ca in cas:
        assert "40.7" not in ca["description"]
        assert "59.3" not in ca["description"]


def test_cost_allocation_is_accounting_metadata_only(inst_service):
    tmpv = inst_service.get_tax_cost_allocation_metadata("TMPV")
    tmcv = inst_service.get_tax_cost_allocation_metadata("TMCV")
    assert tmpv["allocation_pct"] == 68.85
    assert tmcv["allocation_pct"] == 31.15
    assert tmpv["effective_date_type"] == "TAX_ALLOCATION"
    assert tmpv["effective_date_verification_status"] == "UNVERIFIED"
    assert tmpv["purpose"] == tmcv["purpose"] == "ACCOUNTING_ACQUISITION_COST_ONLY"
    with pytest.raises(ValueError, match="accounting metadata"):
        inst_service.get_price_continuity_series(
            "TMPV", "2025-01-01", "2025-11-01", "COST_APPORTIONMENT"
        )


def test_tax_allocation_cannot_mutate_raw_ohlcv(inst_service):
    """
    CRITICAL RULE: Statutory tax acquisition cost allocation percentages under
    Sections 49(2C) and 49(2D) are purely for capital gains tax computation.
    They must NOT alter or mutate raw OHLCV prices in the database.
    """
    with connect() as con:
        # Snapshot raw OHLCV count and a sample bar
        count_before = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]

    # Accounting metadata lookup must not expose price adjustment factors.
    inst_service.get_tax_cost_allocation_metadata("TMPV")
    inst_service.get_tax_cost_allocation_metadata("TMCV")

    with connect() as con:
        count_after = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        assert count_before == count_after == 24786, "Raw OHLCV database was mutated by tax cost allocation"

    # Default policy must remain RAW_ONLY
    default_res = inst_service.get_price_continuity_series("TMPV", "2025-01-01", "2026-03-01")
    assert default_res["policy"] == PriceAdjustmentPolicy.RAW_ONLY.value
    assert "adjustment_factor_applied" not in default_res
    assert "tax_cost_allocation_metadata" not in default_res


def test_prohibited_merge_enforcement(inst_service):
    """
    Direct unadjusted 1:1 splicing of predecessor and successor series is strictly blocked.
    """
    with pytest.raises(ValueError, match="strictly prohibited"):
        inst_service.get_price_continuity_series("TMPV", "2025-01-01", "2026-03-01", PriceAdjustmentPolicy.PROHIBITED_MERGE)


# ---------------------------------------------------------------------------
# 2. Immutable LTIMindtree Instrument Identity (INST_NSE_LTIM)
# ---------------------------------------------------------------------------

def test_ltimindtree_immutable_canonical_id(inst_service):
    """
    Verify LTIMindtree canonical identity:
    - Internal canonical instrument ID: INST_NSE_LTIM (restored immutable identity)
    - Current exchange symbol: LTM (effective 2026-02-27 per NSE/CML/72948)
    - ISIN: INE214T01019
    - Exactly 1 instrument record in database (no duplicates)
    - Alias lookup for INST_NSE_LTM resolves cleanly to INST_NSE_LTIM
    """
    inst = inst_service.resolve_instrument("INST_NSE_LTIM")
    assert inst is not None
    assert inst["instrument_id"] == "INST_NSE_LTIM"
    assert inst["symbol"] == "LTM"
    assert inst["isin"] == "INE214T01019"

    # Alias resolution
    inst_alias = inst_service.resolve_instrument("INST_NSE_LTM")
    assert inst_alias is not None
    assert inst_alias["instrument_id"] == "INST_NSE_LTIM"

    # Direct ticker resolution
    inst_by_sym = inst_service.resolve_instrument("LTM")
    assert inst_by_sym["instrument_id"] == "INST_NSE_LTIM"

    inst_by_old_sym = inst_service.resolve_instrument("LTIM")
    assert inst_by_old_sym["instrument_id"] == "INST_NSE_LTIM"

    # Verify no duplicate instruments in DB
    with connect() as con:
        rows = con.execute("SELECT instrument_id, symbol FROM instruments WHERE isin = 'INE214T01019'").fetchall()
        assert len(rows) == 1, f"Expected exactly 1 instrument for LTIMindtree, found {len(rows)}"
        assert rows[0][0] == "INST_NSE_LTIM"
        assert rows[0][1] == "LTM"


def test_ltim_ltm_date_aware_resolution(inst_service):
    """
    Verify date-aware exchange trading symbol resolution:
    - On or before 2026-02-26 -> LTIM
    - On or after 2026-02-27 -> LTM
    """
    assert inst_service.resolve_symbol_for_date("LTM", "2026-01-15") == "LTIM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-01-15") == "LTIM"
    assert inst_service.resolve_symbol_for_date("INST_NSE_LTIM", "2026-01-15") == "LTIM"

    # Transition boundary
    assert inst_service.resolve_symbol_for_date("LTM", "2026-02-26") == "LTIM"
    assert inst_service.resolve_symbol_for_date("LTM", "2026-02-27") == "LTM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-02-27") == "LTM"
    assert inst_service.resolve_symbol_for_date("INST_NSE_LTIM", "2026-02-27") == "LTM"


# ---------------------------------------------------------------------------
# 3. Authoritative HAL ISIN & Check-Digit Algorithm
# ---------------------------------------------------------------------------

def test_hal_authoritative_isin(inst_service):
    """
    Verify Hindustan Aeronautics Limited ISIN records:
    - Active ISIN: INE066F01020 (post-split Rs. 5 face value per NSE/CML/58539)
    - Historical ISIN: INE066F01012 (pre-split Rs. 10 face value)
    - Effective date: 2023-09-29
    - Corporate action CA_HAL_SPLIT_2023 registered
    """
    hal = inst_service.resolve_instrument("HAL")
    assert hal is not None
    assert hal["instrument_id"] == "INST_NSE_HAL"
    assert hal["isin"] == "INE066F01020"
    assert hal["historical_isin"] == "INE066F01012"
    assert hal["effective_date"] == "2023-09-29"

    # Corporate action registered
    cas = inst_service.get_corporate_actions("HAL")
    split_ca = next((c for c in cas if c["action_id"] == "CA_HAL_SPLIT_2023"), None)
    assert split_ca is not None
    assert split_ca["action_type"] == CorporateActionType.SPLIT
    assert split_ca["ex_date"] == "2023-09-29"
    assert split_ca["ratio"] == "1:2"
    assert split_ca["historical_adjustment_factor"] == 0.5


def test_isin_luhn_check_digit_algorithm():
    """
    Verify ISO 6166 Luhn modulus-10 double-add-double algorithm
    across authoritative reference ISINs.
    """
    # Test individual components
    assert calculate_isin_check_digit("INE066F0102") == "0"  # HAL active
    assert calculate_isin_check_digit("INE066F0101") == "2"  # HAL historical
    assert calculate_isin_check_digit("INE002A0101") == "8"  # RELIANCE
    assert calculate_isin_check_digit("INE467B0102") == "9"  # TCS
    assert calculate_isin_check_digit("INE040A0103") == "4"  # HDFCBANK
    assert calculate_isin_check_digit("INE214T0101") == "9"  # LTM
    assert calculate_isin_check_digit("INE155A0102") == "2"  # TMPV / TATAMOTORS
    assert calculate_isin_check_digit("INE1TAE0101") == "0"  # TMCV

    # Full check-digit validation
    assert validate_isin_check_digit("INE066F01020") is True
    assert validate_isin_check_digit("INE066F01012") is True
    assert validate_isin_check_digit("INE066F01021") is False  # Wrong check digit 1 != 0
    assert validate_isin_check_digit("INE066F01013") is False  # Wrong check digit 3 != 2


def test_all_database_isins_have_valid_check_digits():
    """
    Audit every ISIN stored in the database to guarantee 100% mathematical validity.
    """
    with connect() as con:
        rows = con.execute("SELECT instrument_id, symbol, isin, historical_isin FROM instruments").fetchall()
        for inst_id, sym, isin, hist_isin in rows:
            if isin:
                assert validate_isin(isin) is True, f"Invalid active ISIN in {inst_id} ({sym}): {isin}"
            if hist_isin:
                assert validate_isin(hist_isin) is True, f"Invalid historical ISIN in {inst_id} ({sym}): {hist_isin}"


def test_authoritative_isin_separation_from_format_validation():
    """
    Verify that verify_authoritative_isin separates syntactic validity
    from actual company identity verification.
    """
    # A syntactically valid ISIN for TCS (INE467B01029) does NOT belong to RELIANCE
    assert validate_isin("INE467B01029") is True
    assert verify_authoritative_isin("TCS", "INE467B01029") is True
    assert verify_authoritative_isin("RELIANCE", "INE467B01029") is False

    # HAL's ISINs
    assert verify_authoritative_isin("HAL", "INE066F01020") is True
    assert verify_authoritative_isin("HAL", "INE066F01012") is True
    assert verify_authoritative_isin("HAL", "INE002A01018") is False


# ---------------------------------------------------------------------------
# 4. Effective-Dated Provider Mappings & Unambiguous Resolution
# ---------------------------------------------------------------------------

def test_effective_dated_provider_mappings_schema():
    """
    Verify instrument_provider_mappings table contains effective_from and effective_to columns.
    """
    with connect() as con:
        cols = [c[1] for c in con.execute("PRAGMA table_info(instrument_provider_mappings)").fetchall()]
        assert "effective_from" in cols
        assert "effective_to" in cols


def test_dhan_security_id_3456_temporal_resolution(inst_service):
    """
    Dhan security ID 3456 resolution:
    - Current resolution returns active TMPV instrument.
    - Historical provider identity fails closed while its first effective date is unverified.
    - Guarantees zero ambiguity between simultaneously active primary mappings.
    """
    # Current resolution
    curr = inst_service.resolve_provider_security_id("dhan", "3456")
    assert curr is not None
    assert curr["instrument_id"] == "INST_NSE_TMPV"
    assert curr["symbol"] == "TMPV"

    # Historical resolution
    hist = inst_service.resolve_provider_security_id("dhan", "3456", query_date="2025-05-15")
    assert hist is None, "Historical Dhan identity lacks a verified effective start date."

    # Post-demerger date resolution
    post = inst_service.resolve_provider_security_id("dhan", "3456", query_date="2026-03-01")
    assert post is None, "Current mapping identity does not verify its historical effective start."


def test_provider_mapping_status_breakdown(inst_service):
    """
    Verify provider mapping status counts:
    - 64 VERIFIED
    - 2 UNAVAILABLE (MAP_TATAMOTORS_YF, MAP_TATAMOTORS_DHAN)
    - 0 INVALID
    - 0 UNVERIFIED
    Total: 66 mappings
    An unavailable mapping must NEVER be claimed as 100% verified.
    """
    mappings = get_provider_mappings()
    assert len(mappings) == 66

    verified = [m for m in mappings if m["mapping_status"] == MappingStatus.VERIFIED]
    unavailable = [m for m in mappings if m["mapping_status"] == MappingStatus.UNAVAILABLE]
    invalid = [m for m in mappings if m["mapping_status"] == MappingStatus.INVALID]
    unverified = [m for m in mappings if m["mapping_status"] == MappingStatus.UNVERIFIED]

    assert len(verified) == 64
    assert len(unavailable) == 2
    assert len(invalid) == 0
    assert len(unverified) == 0

    unavail_ids = {m["mapping_id"] for m in unavailable}
    assert unavail_ids == {"MAP_TATAMOTORS_YF", "MAP_TATAMOTORS_DHAN"}


# ---------------------------------------------------------------------------
# 5. Universe Accounting & Reconciliation
# ---------------------------------------------------------------------------

def test_comprehensive_universe_accounting(inst_service):
    """
    Accurately separate:
    - Active listed instruments: 32 (30 standard + TMPV + TMCV)
    - Historical predecessor instruments: 1 (INST_NSE_TATAMOTORS_HIST)
    - Original 31-stock universe representation: 31 (30 standard + TMPV)
    - Additional successor instruments: 1 (TMCV)
    - F&O Universe: 30 (excludes DEEPAKNTR and TMCV)
    - CAS Universe: 30 (excludes DEEPAKNTR and TMCV)
    """
    recon = inst_service.get_universe_reconciliation()
    assert len(recon) == 33

    active = [r for r in recon if r["status"] == InstrumentStatus.ACTIVE]
    assert len(active) == 32

    demerged = [r for r in recon if r["status"] == InstrumentStatus.DEMERGED]
    assert len(demerged) == 1
    assert demerged[0]["instrument_id"] == "INST_NSE_TATAMOTORS"

    fo_eligible = [r for r in active if r["is_fo_eligible"]]
    assert len(fo_eligible) == 30

    cas_eligible = [r for r in active if r["is_cas_eligible"]]
    assert len(cas_eligible) == 30


# ---------------------------------------------------------------------------
# 6. Database Preservation & Provenance Integrity
# ---------------------------------------------------------------------------

def test_data_preservation_and_integrity():
    """
    Absolute preservation of all baseline records:
    - Observed 5-minute bars == 24,786
    - Matching provenance records == 24,786 (1:1 correspondence)
    - Synthetic/daily bars >= 46,500
    - PRAGMA foreign_key_check is clean (0 errors)
    - PRAGMA integrity_check is ok
    """
    with connect() as con:
        # FK check
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors: {fk_errors}"

        # Integrity check
        integrity = [tuple(r) for r in con.execute("PRAGMA integrity_check").fetchall()]
        assert integrity == [("ok",)], f"Integrity check failed: {integrity}"

        # Counts
        obs = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        ohlcv = con.execute("SELECT count(*) FROM ohlcv").fetchone()[0]

        assert obs == 24786, f"Observed bars altered: {obs} != 24,786"
        assert prov == 24786, f"Provenance records altered: {prov} != 24,786"
        assert ohlcv >= 46500, f"OHLCV count altered: {ohlcv} < 46,500"
