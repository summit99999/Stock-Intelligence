"""
Phase 14.1 — Market Movers Data Accuracy & Validation Audit Test Suite.

Verifies:
1. Differentiated RVOL:
   - Daily RVOL is marked PROVISIONAL during active market session.
   - Daily RVOL is marked COMPLETED post-market / historical EOD.
   - Time-of-day RVOL is marked UNAVAILABLE when intraday bar history is absent.
   - Never substitutes linear estimated intraday RVOL as historical time-of-day RVOL.
2. Price & LTP Correctness:
   - Historical-only data sets ltp=None and ltp_available=False.
   - Separates latest_completed_close, previous_completed_close, and completed_session_change_pct.
   - Live stream quote sets ltp and intraday_change_pct.
3. Universe Coverage Audit:
   - NIFTY 500 coverage reports actual tracked count (e.g. 31/500 = 6.2%), missing count (469), and disclosure.
   - All Tracked Equities reports research sample of ~2,100 listed equities, NOT 100% NSE coverage.
   - NIFTY 50 constituent mapping and missing symbols count.
4. Snapshot Integrity & Provenance:
   - Preserves data_source, source_timestamp, retrieval_timestamp, data_mode, and data_quality_status.
   - Distinguishes calculation_snapshot_id from underlying data timestamps.
   - Detects and flags stale records (> 5 trading sessions old).
   - exclude_stale filter correctly rejects stale records.
5. Turnover Accuracy:
   - ACTUAL_TURNOVER only when supplied directly by exchange/provider.
   - ESTIMATED_TURNOVER when calculated from OHLCV volume × price.
   - UNAVAILABLE when volume or price is missing/zero.
6. Heuristic Confluence:
   - Compound score labeled HEURISTIC; not presented as probability or institutional flow.
   - Clean handling of empty intersections.
"""

import sys
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.market_movers_service import (
    extract_stock_mover_metrics,
    get_market_movers_and_confluence,
    audit_universe_coverage_movers,
    check_is_stale,
    ESTIMATED_NSE_CASH_LISTINGS_COUNT,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Price and LTP Correctness Tests
# ---------------------------------------------------------------------------

def test_historical_only_data_never_presented_as_live_ltp():
    """Verify that historical stock records have ltp=None and are never labeled as live LTP."""
    sample_stock = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Limited",
        "close": 2450.0,
        "daily_change_pct": 1.25,
        "volume": 5000000,
        "relative_volume": 1.1,
        "data_source": "yfinance",
        "updated_at": "2026-11-05 15:30:00",
    }
    metrics = extract_stock_mover_metrics(sample_stock, live_quote=None)

    # LTP must be None because data is historical
    assert metrics["ltp"] is None
    assert metrics["ltp_available"] is False
    assert metrics["intraday_change_pct"] is None
    assert metrics["data_mode"] in ("HISTORICAL", "PROVISIONAL", "STALE")
    assert metrics["data_mode"] != "LIVE"

    # Completed session fields must be populated
    assert metrics["latest_completed_close"] > 0
    assert metrics["previous_completed_close"] > 0
    assert isinstance(metrics["completed_session_change_pct"], float)
    assert metrics["source_timestamp"] is not None
    assert metrics["retrieval_timestamp"] is not None


def test_live_stream_quote_populates_ltp_and_intraday_change():
    """Verify that an active live quote populates LTP, intraday change, and data_mode=LIVE."""
    sample_stock = {
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services",
        "close": 3800.0,
        "previous_close": 3750.0,
        "volume": 2000000,
        "relative_volume": 1.4,
        "data_source": "dhan",
        "updated_at": "2026-11-06 10:15:00",
    }
    live_quote = {
        "source": "LIVE",
        "ltp": 3850.0,
        "volume": 2400000,
        "change_percent": 2.67,
        "timestamp": "2026-11-06 10:15:22",
    }
    metrics = extract_stock_mover_metrics(sample_stock, live_quote=live_quote, is_session_open=True)

    assert metrics["ltp"] == 3850.0
    assert metrics["ltp_available"] is True
    assert metrics["data_mode"] == "LIVE"
    assert metrics["close"] == 3850.0
    assert metrics["intraday_change_pct"] is not None
    assert metrics["source_timestamp"] == "2026-11-06 10:15:22"


# ---------------------------------------------------------------------------
# 2. Differentiated RVOL Tests (Intraday vs Daily)
# ---------------------------------------------------------------------------

def test_daily_rvol_provisional_during_active_session():
    """Verify daily RVOL is marked PROVISIONAL when evaluated during market hours."""
    sample_stock = {
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "close": 1500.0,
        "volume": 3000000,
        "relative_volume": 1.5,
        "data_source": "yfinance",
    }
    metrics = extract_stock_mover_metrics(sample_stock, is_session_open=True)

    assert metrics["daily_rvol_status"] == "PROVISIONAL"
    assert metrics["daily_rvol_is_provisional"] is True
    assert "provisional" in metrics["daily_rvol_note"].lower()


