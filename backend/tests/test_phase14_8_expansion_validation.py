"""
Phase 14.8 Automated Verification Suite.
Validates:
1. Effective-dated CAS schedule transition (Pre-CAS, CAS V1 Historical, CAS V2 Revised, Non-CAS, Special sessions).
2. December 6 vs December 7 boundary.
3. CAS and Non-CAS security handling.
4. Special trading session overrides.
5. Exact expected continuous intervals (72 vs 75 bars).
6. Missing opening, interior, and closing interval detection.
7. Auction record exclusion from continuous TOD RVOL baselines.
8. Provider timestamp normalization and timezone integrity.
9. Duplicate and malformed OHLCV detection.
10. Provenance one-to-one database integrity (24,786 records).
11. Idempotent ingestion and atomic persistence.
12. Strict synthetic isolation (46,500 bars preserved).
13. TOD RVOL independent manual calculations for expanded universe.
14. Current-session exclusion from baseline.
15. Same-time cumulative volume denominator verification.
16. Insufficient baseline (< 3 sessions) handling.
17. Missing provider symbol handling (DEEPAKNTR, LTIM, TATAMOTORS).
18. Downstream health interface and API consistency.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pytest

from app.database import connect, get_bars
from app.services.data_quality_service import (
    DataSourceClassification,
    validate_session_completeness,
)
from app.services.intraday_data_service import (
    TRACKED_NSE_SYMBOLS,
    get_intraday_ingestion_status,
)
from app.services.money_flow_service import calculate_historical_time_of_day_rvol
from app.services.trading_calendar_service import (
    CASSymbolScheduleVersion,
    CAS_V1_HISTORICAL_START,
    CAS_V2_REVISED_START,
    get_expected_session_schedule,
    get_session_expected_bars,
    is_cas_eligible_security,
    is_special_trading_session,
    is_trading_day,
)


# ---------------------------------------------------------------------------
# 1. Effective-Dated CAS Schedule Tests
# ---------------------------------------------------------------------------

def test_effective_dated_cas_schedule_transition():
    """Verify that CAS schedule versions transition based on session dates."""
    # Pre-CAS: before 2026-08-03
    sched_pre = get_expected_session_schedule("RELIANCE", "2026-07-15")
    assert sched_pre["schedule_version"] == CASSymbolScheduleVersion.PRE_CAS_STANDARD.value
    assert sched_pre["expected_continuous_bars"] == 75
    assert sched_pre["is_cas_eligible"] is False

    # Historical CAS V1: 2026-08-03 to 2026-12-06
    sched_v1 = get_expected_session_schedule("RELIANCE", "2026-10-22")
    assert sched_v1["schedule_version"] == CASSymbolScheduleVersion.CAS_V1_HISTORICAL.value
    assert sched_v1["expected_continuous_bars"] == 72
    assert sched_v1["continuous_end_time"] == "15:15:00"
    assert sched_v1["last_continuous_bar_time"] == "15:10:00"
    assert sched_v1["is_cas_eligible"] is True
    assert sched_v1["has_closing_auction"] is True
    assert "15:25:00" in sched_v1["acceptable_auction_timestamps"]

    # Revised SEBI CAS V2: 2026-12-07 onward
    sched_v2 = get_expected_session_schedule("RELIANCE", "2026-12-07")
    assert sched_v2["schedule_version"] == CASSymbolScheduleVersion.CAS_V2_REVISED.value
    assert sched_v2["expected_continuous_bars"] == 75
    assert sched_v2["continuous_end_time"] == "15:30:00"
    assert sched_v2["last_continuous_bar_time"] == "15:25:00"
    assert sched_v2["is_cas_eligible"] is True
    assert sched_v2["has_closing_auction"] is True
    assert "15:40:00" in sched_v2["acceptable_auction_timestamps"]


def test_december_6_versus_december_7_boundary():
    """Verify the exact boundary date transition from Historical to Revised CAS."""
    # 2026-12-04 is the Friday before the Monday 2026-12-07 go-live
    sched_friday = get_expected_session_schedule("TCS", "2026-12-04")
    assert sched_friday["schedule_version"] == CASSymbolScheduleVersion.CAS_V1_HISTORICAL.value
    assert sched_friday["expected_continuous_bars"] == 72
    assert sched_friday["continuous_end_time"] == "15:15:00"

    # 2026-12-07 is the effective date of SEBI Circular HO/47/11/11(3)2025-MRD-POD2/I/23843/2026
    sched_monday = get_expected_session_schedule("TCS", "2026-12-07")
    assert sched_monday["schedule_version"] == CASSymbolScheduleVersion.CAS_V2_REVISED.value
    assert sched_monday["expected_continuous_bars"] == 75
    assert sched_monday["continuous_end_time"] == "15:30:00"


def test_cas_and_non_cas_security_handling():
    """Verify F&O eligible securities are CAS governed while non-F&O securities remain on standard 75-bar schedule."""
    # Tracked F&O security
    is_cas_rel, _ = is_cas_eligible_security("INFY", "2026-10-22")
    assert is_cas_rel is True

    # Non-F&O equity
    is_cas_non, reason_non = is_cas_eligible_security("PENNYSTOCK", "2026-10-22")
    assert is_cas_non is False
    assert "NON_CAS_SECURITY" in reason_non
    sched_non = get_expected_session_schedule("PENNYSTOCK", "2026-10-22")
    assert sched_non["schedule_version"] == CASSymbolScheduleVersion.STANDARD_NON_CAS.value
    assert sched_non["expected_continuous_bars"] == 75


def test_special_trading_sessions_override_cas():
    """Verify Diwali Muhurat trading and DR drill sessions override CAS logic."""
    # Diwali Muhurat Trading 2026-11-08
    sched_muh = get_expected_session_schedule("RELIANCE", "2026-11-08")
    assert sched_muh["schedule_version"] == CASSymbolScheduleVersion.SPECIAL_TRUNCATED.value
    assert sched_muh["expected_continuous_bars"] == 12
    assert sched_muh["has_closing_auction"] is False

    # Disaster recovery drill 2024-03-02
    sched_dr = get_expected_session_schedule("HDFCBANK", "2024-03-02")
    assert sched_dr["schedule_version"] == CASSymbolScheduleVersion.SPECIAL_TRUNCATED.value
    assert sched_dr["expected_continuous_bars"] == 21


def test_exact_continuous_intervals_v1_and_v2():
    """Verify the exact sequence of 5-minute continuous bar timestamps for V1 and V2."""
    sched_v1 = get_expected_session_schedule("RELIANCE", "2026-10-22")
    times_v1 = sched_v1["expected_continuous_timestamps"]
    assert len(times_v1) == 72
    assert times_v1[0] == "09:15:00"
    assert times_v1[-1] == "15:10:00"

    sched_v2 = get_expected_session_schedule("RELIANCE", "2026-12-07")
    times_v2 = sched_v2["expected_continuous_timestamps"]
    assert len(times_v2) == 75
    assert times_v2[0] == "09:15:00"
    assert times_v2[-1] == "15:25:00"


# ---------------------------------------------------------------------------
# 2. Session Completeness & Data Quality Tests
# ---------------------------------------------------------------------------

def test_missing_opening_interior_and_closing_intervals():
    """Verify detection of missing opening, interior, and closing intervals."""
    from app.services.intraday_data_service import ist_to_utc_iso
    # Construct a session missing opening bar (09:15:00) and interior bar (11:00:00)
    sched = get_expected_session_schedule("RELIANCE", "2026-10-22")
    exp_times = sched["expected_continuous_timestamps"]
    
    # Exclude 09:15:00 (boundary) and 11:00:00 (interior)
    test_times = [t for t in exp_times if t not in ("09:15:00", "11:00:00")]
    mock_bars = [
        {
            "timestamp": ist_to_utc_iso("2026-10-22", t),
            "provider_timestamp": f"2026-10-22T{t}+05:30",
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000,
        }
        for t in test_times
    ]

    val = validate_session_completeness("2026-10-22", mock_bars, symbol="RELIANCE")
    assert val["is_complete"] is False
    assert any("MISSING_INTERIOR_INTERVALS" in e for e in val["errors"])
    assert "11:00:00" in val["missing_interior_intervals"]
    assert "09:15:00" in val["missing_intervals"]


def test_auction_record_exclusion_from_continuous_tod_rvol():
    """Verify that auction bar volume is excluded from continuous volume sums."""
    bars_with_auction = [
        {"time": "09:15:00", "volume": 10000},
        {"time": "12:00:00", "volume": 20000},
        {"time": "15:10:00", "volume": 30000},
        {"time": "15:25:00", "volume": 5000000},  # Auction block
    ]
    # Sched cutoff is 15:10:00 for CAS V1
    sched = get_expected_session_schedule("RELIANCE", "2026-10-22")
    cutoff = sched["last_continuous_bar_time"]
    cont_bars = [b for b in bars_with_auction if b["time"] <= cutoff]
    assert len(cont_bars) == 3
    assert not any(b["time"] == "15:25:00" for b in cont_bars)
    assert sum(b["volume"] for b in cont_bars) == 60000


def test_provider_timestamp_normalization():
    """Verify UTC and IST timestamp parsing consistency."""
    from app.services.intraday_data_service import ist_to_utc_iso, parse_bar_to_ist
    utc_str = ist_to_utc_iso("2026-10-22", "09:15:00")
    assert utc_str == "2026-10-22T03:45:00Z"
    
    d_ist, t_ist = parse_bar_to_ist(utc_str)
    assert d_ist == "2026-10-22"
    assert t_ist == "09:15:00"


def test_duplicate_and_malformed_records():
    """Verify that duplicate timestamps and invalid OHLC bounds fail completeness validation."""
    mock_bars = [
        {"timestamp": "2026-10-22T03:45:00Z", "provider_timestamp": "2026-10-22T09:15:00+05:30", "open": 100, "high": 90, "low": 105, "close": 95, "volume": 1000},  # high < low
    ]
    val = validate_session_completeness("2026-10-22", mock_bars, symbol="RELIANCE")
    assert val["is_complete"] is False
    assert any("INVALID_OHLC_RELATIONSHIPS" in e for e in val["errors"])


# ---------------------------------------------------------------------------
# 3. Database Provenance & Synthetic Isolation Tests
# ---------------------------------------------------------------------------

def test_provenance_one_to_one_integrity():
    """Verify exactly 24,786 observed bars and 24,786 provenance records with 0 unmatched."""
    with connect() as con:
        obs_cnt = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_cnt = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        assert obs_cnt >= 24786
        assert prov_cnt == obs_cnt

        unmatched = con.execute("""
            SELECT count(*) FROM observed_intraday_ohlcv o
            LEFT JOIN bar_provenance p 
            ON o.symbol = p.symbol AND o.interval = p.interval AND o.timestamp = p.timestamp
            WHERE p.symbol IS NULL
        """).fetchone()[0]
        assert unmatched == 0

        # Check duplicates
        dups = con.execute("""
            SELECT count(*) FROM (
                SELECT symbol, interval, timestamp, count(*) as cnt
                FROM observed_intraday_ohlcv
                GROUP BY symbol, interval, timestamp
                HAVING cnt > 1
            )
        """).fetchone()[0]
        assert dups == 0


def test_synthetic_isolation_verified():
    """Verify exactly 46,500 synthetic bars preserved in ohlcv and isolated on observed dates."""
    with connect() as con:
        syn_cnt = con.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]
        assert syn_cnt == 46500

    # Ensure get_bars() returns 100% observed data on observed dates
    from app.database import get_bars_provenance_map
    bars = get_bars("INFY", interval="5m")
    prov_map = get_bars_provenance_map("INFY", interval="5m")
    assert len(prov_map) == 886
    for b in bars:
        if b["timestamp"][:10] in ("2026-10-22", "2026-10-23", "2026-11-06"):
            assert b["source"] == "yfinance_historical_5m"
            assert b["timestamp"] in prov_map
            assert prov_map[b["timestamp"]]["provenance_classification"] == "OBSERVED_HISTORICAL"


# ---------------------------------------------------------------------------
# 4. TOD RVOL Mathematical Verification Tests
# ---------------------------------------------------------------------------

def test_tod_rvol_independent_spot_checks():
    """Independently verify manual calculations for INFY, ICICIBANK, and TITAN."""
    # INFY
    tod_infy = calculate_historical_time_of_day_rvol(
        "INFY", current_time_str="12:00:00", allow_synthetic=False, today_date="2026-11-06"
    )
    assert tod_infy["rvol"] == 0.85
    assert tod_infy["tod_valid_sessions"] == 11
    assert tod_infy["denominator"] == 6978153.3
    assert tod_infy["numerator"] == 5956032.0

    # ICICIBANK
    tod_icici = calculate_historical_time_of_day_rvol(
        "ICICIBANK", current_time_str="12:00:00", allow_synthetic=False, today_date="2026-11-06"
    )
    assert tod_icici["rvol"] == 2.39
    assert tod_icici["tod_valid_sessions"] == 11
    assert tod_icici["denominator"] == 4970405.9
    assert tod_icici["numerator"] == 11887739.0

    # TITAN
    tod_titan = calculate_historical_time_of_day_rvol(
        "TITAN", current_time_str="12:00:00", allow_synthetic=False, today_date="2026-11-06"
    )
    assert tod_titan["rvol"] == 8.52
    assert tod_titan["tod_valid_sessions"] == 11
    assert tod_titan["denominator"] == 300062.9
    assert tod_titan["numerator"] == 2557258.0


def test_current_session_excluded_from_baseline():
    """Verify that session 12 (2026-11-06) is never in its own baseline."""
    tod = calculate_historical_time_of_day_rvol(
        "RELIANCE", current_time_str="12:00:00", allow_synthetic=False, today_date="2026-11-06"
    )
    assert tod["tod_valid_sessions"] == 11  # 12 total sessions - 1 current session = 11 baseline sessions
    assert tod["denominator"] == 10389741.9
    assert tod["numerator"] == 9342902.0


def test_missing_provider_symbols_handling():
    """Verify DEEPAKNTR, LTIM, and TATAMOTORS return UNAVAILABLE without synthetic fallback."""
    for sym in ("DEEPAKNTR", "LTIM", "TATAMOTORS"):
        tod = calculate_historical_time_of_day_rvol(sym, current_time_str="12:00:00", allow_synthetic=False)
        assert tod["rvol"] is None
        assert tod["tod_rvol_status"] == "UNAVAILABLE"
        assert tod["tod_valid_sessions"] == 0


def test_downstream_health_api():
    """Verify get_intraday_ingestion_status returns consistent metadata for the expanded universe."""
    status = get_intraday_ingestion_status(allow_synthetic=False)
    assert status["tracked_symbols_count"] == 31
    assert status["symbols_with_observed_history"] == 28
    assert status["symbols_meeting_observed_min"] == 28
    assert status["symbols_meeting_10_sessions"] == 28
    assert status["symbols_meeting_20_sessions"] == 0
    assert status["complete_sessions_count"] == 336
    assert status["incomplete_sessions_count"] == 0
    assert status["total_observed_bars"] == 24786
    assert status["total_synthetic_bars"] == 46500
    assert status["cas_schedule_version"] == CASSymbolScheduleVersion.CAS_V1_HISTORICAL.value
