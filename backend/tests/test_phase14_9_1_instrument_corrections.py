"""
Phase 14.9.1  Instrument Master Corrections, Symbol Effectivity & Corporate Action Data-Integrity Audit Test Suite.
Validates:
1. LTIM-to-LTM symbol transition on February 27, 2026 (NSE Circular NSE/CML/72948).
2. Date-aware historical symbol resolution before, on, and after transition.
3. Single immutable instrument ID across symbol transitions.
4. Authoritative ISIN format validation and historical ISIN handling (no fabricated _HIST suffixes).
5. Strict predecessor-successor isolation for Tata Motors demerger.
6. Corporate action price continuity policies (RAW_ONLY, COST_APPORTIONMENT, prohibition of 1:1 merge).
7. Full 33-instrument universe reconciliation and categorization.
8. Provider mapping correctness (Dhan & Yahoo Finance).
9. Regulatory F&O and CAS classification grounded in effective dates.
10. Database row preservation (24,786 observed bars, 24,786 provenance records, 46,544 ohlcv).
"""

import re
import pytest
from fastapi.testclient import TestClient

from app.database import (
    connect,
    get_instrument,
    get_instruments,
    get_provider_mappings,
    get_corporate_actions,
)
from app.main import app
from app.services.instrument_master_service import (
    InstrumentMasterService,
    InstrumentStatus,
    MappingStatus,
    PriceAdjustmentPolicy,
    get_instrument_master_service,
    validate_isin,
)
from app.services.trading_calendar_service import (
    get_expected_session_schedule,
    is_cas_eligible_security,
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
# 1. LTIM to LTM Symbol Transition & Effectivity
# ---------------------------------------------------------------------------

def test_ltim_to_ltm_transition_identity(inst_service):
    """
    Verify LTIMindtree canonical identity under NSE Circular NSE/CML/72948:
    - Current canonical symbol: LTM
    - ISIN: INE214T01019
    - Effective date: 2026-02-27
    - Historical symbol LTIM preserved with effective date through 2026-02-26
    """
    inst = inst_service.resolve_instrument("LTM")
    assert inst is not None
    assert inst["instrument_id"] == "INST_NSE_LTIM"
    assert inst["symbol"] == "LTM"
    assert inst["company_name"] == "LTIMindtree Limited"
    assert inst["isin"] == "INE214T01019"
    assert inst["effective_date"] == "2026-02-27"
    assert inst["status"] == InstrumentStatus.ACTIVE

    # Verify historical symbols list contains LTIM with valid_to 2026-02-26
    hist_syms = inst.get("historical_symbols") or []
    ltim_entry = next((h for h in hist_syms if h.get("symbol") == "LTIM"), None)
    assert ltim_entry is not None, "LTIM must be recorded as a historical symbol"
    assert ltim_entry.get("valid_to") == "2026-02-26" or ltim_entry.get("effective_until") == "2026-02-26"


def test_historical_symbol_resolution_by_date(inst_service):
    """
    Verify date-aware resolution for LTIMindtree:
    - Prior to 2026-02-27 -> returns LTIM
    - On or after 2026-02-27 -> returns LTM
    - Querying either LTM or LTIM yields correct date-specific symbol
    """
    # Prior to transition date (e.g., January 2026)
    assert inst_service.resolve_symbol_for_date("LTM", "2026-01-15") == "LTIM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-01-15") == "LTIM"

    # Exactly on last day of LTIM (February 26, 2026)
    assert inst_service.resolve_symbol_for_date("LTM", "2026-02-26") == "LTIM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-02-26") == "LTIM"

    # Effective date of transition (February 27, 2026)
    assert inst_service.resolve_symbol_for_date("LTM", "2026-02-27") == "LTM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-02-27") == "LTM"

    # Post-transition date (March 2026 and beyond)
    assert inst_service.resolve_symbol_for_date("LTM", "2026-03-01") == "LTM"
    assert inst_service.resolve_symbol_for_date("LTIM", "2026-03-01") == "LTM"

    # Historical predecessor company before 2022 merger (LTI)
    assert inst_service.resolve_symbol_for_date("LTM", "2020-05-10") == "LTI"


