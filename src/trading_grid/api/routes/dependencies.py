"""
API route dependencies — shared service container access.

This module provides:
- Global service container registry for API routes
- Getter functions for accessing services from routes
- Identity extraction dependency for authenticated endpoints

The service container is wired at application startup
(via lifespan or explicit initialization).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

if TYPE_CHECKING:
    from trading_grid.application.services.authorization import Identity
    from trading_grid.application.services.service_container import (
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


def get_current_identity(request: Request) -> Identity:
    """
    Get the authenticated identity from request state.

    The AuthMiddleware attaches the identity to request.state.identity.
    This dependency extracts it for use in route handlers.

    [I-C3] Security: This dependency MUST be used for endpoints that
    require ownership checks (e.g., start_grid). Never fall back to
    request body fields for identity — always use the authenticated
    identity from the middleware.

    Args:
        request: The FastAPI request object

    Returns:
        The authenticated Identity

    Raises:
        HTTPException: 401 if no identity is attached
    """
    identity = getattr(request.state, "identity", None)
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. No identity attached to request.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return identity
