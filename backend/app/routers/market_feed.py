"""Market Feed API router — live quotes, live feed status, and WebSocket streaming via Upstox."""

from __future__ import annotations

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from app.schemas.upstox_market import (
    LiveFeedStatus,
    LiveQuote,
    LiveQuotesResponse,
    MarketDataHealthDiagnostics,
    SubscribeRequest,
)
from app.services.upstox_market_service import get_upstox_market_service
from app.services.upstox_ws_client import get_upstox_ws_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["live-market-feed"])


@router.get("/api/health/market-data", response_model=MarketDataHealthDiagnostics)
def get_market_data_health():
    """
    Diagnostic health check for Upstox Market Data Feed V3 (Phase 8).
    
    Provides real-time inspection of backend lifecycle, Upstox authentication,
    WebSocket connection state, Protobuf decoder health, subscribed instruments,
    market hours status, and data freshness.
    """
    client = get_upstox_ws_client()
    return client.get_diagnostics()


@router.get("/api/market/live/status", response_model=LiveFeedStatus)
def get_live_feed_status():
    """Return status and diagnostics for the Upstox live market feed."""
    client = get_upstox_ws_client()
    return client.get_feed_status()


@router.get("/api/market/live/quotes", response_model=LiveQuotesResponse)
async def get_live_quotes(symbols: Optional[str] = None):
    """
    Return current live quotes snapshot for subscribed or requested symbols.
    symbols: optional comma-separated list of symbols (e.g. RELIANCE,TCS,NIFTY 50).
    """
    market_svc = get_upstox_market_service()
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None

    # First check if quotes are in cache
    quotes = market_svc.get_all_cached_quotes()
    if sym_list:
        filtered = {s: quotes[s] for s in sym_list if s in quotes}
        # If any requested symbol is missing from cache, fetch or fallback
        missing = [s for s in sym_list if s not in filtered]
        if missing:
            fetched = await market_svc.fetch_quotes(symbols=missing)
            filtered.update(fetched)
        quotes = filtered
    elif not quotes:
        quotes = await market_svc.fetch_quotes()

    predominant_source = "LIVE"
    if not quotes or any(q.source == "DEMO" for q in quotes.values()):
        predominant_source = "DEMO" if all(q.source == "DEMO" for q in quotes.values()) else "HYBRID"

    return LiveQuotesResponse(
        quotes=quotes,
        source=predominant_source,
        count=len(quotes),
    )


@router.get("/api/market/live/quote/{symbol}", response_model=LiveQuote)
async def get_live_quote_single(symbol: str):
    """Return current live quote for a single symbol or index."""
    market_svc = get_upstox_market_service()
    sym = symbol.strip().upper()

    cached = market_svc.get_cached_quote(sym)
    if cached:
        return cached

    quotes = await market_svc.fetch_quotes(symbols=[sym])
    if sym in quotes:
        return quotes[sym]

    raise HTTPException(
        status_code=404,
        detail=f"Quote not found for symbol '{symbol}'. Ensure it is a valid instrument.",
    )


@router.post("/api/market/live/subscribe", response_model=LiveFeedStatus)
async def subscribe_symbols(req: SubscribeRequest):
    """Subscribe to additional symbols on the live feed."""
    client = get_upstox_ws_client()
    await client.subscribe(req.symbols)
    return client.get_feed_status()


@router.post("/api/market/live/reconnect", response_model=LiveFeedStatus)
async def reconnect_live_feed(force: bool = True, enable: bool = False):
    """
    Manually trigger reconnection to the Upstox live market feed.
    Can be used after updating access tokens or enabling live data mode.
    """
    client = get_upstox_ws_client()
    return await client.manual_reconnect(force=force, enable=enable)


@router.post("/api/market/live/refresh", response_model=LiveQuotesResponse)
async def refresh_quotes():
    """Trigger an immediate REST snapshot refresh from Upstox."""
    market_svc = get_upstox_market_service()
    quotes = await market_svc.fetch_quotes()
    predominant = "LIVE" if all(q.source == "LIVE" for q in quotes.values()) else "DEMO"
    return LiveQuotesResponse(
        quotes=quotes,
        source=predominant,
        count=len(quotes),
    )


@router.websocket("/ws/market-feed")
async def websocket_market_feed(websocket: WebSocket):
    """
    FastAPI WebSocket endpoint for frontend clients.

    Streams real-time market updates, ticks, and status changes.
    Frontend clients connect to ws://{host}:{port}/ws/market-feed.
    """
    await websocket.accept()
    ws_client = get_upstox_ws_client()
    await ws_client.register_frontend_client(websocket)

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                msg_type = msg.get("type", "").upper()
                if msg_type == "SUBSCRIBE":
                    symbols = msg.get("symbols", [])
                    if symbols:
                        await ws_client.subscribe(symbols)
                elif msg_type == "PING":
                    await websocket.send_text(json.dumps({"type": "PONG"}))
            except Exception as e:
                logger.warning(f"Error handling frontend WebSocket message: {e}")
    except WebSocketDisconnect:
        logger.info("Frontend WebSocket client disconnected")
    except Exception as e:
        logger.warning(f"Frontend WebSocket exception: {e}")
    finally:
        ws_client.unregister_frontend_client(websocket)
