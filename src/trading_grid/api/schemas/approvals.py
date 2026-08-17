"""
Approvals API schemas.

This module provides schemas for:
- Approval request list/detail responses
- Approval/rejection actions
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED"]
ApprovalType = Literal["LIVE_TRADING", "GRID_START", "RISK_LIMIT_CHANGE", "EMERGENCY_RESUME"]


class ApprovalResponse(BaseModel):
    """Approval request detail response."""

    approval_id: str
    approval_type: ApprovalType
    status: ApprovalStatus
    requested_by: str
    approved_by: str | None = None
    blueprint_id: str | None = None
    market_id: str | None = None
    environment: str = "DEMO"
    capital_allocation: Decimal | None = None
    conditions: list[str] = Field(default_factory=list)
    reason: str | None = None
    requested_at: datetime | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None


class ApprovalListResponse(BaseModel):
    """List of approval requests."""

    approvals: list[ApprovalResponse] = Field(default_factory=list)
    total: int = 0
    pending_count: int = 0


class ApprovalActionRequest(BaseModel):
    """Request to approve or reject an approval."""

    actor: str = Field(..., description="Actor performing the action")
    reason: str | None = Field(default=None, description="Reason for the decision")


class ApprovalActionResponse(BaseModel):
    """Response for approval action."""

    approval_id: str
    action: Literal["APPROVE", "REJECT"]
    status: ApprovalStatus
    decided_by: str
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    reason: str | None = None