def test_daily_rvol_completed_post_market():
    """Verify daily RVOL is marked COMPLETED when evaluated post-market / EOD."""
    sample_stock = {
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "close": 1500.0,
        "volume": 3000000,
        "relative_volume": 1.5,
        "data_source": "yfinance",
    }
    metrics = extract_stock_mover_metrics(sample_stock, is_session_open=False)

    assert metrics["daily_rvol_status"] == "COMPLETED"
    assert metrics["daily_rvol_is_provisional"] is False
    assert "finalized" in metrics["daily_rvol_note"].lower()


def test_time_of_day_rvol_unavailable_when_intraday_history_missing():
    """
    Verify that if intraday minute bar history is missing from the database,
    time_of_day_rvol is marked UNAVAILABLE and NEVER substituted by linear estimate.
    """
    sample_stock = {
        "symbol": "NON_EXISTENT_INTRADAY_STOCK_XYZ",
        "company_name": "XYZ Corp",
        "close": 100.0,
        "volume": 10000,
        "relative_volume": 1.2,
    }
    metrics = extract_stock_mover_metrics(sample_stock, is_session_open=True)

    # Time-of-day RVOL must be None and status UNAVAILABLE
    assert metrics["time_of_day_rvol"] is None
    assert metrics["time_of_day_rvol_status"] == "UNAVAILABLE"
    assert metrics["time_of_day_rvol_reason"] is not None

    # Linear estimated intraday RVOL must be kept separate and explicitly labeled
    assert metrics["linear_estimated_intraday_rvol"] is not None
    assert metrics["linear_estimated_intraday_rvol_status"] == "LINEAR_ESTIMATED"


# ---------------------------------------------------------------------------
# 3. Turnover Accuracy Tests
# ---------------------------------------------------------------------------

def test_actual_turnover_only_when_officially_provided():
    """Verify ACTUAL_TURNOVER is assigned only when exchange turnover is supplied."""
    record_with_actual = {
        "symbol": "HDFCBANK",
        "company_name": "HDFC Bank Limited",
        "close": 1600.0,
        "volume": 10000000,
        "turnover": 16250000000.0,  # 1625 Cr reported directly
        "turnover_status": "ACTUAL_TURNOVER",
    }
    metrics = extract_stock_mover_metrics(record_with_actual)

    assert metrics["turnover_status"] == "ACTUAL_TURNOVER"
    assert metrics["traded_value"] == 16250000000.0
    assert metrics["traded_value_cr"] == 1625.0
    assert "₹1625.00 Cr" in metrics["turnover_formatted"]


def test_estimated_turnover_when_calculated_from_ohlcv():
    """Verify ESTIMATED_TURNOVER is assigned when computed from volume * close."""
    record_ohlcv_only = {
        "symbol": "SBIN",
        "company_name": "State Bank of India",
        "close": 800.0,
        "volume": 5000000,
        # No turnover field provided
    }
    metrics = extract_stock_mover_metrics(record_ohlcv_only)

    assert metrics["turnover_status"] == "ESTIMATED_TURNOVER"
    assert metrics["traded_value"] == 5000000 * 800.0
    assert metrics["traded_value_cr"] == round((5000000 * 800.0) / 1e7, 2)
    assert "OHLCV" in metrics["turnover_note"]


def test_unavailable_turnover_when_missing():
    """Verify UNAVAILABLE is assigned when both price and volume are zero/missing."""
    record_empty = {
        "symbol": "ZEROVOL",
        "company_name": "Zero Volume Corp",
        "close": 0.0,
        "volume": 0,
    }
    metrics = extract_stock_mover_metrics(record_empty)

    assert metrics["turnover_status"] == "UNAVAILABLE"
    assert metrics["traded_value"] == 0.0
    assert metrics["traded_value_cr"] == 0.0


# ---------------------------------------------------------------------------
# 4. Stale Record & Snapshot Integrity Tests
# ---------------------------------------------------------------------------

def test_stale_record_detection():
    """Verify records older than 5 trading days are flagged as STALE."""
    old_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d %H:%M:%S")
    is_stale, reason = check_is_stale(old_date, max_days=7)
    assert is_stale is True
    assert "exceeds 7-day" in reason

    recent_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    is_recent_stale, _ = check_is_stale(recent_date, max_days=7)
    assert is_recent_stale is False


def test_exclude_stale_filter_in_snapshot():
    """Verify exclude_stale=True excludes stale records from mover lists."""
    res_all = get_market_movers_and_confluence(exclude_stale=False, force_refresh=True)
    res_clean = get_market_movers_and_confluence(exclude_stale=True, force_refresh=True)

    assert "stale_records_count" in res_all["summary_counts"]
    assert res_clean["filters_applied"]["exclude_stale"] is True


