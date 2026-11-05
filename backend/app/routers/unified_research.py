"""
Unified Research and Decision Engine Router (Phase 12).

Provides endpoints for:
1. Market Regime Engine: Multi-factor market posture classification & evidence
2. Sector Rotation Engine: 4-quadrant rotation, breadth & relative strength
3. Stock Discovery: Multi-factor ranking, filtering & pagination
4. Stock Research Dossier: Comprehensive 7-factor evaluation and raw module signals
5. Trade Plan Generator: Hypothetical research plan with position sizing & guardrails
6. Historical Setup Validation: Non-repainting backtest validation with Wilson CI
7. Trade Plans & Research Notes Persistence: SQLite CRUD
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import (
    delete_research_note,
    delete_research_trade_plan,
    get_bars,
    get_research_trade_plan,
    get_stock,
    list_research_notes,
    list_research_trade_plans,
    save_research_note,
    save_research_trade_plan,
    update_research_trade_plan,
)
from app.services.fundamental_ratios_service import compute_all_ratios
from app.services.historical_setup_validator import validate_historical_setup
from app.services.indicators import calculate_all_indicators
from app.services.market_regime_engine import classify_market_regime
from app.services.money_flow_service import calculate_stock_volume_intelligence
from app.services.multi_timeframe_service import analyze_multi_timeframe
from app.services.sector_rotation_engine import compute_sector_rotation
from app.services.setup_detection_service import detect_all_setups
from app.services.smc_service import analyze_smart_money_concepts
from app.services.trade_plan_generator import generate_trade_plan
from app.services.unified_research_engine import discover_stocks, evaluate_stock_setup_quality

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["unified-research"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class DiscoveryRequest(BaseModel):
    universe: str = Field(default="all", description="Universe: all, nifty50, nifty100, nifty500, fno")
    direction: Optional[str] = Field(default=None, description="BULLISH, BEARISH, or None")
    min_score: float = Field(default=0.0, description="Minimum setup quality score (0-100)")
    sector: Optional[str] = Field(default=None, description="Filter by sector")
    sort_by: str = Field(default="setup_score", description="Sort field")
    sort_order: str = Field(default="desc", description="asc or desc")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class TradePlanRequest(BaseModel):
    symbol: str
    account_capital: float = Field(default=100000.0, ge=1000.0)
    risk_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    target_rr: float = Field(default=2.0, ge=1.0, le=10.0)
    direction_override: Optional[str] = Field(default=None, description="LONG or SHORT")


class SaveTradePlanPayload(BaseModel):
    symbol: str
    direction: str = "LONG"
    setup_type: str = "ORDER_BLOCK_RETEST"
    entry_type: str = "LIMIT"
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    ideal_entry: float
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    risk_reward_ratio: float = 2.0
    position_size: int = 0
    risk_amount: float = 0.0
    capital_allocated: float = 0.0
    invalidation_condition: Optional[str] = None
    failure_risks: Optional[Any] = None
    evidence: Optional[Any] = None
    notes: Optional[str] = None


class UpdateTradePlanPayload(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


class ResearchNotePayload(BaseModel):
    symbol: str
    note: str
    title: Optional[str] = None
    tags: Optional[str] = None


class HistoricalValidationRequest(BaseModel):
    symbol: str
    setup_type: str = Field(default="ORDER_BLOCK_RETEST")
    initial_capital: float = Field(default=100000.0, ge=1000.0)
    risk_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    target_rr: float = Field(default=2.0, ge=1.0, le=10.0)
    trade_type: str = Field(default="intraday")
    brokerage_model: str = Field(default="dhan")


# ---------------------------------------------------------------------------
# 1. Market Regime & Sector Rotation Endpoints
# ---------------------------------------------------------------------------

@router.get("/regime")
def get_market_regime(universe: str = Query("all", description="Market universe")):
    """
    Get evidence-based market regime classification with multi-factor breakdown.
    """
    try:
        return classify_market_regime(universe=universe)
    except Exception as e:
        logger.exception("Error evaluating market regime: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sectors")
def get_sector_rotation(universe: str = Query("all", description="Market universe")):
    """
    Get 4-quadrant sector rotation, relative strength, and internal breadth.
    """
    try:
        return compute_sector_rotation(universe=universe)
    except Exception as e:
        logger.exception("Error evaluating sector rotation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 2. Stock Discovery & Setup Ranking Endpoints
# ---------------------------------------------------------------------------

@router.post("/discovery")
def run_stock_discovery(req: DiscoveryRequest):
    """
    Run multi-factor stock discovery scan combining all analytical dimensions.
    """
    try:
        return discover_stocks(
            universe=req.universe,
            direction_filter=req.direction,
            min_score=req.min_score,
            sector_filter=req.sector,
            sort_by=req.sort_by,
            sort_order=req.sort_order,
            page=req.page,
            page_size=req.page_size,
        )
    except Exception as e:
        logger.exception("Error during stock discovery: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discovery")
def get_stock_discovery(
    universe: str = Query("all"),
    direction: Optional[str] = Query(None),
    min_score: float = Query(0.0),
    sector: Optional[str] = Query(None),
    sort_by: str = Query("setup_score"),
    sort_order: str = Query("desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    GET variant of stock discovery scan for easy browser/client access.
    """
    try:
        return discover_stocks(
            universe=universe,
            direction_filter=direction,
            min_score=min_score,
            sector_filter=sector,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.exception("Error during GET stock discovery: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 3. Deep-Dive Stock Research Dossier
# ---------------------------------------------------------------------------

@router.get("/stock/{symbol}")
def get_stock_research_dossier(symbol: str):
    """
    Comprehensive research dossier combining 7-factor evaluation,
    fundamentals, technicals, volume intelligence, SMC and MTF data.
    """
    sym = symbol.strip().upper()
    stock_record = get_stock(sym)
    if not stock_record:
        raise HTTPException(status_code=404, detail=f"Stock '{sym}' not found in database.")

    bars = get_bars(sym)

    # 1. 100-point setup score & breakdown
    setup_eval = evaluate_stock_setup_quality(sym)

    # 2. Technical indicators
    indicators = calculate_all_indicators(bars) if bars and len(bars) >= 2 else {}

    # 3. Fundamentals
    fundamentals = None
    try:
        ratios = compute_all_ratios(sym)
        if ratios:
            fundamentals = ratios.model_dump() if hasattr(ratios, "model_dump") else ratios.dict()
    except Exception as e:
        logger.debug("Fundamentals lookup for %s: %s", sym, e)

    # 4. Volume intelligence
    vol_intel = {}
    try:
        vol_intel = calculate_stock_volume_intelligence(sym)
    except Exception as e:
        logger.debug("Volume intelligence for %s: %s", sym, e)

    # 5. SMC
    smc = {}
    if bars and len(bars) >= 10:
        try:
            smc = analyze_smart_money_concepts(sym, bars=bars)
        except Exception as e:
            logger.debug("SMC analysis for %s: %s", sym, e)

    # 6. Multi-Timeframe
    mtf = {}
    try:
        mtf = analyze_multi_timeframe(sym)
    except Exception as e:
        logger.debug("MTF for %s: %s", sym, e)

    # 7. Detected Setups
    setups = []
    if bars and len(bars) >= 10:
        try:
            setups = detect_all_setups(sym, bars=bars)
        except Exception as e:
            logger.debug("Setups for %s: %s", sym, e)

    # 8. Automated Trade Plan
    trade_plan = generate_trade_plan(sym)

    return {
        "symbol": sym,
        "company_name": stock_record.get("company_name", sym),
        "sector": stock_record.get("sector", "Diversified"),
        "close": stock_record.get("close"),
        "daily_change_pct": stock_record.get("daily_change_pct"),
        "setup_evaluation": setup_eval,
        "trade_plan": trade_plan,
        "indicators": indicators,
        "fundamentals": fundamentals,
        "volume_intelligence": vol_intel,
        "smc": smc,
        "multi_timeframe": mtf,
        "detected_setups": setups,
        "bars_count": len(bars),
    }


# ---------------------------------------------------------------------------
# 4. Trade Plan Generation & Validation
# ---------------------------------------------------------------------------

@router.post("/trade-plan")
def create_custom_trade_plan(req: TradePlanRequest):
    """
    Generate customized hypothetical trade plan with specific capital and risk %.
    """
    try:
        plan = generate_trade_plan(
            symbol=req.symbol,
            account_capital=req.account_capital,
            risk_pct=req.risk_pct,
            target_rr=req.target_rr,
            direction_override=req.direction_override,
        )
        if plan.get("status") == "ERROR":
            raise HTTPException(status_code=400, detail=plan.get("error"))
        return plan
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error generating trade plan: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
def validate_setup_endpoint(req: HistoricalValidationRequest):
    """
    Validate trade setup against historical data.
    """
    try:
        res = validate_historical_setup(
            symbol=req.symbol,
            setup_type=req.setup_type,
            initial_capital=req.initial_capital,
            risk_pct=req.risk_pct,
            target_rr=req.target_rr,
            trade_type=req.trade_type,
            brokerage_model=req.brokerage_model,
        )
        if res.get("status") == "ERROR":
            raise HTTPException(status_code=400, detail=res.get("error"))
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error validating setup: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 5. Persistent Trade Plans CRUD
# ---------------------------------------------------------------------------

@router.post("/trade-plans/save")
def save_trade_plan_endpoint(payload: SaveTradePlanPayload):
    """
    Save research trade plan to database.
    """
    try:
        return save_research_trade_plan(payload.model_dump())
    except Exception as e:
        logger.exception("Error saving trade plan: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-plans")
def list_trade_plans_endpoint(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """
    List saved research trade plans.
    """
    try:
        return list_research_trade_plans(symbol=symbol, status=status)
    except Exception as e:
        logger.exception("Error listing trade plans: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trade-plans/{plan_id}")
def get_trade_plan_endpoint(plan_id: int):
    """
    Get a single research trade plan by ID.
    """
    plan = get_research_trade_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Trade plan #{plan_id} not found.")
    return plan


@router.put("/trade-plans/{plan_id}")
def update_trade_plan_endpoint(plan_id: int, payload: UpdateTradePlanPayload):
    """
    Update status or notes on a saved trade plan.
    """
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    res = update_research_trade_plan(plan_id, updates)
    if not res:
        raise HTTPException(status_code=404, detail=f"Trade plan #{plan_id} not found or no updates applied.")
    return res


@router.delete("/trade-plans/{plan_id}")
def delete_trade_plan_endpoint(plan_id: int):
    """
    Delete a saved research trade plan.
    """
    deleted = delete_research_trade_plan(plan_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Trade plan #{plan_id} not found.")
    return {"status": "SUCCESS", "deleted_id": plan_id}


# ---------------------------------------------------------------------------
# 6. Persistent Qualitative Research Notes CRUD
# ---------------------------------------------------------------------------

@router.post("/notes")
def save_research_note_endpoint(payload: ResearchNotePayload):
    """
    Save qualitative research note for a stock.
    """
    try:
        return save_research_note(
            symbol=payload.symbol,
            note=payload.note,
            title=payload.title,
            tags=payload.tags,
        )
    except Exception as e:
        logger.exception("Error saving note: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/notes/{symbol}")
def list_research_notes_endpoint(symbol: str):
    """
    List research notes for a stock.
    """
    try:
        return list_research_notes(symbol=symbol)
    except Exception as e:
        logger.exception("Error listing notes: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/notes/{note_id}")
def delete_research_note_endpoint(note_id: int):
    """
    Delete a research note by ID.
    """
    deleted = delete_research_note(note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Research note #{note_id} not found.")
    return {"status": "SUCCESS", "deleted_id": note_id}
