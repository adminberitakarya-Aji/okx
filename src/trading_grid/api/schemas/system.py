"""
System API schemas.

This module provides schemas for:
- System status
- Risk state
- Approval requests
- Account/Order/Position responses
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class ExchangeInfoResponse(BaseModel):
    """Exchange configuration info (no secrets)."""

    exchange: Literal["OKX", "BINANCE", "BYBIT"]
    configured: bool = False
    mode: Literal["DEMO", "LIVE"] = "DEMO"


class ExchangesListResponse(BaseModel):
    """List of supported exchanges and their configuration status."""

    supported: list[Literal["OKX", "BINANCE", "BYBIT"]] = Field(default_factory=list)
    configured: list[Literal["OKX", "BINANCE", "BYBIT"]] = Field(default_factory=list)
    exchanges: list[ExchangeInfoResponse] = Field(default_factory=list)


class SystemStatusResponse(BaseModel):
    """System status response."""

    environment: Literal["DEMO", "LIVE"]
    api_status: str = "UNKNOWN"
    okx_connection: str = "UNKNOWN"
    exchanges: list[ExchangeInfoResponse] = Field(default_factory=list)
    market_data_status: str = "UNKNOWN"
    private_ws_status: str = "UNKNOWN"
    reconciliation_status: str = "UNKNOWN"
    grid_runtime_status: str = "UNKNOWN"
    research_status: str = "UNKNOWN"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RiskStateResponse(BaseModel):
    """Risk state response."""

    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    total_capital: Decimal = Decimal("0")
    deployed_capital: Decimal = Decimal("0")
    available_capital: Decimal = Decimal("0")
    total_exposure: Decimal = Decimal("0")
    exposure_pct: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")
    active_grids: int = 0
    reserve_pct: Decimal = Decimal("0")
    updated_at: datetime | None = None


class ApprovalResponse(BaseModel):
    """Approval request response."""

    approval_id: str
    operation_id: str
    operation_type: str
    environment: str
    requested_by: str
    description: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
    requested_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    reason: str | None = None


class ApprovalDecisionRequest(BaseModel):
    """Request to approve/reject an approval."""

    decision: Literal["APPROVE", "REJECT"]
    reason: str | None = None


class AccountResponse(BaseModel):
    """Account state response."""

    environment: Literal["DEMO", "LIVE"]
    balances: list["BalanceResponse"] = Field(default_factory=list)
    total_equity: Decimal = Decimal("0")
    updated_at: datetime | None = None


class BalanceResponse(BaseModel):
    """Asset balance response."""

    asset: str
    available: Decimal = Decimal("0")
    frozen: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


class OrderResponse(BaseModel):
    """Order response."""

    order_id: str
    exchange_order_id: str | None = None
    market_id: str
    side: Literal["BUY", "SELL"]
    order_type: str
    quantity: Decimal
    price: Decimal | None = None
    status: str
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    fee: Decimal = Decimal("0")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PositionResponse(BaseModel):
    """Position response."""

    position_id: str
    market_id: str
    quantity: Decimal = Decimal("0")
    average_entry_price: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    grid_level: int | None = None
    section_id: int | None = None
    updated_at: datetime | None = None


class PnlResponse(BaseModel):
    """P&L response."""

    period: str
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    net_pnl: Decimal = Decimal("0")
    updated_at: datetime | None = None
