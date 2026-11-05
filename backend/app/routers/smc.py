"""
Smart Money Concepts & Order Block API Router.

Endpoints for:
- Full SMC analysis (Structure, Order Blocks, FVGs, Supply/Demand, Liquidity, Premium/Discount)
- Granular Order Blocks & Fair Value Gaps
- Market X-Ray dual ranking boards (Bullish Board & Bearish Board)
- Historical validation & backtesting
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_stock
from app.services.data_quality_service import generate_market_data_quality_report
from app.services.market_xray_service import generate_market_xray_dashboard
from app.services.smc_backtest_service import (
    run_parameter_sensitivity,
    run_smc_backtest,
    run_walk_forward_validation,
)
from app.services.smc_service import (
    analyze_smart_money_concepts,
    detect_fair_value_gaps,
    detect_market_structure,
    detect_order_blocks,
    _prepare_df,
)
from app.database import get_bars

router = APIRouter(prefix="/api/smc", tags=["smart-money-concepts"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbol: str
    strategy_type: str = Field(
        "ORDER_BLOCK_RETEST",
        description="ORDER_BLOCK_RETEST, FVG_FILL_REVERSAL, BOS_CONTINUATION, LIQUIDITY_SWEEP_REVERSAL, or SMC_VOLUME_CONFIRMATION"
    )
    target_rr: float = Field(2.0, ge=1.0, le=10.0)
    cost_bps: float = Field(5.0, ge=0.0, le=50.0)
    trade_type: str = Field("delivery", description="'delivery' (default for swing) or 'intraday'")
    brokerage_model: str = Field("dhan", description="'dhan' (default), 'zerodha', 'flat_20', or 'percentage'")
    dp_policy: Optional[str] = Field(None, description="'per_order' (Dhan default) or 'per_isin_daily' (Zerodha/CDSL default)")
    allow_overnight_short: bool = Field(False, description="Allow overnight short delivery trades via SLB mechanism")
    risk_pct: float = Field(0.02, ge=0.001, le=0.20, description="Risk budget fraction (default 0.02 = 2%)")
    risk_free_rate: float = Field(0.06, ge=0.0, le=0.20, description="Assumed annual risk-free benchmark rate (default 0.06 = 6.0%)")
    max_holding_bars: int = Field(15, ge=3, le=50)
    use_indian_costs: bool = Field(True, description="Enable realistic Indian statutory charges")
    allow_overlapping: bool = Field(False, description="Allow concurrent overlapping positions")


# ---------------------------------------------------------------------------
# SMC Endpoints
# ---------------------------------------------------------------------------

@router.get("/analysis/{symbol}")
def get_smc_analysis(
    symbol: str,
    limit: int = Query(120, ge=20, le=500, description="Historical bars count"),
):
    """
    Get full Smart Money Concepts analysis for a symbol:
    Structure, Order Blocks, FVGs, Supply/Demand, Liquidity, Premium/Discount, and Setup Score.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    res = analyze_smart_money_concepts(symbol.upper(), limit=limit)
    return res


@router.get("/order-blocks/{symbol}")
def get_order_blocks_endpoint(
    symbol: str,
    limit: int = Query(120, ge=20, le=500),
):
    """
    Get confirmed Bullish and Bearish Order Blocks with lifecycle tracking.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    bars = get_bars(symbol.upper())
    df = _prepare_df(bars).tail(limit).reset_index(drop=True)
    structure = detect_market_structure(df)
    obs = detect_order_blocks(df, structure["breaks"])

    return {
        "symbol": symbol.upper(),
        "total_order_blocks": len(obs),
        "order_blocks": obs,
    }


@router.get("/structure/{symbol}")
def get_structure_endpoint(
    symbol: str,
    limit: int = Query(120, ge=20, le=500),
):
    """
    Get swing pivots, Higher Highs/Lows, and confirmed BOS / CHoCH breaks.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    bars = get_bars(symbol.upper())
    df = _prepare_df(bars).tail(limit).reset_index(drop=True)
    structure = detect_market_structure(df)

    return {
        "symbol": symbol.upper(),
        "market_structure": structure,
    }


@router.get("/fvg/{symbol}")
def get_fvg_endpoint(
    symbol: str,
    limit: int = Query(120, ge=20, le=500),
):
    """
    Get 3-candle Fair Value Gaps (FVG) and their current fill percentages.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    bars = get_bars(symbol.upper())
    df = _prepare_df(bars).tail(limit).reset_index(drop=True)
    fvgs = detect_fair_value_gaps(df)

    return {
        "symbol": symbol.upper(),
        "total_fvgs": len(fvgs),
        "gaps": fvgs,
    }


@router.get("/xray")
def get_market_xray_endpoint(
    limit: int = Query(50, ge=10, le=200, description="Max stocks to scan"),
):
    """
    Market X-Ray: Market-wide stock ranking dashboard with dual Bullish and Bearish boards.
    """
    return generate_market_xray_dashboard(limit_universe=limit)


@router.post("/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    """
    Run chronological backtest for SMC strategies across any of the 5 independent models.
    """
    stk = get_stock(req.symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{req.symbol.upper()}' not found in database")

    res = run_smc_backtest(
        symbol=req.symbol.upper(),
        strategy_type=req.strategy_type,
        target_rr=req.target_rr,
        cost_bps=req.cost_bps,
        use_indian_costs=req.use_indian_costs,
        trade_type=req.trade_type,
        brokerage_model=req.brokerage_model,
        dp_policy=req.dp_policy,
        allow_overnight_short=req.allow_overnight_short,
        risk_pct=req.risk_pct,
        max_holding_bars=req.max_holding_bars,
        allow_overlapping=req.allow_overlapping,
        risk_free_rate=req.risk_free_rate,
    )
    return res


@router.get("/walk-forward/{symbol}")
def get_walk_forward_endpoint(
    symbol: str,
    strategy_type: str = Query("ORDER_BLOCK_RETEST"),
    num_windows: int = Query(3, ge=1, le=10),
    window_type: str = Query("rolling", pattern="^(rolling|expanding)$"),
    trade_type: str = Query("delivery"),
    brokerage_model: str = Query("dhan"),
    target_rr: float = Query(2.0, ge=1.0, le=10.0),
    cost_bps: float = Query(5.0, ge=0.0, le=50.0),
    risk_free_rate: float = Query(0.06, ge=0.0, le=0.20),
):
    """
    Run chronological walk-forward validation and market regime performance audit.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    return run_walk_forward_validation(
        symbol=symbol.upper(),
        strategy_type=strategy_type,
        num_windows=num_windows,
        window_type=window_type,
        trade_type=trade_type,
        brokerage_model=brokerage_model,
        target_rr=target_rr,
        cost_bps=cost_bps,
        risk_free_rate=risk_free_rate,
    )


@router.get("/sensitivity/{symbol}")
def get_sensitivity_endpoint(
    symbol: str,
    strategy_type: str = Query("ORDER_BLOCK_RETEST"),
):
    """
    Evaluate parameter sensitivity grid across Target R:R and Holding periods.
    """
    stk = get_stock(symbol.upper())
    if not stk:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' not found in database")

    return run_parameter_sensitivity(
        symbol=symbol.upper(),
        strategy_type=strategy_type,
    )


@router.get("/data-quality")
def get_data_quality_endpoint():
    """
    Generate comprehensive data quality diagnostic report across all universe stocks.
    """
    return generate_market_data_quality_report()
