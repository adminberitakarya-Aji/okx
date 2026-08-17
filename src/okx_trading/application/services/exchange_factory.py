"""
Exchange Adapter Factory.

This module provides a factory for creating exchange adapters based on the
selected exchange ID. It is the single wiring point between configuration
and concrete exchange implementations.

Key rules:
1. The application layer depends ONLY on the ExchangeAdapter interface
2. Selecting an exchange that is not configured raises ExchangeNotConfiguredError
3. DEMO and LIVE use separate credentials per exchange
4. Secrets never in logs
5. Fail-fast: validate_config() before adapter creation
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from okx_trading.domain.exchange.errors import ExchangeNotConfiguredError

if TYPE_CHECKING:
    from okx_trading.application.services.credential_service import (
        CredentialService,
        DecryptedCredential,
    )
    from okx_trading.config.settings import Settings
    from okx_trading.domain.exchange.interface import ExchangeAdapter
    from okx_trading.domain.shared.types import ExchangeId

logger = structlog.get_logger()

SUPPORTED_EXCHANGES: tuple[ExchangeId, ...] = ("OKX", "BINANCE", "BYBIT")


class ExchangeAdapterFactory:
    """
    Factory for creating exchange adapters.

    This is the single wiring point between configuration and concrete
    exchange implementations. The application layer depends only on the
    ExchangeAdapter interface, never on concrete adapter classes.

    Usage:
        adapter = ExchangeAdapterFactory.create("BINANCE", settings)
        ExchangeAdapterFactory.validate_config("BINANCE", settings)  # fail-fast
        configured = ExchangeAdapterFactory.get_configured_exchanges(settings)
    """

    @staticmethod
    def validate_config(exchange_id: ExchangeId, settings: Settings) -> None:
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

    @staticmethod
    def create(exchange_id: ExchangeId, settings: Settings) -> ExchangeAdapter:
        """
        Create an exchange adapter for the given exchange ID.

        Validates configuration first (fail-fast), then creates the adapter.

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
        ExchangeAdapterFactory.validate_config(exchange_id, settings)

        exchange_id_upper = exchange_id.upper()

        if exchange_id_upper == "OKX":
            from okx_trading.infrastructure.okx.adapter import OKXAdapter

            adapter: ExchangeAdapter = OKXAdapter(settings.okx)

        elif exchange_id_upper == "BINANCE":
            from okx_trading.infrastructure.binance.adapter import BinanceAdapter

            adapter = BinanceAdapter(settings.binance)

        else:  # BYBIT (already validated)
            from okx_trading.infrastructure.bybit.adapter import BybitAdapter

            adapter = BybitAdapter(settings.bybit)

        logger.info(
            "exchange_adapter_created",
            exchange=adapter.exchange_id,
            mode=adapter.mode,
        )
        return adapter

    @staticmethod
    def get_configured_exchanges(settings: Settings) -> list[ExchangeId]:
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

    @staticmethod
    async def create_for_user(
        exchange_id: ExchangeId,
        user_id: str,
        environment: str,
        credential_service: CredentialService,
        settings: Settings,
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

        Returns:
            Configured ExchangeAdapter instance using user credentials

        Raises:
            CredentialNotFoundError: If user has no active credential
            CredentialEncryptionError: If decryption fails
            ValueError: If exchange_id or environment is invalid
        """
        exchange_id_upper = exchange_id.upper()

        if exchange_id_upper not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange: {exchange_id!r}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES)}"
            )

        if environment not in ("DEMO", "LIVE"):
            raise ValueError(f"Invalid environment: {environment!r}. Use DEMO or LIVE.")

        # Retrieve and decrypt user credential
        cred: DecryptedCredential = await credential_service.get_credential(
            user_id=user_id,
            exchange=exchange_id_upper,
            environment=environment,
        )

        # Build adapter with user credentials
        adapter = ExchangeAdapterFactory._build_adapter_from_credential(
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

    @staticmethod
    def _build_adapter_from_credential(
        exchange_id: ExchangeId,
        cred: DecryptedCredential,
        environment: str,
        settings: Settings,
    ) -> ExchangeAdapter:
        """
        Build an adapter instance from decrypted user credentials.

        Internal helper. Never logs credential values.

        Args:
            exchange_id: Normalized exchange ID (uppercase)
            cred: Decrypted credential container
            environment: "DEMO" or "LIVE"
            settings: Application settings for base URLs/timeouts

        Returns:
            Configured ExchangeAdapter instance
        """
        is_demo = environment == "DEMO"

        if exchange_id == "OKX":
            from okx_trading.config.settings import OKXSettings
            from okx_trading.infrastructure.okx.adapter import OKXAdapter

            okx_settings = OKXSettings(
                api_key=cred.api_key,  # type: ignore[arg-type]
                api_secret=cred.api_secret,  # type: ignore[arg-type]
                passphrase=cred.passphrase or "",  # type: ignore[arg-type]
                demo_mode=is_demo,
                base_url=settings.okx.base_url,
                ws_url=settings.okx.ws_url,
                timeout=settings.okx.timeout,
                max_retries=settings.okx.max_retries,
            )
            return OKXAdapter(okx_settings)

        if exchange_id == "BINANCE":
            from okx_trading.config.settings import BinanceSettings
            from okx_trading.infrastructure.binance.adapter import BinanceAdapter

            binance_settings = BinanceSettings(
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
            return BinanceAdapter(binance_settings)

        # BYBIT
        from okx_trading.config.settings import BybitSettings
        from okx_trading.infrastructure.bybit.adapter import BybitAdapter

        bybit_settings = BybitSettings(
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
        return BybitAdapter(bybit_settings)


# ---------------------------------------------------------------------------
# Backward-compatible function wrappers
# ---------------------------------------------------------------------------


def create_exchange_adapter(exchange_id: ExchangeId, settings: Settings) -> ExchangeAdapter:
    """
    Create an exchange adapter for the given exchange ID.

    Backward-compatible wrapper around ExchangeAdapterFactory.create().

    Args:
        exchange_id: Exchange to create adapter for ("OKX", "BINANCE", "BYBIT")
        settings: Application settings containing exchange credentials

    Returns:
        Configured ExchangeAdapter instance

    Raises:
        ExchangeNotConfiguredError: If the exchange credentials are missing
        ValueError: If the exchange_id is not supported
    """
    return ExchangeAdapterFactory.create(exchange_id, settings)


def get_configured_exchanges(settings: Settings) -> list[ExchangeId]:
    """
    Get list of exchanges that have credentials configured.

    Backward-compatible wrapper around ExchangeAdapterFactory.get_configured_exchanges().

    Args:
        settings: Application settings

    Returns:
        List of configured exchange IDs
    """
    return ExchangeAdapterFactory.get_configured_exchanges(settings)
