"""
Domain error definitions for the OKX Trading system.

All domain-specific errors inherit from DomainError.
Infrastructure errors should be mapped to these domain errors.
"""

from decimal import Decimal


class DomainError(Exception):
    """Base class for all domain errors."""

    def __init__(self, message: str, code: str = "DOMAIN_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


# ============================================================================
# GRID ERRORS
# ============================================================================


class GridError(DomainError):
    """Base class for grid-related errors."""

    def __init__(self, message: str, code: str = "GRID_ERROR") -> None:
        super().__init__(message, code)


class InvalidGridSpacingError(GridError):
    """Raised when grid spacing is invalid or out of bounds."""

    def __init__(self, spacing: Decimal, min_spacing: Decimal, max_spacing: Decimal) -> None:
        self.spacing = spacing
        self.min_spacing = min_spacing
        self.max_spacing = max_spacing
        super().__init__(
            f"Grid spacing {spacing}% is out of bounds (min: {min_spacing}%, max: {max_spacing}%)",
            code="INVALID_GRID_SPACING",
        )


class NonUniformSpacingError(GridError):
    """Raised when grid spacing within a section is not uniform."""

    def __init__(self, section_id: int) -> None:
        self.section_id = section_id
        super().__init__(
            f"Grid spacing in section {section_id} is not uniform",
            code="NON_UNIFORM_SPACING",
        )


class InvalidSectionError(GridError):
    """Raised when a section configuration is invalid."""

    def __init__(self, message: str, section_id: int | None = None) -> None:
        self.section_id = section_id
        super().__init__(message, code="INVALID_SECTION")


class TooManySectionsError(GridError):
    """Raised when the number of sections exceeds the maximum."""

    def __init__(self, count: int, max_count: int) -> None:
        self.count = count
        self.max_count = max_count
        super().__init__(
            f"Number of sections ({count}) exceeds maximum ({max_count})",
            code="TOO_MANY_SECTIONS",
        )


class BlueprintValidationError(GridError):
    """Raised when a blueprint fails validation."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        self.errors = errors or []
        super().__init__(message, code="BLUEPRINT_VALIDATION_ERROR")


# ============================================================================
# MARKET ERRORS
# ============================================================================


class MarketError(DomainError):
    """Base class for market-related errors."""

    def __init__(self, message: str, code: str = "MARKET_ERROR") -> None:
        super().__init__(message, code)


class MarketNotFoundError(MarketError):
    """Raised when a market is not found."""

    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        super().__init__(f"Market not found: {market_id}", code="MARKET_NOT_FOUND")


class MarketSuspendedError(MarketError):
    """Raised when a market is suspended or not tradable."""

    def __init__(self, market_id: str) -> None:
        self.market_id = market_id
        super().__init__(f"Market is suspended: {market_id}", code="MARKET_SUSPENDED")


class InsufficientLiquidityError(MarketError):
    """Raised when market liquidity is insufficient."""

    def __init__(self, market_id: str, required: Decimal, available: Decimal) -> None:
        self.market_id = market_id
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient liquidity for {market_id}: required {required}, available {available}",
            code="INSUFFICIENT_LIQUIDITY",
        )


# ============================================================================
# EXECUTION ERRORS
# ============================================================================


class ExecutionError(DomainError):
    """Base class for execution-related errors."""

    def __init__(self, message: str, code: str = "EXECUTION_ERROR") -> None:
        super().__init__(message, code)


class OrderRejectedError(ExecutionError):
    """Raised when an order is rejected by the exchange."""

    def __init__(self, order_id: str, reason: str) -> None:
        self.order_id = order_id
        self.reason = reason
        super().__init__(
            f"Order {order_id} rejected: {reason}",
            code="ORDER_REJECTED",
        )


class OrderNotFoundError(ExecutionError):
    """Raised when an order is not found."""

    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(f"Order not found: {order_id}", code="ORDER_NOT_FOUND")


class AmbiguousOrderStateError(ExecutionError):
    """Raised when order state is ambiguous and requires reconciliation."""

    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        super().__init__(
            f"Order {order_id} has ambiguous state. Reconcile before retry.",
            code="AMBIGUOUS_ORDER_STATE",
        )


class InsufficientBalanceError(ExecutionError):
    """Raised when there is insufficient balance for an order."""

    def __init__(self, currency: str, required: Decimal, available: Decimal) -> None:
        self.currency = currency
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient {currency} balance: required {required}, available {available}",
            code="INSUFFICIENT_BALANCE",
        )


class ExecutionTimeoutError(ExecutionError):
    """Raised when execution times out."""

    def __init__(self, order_id: str, timeout_seconds: float) -> None:
        self.order_id = order_id
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Order {order_id} execution timed out after {timeout_seconds}s",
            code="EXECUTION_TIMEOUT",
        )


# ============================================================================
# RISK ERRORS
# ============================================================================


class RiskError(DomainError):
    """Base class for risk-related errors."""

    def __init__(self, message: str, code: str = "RISK_ERROR") -> None:
        super().__init__(message, code)


class RiskLimitExceededError(RiskError):
    """Raised when a risk limit is exceeded."""

    def __init__(self, limit_name: str, value: Decimal, limit: Decimal) -> None:
        self.limit_name = limit_name
        self.value = value
        self.limit = limit
        super().__init__(
            f"Risk limit exceeded: {limit_name} = {value} (limit: {limit})",
            code="RISK_LIMIT_EXCEEDED",
        )


class RiskValidationError(RiskError):
    """Raised when risk validation fails."""

    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        self.violations = violations or []
        super().__init__(message, code="RISK_VALIDATION_ERROR")


class MaxDrawdownExceededError(RiskError):
    """Raised when maximum drawdown is exceeded."""

    def __init__(self, drawdown_pct: Decimal, max_drawdown_pct: Decimal) -> None:
        self.drawdown_pct = drawdown_pct
        self.max_drawdown_pct = max_drawdown_pct
        super().__init__(
            f"Max drawdown exceeded: {drawdown_pct}% (limit: {max_drawdown_pct}%)",
            code="MAX_DRAWDOWN_EXCEEDED",
        )


class ApprovalRequiredError(RiskError):
    """Raised when human approval is required before proceeding."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__(
            f"Human approval required for: {action}",
            code="APPROVAL_REQUIRED",
        )