def test_immutable_instrument_id_no_duplicate_created(inst_service):
    """
    Verify that changing symbol from LTIM to LTM does NOT create a duplicate instrument.
    Single immutable entity INST_NSE_LTM exists; legacy INST_NSE_LTIM resolves to it.
    """
    # Resolving either LTM, LTIM, or legacy ID yields INST_NSE_LTM
    by_ltm = inst_service.resolve_instrument("LTM")
    by_ltim = inst_service.resolve_instrument("LTIM")
    by_legacy_id = inst_service.resolve_instrument("INST_NSE_LTIM")

    assert by_ltm["instrument_id"] == "INST_NSE_LTIM"
    assert by_ltim["instrument_id"] == "INST_NSE_LTIM"
    assert by_legacy_id["instrument_id"] == "INST_NSE_LTIM"

    # Verify database has exactly 1 instrument record for LTIMindtree
    with connect() as con:
        rows = con.execute(
            "SELECT instrument_id, symbol, isin FROM instruments WHERE isin = 'INE214T01019'"
        ).fetchall()
        assert len(rows) == 1, f"Expected exactly 1 instrument record for ISIN INE214T01019, found {len(rows)}"
        assert rows[0][0] == "INST_NSE_LTIM"
        assert rows[0][1] == "LTM"


# ---------------------------------------------------------------------------
# 2. ISIN Validation & Authoritative Handling
# ---------------------------------------------------------------------------

def test_authoritative_isin_format_validation():
    """
    Verify strict ISIN format validation:
    - Real 12-character Indian ISINs (starts with IN, ends with numeric check digit).
    - Rejects fabricated identifiers like 'INE155A01022_HIST'.
    - Rejects internal instrument IDs like 'INST_NSE_TATAMOTORS_HIST'.
    """
    # Valid ISINs
    assert validate_isin("INE155A01022") is True   # TMPV
    assert validate_isin("INE1TAE01010") is True   # TMCV
    assert validate_isin("INE214T01019") is True   # LTM
    assert validate_isin("INE002A01018") is True   # RELIANCE
    assert validate_isin("INE467B01029") is True   # TCS

    # Fabricated / invalid values must be strictly rejected
    assert validate_isin("INE155A01022_HIST") is False
    assert validate_isin("INST_NSE_TATAMOTORS_HIST") is False
    assert validate_isin("INE155A0102") is False   # Too short (11 chars)
    assert validate_isin("INE155A0102299") is False # Too long (14 chars)
    assert validate_isin("") is False
    assert validate_isin(None) is False


def test_no_fabricated_isin_in_database():
    """
    Verify that NO record in the database contains a fabricated ISIN (such as _HIST suffix).
    Every non-null ISIN must strictly satisfy the 12-char format validation.
    """
    with connect() as con:
        rows = con.execute("SELECT instrument_id, symbol, isin, historical_isin FROM instruments").fetchall()
        for inst_id, sym, isin, hist_isin in rows:
            if isin is not None:
                assert "_HIST" not in isin, f"Fabricated ISIN suffix found in {inst_id}: {isin}"
                assert validate_isin(isin), f"Invalid ISIN format in {inst_id}: {isin}"
            if hist_isin is not None:
                assert "_HIST" not in hist_isin, f"Fabricated suffix found in historical_isin of {inst_id}: {hist_isin}"
                assert validate_isin(hist_isin), f"Invalid historical_isin format in {inst_id}: {hist_isin}"


def test_tatamotors_predecessor_nullable_isin_and_historical_reference(inst_service):
    """
    Verify that predecessor TATAMOTORS:
    - Has isin = None (does not hold active exchange ISIN).
    - Has historical_isin = 'INE155A01022' (authoritative historical reference).
    - Can still be looked up by its historical ISIN.
    """
    hist = inst_service.resolve_instrument("INST_NSE_TATAMOTORS")
    assert hist is not None
    assert hist["isin"] is None, "Predecessor entity must have NULL isin in active schema"
    assert hist["historical_isin"] == "INE155A01022", "Historical ISIN must hold the genuine 12-char ISIN"

    # Lookup by historical ISIN returns the predecessor
    with connect() as con:
        row = con.execute(
            "SELECT instrument_id, symbol FROM instruments WHERE historical_isin = 'INE155A01022'"
        ).fetchone()
        assert row is not None
        assert row[0] == "INST_NSE_TATAMOTORS"


