"""
Test Suite: Phase 14.6 — NSE Closing Auction Session (CAS) Aware Validation & Observed Intraday Pilot.

Verifies:
1. Exchange circular grounding: NSE/CMTR/72394, NSE/CMTR/73362, NSE/CMTR/74466.
2. Go-live date (2026-08-03) and F&O eligibility partitioning.
3. Schedule expectations: 72 continuous bars (09:15 to 15:10 IST) for CAS vs 75 bars for non-CAS.
4. Distinguishing continuous trading bars from closing auction transition & confirmation bars.
5. Interior gap detection vs boundary omissions.
6. Mathematical OHLC consistency and volume non-negativity.
7. Post-pilot observed bar inventory in observed_intraday_ohlcv and bar_provenance.
8. Preservation of 46,500 synthetic bars in ohlcv.
9. True Time-of-Day RVOL calculation using strict observed baseline (>= 3 sessions, current session excluded).
10. Strict isolation of synthetic data when unobserved stocks request TOD RVOL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import pytest

from app.database import (
    connect,
    get_bars,
    get_bar_provenance,
)
from app.services.data_quality_service import (
    DataSourceClassification,
    classify_session_provenance,
    validate_session_completeness,
    verify_bar_provenance,
)
from app.services.trading_calendar_service import (
    CAS_CIRCULAR_REFERENCES,
    CAS_CONTINUOUS_BARS_5M,
    CAS_EFFECTIVE_DATE,
    NSE_FO_SECURITIES,
    STANDARD_SESSION_BARS_5M,
    get_expected_session_schedule,
    get_session_expected_bars,
    is_cas_eligible_security,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
)


# ---------------------------------------------------------------------------
# Helpers for Synthetic/Mock Bar Generation
# ---------------------------------------------------------------------------

def _generate_mock_cas_bars(
    session_date: str = "2026-11-05",
    include_auction: bool = True,
    symbol: str = "RELIANCE",
) -> List[Dict[str, Any]]:
    """
    Generates a full continuous session of 72 five-minute bars (09:15:00 to 15:10:00 IST),
    optionally appending the 15:15:00 transition and 15:25:00 auction confirmation bars.
    """
    # 09:15 IST = 03:45 UTC
    start_utc = datetime.fromisoformat(f"{session_date}T03:45:00+00:00")
    bars: List[Dict[str, Any]] = []

    # 72 continuous bars (09:15 to 15:10 IST)
    for i in range(72):
        ts_dt = start_utc + timedelta(minutes=5 * i)
        ts_str = ts_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        bars.append({
            "symbol": symbol,
            "interval": "5m",
            "timestamp": ts_str,
            "provider_timestamp": (ts_dt + timedelta(hours=5, minutes=30)).isoformat(),
            "open": 1300.0 + i * 0.1,
            "high": 1305.0 + i * 0.1,
            "low": 1295.0 + i * 0.1,
            "close": 1302.0 + i * 0.1,
            "volume": 25000 + i * 100,
            "source": "yfinance_historical_5m",
            "provider": "yfinance",
            "ingestion_run_id": "test-cas-mock-run",
            "raw_response_hash": "mockhash123",
            "retrieval_timestamp": "2026-11-06T12:00:00Z",
        })

    if include_auction:
        # 15:15:00 IST transition bar (09:45:00 UTC)
        ts_1515 = start_utc + timedelta(minutes=5 * 72)
        bars.append({
            "symbol": symbol,
            "interval": "5m",
            "timestamp": ts_1515.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "provider_timestamp": (ts_1515 + timedelta(hours=5, minutes=30)).isoformat(),
            "open": 1307.2, "high": 1307.5, "low": 1307.0, "close": 1307.2,
            "volume": 1200,
            "source": "yfinance_historical_5m",
            "provider": "yfinance",
            "ingestion_run_id": "test-cas-mock-run",
            "raw_response_hash": "mockhash123",
            "retrieval_timestamp": "2026-11-06T12:00:00Z",
        })
        # 15:25:00 IST closing auction block trade confirmation (09:55:00 UTC)
        ts_1525 = start_utc + timedelta(minutes=5 * 74)
        bars.append({
            "symbol": symbol,
            "interval": "5m",
            "timestamp": ts_1525.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "provider_timestamp": (ts_1525 + timedelta(hours=5, minutes=30)).isoformat(),
            "open": 1308.0, "high": 1308.0, "low": 1308.0, "close": 1308.0,
            "volume": 2500000,
            "source": "yfinance_historical_5m",
            "provider": "yfinance",
            "ingestion_run_id": "test-cas-mock-run",
            "raw_response_hash": "mockhash123",
            "retrieval_timestamp": "2026-11-06T12:00:00Z",
        })

    return bars


# ---------------------------------------------------------------------------
# 1. Exchange Circular Grounding & Schedule Definition Tests
# ---------------------------------------------------------------------------

def test_cas_circular_grounding_and_constants():
    """Verify official NSE circular references and fundamental CAS constants."""
    assert CAS_EFFECTIVE_DATE == "2026-08-03"
    assert CAS_CONTINUOUS_BARS_5M == 72
    assert STANDARD_SESSION_BARS_5M == 75

    assert "FRAMEWORK" in CAS_CIRCULAR_REFERENCES
    assert CAS_CIRCULAR_REFERENCES["FRAMEWORK"] == "NSE/CMTR/72394"
    assert CAS_CIRCULAR_REFERENCES["OPERATIONAL_PARAMETERS"] == "NSE/CMTR/73362"
    assert CAS_CIRCULAR_REFERENCES["GO_LIVE"] == "NSE/CMTR/74466"


def test_cas_eligibility_by_symbol_and_date():
    """Verify CAS eligibility partitioning across securities and date boundaries."""
    # Post-go-live F&O stocks
    is_cas, reason = is_cas_eligible_security("RELIANCE", "2026-11-06")
    assert is_cas is True
    assert "CAS_ELIGIBLE" in reason
    assert "NSE/CMTR/74466" in reason

    is_cas, reason = is_cas_eligible_security("TCS.NS", "2026-08-03")
    assert is_cas is True

    is_cas, reason = is_cas_eligible_security("HDFCBANK", "2026-09-15")
    assert is_cas is True

    # Pre-go-live date: CAS must not apply prior to 2026-08-03
    is_cas, reason = is_cas_eligible_security("RELIANCE", "2026-08-02")
    assert is_cas is False
    assert "PRE_CAS_DATE" in reason

    is_cas, reason = is_cas_eligible_security("TCS", "2026-03-02")
    assert is_cas is False
    assert "PRE_CAS_DATE" in reason

    # Non-F&O cash equity: Standard 75-bar continuous schedule applies
    is_cas, reason = is_cas_eligible_security("NON_FO_EQUITY", "2026-11-06")
    assert is_cas is False
    assert "NON_CAS_SECURITY" in reason

    # None or empty symbol
    is_cas, reason = is_cas_eligible_security(None, "2026-11-06")
    assert is_cas is False


def test_get_expected_session_schedule_cas_regular():
    """Verify schedule resolution for post-Aug 3, 2026 CAS-eligible equity."""
    sched = get_expected_session_schedule("RELIANCE", "2026-11-05", "5m")
    assert sched["is_trading_day"] is True
    assert sched["is_cas_eligible"] is True
    assert sched["session_type"] == "REGULAR_CAS"
    assert sched["continuous_start_time"] == "09:15:00"
    assert sched["continuous_end_time"] == "15:15:00"
    assert sched["expected_continuous_bars"] == 72
    assert len(sched["expected_continuous_timestamps"]) == 72
    assert sched["expected_continuous_timestamps"][0] == "09:15:00"
    assert sched["expected_continuous_timestamps"][-1] == "15:10:00"
    assert sched["has_closing_auction"] is True
    assert sched["auction_start_time"] == "15:15:00"
    assert sched["auction_end_time"] == "15:35:00"
    assert "15:25:00" in sched["acceptable_auction_timestamps"]
    assert "NSE/CMTR/74466" in sched["circular_references"]


def test_get_expected_session_schedule_standard_non_cas():
    """Verify schedule resolution for standard non-CAS regular trading session."""
    sched = get_expected_session_schedule("NON_FO_STOCK", "2026-11-05", "5m")
    assert sched["is_trading_day"] is True
    assert sched["is_cas_eligible"] is False
    assert sched["session_type"] == "REGULAR_STANDARD"
    assert sched["continuous_start_time"] == "09:15:00"
    assert sched["continuous_end_time"] == "15:30:00"
    assert sched["expected_continuous_bars"] == 75
    assert len(sched["expected_continuous_timestamps"]) == 75
    assert sched["expected_continuous_timestamps"][0] == "09:15:00"
    assert sched["expected_continuous_timestamps"][-1] == "15:25:00"
    assert sched["has_closing_auction"] is False


def test_get_expected_session_schedule_special_sessions():
    """Verify special session schedules (Diwali Muhurat, DR drill, holidays)."""
    # Diwali Muhurat 2024
    muhurat = get_expected_session_schedule("RELIANCE", "2024-11-01", "5m")
    assert muhurat["is_trading_day"] is True
    assert muhurat["session_type"] == "MUHURAT"
    assert muhurat["expected_continuous_bars"] == 12

    # Weekend
    weekend = get_expected_session_schedule("RELIANCE", "2026-11-01", "5m")
    assert weekend["is_trading_day"] is False
    assert weekend["expected_continuous_bars"] == 0

    # Holiday
    holiday = get_expected_session_schedule("RELIANCE", "2026-01-26", "5m")
    assert holiday["is_trading_day"] is False


def test_get_session_expected_bars_cas_aware():
    """Verify get_session_expected_bars handles CAS vs non-CAS symbols."""
    # Post-CAS date with CAS symbol -> 72 bars
    assert get_session_expected_bars("2026-11-05", "5m", symbol="RELIANCE") == 72
    # Post-CAS date with non-CAS symbol -> 75 bars
    assert get_session_expected_bars("2026-11-05", "5m", symbol="NON_FO") == 75
    # Pre-CAS date -> 75 bars regardless of symbol
    assert get_session_expected_bars("2026-03-02", "5m", symbol="RELIANCE") == 75


# ---------------------------------------------------------------------------
# 2. Session Completeness Validator (CAS-Aware) Tests
# ---------------------------------------------------------------------------

def test_validate_session_completeness_cas_72_continuous_plus_auction():
    """Verify validation of 72 continuous bars + auction confirmation bar under CAS."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is True
    assert res["status"] == "SESSION_COMPLETE_AUCTION_INCLUDED"
    assert res["is_cas_eligible"] is True
    assert res["expected_continuous_bars"] == 72
    assert res["actual_continuous_bars"] == 72
    assert res["actual_bars"] == 74
    assert res["auction_bars_count"] == 2
    assert "15:25:00" in res["auction_timestamps"]
    assert len(res["missing_intervals"]) == 0
    assert len(res["errors"]) == 0


