"""
Backtest Portfolio & Execution Simulation Engine (Phase 4 & 5).

Timeline-synchronized multi-asset simulation engine for Indian cash equities.
Strictly implements:
- T+1 Open entry execution with configurable slippage.
- Realistic gap-down fill at Open (or worse).
- Intraday conflict resolution: adverse stop-loss assumed first if both touched.
- Whole-share risk-based sizing (1% risk of equity, 20% max allocation, max 5 positions).
- Full Upstox equity delivery transaction cost modeling.
- Mark-to-market daily portfolio valuation and drawdown tracking.
- Cash balance invariant: cash >= 0 at all times.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import numpy as np
import pandas as pd

from app.services.consolidation_breakout_strategy import BreakoutSignal, StrategyParameters
from app.services.upstox_cost_model import calculate_upstox_leg_cost, calculate_upstox_roundtrip_cost


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry_price: float
    quantity: int
    stop_loss: float
    target_price: float
    entry_turnover: float
    entry_costs: float
    holding_sessions: int = 0
    highest_price_seen: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradeRecord:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: int
    entry_turnover: float
    exit_turnover: float
    gross_pnl: float
    net_pnl: float
    return_pct: float
    exit_reason: str  # "PROFIT_TARGET", "STOP_LOSS", "STOP_LOSS_GAP", "STOP_LOSS_CONFLICT", "TRAILING_STOP", "MAX_HOLDING_PERIOD", "FORCE_CLOSE"
    holding_days: int
    entry_cost: float
    exit_cost: float
    total_transaction_cost: float
    cost_breakdown: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyEquityPoint:
    date: str
    cash: float
    invested_value: float
    total_equity: float
    daily_return_pct: float
    cumulative_return_pct: float
    drawdown_pct: float
    high_water_mark: float
    open_positions_count: int
    benchmark_equity: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PortfolioSimulationEngine:
    """Multi-asset portfolio simulation engine."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        risk_per_trade_pct: float = 1.0,
        max_positions: int = 5,
        max_allocation_pct: float = 20.0,
        slippage_bps: float = 5.0,
        strategy_params: Optional[StrategyParameters] = None,
    ):
        self.initial_capital = initial_capital
        self.risk_pct = risk_per_trade_pct / 100.0
        self.max_positions = max_positions
        self.max_alloc_pct = max_allocation_pct / 100.0
        self.slippage_bps = slippage_bps
        self.params = strategy_params or StrategyParameters()

    def run_simulation(
        self,
        universe_dfs: Dict[str, pd.DataFrame],
        signals_by_symbol: Dict[str, List[BreakoutSignal]],
        benchmark_df: Optional[pd.DataFrame] = None,
    ) -> Tuple[List[TradeRecord], List[DailyEquityPoint], Dict[str, Any]]:
        """
        Execute timeline-synchronized multi-asset backtest.
        """
        # 1. Build unified chronological master timeline of all available dates
        all_dates: Set[str] = set()
        for df in universe_dfs.values():
            if not df.empty and "date" in df.columns:
                all_dates.update(df["date"].tolist())

        if not all_dates:
            return [], [], {"error": "No trading dates available for simulation."}

        timeline = sorted(list(all_dates))

        # Index dataframes by date for O(1) lookups
        bar_lookups: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for sym, df in universe_dfs.items():
            bar_lookups[sym] = {}
            for _, row in df.iterrows():
                d_str = str(row["date"])[:10]
                bar_lookups[sym][d_str] = {
                    "open": float(row.get("open", 0.0)),
                    "high": float(row.get("high", 0.0)),
                    "low": float(row.get("low", 0.0)),
                    "close": float(row.get("close", 0.0)),
                    "volume": int(row.get("volume", 0)),
                    "sma_20": float(row.get("sma_20", 0.0)),
                }

        # Index benchmark prices by date
        benchmark_prices: Dict[str, float] = {}
        if benchmark_df is not None and not benchmark_df.empty:
            for _, row in benchmark_df.iterrows():
                benchmark_prices[str(row["date"])[:10]] = float(row.get("close", 0.0))

        initial_benchmark_val = None
        for d in timeline:
            if d in benchmark_prices and benchmark_prices[d] > 0:
                initial_benchmark_val = benchmark_prices[d]
                break

        # Group pending buy signals by their execution date
        signals_by_exec_date: Dict[str, List[BreakoutSignal]] = {}
        for sigs in signals_by_symbol.values():
            for s in sigs:
                signals_by_exec_date.setdefault(s.execution_date, []).append(s)

        # Simulation state
        cash = float(self.initial_capital)
        open_positions: Dict[str, Position] = {}
        closed_trades: List[TradeRecord] = []
        equity_curve: List[DailyEquityPoint] = []

        high_water_mark = float(self.initial_capital)
        prev_equity = float(self.initial_capital)

        for date_curr in timeline:
            # -------------------------------------------------------------
            # STEP 1: Process Entries at Market Open
            # -------------------------------------------------------------
            pending_signals = signals_by_exec_date.get(date_curr, [])
            for sig in pending_signals:
                sym = sig.symbol
                # Check if position already open
                if sym in open_positions:
                    continue
                # Check max open positions
                if len(open_positions) >= self.max_positions:
                    break

                sym_bars = bar_lookups.get(sym, {})
                if date_curr not in sym_bars:
                    continue

                open_price_raw = sym_bars[date_curr]["open"]
                if open_price_raw <= 0:
                    continue

                # Entry execution with slippage
                slip_mult = 1.0 + (self.slippage_bps / 10000.0)
                entry_fill_price = round(open_price_raw * slip_mult, 2)

                stop_price = sig.stop_loss_level
                per_share_risk = entry_fill_price - stop_price
                if per_share_risk <= 0.05:  # Require sensible positive risk distance
                    continue

                current_equity = cash + sum(
                    p.quantity * bar_lookups.get(p.symbol, {}).get(date_curr, {}).get("open", p.entry_price)
                    for p in open_positions.values()
                )

                # Risk-based quantity
                risk_inr = current_equity * self.risk_pct
                qty_by_risk = math.floor(risk_inr / per_share_risk)

                # Max allocation cap (e.g. 20% of equity)
                max_capital_for_stock = current_equity * self.max_alloc_pct
                qty_by_cap = math.floor(max_capital_for_stock / entry_fill_price)

                # Available cash constraint
                est_fee_multiplier = 1.002  # ~0.2% allowance for costs
                qty_by_cash = math.floor(cash / (entry_fill_price * est_fee_multiplier))

                final_qty = min(qty_by_risk, qty_by_cap, qty_by_cash)
                if final_qty < 1:
                    continue

                entry_turnover = round(final_qty * entry_fill_price, 2)
                buy_cost = calculate_upstox_leg_cost(
                    turnover=entry_turnover,
                    side="BUY",
                    effective_date=date_curr,
                    slippage_bps=self.slippage_bps,
                )

                total_entry_outflow = entry_turnover + buy_cost.total_cost
                if total_entry_outflow > cash:
                    continue

                cash -= total_entry_outflow

                # Calculate profit target: 2:1 R:R
                target_dist = sig.profit_target_multiple * per_share_risk
                target_price = round(entry_fill_price + target_dist, 2)

                open_positions[sym] = Position(
                    symbol=sym,
                    entry_date=date_curr,
                    entry_price=entry_fill_price,
                    quantity=final_qty,
                    stop_loss=stop_price,
                    target_price=target_price,
                    entry_turnover=entry_turnover,
                    entry_costs=buy_cost.total_cost,
                    holding_sessions=0,
                    highest_price_seen=entry_fill_price,
                )

            # -------------------------------------------------------------
            # STEP 2: Evaluate Exits for Open Positions during session
            # -------------------------------------------------------------
            positions_to_close: List[Tuple[str, float, str]] = []

            for sym, pos in list(open_positions.items()):
                sym_bars = bar_lookups.get(sym, {})
                if date_curr not in sym_bars:
                    continue

                bar = sym_bars[date_curr]
                o_price = bar["open"]
                h_price = bar["high"]
                l_price = bar["low"]
                c_price = bar["close"]
                sma20 = bar["sma_20"]

                pos.holding_sessions += 1
                pos.highest_price_seen = max(pos.highest_price_seen, h_price)

                exit_price = None
                exit_reason = None

                # 1. Gap-down through stop-loss at Open
                if o_price <= pos.stop_loss:
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(o_price * slip_mult, 2)
                    exit_reason = "STOP_LOSS_GAP"

                # 2. Intraday conflict: Both Stop Loss and Target touched
                elif l_price <= pos.stop_loss and h_price >= pos.target_price and self.params.use_profit_target:
                    # Conservative quantitative rule: Assume adverse stop-loss outcome first
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(pos.stop_loss * slip_mult, 2)
                    exit_reason = "STOP_LOSS_CONFLICT"

                # 3. Normal Stop Loss hit intraday
                elif l_price <= pos.stop_loss:
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(pos.stop_loss * slip_mult, 2)
                    exit_reason = "STOP_LOSS"

                # 4. Profit Target reached
                elif self.params.use_profit_target and h_price >= pos.target_price:
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(pos.target_price * slip_mult, 2)
                    exit_reason = "PROFIT_TARGET"

                # 5. Trailing Stop: Close < SMA20 (when position is in profit)
                elif (
                    self.params.use_trailing_stop
                    and pos.holding_sessions >= 3
                    and c_price < sma20
                    and c_price > pos.entry_price
                ):
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(c_price * slip_mult, 2)
                    exit_reason = "TRAILING_STOP"

                # 6. Max Holding Period reached (default 20 sessions)
                elif self.params.use_max_holding_period and pos.holding_sessions >= self.params.max_holding_period_sessions:
                    slip_mult = 1.0 - (self.slippage_bps / 10000.0)
                    exit_price = round(c_price * slip_mult, 2)
                    exit_reason = "MAX_HOLDING_PERIOD"

                if exit_price and exit_reason:
                    positions_to_close.append((sym, exit_price, exit_reason))

            # Execute closures
            for sym, exit_p, reason in positions_to_close:
                pos = open_positions.pop(sym)
                exit_turnover = round(pos.quantity * exit_p, 2)

                roundtrip = calculate_upstox_roundtrip_cost(
                    entry_turnover=pos.entry_turnover,
                    exit_turnover=exit_turnover,
                    entry_date=pos.entry_date,
                    exit_date=date_curr,
                    slippage_bps=self.slippage_bps,
                )

                sell_cost = roundtrip["sell_leg"]["total_cost"]
                net_proceeds = exit_turnover - sell_cost
                cash += net_proceeds

                gross_pnl = round((exit_p - pos.entry_price) * pos.quantity, 2)
                total_cost = roundtrip["total_cost"]
                net_pnl = round(gross_pnl - total_cost, 2)
                ret_pct = round((net_pnl / pos.entry_turnover) * 100.0, 2) if pos.entry_turnover > 0 else 0.0

                closed_trades.append(
                    TradeRecord(
                        symbol=sym,
                        entry_date=pos.entry_date,
                        exit_date=date_curr,
                        entry_price=pos.entry_price,
                        exit_price=exit_p,
                        quantity=pos.quantity,
                        entry_turnover=pos.entry_turnover,
                        exit_turnover=exit_turnover,
                        gross_pnl=gross_pnl,
                        net_pnl=net_pnl,
                        return_pct=ret_pct,
                        exit_reason=reason,
                        holding_days=pos.holding_sessions,
                        entry_cost=roundtrip["buy_leg"]["total_cost"],
                        exit_cost=roundtrip["sell_leg"]["total_cost"],
                        total_transaction_cost=total_cost,
                        cost_breakdown=roundtrip,
                    )
                )

            # -------------------------------------------------------------
            # STEP 3: Mark-to-Market Daily Valuation
            # -------------------------------------------------------------
            invested_val = 0.0
            for p in open_positions.values():
                b = bar_lookups.get(p.symbol, {}).get(date_curr)
                c = b["close"] if b else p.entry_price
                invested_val += p.quantity * c

            total_equity = round(cash + invested_val, 2)
            high_water_mark = max(high_water_mark, total_equity)

            dd_pct = round(((total_equity - high_water_mark) / high_water_mark) * 100.0, 2)
            daily_ret = round(((total_equity - prev_equity) / prev_equity) * 100.0, 4) if prev_equity > 0 else 0.0
            cum_ret = round(((total_equity - self.initial_capital) / self.initial_capital) * 100.0, 2)

            # Benchmark mark-to-market
            bench_curr = benchmark_prices.get(date_curr, initial_benchmark_val)
            if initial_benchmark_val and initial_benchmark_val > 0 and bench_curr:
                benchmark_equity = round(self.initial_capital * (bench_curr / initial_benchmark_val), 2)
            else:
                benchmark_equity = float(self.initial_capital)

            equity_curve.append(
                DailyEquityPoint(
                    date=date_curr,
                    cash=round(cash, 2),
                    invested_value=round(invested_val, 2),
                    total_equity=total_equity,
                    daily_return_pct=daily_ret,
                    cumulative_return_pct=cum_ret,
                    drawdown_pct=dd_pct,
                    high_water_mark=round(high_water_mark, 2),
                    open_positions_count=len(open_positions),
                    benchmark_equity=benchmark_equity,
                )
            )
            prev_equity = total_equity

        return closed_trades, equity_curve, {"open_positions": [p.to_dict() for p in open_positions.values()]}
