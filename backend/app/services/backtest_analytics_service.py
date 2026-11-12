"""
Backtest Performance Analytics & Metrics Service (Phase 7).

Computes comprehensive quantitative performance analytics for historical equity backtests:
- Capital & Return: Initial capital, final equity, gross/net profit, net return %, CAGR.
- Risk & Drawdown: Max drawdown (₹ and %), max drawdown duration, annualized volatility.
- Risk-Adjusted: Sharpe ratio (Rf=6.5%), Sortino ratio, Calmar ratio.
- Trade Statistics: Win rate, profit factor, avg win/loss, payoff ratio, expectancy.
- Temporal: Average holding period, exposure percentage.
- Monthly & Yearly Returns Heatmap table.
- Benchmark Comparison against NIFTY 50 buy & hold.
- Stock-level breakdown.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import math
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from app.services.backtest_portfolio_engine import DailyEquityPoint, TradeRecord


@dataclass
class PerformanceSummary:
    initial_capital: float
    final_equity: float
    gross_profit: float
    net_profit: float
    net_return_pct: float
    cagr_pct: float
    total_days: int
    total_sessions: int

    # Risk & Drawdown
    max_drawdown_pct: float
    max_drawdown_inr: float
    annualized_volatility_pct: float
    downside_deviation_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    risk_free_rate_pct: float

    # Trade Statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    scratch_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_trade_pnl: float
    avg_winning_trade: float
    avg_losing_trade: float
    payoff_ratio: float
    expectancy_inr: float
    avg_holding_period_days: float
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Costs
    total_transaction_costs: float
    statutory_charges_total: float
    brokerage_total: float
    stt_total: float
    slippage_total: float

    # Benchmark Comparison
    benchmark_symbol: str
    benchmark_final_equity: float
    benchmark_return_pct: float
    benchmark_cagr_pct: float
    alpha_pct: float
    exposure_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BacktestAnalyticsService:
    """Computes comprehensive quantitative performance analytics."""

    def __init__(self, risk_free_rate: float = 0.065):  # 6.5% standard RBI 91-day T-Bill rate
        self.risk_free_rate = risk_free_rate

    def compute_metrics(
        self,
        trades: List[TradeRecord],
        equity_curve: List[DailyEquityPoint],
        initial_capital: float = 100000.0,
        benchmark_symbol: str = "NIFTY 50",
    ) -> Dict[str, Any]:
        """Compute full statistical and risk report."""
        if not equity_curve:
            return {"error": "Equity curve is empty."}

        # 1. Capital and Return
        final_equity = equity_curve[-1].total_equity
        net_profit = round(final_equity - initial_capital, 2)
        net_return_pct = round((net_profit / initial_capital) * 100.0, 2)

        start_date = datetime.strptime(equity_curve[0].date, "%Y-%m-%d")
        end_date = datetime.strptime(equity_curve[-1].date, "%Y-%m-%d")
        total_days = max(1, (end_date - start_date).days)
        total_sessions = len(equity_curve)

        years = total_days / 365.25
        if years > 0 and final_equity > 0:
            cagr = ((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0
        else:
            cagr = 0.0
        cagr_pct = round(cagr, 2)

        # 2. Mark-to-market daily returns & Drawdown
        daily_returns = np.array([pt.daily_return_pct / 100.0 for pt in equity_curve[1:]])
        if len(daily_returns) > 1:
            daily_std = float(np.std(daily_returns, ddof=1))
            ann_vol = daily_std * math.sqrt(252) * 100.0
            # Downside deviation
            neg_returns = daily_returns[daily_returns < 0]
            if len(neg_returns) > 0:
                downside_std = float(np.std(neg_returns, ddof=1)) if len(neg_returns) > 1 else float(np.abs(neg_returns[0]))
                ann_downside = downside_std * math.sqrt(252) * 100.0
            else:
                ann_downside = 0.0001
        else:
            ann_vol = 0.0
            ann_downside = 0.0001

        # Max Drawdown
        max_dd_pct = min([pt.drawdown_pct for pt in equity_curve])  # Negative float
        max_dd_inr = 0.0
        for pt in equity_curve:
            dd_inr = pt.high_water_mark - pt.total_equity
            if dd_inr > max_dd_inr:
                max_dd_inr = dd_inr

        # Sharpe & Sortino & Calmar
        rf_pct = self.risk_free_rate * 100.0
        excess_return = cagr_pct - rf_pct
        sharpe = round(excess_return / ann_vol, 2) if ann_vol > 0 else 0.0
        sortino = round(excess_return / ann_downside, 2) if ann_downside > 0 else 0.0
        calmar = round(cagr_pct / abs(max_dd_pct), 2) if max_dd_pct < 0 else 0.0

        # 3. Trade Statistics
        total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl < 0]
        scratches = [t for t in trades if t.net_pnl == 0]

        win_count = len(wins)
        loss_count = len(losses)
        scratch_count = len(scratches)
        win_rate = round((win_count / total_trades) * 100.0, 2) if total_trades > 0 else 0.0

        total_gross_profit = sum([t.gross_pnl for t in wins]) if wins else 0.0
        total_gross_loss = abs(sum([t.gross_pnl for t in losses])) if losses else 0.0

        if total_gross_loss > 0:
            profit_factor = round(total_gross_profit / total_gross_loss, 2)
        elif total_gross_profit > 0:
            profit_factor = 99.99  # No losses
        else:
            profit_factor = 0.0

        avg_trade_pnl = round(sum([t.net_pnl for t in trades]) / total_trades, 2) if total_trades > 0 else 0.0
        avg_win = round(sum([t.net_pnl for t in wins]) / win_count, 2) if win_count > 0 else 0.0
        avg_loss = round(sum([t.net_pnl for t in losses]) / loss_count, 2) if loss_count > 0 else 0.0
        payoff_ratio = round(avg_win / abs(avg_loss), 2) if avg_loss != 0 else 0.0

        win_prob = win_count / total_trades if total_trades > 0 else 0.0
        loss_prob = loss_count / total_trades if total_trades > 0 else 0.0
        expectancy = round((win_prob * avg_win) + (loss_prob * avg_loss), 2)

        avg_hold = round(sum([t.holding_days for t in trades]) / total_trades, 1) if total_trades > 0 else 0.0

        # Consecutive streaks
        max_cons_wins = 0
        max_cons_losses = 0
        curr_wins = 0
        curr_losses = 0
        for t in trades:
            if t.net_pnl > 0:
                curr_wins += 1
                curr_losses = 0
                max_cons_wins = max(max_cons_wins, curr_wins)
            elif t.net_pnl < 0:
                curr_losses += 1
                curr_wins = 0
                max_cons_losses = max(max_cons_losses, curr_losses)

        # 4. Costs Aggregation
        total_costs = round(sum([t.total_transaction_cost for t in trades]), 2)
        total_brokerage = 0.0
        total_stt = 0.0
        total_txn = 0.0
        total_slippage = 0.0
        total_dp = 0.0
        total_gst = 0.0
        total_sebi = 0.0
        total_stamp = 0.0

        for t in trades:
            item = t.cost_breakdown.get("itemized", {})
            total_brokerage += item.get("brokerage", 0.0)
            total_stt += item.get("stt", 0.0)
            total_txn += item.get("exchange_txn_charge", 0.0)
            total_dp += item.get("dp_charge", 0.0)
            total_gst += item.get("gst", 0.0)
            total_sebi += item.get("sebi_turnover_fee", 0.0)
            total_stamp += item.get("stamp_duty", 0.0)
            total_slippage += t.cost_breakdown.get("slippage_total", 0.0)

        # 5. Exposure percentage
        sessions_invested = sum(1 for pt in equity_curve if pt.open_positions_count > 0)
        exposure_pct = round((sessions_invested / total_sessions) * 100.0, 1) if total_sessions > 0 else 0.0

        # 6. Benchmark Metrics
        bench_final = equity_curve[-1].benchmark_equity
        bench_return_pct = round(((bench_final - initial_capital) / initial_capital) * 100.0, 2)
        if years > 0 and bench_final > 0:
            bench_cagr = ((bench_final / initial_capital) ** (1.0 / years) - 1.0) * 100.0
        else:
            bench_cagr = 0.0
        bench_cagr_pct = round(bench_cagr, 2)
        alpha_pct = round(cagr_pct - bench_cagr_pct, 2)

        summary = PerformanceSummary(
            initial_capital=initial_capital,
            final_equity=final_equity,
            gross_profit=round(total_gross_profit - total_gross_loss, 2),
            net_profit=net_profit,
            net_return_pct=net_return_pct,
            cagr_pct=cagr_pct,
            total_days=total_days,
            total_sessions=total_sessions,
            max_drawdown_pct=abs(max_dd_pct),
            max_drawdown_inr=round(max_dd_inr, 2),
            annualized_volatility_pct=round(ann_vol, 2),
            downside_deviation_pct=round(ann_downside, 2),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            risk_free_rate_pct=rf_pct,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count,
            scratch_trades=scratch_count,
            win_rate_pct=win_rate,
            profit_factor=profit_factor,
            avg_trade_pnl=avg_trade_pnl,
            avg_winning_trade=avg_win,
            avg_losing_trade=avg_loss,
            payoff_ratio=payoff_ratio,
            expectancy_inr=expectancy,
            avg_holding_period_days=avg_hold,
            max_consecutive_wins=max_cons_wins,
            max_consecutive_losses=max_cons_losses,
            total_transaction_costs=total_costs,
            statutory_charges_total=round(total_costs - total_slippage, 2),
            brokerage_total=round(total_brokerage, 2),
            stt_total=round(total_stt, 2),
            slippage_total=round(total_slippage, 2),
            benchmark_symbol=benchmark_symbol,
            benchmark_final_equity=bench_final,
            benchmark_return_pct=bench_return_pct,
            benchmark_cagr_pct=bench_cagr_pct,
            alpha_pct=alpha_pct,
            exposure_pct=exposure_pct,
        )

        # 7. Monthly Returns Heatmap Table
        monthly_matrix = self._compute_monthly_returns(equity_curve)

        # 8. Individual Stock Breakdown
        stock_breakdown = self._compute_stock_breakdown(trades)

        return {
            "summary": summary.to_dict(),
            "monthly_returns": monthly_matrix,
            "stock_performance": stock_breakdown,
            "cost_breakdown_summary": {
                "total_transaction_costs": total_costs,
                "brokerage": round(total_brokerage, 2),
                "stt": round(total_stt, 2),
                "exchange_txn_charges": round(total_txn, 2),
                "dp_charges": round(total_dp, 2),
                "gst": round(total_gst, 2),
                "sebi_fees": round(total_sebi, 2),
                "stamp_duty": round(total_stamp, 2),
                "slippage": round(total_slippage, 2),
            },
        }

    def _compute_monthly_returns(self, equity_curve: List[DailyEquityPoint]) -> List[Dict[str, Any]]:
        """Construct a Year x Month matrix of mark-to-market percentage returns."""
        if not equity_curve:
            return []

        df = pd.DataFrame([{"date": pt.date, "equity": pt.total_equity} for pt in equity_curve])
        df["dt"] = pd.to_datetime(df["date"])
        df["year"] = df["dt"].dt.year
        df["month"] = df["dt"].dt.month

        # Group by year and month, taking the end equity of each month
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        years = sorted(df["year"].unique())

        rows: List[Dict[str, Any]] = []

        prev_month_end_equity = equity_curve[0].total_equity

        for yr in years:
            row: Dict[str, Any] = {"year": int(yr), "returns": {}, "year_total_pct": 0.0}
            yr_df = df[df["year"] == yr]
            yr_start_equity = yr_df.iloc[0]["equity"]

            for m in range(1, 13):
                m_df = yr_df[yr_df["month"] == m]
                if not m_df.empty:
                    m_end_equity = m_df.iloc[-1]["equity"]
                    m_ret = round(((m_end_equity - prev_month_end_equity) / prev_month_end_equity) * 100.0, 2)
                    row["returns"][month_names[m - 1]] = m_ret
                    prev_month_end_equity = m_end_equity
                else:
                    row["returns"][month_names[m - 1]] = None

            yr_end_equity = yr_df.iloc[-1]["equity"]
            row["year_total_pct"] = round(((yr_end_equity - yr_start_equity) / yr_start_equity) * 100.0, 2)
            rows.append(row)

        return rows

    def _compute_stock_breakdown(self, trades: List[TradeRecord]) -> List[Dict[str, Any]]:
        """Group trade performance by individual stock symbol."""
        if not trades:
            return []

        by_sym: Dict[str, List[TradeRecord]] = {}
        for t in trades:
            by_sym.setdefault(t.symbol, []).append(t)

        breakdown = []
        for sym, sym_trades in by_sym.items():
            wins = [t for t in sym_trades if t.net_pnl > 0]
            losses = [t for t in sym_trades if t.net_pnl < 0]
            tot_pnl = sum([t.net_pnl for t in sym_trades])
            tot_costs = sum([t.total_transaction_cost for t in sym_trades])
            tot_turnover = sum([t.entry_turnover + t.exit_turnover for t in sym_trades])

            breakdown.append({
                "symbol": sym,
                "trades_count": len(sym_trades),
                "wins_count": len(wins),
                "losses_count": len(losses),
                "win_rate_pct": round((len(wins) / len(sym_trades)) * 100.0, 1),
                "net_pnl": round(tot_pnl, 2),
                "avg_trade_pnl": round(tot_pnl / len(sym_trades), 2),
                "total_transaction_cost": round(tot_costs, 2),
                "total_turnover": round(tot_turnover, 2),
            })

        breakdown.sort(key=lambda x: x["net_pnl"], reverse=True)
        return breakdown
