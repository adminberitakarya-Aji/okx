"""Tests for approval service."""

from datetime import UTC, datetime, timedelta

import pytest

from okx_trading.application.services.approval import (
    ApprovalError,
    ApprovalRequest,
    ApprovalService,
)


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def _create_request(self, **kwargs) -> ApprovalRequest:
        defaults = {
            "approval_id": "APR-123",
            "operation_id": "op-123",
            "operation_type": "START_LIVE_GRID",
            "environment": "LIVE",
            "requested_by": "user",
            "description": "Start live grid",
        }
        defaults.update(kwargs)
        return ApprovalRequest(**defaults)

    def test_create_pending(self):
        """New approval should be pending."""
        request = self._create_request()
        assert request.is_pending
        assert not request.is_approved
        assert not request.is_decided

    def test_approve(self):
        """Approving should update status."""
        request = self._create_request()
        request.approve("admin")
        assert request.is_approved
        assert request.is_decided
        assert request.decided_by == "admin"
        assert request.decided_at is not None

    def test_approve_non_pending_raises(self):
        """Approving non-pending should raise."""
        request = self._create_request()
        request.approve("admin")
        with pytest.raises(ApprovalError, match="Cannot approve"):
            request.approve("admin2")

    def test_approve_expired_raises(self):
        """Approving expired request should raise."""
        request = self._create_request(expires_at=datetime.now(UTC) - timedelta(hours=1))
        with pytest.raises(ApprovalError, match="expired"):
            request.approve("admin")
        assert request.status == "EXPIRED"

    def test_reject(self):
        """Rejecting should update status."""
        request = self._create_request()
        request.reject("admin", reason="Too risky")
        assert request.status == "REJECTED"
        assert request.is_decided
        assert request.decided_by == "admin"
        assert request.reason == "Too risky"

    def test_reject_non_pending_raises(self):
        """Rejecting non-pending should raise."""
        request = self._create_request()
        request.approve("admin")
        with pytest.raises(ApprovalError, match="Cannot reject"):
            request.reject("admin2")

    def test_expire(self):
        """Expiring pending request should update status."""
        request = self._create_request()
        request.expire()
        assert request.status == "EXPIRED"
        assert request.is_decided

    def test_expire_non_pending_noop(self):
        """Expiring non-pending should be no-op."""
        request = self._create_request()
        request.approve("admin")
        request.expire()
        assert request.status == "APPROVED"

    def test_is_expired_no_expiry(self):
        """No expiry means not expired."""
        request = self._create_request(expires_at=None)
        assert not request.is_expired

    def test_is_expired_future(self):
        """Future expiry means not expired."""
        request = self._create_request(expires_at=datetime.now(UTC) + timedelta(hours=1))
        assert not request.is_expired

    def test_is_expired_past(self):
        """Past expiry means expired."""
        request = self._create_request(expires_at=datetime.now(UTC) - timedelta(hours=1))
        assert request.is_expired

    def test_matches_operation_exact(self):
        """Approval should match exact operation."""
        request = self._create_request(
            market_id="BTC-USDT",
            blueprint_id="bp-123",
        )
        assert request.matches_operation(
            operation_id="op-123",
            environment="LIVE",
            market_id="BTC-USDT",
            blueprint_id="bp-123",
        )

    def test_matches_operation_wrong_id(self):
        """Approval should not match different operation."""
        request = self._create_request()
        assert not request.matches_operation(
            operation_id="op-999",
            environment="LIVE",
        )

    def test_matches_operation_wrong_environment(self):
        """Approval should not match different environment."""
        request = self._create_request()
        assert not request.matches_operation(
            operation_id="op-123",
            environment="DEMO",
        )

    def test_matches_operation_wrong_market(self):
        """Approval should not match different market."""
        request = self._create_request(market_id="BTC-USDT")
        assert not request.matches_operation(
            operation_id="op-123",
            environment="LIVE",
            market_id="ETH-USDT",
        )

    def test_matches_operation_wrong_blueprint(self):
        """Approval should not match different blueprint."""
        request = self._create_request(blueprint_id="bp-123")
        assert not request.matches_operation(
            operation_id="op-123",
            environment="LIVE",
            blueprint_id="bp-999",
        )

    def test_matches_operation_no_market_constraint(self):
        """Approval without market matches any market."""
        request = self._create_request(market_id=None)
        assert request.matches_operation(
            operation_id="op-123",
            environment="LIVE",
            market_id="ANY-USDT",
        )


