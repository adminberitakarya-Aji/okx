"""
Integration tests for Bybit adapter.

These tests verify the full adapter wiring: adapter → REST client → response
parsing → domain models, using realistic Bybit API v5 response payloads.
HTTP calls are mocked at the REST client level to avoid real network requests.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from okx_trading.config.settings import BybitSettings
from okx_trading.domain.execution.models import Order
from okx_trading.infrastructure.bybit.adapter import BybitAdapter
from okx_trading.infrastructure.bybit.rest_client import BybitAPIError
from okx_trading.infrastructure.exchange.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)


def _make_settings(testnet: bool = True) -> BybitSettings:
    return BybitSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_adapter(testnet: bool = True) -> BybitAdapter:
    adapter = BybitAdapter(_make_settings(testnet))
    adapter._rest = AsyncMock()
    return adapter


class TestBybitAdapterIntegration:
    """Full adapter flow: create → connect → market data → orders."""

    async def test_adapter_creation_and_properties(self):
        """Adapter is created with correct exchange ID and mode."""
        adapter = _make_adapter(testnet=True)
        assert adapter.exchange_id == "BYBIT"
        assert adapter.mode == "DEMO"
        assert adapter.needs_reconciliation is False

    async def test_adapter_live_mode(self):
        """Live mode adapter has LIVE execution mode."""
        adapter = _make_adapter(testnet=False)
        assert adapter.mode == "LIVE"

    async def test_get_ticker_returns_raw_dict(self):
        """get_ticker returns the first item from Bybit's list response."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "lastPrice": "50000.00",
                    "bid1Price": "49999.00",
                    "ask1Price": "50001.00",
                    "volume24h": "1234.56",
                    "turnover24h": "61728000.00",
                    "price24hPcnt": "0.025",
                }
            ]
        }

        ticker = await adapter.get_ticker("BTC-USDT")

        assert ticker["symbol"] == "BTCUSDT"
        assert ticker["lastPrice"] == "50000.00"
        adapter._rest.get_ticker.assert_called_once_with("BTCUSDT", category="spot")

    async def test_get_ticker_empty_list(self):
        """get_ticker returns empty dict when no data."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {"list": []}

        ticker = await adapter.get_ticker("BTC-USDT")
        assert ticker == {}

    async def test_get_orderbook_returns_domain_model(self):
        """get_orderbook returns a properly parsed OrderBook domain object."""
        adapter = _make_adapter()
        adapter._rest.get_orderbook.return_value = {
            "b": [["50000.00", "1.5"], ["49999.00", "2.0"]],
            "a": [["50001.00", "1.0"], ["50002.00", "3.0"]],
        }

        orderbook = await adapter.get_orderbook("BTC-USDT")

        assert orderbook.market_id == "BTC-USDT"
        assert len(orderbook.bids) == 2
        assert len(orderbook.asks) == 2
        assert orderbook.bids[0].price == Decimal("50000.00")
        assert orderbook.bids[0].quantity == Decimal("1.5")
        assert orderbook.asks[0].price == Decimal("50001.00")

    async def test_get_candles_returns_domain_models(self):
        """get_candles returns chronologically ordered Candle objects."""
        adapter = _make_adapter()
        # Bybit returns newest first
        adapter._rest.get_candles.return_value = {
            "list": [
                [
                    "1700000060000",
                    "50050.00",
                    "50200.00",
                    "50000.00",
                    "50150.00",
                    "120.0",
                    "6000000.0",
                ],
                [
                    "1700000000000",
                    "50000.00",
                    "50100.00",
                    "49900.00",
                    "50050.00",
                    "100.0",
                    "5000000.0",
                ],
            ]
        }

        candles = await adapter.get_candles("BTC-USDT", interval="1H", limit=2)

        assert len(candles) == 2
        # After reverse, first candle is the older one
        assert candles[0].open == Decimal("50000.00")
        assert candles[0].high == Decimal("50100.00")
        assert candles[0].low == Decimal("49900.00")
        assert candles[0].close == Decimal("50050.00")
        assert candles[0].volume == Decimal("100.0")
        # Second candle is the newer one
        assert candles[1].open == Decimal("50050.00")

    async def test_get_candles_interval_mapping(self):
        """Domain interval is correctly mapped to Bybit interval."""
        adapter = _make_adapter()
        adapter._rest.get_candles.return_value = {"list": []}

        await adapter.get_candles("BTC-USDT", interval="15M", limit=10)

        adapter._rest.get_candles.assert_called_once_with(
            "BTCUSDT", interval="15", limit=10, category="spot"
        )

    async def test_get_balance(self):
        """get_balance parses wallet balance response."""
        adapter = _make_adapter()
        adapter._rest.get_wallet_balance.return_value = {
            "list": [
                {
                    "coin": [
                        {"coin": "USDT", "walletBalance": "10000.00"},
                        {"coin": "BTC", "walletBalance": "0.5"},
                        {"coin": "ETH", "walletBalance": "0"},
                    ]
                }
            ]
        }

        balances = await adapter.get_balance()

        assert balances["USDT"] == Decimal("10000.00")
        assert balances["BTC"] == Decimal("0.5")
        assert "ETH" not in balances  # zero balance excluded

    async def test_get_balance_filtered_by_currency(self):
        """get_balance with currency filter returns only that currency."""
        adapter = _make_adapter()
        adapter._rest.get_wallet_balance.return_value = {
            "list": [
                {
                    "coin": [
                        {"coin": "USDT", "walletBalance": "10000.00"},
                        {"coin": "BTC", "walletBalance": "0.5"},
                    ]
                }
            ]
        }

        balances = await adapter.get_balance(currency="BTC")

        assert "BTC" in balances
        assert "USDT" not in balances

    async def test_get_positions_derived_from_balances(self):
        """Spot positions are derived from wallet balances."""
        adapter = _make_adapter()
        adapter._rest.get_wallet_balance.return_value = {
            "list": [
                {
                    "coin": [
                        {"coin": "USDT", "walletBalance": "10000.00"},
                        {"coin": "SOL", "walletBalance": "5.0"},
                    ]
                }
            ]
        }

        positions = await adapter.get_positions()

        # USDT is a quote asset, not a position
        assert len(positions) == 1
        assert positions[0].market_id == "SOL-USDT"
        assert positions[0].quantity == Decimal("5.0")
        assert positions[0].average_entry_price == Decimal("0")

    async def test_place_order_returns_exchange_order_id(self):
        """place_order returns the exchange order ID string."""
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {"orderId": "98765"}

        order = Order(
            order_id="test-order-1",
            market_id="BTC-USDT",
            side="BUY",
            order_type="LIMIT",
            quantity=Decimal("0.01"),
            price=Decimal("50000.00"),
        )

        exchange_id = await adapter.place_order(order)

        assert exchange_id == "98765"
        adapter._rest.place_order.assert_called_once_with(
            symbol="BTCUSDT",
            side="Buy",
            order_type="Limit",
            qty="0.01",
            price="50000.00",
            order_link_id="test-order-1",
            category="spot",
        )

    async def test_place_order_market_sell(self):
        """Market SELL order uses correct Bybit params."""
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {"orderId": "98766"}

        order = Order(
            order_id="test-order-2",
            market_id="ETH-USDT",
            side="SELL",
            order_type="MARKET",
            quantity=Decimal("1.0"),
        )

        exchange_id = await adapter.place_order(order)

        assert exchange_id == "98766"
        adapter._rest.place_order.assert_called_once_with(
            symbol="ETHUSDT",
            side="Sell",
            order_type="Market",
            qty="1.0",
            price=None,
            order_link_id="test-order-2",
            category="spot",
        )

    async def test_api_error_propagates(self):
        """BybitAPIError is propagated to caller."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.side_effect = BybitAPIError(code="10001", message="Invalid symbol")

        with pytest.raises(BybitAPIError):
            await adapter.get_ticker("INVALID-PAIR")

    async def test_disconnect_sets_reconciliation_flag(self):
        """After disconnect handling, reconciliation is required."""
        adapter = _make_adapter()
        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

    async def test_reconcile_resets_flag(self):
        """reconcile() resets the needs_reconciliation flag."""
        adapter = _make_adapter()
        adapter._rest.get_open_orders.return_value = {"list": []}
        adapter._rest.get_wallet_balance.return_value = {"list": []}

        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

        await adapter.reconcile()
        assert adapter.needs_reconciliation is False

    async def test_get_instruments_filters_non_trading(self):
        """get_instruments only returns Trading status instruments."""
        adapter = _make_adapter()
        adapter._rest.get_instruments.return_value = {
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "status": "Trading",
                    "baseCoin": "BTC",
                    "quoteCoin": "USDT",
                    "lotSizeFilter": {
                        "minOrderQty": "0.00001",
                        "maxOrderQty": "100",
                        "qtyStep": "0.00001",
                    },
                    "priceFilter": {"tickSize": "0.01"},
                },
                {
                    "symbol": "DELISTED",
                    "status": "Closed",
                    "baseCoin": "DEL",
                    "quoteCoin": "USDT",
                    "lotSizeFilter": {"minOrderQty": "0.001"},
                    "priceFilter": {"tickSize": "0.001"},
                },
            ]
        }

        markets = await adapter.get_instruments()

        assert len(markets) == 1
        assert markets[0].market_id == "BTC-USDT"
        assert markets[0].is_active is True


class TestBybitSymbolConversion:
    """Symbol normalization round-trip for Bybit."""

    def test_normalized_to_concatenated(self):
        assert to_concatenated_symbol("BTC-USDT") == "BTCUSDT"
        assert to_concatenated_symbol("ETH-USDT") == "ETHUSDT"

    def test_concatenated_to_normalized(self):
        assert to_normalized_market_id("BTCUSDT") == "BTC-USDT"
        assert to_normalized_market_id("ETHUSDT") == "ETH-USDT"

    def test_round_trip(self):
        """normalize → concatenate → normalize returns original."""
        original = "BTC-USDT"
        concatenated = to_concatenated_symbol(original)
        back = to_normalized_market_id(concatenated)
        assert back == original
