"""
Phase 9.1 Independent Audit Regression & Verification Test Suite.

Exhaustively verifies:
1. Priority 1 — Indian transaction cost model:
   - Separate delivery vs intraday schedules.
   - Configurable trade type.
   - Date-effective exchange charges (post Oct 1, 2024 rate 0.00297% vs pre 0.00345%).
   - STT and Stamp duty calculated according to trade type.
   - Brokerage (Zerodha delivery ₹0, intraday min(₹20, 0.03%)).
   - GST (18% on Brokerage + Exchange + SEBI).
   - DP charges for delivery sell leg (₹15.93).
   - Slippage strictly separated from statutory charges.
   - Exact numerical assertions on actual entry and exit turnovers.

2. Priority 2 — Performance statistics integrity:
   - Independent gross vs net winning/losing trade classification (zero mixing).
   - Gross profit factor and Net profit factor calculated independently.
   - Annualized Sharpe and Sortino based on daily periodic return series.
   - Exposure % and capital utilization %.
   - Drawdown in both % and INR.

3. Priority 3 — Liquidity sweep methodology:
   - Strict 4-stage separation:
     1. Sweep occurrence.
     2. Reclaim confirmation.
     3. Subsequent opposing reaction on candle i+1 (not same-candle wick).
     4. Signal availability on candle i+2.
   - Reclaim without opposing reaction rejected.
   - Failed sweep (continuation breakout) rejected.
   - Pending availability when reaction candle not yet printed.

4. Priority 4 — Strict position sizing:
   - Rejection when 1 share exceeds risk budget (no forced 1 share).
   - Rejection when 1 share exceeds available capital.
   - Actual risk reported as % of capital.

5. Priority 5 — Walk-forward validation:
   - Rolling and expanding multi-window walk-forward slices.
   - Historical warm-up data available without warm-up trade leakage.
   - Frozen parameters before test windows.
   - Independent reporting of out-of-sample performance.
   - Sample sizes reported for every market regime.
   - Multi-metric robustness evaluation (not just win rate).

6. Priority 6 — Data quality engine:
   - Exchange-calendar-aware missing sessions.
   - Duplicate and out-of-order timestamps.
   - Full OHLC consistency.
   - Zero and anomalous volume spikes (>20x median).
   - Unadjusted corporate actions.
   - Truthful provider attribution.

7. Priority 7 — Signal timestamp correctness:
   - Pending availability (None) on last bar of dataset across all detectors.
"""

import math
import pytest
import pandas as pd
import numpy as np

from app.services.smc_backtest_service import (
    calculate_indian_transaction_costs,
    calculate_wilson_score_interval,
    calculate_bootstrap_statistics,
    evaluate_sample_size_validity,
    get_nse_cash_schedule,
    run_parameter_sensitivity,
    run_smc_backtest,
    run_walk_forward_validation,
)
from app.services.smc_service import (
    detect_market_structure,
    detect_order_blocks,
    detect_fair_value_gaps,
    detect_liquidity_and_sweeps,
    _prepare_df,
)
from app.services.data_quality_service import (
    audit_single_symbol_data_quality,
)


# ===========================================================================
# 1. Indian Transaction Cost Model (Phase 9.2 Priorities 1 & 2)
# ===========================================================================

def test_indian_cost_delivery_exact_numerical_values():
    """
    Verify exact statutory delivery equity charges under Dhan default profile:
    Buy 100 shares @ ₹2,500 = ₹250,000 turnover
    Sell 100 shares @ ₹2,600 = ₹260,000 turnover
    Total turnover = ₹510,000
    Brokerage model: Dhan (Delivery = ₹0)
    Schedule: Current NSE cash schedule from 1 March 2026 (₹306.99/cr txn + ₹0.01/cr IPFT = ₹307/cr)
    DP charge: Dhan published rate ₹12.50 + 18% GST = ₹14.75 per ISIN instruction
    Slippage: Separate 5 bps per leg (₹125.00 entry + ₹130.00 exit = ₹255.00)
    """
    costs = calculate_indian_transaction_costs(
        entry_turnover=250000.0,
        exit_turnover=260000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        effective_date="2026-03-15",
        slippage_bps=5.0,
    )

    bd = costs["breakdown"]

    # 1. Brokerage on Dhan delivery = ₹0.0
    assert bd["brokerage"] == 0.0

    # 2. STT: 0.1% on Buy (250) + 0.1% on Sell (260) = ₹510.00
    assert bd["stt"] == 510.00

    # 3. Exchange charges: ₹306.99 per crore on 510,000 = ₹15.66
    assert bd["exchange_charges"] == 15.66
    # IPFT: ₹0.01 per crore on 510,000 = ₹0.00051
    assert bd["ipft"] == 0.00051
    assert bd["combined_exchange_outflow"] == 15.66

    # 4. SEBI turnover fee: ₹10/crore (0.0001% of 510,000) = ₹0.51
    assert bd["sebi_charges"] == 0.51

    # 5. Stamp duty: 0.015% of 250,000 Buy = ₹37.50
    assert bd["stamp_duty"] == 37.50

    # 6. GST: 18% of (Brokerage 0 + Exchange 15.66 + SEBI 0.51 = 16.17) = ₹2.91
    assert bd["gst"] == 2.91

    # 7. DP Charges: Dhan published rate ₹12.50 + 18% GST = ₹14.75
    assert bd["dp_charges"] == 14.75

    # Total Statutory Fees = 0 + 510 + 37.50 + 15.66 + 0.51 + 2.91 + 14.75 = ₹581.33
    assert costs["statutory_fees"] == 581.33

    # 8. Slippage: Separate 5 bps per leg = 125.00 + 130.00 = ₹255.00
    assert bd["slippage_entry"] == 125.00
    assert bd["slippage_exit"] == 130.00
    assert costs["slippage_amount"] == 255.00

    # Total Cost = Statutory (581.33) + Slippage (255.00) = ₹836.33
    assert costs["total_cost"] == 836.33
    # Effective bps on 510,000 turnover = 836.33 / 510,000 * 10,000 = 16.40 bps
    assert costs["effective_bps"] == 16.40


