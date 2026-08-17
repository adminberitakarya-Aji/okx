"""
Grid API schemas.

This module provides schemas for:
- Grid runtime status
- Grid control commands (start, pause, resume, stop, emergency-stop)
- Blueprint responses
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

GridRuntimeStatus = Literal[
    "CREATED",
    "RUNNING",
    "PAUSED",
    "STOPPING",
    "STOPPED",
    "ERROR",
    "EMERGENCY_STOPPED",
]


class SectionResponse(BaseModel):
    """Grid section response."""

    section_id: int
    upper_price: Decimal
    lower_price: Decimal
    grid_count: int
    grid_spacing_pct: Decimal
    capital_allocation_pct: Decimal
    gap_to_next_pct: Decimal | None = None
    status: str
    fill_ratio: Decimal = Decimal("0")


class BlueprintResponse(BaseModel):
    """Blueprint response."""

    blueprint_id: str
    market_id: str
    total_capital: Decimal
    section_count: int
    total_grid_count: int
    sections: list[SectionResponse] = Field(default_factory=list)
    status: str
    created_at: datetime
    updated_at: datetime
    validation_status: str | None = None


class GridRuntimeResponse(BaseModel):
    """Grid runtime status response."""

    grid_id: str
    market_id: str
    environment: Literal["DEMO", "LIVE"]
    status: GridRuntimeStatus
    blueprint_id: str
    capital: Decimal
    deployed_capital: Decimal = Decimal("0")
    capital_utilization: Decimal = Decimal("0")
    exposure: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    section_depth: int = 0
    active_sections: int = 0
    started_at: datetime | None = None
    updated_at: datetime | None = None


class GridStartRequest(BaseModel):
    """Request to start a grid."""

    blueprint_id: str = Field(..., description="Blueprint to execute")
    environment: Literal["DEMO", "LIVE"] = Field(default="DEMO")
    idempotency_key: str | None = Field(default=None, description="Idempotency key")


class GridControlResponse(BaseModel):
    """Response for grid control operations."""

    grid_id: str
    operation_id: str
    status: str
    previous_status: str | None = None
    new_status: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class GridListResponse(BaseModel):
    """List of active grids."""

    grids: list[GridRuntimeResponse] = Field(default_factory=list)
    total: int = 0
