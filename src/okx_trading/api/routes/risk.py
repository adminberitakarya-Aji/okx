"""
Risk API routes.

Endpoints for risk status and validation.

Authorization: LEVEL 0+ (Read), LEVEL 1+ (Validate)
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter

from okx_trading.api.routes.dependencies import get_default_container
from okx_trading.api.schemas.risk import (
    RiskLimitsResponse,
    RiskStatusResponse,
    RiskValidateRequest,
    RiskValidateResponse,
)

logger = structlog.get_logger()

router = APIRouter()


@router.get("/status", response_model=RiskStatusResponse)
async def get_risk_status() -> RiskStatusResponse:
    """
    Get current risk status.

    Returns risk limits, portfolio exposure, and active grid count.
    """
    container = get_default_container()
    risk_validator = container.execution_engine.risk_validator

    limits = risk_validator.limits
    portfolio = risk_validator.portfolio

    active_grids = len(container.grid_engine.get_active_grids())
    open_orders = len(container.execution_engine.get_active_orders())

    limits_response = RiskLimitsResponse(
        max_capital_per_grid=limits.max_capital_per_grid,
        max_total_capital_deployed=limits.max_total_capital,
        max_capital_per_market=None,
        max_open_orders=None,
        max_drawdown_threshold_pct=limits.max_drawdown_pct,
        max_daily_loss_threshold=None,
        max_position_size=limits.max_position_pct,
        min_liquidity_requirement=None,
        max_spread_threshold_pct=limits.max_slippage_pct,
    )

    return RiskStatusResponse(
        environment="DEMO",
        limits=limits_response,
        current_exposure=portfolio.total_exposure,
        current_drawdown_pct=portfolio.drawdown_pct,
        daily_pnl=portfolio.total_pnl,
        open_orders_count=open_orders,
        active_grids_count=active_grids,
        risk_level=portfolio.risk_level,
        violations=[],
        updated_at=datetime.now(UTC),
    )


@router.post("/validate", response_model=RiskValidateResponse)
async def validate_risk(request: RiskValidateRequest) -> RiskValidateResponse:
    """
    Validate an order against risk limits without executing it.

    This is a dry-run risk check. The order is NOT submitted.

    Args:
        request: Order parameters to validate
    """
    container = get_default_container()
    risk_validator = container.execution_engine.risk_validator

    side = request.side.upper()
    if side not in ("BUY", "SELL"):
        return RiskValidateResponse(
            approved=False,
            violations=[f"Invalid side: {request.side}"],
            warnings=[],
            checked_at=datetime.now(UTC),
        )

    # Get current positions for no-shorting validation on SELL
    positions = {p.market_id: p for p in container.execution_engine.get_positions()}

    result = risk_validator.validate_order(
        market_id=request.market_id.upper(),
        side=side,  # type: ignore[arg-type]
        quantity=request.quantity,
        price=request.price,
        reference_price=request.price,
        positions=positions,
    )

    return RiskValidateResponse(
        approved=result.is_passed,
        violations=[v.message for v in result.violations],
        warnings=[w.message for w in result.warnings],
        checked_at=datetime.now(UTC),
    )
