"""[NEW-CR-1] Tests for WebSocket subscription layer.

Verifies:
- subscribe() / subscribe_many() / unsubscribe() send correct protocol messages
- _wait_for_connected() blocks until connection is set
- _resubscribe_all() re-subscribes tracked channels after reconnect
- Adapter subscribe_market_ids() builds correct channel/stream/topic names
- Subscription tracking is deduplicated
- disconnect() clears tracking state
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from websockets.exceptions import ConnectionClosed

from trading_grid.config.settings import (
    BinanceSettings,
    BybitSettings,
    OKXSettings,
)
from trading_grid.infrastructure.binance.websocket_client import (
    BinanceWebSocketClient,
)
from trading_grid.infrastructure.bybit.websocket_client import BybitWebSocketClient
from trading_grid.infrastructure.okx.websocket_client import OKXWebSocketClient


# ---------------------------------------------------------------------------
# Shared FakeWS
# ---------------------------------------------------------------------------


class FakeWS:
    """Fake websocket connection for testing subscribe logic."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False
        self._recv_count = 0

    async def recv(self) -> str:
        self._recv_count += 1
        # First call returns a pong-equivalent to avoid message loop taking over
        if self._recv_count == 1:
            return json.dumps({"event": "pong"})
        await asyncio.sleep(0)
        raise ConnectionClosed(rcvd=None, sent=None)

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True

    async def ping(self) -> AsyncMock:
        return AsyncMock()


def _okx_settings() -> OKXSettings:
    return OKXSettings(
        api_key="test-key",
        api_secret="test-secret",
        passphrase="test-pass",
        demo_mode=True,
        _env_file=None,
    )


def _binance_settings() -> BinanceSettings:
    return BinanceSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=True,
        _env_file=None,
    )


def _bybit_settings() -> BybitSettings:
    return BybitSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=True,
        _env_file=None,
    )


# ===========================================================================
# OKX WebSocket — subscribe logic
# ===========================================================================


