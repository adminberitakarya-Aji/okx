"""
Account API routes.

Endpoints for account status and balances.

Authorization: LEVEL 0+ (Read-only)
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.account import AccountResponse, BalanceResponse, BalancesListResponse

logger = structlog.get_logger()

router = APIRouter()


@router.get("", response_model=AccountResponse)
async def get_account() -> AccountResponse:
    """
    Get account status.

    Returns account summary including equity and balances.
    """
    container = get_default_container()
    settings = container._settings

    environment = "DEMO" if settings.okx.demo_mode else "LIVE"

    return AccountResponse(
        account_id=None,
        environment=environment,
        status="CONFIGURED" if settings.okx.is_configured else "NOT_CONFIGURED",
        total_equity=Decimal("0"),
        available_balance=Decimal("0"),
        frozen_balance=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        updated_at=datetime.now(UTC),
    )


@router.get("/balances", response_model=BalancesListResponse)
async def get_balances() -> BalancesListResponse:
    """
    Get account balances by currency.

    Returns available, frozen, and total balance per currency.
    """
    container = get_default_container()
    settings = container._settings

    environment = "DEMO" if settings.okx.demo_mode else "LIVE"

    # In a full implementation, this would query the exchange adapter
    # for real balances. For now, return empty list.
    return BalancesListResponse(
        balances=[
            BalanceResponse(
                currency="USDT",
                available=Decimal("0"),
                frozen=Decimal("0"),
                total=Decimal("0"),
            )
        ],
        total=1,
        environment=environment,
        updated_at=datetime.now(UTC),
    )
