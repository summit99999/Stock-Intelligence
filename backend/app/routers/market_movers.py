"""
Market Movers & Price-Volume Confluence API Router (Phase 14 & Phase 14.1).

Provides standardized, snapshot-synchronized market intelligence for:
1. Top Gainers: /api/market-movers/gainers
2. Top Losers: /api/market-movers/losers
3. Volume Gainers: /api/market-movers/volume-gainers
4. High-Volume Losers: /api/market-movers/bearish-volume
5. Bullish & Bearish Confluence: /api/market-movers/confluence
6. Unified Movers Dashboard: /api/market-movers/overview
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Query

from app.database import list_ingestion_runs
from app.services.market_movers_service import get_market_movers_and_confluence
from app.services.dhan_market_service import get_dhan_market_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market-movers", tags=["market-movers"])


def _extract_live_quotes_dict() -> Optional[dict[str, Any]]:
    """Extract live quotes from Dhan market service if active."""
    try:
        market_svc = get_dhan_market_service()
        cached = market_svc.get_all_cached_quotes()
        live_dict: dict[str, Any] = {}
        for sym, q in cached.items():
            if getattr(q, "source", "") == "LIVE":
                live_dict[sym] = {
                    "source": "LIVE",
                    "ltp": getattr(q, "ltp", None),
                    "volume": getattr(q, "volume", None),
                    "turnover": getattr(q, "turnover", None),
                    "change_percent": getattr(q, "change_percent", None),
                    "timestamp": getattr(q, "timestamp", None),
                }
        return live_dict if live_dict else None
    except Exception:
        return None


@router.get("/overview")
def get_market_movers_overview_endpoint(
    universe: str = Query("all", description="all, nifty50, nifty100, nifty200, nifty500, fno"),
    exchange: str = Query("NSE", description="NSE or BSE"),
    rvol_mode: str = Query("daily", description="daily (Daily RVOL) or tod (True Time-of-Day RVOL)"),
    min_rvol: float = Query(1.5, ge=0.5, le=10.0, description="Minimum RVOL threshold (default 1.5)"),
    min_price_change_pct: float = Query(0.0, ge=0.0, le=20.0, description="Minimum absolute price change %"),
    min_traded_value_cr: float = Query(0.0, ge=0.0, description="Minimum turnover in ₹ Cr"),
    limit: int = Query(10, ge=3, le=100, description="Number of stocks to display per panel"),
    force_refresh: bool = Query(False, description="Bypass cache and force recalculation"),
    exclude_stale: bool = Query(False, description="Filter out stale records older than 5 trading days"),
    is_session_open: Optional[bool] = Query(None, description="Explicit session state for testing (True=provisional, False=completed)"),
    allow_synthetic: bool = Query(False, description="Allow calibrated synthetic data for demonstration/offline testing (Default: False)"),
) -> dict[str, Any]:
    """
    Retrieve unified Market Movers and Price-Volume Confluence intelligence.
    Returns all 4 market movers panels and 2 confluence intersection panels
    computed from a single, atomic, synchronized snapshot.
    Supports methodology selection between Daily RVOL and True Time-of-Day RVOL.
    Strictly isolates synthetic data unless allow_synthetic=True is explicitly passed.
    """
    try:
        live_quotes = _extract_live_quotes_dict()
        return get_market_movers_and_confluence(
            universe=universe,
            exchange=exchange,
            min_rvol=min_rvol,
            min_price_change_pct=min_price_change_pct,
            min_traded_value_cr=min_traded_value_cr,
            limit=limit,
            force_refresh=force_refresh,
            exclude_stale=exclude_stale,
            is_session_open=is_session_open,
            live_quotes=live_quotes,
            rvol_mode=rvol_mode,
            allow_synthetic=allow_synthetic,
        )
    except Exception as e:
        logger.exception("Error computing market movers overview: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/gainers")
def get_top_gainers_endpoint(
    universe: str = Query("all"),
    exchange: str = Query("NSE"),
    min_price_change_pct: float = Query(0.0, ge=0.0),
    min_traded_value_cr: float = Query(0.0, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
    force_refresh: bool = Query(False),
    exclude_stale: bool = Query(False),
) -> dict[str, Any]:
    """Retrieve Top Gainers sorted by highest percentage price change."""
    live_quotes = _extract_live_quotes_dict()
    res = get_market_movers_and_confluence(
        universe=universe,
        exchange=exchange,
        min_price_change_pct=min_price_change_pct,
        min_traded_value_cr=min_traded_value_cr,
        limit=limit,
        force_refresh=force_refresh,
        exclude_stale=exclude_stale,
        live_quotes=live_quotes,
    )
    return {
        "status": res.get("status", "SUCCESS"),
        "snapshot_id": res.get("calculation_snapshot_id") or res.get("snapshot_id"),
        "calculation_snapshot_id": res.get("calculation_snapshot_id"),
        "calculation_timestamp": res.get("calculation_timestamp"),
        "universe": res.get("universe"),
        "coverage": res.get("coverage"),
        "metadata": res.get("metadata"),
        "count": len(res.get("top_gainers", [])),
        "gainers": res.get("top_gainers", []),
    }


@router.get("/losers")
def get_top_losers_endpoint(
    universe: str = Query("all"),
    exchange: str = Query("NSE"),
    min_price_change_pct: float = Query(0.0, ge=0.0),
    min_traded_value_cr: float = Query(0.0, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
    force_refresh: bool = Query(False),
    exclude_stale: bool = Query(False),
) -> dict[str, Any]:
    """Retrieve Top Losers sorted by largest negative percentage price change."""
    live_quotes = _extract_live_quotes_dict()
    res = get_market_movers_and_confluence(
        universe=universe,
        exchange=exchange,
        min_price_change_pct=min_price_change_pct,
        min_traded_value_cr=min_traded_value_cr,
        limit=limit,
        force_refresh=force_refresh,
        exclude_stale=exclude_stale,
        live_quotes=live_quotes,
    )
    return {
        "status": res.get("status", "SUCCESS"),
        "snapshot_id": res.get("calculation_snapshot_id") or res.get("snapshot_id"),
        "calculation_snapshot_id": res.get("calculation_snapshot_id"),
        "calculation_timestamp": res.get("calculation_timestamp"),
        "universe": res.get("universe"),
        "coverage": res.get("coverage"),
        "metadata": res.get("metadata"),
        "count": len(res.get("top_losers", [])),
        "losers": res.get("top_losers", []),
    }


@router.get("/volume-gainers")
def get_volume_gainers_endpoint(
    universe: str = Query("all"),
    exchange: str = Query("NSE"),
    rvol_mode: str = Query("daily", description="daily or tod"),
    min_rvol: float = Query(1.5, ge=0.5, le=10.0),
    min_traded_value_cr: float = Query(0.0, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
    force_refresh: bool = Query(False),
    exclude_stale: bool = Query(False),
    allow_synthetic: bool = Query(False, description="Allow calibrated synthetic data (Default False)"),
) -> dict[str, Any]:
    """Retrieve Volume Gainers sorted by highest Relative Volume (RVOL)."""
    live_quotes = _extract_live_quotes_dict()
    res = get_market_movers_and_confluence(
        universe=universe,
        exchange=exchange,
        min_rvol=min_rvol,
        min_traded_value_cr=min_traded_value_cr,
        limit=limit,
        force_refresh=force_refresh,
        exclude_stale=exclude_stale,
        live_quotes=live_quotes,
        rvol_mode=rvol_mode,
        allow_synthetic=allow_synthetic,
    )
    return {
        "status": res.get("status", "SUCCESS"),
        "snapshot_id": res.get("calculation_snapshot_id") or res.get("snapshot_id"),
        "calculation_snapshot_id": res.get("calculation_snapshot_id"),
        "calculation_timestamp": res.get("calculation_timestamp"),
        "active_rvol_mode": res.get("active_rvol_mode"),
        "rvol_methodology_label": res.get("rvol_methodology_label"),
        "universe": res.get("universe"),
        "coverage": res.get("coverage"),
        "metadata": res.get("metadata"),
        "count": len(res.get("volume_gainers", [])),
        "volume_gainers": res.get("volume_gainers", []),
    }


@router.get("/bearish-volume")
def get_high_volume_losers_endpoint(
    universe: str = Query("all"),
    exchange: str = Query("NSE"),
    rvol_mode: str = Query("daily", description="daily or tod"),
    min_rvol: float = Query(1.5, ge=0.5, le=10.0),
    min_price_change_pct: float = Query(0.0, ge=0.0),
    min_traded_value_cr: float = Query(0.0, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
    force_refresh: bool = Query(False),
    exclude_stale: bool = Query(False),
    allow_synthetic: bool = Query(False, description="Allow calibrated synthetic data (Default False)"),
) -> dict[str, Any]:
    """Retrieve High-Volume Losers (negative price change + high RVOL)."""
    live_quotes = _extract_live_quotes_dict()
    res = get_market_movers_and_confluence(
        universe=universe,
        exchange=exchange,
        min_rvol=min_rvol,
        min_price_change_pct=min_price_change_pct,
        min_traded_value_cr=min_traded_value_cr,
        limit=limit,
        force_refresh=force_refresh,
        exclude_stale=exclude_stale,
        live_quotes=live_quotes,
        rvol_mode=rvol_mode,
        allow_synthetic=allow_synthetic,
    )
    return {
        "status": res.get("status", "SUCCESS"),
        "snapshot_id": res.get("calculation_snapshot_id") or res.get("snapshot_id"),
        "calculation_snapshot_id": res.get("calculation_snapshot_id"),
        "calculation_timestamp": res.get("calculation_timestamp"),
        "active_rvol_mode": res.get("active_rvol_mode"),
        "rvol_methodology_label": res.get("rvol_methodology_label"),
        "universe": res.get("universe"),
        "coverage": res.get("coverage"),
        "metadata": res.get("metadata"),
        "count": len(res.get("high_volume_losers", [])),
        "high_volume_losers": res.get("high_volume_losers", []),
    }


@router.get("/confluence")
def get_confluence_endpoint(
    universe: str = Query("all"),
    exchange: str = Query("NSE"),
    rvol_mode: str = Query("daily", description="daily or tod"),
    min_rvol: float = Query(1.5, ge=0.5, le=10.0),
    min_price_change_pct: float = Query(0.0, ge=0.0),
    min_traded_value_cr: float = Query(0.0, ge=0.0),
    limit: int = Query(10, ge=1, le=100),
    force_refresh: bool = Query(False),
    exclude_stale: bool = Query(False),
    allow_synthetic: bool = Query(False, description="Allow calibrated synthetic data (Default False)"),
) -> dict[str, Any]:
    """
    Retrieve Bullish Confluence (Gainers ∩ Volume Gainers) and
    Bearish Confluence (Losers ∩ Volume Gainers) intersection panels.
    """
    live_quotes = _extract_live_quotes_dict()
    res = get_market_movers_and_confluence(
        universe=universe,
        exchange=exchange,
        min_rvol=min_rvol,
        min_price_change_pct=min_price_change_pct,
        min_traded_value_cr=min_traded_value_cr,
        limit=limit,
        force_refresh=force_refresh,
        exclude_stale=exclude_stale,
        live_quotes=live_quotes,
        rvol_mode=rvol_mode,
        allow_synthetic=allow_synthetic,
    )
    return {
        "status": res.get("status", "SUCCESS"),
        "snapshot_id": res.get("calculation_snapshot_id") or res.get("snapshot_id"),
        "calculation_snapshot_id": res.get("calculation_snapshot_id"),
        "calculation_timestamp": res.get("calculation_timestamp"),
        "active_rvol_mode": res.get("active_rvol_mode"),
        "rvol_methodology_label": res.get("rvol_methodology_label"),
        "universe": res.get("universe"),
        "coverage": res.get("coverage"),
        "metadata": res.get("metadata"),
        "bullish_confluence": res.get("bullish_confluence", []),
        "bearish_confluence": res.get("bearish_confluence", []),
        "bullish_count": len(res.get("bullish_confluence", [])),
        "bearish_count": len(res.get("bearish_confluence", [])),
    }


# ---------------------------------------------------------------------------
# Intraday Ingestion & Telemetry Endpoints (Phase 14.2)
# ---------------------------------------------------------------------------

@router.get("/intraday/status")
def get_intraday_status_endpoint(
    allow_synthetic: bool = Query(False, description="Audit status with synthetic mode enabled"),
) -> dict[str, Any]:
    """Retrieve 5-minute historical bar ingestion status across all tracked stocks."""
    from app.services.intraday_data_service import get_intraday_ingestion_status
    try:
        return get_intraday_ingestion_status(allow_synthetic=allow_synthetic)
    except Exception as e:
        logger.exception("Error checking intraday ingestion status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intraday/seed")
def seed_intraday_data_endpoint(
    sessions: int = Query(20, ge=1, le=60, description="Number of trading sessions to seed"),
    force: bool = Query(False, description="Force overwrite existing intraday bars"),
) -> dict[str, Any]:
    """Seed 5-minute intraday historical bars for all tracked NSE stocks."""
    from app.services.intraday_data_service import seed_all_tracked_stocks_intraday
    try:
        return seed_all_tracked_stocks_intraday(num_sessions=sessions, force=force)
    except Exception as e:
        logger.exception("Error seeding intraday data: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intraday/providers")
def get_intraday_providers_endpoint() -> dict[str, Any]:
    """Evaluate configured market data providers for intraday OHLCV bars."""
    from app.services.intraday_data_service import assess_intraday_data_providers
    try:
        return assess_intraday_data_providers()
    except Exception as e:
        logger.exception("Error assessing intraday providers: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intraday/ingestions")
def get_intraday_ingestions_endpoint(
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, Any]:
    """Return recent intraday ingestion audit records without exposing provider secrets."""
    try:
        runs = list_ingestion_runs(limit=limit)
        safe_runs = []
        for run in runs:
            error = run.get("error_message")
            if error and run.get("provider") != "yfinance":
                error = "Provider error details are withheld."
            elif error:
                error = str(error)[:1500]
            safe_runs.append({
                "id": run.get("id"),
                "symbol": run.get("symbol"),
                "provider": run.get("provider"),
                "provider_symbol": run.get("provider_symbol"),
                "exchange": run.get("exchange"),
                "interval": run.get("interval"),
                "start_date": run.get("start_date"),
                "end_date": run.get("end_date"),
                "actual_start_date": run.get("actual_start_date"),
                "actual_end_date": run.get("actual_end_date"),
                "bar_count": run.get("bar_count"),
                "retrieval_timestamp": run.get("retrieval_timestamp"),
                "raw_response_hash": run.get("raw_response_hash"),
                "provenance_classification": run.get("provenance_classification"),
                "data_quality_status": run.get("data_quality_status"),
                "provider_metadata": json.loads(run["provider_metadata_json"])
                if run.get("provider_metadata_json") else None,
                "session_quality": json.loads(run["session_quality_json"])
                if run.get("session_quality_json") else None,
                "error_message": error,
                "created_at": run.get("created_at"),
            })
        return {"runs": safe_runs}
    except Exception as e:
        logger.exception("Error listing intraday ingestion records: %s", e)
        raise HTTPException(status_code=500, detail="Unable to load intraday ingestion records.")
