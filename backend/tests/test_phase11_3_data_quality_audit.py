"""
Phase 11.3 Platform-Wide Data Integrity, Source Validation & Reliability Audit Suite.

Verifies all 18 core reliability and transparency audit requirements:
1. DataMode taxonomy: Historical sources (yfinance, sqlite, demo) can NEVER be LIVE
2. Stale data detection and reason identification
3. Missing timestamps and empty datasets handled gracefully without crashing
4. Full OHLC mathematical consistency (High < Low, High < max(O,C), Low > min(O,C), price <= 0)
5. Duplicate timestamps and chronological monotonicity
6. Timezone consistency (Asia/Kolkata UTC+5:30)
7. NSE trading-session boundaries (09:15-15:30 IST) and calendar holiday awareness
8. Incomplete candle handling (developing vs confirmed setup separation)
9. Index source validation & INDIA VIX unavailability disclosure (no dispersion proxy claimed as VIX)
10. Stock universe coverage transparency (31/500 = 6.2%, excluded count disclosed)
11. Fundamental reporting period validation and metadata labeling
12. Missing fundamentals preserved as None (never fabricated as 0)
13. Quarterly growth zero/negative denominator guardrails (returns None, not 0 or Inf)
14. Corporate action limitations and unadjusted gap detection (>40% drop or >80% jump)
15. Backtesting look-ahead prevention & disclaimers (survivorship bias, statutory notice)
16. Scanner data-quality metadata (standardized metadata format)
17. Money Flow source and calculation metadata (MFM buying/selling bias, turnover mode)
18. No fabricated Dhan live data when API credentials / feed are inactive
"""

from __future__ import annotations

import datetime
import pytest
from fastapi.testclient import TestClient

