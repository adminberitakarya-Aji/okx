"""
[I-M8] Shared state and service container helpers for Telegram handlers.

This module holds the global state that was previously at the top of the
monolithic handlers.py:
- Global UserService instance
- Lazy-initialized CredentialService
- MultiExchangeContainer registry

All handler sub-modules import from here instead of holding their own state.
"""

from __future__ import annotations

import sys

import structlog
from aiogram.types import CallbackQuery, Message

from trading_grid.application.services.credential_service import (
    CredentialNotConfiguredError,
    CredentialService,
)
from trading_grid.application.services.service_container import (
    MultiExchangeContainer,
    ServiceContainer,
)
from trading_grid.application.services.user_service import UserService
from trading_grid.config.settings import get_settings

logger = structlog.get_logger()

# Global user service instance (database-backed)
_user_service = UserService()

# Credential service (lazy init — requires CREDENTIAL_ENCRYPTION_KEY)
_credential_service: CredentialService | None = None

# Multi-exchange container registry (wired at startup)
_multi_container: MultiExchangeContainer | None = None


def set_service_container(container: MultiExchangeContainer | ServiceContainer) -> None:
    """
    Set the service container instance (for initialization).

    Accepts either a MultiExchangeContainer (preferred) or a single
    ServiceContainer (backward compatibility — wrapped automatically).
    """
    global _multi_container
    if isinstance(container, MultiExchangeContainer):
        _multi_container = container
    else:
        # Backward compat: wrap a single ServiceContainer
        _multi_container = MultiExchangeContainer(container._settings)
        _multi_container._containers[container.exchange_id] = container


def get_service_container() -> ServiceContainer | None:
    """Get the default (OKX) service container instance."""
    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if handlers_mod is not None:
        handler_fn = getattr(handlers_mod, "get_service_container", None)
        if handler_fn is not None and handler_fn is not get_service_container:
            return handler_fn()  # type: ignore[no-any-return]
    if _multi_container is None:
        return None
    return _multi_container.default_container


def get_multi_container() -> MultiExchangeContainer | None:
    """Get the multi-exchange container registry."""
    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if handlers_mod is not None:
        handler_fn = getattr(handlers_mod, "get_multi_container", None)
        if handler_fn is not None and handler_fn is not get_multi_container:
            return handler_fn()  # type: ignore[no-any-return]
    return _multi_container


def get_container_for_exchange(exchange_id: str) -> ServiceContainer | None:
    """
    Get the ServiceContainer for a specific exchange.

    Args:
        exchange_id: Exchange ID ("OKX", "BINANCE", "BYBIT")

    Returns:
        ServiceContainer for the exchange, or None if not initialized
    """
    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if handlers_mod is not None:
        handler_fn = getattr(handlers_mod, "get_container_for_exchange", None)
        if handler_fn is not None and handler_fn is not get_container_for_exchange:
            return handler_fn(exchange_id)  # type: ignore[no-any-return]
    if _multi_container is None:
        return None
    try:
        return _multi_container.get_container(exchange_id)
    except ValueError:
        return None


def get_credential_service() -> CredentialService | None:
    """
    Get the credential service instance (lazy init).

    Returns None if CREDENTIAL_ENCRYPTION_KEY is not configured.
    """
    global _credential_service
    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if handlers_mod is not None:
        handler_fn = getattr(handlers_mod, "get_credential_service", None)
        if handler_fn is not None and handler_fn is not get_credential_service:
            return handler_fn()  # type: ignore[no-any-return]
    if _credential_service is None:
        try:
            _credential_service = CredentialService(get_settings())
        except CredentialNotConfiguredError:
            logger.warning("credential_service_not_configured")
            return None
    return _credential_service


def get_user_service() -> UserService:
    """
    Get the user service instance.

    Returns:
        UserService instance
    """
    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if handlers_mod is not None:
        handler_fn = getattr(handlers_mod, "get_user_service", None)
        if handler_fn is not None and handler_fn is not get_user_service:
            return handler_fn()  # type: ignore[no-any-return]
    return _user_service


def _get_editable_message(callback: CallbackQuery) -> Message | None:
    """
    Get an editable message from a callback query.

    Args:
        callback: The callback query

    Returns:
        Message if editable, None otherwise
    """
    msg = callback.message
    if msg is None:
        return None
    if not isinstance(msg, Message):
        return None
    return msg
