"""
Phase 14.7 — Independent CAS Validation, TOD RVOL Mathematical Audit & Downstream Integrity.

Covers all 18 mandatory test requirements:
1. Official CAS session timing (NSE circulars).
2. CAS eligibility by symbol and date.
3. Auction timestamp interpretation (flat O=H=L=C auction block confirmation).
4. Auction volume excluded from continuous TOD RVOL.
5. Correct cumulative-volume calculation at 12:00 IST.
6. Full-day ADV rejected as a TOD denominator.
7. Current session excluded from baseline.
8. Synthetic records excluded when allow_synthetic=False.
9. Incomplete sessions excluded (< 60 bars or missing continuous intervals).
10. Independently calculated reference values (RELIANCE: 10,389,741.9, TCS: 1,609,320.6, HDFCBANK: 14,495,838.3).
11. Three-session minimum enforcement.
12. Eleven-session baseline label accuracy.
13. Twenty-session baseline cap.
14. Missing and duplicate bars handling.
15. Date-level synthetic suppression in database.
16. API/frontend value consistency.
17. Observed provenance preservation (2,658 database records).
18. Downstream scanner and ranking integrity.
"""
from __future__ import annotations

import math
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
import pytest

from app.database import connect, get_bars
from app.services.trading_calendar_service import (
    CAS_EFFECTIVE_DATE,
    CAS_CONTINUOUS_BARS_5M,
    CAS_CIRCULAR_REFERENCES,
    NSE_FO_SECURITIES,
    is_cas_eligible_security,
    get_expected_session_schedule,
    get_session_expected_bars,
    is_trading_holiday,
    is_special_trading_session,
)
from app.services.data_quality_service import (
    validate_session_completeness,
    classify_session_provenance,
    DataSourceClassification,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
    calculate_linear_estimated_intraday_rvol,
)


# ===========================================================================
# 1. Official CAS Session Timing & Regulatory Circular Grounding
# ===========================================================================

def test_official_cas_session_timing():
    """Verify official CAS session timings under NSE circulars."""
    assert CAS_EFFECTIVE_DATE == "2026-08-03"
    assert CAS_CONTINUOUS_BARS_5M == 72
    assert CAS_CIRCULAR_REFERENCES["FRAMEWORK"] == "NSE/CMTR/72394"
    assert CAS_CIRCULAR_REFERENCES["OPERATIONAL_PARAMETERS"] == "NSE/CMTR/73362"
    assert CAS_CIRCULAR_REFERENCES["GO_LIVE"] == "NSE/CMTR/74466"

    # Verify schedule structure for CAS-eligible security
    sched = get_expected_session_schedule("RELIANCE", "2026-11-05", "5m")
    assert sched["is_trading_day"] is True
    assert sched["is_cas_eligible"] is True
    assert sched["session_type"] == "REGULAR_CAS_HISTORICAL"
    assert sched["continuous_start_time"] == "09:15:00"
    assert sched["continuous_end_time"] == "15:15:00"
    assert sched["expected_continuous_bars"] == 72
    assert sched["has_closing_auction"] is True
    assert sched["auction_start_time"] == "15:15:00"
    assert sched["auction_end_time"] == "15:35:00"
    assert "15:25:00" in sched["acceptable_auction_timestamps"]


# ===========================================================================
# 2. CAS Eligibility by Symbol and Date
# ===========================================================================

def test_cas_eligibility_by_symbol_and_date():
    """Verify CAS eligibility resolution across dates, F&O set, and non-F&O securities."""
    # Pre-CAS date (e.g. 2026-03-02) -> False regardless of symbol
    is_cas, reason = is_cas_eligible_security("RELIANCE", "2026-03-02")
    assert is_cas is False
    assert "PRE_CAS_DATE" in reason

    # Post-CAS date with F&O security -> True
    is_cas, reason = is_cas_eligible_security("RELIANCE", "2026-08-03")
    assert is_cas is True
    assert "CAS_ELIGIBLE" in reason

    is_cas, reason = is_cas_eligible_security("TCS", "2026-11-05")
    assert is_cas is True
    assert "CAS_ELIGIBLE" in reason

    is_cas, reason = is_cas_eligible_security("HDFCBANK", "2026-11-05")
    assert is_cas is True
    assert "CAS_ELIGIBLE" in reason

    # Post-CAS date with non-F&O security -> False
    is_cas, reason = is_cas_eligible_security("NON_FO_STOCK", "2026-11-05")
    assert is_cas is False
    assert "NON_CAS_SECURITY" in reason

    # No symbol provided -> False
    is_cas, reason = is_cas_eligible_security(None, "2026-11-05")
    assert is_cas is False
    assert "NO_SYMBOL_PROVIDED" in reason


