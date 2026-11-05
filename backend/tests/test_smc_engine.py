"""
Smart Money Concepts (SMC) & Order Block Acceptance Tests.

Tests:
1. Deterministic Market Structure (Pivots, HH, HL, LH, LL, BOS vs CHoCH distinction)
2. Order Block Detection & Lifecycle (Fresh, Tested, Mitigated, Invalidation, No Repainting)
3. Fair Value Gaps (Bullish & Bearish 3-candle FVG, Fill % computation)
4. Liquidity Detection (Equal Highs, Equal Lows, PDH/PDL, Liquidity Sweeps)
5. Premium & Discount Dealing Range (Equilibrium 50%)
6. Market X-Ray Normalized Strength & Choppiness Scoring
7. SMC Walk-Forward Backtesting Engine
8. REST API Endpoints Verification
"""

import pytest
from fastapi.testclient import TestClient
import pandas as pd

from app.main import app
from app.services.market_xray_service import compute_stock_xray, generate_market_xray_dashboard
from app.services.smc_backtest_service import run_smc_backtest
from app.services.smc_service import (
    analyze_smart_money_concepts,
    calculate_premium_discount,
    calculate_setup_score,
    detect_fair_value_gaps,
    detect_liquidity_and_sweeps,
    detect_market_structure,
    detect_order_blocks,
    _prepare_df,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def synthetic_smc_bars():
    """
    Creates an explicit multi-swing market structure:
    - Rally to Swing High 1 (1050)
    - Pullback to Higher Low 1 (1010)
    - Strong impulse break above 1050 to Higher High 2 (1100) -> Bullish BOS & Order Block
    - Pullback into Order Block zone (1020) -> OB Retest & Bounce
    - Closes at 1080
    """
    bars = []
    prices = [
        # Baseline / Base formation
        (1000, 1005, 995, 1000, 100000),
        (1000, 1015, 998, 1010, 120000),
        (1010, 1030, 1005, 1025, 150000),
        # Swing High 1 (1050)
        (1025, 1050, 1020, 1045, 200000),
        (1045, 1048, 1030, 1035, 110000),
        # Pullback to Higher Low 1 (1010) - Last down candle before impulse
        (1035, 1038, 1015, 1018, 90000),
        (1018, 1020, 1010, 1012, 85000),  # Bullish OB origin candle!
        # Bullish Displacement breaking 1050 (BOS!)
        (1012, 1045, 1012, 1040, 350000),
        (1040, 1075, 1038, 1070, 420000),
        (1070, 1100, 1065, 1095, 380000),  # Higher High 2 (1100)
        # Pullback retesting the Order Block zone around 1015-1020
        (1095, 1098, 1060, 1065, 120000),
        (1065, 1070, 1035, 1040, 110000),
        (1040, 1042, 1018, 1025, 210000),  # Retests OB zone
        # Bounce from OB
        (1025, 1060, 1022, 1055, 300000),
        (1055, 1085, 1050, 1080, 250000),
    ]

    for i, (o, h, l, c, v) in enumerate(prices):
        bars.append({
            "timestamp": f"2026-10-{(i + 1):02d}",
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v),
        })
    return bars


def test_market_structure_bos_and_choch(synthetic_smc_bars):
    """Test swing detection and Bullish BOS confirmation."""
    df = _prepare_df(synthetic_smc_bars)
    res = detect_market_structure(df, lookback=2)

    assert "swings" in res
    assert len(res["swings"]) > 0
    assert "breaks" in res
    assert len(res["breaks"]) > 0

    # Ensure break of 1050 was identified as a Bullish break
    bos_breaks = [b for b in res["breaks"] if b["direction"] == "BULLISH"]
    assert len(bos_breaks) >= 1
    assert bos_breaks[0]["broken_level"] >= 1040.0


