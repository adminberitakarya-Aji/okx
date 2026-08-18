"""
Approval service for dangerous operations.

This module provides:
- Approval request creation and management
- Approval state machine (PENDING → APPROVED/REJECTED/EXPIRED)
- Approval binding to exact operation/environment/blueprint
- Approval expiry

Security rules:
1. Live trading requires explicit approval
2. Approval is bound to the exact operation
3. A generic approval cannot be reused for another operation
4. Approvals expire after a configurable duration
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from trading_grid.domain.shared.types import ExecutionMode, Timestamp

ApprovalStatus = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]


@dataclass
class ApprovalRequest:
    """
    Request for human approval of a dangerous operation.

    Approval is bound to the exact:
    - operation
    - blueprint (if applicable)
    - market
    - environment

    Attributes:
        approval_id: Unique approval identifier
        operation_id: The operation requiring approval
        operation_type: Type of operation
        environment: Target environment (DEMO/LIVE)
        market_id: Market identifier (if applicable)
        blueprint_id: Blueprint identifier (if applicable)
        requested_by: Identity that requested the operation
        description: Human-readable description
        status: Current approval status
        requested_at: Request timestamp
        decided_by: Identity that approved/rejected
        decided_at: Decision timestamp
        expires_at: Expiry timestamp
        reason: Reason for rejection (if rejected)
        metadata: Additional metadata
    """

    approval_id: str
    operation_id: str
    operation_type: str
    environment: ExecutionMode
    requested_by: str
    description: str
    market_id: str | None = None
    blueprint_id: str | None = None
    status: ApprovalStatus = "PENDING"
    requested_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    decided_by: str | None = None
    decided_at: Timestamp | None = None
    expires_at: Timestamp | None = None
    reason: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_pending(self) -> bool:
        """Check if approval is pending."""
        return self.status == "PENDING"

    @property
    def is_approved(self) -> bool:
        """Check if approval is approved."""
        return self.status == "APPROVED"

    @property
    def is_decided(self) -> bool:
        """Check if approval has been decided."""
        return self.status in ("APPROVED", "REJECTED", "EXPIRED")

    @property
    def is_expired(self) -> bool:
        """Check if approval has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def approve(self, approved_by: str) -> None:
        """
        Approve the request.

        Args:
            approved_by: Identity approving the request

        Raises:
            ApprovalError: If approval is not pending
        """
        if not self.is_pending:
            raise ApprovalError(f"Cannot approve: status is {self.status}")
        if self.is_expired:
            self.status = "EXPIRED"
            raise ApprovalError("Cannot approve: approval request has expired")

        self.status = "APPROVED"
        self.decided_by = approved_by
        self.decided_at = datetime.now(UTC)

    def reject(self, rejected_by: str, reason: str | None = None) -> None:
        """
        Reject the request.

        Args:
            rejected_by: Identity rejecting the request
            reason: Reason for rejection

        Raises:
            ApprovalError: If approval is not pending
        """
        if not self.is_pending:
            raise ApprovalError(f"Cannot reject: status is {self.status}")

        self.status = "REJECTED"
        self.decided_by = rejected_by
        self.decided_at = datetime.now(UTC)
        self.reason = reason

    def expire(self) -> None:
        """Mark the approval as expired."""
        if self.status in ("PENDING", "APPROVED"):
            self.status = "EXPIRED"
            if self.decided_at is None:
                self.decided_at = datetime.now(UTC)

    def matches_operation(
        self,
        operation_id: str,
        environment: ExecutionMode,
        market_id: str | None = None,
        blueprint_id: str | None = None,
    ) -> bool:
        """
        Check if this approval matches the given operation parameters.

        Approval is bound to the exact operation/environment/blueprint.

        Args:
            operation_id: The operation ID to match
            environment: The environment to match
            market_id: The market to match (if applicable)
            blueprint_id: The blueprint to match (if applicable)

        Returns:
            True if all parameters match
        """
        if self.operation_id != operation_id:
            return False
        if self.environment != environment:
            return False
        if self.market_id is not None and self.market_id != market_id:
            return False
        return not (self.blueprint_id is not None and self.blueprint_id != blueprint_id)


