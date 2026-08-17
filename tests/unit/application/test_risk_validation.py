"""
Unit tests for the RiskValidationService and its wiring into the execution path.

These tests lock in the fix for the "RiskLimits not wired to execution" issue:

1. RiskValidationService enforces deterministic risk limits.
2. ExecutionEngine validates every order BEFORE submission.
3. Orders that violate risk limits are rejected locally and never reach
   the exchange adapter.
4. Spot-only rule: SELL orders must be covered by an open position.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from okx_trading.application.services.execution_engine import ExecutionEngine
from okx_trading.application.services.risk_validation import RiskValidationService
from okx_trading.domain.execution.models import Position
from okx_trading.domain.risk.models import PortfolioRisk, RiskLimits
from okx_trading.infrastructure.okx.adapter import OKXAdapter


def make_limits(**overrides: object) -> RiskLimits:
    """Create risk limits with optional overrides."""
    defaults: dict[str, object] = {
        "max_capital_per_grid": Decimal("100"),
        "max_total_capital": Decimal("500"),
        "max_drawdown_pct": Decimal("10"),
        "max_concurrent_grids": 5,
    }
    defaults.update(overrides)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def make_service(
    limits: RiskLimits | None = None,
    portfolio: PortfolioRisk | None = None,
) -> RiskValidationService:
    """Create a RiskValidationService for testing."""
    return RiskValidationService(limits=limits or make_limits(), portfolio=portfolio)


class TestRiskValidationService:
    """Tests for RiskValidationService.validate_order."""

    def test_valid_buy_passes(self) -> None:
        """A small BUY within all limits passes validation."""
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),  # notional = 50 USDT < 100 limit
        )
        assert result.is_passed is True
        assert len(result.violations) == 0

    def test_positive_quantity_required(self) -> None:
        """Zero or negative quantity is rejected."""
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0"),
            price=Decimal("50000"),
        )
        assert result.is_passed is False
        assert result.violations[0].rule == "POSITIVE_QUANTITY"

    def test_max_capital_per_grid_enforced(self) -> None:
        """BUY notional exceeding max_capital_per_grid is rejected."""
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),  # notional = 500 USDT > 100 limit
        )
        assert result.is_passed is False
        assert any(v.rule == "MAX_CAPITAL_PER_GRID" for v in result.violations)

    def test_max_total_capital_enforced(self) -> None:
        """Projected deployed capital exceeding max_total_capital is rejected."""
        portfolio = PortfolioRisk(
            total_capital=Decimal("500"),
            deployed_capital=Decimal("450"),
            available_capital=Decimal("50"),
        )
        service = make_service(portfolio=portfolio)
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),  # notional 50; 450+50=500 ok... use bigger
        )
        # 450 + 50 = 500 which equals limit (not exceeded), so passes
        assert result.is_passed is True

        result2 = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.002"),
            price=Decimal("50000"),  # notional 100; 450+100=550 > 500
        )
        assert result2.is_passed is False
        assert any(v.rule == "MAX_TOTAL_CAPITAL" for v in result2.violations)

    def test_max_drawdown_blocks_buys(self) -> None:
        """SECURITY: max drawdown breach blocks all new BUY orders."""
        portfolio = PortfolioRisk(
            total_capital=Decimal("500"),
            drawdown_pct=Decimal("15"),  # > 10% limit
        )
        service = make_service(portfolio=portfolio)
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        assert result.is_passed is False
        assert any(v.rule == "MAX_DRAWDOWN" for v in result.violations)

    def test_max_concurrent_grids_enforced(self) -> None:
        """Concurrency limit blocks new BUY orders when at capacity."""
        portfolio = PortfolioRisk(
            total_capital=Decimal("500"),
            active_grids=5,  # at the limit of 5
        )
        service = make_service(portfolio=portfolio)
        result = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        assert result.is_passed is False
        assert any(v.rule == "MAX_CONCURRENT_GRIDS" for v in result.violations)

    def test_sell_without_position_rejected(self) -> None:
        """SECURITY (spot-only): SELL with no position is rejected (no shorting)."""
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("0.001"),
            positions={},
        )
        assert result.is_passed is False
        assert any(v.rule == "NO_SHORTING" for v in result.violations)

    def test_sell_covered_by_position_passes(self) -> None:
        """SELL covered by an open position passes."""
        position = Position(
            position_id="POS-1",
            market_id="BTC-USDT",
            quantity=Decimal("0.01"),
            average_entry_price=Decimal("50000"),
        )
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("0.005"),
            positions={"BTC-USDT": position},
        )
        assert result.is_passed is True

    def test_sell_exceeding_position_rejected(self) -> None:
        """SELL more than held quantity is rejected (no shorting)."""
        position = Position(
            position_id="POS-1",
            market_id="BTC-USDT",
            quantity=Decimal("0.001"),
            average_entry_price=Decimal("50000"),
        )
        service = make_service()
        result = service.validate_order(
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("0.01"),
            positions={"BTC-USDT": position},
        )
        assert result.is_passed is False
        assert any(v.rule == "NO_SHORTING" for v in result.violations)

    def test_deterministic(self) -> None:
        """Same inputs must produce the same validation status."""
        service = make_service()
        r1 = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        r2 = service.validate_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )
        assert r1.is_passed == r2.is_passed
        assert [v.rule for v in r1.violations] == [v.rule for v in r2.violations]


def make_mock_adapter(mode: str = "DEMO") -> MagicMock:
    """Create a mock OKX adapter."""
    adapter = MagicMock(spec=OKXAdapter)
    adapter.mode = mode
    adapter.needs_reconciliation = False
    adapter.place_order = AsyncMock(return_value="EX-ORDER-001")
    return adapter


class TestExecutionEngineRiskWiring:
    """Tests proving risk validation is wired into the execution path."""

    @pytest.mark.asyncio
    async def test_order_passing_risk_is_submitted(self) -> None:
        """An order that passes risk validation is submitted to the adapter."""
        adapter = make_mock_adapter()
        engine = ExecutionEngine(adapter=adapter, risk_validator=make_service())

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )

        assert result.success is True
        adapter.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_order_violating_risk_never_reaches_exchange(self) -> None:
        """SECURITY: an order violating risk limits must NOT reach the adapter."""
        adapter = make_mock_adapter()
        engine = ExecutionEngine(adapter=adapter, risk_validator=make_service())

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),  # notional 500 > 100 per-grid limit
        )

        assert result.success is False
        assert result.error_message is not None
        assert "Risk validation failed" in result.error_message
        adapter.place_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sell_without_position_never_reaches_exchange(self) -> None:
        """SECURITY: an uncovered SELL (shorting) must NOT reach the adapter."""
        adapter = make_mock_adapter()
        engine = ExecutionEngine(adapter=adapter, risk_validator=make_service())

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("0.001"),
            price=Decimal("50000"),
        )

        assert result.success is False
        assert "Risk validation failed" in (result.error_message or "")
        adapter.place_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejected_order_recorded_with_rejected_status(self) -> None:
        """Risk-rejected orders are tracked with REJECTED status."""
        adapter = make_mock_adapter()
        engine = ExecutionEngine(adapter=adapter, risk_validator=make_service())

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"
