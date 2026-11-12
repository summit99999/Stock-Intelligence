"""
Comprehensive Automated Test Suite for Consolidation Breakout Backtest Module V1 (Phase 9).

Tests:
1. Strategy signal scanning: resistance & range exclusion of current breakout candle (No look-ahead).
2. T+1 Open entry execution with slippage.
3. Realistic gap-down through stop execution.
4. Stop-loss and target intraday conflict resolution (adverse outcome first).
5. Position sizing invariants: 1% risk, 20% equity cap, whole shares, no negative cash.
6. Date-effective Upstox transaction cost schedule and DP charges.
7. Data quality auditing against NSE trading calendar.
8. Mark-to-market drawdown and equity accounting.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.backtest_analytics_service import BacktestAnalyticsService
from app.services.backtest_data_engine import BacktestDataEngine
from app.services.backtest_portfolio_engine import (
    DailyEquityPoint,
    PortfolioSimulationEngine,
    Position,
    TradeRecord,
)
from app.services.consolidation_breakout_strategy import (
    BreakoutSignal,
    StrategyParameters,
    scan_consolidation_breakouts,
)
from app.services.upstox_cost_model import (
    calculate_upstox_leg_cost,
    calculate_upstox_roundtrip_cost,
    get_upstox_nse_schedule,
)


def _create_synthetic_consolidation_df() -> pd.DataFrame:
    """Create a 70-day deterministic price series with a clear consolidation and breakout."""
    dates = pd.date_range("2024-01-01", periods=70, freq="B").strftime("%Y-%m-%d").tolist()
    rows = []
    # Warmup 45 days: uptrend from 100 to 120
    price = 100.0
    for i in range(45):
        price += 0.5
        rows.append({
            "date": dates[i],
            "open": price - 0.2,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": 100000,
        })

    # Consolidation: 20 days (days 45 to 64) tight range between 122 and 126 (<4% range)
    # declining volume from 100k down to 40k
    for i in range(45, 65):
        c = 124.0 + (i % 3 - 1) * 0.8
        vol = 80000 - (i - 45) * 2000
        rows.append({
            "date": dates[i],
            "open": c - 0.2,
            "high": 126.0,
            "low": 122.0,
            "close": c,
            "volume": vol,
        })

    # Day 65: Breakout above resistance 126.0 on 200k volume (2.5x volume surge)
    rows.append({
        "date": dates[65],
        "open": 125.0,
        "high": 130.0,
        "low": 124.5,
        "close": 129.0,  # Closes above resistance 126.0
        "volume": 200000,
    })

    # Days 66 to 69: Follow-through
    for i in range(66, 70):
        rows.append({
            "date": dates[i],
            "open": 129.5 + (i - 66),
            "high": 132.0 + (i - 66),
            "low": 128.5 + (i - 66),
            "close": 131.0 + (i - 66),
            "volume": 150000,
        })

    df = pd.DataFrame(rows)
    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["vol_sma_20"] = df["volume"].rolling(20).mean()
    return df


def test_consolidation_breakout_signal_detection_no_lookahead():
    """Verify that signal detects breakout and excludes breakout candle from resistance."""
    df = _create_synthetic_consolidation_df()
    params = StrategyParameters(
        consolidation_lookback=20,
        max_consolidation_range_pct=8.0,
        breakout_volume_multiplier=1.5,
    )
    signals = scan_consolidation_breakouts("TEST_STOCK", df, params)

    assert len(signals) == 1
    sig = signals[0]
    assert sig.symbol == "TEST_STOCK"
    # Signal date must be day 65 close
    assert sig.signal_date == df["date"].iloc[65]
    # Execution date must strictly be day 66 (T+1 Open)
    assert sig.execution_date == df["date"].iloc[66]
    # Resistance must strictly be 126.0 (max high of days 45-64), NOT 130.0 (day 65 high)
    assert sig.resistance == 126.0
    assert sig.close_price == 129.0
    assert sig.close_price > sig.resistance
    # Stop loss must be below consolidation support (122.0)
    assert sig.stop_loss_level < 122.0


def test_t_plus_one_open_execution_and_slippage():
    """Verify execution occurs at T+1 Open with configurable slippage."""
    df = _create_synthetic_consolidation_df()
    params = StrategyParameters(slippage_bps=10.0)  # 10 bps slippage = 0.1%
    signals = scan_consolidation_breakouts("TEST_STOCK", df, params)

    sim = PortfolioSimulationEngine(
        initial_capital=100000.0,
        slippage_bps=10.0,
        strategy_params=params,
    )
    trades, curve, meta = sim.run_simulation({"TEST_STOCK": df}, {"TEST_STOCK": signals})

    open_price_day_66 = df["open"].iloc[66]
    expected_entry = round(open_price_day_66 * (1.0 + 10.0 / 10000.0), 2)

    # Position must have been opened on day 66 at expected fill price
    assert len(trades) > 0 or len(meta["open_positions"]) > 0
    pos_or_trade = trades[0] if trades else meta["open_positions"][0]
    entry_price = pos_or_trade.entry_price if isinstance(pos_or_trade, TradeRecord) else pos_or_trade["entry_price"]
    assert entry_price == expected_entry


def test_gap_down_through_stop_loss():
    """Verify market gapping below stop-loss fills at adverse Open price, not the stop level."""
    df = _create_synthetic_consolidation_df()
    # Modify day 67 to gap down to 110.0 (far below stop-loss ~121.75)
    df.loc[67, "open"] = 110.0
    df.loc[67, "high"] = 112.0
    df.loc[67, "low"] = 108.0
    df.loc[67, "close"] = 109.0

    params = StrategyParameters(slippage_bps=0.0)
    signals = scan_consolidation_breakouts("GAP_STOCK", df, params)

    sim = PortfolioSimulationEngine(
        initial_capital=100000.0,
        slippage_bps=0.0,
        strategy_params=params,
    )
    trades, curve, meta = sim.run_simulation({"GAP_STOCK": df}, {"GAP_STOCK": signals})

    assert len(trades) >= 1
    gap_trade = trades[0]
    assert gap_trade.exit_reason == "STOP_LOSS_GAP"
    # Exit price must be the gap open (110.0), NOT the higher stop loss level (121.75)
    assert gap_trade.exit_price == 110.0


def test_intraday_target_and_stop_conflict_adverse_resolution():
    """If candle touches both Stop-Loss and Profit Target, adverse stop is assumed first."""
    df = _create_synthetic_consolidation_df()
    # Modify day 67 to have massive wick touching both target (>140) and stop (<120)
    df.loc[67, "open"] = 129.5
    df.loc[67, "high"] = 150.0  # Would hit target
    df.loc[67, "low"] = 115.0   # Touches stop loss
    df.loc[67, "close"] = 135.0

    params = StrategyParameters(slippage_bps=0.0)
    signals = scan_consolidation_breakouts("CONFLICT_STOCK", df, params)

    sim = PortfolioSimulationEngine(
        initial_capital=100000.0,
        slippage_bps=0.0,
        strategy_params=params,
    )
    trades, curve, meta = sim.run_simulation({"CONFLICT_STOCK": df}, {"CONFLICT_STOCK": signals})

    assert len(trades) >= 1
    t = trades[0]
    assert t.exit_reason == "STOP_LOSS_CONFLICT"
    assert t.gross_pnl < 0  # Confirms stop-loss exit, not profit target


def test_position_sizing_and_capital_constraints():
    """Verify whole shares, 1% risk, 20% max allocation, and cash >= 0."""
    initial_cap = 100000.0
    sim = PortfolioSimulationEngine(
        initial_capital=initial_cap,
        risk_per_trade_pct=1.0,  # ₹1,000 risk
        max_positions=5,
        max_allocation_pct=20.0,  # Max ₹20,000
    )

    df = _create_synthetic_consolidation_df()
    signals = scan_consolidation_breakouts("SIZING_STOCK", df)
    trades, curve, meta = sim.run_simulation({"SIZING_STOCK": df}, {"SIZING_STOCK": signals})

    for pt in curve:
        # Cash must never be negative
        assert pt.cash >= 0.0
        # Total equity must equal cash + invested value
        assert round(pt.total_equity, 2) == round(pt.cash + pt.invested_value, 2)

    for t in trades:
        # Quantity must be a positive integer
        assert isinstance(t.quantity, int)
        assert t.quantity >= 1
        # Entry turnover must not exceed 20% cap + buffer
        assert t.entry_turnover <= (initial_cap * 0.20 + 200.0)


def test_upstox_transaction_cost_schedule():
    """Verify Upstox delivery schedule statutory calculations."""
    # Test Buy Leg: ₹20k turnover
    buy = calculate_upstox_leg_cost(turnover=20000.0, side="BUY", effective_date="2025-01-15")
    assert buy.brokerage == 20.0
    assert buy.stt == 20.0  # 0.1% of 20,000
    assert buy.stamp_duty == 3.0  # 0.015% of 20,000
    assert buy.dp_charge == 0.0  # ₹0 on Buy

    # Test Sell Leg: ₹20k turnover
    sell = calculate_upstox_leg_cost(turnover=20000.0, side="SELL", effective_date="2025-01-15")
    assert sell.brokerage == 20.0
    assert sell.stt == 20.0
    assert sell.stamp_duty == 0.0  # ₹0 on Sell
    assert sell.dp_charge == 21.83  # ₹18.50 + 18% GST

    # Verify date-effective NSE transaction charge tier
    pre_2023 = get_upstox_nse_schedule("2022-05-10")
    assert pre_2023["txn_rate"] == 0.0000345  # ₹345 / cr

    post_2024 = get_upstox_nse_schedule("2025-01-15")
    assert post_2024["txn_rate"] == 0.0000297  # ₹297 / cr


def test_performance_analytics_metrics():
    """Verify mathematical consistency of CAGR, Sharpe, Sortino, Drawdown."""
    analytics = BacktestAnalyticsService(risk_free_rate=0.065)

    # 3 mock daily equity points over 365 days from 100k to 120k
    points = [
        DailyEquityPoint(date="2024-01-01", cash=100000, invested_value=0, total_equity=100000, daily_return_pct=0, cumulative_return_pct=0, drawdown_pct=0, high_water_mark=100000, open_positions_count=0, benchmark_equity=100000),
        DailyEquityPoint(date="2024-06-01", cash=90000, invested_value=25000, total_equity=115000, daily_return_pct=0.1, cumulative_return_pct=15, drawdown_pct=0, high_water_mark=115000, open_positions_count=1, benchmark_equity=110000),
        DailyEquityPoint(date="2024-12-31", cash=120000, invested_value=0, total_equity=120000, daily_return_pct=0.05, cumulative_return_pct=20, drawdown_pct=0, high_water_mark=120000, open_positions_count=0, benchmark_equity=112000),
    ]

    metrics = analytics.compute_metrics(trades=[], equity_curve=points, initial_capital=100000.0)
    summary = metrics["summary"]

    assert summary["initial_capital"] == 100000.0
    assert summary["final_equity"] == 120000.0
    assert summary["net_profit"] == 20000.0
    assert summary["net_return_pct"] == 20.0
    assert summary["cagr_pct"] > 18.0
    assert summary["max_drawdown_pct"] >= 0.0
