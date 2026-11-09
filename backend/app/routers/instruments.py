"""
FastAPI router for NSE Instrument Master, Symbol Resolution, and Corporate Action Auditing.
Phase 14.9 — Exposes authoritative universe metadata, provider mappings, and reconciliation tables.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.services.instrument_master_service import get_instrument_master_service

router = APIRouter(prefix="/api/instruments", tags=["instruments"])


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
