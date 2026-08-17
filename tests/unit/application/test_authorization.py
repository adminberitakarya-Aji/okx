"""
Tests for AuthorizationService.

Tests cover:
- Role-based access control (RBAC)
- Permission levels
- Identity management
- Authorization decisions
- Environment guards
"""

import pytest

from trading_grid.application.services.authorization import (
    AuthorizationError,
    AuthorizationService,
    Identity,
    PermissionLevel,
    Role,
)


class TestIdentity:
    """Tests for Identity model."""

    def test_create_identity(self) -> None:
        """Test creating an identity."""
        identity = Identity(
            identity_id="user-123",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
        )
        assert identity.identity_id == "user-123"
        assert identity.role == Role.DEMO_OPERATOR
        assert identity.identity_type == "HUMAN"

    def test_identity_permission_level(self) -> None:
        """Test identity permission level matches role."""
        admin = Identity(
            identity_id="admin-1",
            identity_type="HUMAN",
            role=Role.SYSTEM_ADMIN,
        )
        viewer = Identity(
            identity_id="viewer-1",
            identity_type="HUMAN",
            role=Role.VIEWER,
        )

        assert admin.permission_level == PermissionLevel.SYSTEM_ADMIN
        assert viewer.permission_level == PermissionLevel.VIEWER

    def test_identity_environment_access(self) -> None:
        """Test identity environment access control."""
        demo_only = Identity(
            identity_id="demo-1",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
            allowed_environments=("DEMO",),
        )
        live_allowed = Identity(
            identity_id="live-1",
            identity_type="HUMAN",
            role=Role.LIVE_OPERATOR,
            allowed_environments=("DEMO", "LIVE"),
        )

        assert demo_only.can_access_environment("DEMO") is True
        assert demo_only.can_access_environment("LIVE") is False
        assert live_allowed.can_access_environment("DEMO") is True
        assert live_allowed.can_access_environment("LIVE") is True


class TestAuthorizationService:
    """Tests for AuthorizationService."""

    @pytest.fixture
    def service(self) -> AuthorizationService:
        """Create authorization service."""
        return AuthorizationService()

    @pytest.fixture
    def admin_identity(self) -> Identity:
        """Create admin identity."""
        return Identity(
            identity_id="admin-1",
            identity_type="HUMAN",
            role=Role.SYSTEM_ADMIN,
            allowed_environments=("DEMO", "LIVE"),
        )

    @pytest.fixture
    def operator_identity(self) -> Identity:
        """Create demo operator identity."""
        return Identity(
            identity_id="operator-1",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
            allowed_environments=("DEMO",),
        )

    @pytest.fixture
    def viewer_identity(self) -> Identity:
        """Create viewer identity."""
        return Identity(
            identity_id="viewer-1",
            identity_type="HUMAN",
            role=Role.VIEWER,
            allowed_environments=("DEMO",),
        )

    def test_admin_can_do_everything(
        self, service: AuthorizationService, admin_identity: Identity
    ) -> None:
        """Test admin has all permissions."""
        result = service.check_permission(
            identity=admin_identity,
            operation="GRID_START",
        )
        assert result.is_authorized is True

        result = service.check_permission(
            identity=admin_identity,
            operation="GRID_EMERGENCY_STOP",
        )
        assert result.is_authorized is True

    def test_viewer_cannot_trade(
        self, service: AuthorizationService, viewer_identity: Identity
    ) -> None:
        """Test viewer cannot execute grid operations."""
        result = service.check_permission(
            identity=viewer_identity,
            operation="GRID_START",
        )
        assert result.is_authorized is False

    def test_viewer_can_read(
        self, service: AuthorizationService, viewer_identity: Identity
    ) -> None:
        """Test viewer can read status."""
        result = service.check_permission(
            identity=viewer_identity,
            operation="READ_STATUS",
        )
        assert result.is_authorized is True

    def test_operator_can_start_demo_grid(
        self, service: AuthorizationService, operator_identity: Identity
    ) -> None:
        """Test demo operator can start grids in demo."""
        result = service.check_permission(
            identity=operator_identity,
            operation="GRID_START",
            environment="DEMO",
        )
        assert result.is_authorized is True

    def test_operator_cannot_access_live(
        self, service: AuthorizationService, operator_identity: Identity
    ) -> None:
        """Test demo operator cannot access live environment."""
        result = service.check_permission(
            identity=operator_identity,
            operation="GRID_START",
            environment="LIVE",
        )
        assert result.is_authorized is False

    def test_authorization_result_has_reason(
        self, service: AuthorizationService, viewer_identity: Identity
    ) -> None:
        """Test authorization result includes reason when denied."""
        result = service.check_permission(
            identity=viewer_identity,
            operation="GRID_START",
        )
        assert result.is_authorized is False
        assert result.reason is not None
        assert "permission" in result.reason.lower()

    def test_require_permission_raises_on_denial(
        self, service: AuthorizationService, viewer_identity: Identity
    ) -> None:
        """Test require_permission raises AuthorizationError on denial."""
        with pytest.raises(AuthorizationError):
            service.require_permission(
                identity=viewer_identity,
                operation="GRID_START",
            )

    def test_require_permission_returns_result_on_success(
        self, service: AuthorizationService, admin_identity: Identity
    ) -> None:
        """Test require_permission returns result on success."""
        result = service.require_permission(
            identity=admin_identity,
            operation="READ_STATUS",
        )
        assert result.is_authorized is True