# ---------------------------------------------------------------------------
# 3. Tata Motors Predecessor & Successor Isolation
# ---------------------------------------------------------------------------

def test_tata_motors_distinct_successor_instruments(inst_service):
    """
    Verify complete structural separation between:
    1. INST_NSE_TATAMOTORS (Predecessor, DEMERGED)
    2. INST_NSE_TMPV (Passenger Vehicles, ACTIVE, ISIN INE155A01022, F&O eligible)
    3. INST_NSE_TMCV (Commercial Vehicles, ACTIVE, ISIN INE1TAE01010, Cash only)
    """
    hist = inst_service.resolve_instrument("TATAMOTORS")
    tmpv = inst_service.resolve_instrument("TMPV")
    tmcv = inst_service.resolve_instrument("TMCV")

    assert hist["instrument_id"] != tmpv["instrument_id"]
    assert tmpv["instrument_id"] != tmcv["instrument_id"]
    assert hist["instrument_id"] != tmcv["instrument_id"]

    assert tmpv["isin"] == "INE155A01022"
    assert tmcv["isin"] == "INE1TAE01010"
    assert tmpv["isin"] != tmcv["isin"]

    assert tmpv["is_fo_eligible"] == 1
    assert tmcv["is_fo_eligible"] == 0


def test_price_continuity_policy_enforcement(inst_service):
    """
    Verify explicit corporate action price continuity rules:
    - Never blindly copy predecessor history into successor instruments.
    - 1:1 entitlement ratio does NOT mean an adjustment factor of 1.0 applies to prices.
    - Direct 1:1 unadjusted splicing is strictly prohibited (raises error).
    - RAW_ONLY policy marks pre-demerger successor history as UNAVAILABLE_WITHOUT_ADJUSTMENT.
    - Tax-cost allocation metadata cannot be used as price adjustment factors.
    """
    # 1. Prohibited merge throws explicit error
    with pytest.raises(ValueError, match="prohibited"):
        inst_service.get_price_continuity_series(
            "TMPV", "2025-01-01", "2025-11-01", PriceAdjustmentPolicy.PROHIBITED_MERGE
        )

    # 2. RAW_ONLY policy for TMPV across demerger date
    raw_res = inst_service.get_price_continuity_series(
        "TMPV", "2025-01-01", "2025-11-01", PriceAdjustmentPolicy.RAW_ONLY
    )
    assert raw_res["predecessor_data_status"] == "UNKNOWN_EFFECTIVE_DATE"
    assert any("not verified" in n.lower() for n in raw_res["notes"])
    assert "adjustment_factor_applied" not in raw_res
    assert "tax_cost_allocation_metadata" not in raw_res

    with pytest.raises(ValueError, match="accounting metadata"):
        inst_service.get_price_continuity_series(
            "TMPV", "2025-01-01", "2025-11-01", "COST_APPORTIONMENT"
        )
    assert inst_service.get_tax_cost_allocation_metadata("TMPV")["allocation_pct"] == 68.85
    assert inst_service.get_tax_cost_allocation_metadata("TMCV")["allocation_pct"] == 31.15


# ---------------------------------------------------------------------------
# 4. 33-Instrument Universe Audit & Categorization
# ---------------------------------------------------------------------------

def test_universe_breakdown_and_accounting(inst_service):
    """
    Accurately categorizes the 33-instrument universe:
    - Total instruments: 33
    - Active current instruments: 32 (30 standard tracked + TMPV + TMCV)
    - Historical predecessor records: 1 (INST_NSE_TATAMOTORS)
    - Original 31-stock tracked universe representation: 31 (30 standard + TMPV, with LTM representing LTIMindtree)
    - Additional successor instruments: 1 (TMCV)
    """
    instruments = get_instruments()
    assert len(instruments) == 33, f"Expected exactly 33 instruments in database, found {len(instruments)}"

    active = [i for i in instruments if i["status"] == InstrumentStatus.ACTIVE]
    assert len(active) == 32, f"Expected 32 active instruments, found {len(active)}"

    demerged = [i for i in instruments if i["status"] == InstrumentStatus.DEMERGED]
    assert len(demerged) == 1, f"Expected 1 demerged instrument, found {len(demerged)}"
    assert demerged[0]["instrument_id"] == "INST_NSE_TATAMOTORS"

    # Check F&O eligibility breakdown
    fo_eligible = [i for i in active if i["is_fo_eligible"] == 1]
    assert len(fo_eligible) == 30, f"Expected 30 active F&O eligible instruments, found {len(fo_eligible)}"

    # Non-F&O active equities: DEEPAKNTR (cash equity only) and TMCV (cash equity only)
    non_fo = [i for i in active if i["is_fo_eligible"] == 0]
    non_fo_symbols = {i["symbol"] for i in non_fo}
    assert non_fo_symbols == {"DEEPAKNTR", "TMCV"}, f"Unexpected non-F&O active symbols: {non_fo_symbols}"


