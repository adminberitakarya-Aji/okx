"""Tests for OKX exchange adapter."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_grid.config.settings import OKXSettings
from trading_grid.domain.execution.models import Order
from trading_grid.infrastructure.okx.adapter import OKXAdapter
from trading_grid.infrastructure.okx.rest_client import OKXAPIError


def _make_settings(demo=True):
    return OKXSettings(
        api_key="test-key",
        api_secret="test-secret",
        passphrase="test-pass",
        demo_mode=demo,
        _env_file=None,
    )


def _make_adapter(demo=True):
    adapter = OKXAdapter(_make_settings(demo))
    adapter._rest = AsyncMock()
    return adapter


class TestOKXAdapterProperties:
    def test_exchange_id(self):
        adapter = _make_adapter()
        assert adapter.exchange_id == "OKX"

    def test_mode_demo(self):
        adapter = _make_adapter(demo=True)
        assert adapter.mode == "DEMO"

    def test_mode_live(self):
        adapter = _make_adapter(demo=False)
        assert adapter.mode == "LIVE"

    def test_needs_reconciliation_default(self):
        adapter = _make_adapter()
        assert adapter.needs_reconciliation is False


class TestOKXAdapterConnection:
    async def test_connect(self):
        adapter = _make_adapter()
        await adapter.connect()  # Should not raise

    async def test_disconnect(self):
        adapter = _make_adapter()
        adapter._rest.close = AsyncMock()
        await adapter.disconnect()
        adapter._rest.close.assert_called_once()

    async def test_disconnect_with_ws(self):
        adapter = _make_adapter()
        adapter._rest.close = AsyncMock()
        adapter._public_ws = AsyncMock()
        adapter._private_ws = AsyncMock()
        await adapter.disconnect()
        adapter._public_ws.disconnect.assert_called_once()
        adapter._private_ws.disconnect.assert_called_once()

    def test_handle_disconnect(self):
        adapter = _make_adapter()
        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True


class TestOKXAdapterWebSocket:
    async def test_start_market_data_ws(self):
        adapter = _make_adapter()
        with patch("trading_grid.infrastructure.okx.adapter.OKXWebSocketClient") as mock_ws:
            await adapter.start_market_data_ws()
            mock_ws.assert_called_once()

    async def test_start_private_ws(self):
        adapter = _make_adapter()
        with patch("trading_grid.infrastructure.okx.adapter.OKXWebSocketClient") as mock_ws:
            await adapter.start_private_ws()
            mock_ws.assert_called_once()

    def test_on_order_update(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_order_update(handler)
        assert handler in adapter._order_update_handlers

    def test_on_ticker(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_ticker(handler)
        assert handler in adapter._ticker_handlers

    def test_handle_public_message_ticker(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_ticker(handler)
        data = {"arg": {"channel": "tickers"}, "data": []}
        adapter._handle_public_message(data)
        handler.assert_called_once_with(data)

    def test_handle_public_message_non_ticker(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_ticker(handler)
        data = {"arg": {"channel": "other"}}
        adapter._handle_public_message(data)
        handler.assert_not_called()

    def test_handle_private_message_orders(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_order_update(handler)
        data = {"arg": {"channel": "orders"}, "data": []}
        adapter._handle_private_message(data)
        handler.assert_called_once_with(data)

    def test_handle_private_message_non_orders(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_order_update(handler)
        data = {"arg": {"channel": "other"}}
        adapter._handle_private_message(data)
        handler.assert_not_called()


class TestOKXAdapterMarketData:
    async def test_get_instruments(self):
        adapter = _make_adapter()
        adapter._rest.get_instruments.return_value = [
            {
                "instId": "BTC-USDT",
                "baseCcy": "BTC",
                "quoteCcy": "USDT",
                "minSz": "0.00001",
                "maxSz": "9999",
                "tickSz": "0.1",
                "lotSz": "0.00000001",
                "state": "live",
            },
            {"instId": "BAD"},  # missing keys → skipped
        ]
        markets = await adapter.get_instruments()
        assert len(markets) == 1
        assert markets[0].market_id == "BTC-USDT"
        assert markets[0].min_order_size == Decimal("0.00001")
        assert markets[0].is_active is True

    async def test_get_ticker(self):
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {"instId": "BTC-USDT", "last": "50000"}
        result = await adapter.get_ticker("BTC-USDT")
        assert result["instId"] == "BTC-USDT"

    async def test_get_orderbook(self):
        adapter = _make_adapter()
        adapter._rest.get_orderbook.return_value = {
            "bids": [["50000", "1.5", "0", "2"]],
            "asks": [["50001", "1.0", "0", "1"]],
        }
        ob = await adapter.get_orderbook("BTC-USDT", depth=10)
        assert ob.market_id == "BTC-USDT"
        assert len(ob.bids) == 1
        assert len(ob.asks) == 1
        assert ob.bids[0].price == Decimal("50000")

    async def test_get_candles(self):
        adapter = _make_adapter()
        adapter._rest.get_candles.return_value = [
            ["1691841600000", "50000", "51000", "49000", "50500", "100"],
        ]
        candles = await adapter.get_candles("BTC-USDT", interval="1H", limit=10)
        assert len(candles) == 1
        assert candles[0].open == Decimal("50000")
        assert candles[0].close == Decimal("50500")


class TestOKXAdapterAccount:
    async def test_get_balance(self):
        adapter = _make_adapter()
        adapter._rest.get_account_balance.return_value = {
            "details": [
                {"ccy": "USDT", "availBal": "1000", "frozenBal": "500"},
                {"ccy": "BTC", "availBal": "0.5", "frozenBal": "0"},
            ]
        }
        balances = await adapter.get_balance()
        assert balances["USDT"] == Decimal("1500")
        assert balances["BTC"] == Decimal("0.5")

    async def test_get_positions(self):
        adapter = _make_adapter()
        adapter._rest.get_positions.return_value = [
            {"instId": "BTC-USDT", "pos": "0.5", "avgPx": "50000"},
            {"instId": "ETH-USDT", "pos": "0"},
        ]
        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].market_id == "BTC-USDT"
        assert positions[0].quantity == Decimal("0.5")
        assert positions[0].average_entry_price == Decimal("50000")


class TestOKXAdapterOrders:
    async def test_place_order(self):
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {"ordId": "12345"}
        order = Order(
            order_id="test-order-1",
            market_id="BTC-USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        exchange_id = await adapter.place_order(order)
        assert exchange_id == "12345"

    async def test_place_order_no_order_id(self):
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {"sMsg": "error"}
        order = Order(
            order_id="test-order-1",
            market_id="BTC-USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        with pytest.raises(OKXAPIError):
            await adapter.place_order(order)

    async def test_cancel_order_success(self):
        adapter = _make_adapter()
        adapter._rest.cancel_order.return_value = {}
        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is True

    async def test_cancel_order_failure(self):
        adapter = _make_adapter()
        adapter._rest.cancel_order.side_effect = OKXAPIError(code="-1", message="fail")
        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is False

    async def test_get_order_status(self):
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "state": "filled",
            "accFillSz": "0.001",
            "avgPx": "50000",
        }
        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "FILLED"
        assert status["filled_quantity"] == "0.001"
        assert status["average_price"] == "50000"

    async def test_get_order_status_unknown_state(self):
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {"state": "unknown_state"}
        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "SUBMITTED"

    async def test_get_pending_orders(self):
        adapter = _make_adapter()
        adapter._rest.get_pending_orders.return_value = [{"ordId": "1"}]
        orders = await adapter.get_pending_orders()
        assert len(orders) == 1

    async def test_get_fills(self):
        adapter = _make_adapter()
        adapter._rest.get_fills.return_value = [
            {
                "tradeId": "t1",
                "ordId": "123",
                "instId": "BTC-USDT",
                "side": "buy",
                "fillPx": "50000",
                "fillSz": "0.001",
                "fee": "-0.5",
                "feeCcy": "USDT",
            }
        ]
        fills = await adapter.get_fills("BTC-USDT")
        assert len(fills) == 1
        assert fills[0].side == "BUY"
        assert fills[0].price == Decimal("50000")
        assert fills[0].fee == Decimal("0.5")


class TestOKXAdapterReconciliation:
    async def test_reconcile(self):
        adapter = _make_adapter()
        adapter._rest.get_pending_orders.return_value = [{"ordId": "1"}]
        adapter._rest.get_positions.return_value = [
            {"instId": "BTC-USDT", "pos": "0.5", "avgPx": "50000"}
        ]
        adapter._rest.get_account_balance.return_value = {
            "details": [{"ccy": "USDT", "availBal": "1000", "frozenBal": "0"}]
        }
        adapter._needs_reconciliation = True

        result = await adapter.reconcile()

        assert result["pending_orders"] == 1
        assert result["positions"] == 1
        assert result["balances"] == 1
        assert adapter.needs_reconciliation is False
