"""
P&L API schemas.

This module provides schemas for:
- P&L summary responses
- P&L by grid/market breakdown
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PnlSummaryResponse(BaseModel):
    """P&L summary response."""

    environment: str = "DEMO"
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    completed_cycles: int = 0
    total_buy_count: int = 0
    total_sell_count: int = 0
    max_drawdown_pct: Decimal = Decimal("0")
    updated_at: datetime | None = None


class PnlByGridResponse(BaseModel):
    """P&L breakdown by grid."""

    grid_id: str
    market_id: str
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    completed_cycles: int = 0
    status: str | None = None


class PnlByMarketResponse(BaseModel):
    """P&L breakdown by market."""

    market_id: str
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    completed_cycles: int = 0


class PnlDetailResponse(BaseModel):
    """Detailed P&L response with breakdowns."""

    summary: PnlSummaryResponse
    by_grid: list[PnlByGridResponse] = Field(default_factory=list)
    by_market: list[PnlByMarketResponse] = Field(default_factory=list)
