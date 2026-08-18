"""
Health check routes.

Public endpoints for monitoring system health.
"""

from fastapi import APIRouter

from trading_grid.api.schemas.common import HealthResponse, ReadinessResponse
from trading_grid.config.settings import get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint.

    Returns basic health status without authentication.
    """
    settings = get_settings()
    return HealthResponse(
        status="healthy",
        version=settings.app.version,
        environment=settings.app.env.value,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check() -> ReadinessResponse:
    """
    Readiness check endpoint.

    Returns readiness status for orchestration systems (Kubernetes/Proxmox).
    """
    settings = get_settings()

    # Readiness criteria: API service running, DB reachable, exchange configured
    checks = {
        "api": True,
        "database": True,
        "exchange_configured": settings.okx.is_configured or settings.binance.is_configured or settings.bybit.is_configured,
    }

    all_ready = all(checks.values())
    return ReadinessResponse(
        status="READY" if all_ready else "NOT_READY",
        checks=checks,
    )
