"""
Professional Market Intelligence & Scanner API Router (Phase 11).

Endpoints:
- Market Overview Dashboard: /api/market/intelligence/dashboard
- Sector Intelligence: /api/market/intelligence/sectors
- Advanced Multi-Condition Scan: /api/scanner/advanced/scan
- Export Scan to CSV: /api/scanner/advanced/export-csv
- Custom Saved Scanners: /api/scanner/custom/...
- Custom Watchlists: /api/watchlists/...
- Real-Time Market Alerts: /api/alerts/...
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.auth import get_current_user

from app.database import (
    add_symbol_to_watchlist,
    clear_market_alert_history,
    create_custom_watchlist,
    create_market_alert,
    delete_custom_scanner,
    delete_custom_watchlist,
    delete_market_alert,
    get_custom_scanner,
    get_custom_watchlist,
    get_market_alert,
    get_market_alert_history,
    list_custom_scanners,
    list_custom_watchlists,
    list_market_alerts,
    remove_symbol_from_watchlist,
    save_custom_scanner,
    update_custom_scanner,
    update_custom_watchlist,
    update_market_alert,
)
from app.services.advanced_scanner_service import (
    export_scan_to_csv,
    run_advanced_scan,
)
from app.services.alerts_watchlist_service import (
    evaluate_active_alerts,
    get_enriched_watchlist,
)
from app.services.market_intelligence_service import (
    get_market_overview,
    get_sector_intelligence,
)

router = APIRouter(tags=["Market Intelligence & Advanced Scanner"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class AdvancedScanPayload(BaseModel):
    universe: str = Field("all", description="all, nifty50, nifty100, nifty500, fno")
    ranking_preset: Optional[str] = Field(None, description="BULLISH_OPPORTUNITY, etc.")
    logic_mode: str = Field("AND", description="AND or OR")
    filters: dict[str, Any] = Field(default_factory=dict)
    sort_by: Optional[str] = None
    sort_order: str = Field("desc", description="desc or asc")
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class SaveCustomScannerPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    universe: str = Field("all")
    timeframe: str = Field("1D")
    logic_mode: str = Field("AND")
    conditions: dict[str, Any] = Field(default_factory=dict)


class CreateWatchlistPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    symbols: list[str] = Field(default_factory=list)


class AddSymbolPayload(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)


class CreateAlertPayload(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=30)
    alert_type: str = Field(..., description="PRICE_ABOVE, PRICE_BELOW, RSI_ABOVE, RSI_BELOW, VOLUME_SPIKE, BREAKOUT_52W, EMA_CROSSOVER, OB_RETEST, FVG_RETEST")
    target_value: Optional[float] = None
    timeframe: str = Field("1D")
    note: str = Field("", max_length=500)


class UpdateAlertPayload(BaseModel):
    status: Optional[str] = None
    target_value: Optional[float] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. Market Intelligence Dashboard & Sector Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/market/intelligence/dashboard")
def get_dashboard_overview(
    universe: str = Query("all", description="all, nifty50, nifty100, nifty500, fno"),
    force_refresh: bool = Query(False, description="Bypass cache"),
) -> dict[str, Any]:
    """
    Get comprehensive market overview, benchmark indices, breadth meter,
    52W extremes, regime score, and leaders/laggards.
    """
    return get_market_overview(universe=universe, force_refresh=force_refresh)


@router.get("/api/market/intelligence/sectors")
def get_sectors_overview(
    universe: str = Query("all"),
    force_refresh: bool = Query(False),
) -> dict[str, Any]:
    """
    Get deep sector intelligence, performance rankings, relative strength vs market,
    rotation quadrants (Leading/Weakening/Lagging/Improving), and breadth.
    """
    return get_sector_intelligence(universe=universe, force_refresh=force_refresh)


# ---------------------------------------------------------------------------
# 2. Advanced Multi-Condition Scanner Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/scanner/advanced/scan")
def scan_advanced(payload: AdvancedScanPayload) -> dict[str, Any]:
    """
    Execute advanced multi-condition technical & fundamental scan with 7 ranking systems,
    AND/OR logic, and pagination.
    """
    return run_advanced_scan(
        universe=payload.universe,
        ranking_preset=payload.ranking_preset,
        logic_mode=payload.logic_mode,
        filters=payload.filters,
        sort_by=payload.sort_by,
        sort_order=payload.sort_order,
        page=payload.page,
        page_size=payload.page_size,
    )


@router.get("/api/scanner/advanced/export-csv")
def export_advanced_scan_csv(
    universe: str = Query("all"),
    ranking_preset: Optional[str] = Query(None),
    logic_mode: str = Query("AND"),
) -> Response:
    """
    Export current scan results into standard CSV download.
    """
    scan_res = run_advanced_scan(
        universe=universe,
        ranking_preset=ranking_preset,
        logic_mode=logic_mode,
        page=1,
        page_size=100,
    )
    csv_text = export_scan_to_csv(scan_res)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="stock_scanner_export.csv"'},
    )


# ---------------------------------------------------------------------------
# 3. Custom Scanner Builder (CRUD)
# ---------------------------------------------------------------------------

@router.get("/api/scanner/custom/saved")
def get_custom_scanners_list(
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all saved custom scanner definitions for the authenticated user."""
    scanners = list_custom_scanners(user_id=current_user["id"])
    for s in scanners:
        try:
            s["conditions"] = json.loads(s.get("conditions_json", "{}"))
        except Exception:
            s["conditions"] = {}
    return scanners