# ============================================================================
# DATA ERRORS
# ============================================================================


class DataError(DomainError):
    """Base class for data-related errors."""

    def __init__(self, message: str, code: str = "DATA_ERROR") -> None:
        super().__init__(message, code)


class DataValidationError(DataError):
    """Raised when data fails validation."""

    def __init__(self, message: str, field: str | None = None) -> None:
        self.field = field
        super().__init__(message, code="DATA_VALIDATION_ERROR")


class MissingDataError(DataError):
    """Raised when required data is missing."""

    def __init__(self, data_type: str, identifier: str) -> None:
        self.data_type = data_type
        self.identifier = identifier
        super().__init__(
            f"Missing {data_type} data for: {identifier}",
            code="MISSING_DATA",
        )


class FutureDataLeakageError(DataError):
    """Raised when future data is detected in features (causal integrity violation)."""

    def __init__(self, feature_id: str, timestamp: str) -> None:
        self.feature_id = feature_id
        self.timestamp = timestamp
        super().__init__(
            f"Future data detected in feature {feature_id} at {timestamp}",
            code="FUTURE_DATA_LEAKAGE",
        )


# ============================================================================
# CONFIGURATION ERRORS
# ============================================================================


class ConfigurationError(DomainError):
    """Base class for configuration errors."""

    def __init__(self, message: str, code: str = "CONFIGURATION_ERROR") -> None:
        super().__init__(message, code)


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid."""

    def __init__(self, key: str, message: str) -> None:
        self.key = key
        super().__init__(f"Invalid configuration '{key}': {message}", code="INVALID_CONFIGURATION")


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration is missing."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Missing required configuration: {key}", code="MISSING_CONFIGURATION")