# ===========================================================================
# 3. Auction Timestamp Interpretation
# ===========================================================================

def test_auction_timestamp_interpretation():
    """Verify every persisted 15:25:00 bar is an auction execution block."""
    with connect() as con:
        # Check all 15:25:00 bars in observed_intraday_ohlcv
        rows = con.execute("""
            SELECT symbol, timestamp, open, high, low, close, volume
            FROM observed_intraday_ohlcv
            WHERE substr(timestamp, 12, 8) = '09:55:00' -- 15:25 IST is 09:55 UTC
        """).fetchall()

        assert rows, "Expected observed closing-auction bars in the database."
        for r in rows:
            # Equilibrium auction execution: Open == High == Low == Close
            assert r["open"] == r["high"] == r["low"] == r["close"], (
                f"Auction bar on {r['timestamp']} is not a single equilibrium price: "
                f"O={r['open']}, H={r['high']}, L={r['low']}, C={r['close']}"
            )
            # Volume must be positive auction trade confirmation volume
            assert r["volume"] > 0, f"Auction bar on {r['timestamp']} has zero volume"


# ===========================================================================
# 4. Auction Volume Excluded from Continuous TOD RVOL
# ===========================================================================

def test_auction_volume_excluded_from_continuous_tod_rvol():
    """Verify that TOD RVOL calculation strictly excludes 15:15 and 15:25 auction blocks."""
    # When calculating TOD RVOL at 15:10:00 (end of continuous trading),
    # auction bars should NOT be included in cumulative volume baseline
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=1_000_000.0,
        current_time_str="15:10:00",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["tod_rvol_status"] == "OBSERVED_HISTORICAL"
    # Continuous baseline volume at 15:10 must be strictly less than full session volume
    # Full session mean volume is ~22.6M, while continuous-only at 15:10 is ~20.5M
    assert res["historical_avg_volume"] < 21_000_000.0
    assert res["historical_avg_volume"] > 18_000_000.0


# ===========================================================================
# 5. Correct Cumulative Volume Calculation at 12:00 IST
# ===========================================================================

def test_correct_cumulative_volume_calculation_at_1200():
    """Verify exact cumulative volume calculation at 12:00 IST using controlled in-memory data."""
    # Build 3 synthetic sessions where 12:00 volume is exactly known
    # 09:15 to 12:00:00 = 34 bars. Let each bar have volume = 1,000.
    # Total volume up to 12:00:00 = 34 * 1,000 = 34,000 per session.
    # Total session bars = 72 bars (volume = 72,000 per session).
    test_bars = []
    # Use non-holiday trading dates
    dates = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]

    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        for i in range(72):
            bar_time = datetime(dt.year, dt.month, dt.day, 9, 15) + timedelta(minutes=5 * i)
            utc_time = bar_time - timedelta(hours=5, minutes=30)
            test_bars.append({
                "symbol": "MOCK_FO",
                "timestamp": utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
                "source": "yfinance_historical_5m",
            })

    # Call calculate_historical_time_of_day_rvol with today_date="2026-10-29"
    res = calculate_historical_time_of_day_rvol(
        symbol="MOCK_FO",
        today_cumulative_volume=68000.0,  # 2x the 34,000 baseline
        current_time_str="12:00:00",
        intraday_history_bars=test_bars,
        today_date="2026-10-29",
        min_required_sessions=3,
        allow_synthetic=False,
    )

    assert res["tod_rvol_status"] == "OBSERVED_HISTORICAL"
    assert res["tod_valid_sessions"] == 3
    # Denominator must be exactly 34,000 (34 bars * 1000)
    assert res["historical_avg_volume"] == 34000.0
    # RVOL must be exactly 68000 / 34000 = 2.0
    assert res["rvol"] == 2.0


