"""
Application services.

These services provide:
- AuthorizationService: Role-based access control (RBAC)
- ApprovalService: Approval workflow for dangerous operations
- AuditService: Immutable audit trail
- CredentialService: Encrypted user credential storage (Phase 5)
- GridEngine: Grid runtime state machine
- ExecutionEngine: Order management and execution
- RiskValidationService: Deterministic risk limit enforcement
- exchange_factory: Multi-exchange adapter factory (OKX, Binance, Bybit)
"""

from trading_grid.application.services.approval import (
    ApprovalError,
    ApprovalRequest,
    ApprovalService,
    ApprovalStatus,
)
from trading_grid.application.services.audit import (
    ActorType,
    AuditRecord,
    AuditResult,
    AuditService,
)
from trading_grid.application.services.authorization import (
    AuthorizationError,
    AuthorizationResult,
    AuthorizationService,
    Identity,
    OperationType,
    PermissionLevel,
    Role,
)
from trading_grid.application.services.credential_service import (
    CredentialEncryptionError,
    CredentialNotConfiguredError,
    CredentialNotFoundError,
    CredentialService,
    DecryptedCredential,
)
from trading_grid.application.services.exchange_factory import (
    SUPPORTED_EXCHANGES,
    ExchangeAdapterFactory,
    create_exchange_adapter,
    get_configured_exchanges,
)
from trading_grid.application.services.execution_engine import (
    ExecutionEngine,
    ExecutionResult,
)
from trading_grid.application.services.grid_engine import (
    GridEngine,
    GridEngineError,
    GridRuntime,
    GridRuntimeStatus,
)
from trading_grid.application.services.risk_validation import RiskValidationService
from trading_grid.application.services.tenant_limits import (
    MaxGridsExceededError,
    RateLimitExceededError,
    TenantLimitsService,
    UserEmergencyStoppedError,
    UserRiskLimits,
)
from trading_grid.application.services.user_service import UserService

__all__ = [
    "SUPPORTED_EXCHANGES",
    "ActorType",
    "ApprovalError",
    "ApprovalRequest",
    "ApprovalService",
    "ApprovalStatus",
    "AuditRecord",
    "AuditResult",
    "AuditService",
    "AuthorizationError",
    "AuthorizationResult",
    "AuthorizationService",
    "CredentialEncryptionError",
    "CredentialNotConfiguredError",
    "CredentialNotFoundError",
    "CredentialService",
    "DecryptedCredential",
    "ExchangeAdapterFactory",
    "ExecutionEngine",
    "ExecutionResult",
    "GridEngine",
    "GridEngineError",
    "GridRuntime",
    "GridRuntimeStatus",
    "Identity",
    "MaxGridsExceededError",
    "OperationType",
    "PermissionLevel",
    "RateLimitExceededError",
    "RiskValidationService",
    "Role",
    "TenantLimitsService",
    "UserEmergencyStoppedError",
    "UserRiskLimits",
    "UserService",
    "create_exchange_adapter",
    "get_configured_exchanges",
]