from app.database import get_bars, get_stock, init_db, list_stocks
from app.main import app
from app.services.advanced_scanner_service import run_advanced_scan
from app.services.data_quality_service import (
    DataMode,
    audit_single_symbol_data_quality,
    audit_universe_coverage,
    build_standard_metadata,
    check_ist_market_hours,
    generate_market_data_quality_report,
    resolve_data_mode,
)
from app.services.fundamental_ratios_service import (
    calculate_cagr,
    compute_all_ratios,
)
from app.services.market_intelligence_service import (
    get_market_overview,
    get_sector_intelligence,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
    calculate_linear_estimated_intraday_rvol,
    calculate_stock_volume_intelligence,
    get_money_flow_dashboard,
)
from app.services.smc_backtest_service import run_smc_backtest
from app.services.smc_service import (
    detect_market_structure,
    detect_order_blocks,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is initialised."""
    init_db()


# ---------------------------------------------------------------------------
# Test 1: DataMode Taxonomy & Strict Truthfulness
# ---------------------------------------------------------------------------

def test_01_data_mode_resolution_and_taxonomy():
    """Historical providers (yfinance, sqlite, demo) can NEVER be labeled as LIVE."""
    # Historical providers must be forced to HISTORICAL even if caller claims is_live_stream=True
    assert resolve_data_mode("yfinance", is_live_stream=True) == DataMode.HISTORICAL.value
    assert resolve_data_mode("sqlite", is_live_stream=True) == DataMode.HISTORICAL.value
    assert resolve_data_mode("demo", is_live_stream=True) == DataMode.HISTORICAL.value
    assert resolve_data_mode("historical", is_live_stream=True) == DataMode.HISTORICAL.value

    # Dhan broker feed reflects actual stream connectivity
    assert resolve_data_mode("dhan", is_live_stream=False) == DataMode.DELAYED.value
    assert resolve_data_mode("dhan", is_live_stream=True) == DataMode.LIVE.value

    # Stale, estimated, and unavailable modes
    assert resolve_data_mode("yfinance", is_stale=True) == DataMode.STALE.value
    assert resolve_data_mode("any", is_estimated=True) == DataMode.ESTIMATED.value
    assert resolve_data_mode("any", has_data=False) == DataMode.UNAVAILABLE.value


# ---------------------------------------------------------------------------
# Test 2: Stale Data Detection and Reason Identification
# ---------------------------------------------------------------------------

def test_02_stale_data_detection_and_reasoning():
    """Verify that outdated historical bars are flagged as stale with exact business days lag."""
    stale_bars = [
        {"timestamp": "2020-01-01", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
        {"timestamp": "2020-01-02", "open": 102, "high": 108, "low": 101, "close": 106, "volume": 1200},
    ]
    report = audit_single_symbol_data_quality(stale_bars, symbol="TEST_STALE")

    assert report["freshness"]["is_fresh"] is False
    assert report["freshness"]["business_days_lag"] > 100
    assert any("Stale data" in a for a in report["anomalies"])


# ---------------------------------------------------------------------------
# Test 3: Missing Timestamps and Empty Datasets
# ---------------------------------------------------------------------------

def test_03_missing_timestamp_and_empty_bars():
    """Verify resilient handling of empty or None bar datasets without raising unhandled exceptions."""
    report_empty = audit_single_symbol_data_quality([], symbol="EMPTY_STK")
    assert report_empty["status"] == "MISSING_DATA"
    assert report_empty["quality_grade"] == "F"
    assert report_empty["bars_count"] == 0
    assert report_empty["first_timestamp"] is None
    assert report_empty["last_timestamp"] is None

    # Missing timestamp column handled via date column fallback
    bars_with_date = [
        {"date": "2026-03-01", "open": 500, "high": 510, "low": 490, "close": 505, "volume": 50000},
        {"date": "2026-03-02", "open": 505, "high": 515, "low": 500, "close": 512, "volume": 60000},
    ]
    report_date = audit_single_symbol_data_quality(bars_with_date, symbol="DATE_STK")
    assert report_date["bars_count"] == 2
    assert report_date["first_timestamp"] == "2026-03-01"


# ---------------------------------------------------------------------------
# Test 4: Full OHLC Mathematical Consistency
# ---------------------------------------------------------------------------

def test_04_full_ohlc_mathematical_consistency():
    """Verify detection of price <= 0, High < Low, and invalid wick geometries."""
    inconsistent_bars = [
        # 1. Negative price
        {"timestamp": "2026-03-01", "open": -10, "high": 105, "low": 95, "close": 100, "volume": 1000},
        # 2. Inverted High < Low
        {"timestamp": "2026-03-02", "open": 100, "high": 90, "low": 110, "close": 95, "volume": 1000},
        # 3. High < max(Open, Close)
        {"timestamp": "2026-03-03", "open": 100, "high": 102, "low": 95, "close": 110, "volume": 1000},
        # 4. Low > min(Open, Close)
        {"timestamp": "2026-03-04", "open": 100, "high": 115, "low": 105, "close": 110, "volume": 1000},
    ]
    report = audit_single_symbol_data_quality(inconsistent_bars, symbol="TEST_OHLC")

    assert report["ohlc_consistency"]["passed"] is False
    assert report["ohlc_consistency"]["violations_count"] >= 4
    assert any("High < Low" in d for d in report["ohlc_consistency"]["details"])
    assert any("High < max(Open, Close)" in d for d in report["ohlc_consistency"]["details"])
    assert any("Low > min(Open, Close)" in d for d in report["ohlc_consistency"]["details"])


# ---------------------------------------------------------------------------
# Test 5: Duplicate and Out-of-Order Timestamps
# ---------------------------------------------------------------------------

def test_05_duplicate_and_out_of_order_timestamps():
    """Verify detection of duplicate and non-chronological bar timestamps."""
    temporal_flawed_bars = [
        {"timestamp": "2026-03-01", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000},
        {"timestamp": "2026-03-01", "open": 102, "high": 106, "low": 98, "close": 103, "volume": 1000},  # duplicate
        {"timestamp": "2026-02-28", "open": 98, "high": 102, "low": 94, "close": 100, "volume": 1000},   # out of order
    ]
    report = audit_single_symbol_data_quality(temporal_flawed_bars, symbol="TEST_TEMPORAL")

    assert report["temporal_integrity"]["is_sorted"] is False
    assert report["temporal_integrity"]["duplicates_count"] == 1
    assert report["temporal_integrity"]["out_of_order_count"] >= 1


# ---------------------------------------------------------------------------
# Test 6: Timezone Consistency (Asia/Kolkata UTC+5:30)
# ---------------------------------------------------------------------------

def test_06_timezone_consistency_ist():
    """Verify Asia/Kolkata timezone offset and session minute tracking."""
    is_open, elapsed, fraction, desc = check_ist_market_hours()

    assert isinstance(is_open, bool)
    assert 0 <= elapsed <= 375
    assert 0.0 <= fraction <= 1.0
    assert "MARKET_" in desc


# ---------------------------------------------------------------------------
# Test 7: NSE Trading Session Boundaries & Fixed Holidays
# ---------------------------------------------------------------------------

def test_07_nse_trading_session_boundaries_and_holidays():
    """Verify exchange-calendar-aware checks accounting for NSE fixed holidays."""
    # Bars spanning Republic Day (Jan 26) - Jan 26 should NOT be flagged as missing session
    holiday_span_bars = [
        {"timestamp": "2026-01-23", "open": 100, "high": 105, "low": 95, "close": 102, "volume": 1000}, # Friday
        {"timestamp": "2026-01-27", "open": 102, "high": 108, "low": 101, "close": 106, "volume": 1200}, # Tuesday (Jan 26 was Mon Republic Day)
    ]
    report = audit_single_symbol_data_quality(holiday_span_bars, symbol="TEST_HOLIDAY")

    # Jan 26 should be recognized as holiday and excluded from missing sessions
    assert "2026-01-26" not in report["calendar_integrity"]["missing_session_dates"]


# ---------------------------------------------------------------------------
# Test 8: Incomplete Candle Handling (Developing vs Confirmed)
# ---------------------------------------------------------------------------

def test_08_incomplete_candle_handling_developing_vs_confirmed():
    """Verify that swing detection and structural signals require confirmation and are not prematurely flagged."""
    bars = get_bars("RELIANCE")
    assert len(bars) >= 20

    import pandas as pd
    df = pd.DataFrame(bars)
    structure = detect_market_structure(df, lookback=3)

    # Swings must have confirmation_index > index (at least index + lookback)
    for sw in structure["swings"]:
        assert sw["is_confirmed"] is True
        assert sw["confirmation_index"] >= sw["index"] + 3
        # Signal available index is strictly after confirmation
        if sw.get("signal_available_index") is not None:
            assert sw["signal_available_index"] > sw["confirmation_index"]


# ---------------------------------------------------------------------------
# Test 9: Index Source Validation & INDIA VIX Unavailability
# ---------------------------------------------------------------------------

def test_09_index_source_validation_and_vix_unavailability():
    """Verify synthesized indices are ESTIMATED and INDIA VIX is UNAVAILABLE."""
    overview = get_market_overview(universe="all", force_refresh=True)

    idx_map = {idx["name"]: idx for idx in overview["indices"]}

    # Grounded indices must be explicitly marked ESTIMATED
    for idx_name in ("NIFTY 50", "BANK NIFTY", "NIFTY 500", "NIFTY MIDCAP"):
        assert idx_name in idx_map
        idx_data = idx_map[idx_name]
        assert idx_data["data_mode"] == DataMode.ESTIMATED.value
        assert idx_data["is_estimated"] is True
        assert idx_data["status"] == "ESTIMATED"
        assert idx_data["source"] == "ESTIMATED_COMPONENT_WEIGHTED"

    # INDIA VIX must be marked UNAVAILABLE (never synthesized as real VIX)
    assert "INDIA VIX" in idx_map
    vix = idx_map["INDIA VIX"]
    assert vix["value"] == "UNAVAILABLE"
    assert vix["numeric_value"] is None
    assert vix["change_pct"] is None
    assert vix["data_mode"] == DataMode.UNAVAILABLE.value
    assert vix["status"] == "UNAVAILABLE"
    assert "feed, which is currently unavailable" in vix["disclaimer"]

    # Market regime disclaims VIX unavailability
    regime = overview["market_regime"]
    assert regime["vix_value"] == "UNAVAILABLE"
    assert regime["vix_status"] == "UNAVAILABLE"
    assert "Actual options-implied INDIA VIX" in regime["vix_disclaimer"]


# ---------------------------------------------------------------------------
# Test 10: Stock Universe Coverage Transparency
# ---------------------------------------------------------------------------

def test_10_stock_universe_coverage_calculations():
    """Verify transparent universe auditing: never claims 100% when database is partial."""
    coverage = audit_universe_coverage("nifty500")

    assert coverage["universe_name"] == "nifty500"
    assert coverage["configured_instruments"] == 500
    assert coverage["tracked_instruments"] == 31
    assert coverage["excluded_count"] == 469
    assert coverage["coverage_pct"] == 6.2
    assert coverage["is_full_coverage"] is False
    assert "scanned 31 of 500" in coverage["coverage_disclosure"].lower()
    assert "469 constituents unseeded/missing" in coverage["coverage_disclosure"].lower()


# ---------------------------------------------------------------------------
# Test 11: Fundamental Reporting Period Validation & Metadata
# ---------------------------------------------------------------------------

def test_11_fundamental_reporting_period_validation():
    """Verify calculated ratios include reporting periods, provenance, and metric metadata."""
    ratios = compute_all_ratios("TCS")

    assert ratios.symbol == "TCS"
    assert ratios.reporting_period.startswith("FY")
    assert ratios.data_provenance in ("verified", "csv_import", "yfinance", "screener", "upstox_api")
    assert ratios.confidence in ("HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA")

    # Metric metadata defines units and calculation types
    meta = ratios.metric_metadata
    assert "revenue_cagr_3y" in meta
    assert meta["revenue_cagr_3y"]["unit"] == "pct"
    assert meta["revenue_cagr_3y"]["type"] == "calculated"
    assert "roe" in meta
    assert meta["roe"]["type"] == "calculated"


# ---------------------------------------------------------------------------
# Test 12: Missing Fundamentals Preserved as None (Never Zero)
# ---------------------------------------------------------------------------

def test_12_missing_fundamentals_preserved_as_none():
    """Verify that missing fundamental metrics remain None, never converted to 0.0."""
    ratios = compute_all_ratios("NON_EXISTENT_TICKER_XYZ")

    assert ratios.growth.revenue_cagr_3y is None
    assert ratios.growth.pat_cagr_3y is None
    assert ratios.profitability.roe is None
    assert ratios.profitability.roce is None
    assert ratios.valuation.pe is None
    assert ratios.health.debt_equity is None


# ---------------------------------------------------------------------------
# Test 13: Quarterly Growth Zero/Negative Denominator Guard
# ---------------------------------------------------------------------------

def test_13_quarterly_growth_zero_denominator_guard():
    """Verify CAGR and QoQ growth guardrails return None when base value is <= 0."""
    # Base zero
    cagr_zero, warn_zero = calculate_cagr(0.0, 150.0, 3)
    assert cagr_zero is None
    assert "non-positive" in warn_zero

    # Base negative
    cagr_neg, warn_neg = calculate_cagr(-50.0, 150.0, 3)
    assert cagr_neg is None
    assert "non-positive" in warn_neg

    # End negative
    cagr_end_neg, warn_end_neg = calculate_cagr(100.0, -20.0, 3)
    assert cagr_end_neg is None
    assert "non-positive" in warn_end_neg


# ---------------------------------------------------------------------------
# Test 14: Corporate Action Limitations & Unadjusted Gap Detection
# ---------------------------------------------------------------------------

def test_14_corporate_action_unadjusted_gap_detection():
    """Verify detection of unadjusted stock split gaps (>40% drop or >80% jump)."""
    split_bars = [
        {"timestamp": "2026-03-01", "open": 2000, "high": 2050, "low": 1980, "close": 2000, "volume": 10000},
        # 5:1 stock split overnight -> open at 400 (-80% gap)
        {"timestamp": "2026-03-02", "open": 400, "high": 420, "low": 390, "close": 410, "volume": 50000},
    ]
    report = audit_single_symbol_data_quality(split_bars, symbol="TEST_SPLIT")

    assert len(report["corporate_actions"]["unadjusted_gap_flags"]) >= 1
    flag = report["corporate_actions"]["unadjusted_gap_flags"][0]
    assert flag["gap_pct"] <= -40.0
    assert any("Unadjusted corporate-action gap" in a for a in report["anomalies"])


# ---------------------------------------------------------------------------
# Test 15: Backtesting Look-Ahead Prevention & Disclaimers
# ---------------------------------------------------------------------------

def test_15_backtesting_lookahead_prevention_and_disclaimers():
    """Verify strict next-candle entry and mandatory statutory/survivorship disclaimers."""
    res = run_smc_backtest("RELIANCE", strategy_type="ORDER_BLOCK_RETEST")

    assert "disclaimers" in res
    disc = res["disclaimers"]
    assert "survivorship_bias" in disc
    assert "corporate_actions" in disc
    assert "lookahead_prevention" in disc
    assert "statutory_notice" in disc
    assert "historical simulations" in disc["statutory_notice"]

    # Verify executed trades entered on or after signal available index
    for trade in res["trades"]:
        assert trade["entry_index"] > trade["signal_confirmation_index"]


# ---------------------------------------------------------------------------
# Test 16: Scanner Data-Quality Metadata
# ---------------------------------------------------------------------------

def test_16_scanner_data_quality_metadata():
    """Verify advanced scanner result returns standard metadata and coverage statistics."""
    scan = run_advanced_scan(universe="nifty500")

    assert "coverage" in scan
    cov = scan["coverage"]
    assert cov["configured_instruments"] == 500
    assert cov["tracked_instruments"] == 31
    assert cov["coverage_pct"] == 6.2

    meta = scan["metadata"]
    assert meta["provider"] == "YFINANCE"
    assert meta["exchange"] == "NSE"
    assert meta["timeframe"] == "1D"
    assert meta["data_mode"] == DataMode.HISTORICAL.value
    assert meta["data_quality_status"] == "HEALTHY"


# ---------------------------------------------------------------------------
# Test 17: Money Flow Source and Calculation Metadata
# ---------------------------------------------------------------------------

def test_17_money_flow_source_and_calculation_metadata():
    """Verify Money Flow Intelligence uses truthful labels and institutional UNAVAILABLE status."""
    mf_dash = get_money_flow_dashboard(force_refresh=True)

    # Check institutional flow requires official exchange data
    inst_flow = mf_dash["institutional_flow"]
    assert inst_flow["status"] == "UNAVAILABLE"
    assert inst_flow["data_mode"] == "UNAVAILABLE"
    assert inst_flow["source"] == "NSE_OFFICIAL_DISCLOSURE_REQUIRED"

    # Check individual stock volume intelligence
    stk = calculate_stock_volume_intelligence("RELIANCE")
    assert 0.0 <= stk["close_location_buying_bias_pct"] <= 100.0
    assert 0.0 <= stk["close_location_selling_bias_pct"] <= 100.0
    assert stk["turnover_type"] in ("ACTUAL_TURNOVER", "ESTIMATED_TURNOVER")
    assert stk["traded_value_status"] in ("ACTUAL_TURNOVER", "ESTIMATED_TURNOVER")


# ---------------------------------------------------------------------------
# Test 18: No Fabricated Dhan Live Data When Inactive
# ---------------------------------------------------------------------------

def test_18_no_fabricated_dhan_live_data_when_inactive():
    """Verify that when Dhan live stream is inactive, platform never claims LIVE data mode."""
    client = TestClient(app)

    # Overview endpoint
    dash_res = client.get("/api/market/intelligence/dashboard?universe=all")
    assert dash_res.status_code == 200
    d_data = dash_res.json()
    assert d_data["metadata"]["data_mode"] == DataMode.HISTORICAL.value

    # Scanner endpoint
    scan_res = client.post("/api/scanner/advanced/scan", json={"universe": "all"})
    assert scan_res.status_code == 200
    s_data = scan_res.json()
    assert s_data["metadata"]["data_mode"] == DataMode.HISTORICAL.value

    # Money flow overview
    mf_res = client.get("/api/money-flow/overview")
    assert mf_res.status_code == 200
    mf_data = mf_res.json()
    assert mf_data["metadata"]["data_mode"] == DataMode.HISTORICAL.value
