"""
System routes.

Endpoints for system status and configuration.
"""

from typing import Literal

from fastapi import APIRouter, Request

from okx_trading.api.schemas.system import (
    ExchangeInfoResponse,
    ExchangesListResponse,
    SystemStatusResponse,
)
from okx_trading.application.services.exchange_factory import (
    SUPPORTED_EXCHANGES,
    ExchangeAdapterFactory,
)
from okx_trading.config.settings import get_settings

router = APIRouter()


def _build_exchange_infos() -> list[ExchangeInfoResponse]:
    """Build exchange info list from settings (no secrets exposed)."""
    settings = get_settings()
    infos: list[ExchangeInfoResponse] = []

    # OKX
    okx_mode: Literal["DEMO", "LIVE"] = "LIVE" if not settings.okx.demo_mode else "DEMO"
    infos.append(
        ExchangeInfoResponse(
            exchange="OKX",
            configured=settings.okx.is_configured,
            mode=okx_mode,
        )
    )

    # Binance
    binance_mode: Literal["DEMO", "LIVE"] = "LIVE" if not settings.binance.testnet_mode else "DEMO"
    infos.append(
        ExchangeInfoResponse(
            exchange="BINANCE",
            configured=settings.binance.is_configured,
            mode=binance_mode,
        )
    )

    # Bybit
    bybit_mode: Literal["DEMO", "LIVE"] = "LIVE" if not settings.bybit.testnet_mode else "DEMO"
    infos.append(
        ExchangeInfoResponse(
            exchange="BYBIT",
            configured=settings.bybit.is_configured,
            mode=bybit_mode,
        )
    )

    return infos


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(request: Request) -> SystemStatusResponse:
    """
    Get system status.

    Returns the current status of all system components,
    including multi-exchange configuration info.
    """
    settings = get_settings()
    environment: Literal["DEMO", "LIVE"] = "LIVE" if not settings.okx.demo_mode else "DEMO"

    return SystemStatusResponse(
        environment=environment,
        api_status="RUNNING",
        okx_connection="CONFIGURED" if settings.okx.is_configured else "NOT_CONFIGURED",
        exchanges=_build_exchange_infos(),
        market_data_status="UNKNOWN",
        private_ws_status="UNKNOWN",
        reconciliation_status="UNKNOWN",
        grid_runtime_status="UNKNOWN",
        research_status="UNKNOWN",
    )


@router.get("/exchanges", response_model=ExchangesListResponse)
async def get_exchanges(request: Request) -> ExchangesListResponse:
    """
    Get supported exchanges and their configuration status.

    Returns:
    - supported: All supported exchange IDs
    - configured: Exchange IDs that have credentials configured
    - exchanges: Detailed info per exchange (configured + mode)

    Security: No secrets are exposed. Only configuration status and mode.
    """
    settings = get_settings()
    configured = ExchangeAdapterFactory.get_configured_exchanges(settings)

    return ExchangesListResponse(
        supported=list(SUPPORTED_EXCHANGES),
        configured=configured,
        exchanges=_build_exchange_infos(),
    )
