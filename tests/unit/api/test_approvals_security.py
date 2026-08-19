"""
Unit tests for approvals actor fallback removal [I-C4].

These tests verify:
1. Approval actions require authenticated identity (401 without)
2. Actor is derived from authenticated identity, NOT request body
3. Actor spoofing attempts are blocked
4. Insufficient permission returns 403 with audit logging
5. Valid approval/rejection with proper identity works
"""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_grid.api.routes.dependencies import get_current_identity
from trading_grid.application.services.authorization import Identity, PermissionLevel, Role


def _make_test_identity(
    identity_id: str,
    permission_level: PermissionLevel = PermissionLevel.LIVE_OPERATOR,
) -> Identity:
    """Create a test identity with specified permission level.

    Note: permission_level is derived from role in the Identity class,
    so we map the desired permission level to the appropriate role.
    """
    # Map permission level to appropriate role
    if permission_level >= PermissionLevel.SYSTEM_ADMIN:
        role = Role.SYSTEM_ADMIN
    elif permission_level >= PermissionLevel.EMERGENCY_ADMIN:
        role = Role.EMERGENCY_ADMIN
    elif permission_level >= PermissionLevel.LIVE_OPERATOR:
        role = Role.LIVE_OPERATOR
    elif permission_level >= PermissionLevel.DEMO_OPERATOR:
        role = Role.DEMO_OPERATOR
    else:
        role = Role.VIEWER
    return Identity(
        identity_id=identity_id,
        identity_type="HUMAN",
        role=role,
        allowed_environments=("DEMO", "LIVE"),
    )


class TestApprovalAuthentication:
    """Tests for approval endpoint authentication requirements."""

    def _build_app_with_mock_container(
        self,
        identity: Identity | None,
        approval_exists: bool = True,
    ) -> FastAPI:
        """Build a test app with mocked container and optional identity."""
        from trading_grid.api.routes.approvals import router

        app = FastAPI()
        app.include_router(router, prefix="/approvals")

        # Mock the container
        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-001"
        mock_approval.status = "APPROVED"
        mock_approval.operation_type = "LIVE_TRADING"
        mock_container.approval_service.approve.return_value = mock_approval
        mock_container.approval_service.reject.return_value = mock_approval

        # Patch get_default_container
        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            # Override get_current_identity to return test identity
            if identity is not None:
                app.dependency_overrides[get_current_identity] = lambda: identity

        return app

    def test_approve_without_identity_returns_401(self) -> None:
        """Approval request without identity must return 401."""
        from trading_grid.api.routes.approvals import router

        app = FastAPI()
        app.include_router(router, prefix="/approvals")

        mock_container = MagicMock()

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "fake-admin", "reason": "test"},
            )

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]

    def test_reject_without_identity_returns_401(self) -> None:
        """Rejection request without identity must return 401."""
        from trading_grid.api.routes.approvals import router

        app = FastAPI()
        app.include_router(router, prefix="/approvals")

        mock_container = MagicMock()

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/reject",
                json={"actor": "fake-admin", "reason": "test"},
            )

        assert response.status_code == 401
        assert "Authentication required" in response.json()["detail"]


class TestActorSpoofingPrevention:
    """Tests for actor spoofing prevention [I-C4]."""

    def test_actor_from_request_body_is_ignored(self) -> None:
        """Actor in request body must be ignored; authenticated identity used instead."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("real-user-123")

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-001"
        mock_approval.status = "APPROVED"
        mock_approval.operation_type = "LIVE_TRADING"
        mock_container.approval_service.approve.return_value = mock_approval

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={
                    "actor": "spoofed-admin",  # Attempted spoofing
                    "reason": "test",
                },
            )

        assert response.status_code == 200
        # The decided_by must be the authenticated identity, NOT the spoofed actor
        assert response.json()["decided_by"] == "real-user-123"
        assert response.json()["decided_by"] != "spoofed-admin"

        # Verify the service was called with the real identity
        mock_container.approval_service.approve.assert_called_once_with(
            "APR-001", approved_by="real-user-123"
        )

    def test_reject_actor_from_request_body_is_ignored(self) -> None:
        """Actor in reject request body must be ignored."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("real-user-456")

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-002"
        mock_approval.status = "REJECTED"
        mock_container.approval_service.reject.return_value = mock_approval

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-002/reject",
                json={
                    "actor": "spoofed-admin",  # Attempted spoofing
                    "reason": "test rejection",
                },
            )

        assert response.status_code == 200
        assert response.json()["decided_by"] == "real-user-456"
        mock_container.approval_service.reject.assert_called_once_with(
            "APR-002", rejected_by="real-user-456", reason="test rejection"
        )


