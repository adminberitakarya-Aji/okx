"""
API route dependencies — shared service container access.

This module provides:
- Global service container registry for API routes
- Getter functions for accessing services from routes

The service container is wired at application startup
(via lifespan or explicit initialization).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from okx_trading.application.services.service_container import (
        MultiExchangeContainer,
        ServiceContainer,
    )

# Global multi-exchange container (wired at startup)
_multi_container: MultiExchangeContainer | None = None


def set_multi_container(container: MultiExchangeContainer) -> None:
    """Set the multi-exchange container (called at app startup)."""
    global _multi_container
    _multi_container = container


def get_multi_container() -> MultiExchangeContainer:
    """Get the multi-exchange container, or raise 503."""
    if _multi_container is None:
        raise HTTPException(
            status_code=503,
            detail="Service container not initialized",
        )
    return _multi_container


def get_container(exchange: str = "OKX") -> ServiceContainer:
    """Get the ServiceContainer for a specific exchange."""
    return get_multi_container().get_container(exchange)


def get_default_container() -> ServiceContainer:
    """Get the default (OKX) service container."""
    return get_multi_container().default_container
