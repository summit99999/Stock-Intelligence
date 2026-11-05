"""
Historical Setup Validation Service (Phase 12).

Validates trade setups against historical price action:
- Backtests specific setup types:
  * ORDER_BLOCK_RETEST
  * FVG_FILL_REVERSAL
  * BOS_CONTINUATION
  * LIQUIDITY_SWEEP_REVERSAL
  * SMC_VOLUME_CONFIRMATION
- Quantifies historical performance:
  * Total occurrences (trade count)
  * Win rate (%)
  * Wilson 95% Score Confidence Interval (lower, center, upper)
  * Profit factor
  * Average risk-reward achieved
  * Max drawdown (%)
  * Average holding period (bars)
- Statistical Reliability Assessment:
  * Sample size < 30: flagged as STATISTICALLY UNVERIFIED with high uncertainty disclaimer
  * Sample size >= 30: marked SUFFICIENT SAMPLE SIZE with Wilson score CI
- Regime-Dependent Win Rates:
  * BULLISH, BEARISH, SIDEWAYS / NEUTRAL, HIGH_VOLATILITY, LOW_VOLATILITY
- Realism Disclosures:
  * Statutory fee deductions (brokerage, STT, exchange, SEBI, GST, stamp duty)
  * Execution slippage
  * Survivorship bias note
  * Research disclosure: past performance is not indicative of future returns
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.database import get_bars, get_stock
from app.services.data_quality_service import DataMode, build_standard_metadata
from app.services.smc_backtest_service import (
    evaluate_sample_size_validity,
    run_smc_backtest,
)

logger = logging.getLogger(__name__)

SETUP_TYPE_MAP = {
    "ORDER_BLOCK_RETEST": "ORDER_BLOCK_RETEST",
    "ORDER_BLOCK": "ORDER_BLOCK_RETEST",
    "FVG_FILL_REVERSAL": "FVG_FILL_REVERSAL",
    "FAIR_VALUE_GAP": "FVG_FILL_REVERSAL",
    "BOS_CONTINUATION": "BOS_CONTINUATION",
    "BREAK_OF_STRUCTURE": "BOS_CONTINUATION",
    "LIQUIDITY_SWEEP_REVERSAL": "LIQUIDITY_SWEEP_REVERSAL",
    "LIQUIDITY_SWEEP": "LIQUIDITY_SWEEP_REVERSAL",
    "SMC_VOLUME_CONFIRMATION": "SMC_VOLUME_CONFIRMATION",
    "VOLUME_CONFIRMATION": "SMC_VOLUME_CONFIRMATION",
}


def validate_historical_setup(
    symbol: str,
    setup_type: str = "ORDER_BLOCK_RETEST",
    initial_capital: float = 100000.0,
    risk_pct: float = 1.0,
    target_rr: float = 2.0,
    trade_type: str = "intraday",
    brokerage_model: str = "dhan",
) -> dict[str, Any]:
    """
    Validate a setup type against historical data for a given symbol.
    """
    sym = symbol.strip().upper()
    stock_record = get_stock(sym) or {}
    bars = get_bars(sym)

    if not bars:
        return {
            "symbol": sym,
            "status": "ERROR",
            "error": f"No historical bars found for symbol '{sym}'.",
        }

    canonical_setup = SETUP_TYPE_MAP.get(setup_type.upper(), "ORDER_BLOCK_RETEST")

    # Run the backtest engine
    risk_decimal = (risk_pct / 100.0) if risk_pct > 0.1 else risk_pct
    backtest_res = run_smc_backtest(
        symbol=sym,
        strategy_type=canonical_setup,
        bars=bars,
        initial_capital=initial_capital,
        risk_pct=risk_decimal,
        target_rr=target_rr,
        trade_type=trade_type,
        brokerage_model=brokerage_model,
        use_indian_costs=True,
    )

    metrics = backtest_res.get("metrics", {})
    total_trades = int(metrics.get("total_trades", 0))
    win_rate = float(metrics.get("win_rate", 0.0))
    wilson_ci = metrics.get("wilson_score_interval", {})
    profit_factor = float(metrics.get("profit_factor", 0.0))
    max_dd = float(metrics.get("max_drawdown_pct", 0.0))
    avg_holding = float(metrics.get("average_holding_bars", 0.0))

    # Sample size assessment
    sample_eval = evaluate_sample_size_validity(total_trades)
    is_reliable = sample_eval.get("is_statistically_valid", False)
    reliability_tier = sample_eval.get("tier", "UNVERIFIED")

    if total_trades < 30:
        sample_warning = (
            f"CAUTION: Sample size ({total_trades} trades) is under 30. "
            "Results are statistically unverified and subject to significant estimation error."
        )
    else:
        sample_warning = (
            f"SUFFICIENT SAMPLE SIZE: {total_trades} trades meet standard minimum sample threshold (>=30). "
            f"Wilson 95% Confidence Interval is [{wilson_ci.get('lower_bound_pct', 0.0)}%, {wilson_ci.get('upper_bound_pct', 0.0)}%]."
        )

    # Regime dependence breakdown
    regime_perf = backtest_res.get("regime_performance", {})
    regime_breakdown = {}
    for r_name, r_stats in regime_perf.items():
        if isinstance(r_stats, dict) and r_stats.get("trades", 0) > 0:
            regime_breakdown[r_name] = {
                "trades": r_stats.get("trades", 0),
                "win_rate_pct": round(r_stats.get("win_rate", 0.0), 1),
                "profit_factor": round(r_stats.get("profit_factor", 0.0), 2),
                "net_pnl": round(r_stats.get("net_pnl", 0.0), 2),
            }

    # Extract recent trades (up to last 10)
    raw_trades = backtest_res.get("trades", [])
    recent_trades = []
    for tr in raw_trades[-10:]:
        recent_trades.append({
            "trade_id": tr.get("id"),
            "entry_time": tr.get("entry_time"),
            "exit_time": tr.get("exit_time"),
            "direction": tr.get("direction"),
            "entry_price": tr.get("entry_price"),
            "exit_price": tr.get("exit_price"),
            "outcome": tr.get("outcome"),
            "pnl": tr.get("pnl"),
            "pnl_pct": tr.get("pnl_pct"),
            "holding_bars": tr.get("holding_bars"),
        })

    metadata = build_standard_metadata(
        provider="yfinance",
        instrument="EQUITY",
        symbol=sym,
        timeframe="1D",
        data_mode=DataMode.HISTORICAL.value,
        last_updated=stock_record.get("updated_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )

    disclaimers = [
        "Past performance is not indicative of future returns.",
        "Hypothetical backtest results are subject to inherent model limitations and survivorship bias.",
        f"Statutory transaction charges modeled under {brokerage_model.upper()} broker fee schedule.",
        "Research and strategy validation only. Not an order instruction or investment advice.",
    ]

    return {
        "symbol": sym,
        "company_name": stock_record.get("company_name", sym),
        "setup_type": canonical_setup,
        "status": "VALIDATED",
        "sample_size_assessment": {
            "total_occurrences": total_trades,
            "is_statistically_reliable": is_reliable,
            "reliability_tier": reliability_tier,
            "warning": sample_warning,
        },
        "performance_metrics": {
            "win_rate_pct": round(win_rate, 1),
            "wilson_ci_95": wilson_ci,
            "profit_factor": round(profit_factor, 2),
            "target_risk_reward": target_rr,
            "max_drawdown_pct": round(max_dd, 2),
            "average_holding_bars": round(avg_holding, 1),
            "gross_profit": round(metrics.get("gross_profit", 0.0), 2),
            "gross_loss": round(metrics.get("gross_loss", 0.0), 2),
            "total_statutory_fees": round(metrics.get("total_statutory_fees", 0.0), 2),
            "total_slippage": round(metrics.get("total_slippage", 0.0), 2),
        },
        "regime_dependence": regime_breakdown,
        "recent_trades": recent_trades,
        "disclaimers": disclaimers,
        "metadata": metadata,
    }