def test_validate_session_completeness_cas_72_continuous_without_auction():
    """Verify validation of 72 continuous bars without auction bar under CAS."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=False, symbol="RELIANCE")
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is True
    assert res["status"] == "SESSION_COMPLETE_CAS_NOT_INCLUDED"
    assert res["actual_continuous_bars"] == 72
    assert res["actual_bars"] == 72
    assert res["auction_bars_count"] == 0
    assert len(res["errors"]) == 0


def test_validate_session_completeness_cas_interior_gap():
    """Verify detection and rejection of interior missing intervals in continuous session."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    # Drop interval #25 (11:20:00 IST)
    dropped_bar = bars.pop(25)
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert "SESSION_INCOMPLETE_INTERIOR_GAP" in res["status"]
    assert len(res["missing_interior_intervals"]) == 1
    assert "11:20:00" in res["missing_interior_intervals"]
    assert any("MISSING_INTERIOR_INTERVALS" in e for e in res["errors"])


def test_validate_session_completeness_cas_boundary_gap():
    """Verify detection of boundary interval omission (e.g. missing market open 09:15 IST)."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    # Drop first bar (09:15:00 IST)
    bars.pop(0)
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert "SESSION_INCOMPLETE_BOUNDARY_GAP" in res["status"]
    assert "09:15:00" in res["missing_intervals"]


def test_validate_session_completeness_cas_duplicate_timestamps():
    """Verify detection of duplicate continuous timestamps."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    # Duplicate bar #10
    bars.append(bars[10].copy())
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert any("DUPLICATE_TIMESTAMPS" in e for e in res["errors"])


