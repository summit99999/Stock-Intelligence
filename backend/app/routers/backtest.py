"""
FastAPI Router for Professional Backtesting Module V1 (Phase 7 & 8).

Endpoints:
- GET  /api/backtest/universes: Pre-canned stock universes.
- POST /api/backtest/run: Execute consolidation breakout backtest.
- POST /api/backtest/export-csv: Download complete trade log as CSV.
- GET  /api/backtest/data-quality/{symbol}: Inspect historical data quality.
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.services.backtest_analytics_service import BacktestAnalyticsService
from app.services.backtest_data_engine import (
    BacktestDataEngine,
    LIQUID_MOMENTUM_UNIVERSE,
    NIFTY_50_CORE,
)
from app.services.backtest_portfolio_engine import PortfolioSimulationEngine
from app.services.consolidation_breakout_strategy import (
    StrategyParameters,
    scan_consolidation_breakouts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["Backtesting"])

PREDEFINED_UNIVERSES: Dict[str, Dict[str, Any]] = {
    "NIFTY_50": {
        "id": "NIFTY_50",
        "name": "NIFTY 50 Bluechip Universe",
        "description": "Top 50 NSE market-cap equities across all major sectors.",
        "symbols": NIFTY_50_CORE,
    },
    "LIQUID_MOMENTUM": {
        "id": "LIQUID_MOMENTUM",
        "name": "Liquid Momentum & High-Beta Leaders",
        "description": "20 highly liquid institutional momentum equities (TRENT, BEL, HAL, DIXON, etc.).",
        "symbols": LIQUID_MOMENTUM_UNIVERSE,
    },
    "DEFENCE_AND_PSU": {
        "id": "DEFENCE_AND_PSU",
        "name": "Defence & PSU Growth Basket",
        "description": "Key industrial, defence, and public sector market leaders (BEL, HAL, NTPC, ONGC, COALINDIA, SBIN).",
        "symbols": ["BEL", "HAL", "NTPC", "ONGC", "COALINDIA", "SBIN"],
    },
}


class BacktestRunRequest(BaseModel):
    universe_id: str = Field("LIQUID_MOMENTUM", description="Preset universe ID or 'CUSTOM'")
    custom_symbols: Optional[List[str]] = Field(None, description="Custom symbols if universe_id is CUSTOM")
    initial_capital: float = Field(100000.0, ge=10000.0, le=100000000.0, description="Starting capital in INR")
    start_date: str = Field("2021-11-12", description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(None, description="End date (YYYY-MM-DD) or latest available")

    # Strategy Parameters
    consolidation_lookback: int = Field(20, ge=10, le=60)
    max_consolidation_range_pct: float = Field(8.0, ge=2.0, le=25.0)
    uptrend_sma_fast: int = Field(20, ge=5, le=50)
    uptrend_sma_slow: int = Field(50, ge=20, le=200)
    breakout_volume_multiplier: float = Field(1.5, ge=1.0, le=5.0)
    stop_buffer_pct: float = Field(0.2, ge=0.0, le=2.0)
    reward_to_risk_ratio: float = Field(2.0, ge=1.0, le=5.0)
    use_trailing_stop: bool = Field(True)
    use_profit_target: bool = Field(True)
    use_max_holding_period: bool = Field(True)
    max_holding_period_sessions: int = Field(20, ge=5, le=120)

    # Risk & Execution
    risk_per_trade_pct: float = Field(1.0, ge=0.1, le=5.0)
    max_positions: int = Field(5, ge=1, le=20)
    max_allocation_pct: float = Field(20.0, ge=5.0, le=100.0)
    slippage_bps: float = Field(5.0, ge=0.0, le=50.0)
    benchmark_symbol: str = Field("NIFTY 50")
    force_data_refresh: bool = Field(False)


@router.get("/universes")
def get_backtest_universes() -> Dict[str, Any]:
    """List available stock universes for backtesting."""
    return {
        "status": "ok",
        "universes": [
            {
                "id": u["id"],
                "name": u["name"],
                "description": u["description"],
                "symbols_count": len(u["symbols"]),
                "sample_symbols": u["symbols"][:6],
            }
            for u in PREDEFINED_UNIVERSES.values()
        ],
    }


@router.post("/run")
def run_backtest(req: BacktestRunRequest) -> Dict[str, Any]:
    """Execute complete historical consolidation breakout backtest."""
    # 1. Resolve symbols
    if req.universe_id.upper() == "CUSTOM" and req.custom_symbols:
        symbols = [s.strip().upper() for s in req.custom_symbols if s.strip()]
    else:
        u_info = PREDEFINED_UNIVERSES.get(req.universe_id, PREDEFINED_UNIVERSES["LIQUID_MOMENTUM"])
        symbols = u_info["symbols"]

    if not symbols:
        raise HTTPException(status_code=400, detail="Stock universe contains no valid symbols.")

    # 2. Load and validate historical data
    data_engine = BacktestDataEngine()
    universe_dfs, quality_reports = data_engine.load_universe_data(
        symbols=symbols,
        start_date=req.start_date,
        end_date=req.end_date,
        force_refresh=req.force_data_refresh,
    )

    # Load benchmark data (NIFTY 50)
    bench_bars, _ = data_engine.fetch_and_store_history(
        symbol="NIFTY 50",
        start_date=req.start_date,
        end_date=req.end_date,
        force_refresh=req.force_data_refresh,
    )
    import pandas as pd
    bench_df = pd.DataFrame(bench_bars) if bench_bars else None

    # 3. Strategy signal scanning
    strat_params = StrategyParameters(
        consolidation_lookback=req.consolidation_lookback,
        max_consolidation_range_pct=req.max_consolidation_range_pct,
        uptrend_sma_fast=req.uptrend_sma_fast,
        uptrend_sma_slow=req.uptrend_sma_slow,
        breakout_volume_multiplier=req.breakout_volume_multiplier,
        stop_buffer_pct=req.stop_buffer_pct,
        reward_to_risk_ratio=req.reward_to_risk_ratio,
        use_trailing_stop=req.use_trailing_stop,
        trailing_stop_sma=req.uptrend_sma_fast,
        use_profit_target=req.use_profit_target,
        use_max_holding_period=req.use_max_holding_period,
        max_holding_period_sessions=req.max_holding_period_sessions,
        slippage_bps=req.slippage_bps,
    )

    signals_by_symbol = {}
    total_signals_detected = 0
    for sym, df in universe_dfs.items():
        sigs = scan_consolidation_breakouts(sym, df, strat_params)
        signals_by_symbol[sym] = sigs
        total_signals_detected += len(sigs)

    # 4. Multi-asset portfolio simulation
    sim_engine = PortfolioSimulationEngine(
        initial_capital=req.initial_capital,
        risk_per_trade_pct=req.risk_per_trade_pct,
        max_positions=req.max_positions,
        max_allocation_pct=req.max_allocation_pct,
        slippage_bps=req.slippage_bps,
        strategy_params=strat_params,
    )

    trades, equity_curve, meta = sim_engine.run_simulation(
        universe_dfs=universe_dfs,
        signals_by_symbol=signals_by_symbol,
        benchmark_df=bench_df,
    )

    # 5. Compute full quantitative analytics
    analytics_service = BacktestAnalyticsService(risk_free_rate=0.065)
    report = analytics_service.compute_metrics(
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=req.initial_capital,
        benchmark_symbol=req.benchmark_symbol,
    )

    return {
        "status": "ok",
        "universe_id": req.universe_id,
        "scanned_symbols_count": len(symbols),
        "total_signals_detected": total_signals_detected,
        "summary": report.get("summary", {}),
        "equity_curve": [pt.to_dict() for pt in equity_curve],
        "trades": [t.to_dict() for t in trades],
        "monthly_returns": report.get("monthly_returns", []),
        "stock_performance": report.get("stock_performance", []),
        "cost_summary": report.get("cost_breakdown_summary", {}),
        "data_quality": {sym: r.to_dict() for sym, r in quality_reports.items()},
        "open_positions": meta.get("open_positions", []),
    }


class ExportCsvRequest(BaseModel):
    trades: List[Dict[str, Any]]


@router.post("/export-csv")
def export_trades_csv(req: ExportCsvRequest) -> Response:
    """Export backtest trade log as downloadable CSV file."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Trade #",
        "Symbol",
        "Entry Date",
        "Exit Date",
        "Holding Days",
        "Quantity",
        "Entry Price (INR)",
        "Exit Price (INR)",
        "Entry Turnover (INR)",
        "Exit Turnover (INR)",
        "Gross P&L (INR)",
        "Total Costs (INR)",
        "Net P&L (INR)",
        "Return %",
        "Exit Reason",
        "Brokerage (INR)",
        "STT (INR)",
        "Exchange Txn Charges (INR)",
        "SEBI Fees (INR)",
        "Stamp Duty (INR)",
        "GST (INR)",
        "DP Charges (INR)",
        "Slippage (INR)",
    ])

    for i, t in enumerate(req.trades, 1):
        cb = t.get("cost_breakdown", {})
        item = cb.get("itemized", {})
        writer.writerow([
            i,
            t.get("symbol", ""),
            t.get("entry_date", ""),
            t.get("exit_date", ""),
            t.get("holding_days", 0),
            t.get("quantity", 0),
            t.get("entry_price", 0.0),
            t.get("exit_price", 0.0),
            t.get("entry_turnover", 0.0),
            t.get("exit_turnover", 0.0),
            t.get("gross_pnl", 0.0),
            t.get("total_transaction_cost", 0.0),
            t.get("net_pnl", 0.0),
            t.get("return_pct", 0.0),
            t.get("exit_reason", ""),
            item.get("brokerage", 0.0),
            item.get("stt", 0.0),
            item.get("exchange_txn_charge", 0.0),
            item.get("sebi_turnover_fee", 0.0),
            item.get("stamp_duty", 0.0),
            item.get("gst", 0.0),
            item.get("dp_charge", 0.0),
            cb.get("slippage_total", 0.0),
        ])

    csv_data = output.getvalue()
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=backtest_trades_upstox_v1.csv"},
    )
