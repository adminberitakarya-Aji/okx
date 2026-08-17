"""
Markets API schemas.

This module provides schemas for:
- Market list responses
- Market detail responses
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MarketResponse(BaseModel):
    """Market detail response."""

    market_id: str
    base_currency: str | None = None
    quote_currency: str | None = None
    last_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    spread_pct: Decimal | None = None
    volume_24h: Decimal | None = None
    status: str = "UNKNOWN"
    updated_at: datetime | None = None


class MarketListResponse(BaseModel):
    """List of markets."""

    markets: list[MarketResponse] = Field(default_factory=list)
    total: int = 0
    updated_at: datetime | None = None
