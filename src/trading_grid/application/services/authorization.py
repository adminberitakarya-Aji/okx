"""
Authorization service implementing Role-Based Access Control (RBAC).

This module provides:
- Role definitions with permission levels
- Permission checking
- Environment guards (DEMO vs LIVE)
- Deny-by-default authorization

Security rules:
1. Authorization is deny-by-default
2. Live trading requires LEVEL 3+ and explicit approval
3. Emergency stop requires LEVEL 4
4. Environment isolation is absolute
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Literal

from trading_grid.domain.shared.types import ExecutionMode, Timestamp


class PermissionLevel(IntEnum):
    """
    Authorization permission levels.

    Higher levels include all permissions of lower levels.
    """

    VIEWER = 0  # Read-only queries
    RESEARCHER = 1  # Research, simulation
    DEMO_OPERATOR = 2  # Demo grid control
    LIVE_OPERATOR = 3  # Live grid control
    EMERGENCY_ADMIN = 4  # Emergency stop, system control
    SYSTEM_ADMIN = 5  # User management, configuration


class Role(IntEnum):
    """
    User roles mapped to permission levels.
    """

    VIEWER = 0
    RESEARCHER = 1
    DEMO_OPERATOR = 2
    LIVE_OPERATOR = 3
    EMERGENCY_ADMIN = 4
    SYSTEM_ADMIN = 5


# Operation types that require authorization
OperationType = Literal[
    "READ_STATUS",
    "READ_RESEARCH",
    "READ_MARKET",
    "READ_BLUEPRINT",
    "READ_GRID",
    "READ_ACCOUNT",
    "READ_ORDERS",
    "READ_POSITIONS",
    "READ_PNL",
    "READ_RISK",
    "RUN_RESEARCH",
    "RUN_SIMULATION",
    "CREATE_BLUEPRINT",
    "APPROVE_BLUEPRINT",
    "GRID_START",
    "GRID_PAUSE",
    "GRID_RESUME",
    "GRID_STOP",
    "GRID_EMERGENCY_STOP",
    "ORDER_CANCEL",
    "LIVE_EXECUTE",
    "LIVE_APPROVE",
    "USER_MANAGEMENT",
    "SYSTEM_CONFIG",
]


# Minimum permission level required for each operation
OPERATION_PERMISSIONS: dict[OperationType, PermissionLevel] = {
    # Read operations - VIEWER (Level 0)
    "READ_STATUS": PermissionLevel.VIEWER,
    "READ_RESEARCH": PermissionLevel.VIEWER,
    "READ_MARKET": PermissionLevel.VIEWER,
    "READ_BLUEPRINT": PermissionLevel.VIEWER,
    "READ_GRID": PermissionLevel.VIEWER,
    "READ_ACCOUNT": PermissionLevel.VIEWER,
    "READ_ORDERS": PermissionLevel.VIEWER,
    "READ_POSITIONS": PermissionLevel.VIEWER,
    "READ_PNL": PermissionLevel.VIEWER,
    "READ_RISK": PermissionLevel.VIEWER,
    # Research operations - RESEARCHER (Level 1)
    "RUN_RESEARCH": PermissionLevel.RESEARCHER,
    "RUN_SIMULATION": PermissionLevel.RESEARCHER,
    "CREATE_BLUEPRINT": PermissionLevel.RESEARCHER,
    "APPROVE_BLUEPRINT": PermissionLevel.RESEARCHER,
    # Demo grid operations - DEMO_OPERATOR (Level 2)
    "GRID_START": PermissionLevel.DEMO_OPERATOR,
    "GRID_PAUSE": PermissionLevel.DEMO_OPERATOR,
    "GRID_RESUME": PermissionLevel.DEMO_OPERATOR,
    "GRID_STOP": PermissionLevel.DEMO_OPERATOR,
    "ORDER_CANCEL": PermissionLevel.DEMO_OPERATOR,
    # Live operations - LIVE_OPERATOR (Level 3)
    "LIVE_EXECUTE": PermissionLevel.LIVE_OPERATOR,
    "LIVE_APPROVE": PermissionLevel.LIVE_OPERATOR,
    # Emergency operations - EMERGENCY_ADMIN (Level 4)
    "GRID_EMERGENCY_STOP": PermissionLevel.EMERGENCY_ADMIN,
    # Admin operations - SYSTEM_ADMIN (Level 5)
    "USER_MANAGEMENT": PermissionLevel.SYSTEM_ADMIN,
    "SYSTEM_CONFIG": PermissionLevel.SYSTEM_ADMIN,
}


@dataclass(frozen=True)
class Identity:
    """
    Authenticated identity.

    Attributes:
        identity_id: Unique identifier (user_id, service_id, etc.)
        identity_type: Type of identity (HUMAN, SERVICE, SYSTEM)
        role: Assigned role
        environment: Allowed environment (DEMO, LIVE, or both)
        metadata: Additional identity metadata
    """

    identity_id: str
    identity_type: Literal["HUMAN", "SERVICE", "SYSTEM"]
    role: Role
    allowed_environments: tuple[ExecutionMode, ...] = ("DEMO",)
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def permission_level(self) -> PermissionLevel:
        """Get permission level for this identity's role."""
        return PermissionLevel(self.role.value)

    def can_access_environment(self, environment: ExecutionMode) -> bool:
        """Check if identity can access the given environment."""
        return environment in self.allowed_environments


