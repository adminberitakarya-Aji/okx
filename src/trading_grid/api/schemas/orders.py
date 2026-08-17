"""
Orders API schemas.

This module provides schemas for:
- Order list and detail responses
- Order cancellation
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

OrderSide = Literal["BUY", "SELL"]
OrderType = Literal["MARKET", "LIMIT"]
OrderStatus = Literal[
    "PENDING",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
    "FAILED",
]


class OrderResponse(BaseModel):
    """Order detail response."""

    order_id: str
    client_order_id: str | None = None
    market_id: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    price: Decimal | None = None
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    grid_id: str | None = None
    grid_level: int | None = None
    environment: str = "DEMO"
    created_at: datetime | None = None
    updated_at: datetime | None = None


class OrderListResponse(BaseModel):
    """List of orders."""

    orders: list[OrderResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


class OrderCancelResponse(BaseModel):
    """Response for order cancellation."""

    order_id: str
    status: str
    cancelled: bool = False
    reason: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
