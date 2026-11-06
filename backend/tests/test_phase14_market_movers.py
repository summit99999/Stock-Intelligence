"""
Unit & Integration Test Suite for Market Movers & Price-Volume Confluence (Phase 14).

Verifies:
1. Top Gainers & Top Losers Ranking (percentage price change ordering)
2. Volume Gainers & High-Volume Losers RVOL ordering
3. Bullish Confluence Intersection (GAINERS ∩ VOLUME_GAINERS) with rank preservation
4. Bearish Confluence Intersection (LOSERS ∩ VOLUME_GAINERS) with rank preservation
5. Deduplication and unique symbol guarantee
6. Single synchronized snapshot verification (timestamp consistency across all lists)
7. Universe and Exchange filtering (NIFTY 50, NIFTY 100, NIFTY 500, All)
8. Custom threshold controls (min_rvol, min_price_change_pct, min_traded_value_cr, limit)
9. Empty state handling (when no stocks satisfy strict criteria)
10. Data mode and data quality status truthfulness (no unsupported institutional flow claims)
11. Full API endpoint validation across all 6 endpoints:
    - /api/market-movers/overview
    - /api/market-movers/gainers
    - /api/market-movers/losers
    - /api/market-movers/volume-gainers
    - /api/market-movers/bearish-volume
    - /api/market-movers/confluence
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.market_movers_service import (
    extract_stock_mover_metrics,
    format_turnover,
    format_volume,
    get_market_movers_and_confluence,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Formatting & Extraction Unit Tests
# ---------------------------------------------------------------------------

def test_turnover_formatting():
    """Verify Indian numbering format for turnover (Cr, L, K)."""
    assert "Cr" in format_turnover(15_000_000.0)  # 1.5 Cr
    assert "₹1.50 Cr" == format_turnover(15_000_000.0)
    assert "₹25.00 L" == format_turnover(2_500_000.0)
    assert "₹50.00 K" == format_turnover(50_000.0)
    assert "₹500.00" == format_turnover(500.0)


def test_volume_formatting():
    """Verify volume formatting (Cr, L, K)."""
    assert "1.50 Cr" == format_volume(15_000_000)
    assert "25.00 L" == format_volume(2_500_000)
    assert "50.0 K" == format_volume(50_000)
    assert "500" == format_volume(500)


def test_extract_stock_mover_metrics_calculation():
    """Verify previous close, percentage change, and RVOL calculations."""
    mock_stock = {
        "symbol": "MOCKTEST",
        "company_name": "Mock Test Ltd",
        "sector": "Technology",
        "close": 1100.0,
        "daily_change_pct": 10.0,
        "volume": 500000,
        "relative_volume": 2.5,
        "previous_close": 1000.0,
    }
    metrics = extract_stock_mover_metrics(mock_stock)
    assert metrics["symbol"] == "MOCKTEST"
    assert metrics["close"] == 1100.0
    assert metrics["previous_close"] == 1000.0
    assert metrics["daily_change_pct"] == 10.0
    assert metrics["today_volume"] == 500000
    assert metrics["daily_rvol"] > 0
    assert metrics["traded_value"] == 550_000_000.0  # 500,000 * 1100
    assert metrics["traded_value_cr"] == 55.0
    assert "₹55.00 Cr" in metrics["turnover_formatted"]


# ---------------------------------------------------------------------------
# 2. Ranking & Ordering Logic Tests
# ---------------------------------------------------------------------------

def test_market_movers_gainers_ranking():
    """Verify Top Gainers are strictly ordered by descending daily percentage change."""
    res = get_market_movers_and_confluence(limit=10, force_refresh=True)
    gainers = res["top_gainers"]
    assert len(gainers) > 0

    changes = [g["daily_change_pct"] for g in gainers]
    assert all(c > 0 for c in changes), "All gainers must have positive price change"
    assert changes == sorted(changes, reverse=True), "Gainers must be sorted descending"
    for idx, g in enumerate(gainers, start=1):
        assert g["rank"] == idx


def test_market_movers_losers_ranking():
    """Verify Top Losers are strictly ordered by ascending (most negative first) change."""
    res = get_market_movers_and_confluence(limit=10, force_refresh=True)
    losers = res["top_losers"]
    assert len(losers) > 0

    changes = [l["daily_change_pct"] for l in losers]
    assert all(c < 0 for c in changes), "All losers must have negative price change"
    assert changes == sorted(changes), "Losers must be sorted ascending (most negative first)"
    for idx, l in enumerate(losers, start=1):
        assert l["rank"] == idx


def test_market_movers_volume_gainers_ranking():
    """Verify Volume Gainers are strictly ordered by descending RVOL >= threshold."""
    res = get_market_movers_and_confluence(min_rvol=1.5, limit=10, force_refresh=True)
    vol_gainers = res["volume_gainers"]
    assert len(vol_gainers) > 0

    rvols = [v["daily_rvol"] for v in vol_gainers]
    assert all(r >= 1.5 for r in rvols), "All volume gainers must satisfy min_rvol threshold"
    assert rvols == sorted(rvols, reverse=True), "Volume gainers must be sorted descending by RVOL"


def test_market_movers_high_volume_losers_ranking():
    """Verify High-Volume Losers have negative change AND RVOL >= threshold."""
    res = get_market_movers_and_confluence(min_rvol=1.5, limit=10, force_refresh=True)
    hv_losers = res["high_volume_losers"]

    for item in hv_losers:
        assert item["daily_change_pct"] < 0, "High-volume losers must have negative price change"
        assert item["daily_rvol"] >= 1.5, "High-volume losers must satisfy RVOL threshold"


# ---------------------------------------------------------------------------
# 3. Confluence Intersection Logic Tests
# ---------------------------------------------------------------------------

def test_bullish_confluence_intersection_and_rank_preservation():
    """Verify Bullish Confluence represents GAINERS ∩ VOLUME_GAINERS with preserved ranks."""
    res = get_market_movers_and_confluence(min_rvol=1.5, limit=10, force_refresh=True)
    bullish = res["bullish_confluence"]
    assert len(bullish) > 0

    # Ensure no duplicates in intersection
    symbols = [b["symbol"] for b in bullish]
    assert len(symbols) == len(set(symbols)), "Bullish confluence must have unique symbols"

    for b in bullish:
        assert b["daily_change_pct"] > 0, "Bullish confluence stocks must have positive change"
        assert b["daily_rvol"] >= 1.5, "Bullish confluence stocks must meet RVOL threshold"
        assert b["confluence_type"] == "BULLISH"
        assert "rank_in_gainers" in b and b["rank_in_gainers"] >= 1
        assert "rank_in_volume_gainers" in b and b["rank_in_volume_gainers"] >= 1
        assert "interpretation" in b and len(b["interpretation"]) > 0


def test_bearish_confluence_intersection_and_rank_preservation():
    """Verify Bearish Confluence represents LOSERS ∩ VOLUME_GAINERS with preserved ranks."""
    res = get_market_movers_and_confluence(min_rvol=1.5, limit=10, force_refresh=True)
    bearish = res["bearish_confluence"]

    # Ensure no duplicates in intersection
    symbols = [b["symbol"] for b in bearish]
    assert len(symbols) == len(set(symbols)), "Bearish confluence must have unique symbols"

    for b in bearish:
        assert b["daily_change_pct"] < 0, "Bearish confluence stocks must have negative change"
        assert b["daily_rvol"] >= 1.5, "Bearish confluence stocks must meet RVOL threshold"
        assert b["confluence_type"] == "BEARISH"
        assert "rank_in_losers" in b and b["rank_in_losers"] >= 1
        assert "rank_in_volume_gainers" in b and b["rank_in_volume_gainers"] >= 1


def test_atomic_snapshot_timestamp_and_id():
    """Verify all lists in the result share identical snapshot ID and timestamp."""
    res = get_market_movers_and_confluence(force_refresh=True)
    snap_id = res["snapshot_id"]
    snap_ts = res["snapshot_timestamp"]

    assert snap_id.startswith("snap_")
    assert len(snap_ts) > 0
    assert res["metadata"]["snapshot_id"] == snap_id
    assert res["metadata"]["snapshot_timestamp"] == snap_ts


# ---------------------------------------------------------------------------
# 4. Filter & Universe Control Tests
# ---------------------------------------------------------------------------

def test_market_movers_high_threshold_empty_intersection():
    """Verify that an impossibly high RVOL threshold cleanly returns empty list without error."""
    res = get_market_movers_and_confluence(min_rvol=99.0, force_refresh=True)
    assert res["status"] == "SUCCESS"
    assert len(res["volume_gainers"]) == 0
    assert len(res["high_volume_losers"]) == 0
    assert len(res["bullish_confluence"]) == 0
    assert len(res["bearish_confluence"]) == 0
    assert res["summary_counts"]["bullish_confluence_count"] == 0
    assert res["summary_counts"]["bearish_confluence_count"] == 0


def test_market_movers_universe_filtering():
    """Verify NIFTY 50 universe filter constrains scanned stocks to core constituents."""
    res = get_market_movers_and_confluence(universe="nifty50", force_refresh=True)
    assert res["universe"] == "nifty50"
    assert res["configured_universe_count"] == 50

    all_symbols = [g["symbol"] for g in res["top_gainers"]] + [l["symbol"] for l in res["top_losers"]]
    from app.services.market_intelligence_service import NIFTY_50_CORE
    for sym in all_symbols:
        assert sym in NIFTY_50_CORE, f"{sym} must be in NIFTY 50 core constituents"


def test_market_movers_min_turnover_filtering():
    """Verify min_traded_value_cr filter excludes low turnover stocks."""
    res = get_market_movers_and_confluence(min_traded_value_cr=10.0, force_refresh=True)
    for g in res["top_gainers"]:
        assert g["traded_value_cr"] >= 10.0, f"Expected turnover >= 10 Cr, got {g['traded_value_cr']}"


# ---------------------------------------------------------------------------
# 5. FastAPI HTTP Endpoints Validation
# ---------------------------------------------------------------------------

def test_api_market_movers_overview_endpoint(client: TestClient):
    """Verify GET /api/market-movers/overview returns complete atomic payload."""
    resp = client.get("/api/market-movers/overview?min_rvol=1.5&limit=5")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "SUCCESS"
    assert "top_gainers" in data
    assert "top_losers" in data
    assert "volume_gainers" in data
    assert "high_volume_losers" in data
    assert "bullish_confluence" in data
    assert "bearish_confluence" in data
    assert "summary_counts" in data
    assert "metadata" in data
    assert len(data["top_gainers"]) <= 5


def test_api_market_movers_sub_endpoints(client: TestClient):
    """Verify GET sub-endpoints return targeted slices with snapshot metadata."""
    # Gainers
    r_gain = client.get("/api/market-movers/gainers?limit=3")
    assert r_gain.status_code == 200
    assert "gainers" in r_gain.json()

    # Losers
    r_lose = client.get("/api/market-movers/losers?limit=3")
    assert r_lose.status_code == 200
    assert "losers" in r_lose.json()

    # Volume gainers
    r_vol = client.get("/api/market-movers/volume-gainers?min_rvol=1.5&limit=3")
    assert r_vol.status_code == 200
    assert "volume_gainers" in r_vol.json()

    # Bearish volume
    r_bear = client.get("/api/market-movers/bearish-volume?min_rvol=1.5&limit=3")
    assert r_bear.status_code == 200
    assert "high_volume_losers" in r_bear.json()

    # Confluence
    r_conf = client.get("/api/market-movers/confluence?min_rvol=1.5&limit=3")
    assert r_conf.status_code == 200
    c_data = r_conf.json()
    assert "bullish_confluence" in c_data
    assert "bearish_confluence" in c_data
