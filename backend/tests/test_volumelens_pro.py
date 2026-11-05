"""
VolumeLens & Stock Intelligence Pro Acceptance Test Suite.

Validates:
1. Volume Profile Calculation (POC, VAH, VAL, Bins distribution)
2. Order Flow & Footprint Engine (Delta, CVD, Price Tier Clustered Imbalances)
3. 20+ Technical Indicators & Volatility Contraction / Consolidation Detection
4. VolumeLens 7-Point Breakout Screener Preset
5. AI Mentor Quantitative 12-Factor Audit API
6. Trade Planner Position Sizing & Risk Management API
7. Market Data Provider Abstraction & Diagnostics API
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.indicators import calculate_all_indicators
from app.services.order_flow_service import calculate_footprint_data
from app.services.volume_profile_service import calculate_volume_profile


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_bars():
    """Generates 40 synthetic daily bars."""
    bars = []
    base_price = 1000.0
    for i in range(40):
        o = base_price + (i * 1.5)
        h = o + 15.0
        l = o - 10.0
        c = o + 5.0
        v = 100000 + (i * 2000)
        bars.append({
            "timestamp": f"2026-09-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": v,
        })
    return bars


def test_volume_profile_calculation(sample_bars):
    """Test Volume Profile calculation engine."""
    vp = calculate_volume_profile("TEST_SYM", bars=sample_bars, num_bins=20)

    assert vp["symbol"] == "TEST_SYM"
    assert vp["is_estimated"] is True
    assert vp["poc"] is not None
    assert vp["vah"] is not None
    assert vp["val"] is not None
    assert vp["val"] <= vp["poc"] <= vp["vah"]
    assert len(vp["bins"]) == 20

    # Ensure POC bin is marked
    poc_bins = [b for b in vp["bins"] if b["is_poc"]]
    assert len(poc_bins) == 1


def test_order_flow_footprint_and_cvd(sample_bars):
    """Test Footprint order flow and Cumulative Volume Delta."""
    of = calculate_footprint_data("TEST_SYM", bars=sample_bars, limit=25, price_levels_per_bar=6)

    assert of["symbol"] == "TEST_SYM"
    assert of["is_estimated"] is True
    assert of["bars_count"] == 25
    assert len(of["candles"]) == 25
    assert len(of["cvd_series"]) == 25

    # Check candle levels
    first_candle = of["candles"][0]
    assert len(first_candle["levels"]) == 6
    assert first_candle["buy_volume"] > 0
    assert first_candle["sell_volume"] > 0
    assert first_candle["delta"] == round(first_candle["buy_volume"] - first_candle["sell_volume"], 1)


def test_expanded_indicators(sample_bars):
    """Test the expanded 20+ indicator calculations."""
    res = calculate_all_indicators(sample_bars)

    # Core Moving Averages
    assert "ema_9" in res and res["ema_9"] is not None
    assert "ema_20" in res and res["ema_20"] is not None
    assert "sma_20" in res and res["sma_20"] is not None

    # Momentum & Volatility
    assert "rsi" in res and res["rsi"] is not None
    assert "atr_14" in res and res["atr_14"] is not None
    assert "bb_upper" in res and res["bb_upper"] is not None
    assert "bb_lower" in res and res["bb_lower"] is not None
    assert "bb_bandwidth" in res and res["bb_bandwidth"] is not None

    # Volume & Flow
    assert "vwap" in res and res["vwap"] is not None
    assert "obv" in res and res["obv"] is not None
    assert "mfi_14" in res and res["mfi_14"] is not None

    # Oscillators
    assert "roc_10" in res and res["roc_10"] is not None
    assert "cci_20" in res and res["cci_20"] is not None

    # Consolidation
    assert "is_consolidating" in res
    assert "consolidation_range_pct" in res
    assert "breakout_type" in res


def test_volumelens_preset_available(client):
    """Verify that the VolumeLens 7-Point Breakout preset is saved in SQLite and accessible."""
    from app.database import init_db
    init_db()
    resp = client.get("/api/screener/presets")
    assert resp.status_code == 200
    presets = resp.json()

    preset_names = [p["name"] for p in presets]
    assert any("VolumeLens" in name for name in preset_names)

    vl_preset = next(p for p in presets if "VolumeLens" in p["name"])
    assert "config_json" in vl_preset
    import json
    cfg = json.loads(vl_preset["config_json"])
    assert cfg["min_relative_volume"] == 1.5
    assert cfg["min_rsi"] == 55.0


def test_volume_profile_endpoint(client):
    """Test GET /api/volume/profile/{symbol}."""
    resp = client.get("/api/volume/profile/RELIANCE?bins=20")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "RELIANCE"
    assert "poc" in data
    assert "vah" in data
    assert "val" in data
    assert len(data["bins"]) == 20


def test_orderflow_footprint_endpoint(client):
    """Test GET /api/orderflow/footprint/{symbol}."""
    resp = client.get("/api/orderflow/footprint/TCS?limit=15")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "TCS"
    assert data["bars_count"] == 15
    assert data["is_estimated"] is True
    assert len(data["candles"]) == 15


def test_ai_mentor_audit_endpoint(client):
    """Test POST /api/ai/audit/{symbol}."""
    resp = client.post("/api/ai/audit/INFY", json={"query": "Evaluate technical and fundamental health."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "INFY"
    assert "overall_quality_score" in data
    assert "pass_count" in data
    assert data["total_factors"] == 12
    assert len(data["factors"]) == 12
    assert "recommendation" in data


def test_trade_planner_calculate_endpoint(client):
    """Test POST /api/trade-planner/calculate."""
    payload = {
        "symbol": "RELIANCE",
        "direction": "LONG",
        "capital": 500000.0,
        "risk_pct": 1.5,
        "entry_price": 1400.0,
        "stop_loss": 1370.0,
        "target_price": 1490.0,
    }
    resp = client.post("/api/trade-planner/calculate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "RELIANCE"
    assert data["max_risk_budget"] == 7500.0  # 1.5% of 500,000
    assert data["risk_per_share"] == 30.0    # 1400 - 1370
    assert data["reward_per_share"] == 90.0  # 1490 - 1400
    assert data["risk_reward_ratio"] == 3.0  # 90 / 30
    assert data["recommended_shares"] == 250 # 7500 / 30
    assert data["total_cost"] == 350000.0    # 250 * 1400
    assert data["potential_profit"] == 22500.0


def test_provider_status_endpoint(client):
    """Test GET /api/market/provider/status."""
    resp = client.get("/api/market/provider/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_provider" in data
    assert "preferred_provider" in data
    assert "yfinance_available" in data
    assert data["yfinance_available"] is True
