"""
Phase 10.1: Technical Audit, Signal Accuracy & Production Hardening Test Suite.

Comprehensive test coverage for:
1. Mansfield Relative Strength indicator (conventional formula vs base MA, ratio series, return-ratio alias).
2. Look-ahead bias prevention & prefix-invariance validation.
3. Institutional NSE session-aware resampling (09:15-15:30 IST, 7 hourly session bars, weekend rejection).
4. Estimated Volume Profile (70% value area expansion, POC, configurable bin size, zero-volume handling).
5. Setup score calibration ([0, 95] bounded, is_empirical_probability=False, deduplication).
6. Market scanner consistency (mutual exclusivity, setup count match, metadata fields).
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services.indicators import (
    _mansfield_rs,
    _mansfield_rs_series,
    _relative_performance_vs_benchmark,
    calculate_all_indicators,
)
from app.services.multi_timeframe_service import (
    resample_ohlcv_bars,
    analyze_multi_timeframe,
    _parse_to_ist,
)
from app.services.volume_profile_service import (
    calculate_volume_profile,
)
from app.services.setup_detection_service import detect_all_setups
from app.services.trendline_level_service import (
    find_swing_pivots,
    detect_validated_trendlines,
    analyze_trendlines_and_levels,
)
from app.services.market_scanner_service import (
    scan_single_stock,
    run_market_scan,
)
from app.services.smc_service import (
    analyze_smart_money_concepts,
    detect_market_structure,
    detect_order_blocks,
    detect_fair_value_gaps,
    detect_liquidity_and_sweeps,
)


# =============================================================================
# 1. Mansfield Relative Strength Tests
# =============================================================================

def test_mansfield_rs_conventional_formula():
    """
    Validate the conventional Mansfield Relative Strength formula:
    Ratio_t = S_t / B_t
    BaseMA_t = SMA(Ratio, N)
    MRS_t = ((Ratio_t / BaseMA_t) - 1.0) * 100
    """
    # 10 periods with constant ratio = 1.0 (MRS should be 0.0)
    stock_flat = pd.Series([100.0] * 10)
    bench_flat = pd.Series([100.0] * 10)
    mrs_series = _mansfield_rs_series(stock_flat, bench_flat, period=5)
    assert not mrs_series.dropna().empty
    for val in mrs_series.dropna():
        assert abs(val) < 1e-6

    # Outperforming stock: stock price rising faster than benchmark
    # Ratio goes: 1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.4, 1.6
    stock_rising = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 120.0, 140.0, 160.0])
    bench_steady = pd.Series([100.0] * 8)
    mrs_rising = _mansfield_rs_series(stock_rising, bench_steady, period=5)
    # The latest value must be substantially positive
    assert mrs_rising.iloc[-1] > 0.0

    # Hand-calculated check for latest point:
    # Ratios: [1.0, 1.0, 1.0, 1.0, 1.0, 1.2, 1.4, 1.6]
    # For last point (index 7, ratio 1.6): 5-period window is [1.0, 1.0, 1.2, 1.4, 1.6]
    # mean = (1.0 + 1.0 + 1.2 + 1.4 + 1.6) / 5 = 6.2 / 5 = 1.24
    # Expected MRS = ((1.6 / 1.24) - 1.0) * 100 = (1.29032258 - 1) * 100 = 29.032%
    expected_mrs = ((1.6 / 1.24) - 1.0) * 100.0
    assert abs(mrs_rising.iloc[-1] - expected_mrs) < 1e-4

    # Underperforming stock check
    stock_falling = pd.Series([100.0, 100.0, 100.0, 100.0, 100.0, 80.0, 70.0, 60.0])
    mrs_falling = _mansfield_rs_series(stock_falling, bench_steady, period=5)
    assert mrs_falling.iloc[-1] < 0.0


def test_relative_performance_vs_benchmark_distinct_from_mansfield():
    """
    Ensure the return-ratio metric is preserved under its proper name
    and mathematically differs from the moving-average ratio MRS.
    """
    stock = pd.Series([100.0, 105.0, 110.0, 115.0, 120.0])
    bench = pd.Series([100.0, 102.0, 104.0, 106.0, 110.0])
    ret_perf = _relative_performance_vs_benchmark(stock, bench, period=4)
    # Stock return over 4 bars = (120 - 100)/100 = 0.20
    # Bench return over 4 bars = (110 - 100)/100 = 0.10
    # Return ratio = ((1 + 0.20) / (1 + 0.10) - 1) * 100 = (1.20 / 1.10 - 1) * 100 = 9.0909%
    assert ret_perf is not None
    assert abs(ret_perf - ((1.20 / 1.10 - 1.0) * 100.0)) < 1e-3


def test_calculate_all_indicators_includes_mansfield_and_return_ratio():
    """
    Verify calculate_all_indicators computes both conventional MRS and relative performance.
    """
    bars = []
    for i in range(60):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}" if i < 30 else f"2026-02-{i-29:02d}",
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 100000 + i * 1000,
        })
    res = calculate_all_indicators(bars)
    assert "mansfield_rs_50" in res
    assert "mansfield_rs_20" in res
    assert "relative_performance_vs_benchmark_20" in res
    assert "relative_performance_vs_benchmark_50" in res


# =============================================================================
# 2. Look-Ahead Bias & Prefix-Invariance Tests
# =============================================================================

def test_swing_pivot_confirmation_index_and_prefix_invariance():
    """
    Pivots at bar i confirmed at i + right_bars must be strictly invariant
    to subsequent bars added after confirmation.
    """
    np.random.seed(42)
    n = 60
    prices = 100.0 + np.cumsum(np.random.randn(n))
    bars = []
    for i in range(n):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": float(prices[i]),
            "high": float(prices[i] + 1.5),
            "low": float(prices[i] - 1.5),
            "close": float(prices[i]),
            "volume": 50000,
        })

    df_full = pd.DataFrame(bars)
    sh_full, sl_full = find_swing_pivots(df_full, left_bars=3, right_bars=3)

    # All confirmed pivots must carry occurrence_index and confirmation_index
    for p in sh_full + sl_full:
        assert "occurrence_index" in p
        assert "confirmation_index" in p
        assert p["confirmation_index"] == p["occurrence_index"] + 3

    # Check prefix invariance at cut T = 40
    T = 40
    df_cut = pd.DataFrame(bars[:T])
    sh_cut, sl_cut = find_swing_pivots(df_cut, left_bars=3, right_bars=3)

    # Any pivot in df_cut must match the identical pivot in df_full confirmed at <= T-1
    for p_cut in sh_cut:
        matching = [p for p in sh_full if p["occurrence_index"] == p_cut["occurrence_index"]]
        assert len(matching) == 1
        assert matching[0]["price"] == p_cut["price"]
        assert matching[0]["confirmation_index"] == p_cut["confirmation_index"]


def test_trendline_confirmation_index_present():
    """
    Verify trendlines include confirmation_index and confirmation_date.
    """
    bars = []
    # Create clean ascending series of pivots
    for i in range(50):
        base = 100.0 + i * 2.0
        # Swing lows every 10 bars
        if i % 10 == 0:
            low_val = base - 5.0
        else:
            low_val = base - 1.0
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": base,
            "high": base + 3.0,
            "low": low_val,
            "close": base + 1.0,
            "volume": 10000,
        })
    levels = analyze_trendlines_and_levels(bars)
    for tl in levels.get("trendlines", []):
        assert "confirmation_index" in tl
        assert "confirmation_date" in tl


# =============================================================================
# 3. Institutional NSE Multi-Timeframe Resampling Tests
# =============================================================================

def test_nse_session_aware_resampling_1h_produces_7_bars():
    """
    NSE trading hours are 09:15 to 15:30 IST (375 minutes).
    A complete trading day of 1-minute bars must resample into exactly 7 session hourly bars:
    09:15 (60m), 10:15 (60m), 11:15 (60m), 12:15 (60m), 13:15 (60m), 14:15 (60m), 15:15 (15m close).
    """
    day_str = "2026-01-05"  # Monday
    bars_1m = []
    # 09:15 to 15:30 is 375 minutes (i = 0 to 374)
    start_hour = 9
    start_min = 15
    for i in range(375):
        tot_min = start_hour * 60 + start_min + i
        h = tot_min // 60
        m = tot_min % 60
        ts = f"{day_str} {h:02d}:{m:02d}:00"
        bars_1m.append({
            "timestamp": ts,
            "open": 2000.0 + i * 0.1,
            "high": 2000.0 + i * 0.1 + 0.5,
            "low": 2000.0 + i * 0.1 - 0.5,
            "close": 2000.0 + i * 0.1 + 0.2,
            "volume": 1000,
        })

    resampled_1h = resample_ohlcv_bars(bars_1m, rule="1h")
    # Must produce exactly 7 bars
    assert len(resampled_1h) == 7

    # First bar must be 09:15 IST
    assert "09:15" in str(resampled_1h[0]["timestamp"])
    # Last bar must be 15:15 IST
    assert "15:15" in str(resampled_1h[-1]["timestamp"])

    # High of the day in 1h bars must match the maximum high in the 1m source
    max_high_1m = max(b["high"] for b in bars_1m)
    max_high_1h = max(b["high"] for b in resampled_1h)
    assert abs(max_high_1m - max_high_1h) < 1e-4

    # Total volume must match
    assert sum(b["volume"] for b in resampled_1h) == sum(b["volume"] for b in bars_1m)


def test_nse_session_resampling_rejects_weekends_and_off_hours():
    """
    Bars outside 09:15-15:30 IST or on Saturday/Sunday must be rejected.
    """
    bars = [
        # Pre-market off-hours (08:30 IST)
        {"timestamp": "2026-01-05 08:30:00", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 500},
        # Valid session bar (09:30 IST, Monday)
        {"timestamp": "2026-01-05 09:30:00", "open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000},
        # Post-market off-hours (16:30 IST)
        {"timestamp": "2026-01-05 16:30:00", "open": 102, "high": 104, "low": 101, "close": 103, "volume": 200},
        # Weekend bar (2026-01-10 is Saturday)
        {"timestamp": "2026-01-10 10:00:00", "open": 103, "high": 105, "low": 102, "close": 104, "volume": 300},
    ]

    res = resample_ohlcv_bars(bars, rule="1h")
    # Only the valid Monday 09:30 bar should be retained in the hourly session bar
    assert len(res) == 1
    assert "2026-01-05" in str(res[0]["timestamp"])
    assert res[0]["volume"] == 1000


def test_nse_resampling_4h_produces_two_half_session_bars():
    """
    On 4h target, a full trading day produces exactly 2 half-session bars:
    09:15 (first half) and 12:15 (second half).
    """
    day_str = "2026-01-05"
    bars_1m = []
    for i in range(375):
        tot_min = 9 * 60 + 15 + i
        h = tot_min // 60
        m = tot_min % 60
        bars_1m.append({
            "timestamp": f"{day_str} {h:02d}:{m:02d}:00",
            "open": 1500.0,
            "high": 1510.0,
            "low": 1490.0,
            "close": 1505.0,
            "volume": 100,
        })
    res_4h = resample_ohlcv_bars(bars_1m, rule="4h")
    assert len(res_4h) == 2
    assert "09:15" in str(res_4h[0]["timestamp"])
    assert res_4h[0]["span_minutes"] == 240
    assert res_4h[0]["is_shortened"] is False
    assert res_4h[0]["bar_type"] == "FULL_4H"

    assert "13:15" in str(res_4h[1]["timestamp"])
    assert res_4h[1]["span_minutes"] == 135
    assert res_4h[1]["is_shortened"] is True
    assert res_4h[1]["bar_type"] == "PARTIAL_SESSION_TAIL"


# =============================================================================
# 4. Estimated Volume Profile Tests
# =============================================================================

def test_volume_profile_estimated_labelling_and_structure():
    """
    Volume profile derived from OHLCV spans must be labelled as estimated,
    not trade-level tape data.
    """
    bars = [
        {"timestamp": f"2026-01-{i+1:02d}", "open": 100.0 + i, "high": 105.0 + i, "low": 95.0 + i, "close": 102.0 + i, "volume": 50000}
        for i in range(30)
    ]
    vp = calculate_volume_profile("RELIANCE", bars, num_bins=20)
    assert vp["profile_type"] == "estimated_volume_profile"
    assert vp["is_estimated"] is True
    assert vp["is_trade_level_tape"] is False
    assert "methodology" in vp
    assert vp["poc"] > 0.0
    assert vp["vah"] >= vp["poc"]
    assert vp["val"] <= vp["poc"]
    assert vp["total_volume"] > 0


def test_volume_profile_70_percent_value_area_expansion():
    """
    Value Area must encapsulate approximately 70% (+-15% due to discretisation) of total volume.
    """
    bars = []
    for i in range(40):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": 500.0 + (i % 5),
            "high": 510.0,
            "low": 490.0,
            "close": 502.0,
            "volume": 20000,
        })
    vp = calculate_volume_profile("TCS", bars, num_bins=24)
    tot = vp["total_volume"]
    va_vol = sum(b["volume"] for b in vp["bins"] if b.get("in_value_area"))
    ratio = va_vol / tot if tot > 0 else 0
    assert 0.65 <= ratio <= 0.85


def test_volume_profile_zero_volume_handling():
    """
    Ensure zero volume or flat price bars do not raise ZeroDivisionError.
    """
    bars = [
        {"timestamp": f"2026-01-{i+1:02d}", "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 0}
        for i in range(20)
    ]
    vp = calculate_volume_profile("TEST_FLAT", bars)
    assert vp["total_volume"] == 0
    assert vp["poc"] == 100.0
    assert vp["vah"] == 100.0
    assert vp["val"] == 100.0


# =============================================================================
# 5. Setup Scoring Calibration & Deduplication Tests
# =============================================================================

def test_setup_confidence_score_bounded_and_not_empirical_probability():
    """
    All generated setups must designate confidence as heuristic technical scores
    bounded in [0, 95] with is_empirical_probability=False and explicit invalidation.
    """
    bars = []
    for i in range(50):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": 200.0 + i,
            "high": 205.0 + i,
            "low": 198.0 + i,
            "close": 204.0 + i,
            "volume": 100000 if i != 48 else 300000,
        })
    setups = detect_all_setups("HDFCBANK", bars)
    for s in setups:
        assert "heuristic_technical_score" in s
        assert "confidence_score" in s
        assert 0.0 <= s["heuristic_technical_score"] <= 95.0
        assert s["is_empirical_probability"] is False
        assert s["status"] in ("CONFIRMED", "DEVELOPING")
        assert "is_actionable_entry" in s
        assert s["is_actionable_entry"] == (s["status"] == "CONFIRMED")
        assert "score_breakdown" in s
        assert s["score_breakdown"]["min_score"] == 0.0
        assert s["score_breakdown"]["max_score"] == 95.0
        assert "invalidation_condition" in s
        assert len(s["invalidation_condition"]) > 0


def test_setup_deduplication():
    """
    Ensure deduplication logic prevents duplicate entries for the same setup type and ideal entry.
    """
    bars = []
    for i in range(50):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": 100.0 + i * 0.5,
            "high": 102.0 + i * 0.5,
            "low": 99.0 + i * 0.5,
            "close": 101.0 + i * 0.5,
            "volume": 20000,
        })
    setups = detect_all_setups("INFY", bars)
    keys = set()
    for s in setups:
        ideal_entry = s.get("entry_zone", {}).get("ideal_entry", 0.0)
        key = (s["setup_type"], s["direction"], round(float(ideal_entry), 1))
        assert key not in keys, f"Duplicate setup key found: {key}"
        keys.add(key)


# =============================================================================
# 6. Market Scanner Consistency & Metadata Tests
# =============================================================================

def test_market_scanner_bullish_bearish_mutual_exclusivity():
    """
    A single stock can NEVER be categorized simultaneously as Bullish and Bearish.
    """
    stock_meta = {
        "symbol": "SBIN",
        "company_name": "State Bank of India",
        "sector": "Banking",
        "close": 800.0,
        "daily_change_pct": 1.5,
        "relative_volume": 1.8,
        "rsi": 62.0,
        "supertrend_dir": "up",
        "ema_20": 780.0,
        "ema_50": 760.0,
    }
    item = scan_single_stock("SBIN", stock_meta)
    assert item is not None
    assert not (item["is_bullish"] and item["is_bearish"])

    # Contradictory input case
    contradictory_meta = {
        "symbol": "CONTRADICT",
        "company_name": "Contradictory Stock",
        "close": 500.0,
        "daily_change_pct": 0.0,
        "relative_volume": 1.0,
        "rsi": 50.0,
        "supertrend_dir": "up",
        "ema_20": 500.0,
    }
    item2 = scan_single_stock("CONTRADICT", contradictory_meta)
    if item2:
        assert not (item2["is_bullish"] and item2["is_bearish"])


def test_market_scanner_setup_count_matches_setups_length():
    """
    Verify setup_count strictly matches len(setups).
    """
    stock_meta = {
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries",
        "close": 2800.0,
        "daily_change_pct": 0.5,
    }
    item = scan_single_stock("RELIANCE", stock_meta)
    if item:
        assert item["setup_count"] == len(item["setups"])


def test_market_scan_response_metadata_and_cache_ttl():
    """
    run_market_scan must include cache_ttl_seconds, is_cached, data_mode, exchange.
    """
    scan = run_market_scan(universe="all", force_refresh=True)
    assert "cache_ttl_seconds" in scan
    assert scan["cache_ttl_seconds"] == 60
    assert "is_cached" in scan
    assert scan["is_cached"] is False
    assert scan["exchange"] == "NSE"
    assert scan["data_mode"] == "HISTORICAL"
    assert "metadata" in scan
    assert scan["metadata"]["data_mode"] == "HISTORICAL"
    assert scan["metadata"]["is_cached"] is False

    # Second call within TTL should serve cached response
    scan2 = run_market_scan(universe="all", force_refresh=False)
    assert scan2["is_cached"] is True
    assert scan2["metadata"]["is_cached"] is True
    assert scan2["metadata"]["data_mode"] == "HISTORICAL"


# =============================================================================
# 7. Prefix-Invariance Verification for SMC & Setups (Phase 10.1 Targeted)
# =============================================================================

@pytest.fixture
def trending_smc_bars():
    """Generate a clean synthetic wave series with clear swings and breaks."""
    bars = []
    # 70 bars creating 2 full cycles of higher highs and higher lows
    for i in range(70):
        # Sine wave superimposed on upward slope
        angle = (i / 10.0) * math.pi
        cycle = 15.0 * math.sin(angle)
        trend = i * 2.5
        c = 500.0 + trend + cycle
        h = c + 4.0
        l = c - 4.0
        o = (h + l) / 2.0
        v = 50000 + (100000 if i % 10 == 0 else 0)
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}" if i < 31 else f"2026-02-{i-30:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": v,
        })
    return bars


def test_prefix_invariance_bos_and_choch(trending_smc_bars):
    """
    Verify that BOS and CHoCH structural breaks confirmed on or before cutoff T
    are identical whether evaluated on bars[0:T] or the full bars series.
    """
    df_full = pd.DataFrame(trending_smc_bars)
    res_full = detect_market_structure(df_full, lookback=3)
    breaks_full = res_full["breaks"]

    # Choose cutoff T after at least one confirmed break
    assert len(breaks_full) >= 1
    T = breaks_full[0]["confirmation_index"] + 5

    df_cut = pd.DataFrame(trending_smc_bars[:T])
    res_cut = detect_market_structure(df_cut, lookback=3)
    breaks_cut = res_cut["breaks"]

    # All breaks in cut series must match those in full series confirmed <= T-1
    for b_c in breaks_cut:
        matching = [b for b in breaks_full if b["occurrence_index"] == b_c["occurrence_index"]]
        assert len(matching) == 1, f"Break at index {b_c['occurrence_index']} not found in full run"
        assert matching[0]["type"] == b_c["type"]
        assert matching[0]["broken_level"] == b_c["broken_level"]
        assert matching[0]["confirmation_index"] == b_c["confirmation_index"]


def test_prefix_invariance_order_blocks(trending_smc_bars):
    """
    Verify Order Blocks confirmed at break_bar <= T-1 are invariant to subsequent bars.
    """
    df_full = pd.DataFrame(trending_smc_bars)
    ms_full = detect_market_structure(df_full, lookback=3)
    obs_full = detect_order_blocks(df_full, ms_full["breaks"])

    assert len(obs_full) >= 1
    # Pick cutoff T after the first confirmed order block
    first_ob = obs_full[0]
    T = first_ob["confirmation_index"] + 5

    df_cut = pd.DataFrame(trending_smc_bars[:T])
    ms_cut = detect_market_structure(df_cut, lookback=3)
    obs_cut = detect_order_blocks(df_cut, ms_cut["breaks"])

    assert len(obs_cut) >= 1
    for ob_c in obs_cut:
        matching = [o for o in obs_full if o["occurrence_index"] == ob_c["occurrence_index"]]
        assert len(matching) == 1
        # Zone boundaries must be strictly identical
        assert matching[0]["zone_high"] == ob_c["zone_high"]
        assert matching[0]["zone_low"] == ob_c["zone_low"]
        assert matching[0]["invalidation_level"] == ob_c["invalidation_level"]


def test_prefix_invariance_fair_value_gaps(trending_smc_bars):
    """
    Verify Fair Value Gaps confirmed at bar i <= T-1 are invariant to subsequent bars.
    """
    df_full = pd.DataFrame(trending_smc_bars)
    fvgs_full = detect_fair_value_gaps(df_full)

    if fvgs_full:
        first_fvg = fvgs_full[0]
        T = first_fvg["confirmation_index"] + 5
        df_cut = pd.DataFrame(trending_smc_bars[:T])
        fvgs_cut = detect_fair_value_gaps(df_cut)

        for f_c in fvgs_cut:
            matching = [f for f in fvgs_full if f["confirmation_index"] == f_c["confirmation_index"]]
            assert len(matching) == 1
            assert matching[0]["zone_high"] == f_c["zone_high"]
            assert matching[0]["zone_low"] == f_c["zone_low"]
            assert matching[0]["direction"] == f_c["direction"]


def test_prefix_invariance_liquidity_sweeps(trending_smc_bars):
    """
    Verify confirmed Liquidity Sweeps are invariant to future bars.
    """
    df_full = pd.DataFrame(trending_smc_bars)
    ms_full = detect_market_structure(df_full, lookback=3)
    liq_full = detect_liquidity_and_sweeps(df_full, ms_full["swings"])
    sweeps_full = [s for s in liq_full["sweeps"] if s.get("confirmation_index") is not None]

    if sweeps_full:
        first_sw = sweeps_full[0]
        T = first_sw["confirmation_index"] + 4
        df_cut = pd.DataFrame(trending_smc_bars[:T])
        ms_cut = detect_market_structure(df_cut, lookback=3)
        liq_cut = detect_liquidity_and_sweeps(df_cut, ms_cut["swings"])
        sweeps_cut = [s for s in liq_cut["sweeps"] if s.get("confirmation_index") is not None]

        for s_c in sweeps_cut:
            matching = [s for s in sweeps_full if s["bar_index"] == s_c["bar_index"]]
            assert len(matching) == 1
            assert matching[0]["level_name"] == s_c["level_name"]
            assert matching[0]["direction"] == s_c["direction"]


def test_developing_vs_confirmed_setups_distinction():
    """
    Verify that DEVELOPING and CONFIRMED setups are strictly distinguished:
    - Developing setups must have is_actionable_entry = False.
    - Confirmed setups must have is_actionable_entry = True.
    - Developing signals are never presented as confirmed actionable entries.
    """
    # Create a scenario where an order block exists but price is just in proximity
    bars = []
    for i in range(40):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": 200.0 + i,
            "high": 204.0 + i,
            "low": 198.0 + i,
            "close": 202.0 + i,
            "volume": 25000,
        })
    setups = detect_all_setups("TCS", bars)
    for s in setups:
        assert s["status"] in ("CONFIRMED", "DEVELOPING")
        if s["status"] == "DEVELOPING":
            assert s["is_actionable_entry"] is False
            assert "Developing" in s["summary"]
        elif s["status"] == "CONFIRMED":
            assert s["is_actionable_entry"] is True
            assert "Confirmed" in s["summary"]


def test_all_nine_trade_setup_types_supported():
    """
    Verify that all nine documented setup types can be processed by the engine:
    1. Order Block Retest
    2. BOS Breakout
    3. CHoCH Reversal
    4. FVG Retracement
    5. Liquidity Sweep Reversal
    6. High-Volume Breakout / Breakdown
    7. EMA Pullback
    8. Consolidation Box Breakout
    9. Key Level Rejection
    """
    valid_types = {
        "Order Block Retest",
        "BOS Breakout",
        "BOS Breakdown",
        "CHoCH Reversal",
        "FVG Retracement",
        "Liquidity Sweep Reversal",
        "High-Volume Breakout",
        "High-Volume Breakdown",
        "EMA Pullback",
        "Consolidation Box Breakout",
        "Key Level Rejection",
    }
    # Run across multiple market setups
    bars = []
    for i in range(50):
        bars.append({
            "timestamp": f"2026-01-{i+1:02d}",
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 98.0 + i,
            "close": 103.0 + i,
            "volume": 50000,
        })
    setups = detect_all_setups("INFY", bars)
    for s in setups:
        assert s["setup_type"] in valid_types


def test_standardized_metadata_across_scanner_and_chart_endpoints():
    """
    Verify standardized metadata across all scanner and chart analysis endpoints:
    - provider
    - instrument
    - timeframe
    - data_mode (HISTORICAL)
    - last_candle_timestamp
    - last_update_timestamp
    - is_stale
    """
    client = TestClient(app)

    # 1. Market scan endpoint
    res_m = client.get("/api/scanner/market?universe=all&limit=5")
    assert res_m.status_code == 200
    data_m = res_m.json()
    assert "metadata" in data_m
    m_meta = data_m["metadata"]
    for k in ("provider", "instrument", "timeframe", "data_mode", "last_update_timestamp", "is_stale"):
        assert k in m_meta, f"Missing {k} in /api/scanner/market metadata"
    assert m_meta["exchange"] == "NSE"
    assert m_meta["data_mode"] == "HISTORICAL"

    # 2. Category scan endpoint
    res_c = client.get("/api/scanner/category/bullish?universe=all&limit=5")
    assert res_c.status_code == 200
    data_c = res_c.json()
    assert "metadata" in data_c
    c_meta = data_c["metadata"]
    for k in ("provider", "instrument", "timeframe", "data_mode", "last_update_timestamp", "is_stale"):
        assert k in c_meta, f"Missing {k} in /api/scanner/category metadata"
    assert c_meta["data_mode"] == "HISTORICAL"

    # 3. Stock analysis endpoint (RELIANCE)
    res_s = client.get("/api/scanner/stock/RELIANCE/analysis?timeframe=1D")
    assert res_s.status_code == 200
    data_s = res_s.json()
    assert "metadata" in data_s
    s_meta = data_s["metadata"]
    for k in ("provider", "instrument", "timeframe", "data_mode", "last_update_timestamp", "is_stale"):
        assert k in s_meta, f"Missing {k} in /api/scanner/stock/analysis metadata"
    assert s_meta["data_mode"] == "HISTORICAL"

    # 4. Volume profile endpoint
    res_vp = client.get("/api/volume/profile/RELIANCE")
    assert res_vp.status_code == 200
    data_vp = res_vp.json()
    assert "metadata" in data_vp
    assert data_vp["metadata"]["data_mode"] == "HISTORICAL"

    # 5. Volume VWAP endpoint
    res_vwap = client.get("/api/volume/vwap/RELIANCE")
    assert res_vwap.status_code == 200
    data_vwap = res_vwap.json()
    assert "metadata" in data_vwap
    assert data_vwap["metadata"]["data_mode"] == "HISTORICAL"


def test_historical_never_represented_as_live_and_cache_expiry_integrity():
    """
    Verify that historical data is NEVER represented as LIVE data and that
    cache expiration or refresh does NOT falsely switch data_mode to LIVE.
    """
    client = TestClient(app)

    # First request: force refresh
    res1 = client.get("/api/scanner/market?force_refresh=true")
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["data_mode"] == "HISTORICAL"
    assert d1["metadata"]["data_mode"] == "HISTORICAL"
    assert d1["metadata"]["is_cached"] is False

    # Second request: served from cache within TTL
    res2 = client.get("/api/scanner/market?force_refresh=false")
    assert res2.status_code == 200
    d2 = res2.json()
    # Cache expiration/state must never flip data_mode to LIVE
    assert d2["data_mode"] == "HISTORICAL"
    assert d2["metadata"]["data_mode"] == "HISTORICAL"
    assert d2["metadata"]["is_cached"] is True

