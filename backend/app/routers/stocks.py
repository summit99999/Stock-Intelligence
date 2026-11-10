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


@router.get("/stocks/search")
def search_stocks(q: str = "", limit: int = 15):
    """Search full NSE universe (~3,400 instruments) by symbol, company name, or ISIN."""
    from app.services.nse_universe_service import search_nse_universe
    results = search_nse_universe(query=q, limit=limit)
    return {"query": q, "count": len(results), "items": results}


@router.get("/stocks/{symbol}")
def stock_detail(symbol: str):
    """Get detailed info for a single stock with canonical price guarantees."""
    sym_upper = symbol.upper()
    item = get_stock(sym_upper)
    if not item:
        raise HTTPException(status_code=404, detail="Stock not found")

    from app.services.canonical_market_data_service import get_canonical_market_data_service
    canonical = get_canonical_market_data_service().get_quote(sym_upper)
    item["close"] = canonical["ltp"]
    item["daily_change_pct"] = canonical["change_pct"]
    item["volume"] = canonical["volume"]
    item["data_source"] = canonical["data_source"]

    bars = get_bars(sym_upper)
    indicators = calculate_all_indicators(bars) if bars else {"message": "No OHLCV data"}
    return {
        "stock": item,
        "canonical_quote": canonical,
        "bars": bars[-30:] if bars else [],   # last 30 bars for quick view
        "indicators": indicators,
        "data_source": canonical["data_source"],
        "data_mode": canonical["data_status"],
    }


@router.get("/stocks/{symbol}/history")
def stock_history(symbol: str, interval: str = "daily", limit: int = 300):
    """Get historical OHLCV candles for charting."""
    sym_upper = symbol.upper()
    item = get_stock(sym_upper)
    if not item:
        raise HTTPException(status_code=404, detail=f"Stock {sym_upper} not found")
    bars = get_bars(sym_upper, interval=interval)
    if not bars:
        try:
            from app.providers.manager import get_provider
            provider = get_provider()
            bars = provider.get_daily_candles(sym_upper, period="1y")
        except Exception:
            bars = []
    sliced = bars[-limit:] if bars else []
    return {
        "symbol": sym_upper,
        "interval": interval,
        "count": len(sliced),
        "bars": sliced,
        "data_source": item.get("data_source", "demo"),
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