class TestApprovalService:
    """Tests for ApprovalService."""

    def test_create_approval(self):
        """Should create approval request."""
        service = ApprovalService()
        approval = service.create_approval(
            operation_id="op-123",
            operation_type="START_LIVE_GRID",
            environment="LIVE",
            requested_by="user",
            description="Start live grid",
            market_id="BTC-USDT",
            blueprint_id="bp-123",
        )
        assert approval.approval_id.startswith("APR-")
        assert approval.is_pending
        assert approval.expires_at is not None

    def test_get_approval(self):
        """Should retrieve approval by ID."""
        service = ApprovalService()
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        found = service.get_approval(created.approval_id)
        assert found is created

    def test_get_approval_not_found(self):
        """Should return None for unknown ID."""
        service = ApprovalService()
        assert service.get_approval("APR-UNKNOWN") is None

    def test_get_approval_expires_stale(self):
        """Getting stale approval should expire it."""
        service = ApprovalService(expiry_hours=0)
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        # Force expiry in the past
        created.expires_at = datetime.now(UTC) - timedelta(hours=1)
        found = service.get_approval(created.approval_id)
        assert found is not None
        assert found.status == "EXPIRED"

    def test_approve(self):
        """Service approve should update approval."""
        service = ApprovalService()
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        approved = service.approve(created.approval_id, "admin")
        assert approved.is_approved
        assert approved.decided_by == "admin"

    def test_approve_not_found(self):
        """Approving unknown ID should raise."""
        service = ApprovalService()
        with pytest.raises(ApprovalError, match="not found"):
            service.approve("APR-UNKNOWN", "admin")

    def test_reject(self):
        """Service reject should update approval."""
        service = ApprovalService()
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        rejected = service.reject(created.approval_id, "admin", reason="No")
        assert rejected.status == "REJECTED"
        assert rejected.reason == "No"

    def test_reject_not_found(self):
        """Rejecting unknown ID should raise."""
        service = ApprovalService()
        with pytest.raises(ApprovalError, match="not found"):
            service.reject("APR-UNKNOWN", "admin")

    def test_get_pending_approvals(self):
        """Should return only pending approvals."""
        service = ApprovalService()
        a1 = service.create_approval(
            operation_id="op-1",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test 1",
        )
        a2 = service.create_approval(
            operation_id="op-2",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test 2",
        )
        service.approve(a1.approval_id, "admin")

        pending = service.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].approval_id == a2.approval_id

    def test_get_pending_expires_stale(self):
        """Pending list should expire stale approvals."""
        service = ApprovalService(expiry_hours=0)
        created = service.create_approval(
            operation_id="op-1",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        created.expires_at = datetime.now(UTC) - timedelta(hours=1)

        pending = service.get_pending_approvals()
        assert len(pending) == 0
        assert created.status == "EXPIRED"

    def test_has_valid_approval(self):
        """Should find valid approval for operation."""
        service = ApprovalService()
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="LIVE",
            requested_by="user",
            description="Test",
            market_id="BTC-USDT",
        )
        service.approve(created.approval_id, "admin")

        assert service.has_valid_approval(
            operation_id="op-123",
            environment="LIVE",
            market_id="BTC-USDT",
        )

    def test_has_valid_approval_not_found(self):
        """Should return False when no valid approval."""
        service = ApprovalService()
        assert not service.has_valid_approval(
            operation_id="op-123",
            environment="LIVE",
        )

    def test_has_valid_approval_pending_not_valid(self):
        """Pending approval is not valid."""
        service = ApprovalService()
        service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="LIVE",
            requested_by="user",
            description="Test",
        )
        assert not service.has_valid_approval(
            operation_id="op-123",
            environment="LIVE",
        )

    def test_has_valid_approval_expired_not_valid(self):
        """Expired approval is not valid."""
        service = ApprovalService()
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="LIVE",
            requested_by="user",
            description="Test",
        )
        service.approve(created.approval_id, "admin")
        # Simulate expiry after approval - has_valid_approval checks is_approved
        # but _expire_stale_approvals only expires pending ones
        created.status = "EXPIRED"
        assert not service.has_valid_approval(
            operation_id="op-123",
            environment="LIVE",
        )

    def test_custom_expiry_hours(self):
        """Custom expiry hours should be used."""
        service = ApprovalService(expiry_hours=1)
        created = service.create_approval(
            operation_id="op-123",
            operation_type="TEST",
            environment="DEMO",
            requested_by="user",
            description="Test",
        )
        assert created.expires_at is not None
        delta = created.expires_at - created.requested_at
        assert timedelta(minutes=59) < delta < timedelta(minutes=61)


class TestApprovalError:
    """Tests for ApprovalError."""

    def test_approval_error(self):
        """ApprovalError should store message."""
        error = ApprovalError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
