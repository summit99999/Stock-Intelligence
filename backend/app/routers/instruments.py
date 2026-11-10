"""
FastAPI router for NSE Instrument Master, Symbol Resolution, and Corporate Action Auditing.
Phase 14.9 — Exposes authoritative universe metadata, provider mappings, and reconciliation tables.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.services.instrument_master_service import get_instrument_master_service

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


@router.get("/search")
def search_instruments(
    q: str = Query("", description="Symbol, company name, or ISIN"),
    exchange: Optional[str] = Query(None, description="Filter by exchange (NSE, BSE)"),
    limit: int = Query(15, ge=1, le=100),
):
    """Search full market universe across symbols, company names, and ISINs."""
    from app.services.nse_universe_service import search_market_universe
    exch_str = str(exchange) if (exchange and not hasattr(exchange, "default")) else None
    q_str = str(q) if (q and not hasattr(q, "default")) else ""
    lim_int = int(limit) if (limit and not hasattr(limit, "default")) else 15
    items = search_market_universe(query=q_str, exchange=exch_str, limit=lim_int)
    return {"query": q_str, "exchange": exch_str, "count": len(items), "items": items}


@router.post("/sync")
def trigger_instrument_sync(force: bool = Query(False, description="Force full re-sync")):
    """Trigger on-demand synchronization of the full market instrument master."""
    from app.services.nse_universe_service import sync_full_market_universe
    return sync_full_market_universe(force=force)


@router.get("/coverage")
def get_universe_coverage():
    """Retrieve comprehensive instrument coverage statistics across all exchanges and segments."""
    import datetime
    from app.services.nse_universe_service import get_db_connection
    with get_db_connection() as con:
        total_market = con.execute("SELECT COUNT(*) FROM market_instruments").fetchone()[0]
        nse_eq = con.execute("SELECT COUNT(*) FROM nse_instruments").fetchone()[0]
        stocks_count = con.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        nifty50_count = con.execute("SELECT COUNT(*) FROM market_instruments WHERE is_nifty50 = 1").fetchone()[0]
        fno_count = con.execute("SELECT COUNT(*) FROM market_instruments WHERE is_fno = 1 AND instrument_type = 'EQ'").fetchone()[0]
        bse_count = con.execute("SELECT COUNT(*) FROM market_instruments WHERE exchange = 'BSE'").fetchone()[0]
        indices_count = con.execute("SELECT COUNT(*) FROM market_instruments WHERE instrument_type = 'INDEX'").fetchone()[0]
        options_count = con.execute("SELECT COUNT(*) FROM market_instruments WHERE instrument_type IN ('CE', 'PE')").fetchone()[0]

    return {
        "total_market_instruments": total_market,
        "active_nse_equities": nse_eq,
        "stocks_screener_universe": stocks_count,
        "nifty50_count": nifty50_count,
        "fno_eligible_count": fno_count,
        "bse_instruments_count": bse_count,
        "indices_count": indices_count,
        "options_contracts_count": options_count,
        "coverage_status": "FULL_MARKET_COVERAGE",
        "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("", response_model=List[Dict[str, Any]])
def list_instruments(active_only: bool = Query(False, description="Filter for ACTIVE status only")):
    """List all tracked securities in the authoritative instrument master."""
    svc = get_instrument_master_service()
    instruments = svc.get_universe_reconciliation()
    if active_only:
        instruments = [i for i in instruments if i.get("status") == "ACTIVE"]
    return instruments


@router.get("/reconciliation", response_model=List[Dict[str, Any]])
def get_reconciliation_table():
    """
    Returns the comprehensive 31-stock Universe Reconciliation Table covering:
    - Internal Instrument ID
    - Current NSE Symbol
    - Company Name & ISIN
    - Historical Symbols & Change Dates
    - Yahoo Finance & Dhan Provider Mappings & Status
    - F&O Eligibility & CAS Schedule Version
    - Observed 5-minute and Daily Bar Counts
    - Corporate Action Notes
    """
    svc = get_instrument_master_service()
    return svc.get_universe_reconciliation()


@router.get("/corporate-actions", response_model=List[Dict[str, Any]])
def list_all_corporate_actions():
    """Retrieve all corporate actions registered in the system."""
    svc = get_instrument_master_service()
    return svc.get_corporate_actions()


@router.get("/{symbol_or_id}")
def get_instrument_detail(symbol_or_id: str):
    """
    Resolve an instrument by its internal ID, ISIN, current symbol, historical ticker,
    or provider symbol. Returns full metadata, mappings, and corporate actions.
    """
    svc = get_instrument_master_service()
    inst = svc.resolve_instrument(symbol_or_id)
    if not inst:
        raise HTTPException(
            status_code=404,
            detail=f"Security '{symbol_or_id}' could not be resolved in the Authoritative Instrument Master.",
        )

    inst_id = inst["instrument_id"]
    from app.database import get_provider_mappings
    mappings = get_provider_mappings(instrument_id=inst_id)
    corporate_actions = svc.get_corporate_actions(symbol_or_id)

    return {
        "instrument": inst,
        "provider_mappings": mappings,
        "corporate_actions": corporate_actions,
    }
