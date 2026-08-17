"""
Approvals API routes.

Endpoints for approval request management (list, detail, approve, reject).

Authorization: LEVEL 3+ (Approve/Reject)
"""

from datetime import UTC, datetime
from typing import cast

import structlog
from fastapi import APIRouter, HTTPException

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.approvals import (
    ApprovalActionRequest,
    ApprovalActionResponse,
    ApprovalListResponse,
    ApprovalResponse,
    ApprovalType,
)
from trading_grid.application.services.approval import ApprovalError, ApprovalRequest

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
        approval_type=approval_type,
        status=approval.status,
        requested_by=approval.requested_by,
        approved_by=approval.decided_by,
        blueprint_id=approval.blueprint_id,
        market_id=approval.market_id,
        environment=approval.environment,
        capital_allocation=None,
        conditions=[],
        reason=approval.reason,
        requested_at=approval.requested_at,
        decided_at=approval.decided_at,
        expires_at=approval.expires_at,
    )


@router.get("", response_model=ApprovalListResponse)
async def list_approvals() -> ApprovalListResponse:
    """
    List all approval requests.

    Returns approvals in any status (pending, approved, rejected, expired).
    """
    container = get_default_container()
    service = container.approval_service

    approvals = service.get_all_approvals()
    pending = [a for a in approvals if a.is_pending]

    responses = [_approval_to_response(a) for a in approvals]

    return ApprovalListResponse(
        approvals=responses,
        total=len(responses),
        pending_count=len(pending),
    )


@router.get("/pending", response_model=ApprovalListResponse)
async def list_pending_approvals() -> ApprovalListResponse:
    """
    List pending approval requests only.
    """
    container = get_default_container()
    service = container.approval_service

    approvals = service.get_pending_approvals()
    responses = [_approval_to_response(a) for a in approvals]

    return ApprovalListResponse(
        approvals=responses,
        total=len(responses),
        pending_count=len(responses),
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
    approval_id: str, request: ApprovalActionRequest
) -> ApprovalActionResponse:
    """
    Approve a pending approval request.

    Authorization: LEVEL 3+ (Live Trading Approval)
    """
    container = get_default_container()
    service = container.approval_service

    try:
        approval = service.approve(approval_id, approved_by=request.actor)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "approval_approved",
        approval_id=approval_id,
        approved_by=request.actor,
        operation_type=approval.operation_type,
    )

    return ApprovalActionResponse(
        approval_id=approval_id,
        action="APPROVE",
        status=approval.status,
        decided_by=request.actor,
        decided_at=datetime.now(UTC),
        reason=request.reason,
    )


@router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject_approval(
    approval_id: str, request: ApprovalActionRequest
) -> ApprovalActionResponse:
    """
    Reject a pending approval request.

    Authorization: LEVEL 3+ (Live Trading Approval)
    """
    container = get_default_container()
    service = container.approval_service

    try:
        approval = service.reject(approval_id, rejected_by=request.actor, reason=request.reason)
    except ApprovalError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    logger.info(
        "approval_rejected",
        approval_id=approval_id,
        rejected_by=request.actor,
        reason=request.reason,
    )

    return ApprovalActionResponse(
        approval_id=approval_id,
        action="REJECT",
        status=approval.status,
        decided_by=request.actor,
        decided_at=datetime.now(UTC),
        reason=request.reason,
    )
