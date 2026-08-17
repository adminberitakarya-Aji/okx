"""Tests for domain error definitions."""

from decimal import Decimal

from trading_grid.domain.shared.errors import (
    AmbiguousOrderStateError,
    ApprovalRequiredError,
    BlueprintValidationError,
    ConfigurationError,
    DataError,
    DataValidationError,
    DomainError,
    ExecutionError,
    ExecutionTimeoutError,
    FutureDataLeakageError,
    GridError,
    InsufficientBalanceError,
    InsufficientLiquidityError,
    InvalidConfigurationError,
    InvalidGridSpacingError,
    InvalidSectionError,
    MarketError,
    MarketNotFoundError,
    MarketSuspendedError,
    MaxDrawdownExceededError,
    MissingConfigurationError,
    MissingDataError,
    NonUniformSpacingError,
    OrderNotFoundError,
    OrderRejectedError,
    RiskError,
    RiskLimitExceededError,
    RiskValidationError,
    TooManySectionsError,
)


class TestDomainError:
    """Tests for base DomainError."""

    def test_domain_error(self):
        """DomainError should store message and code."""
        error = DomainError("Test error", code="TEST_CODE")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.code == "TEST_CODE"

    def test_domain_error_default_code(self):
        """DomainError should have default code."""
        error = DomainError("Test error")
        assert error.code == "DOMAIN_ERROR"


class TestGridErrors:
    """Tests for grid-related errors."""

    def test_grid_error(self):
        """GridError should inherit from DomainError."""
        error = GridError("Grid error")
        assert isinstance(error, DomainError)
        assert error.code == "GRID_ERROR"

    def test_invalid_grid_spacing_error(self):
        """InvalidGridSpacingError should store spacing details."""
        error = InvalidGridSpacingError(
            spacing=Decimal("5"),
            min_spacing=Decimal("0.1"),
            max_spacing=Decimal("2"),
        )
        assert error.spacing == Decimal("5")
        assert error.min_spacing == Decimal("0.1")
        assert error.max_spacing == Decimal("2")
        assert error.code == "INVALID_GRID_SPACING"
        assert "5" in str(error)

    def test_non_uniform_spacing_error(self):
        """NonUniformSpacingError should store section_id."""
        error = NonUniformSpacingError(section_id=2)
        assert error.section_id == 2
        assert error.code == "NON_UNIFORM_SPACING"
        assert "2" in str(error)

    def test_invalid_section_error(self):
        """InvalidSectionError should store section_id."""
        error = InvalidSectionError("Invalid section", section_id=1)
        assert error.section_id == 1
        assert error.code == "INVALID_SECTION"

    def test_invalid_section_error_no_id(self):
        """InvalidSectionError without section_id."""
        error = InvalidSectionError("Invalid section")
        assert error.section_id is None

    def test_too_many_sections_error(self):
        """TooManySectionsError should store counts."""
        error = TooManySectionsError(count=6, max_count=5)
        assert error.count == 6
        assert error.max_count == 5
        assert error.code == "TOO_MANY_SECTIONS"

    def test_blueprint_validation_error(self):
        """BlueprintValidationError should store errors list."""
        error = BlueprintValidationError("Validation failed", errors=["err1", "err2"])
        assert error.errors == ["err1", "err2"]
        assert error.code == "BLUEPRINT_VALIDATION_ERROR"

    def test_blueprint_validation_error_no_errors(self):
        """BlueprintValidationError without errors list."""
        error = BlueprintValidationError("Validation failed")
        assert error.errors == []


class TestMarketErrors:
    """Tests for market-related errors."""

    def test_market_error(self):
        """MarketError should inherit from DomainError."""
        error = MarketError("Market error")
        assert isinstance(error, DomainError)
        assert error.code == "MARKET_ERROR"

    def test_market_not_found_error(self):
        """MarketNotFoundError should store market_id."""
        error = MarketNotFoundError("BTC-USDT")
        assert error.market_id == "BTC-USDT"
        assert error.code == "MARKET_NOT_FOUND"
        assert "BTC-USDT" in str(error)

    def test_market_suspended_error(self):
        """MarketSuspendedError should store market_id."""
        error = MarketSuspendedError("ETH-USDT")
        assert error.market_id == "ETH-USDT"
        assert error.code == "MARKET_SUSPENDED"

    def test_insufficient_liquidity_error(self):
        """InsufficientLiquidityError should store details."""
        error = InsufficientLiquidityError(
            market_id="BTC-USDT",
            required=Decimal("1000"),
            available=Decimal("500"),
        )
        assert error.market_id == "BTC-USDT"
        assert error.required == Decimal("1000")
        assert error.available == Decimal("500")
        assert error.code == "INSUFFICIENT_LIQUIDITY"


