"""
Comprehensive Test Suite for Phase 14.9 — NSE Instrument Master, Symbol Mapping & Corporate Action Reconciliation.
Verifies:
1. Authoritative instrument master persistence and schema constraints.
2. ISIN uniqueness across the universe.
3. Multi-tier provider mapping and status classification (VERIFIED, UNAVAILABLE).
4. Accurate historical ticker and alias resolution (TATAMOTORS, LTI, MINDTREE, LTM).
5. Post-demerger separation of TMPV and TMCV without synthetic price merging.
6. Non-CAS classification of DEEPAKNTR (75-bar continuous trading).
7. Rejection of invalid/ambiguous tickers.
8. API endpoints for universe reconciliation and instrument detail.
9. Absolute preservation of observed and synthetic bar inventories.
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.database import (
    connect,
    get_corporate_actions,
    get_instrument,
    get_instruments,
    get_provider_mappings,
)
from app.main import app
from app.services.instrument_master_service import (
    InstrumentMasterService,
    InstrumentStatus,
    MappingStatus,
    get_instrument_master_service,
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


def test_authoritative_instrument_master_seeded(inst_service):
    """Verify that all 33 tracked instruments are seeded with valid metadata."""
    instruments = get_instruments()
    assert len(instruments) >= 33, f"Expected at least 33 instruments, found {len(instruments)}"

    symbols = {i["symbol"] for i in instruments}
    required = {
        "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL",
        "LT", "MARUTI", "HINDUNILVR", "BAJFINANCE", "ASIANPAINT", "HCLTECH",
        "TITAN", "SUNPHARMA", "TRENT", "BEL", "ADANIENT", "COALINDIA", "ONGC",
        "POWERGRID", "HAL", "WIPRO", "DIXON", "POLYCAB", "CDSL", "KPITTECH",
        "TATAELXSI", "DEEPAKNTR", "LTM", "TMPV", "TMCV", "TATAMOTORS"
    }
    assert required.issubset(symbols), f"Missing required symbols: {required - symbols}"


def test_isin_uniqueness_across_universe(inst_service):
    """Verify that every active security has a globally unique, well-formed ISIN."""
    instruments = get_instruments(active_only=True)
    isins = [i["isin"] for i in instruments]
    assert len(isins) == len(set(isins)), "Duplicate ISIN detected in active instrument universe"

    for isin in isins:
        assert isin.startswith("INE"), f"Invalid Indian ISIN prefix: {isin}"
        assert len(isin) == 12, f"ISIN {isin} length is {len(isin)}, expected exactly 12 characters"


def test_primary_key_immutability(inst_service):
    """Verify that internal instrument_id acts as primary key and is distinct from symbol."""
    inst = inst_service.resolve_instrument("RELIANCE")
    assert inst is not None
    assert inst["instrument_id"] == "INST_NSE_RELIANCE"
    assert inst["exchange"] == "NSE"
    assert inst["security_type"] == "EQUITY"


def test_provider_symbol_resolution(inst_service):
    """Verify provider symbol resolution across standard and non-standard tickers."""
    # Standard: RELIANCE -> RELIANCE.NS
    assert inst_service.get_provider_symbol("RELIANCE", "yfinance") == "RELIANCE.NS"

    # Override: LTIM -> LTM.NS (overcoming Yahoo 404)
    assert inst_service.get_provider_symbol("LTIM", "yfinance") == "LTM.NS"

    # Override: DEEPAKNTR -> DEEPAKNTR.NS
    assert inst_service.get_provider_symbol("DEEPAKNTR", "yfinance") == "DEEPAKNTR.NS"

    # Demerged Passenger Vehicles: TMPV -> TMPV.NS
    assert inst_service.get_provider_symbol("TMPV", "yfinance") == "TMPV.NS"

    # Demerged Commercial Vehicles: TMCV -> TMCV.NS
    assert inst_service.get_provider_symbol("TMCV", "yfinance") == "TMCV.NS"


def test_historical_and_alias_symbol_resolution(inst_service):
    """Verify that historical tickers and aliases resolve correctly to canonical entities."""
    # Predecessor TATAMOTORS resolves to historical demerged entity
    tata_hist = inst_service.resolve_instrument("TATAMOTORS")
    assert tata_hist is not None
    assert tata_hist["instrument_id"] == "INST_NSE_TATAMOTORS"
    assert tata_hist["status"] == InstrumentStatus.DEMERGED

    # Merged LTI and MINDTREE resolve to LTM
    lti = inst_service.resolve_instrument("LTI")
    assert lti is not None
    assert lti["instrument_id"] == "INST_NSE_LTIM"

    mindtree = inst_service.resolve_instrument("MINDTREE")
    assert mindtree is not None
    assert mindtree["instrument_id"] == "INST_NSE_LTIM"

    # Provider ticker LTM resolves to LTM
    ltm = inst_service.resolve_instrument("LTM")
    assert ltm is not None
    assert ltm["instrument_id"] == "INST_NSE_LTIM"

    # Historical symbol LTIM resolves to LTM
    ltim = inst_service.resolve_instrument("LTIM")
    assert ltim is not None
    assert ltim["instrument_id"] == "INST_NSE_LTIM"


def test_delisted_or_unavailable_security_rejection(inst_service):
    """Verify that live provider query for delisted TATAMOTORS reports UNAVAILABLE without data fabrication."""
    # Provider symbol for historical TATAMOTORS must return None (or raise) because it is marked UNAVAILABLE
    prov_sym = inst_service.get_provider_symbol("TATAMOTORS", "yfinance")
    assert prov_sym is None, f"Expected None for UNAVAILABLE security TATAMOTORS, got {prov_sym}"


def test_invalid_and_unknown_symbol_rejection(inst_service):
    """Verify that non-existent or ambiguous tickers are cleanly rejected."""
    assert inst_service.resolve_instrument("INVALID_XYZ_TICKER") is None
    assert inst_service.resolve_instrument("") is None
    assert inst_service.get_provider_symbol("UNKNOWN_123") is None
    assert inst_service.get_dhan_security_id("UNKNOWN_123") is None


def test_dhan_security_id_mapping(inst_service):
    """Verify authoritative Dhan security IDs for order routing and scrip identification."""
    assert inst_service.get_dhan_security_id("RELIANCE") == "2885"
    assert inst_service.get_dhan_security_id("TCS") == "11536"
    assert inst_service.get_dhan_security_id("HDFCBANK") == "1333"
    assert inst_service.get_dhan_security_id("LTIM") == "17818"
    assert inst_service.get_dhan_security_id("TMPV") == "3456"
    assert inst_service.get_dhan_security_id("TMCV") == "759782"
    assert inst_service.get_dhan_security_id("DEEPAKNTR") == "19943"


def test_demerger_separation_tatamotors(inst_service):
    """
    CRITICAL RULE: Verify TMPV and TMCV remain strictly separate instruments with
    distinct ISINs, distinct Dhan IDs, distinct prices, and NO synthetic merging.
    """
    tmpv = inst_service.resolve_instrument("TMPV")
    tmcv = inst_service.resolve_instrument("TMCV")

    assert tmpv is not None
    assert tmcv is not None
    assert tmpv["instrument_id"] != tmcv["instrument_id"]
    assert tmpv["isin"] != tmcv["isin"]
    assert tmpv["isin"] == "INE155A01022"
    assert tmcv["isin"] == "INE1TAE01010"

    # F&O status separation
    assert tmpv["is_fo_eligible"] == 1
    assert tmcv["is_fo_eligible"] == 0

    # Dhan ID separation
    assert inst_service.get_dhan_security_id("TMPV") == "3456"
    assert inst_service.get_dhan_security_id("TMCV") == "759782"


def test_corporate_actions_mathematical_tracking(inst_service):
    """Verify that corporate action records preserve adjustment ratios and treatments."""
    actions = get_corporate_actions()
    assert len(actions) >= 3, f"Expected at least 3 corporate actions, found {len(actions)}"

    # Check Tata Motors demerger
    tata_action = next((a for a in actions if a["instrument_id"] == "INST_NSE_TATAMOTORS"), None)
    assert tata_action is not None
    assert tata_action["action_type"] == "DEMERGER"
    assert tata_action["ex_date"] == "2025-10-24"
    assert tata_action["ratio"] == "1:1"
    assert tata_action["resulting_instrument_id"] == "INST_NSE_TMCV"
    assert json.loads(tata_action["resulting_instrument_ids"]) == [
        "INST_NSE_TMPV", "INST_NSE_TMCV"
    ]
    assert tata_action["historical_adjustment_factor"] is None
    assert "SEPARATE_SERIES" in tata_action["adjustment_treatment"]

    # Check LTI merger
    lti_action = next((a for a in actions if a["instrument_id"] == "INST_NSE_LTIM" and a["action_type"] == "MERGER"), None)
    assert lti_action is not None
    assert lti_action["action_type"] == "MERGER"
    assert lti_action["ratio"] == "73:100"

    # Check LTM symbol change
    ltm_action = next((a for a in actions if a["action_id"] == "CA_LTM_SYMBOL_CHANGE_2026"), None)
    assert ltm_action is not None
    assert ltm_action["pre_action_symbol"] == "LTIM"
    assert ltm_action["post_action_symbol"] == "LTM"


def test_fo_and_cas_eligibility_classification():
    """
    Verify regulatory schedule classification:
    - DEEPAKNTR is cash equity only (non-F&O) -> standard 75 continuous bars.
    - RELIANCE, LTIM, TMPV are F&O equities -> CAS V1 72 continuous bars.
    """
    # DEEPAKNTR
    is_cas_deepak, _ = is_cas_eligible_security("DEEPAKNTR", "2026-11-02")
    assert not is_cas_deepak, "DEEPAKNTR must not be classified as CAS eligible"
    sched_deepak = get_expected_session_schedule("DEEPAKNTR", "2026-11-02")
    assert sched_deepak["expected_continuous_bars"] == 75

    # RELIANCE
    is_cas_rel, _ = is_cas_eligible_security("RELIANCE", "2026-11-02")
    assert is_cas_rel, "RELIANCE must be classified as CAS eligible"
    sched_rel = get_expected_session_schedule("RELIANCE", "2026-11-02")
    assert sched_rel["expected_continuous_bars"] == 72

    # LTIM
    is_cas_ltim, _ = is_cas_eligible_security("LTIM", "2026-11-02")
    assert is_cas_ltim, "LTIM must be classified as CAS eligible"
    sched_ltim = get_expected_session_schedule("LTIM", "2026-11-02")
    assert sched_ltim["expected_continuous_bars"] == 72

    # TMPV
    is_cas_tmpv, _ = is_cas_eligible_security("TMPV", "2026-11-02")
    assert is_cas_tmpv, "TMPV must be classified as CAS eligible"
    sched_tmpv = get_expected_session_schedule("TMPV", "2026-11-02")
    assert sched_tmpv["expected_continuous_bars"] == 72


def test_universe_reconciliation_table_integrity(inst_service):
    """Verify that get_universe_reconciliation() returns a complete, populated table."""
    table = inst_service.get_universe_reconciliation()
    assert len(table) >= 33, f"Expected 33 reconciliation rows, got {len(table)}"

    for row in table:
        assert row["instrument_id"].startswith("INST_NSE_")
        assert len(row["symbol"]) > 0
        assert len(row["company_name"]) > 0
        if row.get("status") == "ACTIVE":
            assert len(row["isin"]) == 12
        else:
            # Historical / demerged entity carries valid historical ISIN
            assert row.get("isin") is None or len(row.get("isin")) == 12
        assert row["yahoo_status"] in (MappingStatus.VERIFIED, MappingStatus.UNAVAILABLE, MappingStatus.UNVERIFIED)
        assert row["dhan_status"] in (MappingStatus.VERIFIED, MappingStatus.UNAVAILABLE, MappingStatus.UNVERIFIED)


def test_api_endpoints_health(client):
    """Verify that all FastAPI instrument endpoints respond with HTTP 200 and valid JSON."""
    # 1. List instruments
    res = client.get("/api/instruments")
    assert res.status_code == 200
    assert len(res.json()) >= 33

    # 2. Universe reconciliation table
    res_rec = client.get("/api/instruments/reconciliation")
    assert res_rec.status_code == 200
    assert len(res_rec.json()) >= 33

    # 3. Corporate actions
    res_ca = client.get("/api/instruments/corporate-actions")
    assert res_ca.status_code == 200
    assert len(res_ca.json()) >= 3

    # 4. Detail endpoint
    res_det = client.get("/api/instruments/LTIM")
    assert res_det.status_code == 200
    det = res_det.json()
    assert det["instrument"]["symbol"] == "LTM"
    assert det["instrument"]["instrument_id"] == "INST_NSE_LTIM"
    assert any(m["provider_symbol"] == "LTM.NS" for m in det["provider_mappings"])

    # 5. Non-existent symbol returns 404
    res_404 = client.get("/api/instruments/NONEXISTENT_XYZ")
    assert res_404.status_code == 404


def test_database_preservation_integrity():
    """
    CRITICAL RULE: Absolute preservation of all previously verified observed bars (>= 24,786),
    matching provenance records, and 46,500 synthetic bars.
    """
    with connect() as con:
        obs_count = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_count = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        syn_count = con.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

    assert obs_count >= 24786, f"Observed bars count regressed: {obs_count} < 24786"
    assert prov_count == obs_count, f"Provenance records ({prov_count}) do not match observed bars ({obs_count})"
    assert syn_count == 46500, f"Synthetic bars count mutated: {syn_count} != 46500"