@router.post("/api/scanner/custom/save")
def create_custom_scanner_endpoint(
    payload: SaveCustomScannerPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Create and save a new custom scanner configuration."""
    cond_str = json.dumps(payload.conditions)
    sc_id = save_custom_scanner(
        name=payload.name,
        description=payload.description,
        universe=payload.universe,
        timeframe=payload.timeframe,
        logic_mode=payload.logic_mode,
        conditions_json=cond_str,
        user_id=current_user["id"],
    )
    return {
        "status": "success",
        "id": sc_id,
        "name": payload.name,
        "message": "Custom scanner successfully saved.",
    }


@router.put("/api/scanner/custom/{scanner_id}")
def update_custom_scanner_endpoint(
    scanner_id: int,
    payload: SaveCustomScannerPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Update an existing saved custom scanner."""
    cond_str = json.dumps(payload.conditions)
    ok = update_custom_scanner(
        scanner_id=scanner_id,
        name=payload.name,
        description=payload.description,
        universe=payload.universe,
        timeframe=payload.timeframe,
        logic_mode=payload.logic_mode,
        conditions_json=cond_str,
        user_id=current_user["id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Custom scanner not found.")
    return {"status": "success", "message": "Custom scanner updated successfully."}


@router.delete("/api/scanner/custom/{scanner_id}")
def delete_custom_scanner_endpoint(
    scanner_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a saved custom scanner."""
    ok = delete_custom_scanner(scanner_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Custom scanner not found.")
    return {"status": "success", "message": "Custom scanner deleted."}


# ---------------------------------------------------------------------------
# 4. Custom Watchlists (Multi-Watchlist Management)
# ---------------------------------------------------------------------------

@router.get("/api/watchlists")
def get_all_watchlists(
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all custom watchlists with summary info for the authenticated user."""
    raw_list = list_custom_watchlists(user_id=current_user["id"])
    results = []
    for wl in raw_list:
        try:
            syms = json.loads(wl.get("symbols_json", "[]"))
        except Exception:
            syms = []
        results.append({
            "id": wl["id"],
            "name": wl["name"],
            "description": wl.get("description", ""),
            "symbol_count": len(syms),
            "symbols": syms,
            "created_at": wl.get("created_at"),
            "updated_at": wl.get("updated_at"),
        })
    return results


@router.get("/api/watchlists/{watchlist_id}")
def get_watchlist_detail(
    watchlist_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Get enriched watchlist by ID with live/database price data."""
    enriched = get_enriched_watchlist(watchlist_id, user_id=current_user["id"])
    if not enriched:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return enriched


@router.post("/api/watchlists")
def create_watchlist_endpoint(
    payload: CreateWatchlistPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new custom watchlist."""
    wl_id = create_custom_watchlist(
        name=payload.name,
        description=payload.description,
        symbols=payload.symbols,
        user_id=current_user["id"],
    )
    return {
        "status": "success",
        "id": wl_id,
        "name": payload.name,
        "message": "Watchlist created successfully.",
    }


@router.put("/api/watchlists/{watchlist_id}")
def update_watchlist_endpoint(
    watchlist_id: int,
    payload: CreateWatchlistPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Update watchlist details or symbol list."""
    ok = update_custom_watchlist(
        watchlist_id=watchlist_id,
        name=payload.name,
        description=payload.description,
        symbols=payload.symbols,
        user_id=current_user["id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"status": "success", "message": "Watchlist updated successfully."}


@router.delete("/api/watchlists/{watchlist_id}")
def delete_watchlist_endpoint(
    watchlist_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete a watchlist."""
    ok = delete_custom_watchlist(watchlist_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"status": "success", "message": "Watchlist deleted."}


@router.post("/api/watchlists/{watchlist_id}/symbols")
def add_symbol_endpoint(
    watchlist_id: int,
    payload: AddSymbolPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Add a stock symbol to a watchlist."""
    ok = add_symbol_to_watchlist(watchlist_id, payload.symbol, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"status": "success", "message": f"{payload.symbol.upper()} added to watchlist."}


@router.delete("/api/watchlists/{watchlist_id}/symbols/{symbol}")
def remove_symbol_endpoint(
    watchlist_id: int,
    symbol: str,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove a stock symbol from a watchlist."""
    ok = remove_symbol_from_watchlist(watchlist_id, symbol, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return {"status": "success", "message": f"{symbol.upper()} removed from watchlist."}


# ---------------------------------------------------------------------------
# 5. Market Alerts & Alert Trigger Evaluation
# ---------------------------------------------------------------------------

@router.get("/api/alerts")
def get_alerts_endpoint(
    status: Optional[str] = Query(None, description="ACTIVE, MUTED, TRIGGERED"),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all market alerts for authenticated user."""
    return list_market_alerts(status=status, user_id=current_user["id"])


@router.post("/api/alerts")
def create_alert_endpoint(
    payload: CreateAlertPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new technical or price alert rule."""
    alert_id = create_market_alert(
        symbol=payload.symbol,
        alert_type=payload.alert_type,
        target_value=payload.target_value,
        timeframe=payload.timeframe,
        note=payload.note,
        user_id=current_user["id"],
    )
    return {
        "status": "success",
        "id": alert_id,
        "message": f"Alert rule #{alert_id} for {payload.symbol.upper()} created.",
    }


@router.put("/api/alerts/{alert_id}")
def update_alert_endpoint(
    alert_id: int,
    payload: UpdateAlertPayload,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Update alert status (e.g. MUTE/ACTIVE), target value, or note."""
    ok = update_market_alert(
        alert_id=alert_id,
        status=payload.status,
        target_value=payload.target_value,
        note=payload.note,
        user_id=current_user["id"],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"status": "success", "message": "Alert updated successfully."}


@router.delete("/api/alerts/{alert_id}")
def delete_alert_endpoint(
    alert_id: int,
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Delete an alert rule."""
    ok = delete_market_alert(alert_id, user_id=current_user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return {"status": "success", "message": "Alert deleted."}


@router.post("/api/alerts/evaluate")
def evaluate_alerts_endpoint(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Run the automated alert evaluation engine against current market indicators and SMC levels.
    """
    triggered = evaluate_active_alerts()
    return {
        "status": "success",
        "evaluated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "triggered_count": len(triggered),
        "triggered_events": triggered,
    }


@router.get("/api/alerts/history")
def get_alerts_history_endpoint(
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Retrieve logged alert trigger history events for authenticated user."""
    return get_market_alert_history(limit=limit, user_id=current_user["id"])


@router.delete("/api/alerts/history")
def clear_alerts_history_endpoint(
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Clear all alert trigger history events for authenticated user."""
    deleted_count = clear_market_alert_history(user_id=current_user["id"])
    return {"status": "success", "cleared_count": deleted_count}
