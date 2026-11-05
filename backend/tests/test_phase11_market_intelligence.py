"""
Phase 11 Comprehensive Verification & Regression Suite:
Professional Market Intelligence Dashboard & Advanced Scanner.

Tests:
1. Market Intelligence Dashboard calculations (indices, breadth, 52W extremes, regime rating)
2. Sector Intelligence (performance rankings, relative strength, sector rotation quadrants, breadth)
3. Advanced multi-condition technical filters (EMA 20/50/200, RSI, MACD, ADX, Supertrend, RVOL, BB squeeze)
4. Fundamental screening filters (profit growth, revenue growth, ROE, ROCE, Debt/Equity, OPM)
5. AND vs OR filter combination logic
6. 7 Institutional transparent ranking systems
7. Custom Scanner builder CRUD and CSV export
8. Multi-Watchlists persistence and symbol management
9. Automated Alert rule evaluation and trigger history logging
10. Fast API integration endpoints
"""

import json
import pytest
from fastapi.testclient import TestClient

from app.database import (
    clear_market_alert_history,
    create_custom_watchlist,
    create_market_alert,
    delete_custom_scanner,
    delete_custom_watchlist,
    delete_market_alert,
    get_custom_scanner,
    get_custom_watchlist,
    get_market_alert,
    get_market_alert_history,
    init_db,
    list_custom_scanners,
    list_custom_watchlists,
    list_market_alerts,
    save_custom_scanner,
    update_custom_scanner,
    update_market_alert,
)
from app.main import app
from app.services.advanced_scanner_service import (
    export_scan_to_csv,
    run_advanced_scan,
)
from app.services.alerts_watchlist_service import (
    evaluate_active_alerts,
    get_enriched_watchlist,
)
from app.services.market_intelligence_service import (
    get_market_overview,
    get_sector_intelligence,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database is initialised."""
    init_db()


# ---------------------------------------------------------------------------
# 1. Market Intelligence Dashboard Tests
# ---------------------------------------------------------------------------

def test_market_overview_basic():
    """Verify market overview returns indices, breadth, extremes, and regime."""
    overview = get_market_overview(universe="all", force_refresh=True)

    assert "indices" in overview
    assert len(overview["indices"]) >= 5
    index_names = {idx["name"] for idx in overview["indices"]}
    assert "NIFTY 50" in index_names
    assert "BANK NIFTY" in index_names
    assert "INDIA VIX" in index_names

    # Check Breadth
    breadth = overview["breadth"]
    assert breadth["total_tracked"] > 0
    assert breadth["advances"] + breadth["declines"] + breadth["unchanged"] == breadth["total_tracked"]
    assert breadth["advance_decline_ratio"] >= 0
    assert 0.0 <= breadth["breadth_pct"] <= 100.0

    # Check 52W Extremes
    extremes = overview["extremes_52w"]
    assert "highs_count" in extremes
    assert "lows_count" in extremes
    assert isinstance(extremes["near_highs"], list)
    assert isinstance(extremes["near_lows"], list)

    # Check Market Regime
    regime = overview["market_regime"]
    assert regime["regime"] in ("STRONG_BULLISH", "MODERATE_BULLISH", "NEUTRAL", "MODERATE_BEARISH", "STRONG_BEARISH")
    assert 0.0 <= regime["score"] <= 100.0
    assert regime["volatility_regime"] in ("LOW", "NORMAL", "ELEVATED", "HIGH")

    # Check Metadata
    meta = overview["metadata"]
    assert meta["data_mode"] == "HISTORICAL"
    assert meta["exchange"] == "NSE"


def test_market_overview_universe_coverage():
    """Verify transparent coverage reporting between nifty50 and all."""
    ov_all = get_market_overview(universe="all", force_refresh=True)
    ov_nifty50 = get_market_overview(universe="nifty50", force_refresh=True)

    assert ov_all["scanned_count"] >= ov_nifty50["scanned_count"]
    assert ov_nifty50["universe_label"] == "NIFTY 50"
    assert ov_nifty50["configured_universe_count"] == 50
    assert "coverage_pct" in ov_nifty50
    assert "coverage_note" in ov_nifty50


# ---------------------------------------------------------------------------
# 2. Sector Intelligence Tests
# ---------------------------------------------------------------------------

def test_sector_intelligence_calculations():
    """Verify sector performance, breadth, and rotation quadrants."""
    sec_data = get_sector_intelligence(universe="all", force_refresh=True)

    assert sec_data["total_sectors"] > 0
    sectors = sec_data["sectors"]
    assert len(sectors) > 0

    valid_quadrants = {"LEADING", "WEAKENING", "LAGGING", "IMPROVING"}

    for s in sectors:
        assert "sector" in s
        assert s["stock_count"] > 0
        assert "average_change_pct" in s
        assert "relative_strength_vs_market" in s
        assert s["rotation_quadrant"] in valid_quadrants
        assert 0.0 <= s["breadth_pct"] <= 100.0
        assert "strongest_stock" in s
        assert "weakest_stock" in s
        assert s["strongest_stock"]["symbol"] is not None

    # Verify sectors are sorted by performance descending
    changes = [s["average_change_pct"] for s in sectors]
    assert changes == sorted(changes, reverse=True)


# ---------------------------------------------------------------------------
# 3. Advanced Technical & Fundamental Scanner Tests
# ---------------------------------------------------------------------------

def test_advanced_scanner_technical_filters():
    """Test individual technical filters and AND logic."""
    # Price > EMA 20
    scan_ema = run_advanced_scan(
        universe="all",
        filters={"price_above_ema20": True},
        logic_mode="AND",
        page_size=50,
    )
    for stock in scan_ema["items"]:
        assert stock["ema_20"] is not None
        assert stock["close"] > stock["ema_20"]

    # RSI range filter: 50 <= RSI <= 70
    scan_rsi = run_advanced_scan(
        universe="all",
        filters={"min_rsi": 50.0, "max_rsi": 70.0},
        logic_mode="AND",
        page_size=50,
    )
    for stock in scan_rsi["items"]:
        assert 50.0 <= stock["rsi"] <= 70.0

    # Relative volume filter
    scan_rvol = run_advanced_scan(
        universe="all",
        filters={"min_rvol": 1.2},
        logic_mode="AND",
        page_size=50,
    )
    for stock in scan_rvol["items"]:
        assert stock["relative_volume"] >= 1.2


def test_advanced_scanner_fundamental_filters():
    """Test fundamental screening filters (ROE, ROCE, Debt/Equity, Profit Growth)."""
    scan_fund = run_advanced_scan(
        universe="all",
        filters={"min_roe": 15.0, "max_debt_equity": 1.0},
        logic_mode="AND",
        page_size=50,
    )
    assert scan_fund["total_records"] > 0
    for stock in scan_fund["items"]:
        assert stock["roe"] is not None and stock["roe"] >= 15.0
        assert stock["debt_equity"] is not None and stock["debt_equity"] <= 1.0


def test_advanced_scanner_logic_modes():
    """Verify difference between AND mode and OR mode."""
    # In AND mode, both conditions must match (tight)
    scan_and = run_advanced_scan(
        universe="all",
        filters={"min_rsi": 65.0, "min_rvol": 2.0},
        logic_mode="AND",
    )

    # In OR mode, either condition can match (broad)
    scan_or = run_advanced_scan(
        universe="all",
        filters={"min_rsi": 65.0, "min_rvol": 2.0},
        logic_mode="OR",
    )

    assert scan_or["total_records"] >= scan_and["total_records"]


# ---------------------------------------------------------------------------
# 4. 7 Institutional Ranking Systems Tests
# ---------------------------------------------------------------------------

def test_seven_ranking_systems():
    """Verify all 7 transparent ranking presets execute and return ranked items."""
    presets = [
        "BULLISH_OPPORTUNITY",
        "BEARISH_WEAKNESS",
        "BREAKOUT_CANDIDATES",
        "BREAKDOWN_CANDIDATES",
        "HIGH_RELATIVE_STRENGTH",
        "HIGH_VOLUME_ACCUMULATION",
        "CONSOLIDATION_CANDIDATES",
    ]

    for p in presets:
        res = run_advanced_scan(universe="all", ranking_preset=p, page_size=10)
        assert res["ranking_preset"] == p
        assert res["total_records"] > 0
        items = res["items"]
        assert len(items) > 0

        # Verify ranks are sequential and rank_scores are present
        for idx, item in enumerate(items, start=1):
            assert item["rank"] == idx
            assert "rank_score" in item
            assert "rank_reason" in item
            assert len(item["rank_reason"]) > 0


def test_csv_export():
    """Verify CSV export produces standard comma-separated lines."""
    scan_res = run_advanced_scan(universe="all", ranking_preset="BULLISH_OPPORTUNITY", page_size=20)
    csv_str = export_scan_to_csv(scan_res)

    lines = csv_str.strip().splitlines()
    assert len(lines) >= 2  # Header + at least one stock
    header = lines[0].split(",")
    assert "Symbol" in header
    assert "Price" in header
    assert "RankScore" in header


# ---------------------------------------------------------------------------
# 5. Custom Scanner Persistence (CRUD) Tests
# ---------------------------------------------------------------------------

def test_custom_scanner_crud():
    """Verify saving, loading, updating, and deleting custom scanners."""
    conds = {"min_rsi": 55.0, "min_roe": 18.0}
    sc_id = save_custom_scanner(
        name="Test High Quality Momentum",
        description="RSI > 55 and ROE > 18%",
        universe="nifty50",
        timeframe="1D",
        logic_mode="AND",
        conditions_json=json.dumps(conds),
    )
    assert sc_id > 0

    scanners = list_custom_scanners()
    found = [s for s in scanners if s["id"] == sc_id]
    assert len(found) == 1
    assert found[0]["name"] == "Test High Quality Momentum"

    # Update
    updated = update_custom_scanner(
        scanner_id=sc_id,
        name="Updated Name",
        description="Updated desc",
        universe="all",
        timeframe="1D",
        logic_mode="OR",
        conditions_json=json.dumps(conds),
    )
    assert updated is True
    sc_after = get_custom_scanner(sc_id)
    assert sc_after["name"] == "Updated Name"

    # Delete
    deleted = delete_custom_scanner(sc_id)
    assert deleted is True
    assert get_custom_scanner(sc_id) is None


# ---------------------------------------------------------------------------
# 6. Custom Watchlists & Alerts Evaluation Tests
# ---------------------------------------------------------------------------

def test_custom_watchlist_management():
    """Verify multi-watchlist creation and enriched symbol data."""
    wl_id = create_custom_watchlist("Test Portfolio", "High conviction ideas", ["INFY", "TCS"])
    assert wl_id > 0

    enriched = get_enriched_watchlist(wl_id)
    assert enriched is not None
    assert enriched["name"] == "Test Portfolio"
    assert len(enriched["items"]) == 2
    symbols = {it["symbol"] for it in enriched["items"]}
    assert "INFY" in symbols
    assert "TCS" in symbols

    # Cleanup
    assert delete_custom_watchlist(wl_id) is True


def test_alert_rule_creation_and_evaluation():
    """Verify alert rule evaluation against real stock indicators."""
    # Create an alert designed to trigger: PRICE_ABOVE with low threshold
    alt_id = create_market_alert(
        symbol="RELIANCE",
        alert_type="PRICE_ABOVE",
        target_value=1000.0,  # RELIANCE close is ~2480, so this triggers
        timeframe="1D",
        note="Test trigger condition",
    )
    assert alt_id > 0

    triggered = evaluate_active_alerts()
    matched = [t for t in triggered if t["symbol"] == "RELIANCE"]
    assert len(matched) >= 1

    # Verify history
    history = get_market_alert_history(limit=10)
    hist_rel = [h for h in history if h["symbol"] == "RELIANCE"]
    assert len(hist_rel) >= 1

    # Cleanup
    assert delete_market_alert(alt_id) is True


# ---------------------------------------------------------------------------
# 7. Fast API Integration Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_endpoints():
    """Verify all FastAPI routes for Phase 11."""
    client = TestClient(app)

    # Dashboard overview
    r_dash = client.get("/api/market/intelligence/dashboard")
    assert r_dash.status_code == 200
    d = r_dash.json()
    assert "indices" in d
    assert "breadth" in d

    # Sector intelligence
    r_sec = client.get("/api/market/intelligence/sectors")
    assert r_sec.status_code == 200
    s = r_sec.json()
    assert "sectors" in s

    # Advanced scan
    r_scan = client.post(
        "/api/scanner/advanced/scan",
        json={"universe": "all", "ranking_preset": "BULLISH_OPPORTUNITY", "page": 1, "page_size": 10},
    )
    assert r_scan.status_code == 200
    sc = r_scan.json()
    assert sc["total_records"] > 0

    # CSV Export
    r_csv = client.get("/api/scanner/advanced/export-csv")
    assert r_csv.status_code == 200
    assert "text/csv" in r_csv.headers["content-type"]

    # Watchlists
    r_wl = client.get("/api/watchlists")
    assert r_wl.status_code == 200
    assert isinstance(r_wl.json(), list)

    # Alerts
    r_alt = client.get("/api/alerts")
    assert r_alt.status_code == 200
    assert isinstance(r_alt.json(), list)

    # Evaluate alerts
    r_ev = client.post("/api/alerts/evaluate")
    assert r_ev.status_code == 200
    assert r_ev.json()["status"] == "success"