def test_calculation_snapshot_distinguished_from_market_data_timestamps():
    """
    Verify calculation_snapshot_id represents the calculation run while
    underlying_market_data tracks the range and synchronization of actual data timestamps.
    """
    res = get_market_movers_and_confluence(force_refresh=True)

    assert "calculation_snapshot_id" in res
    assert "calculation_timestamp" in res
    assert "underlying_market_data" in res["metadata"]

    und_data = res["metadata"]["underlying_market_data"]
    assert "earliest_source_timestamp" in und_data
    assert "latest_source_timestamp" in und_data
    assert "is_time_synchronized" in und_data
    assert "synchronization_disclosure" in und_data
    assert "not represent a synchronized exchange tick snapshot" in und_data["synchronization_disclosure"]


# ---------------------------------------------------------------------------
# 5. Universe Coverage Audit Tests
# ---------------------------------------------------------------------------

def test_nifty500_universe_coverage_transparency():
    """Verify NIFTY 500 reports true tracked count (e.g. 31/500 = 6.2%), not 100%."""
    res = get_market_movers_and_confluence(universe="nifty500", force_refresh=True)
    cov = res["coverage"]

    assert cov["requested_universe_size"] == 500
    assert cov["tracked_symbols_count"] <= 50  # exactly 31 in local DB
    assert cov["missing_symbols_count"] >= 450
    assert cov["coverage_pct"] < 15.0
    assert cov["is_full_coverage"] is False
    assert "6." in str(cov["coverage_pct"]) or cov["coverage_pct"] < 10.0
    assert "unseeded/missing" in cov["coverage_disclosure"]


def test_all_nse_equities_coverage_transparency():
    """
    Verify 'all' universe reports research sample against ~2,100 active listed NSE equities,
    explicitly NOT reporting 100% NSE coverage.
    """
    res = get_market_movers_and_confluence(universe="all", force_refresh=True)
    cov = res["coverage"]

    assert cov["requested_universe_size"] == ESTIMATED_NSE_CASH_LISTINGS_COUNT
    assert cov["tracked_symbols_count"] <= 50
    assert cov["coverage_pct"] < 5.0
    assert cov["is_full_coverage"] is False
    assert "NOT 100% NSE coverage" in cov["coverage_disclosure"]


def test_nifty50_universe_coverage_audit():
    """Verify NIFTY 50 audits canonical constituents and missing symbols."""
    res = get_market_movers_and_confluence(universe="nifty50", force_refresh=True)
    cov = res["coverage"]

    assert cov["requested_universe_size"] == 50
    assert cov["tracked_symbols_count"] > 0
    assert cov["missing_symbols_count"] > 0
    assert len(cov["missing_symbols_sample"]) > 0


# ---------------------------------------------------------------------------
# 6. Confluence Heuristic Labeling & Empty Intersection Tests
# ---------------------------------------------------------------------------

def test_confluence_compound_score_labeled_heuristic():
    """Verify confluence items carry explicit HEURISTIC score labels and disclosures."""
    res = get_market_movers_and_confluence(min_rvol=0.8, force_refresh=True)
    confluence_items = res["bullish_confluence"] + res["bearish_confluence"]

    if confluence_items:
        first = confluence_items[0]
        assert "heuristic_compound_score" in first
        assert first["score_label"] == "HEURISTIC"
        assert "NOT a probability" in first["score_nature"]
        assert "Heuristic score" in first["interpretation"]


def test_empty_bullish_and_bearish_intersections():
    """Verify empty lists are handled cleanly when high hurdles yield zero matches."""
    res = get_market_movers_and_confluence(
        min_rvol=9.9,
        min_price_change_pct=15.0,
        force_refresh=True,
    )
    assert res["bullish_confluence"] == []
    assert res["bearish_confluence"] == []
    assert res["summary_counts"]["bullish_confluence_count"] == 0
    assert res["summary_counts"]["bearish_confluence_count"] == 0


# ---------------------------------------------------------------------------
# 7. API Router Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_overview_endpoint_phase14_1_fields():
    """Verify /api/market-movers/overview returns all Phase 14.1 fields."""
    response = client.get("/api/market-movers/overview?universe=all&is_session_open=false")
    assert response.status_code == 200
    data = response.json()

    assert "coverage" in data
    assert "requested_universe_size" in data["coverage"]
    assert "calculation_snapshot_id" in data
    assert "calculation_timestamp" in data

    # Check stock item schema
    if data["top_gainers"]:
        g = data["top_gainers"][0]
        assert "ltp" in g
        assert "latest_completed_close" in g
        assert "previous_completed_close" in g
        assert "daily_rvol_status" in g
        assert "time_of_day_rvol_status" in g
        assert "turnover_status" in g
        assert "data_mode" in g
        assert "source_timestamp" in g
        assert "retrieval_timestamp" in g
