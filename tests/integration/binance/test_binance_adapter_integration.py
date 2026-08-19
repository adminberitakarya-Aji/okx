"""
Integration tests for Binance adapter.

These tests verify the full adapter wiring: adapter -> REST client -> response
parsing -> domain models, using realistic Binance API response payloads.
HTTP calls are mocked at the REST client level to avoid real network requests.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from trading_grid.config.settings import BinanceSettings
from trading_grid.domain.execution.models import Order
from trading_grid.infrastructure.binance.adapter import BinanceAdapter
from trading_grid.infrastructure.binance.rest_client import BinanceAPIError
from trading_grid.domain.market.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)


def _make_settings(testnet: bool = True) -> BinanceSettings:
    return BinanceSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_adapter(testnet: bool = True) -> BinanceAdapter:
    adapter = BinanceAdapter(_make_settings(testnet))
    adapter._rest = AsyncMock()
    return adapter


class TestBinanceAdapterIntegration:
    """Full adapter flow: create -> connect -> market data -> orders."""

    async def test_adapter_creation_and_properties(self):
        """Adapter is created with correct exchange ID and mode."""
        adapter = _make_adapter(testnet=True)
        assert adapter.exchange_id == "BINANCE"
        assert adapter.mode == "DEMO"
        assert adapter.needs_reconciliation is False

    async def test_adapter_live_mode(self):
        """Live mode adapter has LIVE execution mode."""
        adapter = _make_adapter(testnet=False)
        assert adapter.mode == "LIVE"

    async def test_get_instruments_returns_domain_models(self):
        """get_instruments returns a list of Market domain models."""
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
                        {
                            "filterType": "PRICE_FILTER",
                            "tickSize": "0.01",
                        },
                    ],
                },
            ],
        }

        markets = await adapter.get_instruments()

        assert len(markets) == 1
        market = markets[0]
        assert market.market_id == "BTC-USDT"
        assert market.base_currency == "BTC"
        assert market.quote_currency == "USDT"
        assert market.min_order_size == Decimal("0.00001")
        assert market.tick_size == Decimal("0.01")

    async def test_get_ticker_returns_domain_model(self):
        """get_ticker returns the raw ticker dict from Binance."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {
            "symbol": "BTCUSDT",
            "lastPrice": "50000.00",
            "bidPrice": "49999.00",
            "askPrice": "50001.00",
            "volume": "1234.56",
        }

        ticker = await adapter.get_ticker("BTC-USDT")

        assert ticker.market_id == "BTC-USDT"
        assert ticker.last_price == Decimal("50000.00")
        assert ticker.bid_price == Decimal("49999.00")
        assert ticker.ask_price == Decimal("50001.00")
        adapter._rest.get_ticker.assert_called_once_with("BTCUSDT")

    async def test_get_orderbook_returns_domain_model(self):
        """get_orderbook returns a properly parsed OrderBook domain object."""
        adapter = _make_adapter()
        adapter._rest.get_orderbook.return_value = {
            "bids": [["50000.00", "1.5"], ["49999.00", "2.0"]],
            "asks": [["50001.00", "1.0"], ["50002.00", "3.0"]],
        }

        orderbook = await adapter.get_orderbook("BTC-USDT")

        assert orderbook.market_id == "BTC-USDT"
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == Decimal("50000.00")
        assert orderbook.bids[0].quantity == Decimal("1.5")
        assert orderbook.asks[0].price == Decimal("50001.00")

    async def test_get_candles_returns_domain_models(self):
        """get_candles returns a list of Candle domain objects."""
        adapter = _make_adapter()
        adapter._rest.get_candles.return_value = [
            [
                1700000000000,
                "50000.00",
                "50100.00",
                "49900.00",
                "50050.00",
                "100.0",
                1700000059999,
                "5000000.0",
                500,
                "50.0",
                "2500000.0",
                "0",
            ],
            [
                1700000060000,
                "50050.00",
                "50200.00",
                "50000.00",
                "50150.00",
                "120.0",
                1700000119999,
                "6000000.0",
                600,
                "60.0",
                "3000000.0",
                "0",
            ],
        ]

        candles = await adapter.get_candles("BTC-USDT", interval="1H", limit=2)

        assert len(candles) == 2
        assert candles[0].open == Decimal("50000.00")
        assert candles[0].high == Decimal("50100.00")
        assert candles[0].low == Decimal("49900.00")
        assert candles[0].close == Decimal("50050.00")
        assert candles[0].volume == Decimal("100.0")

    async def test_place_order_returns_exchange_order_id(self):
        """place_order returns the exchange order ID string."""
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {
            "symbol": "BTCUSDT",
            "orderId": 12345,
            "clientOrderId": "test-client-id",
            "status": "NEW",
            "side": "BUY",
            "type": "LIMIT",
            "price": "50000.00",
            "origQty": "0.01",
            "executedQty": "0",
            "transactTime": 1700000000000,
        }

        order = Order(
            order_id="test-order-1",
            market_id="BTC-USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.01"),
            price=Decimal("50000.00"),
        )

        exchange_order_id = await adapter.place_order(order)

        assert exchange_order_id == "12345"
        adapter._rest.place_order.assert_called_once()

    async def test_place_order_market_buy(self):
        """Market BUY order is placed correctly."""
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {
            "symbol": "BTCUSDT",
            "orderId": 12346,
            "status": "FILLED",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "0.01",
            "executedQty": "0.01",
            "transactTime": 1700000000000,
        }

        order = Order(
            order_id="test-order-2",
            market_id="BTC-USDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
        )

        exchange_order_id = await adapter.place_order(order)

        assert exchange_order_id == "12346"
        adapter._rest.place_order.assert_called_once()

    async def test_cancel_order(self):
        """cancel_order calls REST client with correct params."""
        adapter = _make_adapter()
        adapter._rest.cancel_order.return_value = {
            "symbol": "BTCUSDT",
            "orderId": 12345,
            "status": "CANCELED",
        }

        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is True

    async def test_get_order_status_mapping(self):
        """Order status is correctly mapped from Binance to domain."""
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "symbol": "BTCUSDT",
            "orderId": 12345,
            "status": "PARTIALLY_FILLED",
            "side": "BUY",
            "type": "LIMIT",
            "price": "50000.00",
            "origQty": "0.01",
            "executedQty": "0.005",
            "transactTime": 1700000000000,
        }

        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "PARTIALLY_FILLED"
        assert status["filled_quantity"] == "0.005"

    async def test_api_error_propagates(self):
        """BinanceAPIError is propagated to caller."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.side_effect = BinanceAPIError(
            code="-1121", message="Invalid symbol."
        )

        with pytest.raises(BinanceAPIError):
            await adapter.get_ticker("INVALID-PAIR")

    async def test_disconnect_sets_reconciliation_flag(self):
        """After disconnect handling, reconciliation is required."""
        adapter = _make_adapter()
        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

    async def test_reconcile_resets_flag(self):
        """reconcile() resets the needs_reconciliation flag."""
        adapter = _make_adapter()
        adapter._rest.get_open_orders.return_value = []
        adapter._rest.get_account.return_value = {"balances": []}

        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

        await adapter.reconcile()
        assert adapter.needs_reconciliation is False


class TestBinanceSymbolConversion:
    """Symbol normalization round-trip for Binance."""

    def test_normalized_to_concatenated(self):
        assert to_concatenated_symbol("BTC-USDT") == "BTCUSDT"
        assert to_concatenated_symbol("ETH-USDT") == "ETHUSDT"

    def test_concatenated_to_normalized(self):
        assert to_normalized_market_id("BTCUSDT") == "BTC-USDT"
        assert to_normalized_market_id("ETHUSDT") == "ETH-USDT"

    def test_round_trip(self):
        """normalize -> concatenate -> normalize returns original."""
        original = "BTC-USDT"
        concatenated = to_concatenated_symbol(original)
        back = to_normalized_market_id(concatenated)
        assert back == original
