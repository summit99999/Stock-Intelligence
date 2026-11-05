"""
Test Suite for Phase 10: VolumeLens-Inspired Chart Analysis & Market Scanner.

Verifies:
1. Technical indicators: A/D line, CMF 20, Relative Strength vs NIFTY, Volume Spikes & Contractions.
2. Trendline, channel, support/resistance clusters & session key levels.
3. Multi-timeframe bar resampling, consensus scoring, and conflict detection.
4. Rule-based setup detection (OB retests, BOS, CHoCH, FVGs, Sweeps, Breakouts).
5. Market scanner 7-category classification and TTL caching.
6. FastAPI endpoints (/api/scanner/market, /api/scanner/category/{cat}, /api/scanner/stock/{sym}/analysis).
"""

from __future__ import annotations

import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.indicators import (
    calculate_all_indicators,
    calculate_indicators_timeseries,
    _ad_series,
    _cmf_series,
    _is_volume_spike,
    _is_volume_contraction,
    _relative_strength,
)
from app.services.trendline_level_service import (
    find_swing_pivots,
    detect_support_resistance_clusters,
    detect_validated_trendlines,
    calculate_session_key_levels,
    analyze_trendlines_and_levels,
)
from app.services.multi_timeframe_service import (
    evaluate_single_timeframe,
    analyze_multi_timeframe,
    resample_ohlcv_bars,
)
from app.services.setup_detection_service import detect_all_setups
from app.services.market_scanner_service import (
    scan_single_stock,
    run_market_scan,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_bars():
    """Generate 60 deterministic synthetic OHLCV bars."""
    bars = []
    base_price = 1000.0
    for i in range(60):
        # Create a wavy upward trending series
        wave = np.sin(i / 4.0) * 15.0
        trend = i * 2.5
        close = round(base_price + trend + wave, 2)
        open_ = round(close - 2.0, 2)
        high = round(close + 5.0, 2)
        low = round(open_ - 4.0, 2)
        vol = 10000 + (i % 5) * 2000
        bars.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        })
    return bars


# ---------------------------------------------------------------------------
# 1. Technical Indicators Tests
# ---------------------------------------------------------------------------

def test_accumulation_distribution_math():
    """Verify that A/D line correctly tracks Close relative to High-Low range."""
    # When Close == High, MFM = +1, A/D increases by full volume
    high = pd.Series([100.0, 110.0])
    low = pd.Series([90.0, 100.0])
    close = pd.Series([100.0, 110.0])
    volume = pd.Series([1000, 2000])

    ad = _ad_series(high, low, close, volume)
    assert len(ad) == 2
    assert ad.iloc[0] == 1000.0
    assert ad.iloc[1] == 3000.0


def test_cmf_calculation():
    """Verify Chaikin Money Flow (CMF 20) bounds and positive sign on strong closes."""
    high = pd.Series([100.0 + i for i in range(25)])
    low = pd.Series([90.0 + i for i in range(25)])
    close = pd.Series([100.0 + i for i in range(25)])  # Close at High -> MFM = +1.0
    vol = pd.Series([1000 for _ in range(25)])

    cmf = _cmf_series(high, low, close, vol, period=20)
    assert cmf.iloc[-1] == 1.0


def test_volume_spike_and_contraction():
    """Verify volume spike and contraction detection against baseline."""
    # 20 baseline bars of 1000 vol
    vols = [1000] * 20

    # Spike: 2500 vol (2.5x > 2.0x)
    spike_vols = pd.Series(vols + [2500])
    assert _is_volume_spike(spike_vols, period=20, threshold=2.0) is True
    assert _is_volume_contraction(spike_vols, period=20, threshold=0.6) is False

    # Contraction: 400 vol (0.4x < 0.6x)
    cont_vols = pd.Series(vols + [400])
    assert _is_volume_contraction(cont_vols, period=20, threshold=0.6) is True
    assert _is_volume_spike(cont_vols, period=20, threshold=2.0) is False


def test_relative_strength_mansfield():
    """Verify Relative Strength vs benchmark calculation."""
    # Stock up 20% (100 -> 120), Benchmark up 10% (1000 -> 1100)
    stock_close = pd.Series([100.0] * 20 + [120.0])
    bench_close = pd.Series([1000.0] * 20 + [1100.0])

    rs = _relative_strength(stock_close, bench_close, period=20)
    assert rs is not None
    # (1.20 / 1.10 - 1.0) * 100 = +9.09% outperformance
    assert pytest.approx(rs, 0.05) == 9.09


def test_timeseries_indicators_output(sample_bars):
    """Verify calculate_indicators_timeseries returns clean aligned arrays."""
    ts = calculate_indicators_timeseries(sample_bars)
    assert "dates" in ts
    assert len(ts["dates"]) == len(sample_bars)
    assert len(ts["ema_20"]) == len(sample_bars)
    assert len(ts["rsi_14"]) == len(sample_bars)
    assert "bollinger" in ts
    assert "macd" in ts


# ---------------------------------------------------------------------------
# 2. Trendlines, Channels & Key Levels Tests
# ---------------------------------------------------------------------------

