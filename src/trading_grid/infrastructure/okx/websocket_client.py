"""
OKX WebSocket client.

This module provides:
- WebSocket connection for real-time market data
- Private WebSocket for order/position updates
- Automatic reconnection
- Ping/pong keepalive

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
"""

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from trading_grid.config.settings import OKXSettings

logger = structlog.get_logger()


class OKXWebSocketClient:
    """
    OKX WebSocket client for real-time data.

    Supports:
    - Public channels (market data)
    - Private channels (orders, positions)
    - Automatic reconnection
    """

    PING_INTERVAL = 25  # seconds
    RECONNECT_DELAY = 5  # seconds

    def __init__(self, settings: OKXSettings, private: bool = False) -> None:
        """
        Initialize WebSocket client.

        Args:
            settings: OKX API settings
            private: Whether to connect to private channel
        """
        self._settings = settings
        self._private = private
        self._ws: websockets.ClientConnection | None = None
        self._running = False
        self._reconnect_task: asyncio.Task[None] | None = None
        self._message_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._disconnect_handlers: list[Callable[[], None]] = []

    @property
    def ws_url(self) -> str:
        """Get WebSocket URL based on mode."""
        base = self._settings.ws_url
        if self._private:
            # Private WebSocket uses different URL in demo mode
            if self._settings.demo_mode:
                return "wss://wspap.okx.com:8443/ws/v5/private"
            return f"{base}/private"
        # Public WebSocket
        if self._settings.demo_mode:
            return "wss://wspap.okx.com:8443/ws/v5/public"
        return f"{base}/public"

    def on_message(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register message handler."""
        self._message_handlers.append(handler)

    def on_disconnect(self, handler: Callable[[], None]) -> None:
        """Register disconnect handler."""
        self._disconnect_handlers.append(handler)

    async def connect(self) -> None:
        """Connect to WebSocket with iterative reconnect loop."""
        self._running = True
        while self._running:
            await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic."""
        try:
            logger.info("ws_connecting", url=self.ws_url, private=self._private)
            self._ws = await websockets.connect(self.ws_url)
            logger.info("ws_connected", private=self._private)

            # Login for private channel
            if self._private:
                await self._login()

            # Start message loop
            await self._message_loop()
        except ConnectionClosed as e:
            logger.warning("ws_connection_closed", code=e.code, reason=e.reason)
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()
        except Exception as e:
            logger.error("ws_error", error=str(e))
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()

    async def _login(self) -> None:
        """Login to private WebSocket channel."""
        if self._ws is None:
            return

        timestamp = str(int(datetime.now(UTC).timestamp()))
        message = f"{timestamp}GET/users/self/verify"

        import base64
        import hashlib
        import hmac

        secret = self._settings.api_secret.get_secret_value()
        signature = base64.b64encode(
            hmac.new(
                secret.encode("utf-8"),
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")

        login_msg = {
            "op": "login",
            "args": [
                {
                    "apiKey": self._settings.api_key.get_secret_value(),
                    "passphrase": self._settings.passphrase.get_secret_value(),
                    "timestamp": timestamp,
                    "sign": signature,
                }
            ],
        }

        await self._ws.send(json.dumps(login_msg))
        response = await self._ws.recv()
        data = json.loads(response)

        if data.get("code") == "0":
            logger.info("ws_login_success")
        else:
            logger.error("ws_login_failed", code=data.get("code"), msg=data.get("msg"))
            raise ConnectionError(f"WebSocket login failed: {data.get('msg')}")

    async def _message_loop(self) -> None:
        """Process incoming messages."""
        if self._ws is None:
            return

        while self._running:
            try:
                # Wait for message with timeout for ping
                raw_message = await asyncio.wait_for(self._ws.recv(), timeout=self.PING_INTERVAL)
                message = (
                    raw_message if isinstance(raw_message, str) else raw_message.decode("utf-8")
                )
                await self._handle_message(message)

            except TimeoutError:
                # Send ping to keep connection alive
                await self._send_ping()

            except ConnectionClosed:
                raise

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)

            # Handle pong response
            if data.get("event") == "pong":
                return

            # Handle subscription confirmations
            if data.get("event") in ("subscribe", "unsubscribe"):
                logger.info("ws_subscription", ws_event=data.get("event"), channel=data.get("arg"))
                return

            # Handle errors
            if data.get("event") == "error":
                logger.error("ws_error_event", code=data.get("code"), msg=data.get("msg"))
                return

            # Dispatch to handlers
            for handler in self._message_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("ws_handler_error", error=str(e))

        except json.JSONDecodeError:
            logger.warning("ws_invalid_message", message=message[:100])

    async def _send_ping(self) -> None:
        """Send ping to keep connection alive."""
        if self._ws is not None:
            try:
                await self._ws.send("ping")
            except Exception as e:
                logger.warning("ws_ping_failed", error=str(e))

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection delay (reconnection loop handled by connect())."""
        logger.info("ws_scheduling_reconnect", delay=self.RECONNECT_DELAY)
        await asyncio.sleep(self.RECONNECT_DELAY)

    def _notify_disconnect(self) -> None:
        """Notify disconnect handlers."""
        for handler in self._disconnect_handlers:
            try:
                handler()
            except Exception as e:
                logger.error("ws_disconnect_handler_error", error=str(e))

    async def subscribe(self, channel: str, inst_id: str | None = None) -> None:
        """
        Subscribe to channel.

        Args:
            channel: Channel name (e.g., 'tickers', 'orders')
            inst_id: Instrument ID (if applicable)
        """
        if self._ws is None:
            raise ConnectionError("Not connected")

        arg: dict[str, str] = {"channel": channel}
        if inst_id:
            arg["instId"] = inst_id

        message = {"op": "subscribe", "args": [arg]}
        await self._ws.send(json.dumps(message))
        logger.info("ws_subscribed", channel=channel, inst_id=inst_id)

    async def unsubscribe(self, channel: str, inst_id: str | None = None) -> None:
        """Unsubscribe from channel."""
        if self._ws is None:
            return

        arg: dict[str, str] = {"channel": channel}
        if inst_id:
            arg["instId"] = inst_id

        message = {"op": "unsubscribe", "args": [arg]}
        await self._ws.send(json.dumps(message))

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("ws_disconnected", private=self._private)
