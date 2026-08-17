"""Tests for risk domain models."""

from decimal import Decimal

import pytest

from okx_trading.domain.risk.models import (
    ApprovalRequest,
    MarketRiskAssessment,
    PortfolioRisk,
    RiskLimits,
    RiskValidationResult,
    RiskViolation,
)


class TestRiskLimits:
    """Tests for RiskLimits."""

    def test_default_values(self):
        """Default risk limits should have sensible values."""
        limits = RiskLimits()
        assert limits.max_capital_per_grid == Decimal("100")
        assert limits.max_total_capital == Decimal("500")
        assert limits.max_drawdown_pct == Decimal("10")
        assert limits.max_concurrent_grids == 5
        assert limits.max_position_pct == Decimal("20")
        assert limits.min_profitable_exit_pct == Decimal("0.5")
        assert limits.max_slippage_pct == Decimal("1")
        assert limits.max_execution_cost_pct == Decimal("2")
        assert limits.min_reserve_pct == Decimal("10")
        assert limits.max_exposure_pct == Decimal("80")

    def test_custom_values(self):
        """Custom risk limits should be accepted."""
        limits = RiskLimits(
            max_capital_per_grid=Decimal("200"),
            max_total_capital=Decimal("1000"),
            max_drawdown_pct=Decimal("15"),
            max_concurrent_grids=10,
        )
        assert limits.max_capital_per_grid == Decimal("200")
        assert limits.max_total_capital == Decimal("1000")
        assert limits.max_drawdown_pct == Decimal("15")
        assert limits.max_concurrent_grids == 10

    def test_zero_capital_per_grid_raises(self):
        """Zero max_capital_per_grid should raise ValueError."""
        with pytest.raises(ValueError, match="max_capital_per_grid must be positive"):
            RiskLimits(max_capital_per_grid=Decimal("0"))

    def test_negative_capital_per_grid_raises(self):
        """Negative max_capital_per_grid should raise ValueError."""
        with pytest.raises(ValueError, match="max_capital_per_grid must be positive"):
            RiskLimits(max_capital_per_grid=Decimal("-10"))

    def test_zero_total_capital_raises(self):
        """Zero max_total_capital should raise ValueError."""
        with pytest.raises(ValueError, match="max_total_capital must be positive"):
            RiskLimits(max_total_capital=Decimal("0"))

    def test_zero_drawdown_raises(self):
        """Zero max_drawdown_pct should raise ValueError."""
        with pytest.raises(ValueError, match="max_drawdown_pct must be between 0 and 100"):
            RiskLimits(max_drawdown_pct=Decimal("0"))

    def test_over_100_drawdown_raises(self):
        """max_drawdown_pct > 100 should raise ValueError."""
        with pytest.raises(ValueError, match="max_drawdown_pct must be between 0 and 100"):
            RiskLimits(max_drawdown_pct=Decimal("101"))

    def test_zero_concurrent_grids_raises(self):
        """Zero max_concurrent_grids should raise ValueError."""
        with pytest.raises(ValueError, match="max_concurrent_grids must be >= 1"):
            RiskLimits(max_concurrent_grids=0)

    def test_frozen(self):
        """RiskLimits should be immutable."""
        limits = RiskLimits()
        with pytest.raises(AttributeError):
            limits.max_capital_per_grid = Decimal("999")  # type: ignore[misc]


class TestRiskViolation:
    """Tests for RiskViolation."""

    def test_create_violation(self):
        """Should create a risk violation."""
        violation = RiskViolation(
            rule="MAX_CAPITAL",
            message="Capital exceeds limit",
            value=Decimal("150"),
            limit=Decimal("100"),
            severity="HIGH",
        )
        assert violation.rule == "MAX_CAPITAL"
        assert violation.message == "Capital exceeds limit"
        assert violation.value == Decimal("150")
        assert violation.limit == Decimal("100")
        assert violation.severity == "HIGH"

    def test_default_severity(self):
        """Default severity should be MEDIUM."""
        violation = RiskViolation(rule="TEST", message="Test")
        assert violation.severity == "MEDIUM"

    def test_none_values(self):
        """Value and limit can be None."""
        violation = RiskViolation(rule="TEST", message="Test")
        assert violation.value is None
        assert violation.limit is None


class TestRiskValidationResult:
    """Tests for RiskValidationResult."""

    def test_default_pass(self):
        """Default status should be PASS."""
        result = RiskValidationResult()
        assert result.status == "PASS"
        assert result.is_passed
        assert not result.has_warnings
        assert len(result.violations) == 0
        assert len(result.warnings) == 0

    def test_add_violation_sets_fail(self):
        """Adding a violation should set status to FAIL."""
        result = RiskValidationResult()
        violation = RiskViolation(rule="TEST", message="Test violation")
        result.add_violation(violation)
        assert result.status == "FAIL"
        assert not result.is_passed
        assert len(result.violations) == 1

    def test_add_warning_sets_warning(self):
        """Adding a warning should set status to WARNING."""
        result = RiskValidationResult()
        warning = RiskViolation(rule="TEST", message="Test warning", severity="LOW")
        result.add_warning(warning)
        assert result.status == "WARNING"
        assert result.has_warnings
        assert not result.is_passed  # WARNING is not PASS
        assert len(result.warnings) == 1

    def test_violation_overrides_warning(self):
        """Adding violation after warning should set FAIL."""
        result = RiskValidationResult()
        result.add_warning(RiskViolation(rule="W", message="Warning"))
        result.add_violation(RiskViolation(rule="V", message="Violation"))
        assert result.status == "FAIL"

    def test_metadata(self):
        """Metadata should be stored."""
        result = RiskValidationResult(metadata={"key": "value"})
        assert result.metadata["key"] == "value"


