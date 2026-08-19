"""
Exchange Adapter Factory.

This module provides a factory for creating exchange adapters based on the
selected exchange ID. It receives a registry of adapter classes via dependency
injection from the composition root (infrastructure layer).

Key rules:
1. The application layer depends ONLY on the ExchangeAdapter interface
2. Concrete adapter classes are injected via registry (never imported here)
3. Selecting an exchange that is not configured raises ExchangeNotConfiguredError
4. DEMO and LIVE use separate credentials per exchange
5. Secrets never in logs
6. Fail-fast: validate_config() before adapter creation

[A-H13] Phase 10.1: Factory pattern with registry injection.
The registry is built at composition root (infrastructure/exchange/registry.py)
and injected into this factory. This ensures the application layer never
imports concrete adapters from infrastructure.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

import structlog

from trading_grid.domain.exchange.errors import ExchangeNotConfiguredError

if TYPE_CHECKING:
    from trading_grid.application.services.authorization import Identity
    from trading_grid.application.services.credential_service import (
        CredentialService,
        DecryptedCredential,
    )
    from trading_grid.config.settings import Settings
    from trading_grid.domain.exchange.interface import ExchangeAdapter
    from trading_grid.domain.shared.types import ExchangeId

# Type alias for adapter constructor: takes exchange settings, returns adapter
AdapterConstructor = Callable[[Any], "ExchangeAdapter"]

logger = structlog.get_logger()

SUPPORTED_EXCHANGES: tuple[ExchangeId, ...] = ("OKX", "BINANCE", "BYBIT")


class ExchangeAdapterFactory:
    """
    Factory for creating exchange adapters.

    [A-H13] This factory receives a registry of adapter classes via constructor
    injection. The registry is built at composition root (infrastructure layer)
    and maps exchange IDs to concrete adapter classes.

    The application layer depends only on the ExchangeAdapter interface,
    never on concrete adapter classes.

    Usage:
        # At composition root (infrastructure):
        registry = build_adapter_registry()  # {"OKX": OKXAdapter, ...}
        factory = ExchangeAdapterFactory(registry)

        # In application code:
        adapter = factory.create("BINANCE", settings)
        factory.validate_config("BINANCE", settings)  # fail-fast
        configured = factory.get_configured_exchanges(settings)
    """

    def __init__(self, registry: dict[str, AdapterConstructor]) -> None:
        """
        Initialize the factory with an adapter registry.

        Args:
            registry: Mapping of exchange IDs to adapter constructors,
                e.g., {"OKX": OKXAdapter, "BINANCE": BinanceAdapter, "BYBIT": BybitAdapter}
        """
        self._registry = registry

    @property
    def registry(self) -> dict[str, AdapterConstructor]:
        """Get the adapter registry (for inspection/testing)."""
        return dict(self._registry)

    def validate_config(self, exchange_id: ExchangeId, settings: Settings) -> None:
        """
        Validate that an exchange is properly configured.

        Fail-fast validation that should be called before creating an adapter.
        Raises immediately if credentials are missing or exchange is unsupported.

        Args:
            exchange_id: Exchange to validate ("OKX", "BINANCE", "BYBIT")
            settings: Application settings containing exchange credentials

        Raises:
            ValueError: If the exchange_id is not supported
            ExchangeNotConfiguredError: If the exchange credentials are missing
        """
        exchange_id_upper = exchange_id.upper()

        if exchange_id_upper not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange: {exchange_id!r}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES)}"
            )

        if exchange_id_upper == "OKX" and not settings.okx.is_configured:
            raise ExchangeNotConfiguredError("OKX")

        if exchange_id_upper == "BINANCE" and not settings.binance.is_configured:
            raise ExchangeNotConfiguredError("BINANCE")

        if exchange_id_upper == "BYBIT" and not settings.bybit.is_configured:
            raise ExchangeNotConfiguredError("BYBIT")

    def create(self, exchange_id: ExchangeId, settings: Settings) -> ExchangeAdapter:
        """
        Create an exchange adapter for the given exchange ID.

        Validates configuration first (fail-fast), then creates the adapter
        using the registered adapter class.

        Args:
            exchange_id: Exchange to create adapter for ("OKX", "BINANCE", "BYBIT")
            settings: Application settings containing exchange credentials

        Returns:
            Configured ExchangeAdapter instance

        Raises:
            ExchangeNotConfiguredError: If the exchange credentials are missing
            ValueError: If the exchange_id is not supported
        """
        # Fail-fast validation before creating adapter
        self.validate_config(exchange_id, settings)

        exchange_id_upper = exchange_id.upper()

        adapter_cls = self._registry.get(exchange_id_upper)
        if adapter_cls is None:
            raise ValueError(
                f"No adapter registered for exchange: {exchange_id!r}. "
                f"Registered: {', '.join(self._registry.keys())}"
            )

        # Get the appropriate settings for this exchange
        exchange_settings = self._get_exchange_settings(exchange_id_upper, settings)

        adapter = adapter_cls(exchange_settings)

        logger.info(
            "exchange_adapter_created",
            exchange=adapter.exchange_id,
            mode=adapter.mode,
        )
        return adapter

    def _get_exchange_settings(self, exchange_id: str, settings: Settings) -> Any:
        """
        Get the exchange-specific settings object for an adapter.

        Args:
            exchange_id: Normalized exchange ID (uppercase)
            settings: Application settings

        Returns:
            Exchange-specific settings (OKXSettings, BinanceSettings, or BybitSettings)
        """
        if exchange_id == "OKX":
            return settings.okx
        if exchange_id == "BINANCE":
            return settings.binance
        return settings.bybit  # BYBIT

    def get_configured_exchanges(self, settings: Settings) -> list[ExchangeId]:
        """
        Get list of exchanges that have credentials configured.

        Args:
            settings: Application settings

        Returns:
            List of configured exchange IDs
        """
        configured: list[ExchangeId] = []
        if settings.okx.is_configured:
            configured.append("OKX")
        if settings.binance.is_configured:
            configured.append("BINANCE")
        if settings.bybit.is_configured:
            configured.append("BYBIT")
        return configured

    async def create_for_user(
        self,
        exchange_id: ExchangeId,
        user_id: str,
        environment: str,
        credential_service: CredentialService,
        settings: Settings,
        identity: Identity | None = None,
    ) -> ExchangeAdapter:
        """
        Create an exchange adapter using a user's stored credentials (Phase 5).

        This is the multi-tenant entry point. Instead of using system-level
        credentials from settings, it retrieves the user's encrypted credentials
        from the credential service, decrypts them, and builds an adapter
        scoped to that user.

        Security rules:
        1. Credentials are decrypted in-memory only, never logged
        2. The adapter is scoped to the user's environment (DEMO/LIVE)
        3. LIVE environment requires explicit approval upstream
        4. Secrets never in logs

        Args:
            exchange_id: Exchange to create adapter for ("OKX", "BINANCE", "BYBIT")
            user_id: User ID whose credentials to use
            environment: "DEMO" or "LIVE"
            credential_service: Service for retrieving encrypted credentials
            settings: Application settings (for base URLs, timeouts, etc.)
            identity: [A-H8] Optional authenticated identity for RBAC. If not
                provided, a SYSTEM identity is used (system-level operations
                like autonomous grid execution are authorized to access
                credentials for any user).

        Returns:
            Configured ExchangeAdapter instance using user credentials

        Raises:
            CredentialNotFoundError: If user has no active credential
            CredentialEncryptionError: If decryption fails
            ValueError: If exchange_id or environment is invalid
        """
        from trading_grid.application.services.authorization import Identity, Role

        exchange_id_upper = exchange_id.upper()

        if exchange_id_upper not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange: {exchange_id!r}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES)}"
            )

        if environment not in ("DEMO", "LIVE"):
            raise ValueError(f"Invalid environment: {environment!r}. Use DEMO or LIVE.")

        # [A-H8] Use provided identity or default to SYSTEM identity for
        # system-level operations (autonomous grid execution, etc.)
        if identity is None:
            identity = Identity(
                identity_id="system",
                identity_type="SYSTEM",
                role=Role.SYSTEM_ADMIN,
            )

        # Retrieve and decrypt user credential
        cred: DecryptedCredential = await credential_service.get_credential(
            user_id=user_id,
            exchange=exchange_id_upper,
            environment=environment,
            identity=identity,
        )

        # Build adapter with user credentials
        adapter = self._build_adapter_from_credential(
            exchange_id_upper, cred, environment, settings
        )

        logger.info(
            "user_exchange_adapter_created",
            exchange=adapter.exchange_id,
            mode=adapter.mode,
            user_id=user_id,
            environment=environment,
        )
        return adapter

    def _build_adapter_from_credential(
        self,
        exchange_id: ExchangeId,
        cred: DecryptedCredential,
        environment: str,
        settings: Settings,
    ) -> ExchangeAdapter:
        """
        Build an adapter instance from decrypted user credentials.

        Internal helper. Never logs credential values.

        [A-H13] Uses the registry to get the adapter class instead of
        importing concrete adapters directly.

        Args:
            exchange_id: Normalized exchange ID (uppercase)
            cred: Decrypted credential container
            environment: "DEMO" or "LIVE"
            settings: Application settings for base URLs/timeouts

        Returns:
            Configured ExchangeAdapter instance
        """
        is_demo = environment == "DEMO"

        adapter_cls = self._registry.get(exchange_id)
        if adapter_cls is None:
            raise ValueError(
                f"No adapter registered for exchange: {exchange_id!r}. "
                f"Registered: {', '.join(self._registry.keys())}"
            )

        # Build exchange-specific settings with user credentials
        exchange_settings = self._build_settings_from_credential(
            exchange_id, cred, is_demo, settings
        )

        return adapter_cls(exchange_settings)

    def _build_settings_from_credential(
        self,
        exchange_id: str,
        cred: DecryptedCredential,
        is_demo: bool,
        settings: Settings,
    ) -> Any:
        """
        Build exchange-specific settings from decrypted user credentials.

        Args:
            exchange_id: Normalized exchange ID (uppercase)
            cred: Decrypted credential container
            is_demo: True for DEMO environment, False for LIVE
            settings: Application settings for base URLs/timeouts

        Returns:
            Exchange-specific settings object
        """
        if exchange_id == "OKX":
            from trading_grid.config.settings import OKXSettings

            return OKXSettings(
                api_key=cred.api_key,  # type: ignore[arg-type]
                api_secret=cred.api_secret,  # type: ignore[arg-type]
                passphrase=cred.passphrase or "",  # type: ignore[arg-type]
                demo_mode=is_demo,
                base_url=settings.okx.base_url,
                ws_url=settings.okx.ws_url,
                timeout=settings.okx.timeout,
                max_retries=settings.okx.max_retries,
            )

        if exchange_id == "BINANCE":
            from trading_grid.config.settings import BinanceSettings

            return BinanceSettings(
                api_key=cred.api_key,  # type: ignore[arg-type]
                api_secret=cred.api_secret,  # type: ignore[arg-type]
                testnet_mode=is_demo,
                base_url=settings.binance.base_url,
                testnet_base_url=settings.binance.testnet_base_url,
                ws_url=settings.binance.ws_url,
                testnet_ws_url=settings.binance.testnet_ws_url,
                timeout=settings.binance.timeout,
                max_retries=settings.binance.max_retries,
            )

        # BYBIT
        from trading_grid.config.settings import BybitSettings

        return BybitSettings(
            api_key=cred.api_key,  # type: ignore[arg-type]
            api_secret=cred.api_secret,  # type: ignore[arg-type]
            testnet_mode=is_demo,
            base_url=settings.bybit.base_url,
            testnet_base_url=settings.bybit.testnet_base_url,
            ws_url=settings.bybit.ws_url,
            testnet_ws_url=settings.bybit.testnet_ws_url,
            timeout=settings.bybit.timeout,
            max_retries=settings.bybit.max_retries,
        )


# ---------------------------------------------------------------------------
# Module-level factory instance (set at composition root)
# ---------------------------------------------------------------------------

_factory_instance: ExchangeAdapterFactory | None = None


def set_factory(factory: ExchangeAdapterFactory) -> None:
    """
    Set the module-level factory instance.

    Called at composition root (api/app.py or service_container.py) after
    building the registry.

    Args:
        factory: Configured ExchangeAdapterFactory instance
    """
    global _factory_instance
    _factory_instance = factory
    logger.info("exchange_adapter_factory_set")


def get_factory() -> ExchangeAdapterFactory:
    """
    Get the module-level factory instance.

    Raises:
        RuntimeError: If factory has not been set (call set_factory first)
    """
    if _factory_instance is None:
        raise RuntimeError(
            "ExchangeAdapterFactory not initialized. "
            "Call set_factory() at composition root first."
        )
    return _factory_instance


# ---------------------------------------------------------------------------
# Backward-compatible function wrappers
# ---------------------------------------------------------------------------


def create_exchange_adapter(exchange_id: ExchangeId, settings: Settings) -> ExchangeAdapter:
    """
    Create an exchange adapter for the given exchange ID.

    Backward-compatible wrapper around get_factory().create().

    Args:
        exchange_id: Exchange to create adapter for ("OKX", "BINANCE", "BYBIT")
        settings: Application settings containing exchange credentials

    Returns:
        Configured ExchangeAdapter instance

    Raises:
        ExchangeNotConfiguredError: If the exchange credentials are missing
        ValueError: If the exchange_id is not supported
        RuntimeError: If factory has not been initialized
    """
    return get_factory().create(exchange_id, settings)


def get_configured_exchanges(settings: Settings) -> list[ExchangeId]:
    """
    Get list of exchanges that have credentials configured.

    Backward-compatible wrapper around get_factory().get_configured_exchanges().

    Args:
        settings: Application settings

    Returns:
        List of configured exchange IDs

    Raises:
        RuntimeError: If factory has not been initialized
    """
    return get_factory().get_configured_exchanges(settings)