class TestExecutionErrors:
    """Tests for execution-related errors."""

    def test_execution_error(self):
        """ExecutionError should inherit from DomainError."""
        error = ExecutionError("Execution error")
        assert isinstance(error, DomainError)
        assert error.code == "EXECUTION_ERROR"

    def test_order_rejected_error(self):
        """OrderRejectedError should store order details."""
        error = OrderRejectedError("ORD-001", "Insufficient balance")
        assert error.order_id == "ORD-001"
        assert error.reason == "Insufficient balance"
        assert error.code == "ORDER_REJECTED"

    def test_order_not_found_error(self):
        """OrderNotFoundError should store order_id."""
        error = OrderNotFoundError("ORD-002")
        assert error.order_id == "ORD-002"
        assert error.code == "ORDER_NOT_FOUND"

    def test_ambiguous_order_state_error(self):
        """AmbiguousOrderStateError should store order_id."""
        error = AmbiguousOrderStateError("ORD-003")
        assert error.order_id == "ORD-003"
        assert error.code == "AMBIGUOUS_ORDER_STATE"
        assert "Reconcile" in str(error)

    def test_insufficient_balance_error(self):
        """InsufficientBalanceError should store balance details."""
        error = InsufficientBalanceError(
            currency="USDT",
            required=Decimal("100"),
            available=Decimal("50"),
        )
        assert error.currency == "USDT"
        assert error.required == Decimal("100")
        assert error.available == Decimal("50")
        assert error.code == "INSUFFICIENT_BALANCE"

    def test_execution_timeout_error(self):
        """ExecutionTimeoutError should store timeout details."""
        error = ExecutionTimeoutError("ORD-004", 30.0)
        assert error.order_id == "ORD-004"
        assert error.timeout_seconds == 30.0
        assert error.code == "EXECUTION_TIMEOUT"


class TestRiskErrors:
    """Tests for risk-related errors."""

    def test_risk_error(self):
        """RiskError should inherit from DomainError."""
        error = RiskError("Risk error")
        assert isinstance(error, DomainError)
        assert error.code == "RISK_ERROR"

    def test_risk_limit_exceeded_error(self):
        """RiskLimitExceededError should store limit details."""
        error = RiskLimitExceededError(
            limit_name="max_capital",
            value=Decimal("150"),
            limit=Decimal("100"),
        )
        assert error.limit_name == "max_capital"
        assert error.value == Decimal("150")
        assert error.limit == Decimal("100")
        assert error.code == "RISK_LIMIT_EXCEEDED"

    def test_risk_validation_error(self):
        """RiskValidationError should store violations."""
        error = RiskValidationError("Validation failed", violations=["v1", "v2"])
        assert error.violations == ["v1", "v2"]
        assert error.code == "RISK_VALIDATION_ERROR"

    def test_risk_validation_error_no_violations(self):
        """RiskValidationError without violations."""
        error = RiskValidationError("Validation failed")
        assert error.violations == []

    def test_max_drawdown_exceeded_error(self):
        """MaxDrawdownExceededError should store drawdown details."""
        error = MaxDrawdownExceededError(
            drawdown_pct=Decimal("15"),
            max_drawdown_pct=Decimal("10"),
        )
        assert error.drawdown_pct == Decimal("15")
        assert error.max_drawdown_pct == Decimal("10")
        assert error.code == "MAX_DRAWDOWN_EXCEEDED"

    def test_approval_required_error(self):
        """ApprovalRequiredError should store action."""
        error = ApprovalRequiredError("START_LIVE_TRADING")
        assert error.action == "START_LIVE_TRADING"
        assert error.code == "APPROVAL_REQUIRED"


class TestDataErrors:
    """Tests for data-related errors."""

    def test_data_error(self):
        """DataError should inherit from DomainError."""
        error = DataError("Data error")
        assert isinstance(error, DomainError)
        assert error.code == "DATA_ERROR"

    def test_data_validation_error(self):
        """DataValidationError should store field."""
        error = DataValidationError("Invalid value", field="price")
        assert error.field == "price"
        assert error.code == "DATA_VALIDATION_ERROR"

    def test_data_validation_error_no_field(self):
        """DataValidationError without field."""
        error = DataValidationError("Invalid value")
        assert error.field is None

    def test_missing_data_error(self):
        """MissingDataError should store data details."""
        error = MissingDataError("candle", "BTC-USDT")
        assert error.data_type == "candle"
        assert error.identifier == "BTC-USDT"
        assert error.code == "MISSING_DATA"

    def test_future_data_leakage_error(self):
        """FutureDataLeakageError should store feature details."""
        error = FutureDataLeakageError("F-MKT-001", "2024-01-01T00:00:00Z")
        assert error.feature_id == "F-MKT-001"
        assert error.timestamp == "2024-01-01T00:00:00Z"
        assert error.code == "FUTURE_DATA_LEAKAGE"


class TestConfigurationErrors:
    """Tests for configuration errors."""

    def test_configuration_error(self):
        """ConfigurationError should inherit from DomainError."""
        error = ConfigurationError("Config error")
        assert isinstance(error, DomainError)
        assert error.code == "CONFIGURATION_ERROR"

    def test_invalid_configuration_error(self):
        """InvalidConfigurationError should store key."""
        error = InvalidConfigurationError("api_key", "Must not be empty")
        assert error.key == "api_key"
        assert error.code == "INVALID_CONFIGURATION"
        assert "api_key" in str(error)

    def test_missing_configuration_error(self):
        """MissingConfigurationError should store key."""
        error = MissingConfigurationError("database_url")
        assert error.key == "database_url"
        assert error.code == "MISSING_CONFIGURATION"
