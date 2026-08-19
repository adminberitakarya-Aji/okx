"""
Approvals API routes.

Endpoints for approval request management (list, detail, approve, reject).

Authorization: LEVEL 3+ (Approve/Reject)

[I-C4] Security: All approval actions require authenticated identity.
The actor is derived from the authenticated identity, NOT from request body.
"""

from datetime import UTC, datetime
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException

from trading_grid.api.routes.dependencies import get_current_identity, get_default_container
from trading_grid.api.schemas.approvals import (
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalListResponse,
    ApprovalResponse,
    ApprovalType,
)
from trading_grid.application.services.approval import ApprovalError, ApprovalRequest
from trading_grid.application.services.authorization import Identity, PermissionLevel

logger = structlog.get_logger()

router = APIRouter()

_KNOWN_APPROVAL_TYPES = {"LIVE_TRADING", "GRID_START", "RISK_LIMIT_CHANGE", "EMERGENCY_RESUME"}


def _approval_to_response(approval: ApprovalRequest) -> ApprovalResponse:
    """Convert a domain ApprovalRequest to ApprovalResponse."""
    approval_type = cast(
        "ApprovalType",
        approval.operation_type
        if approval.operation_type in _KNOWN_APPROVAL_TYPES
        else "GRID_START",
    )

    return ApprovalResponse(
        approval_id=approval.approval_id,
        operation_type=approval_type,
        status=approval.status,
        requested_by=approval.requested_by,
        requested_at=approval.requested_at,
        description=approval.description,
        market_id=approval.market_id,
        blueprint_id=approval.blueprint_id,
        environment=approval.environment,
        decided_by=approval.decided_by,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
        reason=approval.reason,
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    status: str | None = None,
    environment: str | None = None,
) -> ApprovalListResponse:
    """
    List approval requests with optional status and environment filters.

    Authorization: VIEWER+
    """
    container = get_default_container()
    service = container.approval_service

    if status == "PENDING":
        approvals = service.get_pending_approvals()
    else:
        approvals = list(service._approvals.values())

    if environment:
        approvals = [a for a in approvals if a.environment == environment]

    items = [_approval_to_response(a) for a in approvals]
    pending_count = sum(1 for a in approvals if a.is_pending)

    return ApprovalListResponse(
        approvals=items,
        total=len(items),
        pending_count=pending_count,
    )


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(approval_id: str) -> ApprovalResponse:
    """
    Get a specific approval request by ID.

    Args:
        approval_id: Approval ID (e.g., APR-xxx)
    """
    container = get_default_container()
    service = container.approval_service

    approval = service.get_approval(approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail=f"Approval not found: {approval_id}")

    return _approval_to_response(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve_approval(
    approval_id: str,
    request: ApprovalActionRequest,
    identity: Identity = Depends(get_current_identity),
) -> ApprovalActionResponse:
    """
    Approve a pending approval request.

    Authorization: LEVEL 3+ (Live Trading Approval)

    [I-C4] Security: Actor is derived from authenticated identity only.
    The request.actor field is ignored to prevent spoofing.
    """
    if identity.permission_level < PermissionLevel.LIVE_OPERATOR:
        logger.warning(
            "approval_insufficient_permission",
            approval_id=approval_id,
            identity_id=identity.identity_id,
            permission_level=identity.permission_level,
            required_level=PermissionLevel.LIVE_OPERATOR,
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: LIVE_OPERATOR (Level 3+) role required to approve requests",
        )

    # [I-C4] Actor is ALWAYS from authenticated identity, never from request body
    actor = identity.identity_id

    container = get_default_container()
    service = container.approval_service

    try:
        approval = service.approve(approval_id, approved_by=actor)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "approval_approved",
        approval_id=approval_id,
        approved_by=actor,
        operation_type=approval.operation_type,
    )

    return ApprovalActionResponse(
        approval_id=approval_id,
        action="APPROVE",
        status=approval.status,
        decided_by=actor,
        decided_at=datetime.now(UTC),
        reason=request.reason,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject_approval(
    approval_id: str,
    request: ApprovalActionRequest,
    identity: Identity = Depends(get_current_identity),
) -> ApprovalActionResponse:
    """
    Reject a pending approval request.

    Authorization: LEVEL 3+ (Live Trading Approval)

    [I-C4] Security: Actor is derived from authenticated identity only.
    The request.actor field is ignored to prevent spoofing.
    """
    if identity.permission_level < PermissionLevel.LIVE_OPERATOR:
        logger.warning(
            "approval_insufficient_permission",
            approval_id=approval_id,
            identity_id=identity.identity_id,
            permission_level=identity.permission_level,
            required_level=PermissionLevel.LIVE_OPERATOR,
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: LIVE_OPERATOR (Level 3+) role required to reject requests",
        )

    # [I-C4] Actor is ALWAYS from authenticated identity, never from request body
    actor = identity.identity_id

    container = get_default_container()
    service = container.approval_service

    try:
        approval = service.reject(approval_id, rejected_by=actor, reason=request.reason)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "approval_rejected",
        approval_id=approval_id,
        rejected_by=actor,
        reason=request.reason,
    )

    return ApprovalActionResponse(
        approval_id=approval_id,
        action="REJECT",
        status=approval.status,
        decided_by=actor,
        decided_at=datetime.now(UTC),
        reason=request.reason,
    )