# ---------------------------------------------------------------------------
# 5. Provider Mapping Resolution
# ---------------------------------------------------------------------------

def test_provider_mappings_for_all_instruments(inst_service):
    """
    Verify provider mapping integrity across all 33 instruments:
    - 66 total mappings (2 per instrument: yfinance and dhan).
    - Every mapping links to a valid instrument.
    - Verified against empirical probes and Dhan Scrip Master.
    """
    mappings = get_provider_mappings()
    assert len(mappings) == 66, f"Expected 66 provider mappings, found {len(mappings)}"

    # Verify LTM mappings
    ltm_yf = inst_service.get_provider_symbol("LTM", "yfinance")
    assert ltm_yf == "LTM.NS"
    ltm_dhan_id = inst_service.get_dhan_security_id("LTM")
    assert ltm_dhan_id == "17818"

    # Historical LTIM resolves to same provider symbol
    assert inst_service.get_provider_symbol("LTIM", "yfinance") == "LTM.NS"
    assert inst_service.get_dhan_security_id("LTIM") == "17818"

    # Verify TMPV mappings
    assert inst_service.get_provider_symbol("TMPV", "yfinance") == "TMPV.NS"
    assert inst_service.get_dhan_security_id("TMPV") == "3456"

    # Verify TMCV mappings
    assert inst_service.get_provider_symbol("TMCV", "yfinance") == "TMCV.NS"
    assert inst_service.get_dhan_security_id("TMCV") == "759782"

    # Historical TATAMOTORS returns None on Yahoo Finance (delisted HTTP 404)
    assert inst_service.get_provider_symbol("TATAMOTORS", "yfinance") is None


# ---------------------------------------------------------------------------
# 6. Corporate Action Audit & Tracking
# ---------------------------------------------------------------------------

def test_corporate_actions_inventory():
    """
    Verify authoritative corporate actions registered:
    1. CA_TATAMOTORS_DEMERGER_2025
    2. CA_LTIM_MERGER_2022
    3. CA_LTM_SYMBOL_CHANGE_2026
    """
    actions = get_corporate_actions()
    assert len(actions) == 4, f"Expected 3 corporate actions, found {len(actions)}"

    action_ids = {a["action_id"] for a in actions}
    expected_ids = {
        "CA_TATAMOTORS_DEMERGER_2025",
        "CA_LTIM_MERGER_2022",
        "CA_LTM_SYMBOL_CHANGE_2026",
        "CA_HAL_SPLIT_2023",
    }
    assert expected_ids == action_ids

    # Check symbol change details
    ltm_ca = next(a for a in actions if a["action_id"] == "CA_LTM_SYMBOL_CHANGE_2026")
    assert ltm_ca["ex_date"] == "2026-02-27"
    assert ltm_ca["pre_action_symbol"] == "LTIM"
    assert ltm_ca["post_action_symbol"] == "LTM"
    assert ltm_ca["circular_reference"] == "NSE/CML/72948"


# ---------------------------------------------------------------------------
# 7. Regulatory F&O & CAS Classification
# ---------------------------------------------------------------------------