class ApprovalService:
    """
    Service for managing approval workflows.

    Handles:
    - Creating approval requests
    - Approving/rejecting requests
    - Checking approval status
    - Expiring stale approvals
    """

    DEFAULT_EXPIRY_HOURS = 24

    def __init__(self, expiry_hours: int = DEFAULT_EXPIRY_HOURS) -> None:
        """
        Initialize approval service.

        Args:
            expiry_hours: Hours before an approval request expires
        """
        self._approvals: dict[str, ApprovalRequest] = {}
        self._expiry_hours = expiry_hours

    def create_approval(
        self,
        operation_id: str,
        operation_type: str,
        environment: ExecutionMode,
        requested_by: str,
        description: str,
        market_id: str | None = None,
        blueprint_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> ApprovalRequest:
        """
        Create a new approval request.

        Args:
            operation_id: The operation requiring approval
            operation_type: Type of operation
            environment: Target environment
            requested_by: Identity requesting the operation
            description: Human-readable description
            market_id: Market identifier (if applicable)
            blueprint_id: Blueprint identifier (if applicable)
            metadata: Additional metadata

        Returns:
            The created ApprovalRequest
        """
        approval_id = f"APR-{uuid4().hex[:12].upper()}"
        expires_at = datetime.now(UTC) + timedelta(hours=self._expiry_hours)

        approval = ApprovalRequest(
            approval_id=approval_id,
            operation_id=operation_id,
            operation_type=operation_type,
            environment=environment,
            requested_by=requested_by,
            description=description,
            market_id=market_id,
            blueprint_id=blueprint_id,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._approvals[approval_id] = approval
        return approval

    def get_approval(self, approval_id: str) -> ApprovalRequest | None:
        """Get an approval request by ID."""
        approval = self._approvals.get(approval_id)
        if approval is not None and approval.is_expired and approval.is_pending:
            approval.expire()
        return approval

    def approve(self, approval_id: str, approved_by: str) -> ApprovalRequest:
        """
        Approve a pending request.

        Args:
            approval_id: The approval ID
            approved_by: Identity approving

        Returns:
            The updated ApprovalRequest

        Raises:
            ApprovalError: If approval not found or not pending
        """
        approval = self.get_approval(approval_id)
        if approval is None:
            raise ApprovalError(f"Approval not found: {approval_id}")
        approval.approve(approved_by)
        return approval

    def reject(
        self, approval_id: str, rejected_by: str, reason: str | None = None
    ) -> ApprovalRequest:
        """
        Reject a pending request.

        Args:
            approval_id: The approval ID
            rejected_by: Identity rejecting
            reason: Reason for rejection

        Returns:
            The updated ApprovalRequest

        Raises:
            ApprovalError: If approval not found or not pending
        """
        approval = self.get_approval(approval_id)
        if approval is None:
            raise ApprovalError(f"Approval not found: {approval_id}")
        approval.reject(rejected_by, reason)
        return approval

    def get_pending_approvals(self) -> list[ApprovalRequest]:
        """Get all pending approval requests."""
        self._expire_stale_approvals()
        return [a for a in self._approvals.values() if a.is_pending]

    def get_all_approvals(self) -> list[ApprovalRequest]:
        """Get all approval requests (any status)."""
        self._expire_stale_approvals()
        return list(self._approvals.values())

    def has_valid_approval(
        self,
        operation_id: str,
        environment: ExecutionMode,
        market_id: str | None = None,
        blueprint_id: str | None = None,
    ) -> bool:
        """
        Check if there is a valid (approved, non-expired) approval for the operation.

        Args:
            operation_id: The operation ID
            environment: The environment
            market_id: The market (if applicable)
            blueprint_id: The blueprint (if applicable)

        Returns:
            True if valid approval exists
        """
        self._expire_stale_approvals()
        for approval in self._approvals.values():
            if (
                approval.is_approved
                and not approval.is_expired
                and approval.matches_operation(
                    operation_id, environment, market_id, blueprint_id
                )
            ):
                return True
        return False

    def _expire_stale_approvals(self) -> None:
        """Expire all stale approvals (pending or approved whose validity has elapsed)."""
        for approval in self._approvals.values():
            if approval.is_expired and approval.status in ("PENDING", "APPROVED"):
                approval.expire()


class ApprovalError(Exception):
    """Raised when approval operations fail."""

    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        super().__init__(message)
        self.message = message
