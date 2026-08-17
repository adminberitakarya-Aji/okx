"""
Positions API schemas.

This module provides schemas for:
- Position list responses
- Position detail
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PositionResponse(BaseModel):
    """Position detail response."""

    market_id: str
    quantity: Decimal = Decimal("0")
    average_entry_price: Decimal | None = None
    current_price: Decimal | None = None
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    grid_id: str | None = None
    environment: str = "DEMO"
    updated_at: datetime | None = None


class PositionListResponse(BaseModel):
    """List of positions."""

    positions: list[PositionResponse] = Field(default_factory=list)
    total: int = 0
    environment: str = "DEMO"
    updated_at: datetime | None = None