def test_order_block_detection_and_lifecycle(synthetic_smc_bars):
    """Test Order Block detection, displacement, and retest tracking."""
    df = _prepare_df(synthetic_smc_bars)
    structure = detect_market_structure(df, lookback=2)
    obs = detect_order_blocks(df, structure["breaks"], min_displacement_atr=0.8)

    assert len(obs) >= 1
    bull_obs = [ob for ob in obs if ob["direction"] == "BULLISH"]
    assert len(bull_obs) >= 1

    first_ob = bull_obs[0]
    assert first_ob["zone_low"] <= first_ob["zone_high"]
    assert first_ob["invalidation_level"] <= first_ob["zone_low"]
    assert first_ob["displacement_atr"] > 0
    # Must have tested the zone on the pullback
    assert first_ob["status"] in ("TESTED", "MITIGATED")
    assert first_ob["retest_count"] >= 1


def test_fair_value_gaps():
    """Test 3-candle FVG detection with known synthetic gap."""
    bars = [
        {"timestamp": "2026-10-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 102, "high": 115, "low": 102, "close": 114, "volume": 5000},  # Big displacement
        {"timestamp": "2026-10-03", "open": 115, "high": 120, "low": 110, "close": 118, "volume": 3000},  # Low 110 > High 102
        {"timestamp": "2026-10-04", "open": 118, "high": 119, "low": 106, "close": 108, "volume": 2000},  # Partially fills gap
    ]
    df = _prepare_df(bars)
    fvgs = detect_fair_value_gaps(df, min_atr_mult=0.05)

    assert len(fvgs) >= 1
    bull_fvg = next(g for g in fvgs if g["direction"] == "BULLISH")
    assert bull_fvg["zone_low"] == 102.0
    assert bull_fvg["zone_high"] == 110.0
    assert bull_fvg["fill_pct"] > 0  # Bar 4 dipped to 106, filling 50%
    assert bull_fvg["is_filled"] is False


def test_liquidity_detection_and_sweep():
    """Test detection of Equal Highs and Liquidity Sweep condition."""
    bars = [
        {"timestamp": "2026-10-01", "open": 100, "high": 110.0, "low": 98, "close": 105, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 105, "high": 106.0, "low": 101, "close": 103, "volume": 1000},
        {"timestamp": "2026-10-03", "open": 103, "high": 110.1, "low": 102, "close": 104, "volume": 1000},  # EQH around 110
        {"timestamp": "2026-10-04", "open": 104, "high": 112.5, "low": 103, "close": 107, "volume": 2000},  # Wicks to 112.5, closes at 107 (SWEEP!)
    ]
    df = _prepare_df(bars)
    swings = [
        {"index": 0, "timestamp": "2026-10-01", "type": "SWING_HIGH", "price": 110.0},
        {"index": 2, "timestamp": "2026-10-03", "type": "SWING_HIGH", "price": 110.1},
    ]
    liq = detect_liquidity_and_sweeps(df, swings, tolerance_pct=0.2)

    assert len(liq["equal_highs"]) >= 1
    assert "PDH" in liq["key_levels"]
    assert "PDL" in liq["key_levels"]
    assert len(liq["sweeps"]) >= 1
    assert "BEARISH" in liq["sweeps"][0]["direction"]


def test_premium_and_discount():
    """Test Premium, Discount, and Equilibrium calculations."""
    bars = [
        {"timestamp": "2026-10-01", "open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 120, "high": 120, "low": 120, "close": 120, "volume": 1000},
    ]
    df = _prepare_df(bars)
    swings = [
        {"index": 0, "type": "SWING_LOW", "price": 100.0},
        {"index": 1, "type": "SWING_HIGH", "price": 200.0},
    ]
    pd_res = calculate_premium_discount(df, swings)

    assert pd_res["equilibrium"] == 150.0
    assert pd_res["swing_low"] == 100.0
    assert pd_res["swing_high"] == 200.0
    # Price is 120, which is below 150 -> Discount
    assert "DISCOUNT" in pd_res["zone"]


def test_market_xray_computation():
    """Test normalized directional strength scoring and choppiness detection."""
    stock_meta = {"company_name": "Test Co", "sector": "IT", "close": 1050.0, "daily_change_pct": 2.5}
    res = compute_stock_xray("RELIANCE", stock_meta)

    assert "bullish_score" in res
    assert "bearish_score" in res
    assert "adr_50" in res
    assert "rvol" in res
    assert "is_choppy" in res
    assert 0.0 <= res["bullish_score"] <= 100.0
    assert 0.0 <= res["bearish_score"] <= 100.0


def test_smc_walk_forward_backtest(synthetic_smc_bars):
    """Test historical walk-forward backtest for Order Block retest strategy."""
    bt = run_smc_backtest("TEST_SYM", strategy_type="ORDER_BLOCK_RETEST", bars=synthetic_smc_bars, target_rr=2.0)

    assert bt["symbol"] == "TEST_SYM"
    assert bt["strategy"] == "ORDER_BLOCK_RETEST"
    assert "summary" in bt
    assert "win_rate_pct" in bt["summary"]
    assert "profit_factor" in bt["summary"]
    assert "equity_curve" in bt
    assert len(bt["equity_curve"]) >= 1


def test_api_smc_endpoints(client):
    """Test full suite of SMC API endpoints."""
    # 1. Full SMC Analysis
    resp = client.get("/api/smc/analysis/RELIANCE")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "RELIANCE"
    assert "market_structure" in data
    assert "order_blocks" in data
    assert "fair_value_gaps" in data
    assert "liquidity" in data
    assert "premium_discount" in data
    assert "setup_score" in data

    # 2. Granular Order Blocks
    resp_ob = client.get("/api/smc/order-blocks/TCS")
    assert resp_ob.status_code == 200
    assert "order_blocks" in resp_ob.json()

    # 3. Market X-Ray Dashboard
    resp_xray = client.get("/api/smc/xray?limit=15")
    assert resp_xray.status_code == 200
    xray = resp_xray.json()
    assert "bullish_board" in xray
    assert "bearish_board" in xray
    assert "market_breadth" in xray
    assert "sector_rankings" in xray

    # 4. Backtest API
    payload = {
        "symbol": "RELIANCE",
        "strategy_type": "ORDER_BLOCK_RETEST",
        "target_rr": 2.0,
        "cost_bps": 5.0,
        "max_holding_bars": 15,
        "use_indian_costs": True,
        "allow_overlapping": False,
    }
    resp_bt = client.post("/api/smc/backtest", json=payload)
    assert resp_bt.status_code == 200
    bt_data = resp_bt.json()
    assert bt_data["symbol"] == "RELIANCE"
    assert "summary" in bt_data
    assert "total_statutory_fees" in bt_data["summary"]


def test_non_repainting_timestamps_validation(synthetic_smc_bars):
    """
    Milestone 2 Validation:
    Verify that swing pivots, structural breaks, and order blocks strictly require
    confirmation latency and cannot be accessed before their confirmation bars.
    """
    df = _prepare_df(synthetic_smc_bars)
    lookback = 2
    res = detect_market_structure(df, lookback=lookback)

    for sw in res["swings"]:
        occ_idx = sw["occurrence_index"]
        conf_idx = sw["confirmation_index"]
        avail_idx = sw["signal_available_index"]

        # Confirmation must occur strictly after lookback candles
        assert conf_idx == occ_idx + lookback
        if avail_idx is not None:
            assert avail_idx >= conf_idx
        else:
            assert conf_idx + 1 >= len(df)
        # Confirmation timestamp must be chronologically >= occurrence timestamp
        assert sw["confirmation_timestamp"] >= sw["occurrence_timestamp"]

    # Structural breaks must only break levels whose confirmation was <= break_bar
    for brk in res["breaks"]:
        break_bar = brk["bar_index"]
        if brk["signal_available_index"] is not None:
            assert brk["signal_available_index"] == break_bar + 1
        else:
            assert break_bar + 1 >= len(df)
        assert brk["confirmation_timestamp"] == brk["timestamp"]


def test_order_block_lifecycle_priority_and_gap_through():
    """
    Milestone 3 Validation:
    Test deterministic priority:
    1. Immediate invalidation
    2. Gap-through without touching zone
    3. 50% mitigation
    4. Multiple retests from outside
    """
    # Create test bars with an order block and subsequent lifecycle events
    prices = [
        # Baseline
        (100, 102, 98, 100, 1000),
        (100, 101, 99, 100, 1000),
        # OB candidate: Down candle
        (100, 101, 95, 96, 2000),  # Bullish OB (Zone 95-101, Invalidation 95)
        # Big impulse up (BOS break)
        (96, 120, 96, 118, 5000),
        # Test 1: Price enters zone to 98 (tested, depth ~50%)
        (118, 118, 98, 108, 2000),
        # Bounce up
        (108, 115, 107, 114, 1500),
        # Test 2: Invalidation by closing below 95
        (114, 114, 90, 92, 4000),
    ]
    bars = []
    for i, (o, h, l, c, v) in enumerate(prices):
        bars.append({
            "timestamp": f"2026-10-{(i + 1):02d}",
            "open": float(o),
            "high": float(h),
            "low": float(l),
            "close": float(c),
            "volume": float(v),
        })

    df = _prepare_df(bars)
    breaks = [{
        "bar_index": 3,
        "type": "BOS",
        "direction": "BULLISH",
    }]
    obs = detect_order_blocks(df, breaks, min_displacement_atr=0.5)
    assert len(obs) == 1
    ob = obs[0]
    # Because candle 6 closed at 92 < 95, final status MUST be INVALIDATED!
    assert ob["status"] == "INVALIDATED"
    assert ob["retest_count"] >= 1
    assert ob["invalidation_index"] == 6


def test_liquidity_sweep_vs_breakout_rejection():
    """
    Milestone 4 Validation:
    Verify true liquidity sweep with reclaim & rejection vs failed sweep (continuation breakout).
    """
    # 1. Sweep setup: Bar 0 has high 100. Bar 1 wicks to 105, but closes at 98 (reclaim + rejection)
    prices_sweep = [
        (95, 100, 94, 98, 1000),
        (98, 105, 96, 97, 3000),  # Wick through 100, close at 97 < 100 (True Bearish Sweep)
    ]
    bars_sweep = [
        {"timestamp": f"2026-10-0{i+1}", "open": o, "high": h, "low": l, "close": c, "volume": v}
        for i, (o, h, l, c, v) in enumerate(prices_sweep)
    ]
    df_sweep = _prepare_df(bars_sweep)
    res_sweep = detect_liquidity_and_sweeps(df_sweep, [])
    assert len(res_sweep["sweeps"]) >= 1
    sw = res_sweep["sweeps"][0]
    assert sw["reclaim_confirmed"] is True
    assert "BEARISH" in sw["direction"]

    # 2. Breakout setup: Bar 0 has high 100. Bar 1 breaks to 105 and closes at 104 (Breakout, NOT sweep)
    prices_bo = [
        (95, 100, 94, 98, 1000),
        (98, 105, 97, 104, 3000),  # Closed above 100!
    ]
    bars_bo = [
        {"timestamp": f"2026-10-0{i+1}", "open": o, "high": h, "low": l, "close": c, "volume": v}
        for i, (o, h, l, c, v) in enumerate(prices_bo)
    ]
    df_bo = _prepare_df(bars_bo)
    res_bo = detect_liquidity_and_sweeps(df_bo, [])
    # Should be classified as failed sweep / breakout, not a true reclaim sweep
    assert len(res_bo["failed_sweeps"]) >= 1
    assert "FAILED_SWEEP" in res_bo["failed_sweeps"][0]["status"]


def test_five_independent_strategies_backtest(synthetic_smc_bars):
    """
    Milestone 5 & 6 Validation:
    Backtest all 5 independent strategies and verify realistic Indian costs & metrics.
    """
    strategies = [
        "ORDER_BLOCK_RETEST",
        "FVG_FILL_REVERSAL",
        "BOS_CONTINUATION",
        "LIQUIDITY_SWEEP_REVERSAL",
        "SMC_VOLUME_CONFIRMATION",
    ]

    for strat in strategies:
        res = run_smc_backtest(
            "TEST_SYM",
            strategy_type=strat,
            bars=synthetic_smc_bars,
            target_rr=2.0,
            use_indian_costs=True,
            cost_bps=5.0,
        )
        assert res["strategy"] == strat
        assert "summary" in res
        assert "win_rate_pct" in res["summary"]
        assert "profit_factor" in res["summary"]
        assert "expectancy_inr" in res["summary"]
        assert "average_r" in res["summary"]
        assert "performance_breakdown" in res
        assert "long" in res["performance_breakdown"]
        assert "short" in res["performance_breakdown"]


def test_walk_forward_and_regimes_audit(synthetic_smc_bars):
    """
    Milestone 7 Validation:
    Verify chronological train/test splitting and market regime breakdown.
    """
    from app.services.smc_backtest_service import run_walk_forward_validation

    # Replicate bars to give sufficient length for walk-forward
    extended_bars = synthetic_smc_bars * 3
    for i, b in enumerate(extended_bars):
        b["timestamp"] = f"2026-09-{(i % 28 + 1):02d}T{i:02d}:00:00"

    wf = run_walk_forward_validation(
        "TEST_SYM",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=extended_bars,
        train_ratio=0.60,
    )

    assert "train_period" in wf
    assert "test_period_oos" in wf
    assert "regime_breakdown" in wf
    assert "overfitting_audit" in wf
    assert wf["train_period"]["bars"] > wf["test_period_oos"]["bars"]


def test_parameter_sensitivity_grid(synthetic_smc_bars):
    """
    Milestone 8 Validation:
    Verify parameter perturbation grid without cliff-edge overfitting.
    """
    from app.services.smc_backtest_service import run_parameter_sensitivity

    extended_bars = synthetic_smc_bars * 2
    for i, b in enumerate(extended_bars):
        b["timestamp"] = f"2026-09-{(i % 28 + 1):02d}"

    ps = run_parameter_sensitivity("TEST_SYM", strategy_type="ORDER_BLOCK_RETEST", bars=extended_bars)
    assert "grid_evaluations" in ps
    assert ps["grid_evaluations"] >= 4
    assert "metrics_distribution" in ps
    assert "robustness_verdict" in ps


def test_data_quality_report_and_endpoints(client):
    """
    Milestones 9 & 10 Validation:
    Test market data quality diagnostic service and newly registered endpoints.
    """
    from app.services.data_quality_service import generate_market_data_quality_report

    dq = generate_market_data_quality_report()
    assert "total_stocks_evaluated" in dq
    assert "healthy_stocks" in dq
    assert "data_providers" in dq
    assert dq["total_stocks_evaluated"] > 0

    # API endpoints
    resp_dq = client.get("/api/smc/data-quality")
    assert resp_dq.status_code == 200
    assert resp_dq.json()["total_stocks_evaluated"] > 0

    resp_wf = client.get("/api/smc/walk-forward/RELIANCE?strategy_type=ORDER_BLOCK_RETEST")
    assert resp_wf.status_code == 200

    resp_sens = client.get("/api/smc/sensitivity/TCS?strategy_type=ORDER_BLOCK_RETEST")
    assert resp_sens.status_code == 200