def test_validate_session_completeness_cas_misaligned_timestamps():
    """Verify rejection of timestamps not on 5-minute boundaries."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    # Set unaligned timestamp 09:17:00 IST
    bars[5]["timestamp"] = "2026-11-05T03:47:00Z"
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert any("MISALIGNED_INTERVALS" in e for e in res["errors"])


def test_validate_session_completeness_cas_invalid_ohlc():
    """Verify rejection of bars violating high >= low geometry."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    bars[15]["high"] = 1290.0
    bars[15]["low"] = 1310.0
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert res["status"] == "SESSION_INVALID"
    assert any("INVALID_OHLC_RELATIONSHIPS" in e for e in res["errors"])


def test_validate_session_completeness_cas_negative_volume():
    """Verify rejection of bars with negative volume."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    bars[20]["volume"] = -50
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert res["status"] == "SESSION_INVALID"
    assert any("NEGATIVE_OR_INVALID_VOLUME" in e for e in res["errors"])


def test_validate_session_completeness_cas_out_of_session():
    """Verify rejection of timestamps outside continuous trading and CAS window."""
    bars = _generate_mock_cas_bars("2026-11-05", include_auction=True, symbol="RELIANCE")
    # Add 09:05:00 IST bar (pre-market order collection)
    out_bar = bars[0].copy()
    out_bar["timestamp"] = "2026-11-05T03:35:00Z"  # 09:05 IST
    bars.insert(0, out_bar)
    res = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")

    assert res["is_complete"] is False
    assert any("OUT_OF_SESSION_TIMESTAMPS" in e for e in res["errors"])


# ---------------------------------------------------------------------------
# 3. Pilot Ingestion Database Verification Tests
# ---------------------------------------------------------------------------

def test_pilot_database_records_inspection():
    """Verify actual persisted database records for RELIANCE, TCS, and HDFCBANK."""
    with connect() as con:
        # 1. Total observed bars count
        obs_count = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_count = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        synth_count = con.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

        assert obs_count == 2658, f"Expected 2658 observed bars, got {obs_count}"
        assert prov_count == 2658, f"Expected 2658 provenance records, got {prov_count}"
        assert synth_count == 46500, f"Expected 46500 preserved synthetic bars, got {synth_count}"

        # 2. Individual symbol bar counts
        for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
            s_obs = con.execute(
                "SELECT count(*) FROM observed_intraday_ohlcv WHERE symbol = ?", (sym,)
            ).fetchone()[0]
            s_prov = con.execute(
                "SELECT count(*) FROM bar_provenance WHERE symbol = ?", (sym,)
            ).fetchone()[0]
            assert s_obs > 800, f"{sym} observed bars {s_obs} < 800"
            assert s_obs == s_prov, f"{sym} observed count {s_obs} != provenance {s_prov}"

        # 3. Verify provenance classification and data quality status
        invalid_prov = con.execute(
            "SELECT count(*) FROM bar_provenance "
            "WHERE provenance_classification != 'OBSERVED_HISTORICAL' "
            "OR data_quality_status != 'VERIFIED_OBSERVED_INTRADAY'"
        ).fetchone()[0]
        assert invalid_prov == 0, "Found non-observed records in bar_provenance"


def test_date_isolated_get_bars_no_synthetic_leakage():
    """Verify that get_bars prevents synthetic bar leakage into observed dates."""
    bars = get_bars("RELIANCE", interval="5m")
    # Find all bars on an observed date
    obs_date_bars = [b for b in bars if "2026-11-05" in b["timestamp"]]
    assert len(obs_date_bars) == 74, f"Expected 74 bars on 2026-11-05, got {len(obs_date_bars)}"

    # Confirm 100% of bars on that date are observed and none are synthetic
    for b in obs_date_bars:
        assert b["source"] == "yfinance_historical_5m"
        assert "calibrated" not in b["source"]
        assert "synthetic" not in b["source"]


# ---------------------------------------------------------------------------
# 4. True Time-of-Day RVOL Safeguard Tests
# ---------------------------------------------------------------------------

def test_tod_rvol_strict_observed_calculation():
    """Verify TOD RVOL calculation for pilot stocks using strictly observed data."""
    for sym in ["RELIANCE", "TCS", "HDFCBANK"]:
        res = calculate_historical_time_of_day_rvol(
            symbol=sym,
            today_cumulative_volume=500000.0,
            current_time_str="12:00:00",
            min_required_sessions=3,
            allow_synthetic=False,
        )
        assert res["rvol"] is not None
        assert res["rvol"] > 0
        assert res["tod_rvol_status"] == "OBSERVED_HISTORICAL"
        assert res["tod_source"] == "OBSERVED_HISTORICAL"
        assert res["tod_data_quality"] == "VERIFIED_OBSERVED_INTRADAY"
        assert res["tod_valid_sessions"] >= 3
        assert res["historical_avg_volume"] > 0
        assert "Historical Time-of-Day" in res["label"]


def test_tod_rvol_unobserved_stock_returns_unavailable():
    """Verify that uningested stock (e.g. INFY) returns UNAVAILABLE when allow_synthetic=False."""
    res = calculate_historical_time_of_day_rvol(
        symbol="INFY",
        today_cumulative_volume=500000.0,
        current_time_str="12:00:00",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_data_quality"] == "INSUFFICIENT_OBSERVED_DATA"
    assert res["tod_valid_sessions"] == 0
    assert "UNAVAILABLE" in res["label"]


def test_tod_rvol_continuous_volume_excludes_auction_blocks():
    """Verify that TOD RVOL calculation strictly excludes post-continuous auction blocks."""
    # When calculating at 15:10:00 (continuous close), volume should not include the 15:25 auction block
    res_cont = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=1000000.0,
        current_time_str="15:10:00",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    # When calculating at 15:30:00 (during auction window), historical volume should still only include continuous bars
    res_auc = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=1000000.0,
        current_time_str="15:30:00",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res_cont["historical_avg_volume"] is not None
    assert res_auc["historical_avg_volume"] is not None
    # Historical continuous volume must be identical because continuous trading ended at 15:15 (last bar 15:10)
    assert res_cont["historical_avg_volume"] == res_auc["historical_avg_volume"]
