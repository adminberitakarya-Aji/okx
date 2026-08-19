"""
Bybit WebSocket client (API v5).

This module provides:
- WebSocket connection for real-time market data (public)
- Private WebSocket for order updates
- Automatic reconnection
- Ping/pong keepalive

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
3. Secrets never in logs

Reference: https://bybit-exchange.github.io/docs/v5/ws/connect
"""

import asyncio
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from trading_grid.config.settings import BybitSettings
from trading_grid.infrastructure._common.ws_backoff import ws_reconnect_delay

logger = structlog.get_logger()


class BybitWebSocketClient:
    """
    Bybit WebSocket v5 client for real-time data.

    Supports:
    - Public channels (market data)
    - Private channels (orders) — requires auth
    - Automatic reconnection
    """

    PING_INTERVAL = 20  # seconds (Bybit requires ping every 20s)
    # [NEW-M-3] Reconnect uses exponential backoff via ws_reconnect_delay.
    # RECONNECT_DELAY kept for backward compatibility but no longer used directly.
    RECONNECT_DELAY = 5  # seconds (legacy, replaced by exponential backoff)

    def __init__(self, settings: BybitSettings, private: bool = False) -> None:
        """
        Initialize WebSocket client.

        Args:
            settings: Bybit API settings
            private: Whether to connect to private channel
        """
        self._settings = settings
        self._private = private
        self._ws: websockets.ClientConnection | None = None
        self._running = False
        self._message_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._disconnect_handlers: list[Callable[[], None]] = []
        # [NEW-CR-1] Track connection state and subscriptions for reconnect logic
        self._connected: asyncio.Event = asyncio.Event()
        self._subscribed_topics: list[str] = []
        # [NEW-M-3] Track consecutive reconnect attempts for exponential backoff
        self._reconnect_attempt = 0
        # [NEW-M-5] Track in-flight async handler tasks to prevent GC (RUF006)
        self._handler_tasks: set[asyncio.Task[Any]] = set()

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL based on mode and channel type."""
        if self._private:
            # Private endpoint
            if self._settings.testnet_mode:
                return "wss://stream-testnet.bybit.com/v5/private"
            return "wss://stream.bybit.com/v5/private"
        # Public endpoint
        if self._settings.testnet_mode:
            return "wss://stream-testnet.bybit.com/v5/public"
        return "wss://stream.bybit.com/v5/public"

    def on_message(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register message handler."""
        self._message_handlers.append(handler)

    def on_disconnect(self, handler: Callable[[], None]) -> None:
        """Register disconnect handler."""
        self._disconnect_handlers.append(handler)

    async def connect(self) -> None:
        """Connect to WebSocket with iterative reconnect loop."""
        self._running = True
        self._reconnect_attempt = 0
        while self._running:
            await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic."""
        try:
            logger.info("bybit_ws_connecting", url=self.ws_url, private=self._private)
            self._ws = await websockets.connect(self.ws_url)
            logger.info("bybit_ws_connected", private=self._private)
            # [NEW-M-3] Reset attempt counter on successful connect
            self._reconnect_attempt = 0
            # [NEW-CR-1] Signal connection ready
            self._connected.set()

            # Authenticate for private channel
            if self._private:
                await self._authenticate()

            # [NEW-CR-1] Re-subscribe topics after reconnect
            if self._subscribed_topics:
                await self._resubscribe_all()

            await self._message_loop()
        except ConnectionClosed as e:
            logger.warning("bybit_ws_connection_closed", code=e.code, reason=e.reason)
            self._connected.clear()
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()
        except Exception as e:
            logger.error("bybit_ws_error", error=str(e))
            self._connected.clear()
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()

    async def _authenticate(self) -> None:
        """Authenticate private WebSocket connection."""
        if self._ws is None:
            return

        expires = int(time.time() * 1000) + 10000
        api_key = self._settings.api_key.get_secret_value()
        secret = self._settings.api_secret.get_secret_value()

        # Bybit v5 signature: HMAC_SHA256(secret, "GET/realtime" + expires)
        message = f"GET/realtime{expires}"
        signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        auth_msg = {"op": "auth", "args": [api_key, expires, signature]}
        await self._ws.send(json.dumps(auth_msg))

        response = await self._ws.recv()
        data = json.loads(response)

        if data.get("op") == "auth" and data.get("success") is True:
            logger.info("bybit_ws_auth_success")
        else:
            logger.error("bybit_ws_auth_failed", ret_msg=data.get("retMsg"))
            raise ConnectionError(f"Bybit WebSocket auth failed: {data.get('retMsg')}")

    async def _message_loop(self) -> None:
        """Process incoming messages."""
        if self._ws is None:
            return

        while self._running:
            try:
                raw_message = await asyncio.wait_for(self._ws.recv(), timeout=self.PING_INTERVAL)
                message = (
                    raw_message if isinstance(raw_message, str) else raw_message.decode("utf-8")
                )
                await self._handle_message(message)

            except TimeoutError:
                await self._send_ping()

            except ConnectionClosed:
                raise

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            # Handle pong
            if data.get("op") == "pong" or data.get("ret_msg") == "pong":
                return

            # Handle subscription confirmations
            if data.get("op") in ("subscribe", "unsubscribe"):
                logger.info("bybit_ws_subscription", op=data.get("op"), success=data.get("success"))
                return

            # [NEW-M-5] Dispatch to handlers — async handlers run as tasks,
            # sync handlers run in executor to avoid blocking the event loop.
            for handler in self._message_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        # RUF006: track task in set to prevent GC
                        task = asyncio.create_task(handler(data))
                        self._handler_tasks.add(task)
                        task.add_done_callback(self._handler_tasks.discard)
                    else:
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, handler, data)
                except Exception as e:
                    logger.error("bybit_ws_handler_error", error=str(e))

        except json.JSONDecodeError:
            logger.warning("bybit_ws_invalid_message", message=message[:100])

    async def _send_ping(self) -> None:
        """Send ping to keep connection alive."""
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"op": "ping"}))
            except Exception as e:
                logger.warning("bybit_ws_ping_failed", error=str(e))

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection delay with exponential backoff + jitter."""
        delay = ws_reconnect_delay(self._reconnect_attempt)
        self._reconnect_attempt += 1
        logger.info(
            "bybit_ws_scheduling_reconnect",
            delay=delay,
            attempt=self._reconnect_attempt,
        )
        await asyncio.sleep(delay)

    def _notify_disconnect(self) -> None:
        """Notify disconnect handlers."""
        for handler in self._disconnect_handlers:
            try:
                handler()
            except Exception as e:
                logger.error("bybit_ws_disconnect_handler_error", error=str(e))

    async def _wait_for_connected(self, timeout: float = 10.0) -> None:
        """
        [NEW-CR-1] Wait until WebSocket is connected.

        Args:
            timeout: Maximum seconds to wait

        Raises:
            asyncio.TimeoutError: If connection not established within timeout
        """
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
        except TimeoutError:
            logger.error("bybit_ws_connect_timeout", timeout=timeout)
            raise

    async def _resubscribe_all(self) -> None:
        """
        [NEW-CR-1] Re-subscribe all tracked topics after reconnect.

        Called automatically by _connect() when re-establishing connection.
        """
        if not self._subscribed_topics or self._ws is None:
            return
        msg = {"op": "subscribe", "args": list(self._subscribed_topics)}
        await self._ws.send(json.dumps(msg))
        logger.info(
            "bybit_ws_resubscribed",
            count=len(self._subscribed_topics),
            private=self._private,
        )

    async def subscribe(self, topic: str) -> None:
        """
        Subscribe to a single topic (legacy helper).

        Args:
            topic: Topic name (e.g., 'tickers.BTCUSDT', 'order')

        Note:
            For multiple topics at once, prefer subscribe_many().
        """
        await self.subscribe_many([topic])

    async def subscribe_many(self, topics: list[str]) -> None:
        """
        [NEW-CR-1] Subscribe to multiple topics at once.

        Args:
            topics: List of topic names, e.g.
                ["tickers.BTCUSDT", "kline.60.ETHUSDT", "order"]

        Tracks topics for automatic re-subscription after reconnect.
        """
        if self._ws is None:
            raise ConnectionError("Not connected")
        if not topics:
            return

        message = {"op": "subscribe", "args": topics}
        await self._ws.send(json.dumps(message))

        # Track topics for re-subscribe (deduplicated)
        for topic in topics:
            if topic not in self._subscribed_topics:
                self._subscribed_topics.append(topic)

        logger.info(
            "bybit_ws_subscribed",
            count=len(topics),
            total_tracked=len(self._subscribed_topics),
        )

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a single topic (legacy helper)."""
        await self.unsubscribe_many([topic])

    async def unsubscribe_many(self, topics: list[str]) -> None:
        """
        [NEW-CR-1] Unsubscribe from topics and remove from tracking.

        Args:
            topics: List of topic names to unsubscribe
        """
        if self._ws is None or not topics:
            return

        message = {"op": "unsubscribe", "args": topics}
        await self._ws.send(json.dumps(message))

        # Remove from tracking
        self._subscribed_topics = [
            t for t in self._subscribed_topics if t not in topics
        ]
        logger.info("bybit_ws_unsubscribed", count=len(topics))

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False
        self._connected.clear()
        # [NEW-CR-1] Clear subscription tracking on full disconnect
        self._subscribed_topics = []
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("bybit_ws_disconnected", private=self._private)
