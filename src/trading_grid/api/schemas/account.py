"""
Account API schemas.

This module provides schemas for:
- Account status
- Account balances
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class AccountResponse(BaseModel):
    """Account status response."""

    account_id: str | None = None
    environment: str = "DEMO"
    status: str = "UNKNOWN"
    total_equity: Decimal = Decimal("0")
    available_balance: Decimal = Decimal("0")
    frozen_balance: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    updated_at: datetime | None = None


class BalanceResponse(BaseModel):
    """Single currency balance."""

    currency: str
    available: Decimal = Decimal("0")
    frozen: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


class BalancesListResponse(BaseModel):
    """List of account balances."""

    balances: list[BalanceResponse] = Field(default_factory=list)
    total: int = 0
    environment: str = "DEMO"
    updated_at: datetime | None = None
