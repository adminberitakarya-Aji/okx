"""
Exchange Adapter Registry — Composition root wiring for concrete adapters.

This module is the ONLY place where concrete adapter classes are imported
and registered. It lives in infrastructure/ because infrastructure is allowed
to depend on concrete implementations.

The application layer receives this registry via dependency injection and
never imports concrete adapters directly.

Dependency rule:
    application/ MUST NOT import from infrastructure/
    infrastructure/ CAN import concrete adapters
    This registry is injected into application services at composition root.

Usage (at composition root - api/app.py or service_container.py):
    from trading_grid.infrastructure.exchange.registry import build_adapter_registry

    registry = build_adapter_registry()
    factory = ExchangeAdapterFactory(registry)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from trading_grid.domain.exchange.interface import ExchangeAdapter

logger = structlog.get_logger()

# Type alias for adapter constructor: takes exchange settings, returns adapter
AdapterConstructor = Callable[[Any], "ExchangeAdapter"]


def build_adapter_registry() -> dict[str, AdapterConstructor]:
    """
    Build the adapter registry mapping exchange IDs to concrete adapter classes.

    This is the single wiring point between exchange IDs and their concrete
    implementations. Called once at application startup (composition root).

    Returns:
        Dictionary mapping exchange IDs to adapter classes:
        {"OKX": OKXAdapter, "BINANCE": BinanceAdapter, "BYBIT": BybitAdapter}
    """
    from trading_grid.infrastructure.binance.adapter import BinanceAdapter
    from trading_grid.infrastructure.bybit.adapter import BybitAdapter
    from trading_grid.infrastructure.okx.adapter import OKXAdapter

    registry: dict[str, AdapterConstructor] = {
        "OKX": OKXAdapter,
        "BINANCE": BinanceAdapter,
        "BYBIT": BybitAdapter,
    }

    logger.info(
        "exchange_adapter_registry_built",
        exchanges=list(registry.keys()),
    )
    return registry


def get_adapter_class(exchange_id: str) -> AdapterConstructor | None:
    """
    Get the adapter class for a specific exchange.

    Convenience function for cases where only one adapter class is needed.

    Args:
        exchange_id: Exchange ID ("OKX", "BINANCE", "BYBIT")

    Returns:
        Adapter class or None if exchange is not supported
    """
    registry = build_adapter_registry()
    return registry.get(exchange_id.upper())