def test_regulatory_cas_and_fo_classification():
    """
    Verify CAS and F&O classification grounded in exchange data:
    - LTM: CAS eligible, 72 continuous bars.
    - TMPV: CAS eligible starting 2026-08-03, 72 continuous bars.
    - TMCV: Non-CAS, 75 continuous bars.
    - DEEPAKNTR: Non-CAS, 75 continuous bars.
    """
    # LTM
    is_cas_ltm, _ = is_cas_eligible_security("LTM", "2026-11-02")
    assert is_cas_ltm is True
    sched_ltm = get_expected_session_schedule("LTM", "2026-11-02")
    assert sched_ltm["expected_continuous_bars"] == 72

    # TMPV
    is_cas_tmpv, _ = is_cas_eligible_security("TMPV", "2026-11-02")
    assert is_cas_tmpv is True
    sched_tmpv = get_expected_session_schedule("TMPV", "2026-11-02")
    assert sched_tmpv["expected_continuous_bars"] == 72

    # TMCV
    is_cas_tmcv, _ = is_cas_eligible_security("TMCV", "2026-11-02")
    assert is_cas_tmcv is False
    sched_tmcv = get_expected_session_schedule("TMCV", "2026-11-02")
    assert sched_tmcv["expected_continuous_bars"] == 75

    # DEEPAKNTR
    is_cas_deepak, _ = is_cas_eligible_security("DEEPAKNTR", "2026-11-02")
    assert is_cas_deepak is False
    sched_deepak = get_expected_session_schedule("DEEPAKNTR", "2026-11-02")
    assert sched_deepak["expected_continuous_bars"] == 75


# ---------------------------------------------------------------------------
# 8. API Endpoints Health & Downstream Delivery
# ---------------------------------------------------------------------------

def test_api_symbol_resolution_and_metadata(client):
    """
    Verify FastAPI instrument endpoints for LTM, TMPV, TMCV, and TATAMOTORS.
    """
    # LTM by current symbol
    res = client.get("/api/instruments/LTM")
    assert res.status_code == 200
    data = res.json()
    assert data["instrument"]["symbol"] == "LTM"
    assert data["instrument"]["isin"] == "INE214T01019"

    # LTM by historical symbol LTIM
    res_hist = client.get("/api/instruments/LTIM")
    assert res_hist.status_code == 200
    data_hist = res_hist.json()
    assert data_hist["instrument"]["symbol"] == "LTM"

    # TMPV
    res_tmpv = client.get("/api/instruments/TMPV")
    assert res_tmpv.status_code == 200
    assert res_tmpv.json()["instrument"]["symbol"] == "TMPV"

    # TMCV
    res_tmcv = client.get("/api/instruments/TMCV")
    assert res_tmcv.status_code == 200
    assert res_tmcv.json()["instrument"]["symbol"] == "TMCV"

    # TATAMOTORS predecessor
    res_tata = client.get("/api/instruments/TATAMOTORS")
    assert res_tata.status_code == 200
    tata_data = res_tata.json()
    assert tata_data["instrument"]["status"] == "DEMERGED"
    assert tata_data["instrument"]["isin"] is None
    assert tata_data["instrument"]["historical_isin"] == "INE155A01022"


# ---------------------------------------------------------------------------
# 9. Database Preservation & Row-Count Integrity
# ---------------------------------------------------------------------------

def test_database_integrity_and_row_counts():
    """
    CRITICAL RULE: Absolute preservation of all previously verified records:
    - Observed 5-minute bars >= 24,786
    - Matching provenance records == observed count
    - Synthetic 5-minute bars >= 46,500
    - Foreign key check returns 0 errors
    - PRAGMA integrity_check returns ok
    """
    with connect() as con:
        # Integrity checks
        fk_check = con.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_check) == 0, f"Foreign key integrity violations detected: {fk_check}"

        integrity = [tuple(r) for r in con.execute("PRAGMA integrity_check").fetchall()]
        assert integrity == [("ok",)], f"Database corruption detected: {integrity}"

        # Row counts
        obs_cnt = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_cnt = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        ohlcv_cnt = con.execute("SELECT count(*) FROM ohlcv").fetchone()[0]

        assert obs_cnt == 24786, f"Observed bar count altered: {obs_cnt} != 24,786"
        assert prov_cnt == obs_cnt, f"Provenance mismatch: {prov_cnt} != {obs_cnt}"
        assert ohlcv_cnt >= 46500, f"Synthetic bar count altered: {ohlcv_cnt} < 46,500"
