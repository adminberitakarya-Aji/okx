"""
Risk domain models.

This module defines risk-related models:
- RiskLimits: Configurable risk limits
- RiskValidationResult: Validation result
- PortfolioRisk: Portfolio-level risk metrics

Key domain rules:
1. All orders go through risk validation
2. Live trading requires explicit human approval
3. Maximum drawdown triggers emergency stop
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from trading_grid.domain.shared.types import (
    MarketId,
    RiskLevel,
    Timestamp,
    ValidationStatus,
)


@dataclass(frozen=True)
class RiskLimits:
    """
    Configurable risk limits.

    These limits are enforced deterministically.
    AI recommendations must pass these limits.

    Attributes:
        max_capital_per_grid: Maximum capital per grid (USDT)
        max_total_capital: Maximum total capital across all grids (USDT)
        max_drawdown_pct: Maximum drawdown before emergency stop (%)
        max_concurrent_grids: Maximum number of concurrent grids
        max_position_pct: Maximum position size as % of capital
        min_profitable_exit_pct: Minimum profitable exit threshold (%)
        max_slippage_pct: Maximum acceptable slippage (%)
        max_execution_cost_pct: Maximum acceptable execution cost (%)
        min_reserve_pct: Minimum reserve capital (%)
        max_exposure_pct: Maximum exposure as % of capital
    """

    max_capital_per_grid: Decimal = Decimal("100")
    max_total_capital: Decimal = Decimal("500")
    max_drawdown_pct: Decimal = Decimal("10")
    max_concurrent_grids: int = 5
    max_position_pct: Decimal = Decimal("20")
    min_profitable_exit_pct: Decimal = Decimal("0.5")
    max_slippage_pct: Decimal = Decimal("1")
    max_execution_cost_pct: Decimal = Decimal("2")
    min_reserve_pct: Decimal = Decimal("10")
    max_exposure_pct: Decimal = Decimal("80")

    def __post_init__(self) -> None:
        """Validate risk limits constraints."""
        if self.max_capital_per_grid <= 0:
            raise ValueError("max_capital_per_grid must be positive")
        if self.max_total_capital <= 0:
            raise ValueError("max_total_capital must be positive")
        if not (Decimal("0") < self.max_drawdown_pct <= Decimal("100")):
            raise ValueError("max_drawdown_pct must be between 0 and 100")
        if self.max_concurrent_grids < 1:
            raise ValueError("max_concurrent_grids must be >= 1")


@dataclass(frozen=True)
class RiskViolation:
    """
    A single risk violation.

    Attributes:
        rule: The rule that was violated
        message: Human-readable description
        value: The actual value
        limit: The limit that was exceeded
        severity: Violation severity
    """

    rule: str
    message: str
    value: Decimal | int | None = None
    limit: Decimal | int | None = None
    severity: RiskLevel = "MEDIUM"


@dataclass
class RiskValidationResult:
    """
    Result of risk validation.

    Attributes:
        status: Overall validation status (PASS/FAIL/WARNING)
        violations: List of violations
        warnings: List of warnings
        validated_at: Validation timestamp
        metadata: Additional metadata
    """

    status: ValidationStatus = "PASS"
    violations: list[RiskViolation] = field(default_factory=list)
    warnings: list[RiskViolation] = field(default_factory=list)
    validated_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_passed(self) -> bool:
        """Check if validation passed."""
        return self.status == "PASS"

    @property
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return len(self.warnings) > 0

    def add_violation(self, violation: RiskViolation) -> None:
        """Add a violation and update status."""
        self.violations.append(violation)
        self.status = "FAIL"

    def add_warning(self, warning: RiskViolation) -> None:
        """Add a warning."""
        self.warnings.append(warning)
        if self.status == "PASS":
            self.status = "WARNING"


@dataclass
class PortfolioRisk:
    """
    Portfolio-level risk metrics.

    Attributes:
        total_capital: Total capital allocated
        deployed_capital: Capital currently deployed
        available_capital: Capital available for new positions
        total_exposure: Total exposure (position value)
        exposure_pct: Exposure as % of capital
        unrealized_pnl: Total unrealized P&L
        realized_pnl: Total realized P&L
        drawdown_pct: Current drawdown percentage
        peak_equity: Peak equity value
        current_equity: Current equity value
        active_grids: Number of active grids
        risk_level: Overall risk level
        updated_at: Last update timestamp
    """

    total_capital: Decimal = Decimal("0")
    deployed_capital: Decimal = Decimal("0")
    available_capital: Decimal = Decimal("0")
    total_exposure: Decimal = Decimal("0")
    exposure_pct: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")
    current_equity: Decimal = Decimal("0")
    active_grids: int = 0
    risk_level: RiskLevel = "LOW"
    updated_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))

    @property
    def reserve_pct(self) -> Decimal:
        """Calculate reserve capital percentage."""
        if self.total_capital == 0:
            return Decimal("0")
        return (self.available_capital / self.total_capital) * 100

    @property
    def total_pnl(self) -> Decimal:
        """Calculate total P&L."""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def total_pnl_pct(self) -> Decimal:
        """Calculate total P&L percentage."""
        if self.total_capital == 0:
            return Decimal("0")
        return (self.total_pnl / self.total_capital) * 100

    def update_drawdown(self) -> None:
        """Update drawdown calculation."""
        if self.peak_equity > 0:
            self.drawdown_pct = ((self.peak_equity - self.current_equity) / self.peak_equity) * 100
        else:
            self.drawdown_pct = Decimal("0")


@dataclass
class MarketRiskAssessment:
    """
    Risk assessment for a specific market.

    Attributes:
        market_id: Market identifier
        risk_level: Assessed risk level
        volatility_pct: Current volatility
        liquidity_score: Liquidity score (0-1)
        spread_pct: Current spread percentage
        risk_factors: Identified risk factors
        assessed_at: Assessment timestamp
    """

    market_id: MarketId
    risk_level: RiskLevel = "MEDIUM"
    volatility_pct: Decimal | None = None
    liquidity_score: Decimal | None = None
    spread_pct: Decimal | None = None
    risk_factors: list[str] = field(default_factory=list)
    assessed_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_tradeable(self) -> bool:
        """Check if market is considered tradeable."""
        return self.risk_level != "CRITICAL"


@dataclass
class ApprovalRequest:
    """
    Request for human approval.

    Used for live trading and high-risk operations.

    Attributes:
        request_id: Request identifier
        action: Action requiring approval
        description: Human-readable description
        risk_assessment: Associated risk assessment
        requested_at: Request timestamp
        approved_by: Who approved (None if pending)
        approved_at: Approval timestamp
        is_approved: Approval status
    """

    request_id: str
    action: str
    description: str
    risk_assessment: RiskValidationResult | None = None
    requested_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    approved_by: str | None = None
    approved_at: Timestamp | None = None
    is_approved: bool = False

    def approve(self, approved_by: str) -> None:
        """Approve the request."""
        self.is_approved = True
        self.approved_by = approved_by
        self.approved_at = datetime.now(UTC)

    @property
    def is_pending(self) -> bool:
        """Check if approval is pending."""
        return not self.is_approved