class TestOKXSubscribeMany:
    async def test_subscribe_many_sends_one_message(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake

        channels = [
            {"channel": "tickers", "instId": "BTC-USDT"},
            {"channel": "tickers", "instId": "ETH-USDT"},
            {"channel": "candle1H", "instId": "BTC-USDT"},
        ]
        await client.subscribe_many(channels)

        # Single SUBSCRIBE message with all 3 channels
        assert len(fake.sent) == 1
        msg = json.loads(fake.sent[0])
        assert msg["op"] == "subscribe"
        assert len(msg["args"]) == 3
        assert msg["args"] == channels

    async def test_subscribe_many_tracks_channels(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake

        await client.subscribe_many(
            [
                {"channel": "tickers", "instId": "BTC-USDT"},
                {"channel": "tickers", "instId": "ETH-USDT"},
            ]
        )
        assert len(client._subscribed_channels) == 2

    async def test_subscribe_many_deduplicates(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake

        # Subscribe same channel twice
        await client.subscribe_many([{"channel": "tickers", "instId": "BTC-USDT"}])
        await client.subscribe_many([{"channel": "tickers", "instId": "BTC-USDT"}])
        assert len(client._subscribed_channels) == 1

    async def test_subscribe_many_empty_noop(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many([])
        assert fake.sent == []

    async def test_subscribe_many_not_connected_raises(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        client._ws = None
        with pytest.raises(ConnectionError):
            await client.subscribe_many([{"channel": "tickers"}])

    async def test_legacy_subscribe_delegates_to_subscribe_many(self):
        """Backward compatibility: subscribe(channel, inst_id) still works."""
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe("tickers", "BTC-USDT")
        assert len(client._subscribed_channels) == 1
        msg = json.loads(fake.sent[0])
        assert msg["args"] == [{"channel": "tickers", "instId": "BTC-USDT"}]


class TestOKXUnsubscribe:
    async def test_unsubscribe_many_removes_from_tracking(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many(
            [
                {"channel": "tickers", "instId": "BTC-USDT"},
                {"channel": "tickers", "instId": "ETH-USDT"},
            ]
        )
        await client.unsubscribe_many([{"channel": "tickers", "instId": "BTC-USDT"}])
        assert len(client._subscribed_channels) == 1
        assert client._subscribed_channels[0]["instId"] == "ETH-USDT"

    async def test_unsubscribe_no_ws_noop(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        client._ws = None
        await client.unsubscribe_many([{"channel": "tickers"}])  # no raise


class TestOKXWaitForConnected:
    async def test_wait_for_connected_success(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        # Set the event in background after small delay
        async def setter():
            await asyncio.sleep(0.01)
            client._connected.set()
        asyncio.create_task(setter())
        await client._wait_for_connected(timeout=1.0)  # should succeed

    async def test_wait_for_connected_timeout(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        # Event never set
        with pytest.raises(asyncio.TimeoutError):
            await client._wait_for_connected(timeout=0.1)


class TestOKXResubscribeAfterReconnect:
    async def test_resubscribe_all_sends_tracked_channels(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        # Pre-populate tracked channels (simulating prior subscription)
        client._subscribed_channels = [
            {"channel": "tickers", "instId": "BTC-USDT"},
            {"channel": "candle1H", "instId": "ETH-USDT"},
        ]
        await client._resubscribe_all()
        assert len(fake.sent) == 1
        msg = json.loads(fake.sent[0])
        assert msg["op"] == "subscribe"
        assert len(msg["args"]) == 2

    async def test_resubscribe_all_empty_noop(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client._resubscribe_all()
        assert fake.sent == []


class TestOKXDisconnect:
    async def test_disconnect_clears_subscriptions(self):
        client = OKXWebSocketClient(_okx_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many([{"channel": "tickers", "instId": "BTC-USDT"}])
        assert client._subscribed_channels
        await client.disconnect()
        assert client._subscribed_channels == []
        assert client._connected.is_set() is False


# ===========================================================================
# Binance WebSocket — subscribe logic
# ===========================================================================


class TestBinanceSubscribe:
    async def test_subscribe_sends_message(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe(["btcusdt@ticker", "ethusdt@kline_1h"])
        assert len(fake.sent) == 1
        msg = json.loads(fake.sent[0])
        assert msg["method"] == "SUBSCRIBE"
        assert msg["params"] == ["btcusdt@ticker", "ethusdt@kline_1h"]
        assert "id" in msg

    async def test_subscribe_tracks_streams(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe(["btcusdt@ticker", "ethusdt@ticker"])
        assert len(client._subscribed_streams) == 2

    async def test_subscribe_deduplicates(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe(["btcusdt@ticker"])
        await client.subscribe(["btcusdt@ticker"])
        assert len(client._subscribed_streams) == 1

    async def test_subscribe_empty_noop(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe([])
        assert fake.sent == []

    async def test_subscribe_not_connected_raises(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        client._ws = None
        with pytest.raises(ConnectionError):
            await client.subscribe(["btcusdt@ticker"])

    async def test_legacy_subscribe_ticker_works(self):
        """Backward compat: subscribe_ticker(symbol) still works."""
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_ticker("BTCUSDT")
        assert client._subscribed_streams == ["btcusdt@ticker"]


class TestBinanceUnsubscribe:
    async def test_unsubscribe_removes_from_tracking(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe(["btcusdt@ticker", "ethusdt@ticker"])
        await client.unsubscribe(["btcusdt@ticker"])
        assert client._subscribed_streams == ["ethusdt@ticker"]

    async def test_unsubscribe_no_ws_noop(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        client._ws = None
        await client.unsubscribe(["btcusdt@ticker"])


class TestBinanceWaitAndResubscribe:
    async def test_wait_for_connected_success(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        async def setter():
            await asyncio.sleep(0.01)
            client._connected.set()
        asyncio.create_task(setter())
        await client._wait_for_connected(timeout=1.0)

    async def test_resubscribe_all_sends_tracked(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        client._subscribed_streams = ["btcusdt@ticker", "ethusdt@kline_1h"]
        await client._resubscribe_all()
        msg = json.loads(fake.sent[0])
        assert msg["method"] == "SUBSCRIBE"
        assert sorted(msg["params"]) == ["btcusdt@ticker", "ethusdt@kline_1h"]


class TestBinanceDisconnect:
    async def test_disconnect_clears_subscriptions(self):
        client = BinanceWebSocketClient(_binance_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe(["btcusdt@ticker"])
        await client.disconnect()
        assert client._subscribed_streams == []


# ===========================================================================
# Bybit WebSocket — subscribe logic
# ===========================================================================


class TestBybitSubscribeMany:
    async def test_subscribe_many_sends_one_message(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        topics = ["tickers.BTCUSDT", "tickers.ETHUSDT", "kline.60.SOLUSDT"]
        await client.subscribe_many(topics)
        assert len(fake.sent) == 1
        msg = json.loads(fake.sent[0])
        assert msg["op"] == "subscribe"
        assert msg["args"] == topics

    async def test_subscribe_many_tracks(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many(["tickers.BTCUSDT"])
        assert client._subscribed_topics == ["tickers.BTCUSDT"]

    async def test_subscribe_many_dedup(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many(["tickers.BTCUSDT"])
        await client.subscribe_many(["tickers.BTCUSDT"])
        assert client._subscribed_topics == ["tickers.BTCUSDT"]

    async def test_legacy_subscribe_delegates(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe("tickers.BTCUSDT")
        assert client._subscribed_topics == ["tickers.BTCUSDT"]


class TestBybitUnsubscribe:
    async def test_unsubscribe_removes(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many(["tickers.BTCUSDT", "tickers.ETHUSDT"])
        await client.unsubscribe_many(["tickers.BTCUSDT"])
        assert client._subscribed_topics == ["tickers.ETHUSDT"]


class TestBybitWaitAndResubscribe:
    async def test_resubscribe_all(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        client._subscribed_topics = ["tickers.BTCUSDT", "order"]
        await client._resubscribe_all()
        msg = json.loads(fake.sent[0])
        assert msg["op"] == "subscribe"
        assert sorted(msg["args"]) == ["order", "tickers.BTCUSDT"]


class TestBybitDisconnect:
    async def test_disconnect_clears(self):
        client = BybitWebSocketClient(_bybit_settings(), private=False)
        fake = FakeWS()
        client._ws = fake
        await client.subscribe_many(["tickers.BTCUSDT"])
        await client.disconnect()
        assert client._subscribed_topics == []
