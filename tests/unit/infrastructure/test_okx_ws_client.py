"""Tests for OKX WebSocket client — connection, message loop, reconnect.

Mocks websockets.connect to test:
- ws_url selection (demo/live, public/private)
- Handler registration
- connect() / _connect() success and failure paths
- _login() for private channel
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

from trading_grid.config.settings import OKXSettings
from trading_grid.infrastructure.okx.websocket_client import OKXWebSocketClient


def _make_settings(demo: bool = True) -> OKXSettings:
    return OKXSettings(
        api_key="test-key",
        api_secret="test-secret",
        passphrase="test-pass",
        demo_mode=demo,
        _env_file=None,
    )


def _make_client(private: bool = False, demo: bool = True) -> OKXWebSocketClient:
    return OKXWebSocketClient(_make_settings(demo), private=private)


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
    def test_demo_public_url(self):
        client = _make_client(private=False, demo=True)
        assert client.ws_url == "wss://wspap.okx.com:8443/ws/v5/public"

    def test_demo_private_url(self):
        client = _make_client(private=True, demo=True)
        assert client.ws_url == "wss://wspap.okx.com:8443/ws/v5/private"

    def test_live_public_url(self):
        client = _make_client(private=False, demo=False)
        assert client.ws_url == "wss://ws.okx.com:8443/ws/v5/public"

    def test_live_private_url(self):
        client = _make_client(private=True, demo=False)
        assert client.ws_url == "wss://ws.okx.com:8443/ws/v5/private"


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
        await client._handle_message(json.dumps({"event": "pong"}))
        handler.assert_not_called()

    async def test_subscribe_event_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(
            json.dumps({"event": "subscribe", "arg": {"channel": "tickers"}})
        )
        handler.assert_not_called()

    async def test_error_event_ignored(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        await client._handle_message(json.dumps({"event": "error", "code": "123", "msg": "err"}))
        handler.assert_not_called()

    async def test_data_dispatched_to_handler(self):
        client = _make_client()
        handler = MagicMock()
        client.on_message(handler)
        data = {"arg": {"channel": "tickers"}, "data": [{"last": "50000"}]}
        await client._handle_message(json.dumps(data))
        handler.assert_called_once_with(data)

    async def test_handler_exception_isolated(self):
        """One handler raising should not prevent other handlers."""
        client = _make_client()
        bad_handler = MagicMock(side_effect=ValueError("boom"))
        good_handler = MagicMock()
        client.on_message(bad_handler)
        client.on_message(good_handler)
        data = {"data": []}
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
        data = {"data": [{"last": "1"}]}

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
            return json.dumps({"event": "pong"})

        fake_ws._recv = recv
        client._ws = fake_ws
        client._running = True
        client.PING_INTERVAL = 0.01  # force timeout quickly

        await client._message_loop()
        assert "ping" in fake_ws.sent

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
        assert fake_ws.sent == ["ping"]

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
            return json.dumps({"event": "pong"})

        fake_ws._recv = recv

        with patch(
            "trading_grid.infrastructure.okx.websocket_client.websockets.connect",
            new_callable=AsyncMock,
            return_value=fake_ws,
        ):
            await client.connect()
        # connect() sets _running True, loop stops it
        assert client._ws is fake_ws

    async def test_connect_failure_notifies_disconnect_and_reconnects(self):
        client = _make_client()
        client._running = True

        with (
            patch(
                "trading_grid.infrastructure.okx.websocket_client.websockets.connect",
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
                "trading_grid.infrastructure.okx.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                side_effect=OSError("refused"),
            ),
            patch.object(client, "_schedule_reconnect", new_callable=AsyncMock) as mock_reconnect,
        ):
            await client._connect()
            mock_reconnect.assert_not_awaited()


# ---------------------------------------------------------------------------
# Login (private channel)
# ---------------------------------------------------------------------------


class TestLogin:
    async def test_login_success(self):
        client = _make_client(private=True)
        fake_ws = FakeWS()
        fake_ws.messages = [json.dumps({"code": "0", "data": []})]
        client._ws = fake_ws

        await client._login()
        # A login message should have been sent
        assert len(fake_ws.sent) == 1
        login_msg = json.loads(fake_ws.sent[0])
        assert login_msg["op"] == "login"
        assert login_msg["args"][0]["apiKey"] == "test-key"

    async def test_login_failure_raises(self):
        client = _make_client(private=True)
        fake_ws = FakeWS()
        fake_ws.messages = [json.dumps({"code": "60009", "msg": "Login failed"})]
        client._ws = fake_ws

        with pytest.raises(ConnectionError, match="Login failed"):
            await client._login()

    async def test_login_no_ws_returns(self):
        client = _make_client(private=True)
        client._ws = None
        await client._login()  # should not raise


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    async def test_subscribe_sends_message(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.subscribe("tickers", inst_id="BTC-USDT")
        msg = json.loads(fake_ws.sent[0])
        assert msg["op"] == "subscribe"
        assert msg["args"][0]["channel"] == "tickers"
        assert msg["args"][0]["instId"] == "BTC-USDT"

    async def test_subscribe_no_inst_id(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.subscribe("orders")
        msg = json.loads(fake_ws.sent[0])
        assert "instId" not in msg["args"][0]

    async def test_subscribe_not_connected_raises(self):
        client = _make_client()
        client._ws = None
        with pytest.raises(ConnectionError):
            await client.subscribe("tickers")

    async def test_unsubscribe_sends_message(self):
        client = _make_client()
        fake_ws = FakeWS()
        client._ws = fake_ws
        await client.unsubscribe("tickers", inst_id="BTC-USDT")
        msg = json.loads(fake_ws.sent[0])
        assert msg["op"] == "unsubscribe"

    async def test_unsubscribe_no_ws_no_raise(self):
        client = _make_client()
        client._ws = None
        await client.unsubscribe("tickers")  # should not raise


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


class TestScheduleReconnect:
    async def test_schedule_reconnect_uses_backoff(self):
        """[NEW-M-3] _schedule_reconnect should use exponential backoff."""
        client = _make_client()
        client._reconnect_attempt = 0

        with (
            patch(
                "trading_grid.infrastructure.okx.websocket_client.ws_reconnect_delay",
                return_value=1.5,
            ) as mock_delay,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await client._schedule_reconnect()

        mock_delay.assert_called_once_with(0)
        mock_sleep.assert_awaited_once_with(1.5)
        assert client._reconnect_attempt == 1

    async def test_schedule_reconnect_increments_attempt(self):
        """[NEW-M-3] Each reconnect should increment the attempt counter."""
        client = _make_client()
        client._reconnect_attempt = 2

        with (
            patch(
                "trading_grid.infrastructure.okx.websocket_client.ws_reconnect_delay",
                return_value=4.0,
            ) as mock_delay,
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await client._schedule_reconnect()

        mock_delay.assert_called_once_with(2)
        assert client._reconnect_attempt == 3

    async def test_connect_resets_attempt_counter(self):
        """[NEW-M-3] connect() should reset the attempt counter."""
        client = _make_client()
        client._reconnect_attempt = 5
        fake_ws = FakeWS()

        async def recv():
            client._running = False
            return json.dumps({"event": "pong"})

        fake_ws._recv = recv

        with patch(
            "trading_grid.infrastructure.okx.websocket_client.websockets.connect",
            new_callable=AsyncMock,
            return_value=fake_ws,
        ):
            await client.connect()

        assert client._reconnect_attempt == 0

    async def test_successful_connect_resets_attempt_counter(self):
        """[NEW-M-3] Successful _connect() should reset the attempt counter."""
        client = _make_client()
        client._reconnect_attempt = 3
        fake_ws = FakeWS()

        async def recv():
            client._running = False
            return json.dumps({"event": "pong"})

        fake_ws._recv = recv

        with (
            patch(
                "trading_grid.infrastructure.okx.websocket_client.websockets.connect",
                new_callable=AsyncMock,
                return_value=fake_ws,
            ),
            patch.object(client, "_message_loop", new_callable=AsyncMock),
        ):
            await client._connect()

        assert client._reconnect_attempt == 0


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