@dataclass(frozen=True)
class AuthorizationResult:
    """
    Result of authorization check.

    Attributes:
        is_authorized: Whether the operation is authorized
        identity: The identity that was checked
        operation: The operation that was checked
        environment: The environment (if applicable)
        reason: Reason for denial (if denied)
        checked_at: Timestamp of check
    """

    is_authorized: bool
    identity: Identity
    operation: OperationType
    environment: ExecutionMode | None = None
    reason: str | None = None
    checked_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))


class AuthorizationService:
    """
    Service for enforcing role-based authorization.

    Implements deny-by-default authorization with:
    - Permission level checking
    - Environment guards
    - Operation-specific requirements
    """

    def __init__(self) -> None:
        """Initialize authorization service."""
        self._denial_callbacks: list[object] = []

    def check_permission(
        self,
        identity: Identity,
        operation: OperationType,
        environment: ExecutionMode | None = None,
    ) -> AuthorizationResult:
        """
        Check if identity is authorized to perform operation.

        Args:
            identity: The authenticated identity
            operation: The operation to perform
            environment: The target environment (for environment-guarded ops)

        Returns:
            AuthorizationResult with authorization decision
        """
        # Get required permission level for operation
        required_level = OPERATION_PERMISSIONS.get(operation)
        if required_level is None:
            # Unknown operation - deny by default
            return AuthorizationResult(
                is_authorized=False,
                identity=identity,
                operation=operation,
                environment=environment,
                reason=f"Unknown operation: {operation}",
            )

        # Check permission level
        if identity.permission_level < required_level:
            return AuthorizationResult(
                is_authorized=False,
                identity=identity,
                operation=operation,
                environment=environment,
                reason=(
                    f"Insufficient permission level. "
                    f"Required: {required_level.name}, "
                    f"Has: {identity.permission_level.name}"
                ),
            )

        # Check environment access if specified
        if environment is not None:
            if not identity.can_access_environment(environment):
                return AuthorizationResult(
                    is_authorized=False,
                    identity=identity,
                    operation=operation,
                    environment=environment,
                    reason=f"Identity not authorized for environment: {environment}",
                )

            # Live operations require LIVE_OPERATOR level
            if environment == "LIVE" and identity.permission_level < PermissionLevel.LIVE_OPERATOR:
                return AuthorizationResult(
                    is_authorized=False,
                    identity=identity,
                    operation=operation,
                    environment=environment,
                    reason="Live operations require LIVE_OPERATOR permission or higher",
                )

        return AuthorizationResult(
            is_authorized=True,
            identity=identity,
            operation=operation,
            environment=environment,
        )

    def require_permission(
        self,
        identity: Identity,
        operation: OperationType,
        environment: ExecutionMode | None = None,
    ) -> AuthorizationResult:
        """
        Check permission and raise exception if denied.

        Args:
            identity: The authenticated identity
            operation: The operation to perform
            environment: The target environment

        Returns:
            AuthorizationResult if authorized

        Raises:
            AuthorizationError: If authorization is denied
        """
        result = self.check_permission(identity, operation, environment)
        if not result.is_authorized:
            raise AuthorizationError(result.reason or "Authorization denied")
        return result

    def is_live_operation(
        self, operation: OperationType, environment: ExecutionMode | None
    ) -> bool:
        """Check if operation is a live trading operation."""
        if environment != "LIVE":
            return False
        return operation in ("GRID_START", "GRID_RESUME", "LIVE_EXECUTE", "GRID_STOP")

    def requires_approval(
        self, operation: OperationType, environment: ExecutionMode | None
    ) -> bool:
        """Check if operation requires explicit approval."""
        # Live grid start and resume require approval
        if environment == "LIVE":
            return operation in ("GRID_START", "GRID_RESUME", "LIVE_EXECUTE")
        return False


class AuthorizationError(Exception):
    """Raised when authorization is denied."""

    def __init__(self, message: str) -> None:
        """Initialize with denial message."""
        super().__init__(message)
        self.message = message
