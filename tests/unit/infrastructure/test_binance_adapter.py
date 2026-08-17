"""Tests for Binance exchange adapter."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from okx_trading.config.settings import BinanceSettings
from okx_trading.domain.execution.models import Order
from okx_trading.infrastructure.binance.adapter import BinanceAdapter
from okx_trading.infrastructure.binance.rest_client import BinanceAPIError


def _make_settings(testnet=True):
    return BinanceSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_adapter(testnet=True):
    adapter = BinanceAdapter(_make_settings(testnet))
    adapter._rest = AsyncMock()
    return adapter


class TestBinanceAdapterProperties:
    def test_exchange_id(self):
        adapter = _make_adapter()
        assert adapter.exchange_id == "BINANCE"

    def test_mode_testnet(self):
        adapter = _make_adapter(testnet=True)
        assert adapter.mode == "DEMO"

    def test_mode_live(self):
        adapter = _make_adapter(testnet=False)
        assert adapter.mode == "LIVE"

    def test_needs_reconciliation_default(self):
        adapter = _make_adapter()
        assert adapter.needs_reconciliation is False


class TestBinanceAdapterConnection:
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


class TestBinanceAdapterWebSocket:
    async def test_start_market_data_ws(self):
        adapter = _make_adapter()
        with patch("okx_trading.infrastructure.binance.adapter.BinanceWebSocketClient") as mock_ws:
            await adapter.start_market_data_ws()
            mock_ws.assert_called_once()

    async def test_start_private_ws(self):
        adapter = _make_adapter()
        with patch("okx_trading.infrastructure.binance.adapter.BinanceWebSocketClient") as mock_ws:
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
        data = {"e": "24hrTicker", "s": "BTCUSDT"}
        adapter._handle_public_message(data)
        handler.assert_called_once_with(data)

    def test_handle_public_message_non_ticker(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_ticker(handler)
        data = {"e": "other"}
        adapter._handle_public_message(data)
        handler.assert_not_called()

    def test_handle_private_message_execution_report(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_order_update(handler)
        data = {
            "e": "executionReport",
            "s": "BTCUSDT",
            "i": 12345,
            "c": "client-123",
            "X": "FILLED",
            "z": "0.001",
            "Z": "50000.5",
        }
        adapter._handle_private_message(data)
        handler.assert_called_once()
        call_args = handler.call_args[0][0]
        assert call_args["event"] == "order_update"
        assert call_args["market_id"] == "BTC-USDT"
        assert call_args["status"] == "FILLED"

    def test_handle_private_message_non_execution(self):
        adapter = _make_adapter()
        handler = MagicMock()
        adapter.on_order_update(handler)
        data = {"e": "other"}
        adapter._handle_private_message(data)
        handler.assert_not_called()


class TestBinanceAdapterMarketData:
    async def test_get_instruments(self):
        adapter = _make_adapter()
        adapter._rest.get_exchange_info.return_value = {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.00001",
                            "maxQty": "9999",
                            "stepSize": "0.00001",
                        },
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                    ],
                },
                {"symbol": "HALTED", "status": "BREAK", "baseAsset": "X", "quoteAsset": "USDT"},
            ]
        }
        markets = await adapter.get_instruments()
        assert len(markets) == 1
        assert markets[0].market_id == "BTC-USDT"
        assert markets[0].min_order_size == Decimal("0.00001")
        assert markets[0].tick_size == Decimal("0.01")

    async def test_get_ticker(self):
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {"symbol": "BTCUSDT", "lastPrice": "50000"}
        result = await adapter.get_ticker("BTC-USDT")
        assert result["symbol"] == "BTCUSDT"
        adapter._rest.get_ticker.assert_called_once_with("BTCUSDT")

    async def test_get_orderbook(self):
        adapter = _make_adapter()
        adapter._rest.get_orderbook.return_value = {
            "bids": [["50000", "1.5"], ["49999", "2.0"]],
            "asks": [["50001", "1.0"]],
        }
        ob = await adapter.get_orderbook("BTC-USDT", depth=10)
        assert ob.market_id == "BTC-USDT"
        assert len(ob.bids) == 2
        assert len(ob.asks) == 1
        assert ob.bids[0].price == Decimal("50000")

    async def test_get_candles(self):
        adapter = _make_adapter()
        adapter._rest.get_candles.return_value = [
            [
                1691841600000,
                "50000",
                "51000",
                "49000",
                "50500",
                "100",
                1691845199999,
                "5000000",
                500,
            ],
        ]
        candles = await adapter.get_candles("BTC-USDT", interval="1H", limit=10)
        assert len(candles) == 1
        assert candles[0].open == Decimal("50000")
        assert candles[0].close == Decimal("50500")
        adapter._rest.get_candles.assert_called_once_with("BTCUSDT", interval="1h", limit=10)


class TestBinanceAdapterAccount:
    async def test_get_balance(self):
        adapter = _make_adapter()
        adapter._rest.get_account.return_value = {
            "balances": [
                {"asset": "USDT", "free": "1000", "locked": "500"},
                {"asset": "BTC", "free": "0.5", "locked": "0"},
                {"asset": "EMPTY", "free": "0", "locked": "0"},
            ]
        }
        balances = await adapter.get_balance()
        assert balances["USDT"] == Decimal("1500")
        assert balances["BTC"] == Decimal("0.5")
        assert "EMPTY" not in balances

    async def test_get_balance_filtered(self):
        adapter = _make_adapter()
        adapter._rest.get_account.return_value = {
            "balances": [
                {"asset": "USDT", "free": "1000", "locked": "0"},
                {"asset": "BTC", "free": "0.5", "locked": "0"},
            ]
        }
        balances = await adapter.get_balance(currency="USDT")
        assert "USDT" in balances
        assert "BTC" not in balances

    async def test_get_positions(self):
        adapter = _make_adapter()
        adapter._rest.get_account.return_value = {
            "balances": [
                {"asset": "SOL", "free": "10", "locked": "5"},
                {"asset": "USDT", "free": "1000", "locked": "0"},
            ]
        }
        positions = await adapter.get_positions()
        assert len(positions) == 1
        assert positions[0].market_id == "SOL-USDT"
        assert positions[0].quantity == Decimal("15")


class TestBinanceAdapterOrders:
    async def test_place_order(self):
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {"orderId": 12345}
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
        adapter._rest.place_order.return_value = {}
        order = Order(
            order_id="test-order-1",
            market_id="BTC-USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        with pytest.raises(BinanceAPIError):
            await adapter.place_order(order)

    async def test_cancel_order_success(self):
        adapter = _make_adapter()
        adapter._rest.cancel_order.return_value = {}
        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is True

    async def test_cancel_order_failure(self):
        adapter = _make_adapter()
        adapter._rest.cancel_order.side_effect = BinanceAPIError(code="-1", message="fail")
        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is False

    async def test_get_order_status(self):
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "status": "FILLED",
            "executedQty": "0.001",
            "avgPrice": "50000",
        }
        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "FILLED"
        assert status["filled_quantity"] == "0.001"

    async def test_get_pending_orders(self):
        adapter = _make_adapter()
        adapter._rest.get_open_orders.return_value = [{"orderId": 1}]
        orders = await adapter.get_pending_orders()
        assert len(orders) == 1

    async def test_get_fills_with_market(self):
        adapter = _make_adapter()
        adapter._rest.get_my_trades.return_value = [
            {
                "id": 1,
                "orderId": 123,
                "isBuyer": True,
                "price": "50000",
                "qty": "0.001",
                "commission": "0.5",
                "commissionAsset": "USDT",
            }
        ]
        fills = await adapter.get_fills("BTC-USDT")
        assert len(fills) == 1
        assert fills[0].side == "BUY"
        assert fills[0].price == Decimal("50000")

    async def test_get_fills_without_market(self):
        adapter = _make_adapter()
        fills = await adapter.get_fills(None)
        assert fills == []


class TestBinanceAdapterReconciliation:
    async def test_reconcile(self):
        adapter = _make_adapter()
        adapter._rest.get_open_orders.return_value = [{"orderId": 1}]
        adapter._rest.get_account.return_value = {
            "balances": [{"asset": "SOL", "free": "10", "locked": "0"}]
        }
        adapter._needs_reconciliation = True

        result = await adapter.reconcile()

        assert result["pending_orders"] == 1
        assert result["positions"] == 1
        assert result["balances"] == 1
        assert adapter.needs_reconciliation is False
