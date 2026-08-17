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
    RECONNECT_DELAY = 5  # seconds

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
        """Connect to WebSocket."""
        self._running = True
        await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic."""
        try:
            logger.info("bybit_ws_connecting", url=self.ws_url, private=self._private)
            self._ws = await websockets.connect(self.ws_url)
            logger.info("bybit_ws_connected", private=self._private)

            # Authenticate for private channel
            if self._private:
                await self._authenticate()

            await self._message_loop()

        except ConnectionClosed as e:
            logger.warning("bybit_ws_connection_closed", code=e.code, reason=e.reason)
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()

        except Exception as e:
            logger.error("bybit_ws_error", error=str(e))
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

            # Dispatch to handlers
            for handler in self._message_handlers:
                try:
                    handler(data)
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
        """Schedule reconnection after delay."""
        logger.info("bybit_ws_scheduling_reconnect", delay=self.RECONNECT_DELAY)
        await asyncio.sleep(self.RECONNECT_DELAY)
        if self._running:
            await self._connect()

    def _notify_disconnect(self) -> None:
        """Notify disconnect handlers."""
        for handler in self._disconnect_handlers:
            try:
                handler()
            except Exception as e:
                logger.error("bybit_ws_disconnect_handler_error", error=str(e))

    async def subscribe(self, topic: str) -> None:
        """
        Subscribe to topic.

        Args:
            topic: Topic name (e.g., 'tickers.BTCUSDT', 'order')
        """
        if self._ws is None:
            raise ConnectionError("Not connected")

        message = {"op": "subscribe", "args": [topic]}
        await self._ws.send(json.dumps(message))
        logger.info("bybit_ws_subscribed", topic=topic)

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from topic."""
        if self._ws is None:
            return

        message = {"op": "unsubscribe", "args": [topic]}
        await self._ws.send(json.dumps(message))

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("bybit_ws_disconnected", private=self._private)
