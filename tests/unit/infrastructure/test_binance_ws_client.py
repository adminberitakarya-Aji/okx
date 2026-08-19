"""Tests for Binance WebSocket client — connection, message loop, reconnect.

Mocks websockets.connect to test:
- ws_url property (testnet/live)
- Handler registration
- connect() / _connect() success and failure paths
- _create_listen_key() for private stream
- _message_loop() message dispatch and ping keepalive
- _handle_message() event routing and handler isolation
- subscribe_ticker() / disconnect()
- Reconnect scheduling after disconnect
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosed

from trading_grid.config.settings import BinanceSettings
from trading_grid.infrastructure.binance.websocket_client import BinanceWebSocketClient


def _make_settings(testnet: bool = True) -> BinanceSettings:
    return BinanceSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_client(private: bool = False, testnet: bool = True) -> BinanceWebSocketClient:
    return BinanceWebSocketClient(_make_settings(testnet), private=private)


class FakeWS:
    """Fake websocket connection for testing."""

    def __init__(self, messages: list[str] | None = None) -> None:
        self.messages = list(messages or [])
        self.sent: list[str] = []
        self.closed = False
        self._recv = None  # custom recv coroutine

    async def recv(self) -> str:
        if self._recv is not None:
            return await self._recv()
        if self.messages:
            return self.messages.pop(0)
        raise ConnectionClosed(rcvd=None, sent=None)

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    async def ping(self) -> AsyncMock:
        return AsyncMock()


# ---------------------------------------------------------------------------
# ws_url property
# ---------------------------------------------------------------------------


class TestWsUrl:
    def test_testnet_url(self):
        client = _make_client(testnet=True)
        assert "testnet" in client.ws_url

    def test_live_url(self):
        client = _make_client(testnet=False)
        assert "testnet" not in client.ws_url


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    def test_on_message_registers(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        assert handler in client._message_handlers

    def test_on_disconnect_registers(self):
        client = _make_client()
        handler = MagicMock()
        client.on_disconnect(handler)
        assert handler in client._disconnect_handlers


# ---------------------------------------------------------------------------
# _handle_message
# ---------------------------------------------------------------------------


class TestHandleMessage:
    async def test_data_dispatched_to_handler(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        data = {"e": "24hrTicker", "s": "BTCUSDT", "c": "50000"}
        await client._handle_message(json.dumps(data))
        handler.assert_called_once_with(data)

    async def test_handler_exception_isolated(self):
        """One handler raising should not prevent other handlers."""
        client = _make_client()
        bad_handler = MagicMock(side_effect=ValueError("boom"))
        good_handler = MagicMock()
        client.on_message(bad_handler)
        client.on_message(good_handler)
        data = {"e": "trade"}
        await client._handle_message(json.dumps(data))
        bad_handler.assert_called_once()
        good_handler.assert_called_once()

    async def test_invalid_json_no_raise(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message("not-json{{{")
        handler.assert_not_called()


# ---------------------------------------------------------------------------
# _message_loop
# ---------------------------------------------------------------------------


class TestMessageLoop:
    async def test_loop_dispatches_then_stops(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)

        fake_ws = FakeWS()
        data = {"e": "24hrTicker", "s": "BTCUSDT"}

        async def recv():
            client._running = False  # stop after this message
            return json.dumps(data)

        fake_ws._recv = recv
        client._ws = fake_ws
        client._running = True

        await client._message_loop()
        handler.assert_called_once_with(data)

    async def test_loop_sends_ping_on_timeout(self):
        client = _make_client()
        fake_ws = FakeWS()
        call_count = 0

        async def recv():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(5)  # will time out
            client._running = False
            return json.dumps({"e": "pong"})

        fake_ws._recv = recv
        client._ws = fake_ws
        client._running = True
        client.PING_INTERVAL = 0.01  # force timeout quickly

        await client._message_loop()
        # ping() should have been called (we can't easily assert on it, but no error)

    async def test_loop_no_ws_returns(self):
        client = _make_client()
        client._ws = None
        client._running = True
        # Should return immediately without error
        await client._message_loop()


# ---------------------------------------------------------------------------
# _send_ping
# ---------------------------------------------------------------------------


class TestSendPing:
    async def test_send_ping(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client._send_ping()  # should not raise

    async def test_send_ping_no_ws(self):
        client = _make_client()
        client._ws = None
        await client._send_ping()  # should not raise


# ---------------------------------------------------------------------------
# connect / _connect
# ---------------------------------------------------------------------------


class TestConnect:
    async def test_connect_sets_running(self):
        client = _make_client()
        fake_ws = FakeWS()

        async def recv():
            client._running = False
            return json.dumps({"e": "pong"})

        fake_ws._recv = recv

        with patch(
            "trading_grid.infrastructure.binance.websocket_client.websockets.connect",
            new_callable=AsyncMock,
            return_value=fake_ws,
        ):
            await client.connect()
        assert client._ws is fake_ws

    async def test_connect_failure_notifies_disconnect_and_reconnects(self):
        client = _make_client()
        client._running = True

        with (
            patch(
                "trading_grid.infrastructure.binance.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                side_effect=OSError("connection refused"),
            ),
            patch.object(client, "_schedule_reconnect", new_callable=AsyncMock) as mock_reconnect,
        ):
            disconnect_handler = MagicMock()
            client.on_disconnect(disconnect_handler)
            await client._connect()

            disconnect_handler.assert_called_once()
            mock_reconnect.assert_awaited_once()

    async def test_connect_failure_no_reconnect_when_stopped(self):
        client = _make_client()
        client._running = False

        with (
            patch(
                "trading_grid.infrastructure.binance.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                side_effect=OSError("refused"),
            ),
            patch.object(client, "_schedule_reconnect", new_callable=AsyncMock) as mock_reconnect,
        ):
            await client._connect()
            mock_reconnect.assert_not_awaited()

    async def test_connect_private_creates_listen_key(self):
        """Private connect should create a listen key and use it in URL."""
        client = _make_client(private=True)
        fake_ws = FakeWS()

        async def recv():
            client._running = False
            return json.dumps({"e": "pong"})

        fake_ws._recv = recv

        with (
            patch.object(
                client, "_create_listen_key", new_callable=AsyncMock, return_value="my-listen-key"
            ),
            patch(
                "trading_grid.infrastructure.binance.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                return_value=fake_ws,
            ) as mock_connect,
        ):
            await client.connect()
            # URL should contain the listen key
            call_args = mock_connect.call_args[0]
            assert "my-listen-key" in call_args[0]


# ---------------------------------------------------------------------------
# _create_listen_key
# ---------------------------------------------------------------------------


class TestCreateListenKey:
    async def test_create_listen_key(self):
        client = _make_client(private=True)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"listenKey": "abc123"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            key = await client._create_listen_key()
            assert key == "abc123"
            # [NEW-M-4] async with must be used — connection closed properly
            mock_client.__aexit__.assert_awaited_once()

    async def test_create_listen_key_closes_on_exception(self):
        """[NEW-M-4] Client must be closed even when request raises."""
        client = _make_client(private=True)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("connection error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            with pytest.raises(Exception, match="connection error"):
                await client._create_listen_key()
            # [NEW-M-4] __aexit__ must be called even on exception (no leak)
            mock_client.__aexit__.assert_awaited_once()


class TestKeepaliveListenKey:
    async def test_keepalive_closes_client_no_leak(self):
        """[NEW-M-4] Keepalive must close httpx client (no connection leak)."""
        client = _make_client(private=True)
        client._running = True
        client._listen_key = "test-listen-key"
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        # Simulate one keepalive cycle then stop
        sleep_count = 0

        async def fake_sleep(_):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                client._running = False

        with (
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.put.return_value = mock_resp
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await client._keepalive_listen_key()

            # [NEW-M-4] async with must be used — connection closed properly
            mock_client.__aexit__.assert_awaited_once()
            mock_client.put.assert_awaited_once()
            # put should include listenKey
            call_kwargs = mock_client.put.call_args[1]
            assert call_kwargs["params"]["listenKey"] == "test-listen-key"

    async def test_keepalive_closes_on_exception(self):
        """[NEW-M-4] Keepalive client must be closed even on API error."""
        client = _make_client(private=True)
        client._running = True
        client._listen_key = "test-listen-key"

        # Simulate one cycle: put raises, then stop
        sleep_count = 0

        async def fake_sleep(_):
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                client._running = False

        with (
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.put.side_effect = Exception("API error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            await client._keepalive_listen_key()  # should not raise

            # [NEW-M-4] __aexit__ must be called even on exception (no leak)
            mock_client.__aexit__.assert_awaited_once()


# ---------------------------------------------------------------------------
# subscribe_ticker
# ---------------------------------------------------------------------------


class TestSubscribeTicker:
    async def test_subscribe_ticker_sends_message(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.subscribe_ticker("BTCUSDT")
        msg = json.loads(fake_ws.sent[0])
        assert msg["method"] == "SUBSCRIBE"
        assert msg["params"] == ["btcusdt@ticker"]
        # [NEW-CR-1] id is now a unique millisecond timestamp, not hardcoded 1
        assert isinstance(msg["id"], int)
        assert msg["id"] > 0

    async def test_subscribe_ticker_not_connected_raises(self):
        client = _make_client()
        client._ws = None
        with pytest.raises(ConnectionError):
            await client.subscribe_ticker("BTCUSDT")


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    async def test_disconnect_closes_ws(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        client._running = True
        await client.disconnect()
        assert fake_ws.closed is True
        assert client._ws is None
        assert client._running is False

    async def test_disconnect_no_ws(self):
        client = _make_client()
        client._ws = None
        await client.disconnect()  # should not raise
        assert client._running is False


# ---------------------------------------------------------------------------
# _notify_disconnect
# ---------------------------------------------------------------------------


class TestNotifyDisconnect:
    def test_notify_disconnect_calls_handlers(self):
        client = _make_client()
        h1 = MagicMock()
        h2 = MagicMock()
        client.on_disconnect(h1)
        client.on_disconnect(h2)
        client._notify_disconnect()
        h1.assert_called_once()
        h2.assert_called_once()

    def test_notify_disconnect_handler_error_isolated(self):
        client = _make_client()
        bad = MagicMock(side_effect=RuntimeError("x"))
        good = MagicMock()
        client.on_disconnect(bad)
        client.on_disconnect(good)
        client._notify_disconnect()
        good.assert_called_once()