def test_swing_pivots_no_lookahead():
    """Ensure swing pivots are confirmed only after required right-side bars."""
    bars = []
    for i in range(15):
        # Create a peak at index 5
        h = 150.0 if i == 5 else 100.0
        bars.append({"open": 100, "high": h, "low": 90, "close": 95, "date": f"2026-01-{i+1:02d}"})

    df = pd.DataFrame(bars)
    swing_highs, _ = find_swing_pivots(df, left_bars=3, right_bars=3)
    assert len(swing_highs) == 1
    assert swing_highs[0]["index"] == 5
    assert swing_highs[0]["price"] == 150.0


def test_session_key_levels_calculation(sample_bars):
    """Verify PDH, PDL, PWH, PWL calculation."""
    df = pd.DataFrame(sample_bars)
    kl = calculate_session_key_levels(df)
    assert "pdh" in kl
    assert "pdl" in kl
    assert "pwh" in kl
    assert "pwl" in kl
    assert kl["pdh"] == round(float(df["high"].iloc[-2]), 2)
    assert kl["pdl"] == round(float(df["low"].iloc[-2]), 2)


def test_trendlines_and_zones_service(sample_bars):
    """Verify analyze_trendlines_and_levels returns zones and levels."""
    res = analyze_trendlines_and_levels(sample_bars)
    assert "support_resistance_zones" in res
    assert "trendlines" in res
    assert "channels" in res
    assert "key_levels" in res
    assert res["bars_count"] == len(sample_bars)


# ---------------------------------------------------------------------------
# 3. Multi-Timeframe Analysis Tests
# ---------------------------------------------------------------------------

def test_resample_ohlcv_bars():
    """Verify resampling logic produces valid bar intervals."""
    intraday = []
    for h in range(4):
        for m in (0, 15, 30, 45):
            intraday.append({
                "date": f"2026-01-05 {9+h:02d}:{m:02d}:00",
                "open": 100.0,
                "high": 105.0,
                "low": 98.0,
                "close": 103.0,
                "volume": 500,
            })
    resampled = resample_ohlcv_bars(intraday, "1h")
    assert len(resampled) == 4
    assert resampled[0]["volume"] == 2000  # 4 * 500


def test_multi_timeframe_consensus(sample_bars):
    """Verify weighted consensus score and alignment rating."""
    tf_data = {
        "1D": sample_bars,
        "4h": sample_bars[-40:],
        "1h": sample_bars[-25:],
    }
    mtf = analyze_multi_timeframe(tf_data, symbol="CUSTOM")
    assert "consensus_score" in mtf
    assert "consensus_rating" in mtf
    assert "conflict_detected" in mtf
    assert -100.0 <= mtf["consensus_score"] <= 100.0


# ---------------------------------------------------------------------------
# 4. Setup Detection Engine Tests
# ---------------------------------------------------------------------------

def test_detect_all_setups(sample_bars):
    """Verify rule-based setup detection produces actionable structured setups."""
    setups = detect_all_setups("TEST_STOCK", sample_bars, timeframe="1D")
    assert isinstance(setups, list)
    for s in setups:
        assert "setup_type" in s
        assert "direction" in s
        assert s["direction"] in ("BULLISH", "BEARISH")
        assert "entry_zone" in s
        assert "stop_loss" in s
        assert "target_1" in s
        assert "target_2" in s
        assert "confidence_score" in s
        # Confidence score must be realistically calibrated
        assert 0.0 <= s["confidence_score"] <= 95.0


# ---------------------------------------------------------------------------
# 5. Market Scanner Service Tests
# ---------------------------------------------------------------------------

def test_market_scanner_run():
    """Verify market scan groups stocks into the 7 required categories."""
    scan = run_market_scan(universe="all", force_refresh=True)
    assert "counts" in scan
    assert "categories" in scan
    assert scan["total_scanned"] > 0

    cats = scan["categories"]
    assert "bullish" in cats
    assert "bearish" in cats
    assert "consolidation" in cats
    assert "breakout" in cats
    assert "breakdown" in cats
    assert "high_rvol" in cats
    assert "new_order_blocks" in cats


# ---------------------------------------------------------------------------
# 6. FastAPI Router Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_scanner_market(client):
    """Test GET /api/scanner/market endpoint."""
    res = client.get("/api/scanner/market?universe=all")
    assert res.status_code == 200
    data = res.json()
    assert "counts" in data
    assert "categories" in data
    assert "total_scanned" in data


def test_api_scanner_category(client):
    """Test GET /api/scanner/category/bullish endpoint."""
    res = client.get("/api/scanner/category/bullish")
    assert res.status_code == 200
    data = res.json()
    assert data["category"] == "bullish"
    assert "items" in data
    assert isinstance(data["items"], list)


def test_api_scanner_invalid_category(client):
    """Test GET /api/scanner/category/unknown returns HTTP 400."""
    res = client.get("/api/scanner/category/unknown_cat")
    assert res.status_code == 400


def test_api_scanner_stock_analysis(client):
    """Test GET /api/scanner/stock/RELIANCE/analysis endpoint."""
    res = client.get("/api/scanner/stock/RELIANCE/analysis?timeframe=1D")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert "indicators" in data
    assert "timeseries" in data
    assert "smc" in data
    assert "levels" in data
    assert "volume_profile" in data
    assert "setups" in data
    assert "multi_timeframe" in data
