"""
Tests for ExchangeAdapter interface compliance.

Verifies that all exchange adapters (OKX, Binance, Bybit) implement
the ExchangeAdapter interface correctly. This is a protocol compliance
test — every adapter must pass these checks.

Security rule #12: Reconciliation required after any disconnect.
"""

from abc import ABC
from decimal import Decimal
from typing import ClassVar

import pytest

from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.infrastructure.binance.adapter import BinanceAdapter
from trading_grid.infrastructure.bybit.adapter import BybitAdapter
from trading_grid.infrastructure.okx.adapter import OKXAdapter


class TestExchangeAdapterIsABC:
    """Verify ExchangeAdapter is a proper abstract base class."""

    def test_is_abstract(self) -> None:
        """ExchangeAdapter must be an ABC."""
        assert issubclass(ExchangeAdapter, ABC)

    def test_cannot_instantiate(self) -> None:
        """ExchangeAdapter cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ExchangeAdapter()  # type: ignore[abstract]


class TestAllAdaptersImplementInterface:
    """Every adapter must implement all interface methods."""

    ADAPTERS: ClassVar[list[type[ExchangeAdapter]]] = [OKXAdapter, BinanceAdapter, BybitAdapter]

    def test_all_adapters_are_subclasses(self) -> None:
        """All adapters must be subclasses of ExchangeAdapter."""
        for adapter_cls in self.ADAPTERS:
            assert issubclass(adapter_cls, ExchangeAdapter), (
                f"{adapter_cls.__name__} must inherit from ExchangeAdapter"
            )

    def test_all_adapters_have_exchange_id(self) -> None:
        """All adapters must have exchange_id property."""
        for adapter_cls in self.ADAPTERS:
            assert hasattr(adapter_cls, "exchange_id"), (
                f"{adapter_cls.__name__} missing exchange_id"
            )

    def test_all_adapters_have_mode(self) -> None:
        """All adapters must have mode property."""
        for adapter_cls in self.ADAPTERS:
            assert hasattr(adapter_cls, "mode"), f"{adapter_cls.__name__} missing mode"

    def test_all_adapters_have_required_methods(self) -> None:
        """All adapters must implement all required interface methods."""
        required_methods = [
            # Connection management
            "connect",
            "disconnect",
            "start_market_data_ws",
            "start_private_ws",
            "on_order_update",
            "on_ticker",
            # Market data
            "get_instruments",
            "get_ticker",
            "get_orderbook",
            "get_candles",
            # Account
            "get_balance",
            "get_positions",
            # Order management
            "place_order",
            "cancel_order",
            "get_order_status",
            "get_pending_orders",
            "get_fills",
            # Reconciliation
            "reconcile",
        ]
        for adapter_cls in self.ADAPTERS:
            for method_name in required_methods:
                assert hasattr(adapter_cls, method_name), (
                    f"{adapter_cls.__name__} missing method: {method_name}"
                )
                method = getattr(adapter_cls, method_name)
                assert callable(method), f"{adapter_cls.__name__}.{method_name} is not callable"

    def test_reconcile_method_exists(self) -> None:
        """Security rule #12: reconcile must exist on all adapters."""
        for adapter_cls in self.ADAPTERS:
            assert hasattr(adapter_cls, "reconcile"), (
                f"{adapter_cls.__name__} missing reconcile method (required by security rule #12)"
            )

    def test_needs_reconciliation_property_exists(self) -> None:
        """Security rule #12: needs_reconciliation property must exist."""
        for adapter_cls in self.ADAPTERS:
            assert hasattr(adapter_cls, "needs_reconciliation"), (
                f"{adapter_cls.__name__} missing needs_reconciliation property"
            )


class TestAdapterExchangeIds:
    """Verify each adapter returns the correct exchange ID."""

    def test_okx_exchange_id(self) -> None:
        """OKXAdapter.exchange_id == 'OKX'."""
        from trading_grid.config.settings import OKXSettings

        settings = OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        adapter = OKXAdapter(settings)
        assert adapter.exchange_id == "OKX"

    def test_binance_exchange_id(self) -> None:
        """BinanceAdapter.exchange_id == 'BINANCE'."""
        from trading_grid.config.settings import BinanceSettings

        settings = BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        adapter = BinanceAdapter(settings)
        assert adapter.exchange_id == "BINANCE"

    def test_bybit_exchange_id(self) -> None:
        """BybitAdapter.exchange_id == 'BYBIT'."""
        from trading_grid.config.settings import BybitSettings

        settings = BybitSettings(api_key="k", api_secret="s", _env_file=None)
        adapter = BybitAdapter(settings)
        assert adapter.exchange_id == "BYBIT"


class TestAdapterModes:
    """Verify each adapter returns correct mode (DEMO/LIVE)."""

    def test_okx_demo_mode(self) -> None:
        """OKXAdapter defaults to DEMO."""
        from trading_grid.config.settings import OKXSettings

        settings = OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        adapter = OKXAdapter(settings)
        assert adapter.mode == "DEMO"

    def test_binance_demo_mode(self) -> None:
        """BinanceAdapter defaults to DEMO (testnet)."""
        from trading_grid.config.settings import BinanceSettings

        settings = BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        adapter = BinanceAdapter(settings)
        assert adapter.mode == "DEMO"

    def test_bybit_demo_mode(self) -> None:
        """BybitAdapter defaults to DEMO (testnet)."""
        from trading_grid.config.settings import BybitSettings

        settings = BybitSettings(api_key="k", api_secret="s", _env_file=None)
        adapter = BybitAdapter(settings)
        assert adapter.mode == "DEMO"

    def test_binance_live_mode(self) -> None:
        """BinanceAdapter is LIVE when testnet_mode=False."""
        from trading_grid.config.settings import BinanceSettings

        settings = BinanceSettings(api_key="k", api_secret="s", testnet_mode=False, _env_file=None)
        adapter = BinanceAdapter(settings)
        assert adapter.mode == "LIVE"

    def test_bybit_live_mode(self) -> None:
        """BybitAdapter is LIVE when testnet_mode=False."""
        from trading_grid.config.settings import BybitSettings

        settings = BybitSettings(api_key="k", api_secret="s", testnet_mode=False, _env_file=None)
        adapter = BybitAdapter(settings)
        assert adapter.mode == "LIVE"


class TestGetTickerModel:
    """[D-M8] Test get_ticker_model domain conversion."""

    @pytest.mark.asyncio
    async def test_get_ticker_model_converts_dict_to_ticker_instance(self) -> None:
        """ExchangeAdapter.get_ticker_model must parse dict into domain Ticker."""
        from unittest.mock import AsyncMock
        from trading_grid.config.settings import OKXSettings
        from trading_grid.domain.market.models import Ticker

        settings = OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        adapter = OKXAdapter(settings)
        adapter.get_ticker = AsyncMock(return_value={
            "instId": "BTC-USDT",
            "last": "65000.5",
            "bid": "65000.0",
            "ask": "65001.0",
            "vol24h": "1234.5",
        })

        ticker = await adapter.get_ticker_model("BTC-USDT")
        assert isinstance(ticker, Ticker)
        assert ticker.market_id == "BTC-USDT"
        assert ticker.last_price == Decimal("65000.5")
        assert ticker.bid_price == Decimal("65000.0")
        assert ticker.ask_price == Decimal("65001.0")
        assert ticker.volume_24h == Decimal("1234.5")