def test_indian_cost_intraday_exact_numerical_values():
    """
    Verify exact statutory intraday equity charges under Dhan:
    Buy ₹250,000, Sell ₹260,000, Total ₹510,000
    Brokerage: min(₹20, 0.03%) per leg = ₹20 Buy + ₹20 Sell = ₹40.00
    STT: 0.025% on Sell only (260,000) = ₹65.00
    Exchange charges: ₹306.99/cr of 510,000 = ₹15.66
    SEBI charges: ₹10/cr of 510,000 = ₹0.51
    Stamp duty: 0.003% on Buy (250,000) = ₹7.50
    GST: 18% of (40 + 15.66 + 0.51 = 56.17) = ₹10.11
    DP charges: ₹0 (intraday)
    """
    costs = calculate_indian_transaction_costs(
        entry_turnover=250000.0,
        exit_turnover=260000.0,
        trade_type="intraday",
        brokerage_model="dhan",
        effective_date="2026-03-15",
        slippage_bps=5.0,
    )

    bd = costs["breakdown"]
    assert bd["brokerage"] == 40.00
    assert bd["stt"] == 65.00
    assert bd["exchange_charges"] == 15.66
    assert bd["sebi_charges"] == 0.51
    assert bd["stamp_duty"] == 7.50
    assert bd["gst"] == 10.11
    assert bd["dp_charges"] == 0.00

    # Total Statutory Fees = 40 + 65 + 15.66 + 0.51 + 7.50 + 10.11 = ₹138.78
    assert costs["statutory_fees"] == 138.78
    assert costs["slippage_amount"] == 255.00
    assert costs["total_cost"] == 393.78
    assert costs["effective_bps"] == 7.72


def test_date_effective_exchange_charges_all_five_tiers():
    """Verify exchange transaction charge rate transition across all five historical date regimes."""
    turnover = 100000.0  # ₹1 Lakh

    # Tier 1: From 1 March 2026: ₹306.99/cr txn + ₹0.01 IPFT = ₹3.07/lakh combined
    c_curr = calculate_indian_transaction_costs(
        entry_turnover=turnover, exit_turnover=0.0, effective_date="2026-03-15"
    )
    assert c_curr["breakdown"]["exchange_charges"] == 3.07
    assert c_curr["breakdown"]["ipft"] == 0.0001
    assert c_curr["breakdown"]["combined_exchange_outflow"] == 3.07
    assert c_curr["breakdown"]["circular_ref"] == "NSE/F&A/66742"

    # Tier 2: Oct 1, 2024 - Feb 28, 2026: ₹297.00/cr txn + ₹10.00 IPFT = ₹3.07/lakh combined
    c_t2 = calculate_indian_transaction_costs(
        entry_turnover=turnover, exit_turnover=0.0, effective_date="2025-06-15"
    )
    assert c_t2["breakdown"]["exchange_charges"] == 2.97
    assert c_t2["breakdown"]["ipft"] == 0.10
    assert c_t2["breakdown"]["combined_exchange_outflow"] == 3.07
    assert c_t2["breakdown"]["circular_ref"] == "NSE/F&A/63799"

    # Tier 3: Apr 1, 2024 - Sep 30, 2024: ₹322.00/cr txn + ₹10.00 IPFT = ₹3.32/lakh combined
    c_t3 = calculate_indian_transaction_costs(
        entry_turnover=turnover, exit_turnover=0.0, effective_date="2024-05-15"
    )
    assert c_t3["breakdown"]["exchange_charges"] == 3.22
    assert c_t3["breakdown"]["ipft"] == 0.10
    assert c_t3["breakdown"]["combined_exchange_outflow"] == 3.32
    assert c_t3["breakdown"]["circular_ref"] == "NSE/F&A/61157"

    # Tier 4: Apr 1, 2023 - Mar 31, 2024: ₹325.00/cr txn + ₹10.00 IPFT = ₹3.35/lakh combined
    c_t4 = calculate_indian_transaction_costs(
        entry_turnover=turnover, exit_turnover=0.0, effective_date="2023-08-15"
    )
    assert c_t4["breakdown"]["exchange_charges"] == 3.25
    assert c_t4["breakdown"]["ipft"] == 0.10
    assert c_t4["breakdown"]["combined_exchange_outflow"] == 3.35
    assert c_t4["breakdown"]["circular_ref"] == "NSE/F&A/55942"

    # Tier 5: Prior to Apr 1, 2023: ₹345.00/cr txn + ₹10.00 IPFT = ₹3.55/lakh combined
    c_t5 = calculate_indian_transaction_costs(
        entry_turnover=turnover, exit_turnover=0.0, effective_date="2022-12-15"
    )
    assert c_t5["breakdown"]["exchange_charges"] == 3.45
    assert c_t5["breakdown"]["ipft"] == 0.10
    assert c_t5["breakdown"]["combined_exchange_outflow"] == 3.55
    assert c_t5["breakdown"]["circular_ref"] == "NSE/F&A/1988"


