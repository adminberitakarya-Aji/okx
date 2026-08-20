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
import time
from collections.abc import Callable
from typing import Any

import httpx
import structlog
import websockets
from websockets.exceptions import ConnectionClosed

from trading_grid.config.settings import BinanceSettings
from trading_grid.infrastructure._common.ws_backoff import ws_reconnect_delay

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
    # [NEW-M-3] Reconnect uses exponential backoff via ws_reconnect_delay.
    # RECONNECT_DELAY kept for backward compatibility but no longer used directly.
    RECONNECT_DELAY = 5  # seconds (legacy, replaced by exponential backoff)

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
        # [NEW-CR-1] Track connection state and subscriptions for reconnect logic
        self._connected: asyncio.Event = asyncio.Event()
        self._subscribed_streams: list[str] = []
        # [NEW-M-3] Track consecutive reconnect attempts for exponential backoff
        self._reconnect_attempt = 0
        # [NEW-M-5] Track in-flight async handler tasks to prevent GC (RUF006)
        self._handler_tasks: set[asyncio.Task[Any]] = set()

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

    async def _keepalive_listen_key(self) -> None:
        """Keep listenKey alive by PUTting every 30 minutes (Binance expires after 60 min)."""
        keepalive_interval = 30 * 60  # 30 minutes
        while self._running and self._listen_key:
            await asyncio.sleep(keepalive_interval)
            if not self._running or not self._listen_key:
                break
            try:
                async with httpx.AsyncClient(
                    base_url=self._settings.effective_base_url,
                    timeout=self._settings.timeout,
                ) as client:
                    response = await client.put(
                        "/api/v3/userDataStream",
                        params={"listenKey": self._listen_key},
                        headers={"X-MBX-APIKEY": self._settings.api_key.get_secret_value()},
                    )
                    response.raise_for_status()
                    logger.info("binance_listen_key_refreshed", listen_key=self._listen_key[:8])
            except Exception as e:
                logger.warning("binance_listen_key_refresh_failed", error=str(e))

    async def connect(self) -> None:
        """Connect to WebSocket with iterative reconnect loop."""
        self._running = True
        self._reconnect_attempt = 0
        while self._running:
            await self._connect()

    async def _connect(self) -> None:
        """Internal connection logic."""
        keepalive_task: asyncio.Task[None] | None = None
        try:
            url = self.ws_url
            if self._private:
                self._listen_key = await self._create_listen_key()
                url = f"{self.ws_url}/{self._listen_key}"

            logger.info("binance_ws_connecting", private=self._private)
            self._ws = await websockets.connect(url)
            logger.info("binance_ws_connected", private=self._private)
            # [NEW-M-3] Reset attempt counter on successful connect
            self._reconnect_attempt = 0
            # [NEW-CR-1] Signal connection ready
            self._connected.set()

            # Start listenKey keepalive background task for private streams
            if self._private and self._listen_key:
                keepalive_task = asyncio.create_task(self._keepalive_listen_key())

            # [NEW-CR-1] Re-subscribe streams after reconnect
            if self._subscribed_streams:
                await self._resubscribe_all()

            await self._message_loop()
        except ConnectionClosed as e:
            logger.warning("binance_ws_connection_closed", code=e.code, reason=e.reason)
            self._connected.clear()
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()
        except Exception as e:
            logger.error("binance_ws_error", error=str(e))
            self._connected.clear()
            self._notify_disconnect()
            if self._running:
                await self._schedule_reconnect()
        finally:
            if keepalive_task and not keepalive_task.done():
                keepalive_task.cancel()

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
        """Schedule reconnection delay with exponential backoff + jitter."""
        delay = ws_reconnect_delay(self._reconnect_attempt)
        self._reconnect_attempt += 1
        logger.info(
            "binance_ws_scheduling_reconnect",
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
                logger.error("binance_ws_disconnect_handler_error", error=str(e))

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
            logger.error("binance_ws_connect_timeout", timeout=timeout)
            raise

    async def _resubscribe_all(self) -> None:
        """
        [NEW-CR-1] Re-subscribe all tracked streams after reconnect.

        Called automatically by _connect() when re-establishing connection.
        """
        if not self._subscribed_streams or self._ws is None:
            return
        msg = {
            "method": "SUBSCRIBE",
            "params": list(self._subscribed_streams),
            "id": int(time.time() * 1000),
        }
        await self._ws.send(json.dumps(msg))
        logger.info(
            "binance_ws_resubscribed",
            count=len(self._subscribed_streams),
            private=self._private,
        )

    async def subscribe_ticker(self, symbol: str) -> None:
        """
        Subscribe to ticker stream (legacy single-symbol helper).

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")

        Note:
            For multiple streams, prefer subscribe().
        """
        await self.subscribe([f"{symbol.lower()}@ticker"])

    async def subscribe(self, streams: list[str]) -> None:
        """
        [NEW-CR-1] Subscribe to multiple streams at once.

        Args:
            streams: List of stream names, e.g.
                ["btcusdt@ticker", "btcusdt@kline_1h", "ethusdt@trade"]

        Tracks streams for automatic re-subscription after reconnect.
        """
        if self._ws is None:
            raise ConnectionError("Not connected")
        if not streams:
            return

        msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": int(time.time() * 1000),
        }
        await self._ws.send(json.dumps(msg))

        # Track streams for re-subscribe (deduplicated)
        for stream in streams:
            if stream not in self._subscribed_streams:
                self._subscribed_streams.append(stream)

        logger.info(
            "binance_ws_subscribed",
            count=len(streams),
            total_tracked=len(self._subscribed_streams),
        )

    async def unsubscribe(self, streams: list[str]) -> None:
        """
        [NEW-CR-1] Unsubscribe from streams and remove from tracking.

        Args:
            streams: List of stream names to unsubscribe
        """
        if self._ws is None or not streams:
            return

        msg = {
            "method": "UNSUBSCRIBE",
            "params": streams,
            "id": int(time.time() * 1000),
        }
        await self._ws.send(json.dumps(msg))

        # Remove from tracking
        self._subscribed_streams = [s for s in self._subscribed_streams if s not in streams]
        logger.info("binance_ws_unsubscribed", count=len(streams))

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False
        self._connected.clear()
        # [NEW-CR-1] Clear subscription tracking on full disconnect
        self._subscribed_streams = []
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        logger.info("binance_ws_disconnected", private=self._private)