class TestPortfolioRisk:
    """Tests for PortfolioRisk."""

    def test_default_values(self):
        """Default portfolio risk should have zero values."""
        risk = PortfolioRisk()
        assert risk.total_capital == Decimal("0")
        assert risk.deployed_capital == Decimal("0")
        assert risk.available_capital == Decimal("0")
        assert risk.active_grids == 0
        assert risk.risk_level == "LOW"

    def test_reserve_pct(self):
        """Reserve percentage should be calculated."""
        risk = PortfolioRisk(
            total_capital=Decimal("1000"),
            available_capital=Decimal("200"),
        )
        assert risk.reserve_pct == Decimal("20")

    def test_reserve_pct_zero_capital(self):
        """Reserve percentage should be 0 when capital is 0."""
        risk = PortfolioRisk(total_capital=Decimal("0"))
        assert risk.reserve_pct == Decimal("0")

    def test_total_pnl(self):
        """Total P&L should sum realized and unrealized."""
        risk = PortfolioRisk(
            realized_pnl=Decimal("50"),
            unrealized_pnl=Decimal("-10"),
        )
        assert risk.total_pnl == Decimal("40")

    def test_total_pnl_pct(self):
        """Total P&L percentage should be calculated."""
        risk = PortfolioRisk(
            total_capital=Decimal("1000"),
            realized_pnl=Decimal("50"),
            unrealized_pnl=Decimal("50"),
        )
        assert risk.total_pnl_pct == Decimal("10")

    def test_total_pnl_pct_zero_capital(self):
        """P&L percentage should be 0 when capital is 0."""
        risk = PortfolioRisk(total_capital=Decimal("0"))
        assert risk.total_pnl_pct == Decimal("0")

    def test_update_drawdown(self):
        """Drawdown should be calculated from peak and current equity."""
        risk = PortfolioRisk(
            peak_equity=Decimal("1000"),
            current_equity=Decimal("900"),
        )
        risk.update_drawdown()
        assert risk.drawdown_pct == Decimal("10")

    def test_update_drawdown_zero_peak(self):
        """Drawdown should be 0 when peak equity is 0."""
        risk = PortfolioRisk(
            peak_equity=Decimal("0"),
            current_equity=Decimal("900"),
        )
        risk.update_drawdown()
        assert risk.drawdown_pct == Decimal("0")

    def test_update_drawdown_no_loss(self):
        """Drawdown should be 0 when equity is at peak."""
        risk = PortfolioRisk(
            peak_equity=Decimal("1000"),
            current_equity=Decimal("1000"),
        )
        risk.update_drawdown()
        assert risk.drawdown_pct == Decimal("0")


class TestMarketRiskAssessment:
    """Tests for MarketRiskAssessment."""

    def test_create_assessment(self):
        """Should create a market risk assessment."""
        assessment = MarketRiskAssessment(
            market_id="BTC-USDT",
            risk_level="LOW",
            volatility_pct=Decimal("2.5"),
            liquidity_score=Decimal("0.9"),
            spread_pct=Decimal("0.01"),
        )
        assert assessment.market_id == "BTC-USDT"
        assert assessment.risk_level == "LOW"
        assert assessment.volatility_pct == Decimal("2.5")
        assert assessment.liquidity_score == Decimal("0.9")
        assert assessment.spread_pct == Decimal("0.01")

    def test_is_tradeable(self):
        """Non-critical markets should be tradeable."""
        assessment = MarketRiskAssessment(market_id="BTC-USDT", risk_level="HIGH")
        assert assessment.is_tradeable

    def test_critical_not_tradeable(self):
        """Critical markets should not be tradeable."""
        assessment = MarketRiskAssessment(market_id="BTC-USDT", risk_level="CRITICAL")
        assert not assessment.is_tradeable

    def test_risk_factors(self):
        """Risk factors should be stored."""
        assessment = MarketRiskAssessment(
            market_id="BTC-USDT",
            risk_factors=["high_volatility", "low_liquidity"],
        )
        assert len(assessment.risk_factors) == 2
        assert "high_volatility" in assessment.risk_factors


class TestApprovalRequest:
    """Tests for ApprovalRequest."""

    def test_create_request(self):
        """Should create an approval request."""
        request = ApprovalRequest(
            request_id="REQ-001",
            action="START_LIVE_TRADING",
            description="Start live trading on BTC-USDT",
        )
        assert request.request_id == "REQ-001"
        assert request.action == "START_LIVE_TRADING"
        assert request.description == "Start live trading on BTC-USDT"
        assert request.is_pending
        assert not request.is_approved

    def test_approve(self):
        """Approving should update status."""
        request = ApprovalRequest(
            request_id="REQ-001",
            action="START_LIVE_TRADING",
            description="Start live trading",
        )
        request.approve("admin")
        assert request.is_approved
        assert not request.is_pending
        assert request.approved_by == "admin"
        assert request.approved_at is not None

    def test_pending_until_approved(self):
        """Request should be pending until approved."""
        request = ApprovalRequest(
            request_id="REQ-001",
            action="TEST",
            description="Test",
        )
        assert request.is_pending
        request.approve("user")
        assert not request.is_pending

    def test_risk_assessment_attachment(self):
        """Risk assessment can be attached."""
        assessment = RiskValidationResult()
        request = ApprovalRequest(
            request_id="REQ-001",
            action="TEST",
            description="Test",
            risk_assessment=assessment,
        )
        assert request.risk_assessment is assessment
