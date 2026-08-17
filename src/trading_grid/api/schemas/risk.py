"""
Risk API schemas.

This module provides schemas for:
- Risk status responses
- Risk validation requests/responses
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class RiskLimitsResponse(BaseModel):
    """Current risk limits configuration."""

    max_capital_per_grid: Decimal | None = None
    max_total_capital_deployed: Decimal | None = None
    max_capital_per_market: Decimal | None = None
    max_open_orders: int | None = None
    max_drawdown_threshold_pct: Decimal | None = None
    max_daily_loss_threshold: Decimal | None = None
    max_position_size: Decimal | None = None
    min_liquidity_requirement: Decimal | None = None
    max_spread_threshold_pct: Decimal | None = None


class RiskStatusResponse(BaseModel):
    """Risk status response."""

    environment: str = "DEMO"
    limits: RiskLimitsResponse = Field(default_factory=RiskLimitsResponse)
    current_exposure: Decimal = Decimal("0")
    current_drawdown_pct: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    open_orders_count: int = 0
    active_grids_count: int = 0
    risk_level: str = "NORMAL"
    violations: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class RiskValidateRequest(BaseModel):
    """Request to validate an operation against risk limits."""

    market_id: str
    side: str = "BUY"
    quantity: Decimal
    price: Decimal | None = None
    grid_id: str | None = None
    user_id: str | None = None


class RiskValidateResponse(BaseModel):
    """Response for risk validation."""

    approved: bool = False
    violations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.utcnow)
