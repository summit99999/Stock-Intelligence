"""
Daily Volume Intelligence & Money Flow Verification Test Suite.

Covers:
1. Daily volume, moving averages (ADV 10, ADV 20, ADV 50) and Volume Change %
2. Daily RVOL & Session Time-Adjusted Intraday RVOL calculations
3. Traded value (₹ and ₹ Cr) calculations
4. Money Flow Multiplier (MFM), Buying/Selling pressure bounds, and CMF 20
5. Price-Volume Divergence detection (Bullish, Bearish, None)
6. Combined Volume + Price Screening Categories:
   - High Volume + Price Gainers
   - High Volume + Price Losers
   - High Volume + Sideways Stocks
   - Low Volume + Price Breakouts
7. Top Volume Gainers and Top Price Gainers/Losers rankings
8. Sector Money Flow aggregation, Relative Strength, and Rotation Quadrants
9. Delivery percentage handling and truthful fallback
10. Resilient handling of missing bars, empty data, or single-bar histories
11. Full API endpoint integration tests via FastAPI TestClient:
    - GET /api/money-flow/overview
    - GET /api/money-flow/stock/{symbol}
    - POST /api/money-flow/scan
"""

import math
import pytest
from fastapi.testclient import TestClient

from app.database import init_db, get_stock
from app.main import app
from app.services.money_flow_service import (
    _get_ist_session_fraction,
    calculate_stock_volume_intelligence,
    get_money_flow_dashboard,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is initialised."""
    init_db()


# ---------------------------------------------------------------------------
# 1. Daily Volume, Moving Averages & Volume Change %
# ---------------------------------------------------------------------------

def test_daily_volume_and_moving_averages():
    """
    Verify today's volume, ADV 10, ADV 20, ADV 50, and volume change % formula:
    Volume Change % = ((Today's Volume / 20-Day Average Volume) - 1) * 100
    """
    # RELIANCE has 22 daily OHLCV bars in test database
    intel = calculate_stock_volume_intelligence("RELIANCE", session_fraction=1.0)

    assert intel["symbol"] == "RELIANCE"
    assert intel["today_volume"] > 0
    assert intel["adv_10"] > 0
    assert intel["adv_20"] > 0
    assert intel["adv_50"] > 0

    # Test formula for volume change %
    expected_vol_change = round(((intel["today_volume"] / intel["adv_20"]) - 1.0) * 100.0, 2)
    assert abs(intel["volume_change_pct"] - expected_vol_change) < 0.05

    # Test formula for Daily RVOL
    expected_daily_rvol = round(intel["today_volume"] / intel["adv_20"], 2)
    assert abs(intel["daily_rvol"] - expected_daily_rvol) < 0.05


# ---------------------------------------------------------------------------
# 2. Daily RVOL and Time-Adjusted Intraday RVOL
# ---------------------------------------------------------------------------

def test_daily_and_intraday_rvol_calculations():
    """
    Verify that Intraday RVOL correctly scales with session fraction:
    Intraday RVOL = Today's Volume / (ADV 20 * session_fraction)
    """
    fraction = 0.5  # Mid-session (e.g. 187.5 mins of 375 mins)
    label = "Intraday Time-Adjusted (187m of 375m, 50.0%)"
    intel = calculate_stock_volume_intelligence(
        "RELIANCE",
        session_fraction=fraction,
        rvol_time_label=label,
    )

    expected_intraday_vol = intel["adv_20"] * fraction
    expected_intraday_rvol = round(intel["today_volume"] / max(expected_intraday_vol, 1.0), 2)

    assert intel["rvol_time_label"] == label
    assert abs(intel["intraday_rvol"] - expected_intraday_rvol) < 0.05
    # When session fraction is 0.5, intraday RVOL should be approximately double daily RVOL
    assert intel["intraday_rvol"] >= intel["daily_rvol"]


def test_session_fraction_bounds():
    """Verify session fraction calculator returns values in [0.0, 1.0] and valid label."""
    fraction, label, is_open = _get_ist_session_fraction()
    assert 0.0 < fraction <= 1.0
    assert isinstance(label, str) and len(label) > 0
    assert isinstance(is_open, bool)


# ---------------------------------------------------------------------------
# 3. Traded Value Calculations (₹ and ₹ Cr)
# ---------------------------------------------------------------------------

def test_traded_value_calculations():
    """
    Verify traded value:
    Traded Value (₹) = Today's Volume * Today's Close
    Traded Value (₹ Cr) = Traded Value / 10,000,000
    """
    intel = calculate_stock_volume_intelligence("RELIANCE")

    expected_traded_val = round(intel["today_volume"] * intel["close"], 2)
    expected_cr = round(expected_traded_val / 1e7, 2)

    assert abs(intel["traded_value"] - expected_traded_val) < 1.0
    assert abs(intel["traded_value_cr"] - expected_cr) < 0.05


# ---------------------------------------------------------------------------
# 4. Money Flow Multiplier, Buying/Selling Pressure, and CMF
# ---------------------------------------------------------------------------

def test_money_flow_pressures_and_bounds():
    """
    Verify Money Flow Multiplier MFM in [-1, 1],
    Buying Pressure in [0, 100],
    Selling Pressure in [0, 100],
    and Buying + Selling == 100.
    """
    intel = calculate_stock_volume_intelligence("RELIANCE")

    buy = intel["buying_pressure_pct"]
    sell = intel["selling_pressure_pct"]

    assert 0.0 <= buy <= 100.0
    assert 0.0 <= sell <= 100.0
    assert abs((buy + sell) - 100.0) < 0.2

    # CMF 20 should be between -1.0 and 1.0
    assert -1.0 <= intel["cmf_20"] <= 1.0


# ---------------------------------------------------------------------------
# 5. Price-Volume Divergence
# ---------------------------------------------------------------------------

def test_price_volume_divergence():
    """Verify divergence field returns recognized categories."""
    intel = calculate_stock_volume_intelligence("RELIANCE")
    assert intel["price_volume_divergence"] in ("BULLISH_DIVERGENCE", "BEARISH_DIVERGENCE", "NONE")
    assert isinstance(intel["divergence_note"], str)


# ---------------------------------------------------------------------------
# 6. Combined Volume + Price Intelligence Categories
# ---------------------------------------------------------------------------

def test_combined_volume_price_categories():
    """
    Verify the 4 screening categories:
    1. High Volume + Price Gainers: Change > 0.5% & RVOL >= 1.3
    2. High Volume + Price Losers: Change < -0.5% & RVOL >= 1.3
    3. High Volume + Sideways: |Change| <= 0.5% & RVOL >= 1.3
    4. Low Volume + Breakouts: (|Change| >= 1.5% or Breakout) & RVOL < 1.0
    """
    dashboard = get_money_flow_dashboard(universe="all", force_refresh=True)

    cats = dashboard["combined_categories"]
    assert "high_volume_price_gainers" in cats
    assert "high_volume_price_losers" in cats
    assert "high_volume_sideways" in cats
    assert "low_volume_breakouts" in cats

    for st in cats["high_volume_price_gainers"]:
        assert st["daily_change_pct"] > 0.5
        assert st["daily_rvol"] >= 1.3

    for st in cats["high_volume_price_losers"]:
        assert st["daily_change_pct"] < -0.5
        assert st["daily_rvol"] >= 1.3

    for st in cats["high_volume_sideways"]:
        assert abs(st["daily_change_pct"]) <= 0.5
        assert st["daily_rvol"] >= 1.3

    for st in cats["low_volume_breakouts"]:
        assert st["daily_rvol"] < 1.0
        assert (st["is_breakout"] or abs(st["daily_change_pct"]) >= 1.5)


# ---------------------------------------------------------------------------
# 7. Volume Gainers and Price Gainers/Losers Rankings
# ---------------------------------------------------------------------------

def test_volume_gainers_and_price_gainers_ranking():
    """
    Verify:
    - Volume Gainers are sorted by daily_rvol descending.
    - Price Gainers are sorted by daily_change_pct descending.
    - Price Losers are sorted by daily_change_pct ascending.
    """
    dashboard = get_money_flow_dashboard(universe="all", force_refresh=True)

    vol_gainers = dashboard["volume_gainers"]
    price_gainers = dashboard["price_gainers"]
    price_losers = dashboard["price_losers"]

    assert len(vol_gainers) > 0
    assert len(price_gainers) > 0
    assert len(price_losers) > 0

    # Check Volume Gainers ordering
    for i in range(len(vol_gainers) - 1):
        assert vol_gainers[i]["daily_rvol"] >= vol_gainers[i + 1]["daily_rvol"]
        assert vol_gainers[i]["rank"] == i + 1

    # Check Price Gainers ordering
    for i in range(len(price_gainers) - 1):
        assert price_gainers[i]["daily_change_pct"] >= price_gainers[i + 1]["daily_change_pct"]
        assert price_gainers[i]["rank"] == i + 1

    # Check Price Losers ordering
    for i in range(len(price_losers) - 1):
        assert price_losers[i]["daily_change_pct"] <= price_losers[i + 1]["daily_change_pct"]
        assert price_losers[i]["rank"] == i + 1


# ---------------------------------------------------------------------------
# 8. Minimum Traded Value & Minimum Volume Filters
# ---------------------------------------------------------------------------

def test_volume_and_value_filters():
    """Verify minimum traded value and volume filters exclude non-matching stocks."""
    # Run scan with min_traded_value_cr=50.0
    filtered = get_money_flow_dashboard(
        universe="all",
        force_refresh=True,
        min_traded_value_cr=50.0,
    )
    for st in filtered["volume_gainers"]:
        assert st["traded_value_cr"] >= 50.0

    # Run scan with min_volume=1,000,000
    filtered_vol = get_money_flow_dashboard(
        universe="all",
        force_refresh=True,
        min_volume=1_000_000,
    )
    for st in filtered_vol["volume_gainers"]:
        assert st["today_volume"] >= 1_000_000


# ---------------------------------------------------------------------------
# 9. Sector Money Flow and Rotation Quadrants
# ---------------------------------------------------------------------------

def test_sector_money_flow_and_rotation():
    """
    Verify sector money flow aggregation:
    - average_change_pct
    - average_rvol
    - total_traded_value_cr
    - relative_strength_vs_market
    - rotation_quadrant in (LEADING, WEAKENING, LAGGING, IMPROVING)
    """
    dashboard = get_money_flow_dashboard(universe="all", force_refresh=True)
    sectors = dashboard["sector_money_flow"]

    assert len(sectors) > 0
    valid_quadrants = {"LEADING", "WEAKENING", "LAGGING", "IMPROVING"}

    for sec in sectors:
        assert sec["stock_count"] > 0
        assert "sector" in sec
        assert sec["rotation_quadrant"] in valid_quadrants
        assert 0.0 <= sec["average_buying_pressure"] <= 100.0
        assert 0.0 <= sec["average_selling_pressure"] <= 100.0
        assert sec["net_flow_bias"] in (
            "POSITIVE_PRICE_VOLUME_BIAS",
            "NEGATIVE_PRICE_VOLUME_BIAS",
            "BALANCED_PRICE_VOLUME",
            "NET_INFLOW",
            "NET_OUTFLOW",
            "BALANCED",
        )


# ---------------------------------------------------------------------------
# 10. Delivery Data Handling
# ---------------------------------------------------------------------------

def test_delivery_data_truthfulness():
    """Verify delivery status provides either honest percentage or truthful N/A string."""
    intel = calculate_stock_volume_intelligence("RELIANCE")
    if intel["delivery_pct"] is not None:
        assert 0.0 <= intel["delivery_pct"] <= 100.0
        assert "%" in intel["delivery_status"]
    else:
        assert "Exchange Delivery N/A" in intel["delivery_status"]


# ---------------------------------------------------------------------------
# 11. Resilient Handling of Missing or Synthetic Records
# ---------------------------------------------------------------------------

def test_missing_and_synthetic_records():
    """Verify that calculation never raises exception on synthetic, zero-bar, or missing symbols."""
    # Fake symbol with no bars and synthetic metadata
    dummy_meta = {
        "symbol": "DUMMYCO",
        "company_name": "Dummy Company Ltd",
        "close": 250.0,
        "daily_change_pct": 1.25,
        "volume": 500000,
        "relative_volume": 1.8,
        "updated_at": "2026-03-30 15:30:00",
    }
    intel = calculate_stock_volume_intelligence("DUMMYCO", stock_meta=dummy_meta)

    assert intel["symbol"] == "DUMMYCO"
    assert intel["today_volume"] == 500000
    assert intel["daily_rvol"] == 1.8
    assert intel["adv_20"] > 0
    assert intel["traded_value_cr"] > 0
    assert 0.0 <= intel["buying_pressure_pct"] <= 100.0


# ---------------------------------------------------------------------------
# 12. Full FastAPI Endpoints Integration Tests
# ---------------------------------------------------------------------------

def test_api_money_flow_overview():
    """Verify GET /api/money-flow/overview returns HTTP 200 with all 8 dashboard sections."""
    client = TestClient(app)
    resp = client.get("/api/money-flow/overview?universe=all&force_refresh=true")

    assert resp.status_code == 200
    data = resp.json()

    assert "metadata" in data
    assert data["metadata"]["provider"] in ("NSE/yfinance", "NSE/Dhan", "yfinance")
    assert data["metadata"]["data_mode"] == "HISTORICAL"
    assert "disclaimer" in data["metadata"]

    assert "market_overview" in data
    assert data["market_overview"]["scanned_count"] > 0

    assert "money_flow_summary" in data
    assert "volume_gainers" in data
    assert "price_gainers" in data
    assert "price_losers" in data
    assert "combined_categories" in data
    assert "sector_money_flow" in data


def test_api_money_flow_stock_analysis():
    """Verify GET /api/money-flow/stock/{symbol} returns HTTP 200 with deep-dive analytics."""
    client = TestClient(app)
    resp = client.get("/api/money-flow/stock/RELIANCE")

    assert resp.status_code == 200
    data = resp.json()

    assert data["symbol"] == "RELIANCE"
    analysis = data["analysis"]
    assert analysis["today_volume"] > 0
    assert analysis["adv_10"] > 0
    assert analysis["adv_20"] > 0
    assert analysis["adv_50"] > 0
    assert analysis["daily_rvol"] > 0
    assert "rvol_time_label" in analysis
    assert "buying_pressure_pct" in analysis
    assert "selling_pressure_pct" in analysis


def test_api_money_flow_scan():
    """Verify POST /api/money-flow/scan applies filters, sorting, and pagination."""
    client = TestClient(app)
    payload = {
        "universe": "all",
        "min_traded_value_cr": 0.0,
        "min_volume": 0,
        "sort_by": "daily_rvol",
        "sort_order": "desc",
        "page": 1,
        "page_size": 10,
    }
    resp = client.post("/api/money-flow/scan", json=payload)

    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] > 0
    assert len(data["items"]) <= 10
    # Verify descending sort by daily_rvol
    items = data["items"]
    for i in range(len(items) - 1):
        assert items[i]["daily_rvol"] >= items[i + 1]["daily_rvol"]


# ---------------------------------------------------------------------------
# 13. Phase 11.2: Historical Time-of-Day RVOL vs Linear Estimated
# ---------------------------------------------------------------------------

def test_historical_time_of_day_rvol_calculation():
    """
    Verify Method A: Historical Time-of-Day RVOL
    Compares today's cumulative volume against the average cumulative volume
    at the exact same time of day across the previous 20 valid trading sessions.
    """
    from app.services.money_flow_service import calculate_historical_time_of_day_rvol

    # Generate 20 historical sessions with 5-minute bars
    synthetic_bars = []
    # 20 sessions (e.g. days 1 to 20)
    for day in range(1, 21):
        date_str = f"2026-02-{day:02d}"
        # Session bars: 09:15, 09:30, 10:00, 11:30, 13:00, 15:00
        synthetic_bars.append({"timestamp": f"{date_str} 09:15:00", "volume": 100000})
        synthetic_bars.append({"timestamp": f"{date_str} 09:30:00", "volume": 50000})
        synthetic_bars.append({"timestamp": f"{date_str} 10:00:00", "volume": 50000})
        synthetic_bars.append({"timestamp": f"{date_str} 11:30:00", "volume": 50000})  # Cumulative at 11:30 = 250,000
        synthetic_bars.append({"timestamp": f"{date_str} 13:00:00", "volume": 40000})
        synthetic_bars.append({"timestamp": f"{date_str} 15:00:00", "volume": 110000})

    # Today's cumulative volume at 11:30 is 500,000 (2x the historical average of 250,000)
    today_volume_at_1130 = 500000
    res = calculate_historical_time_of_day_rvol(
        symbol="TEST_STOCK",
        today_cumulative_volume=today_volume_at_1130,
        current_time_str="11:30:00",
        lookback_sessions=20,
        intraday_history_bars=synthetic_bars,
    )

    assert res["status"] == "HISTORICAL_TIME_OF_DAY"
    assert res["method"] == "HISTORICAL_TIME_OF_DAY"
    assert res["historical_avg_volume"] == 250000.0
    assert res["sessions_evaluated"] == 20
    # RVOL should be 500,000 / 250,000 = 2.0
    assert abs(res["rvol"] - 2.0) < 0.01
    assert "Historical Time-of-Day" in res["label"]


def test_linear_estimated_rvol_fallback():
    """
    Verify Method B: Linear Estimated Intraday RVOL fallback
    Must be explicitly labeled as ESTIMATED, and never presented as historical time-of-day.
    """
    from app.services.money_flow_service import calculate_linear_estimated_intraday_rvol

    adv_20 = 1000000.0
    fraction = 0.40  # 40% into the 375-min session
    today_vol = 600000.0

    res = calculate_linear_estimated_intraday_rvol(
        today_cumulative_volume=today_vol,
        adv_20=adv_20,
        session_fraction=fraction,
    )

    assert res["method"] == "LINEAR_ESTIMATED"
    assert res["status"] == "ESTIMATED"
    # Expected volume = 1,000,000 * 0.40 = 400,000
    assert res["expected_volume"] == 400000.0
    # RVOL = 600,000 / 400,000 = 1.50
    assert abs(res["rvol"] - 1.50) < 0.01
    assert "ESTIMATED" in res["label"]


def test_missing_intraday_history_fallback():
    """
    Verify that when intraday bar history is missing or insufficient (< 3 sessions),
    historical TOD RVOL returns UNAVAILABLE, and calculate_stock_volume_intelligence
    falls back cleanly to LINEAR_ESTIMATED with status ESTIMATED.
    """
    from app.services.money_flow_service import calculate_historical_time_of_day_rvol

    # Pass empty bars
    res = calculate_historical_time_of_day_rvol(
        symbol="EMPTY_STOCK",
        today_cumulative_volume=100000,
        current_time_str="11:00:00",
        intraday_history_bars=[],
    )

    assert res["rvol"] is None
    assert res["status"] == "UNAVAILABLE"

    # Full stock intelligence with missing intraday bars falls back to LINEAR_ESTIMATED
    intel = calculate_stock_volume_intelligence("RELIANCE", session_fraction=0.5)
    assert intel["intraday_rvol_method"] == "LINEAR_ESTIMATED"
    assert intel["intraday_rvol_status"] == "ESTIMATED"
    assert intel["historical_time_of_day_rvol"] is None
    assert "ESTIMATED" in intel["intraday_rvol_explanation"]


def test_opening_midday_closing_volume_patterns():
    """
    Demonstrate that Historical Time-of-Day RVOL accurately accounts for the U-shaped
    equity volume curve (heavy at open, quiet midday, heavy at close),
    whereas linear estimation produces distorted metrics.
    """
    from app.services.money_flow_service import (
        calculate_historical_time_of_day_rvol,
        calculate_linear_estimated_intraday_rvol,
    )

    # 10 sessions with realistic Indian market U-shape volume:
    # 09:15 - 09:45 (30 mins = 8% of time): 300,000 shares (30% of 1,000,000 daily volume)
    # 09:45 - 13:00 (midday): 300,000 shares
    # 13:00 - 15:30 (closing): 400,000 shares
    synthetic_bars = []
    for d in range(1, 11):
        dt = f"2026-03-{d:02d}"
        synthetic_bars.append({"timestamp": f"{dt} 09:45:00", "volume": 300000})
        synthetic_bars.append({"timestamp": f"{dt} 13:00:00", "volume": 300000})
        synthetic_bars.append({"timestamp": f"{dt} 15:30:00", "volume": 400000})

    # Scenario: Today at 09:45 AM, volume is 300,000 (normal historical pace for opening)
    today_open_vol = 300000
    tod_open = calculate_historical_time_of_day_rvol(
        symbol="U_STOCK",
        today_cumulative_volume=today_open_vol,
        current_time_str="09:45:00",
        intraday_history_bars=synthetic_bars,
    )
    # Historical average at 09:45 is 300,000 -> TOD RVOL is exactly 1.0 (normal!)
    assert abs(tod_open["rvol"] - 1.0) < 0.05

    # Linear model with 30m / 375m = 8% session progress:
    # Expected = 1,000,000 * 0.08 = 80,000 -> Reports falsely high RVOL of 3.75x!
    linear_open = calculate_linear_estimated_intraday_rvol(
        today_cumulative_volume=today_open_vol,
        adv_20=1000000.0,
        session_fraction=30.0 / 375.0,
    )
    assert linear_open["rvol"] > 3.0  # Linear distorts early session, whereas TOD is 1.0


# ---------------------------------------------------------------------------
# 14. Phase 11.2: Corrected Money Flow Terminology & Explanations
# ---------------------------------------------------------------------------

def test_renamed_mfm_terminology_and_bounds():
    """
    Verify renamed outputs:
    - close_location_buying_bias_pct
    - close_location_selling_bias_pct
    - money_flow_multiplier
    - chaikin_money_flow_20
    Verify they are explicitly explained as OHLCV-derived estimates and NOT actual buyer/seller trade volume.
    """
    intel = calculate_stock_volume_intelligence("RELIANCE")

    assert "close_location_buying_bias_pct" in intel
    assert "close_location_selling_bias_pct" in intel
    assert "money_flow_multiplier" in intel
    assert "chaikin_money_flow_20" in intel

    buy_bias = intel["close_location_buying_bias_pct"]
    sell_bias = intel["close_location_selling_bias_pct"]
    mfm = intel["money_flow_multiplier"]
    cmf = intel["chaikin_money_flow_20"]

    assert 0.0 <= buy_bias <= 100.0
    assert 0.0 <= sell_bias <= 100.0
    assert abs((buy_bias + sell_bias) - 100.0) < 0.2
    assert -1.0 <= mfm <= 1.0
    assert -1.0 <= cmf <= 1.0

    # Verify explanations disclose OHLCV derivation
    assert "OHLCV-derived estimate" in intel["close_location_explanation"]
    assert "Does NOT represent actual buyer-initiated or seller-initiated" in intel["close_location_explanation"]
    assert "volume-weighted" in intel["chaikin_money_flow_explanation"]


# ---------------------------------------------------------------------------
# 15. Phase 11.2: Removal of Unsupported Institutional Claims
# ---------------------------------------------------------------------------

def test_institutional_data_unavailability():
    """
    Verify that:
    1. Institutional flow status is UNAVAILABLE when actual sourced data is absent.
    2. No OHLCV price-volume classification makes unsupported institutional claims
       (such as BULLISH_ACCUMULATION_BIAS, BEARISH_DISTRIBUTION_BIAS, NET_INSTITUTIONAL_FLOW).
    """
    dashboard = get_money_flow_dashboard(universe="all", force_refresh=True)

    # Check Dashboard institutional flow
    inst_flow = dashboard["institutional_flow"]
    assert inst_flow["status"] == "UNAVAILABLE"
    assert inst_flow["classification"] == "UNAVAILABLE"
    assert "provider" in inst_flow
    assert "disclosure" in inst_flow
    assert "UNAVAILABLE" in inst_flow["disclosure"]

    # Verify money flow summary uses qualified price-volume terminology
    summary = dashboard["money_flow_summary"]
    assert summary["net_flow_bias"] in (
        "PRICE_VOLUME_UPWARD_EXPANSION",
        "PRICE_VOLUME_DOWNWARD_PRESSURE",
        "BALANCED_PRICE_VOLUME_ROTATION",
    )
    assert "institutional" not in summary["net_flow_bias"].lower()
    assert "OHLCV price-volume indication only" in summary["narrative"]

    # Verify stock-level money flow classifications are qualified
    valid_classifications = {
        "PRICE_ADVANCE_HIGH_VOLUME",
        "PRICE_DECLINE_HIGH_VOLUME",
        "HIGH_VOLUME_CONSOLIDATION_CHURN",
        "LIGHT_VOLUME_BREAKOUT_UNCONFIRMED",
        "BALANCED_VOLUME_PARTICIPATION",
    }
    for st in dashboard["volume_gainers"]:
        assert st["money_flow_classification"] in valid_classifications
        assert st["institutional_flow"]["status"] == "UNAVAILABLE"


# ---------------------------------------------------------------------------
# 16. Phase 11.2: Traded Value Accuracy (Actual vs Estimated Turnover)
# ---------------------------------------------------------------------------

def test_actual_vs_estimated_turnover():
    """
    Verify traded value accuracy labeling:
    - ACTUAL_TURNOVER when official exchange turnover is available
    - ESTIMATED_TURNOVER when approximated from executed volume * LTP
    - UNAVAILABLE when neither is present
    """
    # 1. Test with actual turnover provided in metadata
    meta_with_turnover = {
        "symbol": "ACC_TEST",
        "company_name": "Accuracy Test Corp",
        "close": 500.0,
        "daily_change_pct": 2.0,
        "volume": 2000000,
        "turnover": 1050000000.0,  # ₹105 Cr actual exchange turnover
    }
    intel_actual = calculate_stock_volume_intelligence("ACC_TEST", stock_meta=meta_with_turnover)
    assert intel_actual["turnover_type"] == "ACTUAL_TURNOVER"
    assert intel_actual["traded_value_status"] == "ACTUAL_TURNOVER"
    assert intel_actual["traded_value"] == 1050000000.0
    assert intel_actual["traded_value_cr"] == 105.0

    # 2. Test with estimated turnover (volume * close)
    meta_estimated = {
        "symbol": "EST_TEST",
        "company_name": "Estimated Test Corp",
        "close": 250.0,
        "daily_change_pct": 1.0,
        "volume": 1000000,
    }
    intel_est = calculate_stock_volume_intelligence("EST_TEST", stock_meta=meta_estimated)
    assert intel_est["turnover_type"] == "ESTIMATED_TURNOVER"
    assert intel_est["traded_value_status"] == "ESTIMATED_TURNOVER"
    assert intel_est["traded_value"] == 250000000.0
    assert intel_est["traded_value_cr"] == 25.0

    # 3. Test with missing turnover data
    meta_empty = {
        "symbol": "EMPTY_TEST",
        "company_name": "Empty Test Corp",
        "close": 0.0,
        "volume": 0,
    }
    intel_empty = calculate_stock_volume_intelligence("EMPTY_TEST", stock_meta=meta_empty)
    assert intel_empty["turnover_type"] == "UNAVAILABLE"
    assert intel_empty["traded_value_status"] == "UNAVAILABLE"
    assert intel_empty["traded_value"] == 0.0


# ---------------------------------------------------------------------------
# 17. Phase 11.2: API Metadata and Quality Labels
# ---------------------------------------------------------------------------

def test_api_metadata_quality_labels():
    """
    Verify GET /api/money-flow/overview and /api/money-flow/stock/{symbol}
    expose explicit data quality labels and metadata disclaimers.
    """
    client = TestClient(app)

    # Overview endpoint
    resp = client.get("/api/money-flow/overview?universe=all&force_refresh=true")
    assert resp.status_code == 200
    data = resp.json()

    meta = data["metadata"]
    assert "turnover_status" in meta
    assert meta["institutional_flow_status"] == "UNAVAILABLE"
    assert "disclaimer" in meta
    assert "UNAVAILABLE" in meta["disclaimer"]

    # Stock-level endpoint
    resp_st = client.get("/api/money-flow/stock/RELIANCE")
    assert resp_st.status_code == 200
    data_st = resp_st.json()

    st_meta = data_st["metadata"]
    assert st_meta["institutional_flow_status"] == "UNAVAILABLE"
    assert st_meta["turnover_type"] in ("ACTUAL_TURNOVER", "ESTIMATED_TURNOVER")
    assert st_meta["intraday_rvol_method"] in ("HISTORICAL_TIME_OF_DAY", "LINEAR_ESTIMATED")
    assert data_st["institutional_flow"]["status"] == "UNAVAILABLE"