class TestPermissionLevels:
    """Tests for permission level hierarchy."""

    def test_permission_level_ordering(self) -> None:
        """Test permission levels are ordered correctly."""
        assert PermissionLevel.VIEWER < PermissionLevel.RESEARCHER
        assert PermissionLevel.RESEARCHER < PermissionLevel.DEMO_OPERATOR
        assert PermissionLevel.DEMO_OPERATOR < PermissionLevel.LIVE_OPERATOR
        assert PermissionLevel.LIVE_OPERATOR < PermissionLevel.EMERGENCY_ADMIN
        assert PermissionLevel.EMERGENCY_ADMIN < PermissionLevel.SYSTEM_ADMIN

    def test_role_values_match_permission_levels(self) -> None:
        """Test role values match permission level values."""
        assert Role.VIEWER.value == PermissionLevel.VIEWER.value
        assert Role.RESEARCHER.value == PermissionLevel.RESEARCHER.value
        assert Role.DEMO_OPERATOR.value == PermissionLevel.DEMO_OPERATOR.value
        assert Role.LIVE_OPERATOR.value == PermissionLevel.LIVE_OPERATOR.value
        assert Role.EMERGENCY_ADMIN.value == PermissionLevel.EMERGENCY_ADMIN.value
        assert Role.SYSTEM_ADMIN.value == PermissionLevel.SYSTEM_ADMIN.value


class TestEnvironmentGuards:
    """Tests for environment isolation."""

    @pytest.fixture
    def service(self) -> AuthorizationService:
        """Create authorization service."""
        return AuthorizationService()

    def test_live_requires_live_operator(self, service: AuthorizationService) -> None:
        """Test live operations require LIVE_OPERATOR or higher."""
        demo_operator = Identity(
            identity_id="demo-op",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
            allowed_environments=("DEMO", "LIVE"),  # Even with LIVE access
        )

        result = service.check_permission(
            identity=demo_operator,
            operation="GRID_START",
            environment="LIVE",
        )
        # Should be denied because DEMO_OPERATOR < LIVE_OPERATOR
        assert result.is_authorized is False

    def test_requires_approval_for_live_operations(self, service: AuthorizationService) -> None:
        """Test live grid operations require approval."""
        assert service.requires_approval("GRID_START", "LIVE") is True
        assert service.requires_approval("GRID_RESUME", "LIVE") is True
        assert service.requires_approval("GRID_START", "DEMO") is False
        assert service.requires_approval("READ_STATUS", "LIVE") is False