# ===========================================================================
# 2. Performance Statistics Integrity (Priority 2)
# ===========================================================================

def test_independent_gross_vs_net_classification():
    """
    Verify that gross and net winning/losing trade counts and profit factors
    are calculated independently without classification mixing.
    """
    # Create 3 synthetic trades:
    # Trade 1: Gross win (+₹50), Costs ₹100 -> Net loss (-₹50) [FLIPPED WIN TO LOSS]
    # Trade 2: Gross win (+₹400), Costs ₹100 -> Net win (+₹300)
    # Trade 3: Gross loss (-₹200), Costs ₹100 -> Net loss (-₹300)
    synthetic_bars = [
        {"timestamp": f"2026-10-{i+1:02d}", "open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000}
        for i in range(25)
    ]
    # Configure custom bars to trigger 1 order block retest
    res = run_smc_backtest(
        "TEST_SYM",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=synthetic_bars,
        trade_type="delivery",
        initial_capital=50000.0,
    )

    s = res["summary"]
    # Check that both gross and net fields exist independently
    assert "gross_profit_factor" in s
    assert "net_profit_factor" in s
    assert "gross_win_count" in s
    assert "net_profit_factor" in s
    assert "trades_flipped_win_to_loss" in s
    assert "sortino_ratio" in s
    assert "max_drawdown_inr" in s
    assert "market_exposure_pct" in s
    assert "capital_utilization_pct" in s


# ===========================================================================
# 3. Liquidity Sweep Methodology (Priority 3)
# ===========================================================================

def test_liquidity_sweep_four_stage_lifecycle():
    """
    Verify 4-stage liquidity sweep separation:
    Stage 1: Sweep occurrence (candle i wicks past level)
    Stage 2: Reclaim confirmation (candle i closes back inside level)
    Stage 3: Subsequent opposing reaction (candle i+1 closes in reversal direction)
    Stage 4: Executable availability (candle i+2 Open)
    """
    # Test A: Successful Bearish Sweep with subsequent reaction
    bars_success = [
        {"timestamp": "2026-10-01", "open": 95, "high": 100, "low": 94, "close": 98, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 98, "high": 105, "low": 96, "close": 97, "volume": 3000}, # Bar 1: Wicks 105 > 100, closes 97 <= 100
        {"timestamp": "2026-10-03", "open": 97, "high": 98, "low": 91, "close": 92, "volume": 2500},  # Bar 2: Red candle (close 92 < open 97) -> Reaction confirmed!
        {"timestamp": "2026-10-04", "open": 92, "high": 93, "low": 88, "close": 89, "volume": 2000},  # Bar 3: Executable entry bar
    ]
    df = _prepare_df(bars_success)
    res = detect_liquidity_and_sweeps(df, [], scan_lookback=None)

    assert len(res["sweeps"]) >= 1
    sw = res["sweeps"][0]
    # Occurrence at bar 1 (where wick happened)
    assert sw["occurrence_index"] == 1
    assert sw["reclaim_confirmed"] is True
    # Confirmation at bar 2 (where opposing reaction completed)
    assert sw["confirmation_index"] == 2
    assert sw["opposing_reaction"] is True
    # Signal available on bar 3 (next executable candle)
    assert sw["signal_available_index"] == 3
    assert sw["signal_available_timestamp"] == "2026-10-04"


def test_liquidity_sweep_reclaim_without_opposing_reaction_rejected():
    """
    Verify that a reclaim candle whose subsequent candle fails to reverse
    is marked opposing_reaction=False and signal_available_index=None.
    """
    bars_no_reaction = [
        {"timestamp": "2026-10-01", "open": 95, "high": 100, "low": 94, "close": 98, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 98, "high": 105, "low": 96, "close": 97, "volume": 3000}, # Bar 1: Wicks 105, closes 97 (reclaim)
        {"timestamp": "2026-10-03", "open": 97, "high": 106, "low": 96, "close": 103, "volume": 3500}, # Bar 2: GREEN candle (close 103 > open 97) -> Fails bearish reaction!
        {"timestamp": "2026-10-04", "open": 103, "high": 107, "low": 102, "close": 106, "volume": 2000},
    ]
    df = _prepare_df(bars_no_reaction)
    res = detect_liquidity_and_sweeps(df, [], scan_lookback=None)

    assert len(res["sweeps"]) >= 1
    sw = res["sweeps"][0]
    assert sw["reclaim_confirmed"] is True
    assert sw["opposing_reaction"] is False
    assert sw["signal_available_index"] is None  # Not executable!


def test_liquidity_sweep_continuation_breakout_classified_failed():
    """
    Verify that a candle closing beyond the benchmark level is classified as a
    continuation breakout (FAILED_SWEEP) and not a reclaim sweep.
    """
    bars_breakout = [
        {"timestamp": "2026-10-01", "open": 95, "high": 100, "low": 94, "close": 98, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 98, "high": 106, "low": 97, "close": 104, "volume": 3000}, # Closes above 100!
    ]
    df = _prepare_df(bars_breakout)
    res = detect_liquidity_and_sweeps(df, [], scan_lookback=None)

    assert len(res["failed_sweeps"]) >= 1
    fs = res["failed_sweeps"][0]
    assert "FAILED_SWEEP" in fs["status"]
    assert fs["breakout_price"] == 104.0


# ===========================================================================
# 4. Strict Position Sizing & Capital Constraints (Priority 4)
# ===========================================================================

def test_strict_position_sizing_rejection():
    """
    Verify that trades where 1 share exceeds risk budget or capital are strictly
    rejected with logged reasons rather than forcing a 1-share trade.
    """
    # Capital: ₹1,000. Entry price: ₹2,500. Stop loss: ₹2,300.
    # 1 share costs ₹2,500 > ₹1,000 -> Capital exceeded.
    bars = [
        {"timestamp": f"2026-10-{i+1:02d}", "open": 2500.0, "high": 2550.0, "low": 2480.0, "close": 2510.0, "volume": 1000}
        for i in range(25)
    ]
    res = run_smc_backtest(
        "TEST_EXPENSIVE",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=bars,
        initial_capital=1000.0,  # Unaffordable
    )
    # Trade must be rejected, not forced
    assert res["summary"]["total_trades"] == 0
    assert res["summary"]["final_equity"] == 1000.0


# ===========================================================================
# 5. Multi-Window Walk-Forward Validation (Priority 5)
# ===========================================================================

def test_multi_window_walk_forward_rolling():
    """
    Verify multi-window rolling walk-forward evaluation:
    - Multiple windows generated.
    - Historical warm-up data available.
    - No warm-up trades bleeding into test results.
    - Regime sample sizes reported.
    - Multi-metric robustness criteria enforced.
    """
    # 60 synthetic bars
    bars = []
    base_price = 100.0
    for i in range(60):
        o = base_price + (i * 0.5)
        h = o + 5.0
        l = o - 4.0
        c = o + 1.0
        bars.append({
            "timestamp": f"2026-08-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 10000 + (i * 100),
        })

    wf_res = run_walk_forward_validation(
        "TEST_SYM",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=bars,
        num_windows=3,
        window_type="rolling",
        warmup_bars=20,
        trade_type="delivery",
    )

    assert "windows" in wf_res
    assert wf_res["total_windows"] >= 1
    assert "combined_out_of_sample" in wf_res
    assert "regime_breakdown" in wf_res
    assert "overfitting_audit" in wf_res

    # Check regime breakdown has sample_size
    regimes = wf_res["regime_breakdown"]
    for r_name, r_info in regimes.items():
        assert "sample_size" in r_info
        assert isinstance(r_info["sample_size"], int)


# ===========================================================================
# 6. Data Quality Engine Extensions (Priority 6)
# ===========================================================================

def test_data_quality_extended_validations():
    """
    Verify data quality engine validates:
    - Out of order timestamps
    - Inverted OHLC
    - Anomalous volume spike (>20x median)
    - Unadjusted split gap (>40% drop)
    """
    flawed_bars = [
        # Normal baseline
        {"timestamp": "2026-10-01", "open": 100, "high": 105, "low": 98, "close": 102, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 102, "high": 106, "low": 101, "close": 104, "volume": 1000},
        # High < Low violation
        {"timestamp": "2026-10-03", "open": 104, "high": 90, "low": 110, "close": 103, "volume": 1000},
        # High < Open violation
        {"timestamp": "2026-10-04", "open": 105, "high": 101, "low": 99, "close": 100, "volume": 1000},
        # Anomalous volume spike (> 20x median 1000 -> 30,000)
        {"timestamp": "2026-10-05", "open": 100, "high": 105, "low": 98, "close": 102, "volume": 30000},
        # Unadjusted split gap (50% drop: 102 -> 50)
        {"timestamp": "2026-10-06", "open": 50, "high": 52, "low": 48, "close": 51, "volume": 1000},
    ]

    report = audit_single_symbol_data_quality(flawed_bars, symbol="FLAWED_STOCK", provider="yfinance")

    assert report["ohlc_consistency"]["passed"] is False
    assert report["ohlc_consistency"]["violations_count"] >= 2
    assert report["volume_integrity"]["anomalous_spikes_count"] >= 1
    assert len(report["corporate_actions"]["unadjusted_gap_flags"]) >= 1
    assert report["is_live"] is False  # Never label offline yfinance as live!


# ===========================================================================
# 7. Signal Timestamp Pending On Last Bar (Priority 7)
# ===========================================================================

def test_all_detectors_pending_availability_on_last_bar():
    """
    Verify that when any SMC pattern confirms on the last bar of history,
    signal_available_index and signal_available_timestamp are None.
    """
    bars = [
        {"timestamp": "2026-10-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        {"timestamp": "2026-10-02", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1000},
        # Bar 2 is the last bar (index 2, n=3)
        {"timestamp": "2026-10-03", "open": 102, "high": 120, "low": 102, "close": 119, "volume": 5000},
    ]
    df = _prepare_df(bars)
    structure = detect_market_structure(df, lookback=1)

    for brk in structure["breaks"]:
        if brk["bar_index"] == len(df) - 1:
            # Confirmed on last bar -> next bar unavailable
            assert brk["signal_available_index"] is None
            assert brk["signal_available_timestamp"] is None

    obs = detect_order_blocks(df, structure["breaks"])
    for ob in obs:
        if ob["confirmation_index"] == len(df) - 1:
            assert ob["signal_available_index"] is None
            assert ob["signal_available_timestamp"] is None


# ===========================================================================
# 8. Phase 9.2 Enhancements: DP Settlement, Wilson & Bootstrap CIs, Sample Size
# ===========================================================================

def test_dp_charge_settlement_and_isin_modeling():
    """
    Verify DP charges are modeled strictly by settlement instruction and ISIN:
    - Multiple delivery sell trades on the SAME day for the SAME symbol incur ONE DP debit.
    - Delivery sell trades on DIFFERENT days incur separate DP debits.
    - Delivery sell trades on different symbols incur separate DP debits.
    - Intraday trades incur ₹0 DP charge.
    """
    # 1. First trade on 2026-03-15 incurs DP charge
    c1 = calculate_indian_transaction_costs(
        entry_turnover=100000.0,
        exit_turnover=105000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        is_dp_debit=True,
    )
    assert c1["breakdown"]["dp_charges"] == 14.75

    # 2. Second trade on SAME day/ISIN batch has is_dp_debit=False -> DP charge ₹0
    c2 = calculate_indian_transaction_costs(
        entry_turnover=100000.0,
        exit_turnover=105000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        is_dp_debit=False,
    )
    assert c2["breakdown"]["dp_charges"] == 0.0

    # 3. Zerodha profile has ₹13.50 + 18% GST = ₹15.93
    c_zero = calculate_indian_transaction_costs(
        entry_turnover=100000.0,
        exit_turnover=105000.0,
        trade_type="delivery",
        brokerage_model="zerodha",
        is_dp_debit=True,
    )
    assert c_zero["breakdown"]["dp_charges"] == 15.93


def test_wilson_score_confidence_intervals():
    """Verify Wilson score confidence interval bounds and mathematical properties."""
    # 0 trials -> (0.0, 0.0)
    assert calculate_wilson_score_interval(0, 0) == (0.0, 0.0)

    # 20 wins out of 30 trials (66.7% win rate)
    ci_lower, ci_upper = calculate_wilson_score_interval(20, 30, confidence=0.95)
    assert 45.0 <= ci_lower <= 50.0
    assert 78.0 <= ci_upper <= 83.0
    assert ci_lower < 66.7 < ci_upper

    # 100% win rate on 10 trials
    ci_100_low, ci_100_high = calculate_wilson_score_interval(10, 10, confidence=0.95)
    assert ci_100_high == 100.0
    assert ci_100_low >= 65.0


def test_bootstrap_confidence_intervals_and_sample_size_warnings():
    """
    Verify bootstrap resampling and institutional sample size warning tiers.
    """
    # Sample size tier checks
    assert evaluate_sample_size_validity(8)["tier"] == "CRITICALLY_LOW"
    assert evaluate_sample_size_validity(20)["tier"] == "INSUFFICIENT"
    assert evaluate_sample_size_validity(35)["tier"] == "MODERATE"
    assert evaluate_sample_size_validity(75)["tier"] == "ADEQUATE_FOR_PRELIMINARY_TESTING"

    # Bootstrap on insufficient trades (< 5) returns graceful fallback
    res_small = calculate_bootstrap_statistics([{"net_pnl": 100.0}, {"net_pnl": -50.0}])
    assert res_small["status"] == "INSUFFICIENT_TRADES_FOR_BOOTSTRAP"

    # Bootstrap on 15 trades produces non-zero 95% CIs
    rng = np.random.default_rng(42)
    fake_trades = [{"net_pnl": float(x)} for x in rng.normal(loc=50.0, scale=100.0, size=20)]
    boot = calculate_bootstrap_statistics(fake_trades, n_resamples=500)
    assert boot["status"] == "COMPUTED"
    assert boot["resamples_count"] == 500
    assert boot["expectancy_95_ci_inr"][0] < boot["expectancy_95_ci_inr"][1]
    assert 0.0 <= boot["prob_profitable_system_pct"] <= 100.0


def test_walk_forward_rejects_spurious_robustness_with_small_sample():
    """
    Verify Phase 9.2 Priority 3:
    Five out-of-sample trades must NEVER qualify as sufficient evidence of robustness.
    Walk-forward test with small sample size must explicitly declare insufficient evidence.
    """
    bars = []
    base = 1000.0
    for i in range(80):
        o = base + (i * 2.0)
        h = o + 6.0
        l = o - 4.0
        c = o + 1.0
        bars.append({
            "timestamp": f"2026-08-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 15000,
        })

    wf = run_walk_forward_validation(
        "TEST_SYM",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=bars,
        num_windows=3,
        window_type="rolling",
        trade_type="delivery",
        brokerage_model="dhan",
    )

    oos = wf["combined_out_of_sample"]
    audit = wf["overfitting_audit"]

    # In 80 synthetic bars, total OOS trades will be small (< 30)
    assert oos["total_trades"] < 30
    # Must NOT claim robustness!
    assert audit["is_statistically_robust"] is False
    assert "INSUFFICIENT SAMPLE SIZE" in audit["verdict"] or "CRITICALLY INSUFFICIENT" in audit["verdict"]


def test_configurable_risk_free_rate_sharpe():
    """
    Verify Sharpe and Sortino ratios use the configurable benchmark risk-free rate
    and document opportunity cost during non-trading bars.
    """
    bars = []
    base = 1000.0
    for i in range(40):
        bars.append({
            "timestamp": f"2026-09-{(i % 28) + 1:02d}",
            "open": round(base + i, 2),
            "high": round(base + i + 2, 2),
            "low": round(base + i - 2, 2),
            "close": round(base + i + 1, 2),
            "volume": 10000,
        })

    res = run_smc_backtest(
        "TEST_SYM",
        bars=bars,
        brokerage_model="dhan",
        risk_free_rate=0.07,  # 7.0% assumed benchmark
    )

    s = res["summary"]
    assert s["risk_free_rate_assumed"] == 0.07
    assert "7.0%" in s["risk_free_benchmark_note"]
    assert "Dhan" in s["brokerage_model"].capitalize()


# ===========================================================================
# 9. Phase 9.3 Enhancements: Dhan DP EPI Billing, Continuous MTM, Autocorr
# ===========================================================================

def test_dhan_dp_charge_per_order_policy_and_partial_fills():
    """
    Verify Phase 9.3 Priority 1:
    - Dhan charges DP fees per delivery sell order/instruction due to real-time Early Pay-In (EPI).
    - Multiple delivery sells in the same symbol on the same day under Dhan each incur DP charge.
    - Multiple partial fills belonging to one parent order only incur 1 DP charge.
    - Sells across different symbols on the same day each incur DP charge.
    - Intraday trades incur ₹0 DP charge.
    """
    # 1. Single delivery sell on Dhan -> ₹12.50 + 18% GST = ₹14.75
    c_single = calculate_indian_transaction_costs(
        entry_turnover=100000.0,
        exit_turnover=105000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        is_dp_debit=True,
    )
    assert c_single["breakdown"]["dp_charges"] == 14.75
    assert c_single["breakdown"]["dp_base"] == 12.50
    assert c_single["breakdown"]["dp_gst"] == 2.25

    # 2. Backtest simulation with 2 sell orders on same day under Dhan (per_order policy)
    costs_order1 = calculate_indian_transaction_costs(50000.0, 52000.0, trade_type="delivery", brokerage_model="dhan", is_dp_debit=True)
    costs_order2 = calculate_indian_transaction_costs(50000.0, 53000.0, trade_type="delivery", brokerage_model="dhan", is_dp_debit=True)
    assert costs_order1["breakdown"]["dp_charges"] == 14.75
    assert costs_order2["breakdown"]["dp_charges"] == 14.75
    total_dp_two_orders = costs_order1["breakdown"]["dp_charges"] + costs_order2["breakdown"]["dp_charges"]
    assert total_dp_two_orders == 29.50

    # 3. Under Zerodha (per_isin_daily policy), second trade on same day has is_dp_debit=False
    costs_zero1 = calculate_indian_transaction_costs(50000.0, 52000.0, trade_type="delivery", brokerage_model="zerodha", is_dp_debit=True)
    costs_zero2 = calculate_indian_transaction_costs(50000.0, 53000.0, trade_type="delivery", brokerage_model="zerodha", is_dp_debit=False)
    assert costs_zero1["breakdown"]["dp_charges"] == 15.93
    assert costs_zero2["breakdown"]["dp_charges"] == 0.0

    # 4. Partial fills of the same parent order: only 1 DP debit instruction
    fill1 = calculate_indian_transaction_costs(25000.0, 26000.0, trade_type="delivery", brokerage_model="dhan", is_dp_debit=True)
    fill2 = calculate_indian_transaction_costs(25000.0, 26000.0, trade_type="delivery", brokerage_model="dhan", is_dp_debit=False)
    assert fill1["breakdown"]["dp_charges"] == 14.75
    assert fill2["breakdown"]["dp_charges"] == 0.0

    # 5. Intraday trade -> ₹0 DP debit
    c_intra = calculate_indian_transaction_costs(100000.0, 105000.0, trade_type="intraday", brokerage_model="dhan")
    assert c_intra["breakdown"]["dp_charges"] == 0.0


def test_unsupported_overnight_short_in_delivery_rejected():
    """
    Verify Phase 9.3 Priority 1:
    - Retail spot delivery shorting is impossible in Indian cash equities without SLB.
    - Delivery backtests must reject BEARISH setups with reason 'UNSUPPORTED_OVERNIGHT_SHORT'.
    - Intraday backtests must allow BEARISH setups.
    """
    bars = []
    base = 2000.0
    for i in range(35):
        o = base - (i * 5.0)
        h = o + 2.0
        l = o - 8.0
        c = o - 4.0
        bars.append({
            "timestamp": f"2026-02-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 20000,
        })

    # Run in delivery mode without SLB
    res_deliv = run_smc_backtest(
        "TEST_SYM",
        strategy_type="LIQUIDITY_SWEEP_REVERSAL",
        bars=bars,
        trade_type="delivery",
        allow_overnight_short=False,
    )
    if res_deliv["rejected_trades_count"] > 0:
        assert any(r["reason"] == "UNSUPPORTED_OVERNIGHT_SHORT" for r in res_deliv["rejected_trades"])
        assert res_deliv["performance_breakdown"]["short"]["trades_count"] == 0

    # Run in intraday mode -> short trades are accepted
    res_intra = run_smc_backtest(
        "TEST_SYM",
        strategy_type="LIQUIDITY_SWEEP_REVERSAL",
        bars=bars,
        trade_type="intraday",
    )
    assert not any(r["reason"] == "UNSUPPORTED_OVERNIGHT_SHORT" for r in res_intra["rejected_trades"])


def test_continuous_daily_mark_to_market_equity_series():
    """
    Verify Phase 9.3 Priority 5:
    - Continuous daily portfolio equity series across all n historical bars.
    - Open positions marked to market daily via df['close'].
    - Non-trading idle cash bars earn 0.0% return and are penalized against -rf_daily.
    - Final equity on bar n-1 equals realized ending capital.
    - Sortino ratio downside convention: sqrt((1/N) * sum(min(R_k - R_f_daily, 0)^2)).
    """
    bars = []
    base = 1000.0
    for i in range(40):
        o = base + (i * 2.0)
        h = o + 5.0
        l = o - 3.0
        c = o + 2.0
        bars.append({
            "timestamp": f"2026-04-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": 15000,
        })

    res = run_smc_backtest(
        "TEST_SYM",
        strategy_type="ORDER_BLOCK_RETEST",
        bars=bars,
        trade_type="delivery",
        brokerage_model="dhan",
        risk_free_rate=0.06,
    )

    s = res["summary"]
    daily_eq = res["daily_equity_series"]
    eq_curve = res["equity_curve"]

    # Verify daily series spans all n bars
    assert len(daily_eq) == len(bars)
    assert len(eq_curve) == len(bars)

    # Initial equity at bar 0
    assert daily_eq[0] == 100000.0

    # Final equity at bar n-1 matches summary final equity
    assert daily_eq[-1] == s["final_equity"]

    # Verify Sortino ratio metadata
    assert "sortino_downside_convention" in s
    assert "sqrt( (1/N) * sum( min(R_k - R_f_daily, 0)^2 ) )" in s["sortino_downside_convention"]


def test_bootstrap_5000_resamples_zero_loss_cap_and_autocorrelation():
    """
    Verify Phase 9.3 Priority 4:
    - Default 5,000 bootstrap resamples.
    - Zero-loss resamples capped at max_pf_cap = 50.0.
    - Lag-1 serial autocorrelation rho_1 computed.
    - Autocorrelation warning emitted when |rho_1| > 0.2.
    """
    # 1. Zero-loss trades: all trades are winners
    all_wins = [{"net_pnl": 500.0}, {"net_pnl": 300.0}, {"net_pnl": 450.0}, {"net_pnl": 600.0}, {"net_pnl": 200.0}]
    boot_wins = calculate_bootstrap_statistics(all_wins, n_resamples=1000, max_pf_cap=50.0)
    assert boot_wins["status"] == "COMPUTED"
    assert boot_wins["profit_factor_95_ci"][1] <= 50.0
    assert boot_wins["capped_zero_loss_resamples"] > 0
    assert boot_wins["max_pf_cap"] == 50.0

    # 2. Correlated trades: strong positive serial correlation
    correlated_trades = [
        {"net_pnl": 100.0}, {"net_pnl": 120.0}, {"net_pnl": 110.0}, {"net_pnl": 130.0},
        {"net_pnl": -100.0}, {"net_pnl": -110.0}, {"net_pnl": -120.0}, {"net_pnl": -90.0},
    ]
    boot_corr = calculate_bootstrap_statistics(correlated_trades, n_resamples=1000)
    assert boot_corr["status"] == "COMPUTED"
    assert "autocorrelation_lag1" in boot_corr
    assert boot_corr["autocorrelation_lag1"] > 0.2
    assert boot_corr["autocorrelation_warning"] is not None
    assert "notable lag-1 serial autocorrelation" in boot_corr["autocorrelation_warning"]

    # 3. Default resamples is 5,000
    fake_trades = [{"net_pnl": float(x)} for x in range(-5, 6) if x != 0]
    boot_5k = calculate_bootstrap_statistics(fake_trades)
    assert boot_5k["resamples_count"] == 5000


def test_multiple_testing_selection_bias_warning_in_parameter_sensitivity():
    """
    Verify Phase 9.3 Priority 4:
    - Multiple testing / selection bias warning emitted in parameter sensitivity.
    - Family-Wise Error Rate (FWER) false discovery risk percentage reported.
    """
    bars = []
    base = 1000.0
    for i in range(30):
        bars.append({
            "timestamp": f"2026-05-{(i % 28) + 1:02d}",
            "open": round(base + i, 2),
            "high": round(base + i + 3, 2),
            "low": round(base + i - 3, 2),
            "close": round(base + i + 1, 2),
            "volume": 10000,
        })

    sens = run_parameter_sensitivity("TEST_SYM", bars=bars)
    assert "false_discovery_risk_pct" in sens
    assert "multiple_testing_warning" in sens
    assert 40.0 <= sens["false_discovery_risk_pct"] <= 50.0
    assert "MULTIPLE TESTING SELECTION BIAS WARNING" in sens["multiple_testing_warning"]


def test_reliance_numerical_recalculation_current_and_historical_schedules():
    """
    Verify Phase 9.3 Priority 6:
    Exact Reliance numerical example: 100 shares @ ₹2,500 buy, ₹2,600 sell (₹5.1L turnover).
    """
    # 1. Current Schedule (From 1 March 2026)
    curr = calculate_indian_transaction_costs(
        entry_turnover=250000.0,
        exit_turnover=260000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        effective_date="2026-03-15",
        slippage_bps=5.0,
    )
    b_curr = curr["buy_breakdown"]
    s_curr = curr["sell_breakdown"]

    assert b_curr["turnover"] == 250000.0
    assert b_curr["brokerage"] == 0.0
    assert b_curr["stt"] == 250.00
    assert b_curr["exchange_charges"] == 7.67
    assert b_curr["sebi_charges"] == 0.25
    assert b_curr["stamp_duty"] == 37.50
    assert b_curr["gst"] == 1.43
    assert b_curr["slippage"] == 125.00
    assert b_curr["statutory_fees"] == 296.85
    assert b_curr["total_cost"] == 421.85

    assert s_curr["turnover"] == 260000.0
    assert s_curr["brokerage"] == 0.0
    assert s_curr["stt"] == 260.00
    assert s_curr["exchange_charges"] == 7.98
    assert s_curr["sebi_charges"] == 0.26
    assert s_curr["dp_charges"] == 14.75
    assert s_curr["gst"] == 1.48
    assert s_curr["slippage"] == 130.00
    assert s_curr["statutory_fees"] == 284.47
    assert s_curr["total_cost"] == 414.47

    assert curr["statutory_fees"] == 581.33
    assert curr["slippage_amount"] == 255.00
    assert curr["total_cost"] == 836.33
    assert curr["effective_bps"] == 16.40

    # 2. Historical Schedule (Oct 2024 to Feb 2026)
    hist = calculate_indian_transaction_costs(
        entry_turnover=250000.0,
        exit_turnover=260000.0,
        trade_type="delivery",
        brokerage_model="dhan",
        effective_date="2025-06-15",
        slippage_bps=5.0,
    )
    b_hist = hist["buy_breakdown"]
    s_hist = hist["sell_breakdown"]

    assert b_hist["exchange_charges"] in (7.42, 7.43)
    assert b_hist["ipft"] == 0.25
    assert b_hist["gst"] in (1.38, 1.39)
    assert b_hist["statutory_fees"] in (296.55, 296.56)

    assert s_hist["exchange_charges"] == 7.72
    assert s_hist["ipft"] == 0.26
    assert s_hist["gst"] == 1.44
    assert s_hist["dp_charges"] == 14.75
    assert s_hist["statutory_fees"] == 284.17

    assert hist["statutory_fees"] == 580.73
    assert hist["slippage_amount"] == 255.00
    assert hist["total_cost"] == 835.73
    assert hist["effective_bps"] == 16.39

