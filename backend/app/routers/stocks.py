"""Stocks API router."""

from fastapi import APIRouter, HTTPException

from app.database import get_bars, get_stock, list_stocks, get_sectors, get_exchanges
from app.services.indicators import calculate_all_indicators

router = APIRouter(prefix="/api", tags=["stocks"])


@router.get("/stocks")
def stocks(
    exchange: str | None = None,
    sector: str | None = None,
    cap_category: str | None = None,
    search: str | None = None,
):
    """List all stocks, optionally filtered by universe criteria."""
    items = list_stocks(
        exchange=exchange,
        sector=sector,
        cap_category=cap_category,
        search=search,
    )
    return {"items": items, "total": len(items), "data_mode": "demo"}


@router.get("/stocks/{symbol}")
def stock_detail(symbol: str):
    """Get detailed info for a single stock."""
    item = get_stock(symbol.upper())
    if not item:
        raise HTTPException(status_code=404, detail="Stock not found")
    bars = get_bars(symbol.upper())
    indicators = calculate_all_indicators(bars) if bars else {"message": "No OHLCV data"}
    return {
        "stock": item,
        "bars": bars[-30:] if bars else [],   # last 30 bars for quick view
        "indicators": indicators,
        "data_source": item.get("data_source", "demo"),
        "data_mode": item.get("data_source", "demo"),
    }


@router.get("/market/overview")
def market_overview():
    """Return market overview data."""
    return {
        "sectors": get_sectors(),
        "exchanges": get_exchanges(),
        "data_mode": "demo",
        "notice": "Market overview with illustrative data.",
    }
