"""Upstox Market Data Feed WebSocket client.

Connects to Upstox Market Data Feed v2 via:
1. REST authorization: GET /v2/feed/market-data-feed/authorize
2. WebSocket connection to the returned authorized URI
3. Subscribing to instrument keys and broadcasting real-time ticks to connected UI clients
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Set
from fastapi import WebSocket
import httpx

from app.config import get_upstox_config
from app.schemas.upstox_market import LiveFeedStatus, LiveQuote
from app.services.token_store import get_upstox_token
from app.services.upstox_instrument_service import get_upstox_instrument_service
from app.services.upstox_market_service import get_upstox_market_service

logger = logging.getLogger(__name__)

UPSTOX_WS_AUTH_URL = "https://api.upstox.com/v2/feed/market-data-feed/authorize"
DEFAULT_SUBSCRIPTIONS = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "NIFTY 50"]


class UpstoxWebSocketClient:
    """Manages the Upstox Market Data Feed WebSocket connection lifecycle."""

    def __init__(self):
        self.market_service = get_upstox_market_service()
        self.instrument_service = get_upstox_instrument_service()

        self._status: str = "DISCONNECTED"
        self._subscribed_symbols: Set[str] = set(DEFAULT_SUBSCRIPTIONS)
        self._subscribed_keys: Set[str] = set()
        self._frontend_clients: Set[WebSocket] = set()

        self._last_tick_time: Optional[str] = None
        self._ticks_received: int = 0
        self._last_error: Optional[str] = None
        self._retry_in_seconds: Optional[float] = None
        self._force_enabled: bool = False

        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._ws_connection: Any = None

    @property
    def status(self) -> str:
        return self._status

    @property
    def is_connected(self) -> bool:
        return self._status == "CONNECTED"

    def set_disabled(self):
        """Mark client as explicitly disabled without connecting."""
        self._status = "DISABLED"
        self._running = False
        self._force_enabled = False

    def get_feed_status(self) -> LiveFeedStatus:
        """Return diagnostic status of the feed connection."""
        stored = get_upstox_token()
        has_auth = bool(stored and stored.access_token and not stored.is_expired)
        cfg = get_upstox_config()
        is_enabled = bool(cfg.live_data_enabled or self._force_enabled)

        effective_status = self._status
        if not is_enabled:
            effective_status = "DISABLED"
        elif not has_auth:
            effective_status = "AUTHENTICATION_REQUIRED"

        return LiveFeedStatus(
            status=effective_status,
            authenticated=has_auth,
            live_data_enabled=is_enabled,
            subscribed_symbols=sorted(list(self._subscribed_symbols)),
            subscribed_count=len(self._subscribed_symbols),
            last_tick_time=self._last_tick_time,
            ticks_received=self._ticks_received,
            connected_clients=len(self._frontend_clients),
            error=self._last_error,
            retry_in_seconds=self._retry_in_seconds,
        )

    async def manual_reconnect(self, force: bool = True, enable: bool = False) -> LiveFeedStatus:
        """Manually trigger reconnection to the Upstox live feed."""
        if enable:
            self._force_enabled = True
        self._last_error = None
        self._retry_in_seconds = None
        await self.stop()
        self.start(force=force or enable)
        return self.get_feed_status()

    def start(self, force: bool = False):
        """Start the background WebSocket feed loop if enabled and not already running."""
        if force:
            self._force_enabled = True

        cfg = get_upstox_config()
        if not cfg.live_data_enabled and not self._force_enabled:
            self._status = "DISABLED"
            logger.info("Upstox WebSocket client not started: UPSTOX_LIVE_DATA_ENABLED is false")
            return

        stored = get_upstox_token()
        if not stored or not stored.access_token or stored.is_expired:
            self._status = "AUTHENTICATION_REQUIRED"
            logger.info("Upstox WebSocket client waiting: Authentication token required")
            return

        if self._running or (self._task and not self._task.done()):
            return

        self._running = True
        try:
            self._task = asyncio.create_task(self._run_loop())
            logger.info("Upstox WebSocket client task started")
        except RuntimeError:
            # If no running event loop, ignore
            pass

    async def stop(self):
        """Stop the background WebSocket feed loop."""
        self._running = False
        if self._ws_connection:
            try:
                await self._ws_connection.close()
            except Exception:
                pass
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._ws_connection = None
        cfg = get_upstox_config()
        self._status = "DISABLED" if (not cfg.live_data_enabled and not self._force_enabled) else "DISCONNECTED"
        logger.info("Upstox WebSocket client stopped")

    async def register_frontend_client(self, ws: WebSocket):
        """Register a frontend WebSocket client to receive live broadcasts."""
        self._frontend_clients.add(ws)
        quotes = self.market_service.get_all_cached_quotes()
        if not quotes:
            quotes = await self.market_service.fetch_quotes()

        payload = {
            "type": "SNAPSHOT",
            "feed_status": self.get_feed_status().model_dump(),
            "quotes": {k: q.model_dump() for k, q in quotes.items()},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            pass

    def unregister_frontend_client(self, ws: WebSocket):
        """Remove a disconnected frontend client."""
        self._frontend_clients.discard(ws)

    async def broadcast_to_clients(self, message: Dict[str, Any]):
        """Broadcast a message to all connected frontend clients."""
        if not self._frontend_clients:
            return
        text = json.dumps(message)
        stale: List[WebSocket] = []
        for ws in self._frontend_clients:
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._frontend_clients.discard(ws)

    async def broadcast_quote(self, quote: LiveQuote):
        """Broadcast a single updated quote to all connected frontend clients."""
        await self.broadcast_to_clients({
            "type": "TICK",
            "quote": quote.model_dump(),
        })

    async def subscribe(self, symbols: List[str]):
        """Add symbols to the subscription set and send to WebSocket if connected."""
        new_keys: List[str] = []
        for s in symbols:
            sym_clean = s.strip().upper()
            self._subscribed_symbols.add(sym_clean)
            key = self.instrument_service.get_instrument_key(sym_clean)
            if key and key not in self._subscribed_keys:
                self._subscribed_keys.add(key)
                new_keys.append(key)

        if self.is_connected and self._ws_connection and new_keys:
            payload = {
                "guid": "stock_intelligence_sub",
                "method": "sub",
                "params": {
                    "mode": "full",
                    "instrumentKeys": new_keys,
                },
            }
            try:
                await self._ws_connection.send(json.dumps(payload))
            except Exception as e:
                logger.warning("Error subscribing to Upstox keys: %s", e)

    async def _run_loop(self):
        """Main connection and message loop."""
        self._status = "CONNECTING"
        backoff = 2.0

        while self._running:
            stored = get_upstox_token()
            if not stored or not stored.access_token or stored.is_expired:
                self._status = "AUTHENTICATION_REQUIRED"
                await asyncio.sleep(5)
                continue

            try:
                # 1. Authorize WebSocket connection
                ws_url = await self._get_authorized_ws_url(stored.access_token)
                if not ws_url:
                    self._status = "DISCONNECTED"
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 1.5, 30.0)
                    continue

                # 2. Connect via websockets
                import websockets
                async with websockets.connect(ws_url, ping_interval=30, ping_timeout=10) as ws:
                    self._ws_connection = ws
                    self._status = "CONNECTED"
                    self._last_error = None
                    backoff = 2.0
                    logger.info("Connected to Upstox Market Data Feed")
                    await self.broadcast_to_clients({
                        "type": "STATUS_UPDATE",
                        "feed_status": self.get_feed_status().model_dump(),
                    })

                    # 3. Send subscription
                    await self._send_subscriptions(ws)

                    # 4. Message loop
                    while self._running:
                        message = await ws.recv()
                        self._process_message(message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._last_error = str(e)
                self._status = "DISCONNECTED"
                logger.warning("Upstox WebSocket disconnected: %s. Retrying in %.1fs", e, backoff)
                self._retry_in_seconds = backoff
                await self.broadcast_to_clients({
                    "type": "STATUS_UPDATE",
                    "feed_status": self.get_feed_status().model_dump(),
                })
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)

        self._status = "DISCONNECTED"
        await self.broadcast_to_clients({
            "type": "STATUS_UPDATE",
            "feed_status": self.get_feed_status().model_dump(),
        })

    async def _get_authorized_ws_url(self, token: str) -> Optional[str]:
        """Fetch the authenticated WebSocket endpoint from Upstox."""
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(UPSTOX_WS_AUTH_URL, headers=headers)
                if res.status_code == 200:
                    data = res.json().get("data", {})
                    return data.get("authorizedRedirectUri")
        except Exception as e:
            logger.warning("Failed to authorize Upstox WebSocket: %s", e)
        return None

    async def _send_subscriptions(self, ws: Any):
        """Send subscription payload to Upstox."""
        keys = list(self._subscribed_keys)
        if not keys:
            for s in self._subscribed_symbols:
                k = self.instrument_service.get_instrument_key(s)
                if k:
                    keys.append(k)

        if not keys:
            return

        payload = {
            "guid": "stock_intelligence_sub",
            "method": "sub",
            "params": {
                "mode": "full",
                "instrumentKeys": keys,
            },
        }
        await ws.send(json.dumps(payload))

    def _process_message(self, message: Any):
        """Parse incoming market data message (JSON or binary)."""
        try:
            self._ticks_received += 1
            self._last_tick_time = datetime.datetime.now(datetime.timezone.utc).isoformat()

            if isinstance(message, str):
                data = json.loads(message)
                feeds = data.get("feeds", {})
                for key, tick in feeds.items():
                    sym = self.instrument_service.get_symbol_by_key(key)
                    if sym:
                        full_feed = tick.get("fullFeed", {})
                        market_ff = full_feed.get("marketFF", {})
                        ltpc = market_ff.get("ltpc", {})
                        ltp = float(ltpc.get("ltp", 0.0) or 0.0)
                        if ltp > 0:
                            self.market_service.update_cache_from_tick(
                                symbol=sym,
                                ltp=ltp,
                                volume=int(market_ff.get("vtt", 0) or 0),
                                high=float(market_ff.get("ohlc", {}).get("high", 0) or 0) or None,
                                low=float(market_ff.get("ohlc", {}).get("low", 0) or 0) or None,
                                close=float(ltpc.get("cp", 0) or 0) or None,
                            )
                            cached = self.market_service.get_cached_quote(sym)
                            if cached:
                                asyncio.create_task(self.broadcast_quote(cached))
        except Exception as e:
            logger.debug("Error processing tick: %s", e)


_ws_client_instance: Optional[UpstoxWebSocketClient] = None


def get_upstox_ws_client() -> UpstoxWebSocketClient:
    global _ws_client_instance
    if _ws_client_instance is None:
        _ws_client_instance = UpstoxWebSocketClient()
    return _ws_client_instance
