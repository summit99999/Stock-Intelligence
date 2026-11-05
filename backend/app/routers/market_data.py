"""Market data API router — data downloads, status, history, indicators."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.database import (
    get_all_symbols,
    get_bars,
    get_ohlcv_count,
    get_latest_bar_date,
    get_stock,
    list_data_updates,
)
from app.providers.manager import get_provider_manager
from app.schemas.market_data import (
    DataUpdateStatus,
    HistoryResponse,
    IndicatorsResponse,
    JobStatus,
    MarketDataStatus,
    OHLCVBar,
    UpdateRequest,
    UpdateResponse,
)
from app.services.indicators import calculate_all_indicators
from app.services.market_data_service import start_background_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["market-data"])


# ---------------------------------------------------------------------------
# Data update endpoints
# ---------------------------------------------------------------------------

@router.post("/market-data/update", response_model=UpdateResponse)
def trigger_update(request: UpdateRequest):
    """
    Trigger a background download of historical market data.

    If ``symbols`` is empty, updates all stocks in the universe.
    Returns a job ID for status tracking — does not block.
    """
    mgr = get_provider_manager()
    if not mgr.active_provider:
        raise HTTPException(
            status_code=503,
            detail="No data provider available. Ensure yfinance is installed.",
        )

    symbols = request.symbols if request.symbols else None
    actual_count = len(request.symbols) if request.symbols else len(get_all_symbols())

    job_id = start_background_update(
        symbols=symbols,
        period=request.period,
        force=request.force,
    )

    return UpdateResponse(
        job_id=job_id,
        status="started",
        message=f"Background update started for {actual_count} stock(s)",
        symbols_count=actual_count,
    )


@router.get("/market-data/status", response_model=MarketDataStatus)
def data_status():
    """Return the overall market-data status."""
    mgr = get_provider_manager()
    attr = mgr.get_attribution()

    updates = list_data_updates()
    all_syms = get_all_symbols()

    # Count total bars across all symbols
    total_bars = sum(u.get("bars_count", 0) for u in updates)
    stocks_with_data = sum(1 for u in updates if u.get("status") == "ok")

    return MarketDataStatus(
        provider_name=attr.name if attr else None,
        provider_data_type=attr.data_type if attr else None,
        provider_available=mgr.active_provider is not None,
        total_stocks=len(all_syms),
        stocks_with_data=stocks_with_data,
        total_bars=total_bars,
        updates=[
            DataUpdateStatus(
                symbol=u["symbol"],
                provider=u["provider"],
                last_updated=u.get("last_updated"),
                bars_count=u.get("bars_count", 0),
                period=u.get("period"),
                status=u.get("status", "unknown"),
                error_message=u.get("error_message"),
            )
            for u in updates
        ],
    )


@router.get("/market/provider/status")
def provider_status():
    """Return granular diagnostic information about market data providers."""
    import os
    from app.config import get_dhan_config
    from app.services.token_store import get_token

    mgr = get_provider_manager()
    attr = mgr.get_attribution()
    dhan_cfg = get_dhan_config()
    tok = get_token()

    dhan_avail = bool(dhan_cfg.is_configured and tok and tok.access_token and not tok.is_expired)

    return {
        "active_provider": attr.name if attr else "None",
        "provider_data_type": attr.data_type if attr else "None",
        "provider_note": attr.note if attr else "",
        "preferred_provider": os.getenv("MARKET_DATA_PROVIDER", "yfinance").lower(),
        "dhan_configured": dhan_cfg.is_configured,
        "dhan_token_valid": bool(tok and tok.access_token and not tok.is_expired),
        "dhan_live_enabled": dhan_cfg.live_data_enabled,
        "yfinance_available": True,
    }


@router.get("/market-data/jobs/{job_id}", response_model=JobStatus)
def job_status(job_id: str):
    """Get the status of a background update job."""
    mgr = get_provider_manager()
    job = mgr.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatus(
        job_id=job.job_id,
        status=job.status,
        total=job.total,
        completed_count=job.completed_count,
        failed_count=job.failed_count,
        started_at=job.started_at,
        finished_at=job.finished_at,
        symbols_done=job.symbols_done,
        errors=job.errors,
    )


# ---------------------------------------------------------------------------
# Stock history & indicators
# ---------------------------------------------------------------------------

@router.get("/stocks/{symbol}/history", response_model=HistoryResponse)
def stock_history(symbol: str, interval: str = "daily"):
    """Return OHLCV price history for a stock."""
    sym = symbol.upper()
    stock = get_stock(sym)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {sym} not found")

    bars = get_bars(sym, interval)
    latest = get_latest_bar_date(sym, interval)
    source = stock.get("data_source", "demo")

    return HistoryResponse(
        symbol=sym,
        exchange=stock.get("exchange", "NSE"),
        bars=[
            OHLCVBar(
                date=b.get("timestamp", b.get("date", "")),
                open=b.get("open"),
                high=b.get("high"),
                low=b.get("low"),
                close=b.get("close"),
                adj_close=b.get("adj_close"),
                volume=b.get("volume"),
            )
            for b in bars
        ],
        total_bars=len(bars),
        latest_date=latest,
        data_source=source,
        notice=(
            "Historical data from Yahoo Finance — not live exchange prices."
            if source == "yfinance"
            else "Demonstration data — not actual market data."
        ),
    )


@router.get("/stocks/{symbol}/indicators", response_model=IndicatorsResponse)
def stock_indicators(symbol: str):
    """Calculate and return technical indicators for a stock."""
    sym = symbol.upper()
    stock = get_stock(sym)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {sym} not found")

    bars = get_bars(sym, "daily")
    source = stock.get("data_source", "demo")

    if not bars:
        return IndicatorsResponse(
            symbol=sym,
            exchange=stock.get("exchange", "NSE"),
            indicators={"message": "No OHLCV data available for indicator calculation"},
            bars_count=0,
            data_source=source,
        )

    indicators = calculate_all_indicators(bars)

    return IndicatorsResponse(
        symbol=sym,
        exchange=stock.get("exchange", "NSE"),
        indicators=indicators,
        bars_count=len(bars),
        data_source=source,
        notice=(
            "Indicators calculated from historical Yahoo Finance data."
            if source == "yfinance"
            else "Indicators calculated from demonstration data."
        ),
    )
