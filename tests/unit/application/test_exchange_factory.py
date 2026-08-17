"""
Tests for the exchange adapter factory.

Verifies:
1. Factory creates the correct adapter type per exchange ID
2. Unconfigured exchanges raise ExchangeNotConfiguredError
3. Unsupported exchange IDs raise ValueError
4. get_configured_exchanges returns only configured exchanges
5. Adapter mode reflects demo/testnet settings
6. ExchangeAdapterFactory class: create(), validate_config(), get_configured_exchanges()
7. Backward-compatible function wrappers
8. create_for_user (Phase 5 multi-tenant) builds adapters from user credentials
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from okx_trading.application.services.exchange_factory import (
    SUPPORTED_EXCHANGES,
    ExchangeAdapterFactory,
    create_exchange_adapter,
    get_configured_exchanges,
)
from okx_trading.config.settings import (
    BinanceSettings,
    BybitSettings,
    OKXSettings,
    Settings,
)
from okx_trading.domain.exchange.errors import ExchangeNotConfiguredError
from okx_trading.infrastructure.binance.adapter import BinanceAdapter
from okx_trading.infrastructure.bybit.adapter import BybitAdapter
from okx_trading.infrastructure.okx.adapter import OKXAdapter


def make_settings(
    okx_configured: bool = False,
    binance_configured: bool = False,
    bybit_configured: bool = False,
) -> Settings:
    """Build a Settings instance with selected exchanges configured."""
    okx = (
        OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        if okx_configured
        else OKXSettings(_env_file=None)
    )
    binance = (
        BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        if binance_configured
        else BinanceSettings(_env_file=None)
    )
    bybit = (
        BybitSettings(api_key="k", api_secret="s", _env_file=None)
        if bybit_configured
        else BybitSettings(_env_file=None)
    )
    return Settings(okx=okx, binance=binance, bybit=bybit, _env_file=None)


class TestCreateExchangeAdapter:
    """Tests for create_exchange_adapter."""

    def test_creates_okx_adapter(self) -> None:
        """Factory returns OKXAdapter for OKX."""
        settings = make_settings(okx_configured=True)
        adapter = create_exchange_adapter("OKX", settings)
        assert isinstance(adapter, OKXAdapter)
        assert adapter.exchange_id == "OKX"

    def test_creates_binance_adapter(self) -> None:
        """Factory returns BinanceAdapter for BINANCE."""
        settings = make_settings(binance_configured=True)
        adapter = create_exchange_adapter("BINANCE", settings)
        assert isinstance(adapter, BinanceAdapter)
        assert adapter.exchange_id == "BINANCE"

    def test_creates_bybit_adapter(self) -> None:
        """Factory returns BybitAdapter for BYBIT."""
        settings = make_settings(bybit_configured=True)
        adapter = create_exchange_adapter("BYBIT", settings)
        assert isinstance(adapter, BybitAdapter)
        assert adapter.exchange_id == "BYBIT"

    def test_case_insensitive_exchange_id(self) -> None:
        """Factory accepts lowercase exchange IDs."""
        settings = make_settings(binance_configured=True)
        adapter = create_exchange_adapter("binance", settings)  # type: ignore[arg-type]
        assert isinstance(adapter, BinanceAdapter)

    def test_unconfigured_okx_raises(self) -> None:
        """Unconfigured OKX raises ExchangeNotConfiguredError."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            create_exchange_adapter("OKX", settings)

    def test_unconfigured_binance_raises(self) -> None:
        """Unconfigured Binance raises ExchangeNotConfiguredError."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            create_exchange_adapter("BINANCE", settings)

    def test_unconfigured_bybit_raises(self) -> None:
        """Unconfigured Bybit raises ExchangeNotConfiguredError."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            create_exchange_adapter("BYBIT", settings)

    def test_unsupported_exchange_raises_value_error(self) -> None:
        """Unsupported exchange ID raises ValueError."""
        settings = make_settings()
        with pytest.raises(ValueError, match="Unsupported exchange"):
            create_exchange_adapter("KRAKEN", settings)  # type: ignore[arg-type]

    def test_okx_demo_mode_default(self) -> None:
        """OKX adapter defaults to DEMO mode."""
        settings = make_settings(okx_configured=True)
        adapter = create_exchange_adapter("OKX", settings)
        assert adapter.mode == "DEMO"

    def test_binance_testnet_mode_default(self) -> None:
        """Binance adapter defaults to DEMO mode (testnet)."""
        settings = make_settings(binance_configured=True)
        adapter = create_exchange_adapter("BINANCE", settings)
        assert adapter.mode == "DEMO"

    def test_bybit_testnet_mode_default(self) -> None:
        """Bybit adapter defaults to DEMO mode (testnet)."""
        settings = make_settings(bybit_configured=True)
        adapter = create_exchange_adapter("BYBIT", settings)
        assert adapter.mode == "DEMO"

    def test_binance_live_mode(self) -> None:
        """Binance adapter is LIVE when testnet_mode=False."""
        settings = make_settings()
        settings.binance.api_key = "k"  # type: ignore[misc]
        binance = BinanceSettings(api_key="k", api_secret="s", testnet_mode=False, _env_file=None)
        settings = Settings(
            okx=OKXSettings(_env_file=None),
            binance=binance,
            bybit=BybitSettings(_env_file=None),
            _env_file=None,
        )
        adapter = create_exchange_adapter("BINANCE", settings)
        assert adapter.mode == "LIVE"


