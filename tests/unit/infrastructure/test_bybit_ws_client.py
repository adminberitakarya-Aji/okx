"""Tests for Bybit WebSocket client — connection, message loop, reconnect.

Mocks websockets.connect to test:
- ws_url selection (testnet/live, public/private)
- Handler registration
- connect() / _connect() success and failure paths
- _authenticate() for private channel
- _message_loop() message dispatch and ping keepalive
- _handle_message() event routing and handler isolation
- subscribe() / unsubscribe() / disconnect()
- Reconnect scheduling after disconnect
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosed

from okx_trading.config.settings import BybitSettings
from okx_trading.infrastructure.bybit.websocket_client import BybitWebSocketClient


def _make_settings(testnet: bool = True) -> BybitSettings:
    return BybitSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_client(private: bool = False, testnet: bool = True) -> BybitWebSocketClient:
    return BybitWebSocketClient(_make_settings(testnet), private=private)


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


# ---------------------------------------------------------------------------
# ws_url property
# ---------------------------------------------------------------------------


class TestWsUrl:
    def test_testnet_public_url(self):
        client = _make_client(private=False, testnet=True)
        assert client.ws_url == "wss://stream-testnet.bybit.com/v5/public"

    def test_testnet_private_url(self):
        client = _make_client(private=True, testnet=True)
        assert client.ws_url == "wss://stream-testnet.bybit.com/v5/private"

    def test_live_public_url(self):
        client = _make_client(private=False, testnet=False)
        assert client.ws_url == "wss://stream.bybit.com/v5/public"

    def test_live_private_url(self):
        client = _make_client(private=True, testnet=False)
        assert client.ws_url == "wss://stream.bybit.com/v5/private"


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
    async def test_pong_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(json.dumps({"op": "pong"}))
        handler.assert_not_called()

    async def test_ret_msg_pong_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(json.dumps({"ret_msg": "pong"}))
        handler.assert_not_called()

    async def test_subscribe_event_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(json.dumps({"op": "subscribe", "success": True}))
        handler.assert_not_called()

    async def test_unsubscribe_event_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(json.dumps({"op": "unsubscribe", "success": True}))
        handler.assert_not_called()

    async def test_data_dispatched_to_handler(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        data = {"topic": "tickers.BTCUSDT", "data": {"lastPrice": "50000"}}
        await client._handle_message(json.dumps(data))
        handler.assert_called_once_with(data)

    async def test_handler_exception_isolated(self):
        """One handler raising should not prevent other handlers."""
        client = _make_client()
        bad_handler = MagicMock(side_effect=ValueError("boom"))
        good_handler = MagicMock()
        client.on_message(bad_handler)
        client.on_message(good_handler)
        data = {"topic": "order", "data": {}}
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
        data = {"topic": "tickers.BTCUSDT", "data": {"lastPrice": "50000"}}

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
            return json.dumps({"op": "pong"})

        fake_ws._recv = recv
        client._ws = fake_ws
        client._running = True
        client.PING_INTERVAL = 0.01  # force timeout quickly

        await client._message_loop()
        # A ping message should have been sent
        assert any("ping" in msg for msg in fake_ws.sent)

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
        await client._send_ping()
        msg = json.loads(fake_ws.sent[0])
        assert msg["op"] == "ping"

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
            return json.dumps({"op": "pong"})

        fake_ws._recv = recv

        with patch(
            "okx_trading.infrastructure.bybit.websocket_client.websockets.connect",
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
                "okx_trading.infrastructure.bybit.websocket_client.websockets.connect",
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
                "okx_trading.infrastructure.bybit.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                side_effect=OSError("refused"),
            ),
            patch.object(client, "_schedule_reconnect", new_callable=AsyncMock) as mock_reconnect,
        ):
            await client._connect()
            mock_reconnect.assert_not_awaited()


# ---------------------------------------------------------------------------
# Authentication (private channel)
# ---------------------------------------------------------------------------


class TestAuthenticate:
    async def test_authenticate_success(self):
        client = _make_client(private=True)
        fake_ws = FakeWS()
        fake_ws.messages = [json.dumps({"op": "auth", "success": True})]
        client._ws = fake_ws

        await client._authenticate()
        # An auth message should have been sent
        assert len(fake_ws.sent) == 1
        auth_msg = json.loads(fake_ws.sent[0])
        assert auth_msg["op"] == "auth"
        assert auth_msg["args"][0] == "test-key"

    async def test_authenticate_failure_raises(self):
        client = _make_client(private=True)
        fake_ws = FakeWS()
        fake_ws.messages = [json.dumps({"op": "auth", "success": False, "retMsg": "Auth failed"})]
        client._ws = fake_ws

        with pytest.raises(ConnectionError, match="Auth failed"):
            await client._authenticate()

    async def test_authenticate_no_ws_returns(self):
        client = _make_client(private=True)
        client._ws = None
        await client._authenticate()  # should not raise


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    async def test_subscribe_sends_message(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.subscribe("tickers.BTCUSDT")
        msg = json.loads(fake_ws.sent[0])
        assert msg["op"] == "subscribe"
        assert msg["args"] == ["tickers.BTCUSDT"]

    async def test_subscribe_not_connected_raises(self):
        client = _make_client()
        client._ws = None
        with pytest.raises(ConnectionError):
            await client.subscribe("tickers.BTCUSDT")

    async def test_unsubscribe_sends_message(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.unsubscribe("tickers.BTCUSDT")
        msg = json.loads(fake_ws.sent[0])
        assert msg["op"] == "unsubscribe"

    async def test_unsubscribe_no_ws_no_raise(self):
        client = _make_client()
        client._ws = None
        await client.unsubscribe("tickers.BTCUSDT")  # should not raise


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
