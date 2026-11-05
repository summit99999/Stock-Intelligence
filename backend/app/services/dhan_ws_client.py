"""DhanHQ Live Market Feed WebSocket client.

Maintains a resilient background connection to DhanHQ Live Market Feed (v2):
wss://api-feed.dhan.co?version=2&token={token}&clientId={clientId}&authType=2

Handles:
- Authentication & connection management
- Binary packet unpacking via dhan_packet_parser
- Quote cache updates via dhan_market_service
- Broadcasting real-time tick updates to connected frontend clients
- Automatic reconnection with exponential backoff
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import Any, Optional
from fastapi import WebSocket

from app.config import get_dhan_config
from app.schemas.dhan_market import LiveFeedStatus, LiveQuote
from app.services.dhan_instrument_service import (
    DhanInstrument,
    get_instrument_service,
)
from app.services.dhan_market_service import get_dhan_market_service
from app.services.dhan_packet_parser import parse_dhan_packet
from app.services.token_store import get_token

logger = logging.getLogger(__name__)

DHAN_FEED_URL = "wss://api-feed.dhan.co"


class DhanWebSocketClient:
    """Manages the live binary WebSocket stream from Dhan."""

    def __init__(self, feed_url: str = DHAN_FEED_URL):
        self.feed_url = feed_url
        self.market_service = get_dhan_market_service()
        self.instrument_service = get_instrument_service()

        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._force_enabled = False
        cfg = get_dhan_config()
        self._status = "DISABLED" if not cfg.live_data_enabled else "DISCONNECTED"
        self._last_error: Optional[str] = None
        self._ticks_received = 0
        self._last_tick_time: Optional[str] = None
        self._subscribed_symbols: set[str] = set()
        self._consecutive_429 = 0
        self._retry_in_seconds: Optional[float] = None

        # Connected frontend WebSockets
        self._frontend_clients: set[WebSocket] = set()
        self._ws_connection = None

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
        stored = get_token()
        has_auth = bool(stored and stored.access_token and not stored.is_expired)
        cfg = get_dhan_config()
        is_enabled = bool(cfg.live_data_enabled or self._force_enabled)
        return LiveFeedStatus(
            status=self._status,
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

    def start(self, force: bool = False):
        """Start the background WebSocket feed loop if enabled and not already running."""
        if force:
            self._force_enabled = True

        cfg = get_dhan_config()
        if not cfg.live_data_enabled and not self._force_enabled:
            self._status = "DISABLED"
            logger.info("Dhan WebSocket client not started: DHAN_LIVE_DATA_ENABLED is false")
            return

        if self._running or (self._task and not self._task.done()):
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Dhan WebSocket client task started")

    async def manual_reconnect(self, force: bool = True, enable: bool = False) -> LiveFeedStatus:
        """
        Manually trigger reconnection to the Dhan live market feed.
        Resets 429 rate limit backoff and consecutive error counts.
        """
        logger.info(f"Manual reconnect requested (force={force}, enable={enable})")
        if enable:
            self._force_enabled = True

        self._consecutive_429 = 0
        self._retry_in_seconds = None
        self._last_error = None

        await self.stop()
        self.start(force=True if (force or enable) else False)
        return self.get_feed_status()

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
        cfg = get_dhan_config()
        self._status = "DISABLED" if (not cfg.live_data_enabled and not self._force_enabled) else "DISCONNECTED"
        logger.info("Dhan WebSocket client stopped")

    async def register_frontend_client(self, ws: WebSocket):
        """Register a frontend WebSocket client to receive live broadcasts."""
        self._frontend_clients.add(ws)
        # Send initial snapshot of all current cached quotes
        quotes = self.market_service.get_all_cached_quotes()
        if not quotes:
            quotes = self.market_service._get_cached_or_demo_quotes()

        payload = {
            "type": "SNAPSHOT",
            "feed_status": self.get_feed_status().model_dump(),
            "quotes": {k: v.model_dump() for k, v in quotes.items()},
        }
        try:
            await ws.send_text(json.dumps(payload))
        except Exception as e:
            logger.warning(f"Error sending snapshot to frontend client: {e}")

    def unregister_frontend_client(self, ws: WebSocket):
        """Unregister a frontend WebSocket client on disconnect."""
        self._frontend_clients.discard(ws)

    async def broadcast_to_clients(self, message: dict[str, Any]):
        """Broadcast a message to all connected frontend clients."""
        if not self._frontend_clients:
            return

        text = json.dumps(message)
        dead = []
        for ws in self._frontend_clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self._frontend_clients.discard(ws)

    async def subscribe(self, symbols: list[str]):
        """Subscribe to additional symbols."""
        for s in symbols:
            self._subscribed_symbols.add(s.upper())

        if self.is_connected and self._ws_connection:
            instruments = [
                self.instrument_service.get_instrument(s)
                for s in symbols
                if self.instrument_service.get_instrument(s)
            ]
            if instruments:
                payload = self.instrument_service.build_ws_subscription_payload(
                    instruments, request_code=17
                )
                try:
                    await self._ws_connection.send(json.dumps(payload))
                    logger.info(f"Subscribed to {len(instruments)} instruments on Dhan feed")
                except Exception as e:
                    logger.error(f"Failed to send subscription to Dhan WebSocket: {e}")

    async def _run_loop(self):
        """Main connection and message consumption loop with automatic reconnect."""
        import random
        import websockets

        normal_backoff = 5.0
        max_normal_backoff = 60.0

        rate_limit_backoff = 30.0
        max_rate_limit_backoff = 300.0  # 5 minutes
        max_consecutive_429 = 4

        # Pre-seed default subscriptions with benchmark instruments
        for inst in self.instrument_service.get_benchmark_instruments():
            self._subscribed_symbols.add(inst.symbol.upper())

        while self._running:
            cfg = get_dhan_config()
            if not cfg.live_data_enabled and not self._force_enabled:
                self._status = "DISABLED"
                self._last_error = "Dhan live data is disabled (DHAN_LIVE_DATA_ENABLED=false)"
                self._running = False
                logger.info("Dhan WebSocket loop terminated: DHAN_LIVE_DATA_ENABLED is false")
                break

            token_obj = get_token()
            if not token_obj or not token_obj.access_token or token_obj.is_expired or not cfg.client_id:
                self._status = "AUTHENTICATION_REQUIRED"
                self._last_error = "Dhan access token or client ID not available"
                await self.broadcast_to_clients({
                    "type": "STATUS_UPDATE",
                    "feed_status": self.get_feed_status().model_dump(),
                })
                await asyncio.sleep(5)
                continue

            # If we've reached max consecutive 429 errors:
            if self._consecutive_429 >= max_consecutive_429:
                self._status = "RATE_LIMITED"
                self._last_error = (
                    f"Server rejected WebSocket connection: HTTP 429 ({self._consecutive_429} consecutive rejections). "
                    "Dhan Data API subscription may be inactive. Automatic retries paused — use manual reconnect when subscription is active."
                )
                self._retry_in_seconds = None
                logger.warning(self._last_error)
                await self.broadcast_to_clients({
                    "type": "STATUS_UPDATE",
                    "feed_status": self.get_feed_status().model_dump(),
                })
                # Sleep long interval or wait for manual reconnect
                try:
                    await asyncio.sleep(max_rate_limit_backoff)
                except asyncio.CancelledError:
                    break
                continue

            token = token_obj.access_token
            client_id = cfg.client_id
            url = f"{self.feed_url}?version=2&token={token}&clientId={client_id}&authType=2"

            self._status = "CONNECTING"
            self._last_error = None
            await self.broadcast_to_clients({
                "type": "STATUS_UPDATE",
                "feed_status": self.get_feed_status().model_dump(),
            })

            try:
                logger.info(f"Connecting to Dhan Live Market Feed at {self.feed_url}...")
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws_connection = ws
                    self._status = "CONNECTED"
                    self._consecutive_429 = 0
                    self._retry_in_seconds = None
                    normal_backoff = 5.0
                    rate_limit_backoff = 30.0
                    logger.info("Connected to Dhan Live Market Feed WebSocket")

                    # Subscribe to all current symbols
                    instruments = [
                        self.instrument_service.get_instrument(s)
                        for s in self._subscribed_symbols
                        if self.instrument_service.get_instrument(s)
                    ]
                    if instruments:
                        sub_payload = self.instrument_service.build_ws_subscription_payload(
                            instruments, request_code=17
                        )
                        await ws.send(json.dumps(sub_payload))
                        logger.info(
                            f"Sent initial subscription for {len(instruments)} instruments"
                        )

                    # Notify frontend clients of connected status
                    await self.broadcast_to_clients({
                        "type": "STATUS_UPDATE",
                        "feed_status": self.get_feed_status().model_dump(),
                    })

                    # Read binary frames loop
                    while self._running:
                        msg = await ws.recv()
                        if isinstance(msg, (bytes, bytearray)):
                            parsed = parse_dhan_packet(msg)
                            if parsed:
                                self._ticks_received += 1
                                now_str = datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat()
                                self._last_tick_time = now_str

                                # Update quote in market service cache
                                quote = self.market_service.update_from_packet(parsed)
                                if quote:
                                    # Broadcast tick to frontend
                                    await self.broadcast_to_clients({
                                        "type": "TICK",
                                        "quote": quote.model_dump(),
                                    })
                        elif isinstance(msg, str):
                            # Non-binary message (e.g. JSON control / ack)
                            try:
                                data = json.loads(msg)
                                logger.debug(f"Received Dhan text message: {data}")
                            except Exception:
                                pass

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Check for HTTP 429 Rate Limit
                is_429 = False
                retry_after: Optional[float] = None

                status_code = getattr(e, "status_code", None)
                if status_code is None and hasattr(e, "response"):
                    status_code = getattr(e.response, "status_code", None)

                if status_code == 429 or "429" in str(e):
                    is_429 = True

                headers = getattr(e, "headers", None)
                if headers is None and hasattr(e, "response"):
                    headers = getattr(e.response, "headers", None)
                if headers and "Retry-After" in headers:
                    try:
                        retry_after = float(headers["Retry-After"])
                    except (ValueError, TypeError):
                        pass

                if is_429:
                    self._consecutive_429 += 1
                    self._status = "RATE_LIMITED"
                    self._last_error = (
                        f"Server rejected WebSocket connection: HTTP 429 (Rate limit or Data API inactive, attempt {self._consecutive_429}/{max_consecutive_429})"
                    )
                    if retry_after is not None and retry_after > 0:
                        wait_time = max(retry_after, 15.0)
                    else:
                        wait_time = rate_limit_backoff + random.uniform(1.0, 5.0)
                        rate_limit_backoff = min(rate_limit_backoff * 2.0, max_rate_limit_backoff)

                    self._retry_in_seconds = round(wait_time, 1)
                    logger.warning(
                        f"Dhan WebSocket rejected (HTTP 429). Status set to RATE_LIMITED. "
                        f"Backing off for {self._retry_in_seconds}s (attempt {self._consecutive_429}/{max_consecutive_429})..."
                    )
                else:
                    self._status = "DISCONNECTED"
                    self._last_error = str(e)
                    wait_time = normal_backoff + random.uniform(0.5, 2.0)
                    normal_backoff = min(normal_backoff * 1.5, max_normal_backoff)
                    self._retry_in_seconds = round(wait_time, 1)
                    logger.warning(
                        f"Dhan WebSocket disconnected: {e}. Status set to DISCONNECTED. "
                        f"Reconnecting in {self._retry_in_seconds}s..."
                    )

                await self.broadcast_to_clients({
                    "type": "STATUS_UPDATE",
                    "feed_status": self.get_feed_status().model_dump(),
                })
                await asyncio.sleep(wait_time)
            finally:
                self._ws_connection = None

        cfg = get_dhan_config()
        if not cfg.live_data_enabled and not self._force_enabled:
            self._status = "DISABLED"
        elif self._status != "RATE_LIMITED":
            self._status = "DISCONNECTED"


# Global singleton instance
_ws_client: Optional[DhanWebSocketClient] = None


def get_dhan_ws_client() -> DhanWebSocketClient:
    """Return the global DhanWebSocketClient singleton."""
    global _ws_client
    if _ws_client is None:
        _ws_client = DhanWebSocketClient()
    return _ws_client