class TestGetConfiguredExchanges:
    """Tests for get_configured_exchanges."""

    def test_none_configured(self) -> None:
        """No exchanges configured returns empty list."""
        settings = make_settings()
        assert get_configured_exchanges(settings) == []

    def test_only_okx_configured(self) -> None:
        """Only OKX configured."""
        settings = make_settings(okx_configured=True)
        assert get_configured_exchanges(settings) == ["OKX"]

    def test_all_configured(self) -> None:
        """All exchanges configured."""
        settings = make_settings(
            okx_configured=True, binance_configured=True, bybit_configured=True
        )
        assert get_configured_exchanges(settings) == ["OKX", "BINANCE", "BYBIT"]

    def test_binance_and_bybit_configured(self) -> None:
        """Binance and Bybit configured, OKX not."""
        settings = make_settings(binance_configured=True, bybit_configured=True)
        assert get_configured_exchanges(settings) == ["BINANCE", "BYBIT"]


class TestExchangeAdapterFactoryClass:
    """Tests for the ExchangeAdapterFactory class."""

    def test_supported_exchanges_constant(self) -> None:
        """SUPPORTED_EXCHANGES contains all three exchanges."""
        assert SUPPORTED_EXCHANGES == ("OKX", "BINANCE", "BYBIT")

    def test_factory_create_okx(self) -> None:
        """ExchangeAdapterFactory.create returns OKXAdapter."""
        settings = make_settings(okx_configured=True)
        adapter = ExchangeAdapterFactory.create("OKX", settings)
        assert isinstance(adapter, OKXAdapter)
        assert adapter.exchange_id == "OKX"

    def test_factory_create_binance(self) -> None:
        """ExchangeAdapterFactory.create returns BinanceAdapter."""
        settings = make_settings(binance_configured=True)
        adapter = ExchangeAdapterFactory.create("BINANCE", settings)
        assert isinstance(adapter, BinanceAdapter)
        assert adapter.exchange_id == "BINANCE"

    def test_factory_create_bybit(self) -> None:
        """ExchangeAdapterFactory.create returns BybitAdapter."""
        settings = make_settings(bybit_configured=True)
        adapter = ExchangeAdapterFactory.create("BYBIT", settings)
        assert isinstance(adapter, BybitAdapter)
        assert adapter.exchange_id == "BYBIT"

    def test_factory_create_unconfigured_raises(self) -> None:
        """ExchangeAdapterFactory.create raises for unconfigured exchange."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            ExchangeAdapterFactory.create("OKX", settings)

    def test_factory_create_unsupported_raises(self) -> None:
        """ExchangeAdapterFactory.create raises ValueError for unsupported exchange."""
        settings = make_settings()
        with pytest.raises(ValueError, match="Unsupported exchange"):
            ExchangeAdapterFactory.create("KRAKEN", settings)  # type: ignore[arg-type]

    def test_factory_get_configured_exchanges(self) -> None:
        """ExchangeAdapterFactory.get_configured_exchanges returns configured list."""
        settings = make_settings(okx_configured=True, bybit_configured=True)
        result = ExchangeAdapterFactory.get_configured_exchanges(settings)
        assert result == ["OKX", "BYBIT"]


class TestValidateConfig:
    """Tests for ExchangeAdapterFactory.validate_config (fail-fast)."""

    def test_validate_configured_okx_passes(self) -> None:
        """validate_config passes for configured OKX."""
        settings = make_settings(okx_configured=True)
        # Should not raise
        ExchangeAdapterFactory.validate_config("OKX", settings)

    def test_validate_configured_binance_passes(self) -> None:
        """validate_config passes for configured Binance."""
        settings = make_settings(binance_configured=True)
        ExchangeAdapterFactory.validate_config("BINANCE", settings)

    def test_validate_configured_bybit_passes(self) -> None:
        """validate_config passes for configured Bybit."""
        settings = make_settings(bybit_configured=True)
        ExchangeAdapterFactory.validate_config("BYBIT", settings)

    def test_validate_unconfigured_okx_raises(self) -> None:
        """validate_config raises ExchangeNotConfiguredError for unconfigured OKX."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            ExchangeAdapterFactory.validate_config("OKX", settings)

    def test_validate_unconfigured_binance_raises(self) -> None:
        """validate_config raises ExchangeNotConfiguredError for unconfigured Binance."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            ExchangeAdapterFactory.validate_config("BINANCE", settings)

    def test_validate_unconfigured_bybit_raises(self) -> None:
        """validate_config raises ExchangeNotConfiguredError for unconfigured Bybit."""
        settings = make_settings()
        with pytest.raises(ExchangeNotConfiguredError):
            ExchangeAdapterFactory.validate_config("BYBIT", settings)

    def test_validate_unsupported_exchange_raises(self) -> None:
        """validate_config raises ValueError for unsupported exchange."""
        settings = make_settings()
        with pytest.raises(ValueError, match="Unsupported exchange"):
            ExchangeAdapterFactory.validate_config("KRAKEN", settings)  # type: ignore[arg-type]

    def test_validate_case_insensitive(self) -> None:
        """validate_config accepts lowercase exchange IDs."""
        settings = make_settings(binance_configured=True)
        ExchangeAdapterFactory.validate_config("binance", settings)  # type: ignore[arg-type]

    def test_create_calls_validate_first(self) -> None:
        """create() validates config before creating adapter (fail-fast)."""
        settings = make_settings()
        # create should raise the same error as validate_config
        with pytest.raises(ExchangeNotConfiguredError):
            ExchangeAdapterFactory.create("BYBIT", settings)


class TestBackwardCompatibleWrappers:
    """Tests that function wrappers delegate to the factory class."""

    def test_create_wrapper_matches_factory(self) -> None:
        """create_exchange_adapter returns same type as factory."""
        settings = make_settings(okx_configured=True)
        adapter_fn = create_exchange_adapter("OKX", settings)
        adapter_cls = ExchangeAdapterFactory.create("OKX", settings)
        assert type(adapter_fn) is type(adapter_cls)

    def test_get_configured_wrapper_matches_factory(self) -> None:
        """get_configured_exchanges returns same result as factory."""
        settings = make_settings(okx_configured=True, binance_configured=True)
        assert get_configured_exchanges(
            settings
        ) == ExchangeAdapterFactory.get_configured_exchanges(settings)


class TestCreateForUser:
    """Tests for ExchangeAdapterFactory.create_for_user (Phase 5 multi-tenant)."""

    def _make_credential(
        self,
        exchange: str = "OKX",
        environment: str = "DEMO",
        passphrase: str | None = "user-pass",
    ) -> MagicMock:
        """Build a mock DecryptedCredential."""
        cred = MagicMock()
        cred.api_key = "user-api-key"
        cred.api_secret = "user-api-secret"
        cred.passphrase = passphrase
        cred.exchange = exchange
        cred.environment = environment
        return cred

    def _make_credential_service(self, cred: MagicMock | None) -> AsyncMock:
        """Build a mock CredentialService returning the given credential."""
        service = AsyncMock()
        if cred is None:
            from okx_trading.application.services.credential_service import (
                CredentialNotFoundError,
            )

            service.get_credential.side_effect = CredentialNotFoundError("usr_1", "OKX", "DEMO")
        else:
            service.get_credential.return_value = cred
        return service

    @pytest.mark.asyncio
    async def test_creates_okx_adapter_for_user(self) -> None:
        """create_for_user returns OKXAdapter with user credentials."""
        settings = make_settings()
        cred = self._make_credential("OKX", "DEMO")
        cred_service = self._make_credential_service(cred)

        adapter = await ExchangeAdapterFactory.create_for_user(
            "OKX", "usr_1", "DEMO", cred_service, settings
        )

        assert isinstance(adapter, OKXAdapter)
        assert adapter.exchange_id == "OKX"
        assert adapter.mode == "DEMO"
        cred_service.get_credential.assert_awaited_once_with(
            user_id="usr_1", exchange="OKX", environment="DEMO"
        )

    @pytest.mark.asyncio
    async def test_creates_binance_adapter_for_user(self) -> None:
        """create_for_user returns BinanceAdapter with user credentials."""
        settings = make_settings()
        cred = self._make_credential("BINANCE", "DEMO", passphrase=None)
        cred_service = self._make_credential_service(cred)

        adapter = await ExchangeAdapterFactory.create_for_user(
            "BINANCE", "usr_1", "DEMO", cred_service, settings
        )

        assert isinstance(adapter, BinanceAdapter)
        assert adapter.exchange_id == "BINANCE"
        assert adapter.mode == "DEMO"

    @pytest.mark.asyncio
    async def test_creates_bybit_adapter_for_user(self) -> None:
        """create_for_user returns BybitAdapter with user credentials."""
        settings = make_settings()
        cred = self._make_credential("BYBIT", "DEMO", passphrase=None)
        cred_service = self._make_credential_service(cred)

        adapter = await ExchangeAdapterFactory.create_for_user(
            "BYBIT", "usr_1", "DEMO", cred_service, settings
        )

        assert isinstance(adapter, BybitAdapter)
        assert adapter.exchange_id == "BYBIT"
        assert adapter.mode == "DEMO"

    @pytest.mark.asyncio
    async def test_live_environment_sets_live_mode(self) -> None:
        """create_for_user with LIVE environment produces LIVE adapter."""
        settings = make_settings()
        cred = self._make_credential("BINANCE", "LIVE", passphrase=None)
        cred_service = self._make_credential_service(cred)

        adapter = await ExchangeAdapterFactory.create_for_user(
            "BINANCE", "usr_1", "LIVE", cred_service, settings
        )

        assert adapter.mode == "LIVE"

    @pytest.mark.asyncio
    async def test_case_insensitive_exchange_id(self) -> None:
        """create_for_user accepts lowercase exchange IDs."""
        settings = make_settings()
        cred = self._make_credential("OKX", "DEMO")
        cred_service = self._make_credential_service(cred)

        adapter = await ExchangeAdapterFactory.create_for_user(
            "okx",
            "usr_1",
            "DEMO",
            cred_service,
            settings,  # type: ignore[arg-type]
        )

        assert isinstance(adapter, OKXAdapter)

    @pytest.mark.asyncio
    async def test_unsupported_exchange_raises(self) -> None:
        """create_for_user raises ValueError for unsupported exchange."""
        settings = make_settings()
        cred_service = self._make_credential_service(None)

        with pytest.raises(ValueError, match="Unsupported exchange"):
            await ExchangeAdapterFactory.create_for_user(
                "KRAKEN",
                "usr_1",
                "DEMO",
                cred_service,
                settings,  # type: ignore[arg-type]
            )

    @pytest.mark.asyncio
    async def test_invalid_environment_raises(self) -> None:
        """create_for_user raises ValueError for invalid environment."""
        settings = make_settings()
        cred_service = self._make_credential_service(None)

        with pytest.raises(ValueError, match="Invalid environment"):
            await ExchangeAdapterFactory.create_for_user(
                "OKX", "usr_1", "STAGING", cred_service, settings
            )

    @pytest.mark.asyncio
    async def test_missing_credential_propagates_not_found(self) -> None:
        """create_for_user propagates CredentialNotFoundError from service."""
        from okx_trading.application.services.credential_service import (
            CredentialNotFoundError,
        )

        settings = make_settings()
        cred_service = self._make_credential_service(None)

        with pytest.raises(CredentialNotFoundError):
            await ExchangeAdapterFactory.create_for_user(
                "OKX", "usr_1", "DEMO", cred_service, settings
            )

    @pytest.mark.asyncio
    async def test_user_credentials_do_not_leak_to_system_settings(self) -> None:
        """User credentials must not modify system-level settings."""
        settings = make_settings()
        cred = self._make_credential("OKX", "DEMO")
        cred_service = self._make_credential_service(cred)

        await ExchangeAdapterFactory.create_for_user("OKX", "usr_1", "DEMO", cred_service, settings)

        # System settings remain untouched (no user credentials)
        assert settings.okx.api_key.get_secret_value() == ""
        assert settings.okx.api_secret.get_secret_value() == ""
