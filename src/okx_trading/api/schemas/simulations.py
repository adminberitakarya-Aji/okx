"""
Simulations API schemas.

This module provides schemas for:
- Simulation run requests
- Simulation result responses
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

SimulationStatus = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"]


class SimulationRunRequest(BaseModel):
    """Request to run a grid simulation."""

    market_id: str = Field(..., description="Market to simulate (e.g., BTC-USDT)")
    blueprint_id: str | None = Field(default=None, description="Blueprint to use (optional)")
    interval: str = Field(default="1H", description="Candle interval")
    candle_limit: int = Field(default=168, ge=24, le=720, description="Number of candles")
    initial_capital: Decimal = Field(default=Decimal("1000"), gt=0)
    environment: Literal["DEMO", "LIVE"] = Field(default="DEMO")


class SimulationResultResponse(BaseModel):
    """Simulation result response."""

    simulation_id: str
    market_id: str
    status: SimulationStatus
    candles_processed: int = 0
    initial_capital: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    net_pnl_return_pct: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    completed_cycles: int = 0
    total_buy_count: int = 0
    total_sell_count: int = 0
    open_lots: int = 0
    total_fees_paid: Decimal = Decimal("0")
    max_drawdown_pct: Decimal = Decimal("0")
    simulation_status: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class SimulationListResponse(BaseModel):
    """List of simulation results."""

    simulations: list[SimulationResultResponse] = Field(default_factory=list)
    total: int = 0