class TestPermissionLevelEnforcement:
    """Tests for permission level enforcement."""

    def test_approve_with_insufficient_permission_returns_403(self) -> None:
        """User with insufficient permission cannot approve."""
        from trading_grid.api.routes.approvals import router

        # DEMO_OPERATOR has lower permission than LIVE_OPERATOR
        identity = _make_test_identity("demo-user", PermissionLevel.DEMO_OPERATOR)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "demo-user", "reason": "test"},
            )

        assert response.status_code == 403
        assert "LIVE_OPERATOR" in response.json()["detail"]

    def test_reject_with_insufficient_permission_returns_403(self) -> None:
        """User with insufficient permission cannot reject."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("demo-user", PermissionLevel.DEMO_OPERATOR)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/reject",
                json={"actor": "demo-user", "reason": "test"},
            )

        assert response.status_code == 403
        assert "LIVE_OPERATOR" in response.json()["detail"]

    def test_approve_with_live_operator_permission_succeeds(self) -> None:
        """User with LIVE_OPERATOR permission can approve."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("live-operator", PermissionLevel.LIVE_OPERATOR)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-001"
        mock_approval.status = "APPROVED"
        mock_approval.operation_type = "LIVE_TRADING"
        mock_container.approval_service.approve.return_value = mock_approval

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "live-operator", "reason": "approved"},
            )

        assert response.status_code == 200
        assert response.json()["status"] == "APPROVED"

    def test_approve_with_system_admin_permission_succeeds(self) -> None:
        """User with SYSTEM_ADMIN permission can approve."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("admin-user", PermissionLevel.SYSTEM_ADMIN)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-001"
        mock_approval.status = "APPROVED"
        mock_approval.operation_type = "LIVE_TRADING"
        mock_container.approval_service.approve.return_value = mock_approval

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.approvals.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "admin-user", "reason": "approved"},
            )

        assert response.status_code == 200
        assert response.json()["decided_by"] == "admin-user"


class TestApprovalAuditLogging:
    """Tests for audit logging on approval actions."""

    def test_insufficient_permission_logs_warning(self) -> None:
        """Insufficient permission attempt logs warning for audit."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("demo-user", PermissionLevel.DEMO_OPERATOR)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()

        client = TestClient(app)

        with (
            patch(
                "trading_grid.api.routes.approvals.get_default_container",
                return_value=mock_container,
            ),
            patch("trading_grid.api.routes.approvals.logger") as mock_logger,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "demo-user", "reason": "test"},
            )

        assert response.status_code == 403
        # Verify warning was logged
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "approval_insufficient_permission"
        assert call_args[1]["approval_id"] == "APR-001"
        assert call_args[1]["identity_id"] == "demo-user"

    def test_successful_approval_logs_info(self) -> None:
        """Successful approval logs info for audit."""
        from trading_grid.api.routes.approvals import router

        identity = _make_test_identity("live-operator", PermissionLevel.LIVE_OPERATOR)

        app = FastAPI()
        app.include_router(router, prefix="/approvals")
        app.dependency_overrides[get_current_identity] = lambda: identity

        mock_container = MagicMock()
        mock_approval = MagicMock()
        mock_approval.approval_id = "APR-001"
        mock_approval.status = "APPROVED"
        mock_approval.operation_type = "LIVE_TRADING"
        mock_container.approval_service.approve.return_value = mock_approval

        client = TestClient(app)

        with (
            patch(
                "trading_grid.api.routes.approvals.get_default_container",
                return_value=mock_container,
            ),
            patch("trading_grid.api.routes.approvals.logger") as mock_logger,
        ):
            response = client.post(
                "/approvals/APR-001/approve",
                json={"actor": "live-operator", "reason": "approved"},
            )

        assert response.status_code == 200
        # Verify info was logged
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "approval_approved"
        assert call_args[1]["approval_id"] == "APR-001"
        assert call_args[1]["approved_by"] == "live-operator"