# ===========================================================================
# 6. Full-Day ADV Rejected as TOD Denominator
# ===========================================================================

def test_full_day_adv_rejected_as_tod_denominator():
    """Verify that TOD RVOL denominator is strictly cumulative volume through T, NOT full-day ADV."""
    # For RELIANCE in database:
    # Full day mean volume = ~22.69M
    # 12:00 midday cumulative mean volume = 10,389,741.9
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=10_389_741.9,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["historical_avg_volume"] == 10_389_741.9
    # If denominator were full day (~22.69M), RVOL would be ~0.46
    # With correct midday denominator (10.389M), RVOL is exactly 1.00
    assert res["rvol"] == 1.0


# ===========================================================================
# 7. Current Session Excluded from Baseline
# ===========================================================================

def test_current_session_excluded_from_baseline():
    """Verify that the current session date is never included in the historical baseline."""
    # When today_date is specified as 2026-11-06, exactly 11 sessions remain
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=500_000.0,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["tod_valid_sessions"] == 11
    assert "11 sessions avg" in res["label"]


# ===========================================================================
# 8. Synthetic Records Excluded without allow_synthetic
# ===========================================================================

def test_synthetic_records_excluded_without_allow_synthetic():
    """Verify synthetic sessions are rejected when allow_synthetic=False."""
    # TATAMOTORS has synthetic history but no observed 5m sessions in this fixture.
    res = calculate_historical_time_of_day_rvol(
        symbol="TATAMOTORS",
        today_cumulative_volume=500_000.0,
        current_time_str="12:00:00",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_data_quality"] == "INSUFFICIENT_OBSERVED_DATA"
    assert "0 observed found" in res["reason"]


# ===========================================================================
# 9. Incomplete Sessions Excluded
# ===========================================================================

def test_incomplete_sessions_excluded():
    """Verify incomplete sessions (< 60 bars or interior gaps) are excluded from baseline."""
    # Create 3 complete sessions and 1 truncated session (30 bars)
    test_bars = []
    dates = ["2026-10-26", "2026-10-27", "2026-10-28", "2026-10-29"]

    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        # For 2026-10-28, create only 30 bars (severely truncated)
        n_bars = 30 if d == "2026-10-28" else 72
        for i in range(n_bars):
            bar_time = datetime(dt.year, dt.month, dt.day, 9, 15) + timedelta(minutes=5 * i)
            utc_time = bar_time - timedelta(hours=5, minutes=30)
            test_bars.append({
                "symbol": "MOCK_FO",
                "timestamp": utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
                "source": "yfinance_historical_5m",
            })

    res = calculate_historical_time_of_day_rvol(
        symbol="MOCK_FO",
        today_cumulative_volume=34000.0,
        current_time_str="12:00:00",
        intraday_history_bars=test_bars,
        today_date="2026-10-29",
        min_bars_per_session=60,
        min_required_sessions=2,
        allow_synthetic=False,
    )

    # 2026-10-28 must be excluded for having only 30 bars (< 60)
    # Remaining baseline: exactly 2 sessions (2026-10-26 and 2026-10-27)
    assert res["tod_valid_sessions"] == 2


# ===========================================================================
# 10. Independently Calculated Reference Values (Exact Database Proof)
# ===========================================================================

def test_independently_calculated_reference_values_database():
    """Verify exact mathematical baseline values against independent reference calculations."""
    # 1. RELIANCE: 11 baseline sessions sum = 114,287,161.0, mean = 10,389,741.9
    rel_res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=10_389_741.9,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert rel_res["historical_avg_volume"] == 10_389_741.9
    assert rel_res["rvol"] == 1.0

    # 2. TCS: 11 baseline sessions sum = 17,702,527.0, mean = 1,609,320.6
    tcs_res = calculate_historical_time_of_day_rvol(
        symbol="TCS",
        today_cumulative_volume=1_609_320.6,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert tcs_res["historical_avg_volume"] == 1_609_320.6
    assert tcs_res["rvol"] == 1.0

    # 3. HDFCBANK: 11 baseline sessions sum = 159,454,221.0, mean = 14,495,838.3
    hdfc_res = calculate_historical_time_of_day_rvol(
        symbol="HDFCBANK",
        today_cumulative_volume=14_495_838.3,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert hdfc_res["historical_avg_volume"] == 14_495_838.3
    assert hdfc_res["rvol"] == 1.0


# ===========================================================================
# 11. Three-Session Minimum Enforcement
# ===========================================================================

def test_three_session_minimum_enforcement():
    """Verify that fewer than 3 observed sessions returns UNAVAILABLE."""
    test_bars = []
    # Only 2 baseline sessions + today
    dates = ["2026-10-26", "2026-10-27", "2026-10-28"]
    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        for i in range(72):
            bar_time = datetime(dt.year, dt.month, dt.day, 9, 15) + timedelta(minutes=5 * i)
            utc_time = bar_time - timedelta(hours=5, minutes=30)
            test_bars.append({
                "symbol": "MOCK_FO",
                "timestamp": utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
                "source": "yfinance_historical_5m",
            })

    res = calculate_historical_time_of_day_rvol(
        symbol="MOCK_FO",
        today_cumulative_volume=34000.0,
        current_time_str="12:00:00",
        intraday_history_bars=test_bars,
        today_date="2026-10-28",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert "2 observed found, min 3 required" in res["reason"]


# ===========================================================================
# 12. Eleven-Session Baseline Label Accuracy
# ===========================================================================

def test_eleven_session_baseline_label():
    """Verify that the baseline label accurately reports 11 sessions, NOT 20."""
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=500_000.0,
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["label"] == "Historical Time-of-Day (11 sessions avg at 12:00 IST)"
    assert res["tod_valid_sessions"] == 11


# ===========================================================================
# 13. Twenty-Session Baseline Cap
# ===========================================================================

def test_twenty_session_baseline_cap():
    """Verify that when > 20 sessions exist, the baseline is capped at 20 most recent sessions."""
    test_bars = []
    # Create 25 sessions
    base_date = date(2026, 9, 1)
    dates = []
    cur = base_date
    while len(dates) < 26:
        if cur.weekday() < 5:
            dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)

    for d in dates:
        dt = datetime.strptime(d, "%Y-%m-%d")
        for i in range(72):
            bar_time = datetime(dt.year, dt.month, dt.day, 9, 15) + timedelta(minutes=5 * i)
            utc_time = bar_time - timedelta(hours=5, minutes=30)
            test_bars.append({
                "symbol": "MOCK_FO",
                "timestamp": utc_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1000,
                "source": "yfinance_historical_5m",
            })

    res = calculate_historical_time_of_day_rvol(
        symbol="MOCK_FO",
        today_cumulative_volume=34000.0,
        current_time_str="12:00:00",
        intraday_history_bars=test_bars,
        today_date=dates[-1],
        lookback_sessions=20,
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert res["tod_valid_sessions"] == 20
    assert "20 sessions avg" in res["label"]


# ===========================================================================
# 14. Missing and Duplicate Bars Handling
# ===========================================================================

def test_missing_and_duplicate_bars_handling():
    """Verify duplicate bars are detected and missing interior intervals are rejected."""
    # 1. Duplicate continuous bar
    bars = []
    dt = datetime(2026, 11, 5, 9, 15)
    for i in range(72):
        bt = dt + timedelta(minutes=5 * i)
        utc_bt = bt - timedelta(hours=5, minutes=30)
        bars.append({
            "timestamp": utc_bt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000,
            "source": "yfinance_historical_5m",
        })
    # Add duplicate of bar 0
    bars.append(bars[0].copy())
    val = validate_session_completeness("2026-11-05", bars, "5m", symbol="RELIANCE")
    assert val["is_complete"] is False
    assert any("DUPLICATE_TIMESTAMPS" in e for e in val["errors"])

    # 2. Missing interior interval (remove bar at 11:00)
    bars_clean = bars[:-1]  # remove duplicate
    bars_gap = [b for b in bars_clean if "05:30:00Z" not in b["timestamp"]]  # 11:00 IST is 05:30 UTC
    val_gap = validate_session_completeness("2026-11-05", bars_gap, "5m", symbol="RELIANCE")
    assert val_gap["is_complete"] is False
    assert "SESSION_INCOMPLETE_INTERIOR_GAP" in val_gap["status"]


# ===========================================================================
# 15. Date-Level Synthetic Suppression in Database
# ===========================================================================

def test_date_level_synthetic_suppression_in_database():
    """Verify that get_bars suppresses all synthetic bars on dates where observed bars exist."""
    bars = get_bars("RELIANCE", interval="5m")
    # Date 2026-11-05 has observed bars
    obs_date_bars = [b for b in bars if "2026-11-05" in b["timestamp"]]
    assert len(obs_date_bars) == 74
    for b in obs_date_bars:
        assert b["source"] == "yfinance_historical_5m"
        assert "calibrated" not in b["source"]
        assert "synthetic" not in b["source"]


# ===========================================================================
# 16. API/Frontend Value Consistency
# ===========================================================================

def test_api_tod_rvol_response_consistency():
    """Verify that calculate_historical_time_of_day_rvol returns consistent API shape."""
    res = calculate_historical_time_of_day_rvol(
        symbol="RELIANCE",
        today_cumulative_volume=0.0,  # auto-derived from database bars
        current_time_str="12:00:00",
        today_date="2026-11-06",
        min_required_sessions=3,
        allow_synthetic=False,
    )
    assert "rvol" in res
    assert "time_of_day_rvol" in res
    assert "method" in res
    assert "status" in res
    assert "tod_rvol_status" in res
    assert "tod_source" in res
    assert "tod_data_quality" in res
    assert "historical_avg_volume" in res
    assert "numerator" in res
    assert "denominator" in res
    assert "today_cumulative_volume" in res
    assert "tod_valid_sessions" in res
    assert "label" in res
    assert res["numerator"] > 0
    assert res["denominator"] == 10_389_741.9
    assert res["rvol"] == round(res["numerator"] / res["denominator"], 2)


# ===========================================================================
# 17. Observed Provenance Preservation
# ===========================================================================

def test_observed_provenance_preservation():
    """Verify database record preservation and one-to-one observed provenance."""
    with connect() as con:
        obs_count = con.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
        prov_count = con.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
        synth_count = con.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

        assert obs_count > 0
        assert prov_count == obs_count
        assert synth_count == 46500

        # Verify zero unverified records in bar_provenance
        unverified = con.execute("""
            SELECT count(*) FROM bar_provenance
            WHERE provenance_classification != 'OBSERVED_HISTORICAL'
               OR data_quality_status != 'VERIFIED_OBSERVED_INTRADAY'
               OR raw_response_hash IS NULL
        """).fetchone()[0]
        assert unverified == 0


# ===========================================================================
# 18. Downstream Scanner and Ranking Integrity
# ===========================================================================

def test_downstream_scanner_and_ranking_integrity():
    """Verify downstream services maintain observed vs synthetic status distinction."""
    from app.services.market_movers_service import extract_stock_mover_metrics

    # Test extract_stock_mover_metrics for RELIANCE
    stock_record = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Ltd",
        "sector": "Energy",
        "close": 1320.0,
        "volume": 21608127,
    }
    mover = extract_stock_mover_metrics(stock_record, allow_synthetic=False)

    assert mover["symbol"] == "RELIANCE"
    assert mover["tod_rvol_status"] == "OBSERVED_HISTORICAL"
    assert mover["tod_source"] == "OBSERVED_HISTORICAL"
    assert mover["tod_data_quality"] == "VERIFIED_OBSERVED_INTRADAY"
    assert mover["tod_valid_sessions"] >= 3

    # Test uningested stock maintains UNAVAILABLE status
    unobserved_record = {
        "symbol": "TATAMOTORS",
        "company_name": "Infosys Ltd",
        "sector": "Technology",
        "close": 1850.0,
        "volume": 5000000,
    }
    unobserved_mover = extract_stock_mover_metrics(unobserved_record, allow_synthetic=False)
    assert unobserved_mover["tod_rvol_status"] == "UNAVAILABLE"
    assert unobserved_mover["tod_data_quality"] == "INSUFFICIENT_OBSERVED_DATA"
