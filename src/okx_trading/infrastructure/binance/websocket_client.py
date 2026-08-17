"""
Binance WebSocket client.

This module provides:
- WebSocket connection for real-time market data (public streams)
- Private WebSocket for order updates (user data stream)
- Automatic reconnection
- Ping/pong keepalive

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
3. Secrets never in logs

Reference: https://developers.binance.com/docs/binance-spot-api-docs/web-socket-streams
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from okx_trading.config.settings import BinanceSettings

logger = structlog.get_logger()


class BinanceWebSocketClient:
    """
    Binance WebSocket client for real-time data.

    Supports:
    - Public streams (market data)
    - User data stream (orders) — requires listenKey
    - Automatic reconnection
    """

    PING_INTERVAL = 25  # seconds
    RECONNECT_DELAY = 5  # seconds

    def __init__(self, settings: BinanceSettings, private: bool = False) -> None:
        """
        Initialize WebSocket client.

        Args:
            settings: Binance API settings
            private: Whether to connect to user data stream
        """
        self._settings = settings
        self._private = private
        self._ws: websockets.ClientConnection | None = None
        self._running = False
        self._listen_key: str | None = None
        self._message_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._disconnect_handlers: list[Callable[[], None]] = []

    @property
    def ws_url(self) -> str:
        """Get WebSocket base URL based on mode."""
        return self._settings.effective_ws_url

    def on_message(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register message handler."""
        self._message_handlers.append(handler)

    def on_disconnect(self, handler: Callable[[], None]) -> None:
        """Register disconnect handler."""
        self._disconnect_handlers.append(handler)

    async def _create_listen_key(self) -> str:
        """Create user data stream listen key (private only)."""
        async with httpx.AsyncClient(
            base_url=self._settings.effective_base_url, timeout=self._settings.timeout
        ) as client:
            response = await client.post(
                "/api/v3/userDataStream",
                headers={"X-MBX-APIKEY": self._settings.api_key.get_secret_value()},
            )
            response.raise_for_status()
            data = response.json()
            listen_key: str = data["listenKey"]
            return listen_key

    async def connect(self) -> None:
        """Connect to WebSocket."""
        self._running = True
        await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic."""
        try:
            url = self.ws_url
            if self._private:
                self._listen_key = await self._create_listen_key()
                url = f"{self.ws_url}/{self._listen_key}"

            logger.info("binance_ws_connecting", private=self._private)
            self._ws = await websockets.connect(url)
            logger.info("binance_ws_connected", private=self._private)

            await self._message_loop()

        except ConnectionClosed as e:
            logger.warning("binance_ws_connection_closed", code=e.code, reason=e.reason)
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()

        except Exception as e:
            logger.error("binance_ws_error", error=str(e))
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()

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

            # Dispatch to handlers
            for handler in self._message_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("binance_ws_handler_error", error=str(e))

        except json.JSONDecodeError:
            logger.warning("binance_ws_invalid_message", message=message[:100])

    async def _send_ping(self) -> None:
        """Send ping to keep connection alive."""
        if self._ws is not None:
            try:
                pong = await self._ws.ping()
                await asyncio.wait_for(pong, timeout=5)
            except Exception as e:
                logger.warning("binance_ws_ping_failed", error=str(e))

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection after delay."""
        logger.info("binance_ws_scheduling_reconnect", delay=self.RECONNECT_DELAY)
        await asyncio.sleep(self.RECONNECT_DELAY)
        if self._running:
            await self._connect()

    def _notify_disconnect(self) -> None:
        """Notify disconnect handlers."""
        for handler in self._disconnect_handlers:
            try:
                handler()
            except Exception as e:
                logger.error("binance_ws_disconnect_handler_error", error=str(e))

    async def subscribe_ticker(self, symbol: str) -> None:
        """
        Subscribe to ticker stream.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
        """
        if self._ws is None:
            raise ConnectionError("Not connected")

        message = {"method": "SUBSCRIBE", "params": [f"{symbol.lower()}@ticker"], "id": 1}
        await self._ws.send(json.dumps(message))
        logger.info("binance_ws_subscribed", stream="ticker", symbol=symbol)

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("binance_ws_disconnected", private=self._private)
