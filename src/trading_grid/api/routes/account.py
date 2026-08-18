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

    [I-L2] Fetches live balance data from the exchange adapter.
    Falls back to zero balances if the adapter call fails.
    """
    container = get_default_container()
    settings = container._settings

    environment = "DEMO" if settings.okx.demo_mode else "LIVE"

    total_equity = Decimal("0")
    available_balance = Decimal("0")
    frozen_balance = Decimal("0")

    # [I-L2] Fetch real balances from the exchange adapter
    try:
        balances = await container.adapter.get_balance()
        for ccy, amount in balances.items():
            total_equity += amount
            available_balance += amount
        # Note: frozen balance is not available from the simplified
        # get_balance() interface; it would require a full account query.
    except Exception as e:
        logger.warning("account_balance_fetch_failed", error=str(e))

    return AccountResponse(
        account_id=None,
        environment=environment,
        status="CONFIGURED" if settings.okx.is_configured else "NOT_CONFIGURED",
        total_equity=total_equity,
        available_balance=available_balance,
        frozen_balance=frozen_balance,
        unrealized_pnl=Decimal("0"),
        updated_at=datetime.now(UTC),
    )


@router.get("/balances", response_model=BalancesListResponse)
async def get_balances() -> BalancesListResponse:
    """
    Get account balances by currency.

    Returns available, frozen, and total balance per currency.

    [I-L2] Fetches live balance data from the exchange adapter.
    """
    container = get_default_container()
    settings = container._settings

    environment = "DEMO" if settings.okx.demo_mode else "LIVE"

    balance_list: list[BalanceResponse] = []

    # [I-L2] Fetch real balances from the exchange adapter
    try:
        balances = await container.adapter.get_balance()
        for ccy, amount in balances.items():
            balance_list.append(
                BalanceResponse(
                    currency=ccy,
                    available=amount,
                    frozen=Decimal("0"),
                    total=amount,
                )
            )
    except Exception as e:
        logger.warning("account_balances_fetch_failed", error=str(e))

    return BalancesListResponse(
        balances=balance_list,
        total=len(balance_list),
        environment=environment,
        updated_at=datetime.now(UTC),
    )
