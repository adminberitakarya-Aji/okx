"""
Health check routes.

Public endpoints for monitoring system health.
"""

from fastapi import APIRouter

from okx_trading.api.schemas.common import HealthResponse, ReadinessResponse
from okx_trading.config.settings import get_settings

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

    Returns readiness status for orchestration systems.
    """
    # Basic readiness - in production, check all dependencies
    return ReadinessResponse(
        status="READY",
        checks={
            "api": True,
            "database": True,  # TODO: Implement actual check
            "okx_connection": False,  # TODO: Implement actual check
        },
    )
