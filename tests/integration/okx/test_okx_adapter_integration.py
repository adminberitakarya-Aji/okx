"""
Integration tests for OKX adapter.

These tests verify the full adapter wiring: adapter -> REST client -> response
parsing -> domain models, using realistic OKX API response payloads.
HTTP calls are mocked at the REST client level to avoid real network requests.
"""

from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from trading_grid.config.settings import OKXSettings
from trading_grid.domain.execution.models import Order
from trading_grid.infrastructure.okx.adapter import OKXAdapter
from trading_grid.infrastructure.okx.rest_client import OKXAPIError


def _make_settings(demo: bool = True) -> OKXSettings:
    return OKXSettings(
        api_key="test-key",
        api_secret="test-secret",
        passphrase="test-passphrase",
        demo_mode=demo,
        _env_file=None,
    )


def _make_adapter(demo: bool = True) -> OKXAdapter:
    adapter = OKXAdapter(_make_settings(demo))
    adapter._rest = AsyncMock()
    return adapter


class TestOKXAdapterIntegration:
    """Full adapter flow: create -> connect -> market data -> orders."""

    async def test_adapter_creation_and_properties(self):
        """Adapter is created with correct exchange ID and mode."""
        adapter = _make_adapter(demo=True)
        assert adapter.exchange_id == "OKX"
        assert adapter.mode == "DEMO"
        assert adapter.needs_reconciliation is False

    async def test_adapter_live_mode(self):
        """Live mode adapter has LIVE execution mode."""
        adapter = _make_adapter(demo=False)
        assert adapter.mode == "LIVE"

    async def test_get_instruments_returns_domain_models(self):
        """get_instruments returns a list of Market domain models."""
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
        ]

        markets = await adapter.get_instruments()

        assert len(markets) == 1
        market = markets[0]
        assert market.market_id == "BTC-USDT"
        assert market.base_currency == "BTC"
        assert market.quote_currency == "USDT"
        assert market.min_order_size == Decimal("0.00001")
        assert market.tick_size == Decimal("0.1")
        assert market.is_active is True

    async def test_get_ticker_returns_domain_model(self):
        """get_ticker returns a domain Ticker model (not a raw dict) per [D-M8]."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {
            "instId": "BTC-USDT",
            "last": "50000.00",
            "bidPx": "49999.00",
            "askPx": "50001.00",
            "vol24h": "1234.56",
        }

        ticker = await adapter.get_ticker("BTC-USDT")

        # [D-M8] Adapter returns a normalized Ticker domain model
        assert ticker.market_id == "BTC-USDT"
        assert ticker.last_price == Decimal("50000.00")
        assert ticker.bid_price == Decimal("49999.00")
        assert ticker.ask_price == Decimal("50001.00")
        adapter._rest.get_ticker.assert_called_once_with("BTC-USDT")

    async def test_get_orderbook_returns_domain_model(self):
        """get_orderbook returns a properly parsed OrderBook domain object."""
        adapter = _make_adapter()
        adapter._rest.get_orderbook.return_value = {
            "bids": [["50000.00", "1.5", "0", "1"], ["49999.00", "2.0", "0", "2"]],
            "asks": [["50001.00", "1.0", "0", "1"], ["50002.00", "3.0", "0", "3"]],
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
            [1700000000000, "50000.00", "50100.00", "49900.00", "50050.00", "100.0"],
            [1700000060000, "50050.00", "50200.00", "50000.00", "50150.00", "120.0"],
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
            "ordId": "12345",
            "clOrdId": "test-client-id",
            "sCode": "0",
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
            "ordId": "12346",
            "clOrdId": "test-order-2",
            "sCode": "0",
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

    async def test_place_order_failure_raises(self):
        """place_order raises OKXAPIError when ordId is missing."""
        adapter = _make_adapter()
        adapter._rest.place_order.return_value = {
            "sCode": "51000",
            "sMsg": "Insufficient balance",
        }

        order = Order(
            order_id="test-order-3",
            market_id="BTC-USDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
        )

        with pytest.raises(OKXAPIError):
            await adapter.place_order(order)

    async def test_cancel_order(self):
        """cancel_order calls REST client with correct params."""
        adapter = _make_adapter()
        adapter._rest.cancel_order.return_value = {"ordId": "12345"}

        result = await adapter.cancel_order("BTC-USDT", "12345")
        assert result is True

    async def test_cancel_order_failure_returns_false(self):
        """cancel_order returns False when API raises error."""
        adapter = _make_adapter()
        adapter._rest.cancel_order.side_effect = OKXAPIError(
            code="51400", message="Order does not exist"
        )

        result = await adapter.cancel_order("BTC-USDT", "99999")
        assert result is False

    async def test_get_order_status_mapping(self):
        """Order status is correctly mapped from OKX to domain."""
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "ordId": "12345",
            "state": "partially_filled",
            "side": "buy",
            "ordType": "limit",
            "px": "50000.00",
            "sz": "0.01",
            "accFillSz": "0.005",
            "avgPx": "50000.00",
        }

        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "PARTIALLY_FILLED"
        assert status["filled_quantity"] == "0.005"
        assert status["average_price"] == "50000.00"

    async def test_get_order_status_filled(self):
        """Filled order status is mapped correctly."""
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "ordId": "12345",
            "state": "filled",
            "accFillSz": "0.01",
            "avgPx": "50000.00",
        }

        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "FILLED"

    async def test_get_order_status_canceled(self):
        """Canceled order status is mapped correctly."""
        adapter = _make_adapter()
        adapter._rest.get_order.return_value = {
            "ordId": "12345",
            "state": "canceled",
            "accFillSz": "0",
        }

        status = await adapter.get_order_status("BTC-USDT", "12345")
        assert status["status"] == "CANCELLED"

    async def test_get_balance(self):
        """get_balance returns parsed balances."""
        adapter = _make_adapter()
        adapter._rest.get_account_balance.return_value = {
            "details": [
                {"ccy": "USDT", "availBal": "1000.00", "frozenBal": "100.00"},
                {"ccy": "BTC", "availBal": "0.5", "frozenBal": "0"},
            ],
        }

        balances = await adapter.get_balance()

        assert balances["USDT"] == Decimal("1100.00")
        assert balances["BTC"] == Decimal("0.5")

    async def test_get_positions(self):
        """get_positions returns parsed positions."""
        adapter = _make_adapter()
        adapter._rest.get_positions.return_value = [
            {
                "instId": "BTC-USDT",
                "pos": "0.5",
                "avgPx": "45000.00",
            },
        ]

        positions = await adapter.get_positions()

        assert len(positions) == 1
        assert positions[0].market_id == "BTC-USDT"
        assert positions[0].quantity == Decimal("0.5")
        assert positions[0].average_entry_price == Decimal("45000.00")

    async def test_get_fills(self):
        """get_fills returns parsed fills."""
        adapter = _make_adapter()
        adapter._rest.get_fills.return_value = [
            {
                "tradeId": "t1",
                "ordId": "12345",
                "instId": "BTC-USDT",
                "side": "buy",
                "fillPx": "50000.00",
                "fillSz": "0.01",
                "fee": "-0.05",
                "feeCcy": "USDT",
            },
        ]

        fills = await adapter.get_fills("BTC-USDT")

        assert len(fills) == 1
        assert fills[0].trade_id == "t1"
        assert fills[0].side == "BUY"
        assert fills[0].price == Decimal("50000.00")
        assert fills[0].fee == Decimal("0.05")

    async def test_api_error_propagates(self):
        """OKXAPIError is propagated to caller."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.side_effect = OKXAPIError(
            code="51001", message="Instrument ID does not exist"
        )

        with pytest.raises(OKXAPIError):
            await adapter.get_ticker("INVALID-PAIR")

    async def test_disconnect_sets_reconciliation_flag(self):
        """After disconnect handling, reconciliation is required."""
        adapter = _make_adapter()
        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

    async def test_reconcile_resets_flag(self):
        """reconcile() resets the needs_reconciliation flag."""
        adapter = _make_adapter()
        adapter._rest.get_pending_orders.return_value = []
        adapter._rest.get_positions.return_value = []
        adapter._rest.get_account_balance.return_value = {"details": []}

        adapter._handle_disconnect()
        assert adapter.needs_reconciliation is True

        await adapter.reconcile()
        assert adapter.needs_reconciliation is False

    async def test_on_order_update_registers_handler(self):
        """on_order_update registers a handler that receives messages."""
        adapter = _make_adapter()
        received = []
        adapter.on_order_update(lambda data: received.append(data))

        adapter._handle_private_message(
            {
                "arg": {"channel": "orders"},
                "data": [{"ordId": "12345"}],
            }
        )

        assert len(received) == 1

    async def test_on_ticker_registers_handler(self):
        """on_ticker registers a handler that receives messages."""
        adapter = _make_adapter()
        received = []
        adapter.on_ticker(lambda data: received.append(data))

        adapter._handle_public_message(
            {
                "arg": {"channel": "tickers"},
                "data": [{"instId": "BTC-USDT"}],
            }
        )

        assert len(received) == 1
