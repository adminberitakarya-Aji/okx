"""
Tests for ExecutionEngine — order management and execution.

Covers:
- execute_order: risk validation gate, reconciliation trigger, success path,
  ExchangeAPIError path, generic exception path
- cancel_order: not found, no exchange ID, not active, success
- get_order, get_active_orders, get_orders_for_market
- get_positions, get_position
- reconcile: adapter reconcile, position sync, order status update
- _update_order_from_exchange: status change, fill quantity, average price
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_grid.application.services.authorization import Identity, Role
from trading_grid.application.services.execution_engine import (
    ExecutionEngine,
    ExecutionResult,
)
from trading_grid.application.services.risk_validation import RiskValidationService
from trading_grid.application.services.tenant_limits import (
    MaxGridsExceededError,
    RateLimitExceededError,
    TenantLimitsService,
    UserEmergencyStoppedError,
)
from trading_grid.domain.exchange.errors import ExchangeAPIError
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.execution.models import Order, Position
from trading_grid.domain.risk.models import RiskValidationResult, RiskViolation

# [A-H12] Test identity for execute_order (identity is REQUIRED).
DEMO_IDENTITY = Identity(
    identity_id="test-user",
    identity_type="HUMAN",
    role=Role.DEMO_OPERATOR,
    allowed_environments=("DEMO",),
)


def _make_adapter(
    exchange_id: str = "OKX",
    mode: str = "DEMO",
    needs_reconciliation: bool = False,
) -> MagicMock:
    """Create a mock ExchangeAdapter."""
    adapter = MagicMock(spec=ExchangeAdapter)
    adapter.exchange_id = exchange_id
    adapter.mode = mode
    adapter.needs_reconciliation = needs_reconciliation
    adapter.place_order = AsyncMock(return_value="EX-12345")
    adapter.cancel_order = AsyncMock(return_value=True)
    adapter.get_order_status = AsyncMock(
        return_value={
            "status": "FILLED",
            "filled_quantity": "1.0",
            "average_price": "50000",
            "raw": {},
        }
    )
    adapter.get_positions = AsyncMock(return_value=[])
    adapter.reconcile = AsyncMock(return_value={"status": "ok"})
    return adapter


def _make_risk_validator(passed: bool = True) -> MagicMock:
    """Create a mock RiskValidationService."""
    validator = MagicMock(spec=RiskValidationService)
    result = RiskValidationResult()
    if not passed:
        result.add_violation(
            RiskViolation(
                rule="MAX_CAPITAL_PER_GRID",
                message="Order notional exceeds limit",
                value=Decimal("200"),
                limit=Decimal("100"),
                severity="HIGH",
            )
        )
    validator.validate_order = MagicMock(return_value=result)
    return validator


def _make_tenant_limits() -> MagicMock:
    """Create a mock TenantLimitsService."""
    limits = MagicMock(spec=TenantLimitsService)
    limits.check_can_trade = MagicMock(return_value=None)
    return limits


def _make_engine(
    adapter: MagicMock | None = None,
    risk_validator: MagicMock | None = None,
    tenant_limits: MagicMock | None = None,
) -> ExecutionEngine:
    """Create an ExecutionEngine with mocks."""
    return ExecutionEngine(
        adapter=adapter or _make_adapter(),
        risk_validator=risk_validator or _make_risk_validator(),
        tenant_limits=tenant_limits,
    )


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        result = ExecutionResult(
            success=True,
            order_id="ORD-ABC123",
            exchange_order_id="EX-123",
        )
        assert result.success is True
        assert result.order_id == "ORD-ABC123"
        assert result.exchange_order_id == "EX-123"
        assert result.error_message is None
        assert result.fills == []

    def test_failure_result(self):
        result = ExecutionResult(
            success=False,
            order_id="ORD-ABC123",
            error_message="Risk validation failed",
        )
        assert result.success is False
        assert result.error_message == "Risk validation failed"


class TestExecutionEngineInit:
    """Tests for ExecutionEngine initialization."""

    def test_init_stores_adapter_and_validator(self):
        adapter = _make_adapter()
        validator = _make_risk_validator()
        engine = ExecutionEngine(adapter=adapter, risk_validator=validator)
        assert engine._adapter is adapter
        assert engine._risk_validator is validator
        assert engine._orders == {}
        assert engine._positions == {}
        # _fills was removed as unused dead code (A-L1)
        assert not hasattr(engine, "_fills")

    def test_mode_delegates_to_adapter(self):
        adapter = _make_adapter(mode="LIVE")
        engine = _make_engine(adapter=adapter)
        assert engine.mode == "LIVE"

    def test_mode_demo(self):
        adapter = _make_adapter(mode="DEMO")
        engine = _make_engine(adapter=adapter)
        assert engine.mode == "DEMO"


class TestExecuteOrder:
    """Tests for execute_order."""

    @pytest.mark.asyncio
    async def test_successful_market_order(self):
        """Market order passes risk validation and is submitted."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is True
        assert result.order_id.startswith("ORD-")
        assert result.exchange_order_id == "EX-12345"
        assert result.error_message is None
        adapter.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_successful_limit_order(self):
        """Limit order with price is submitted."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("49000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is True
        # Verify order was stored with LIMIT type
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.order_type == "LIMIT"
        assert order.price == Decimal("49000")

    @pytest.mark.asyncio
    async def test_market_order_type_when_no_price(self):
        """Order without price is MARKET type."""
        engine = _make_engine()

        result = await engine.execute_order(
            market_id="ETH-USDT",
            side="SELL",
            quantity=Decimal("1"),
            reference_price=Decimal("3000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.order_type == "MARKET"

    @pytest.mark.asyncio
    async def test_risk_validation_failure_rejects_order(self):
        """Order failing risk validation is rejected locally, never sent to exchange."""
        adapter = _make_adapter()
        validator = _make_risk_validator(passed=False)
        engine = _make_engine(adapter=adapter, risk_validator=validator)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("10"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "Risk validation failed" in result.error_message
        assert "Order notional exceeds limit" in result.error_message
        # Order must NOT reach the exchange
        adapter.place_order.assert_not_awaited()
        # Order is stored as REJECTED
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_risk_validation_called_with_correct_args(self):
        """Risk validator receives all order parameters."""
        validator = _make_risk_validator()
        engine = _make_engine(risk_validator=validator)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.5"),
            price=Decimal("48000"),
            reference_price=Decimal("48100"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        validator.validate_order.assert_called_once()
        call_kwargs = validator.validate_order.call_args.kwargs
        assert call_kwargs["market_id"] == "BTC-USDT"
        assert call_kwargs["side"] == "BUY"
        assert call_kwargs["quantity"] == Decimal("0.5")
        assert call_kwargs["price"] == Decimal("48000")
        assert call_kwargs["reference_price"] == Decimal("48100")

    @pytest.mark.asyncio
    async def test_reconciliation_triggered_before_order_when_needed(self):
        """If adapter.needs_reconciliation is True, reconcile() is called before placing."""
        adapter = _make_adapter(needs_reconciliation=True)
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is True
        adapter.reconcile.assert_awaited()

    @pytest.mark.asyncio
    async def test_no_reconciliation_when_not_needed(self):
        """If adapter.needs_reconciliation is False, reconcile() is not called."""
        adapter = _make_adapter(needs_reconciliation=False)
        engine = _make_engine(adapter=adapter)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        adapter.reconcile.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_exchange_api_error_rejects_order(self):
        """ExchangeAPIError during placement rejects the order with error detail."""
        adapter = _make_adapter()
        adapter.place_order = AsyncMock(
            side_effect=ExchangeAPIError(code="51000", message="Insufficient balance")
        )
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "Insufficient balance" in result.error_message
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_generic_exception_rejects_order(self):
        """Unexpected exception during placement rejects the order."""
        adapter = _make_adapter()
        adapter.place_order = AsyncMock(side_effect=RuntimeError("Network timeout"))
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "Execution failed" in result.error_message
        assert "Network timeout" in result.error_message
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_order_stored_after_successful_submission(self):
        """Submitted order is tracked in internal state."""
        engine = _make_engine()

        result = await engine.execute_order(
            market_id="SOL-USDT",
            side="BUY",
            quantity=Decimal("5"),
            price=Decimal("150"),
            metadata={"grid_level": 3, "section_id": 1},
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.market_id == "SOL-USDT"
        assert order.side == "BUY"
        assert order.status == "SUBMITTED"
        assert order.exchange_order_id == "EX-12345"
        assert order.metadata == {"grid_level": 3, "section_id": 1}

    @pytest.mark.asyncio
    async def test_metadata_defaults_to_empty_dict(self):
        """Metadata defaults to empty dict when not provided."""
        engine = _make_engine()

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.metadata == {}


class TestExecuteOrderIdentity:
    """[A-H12] Tests for identity-required enforcement in execute_order.

    Phase 8.6 (A-H12): identity is now REQUIRED on every execute_order call.
    No caller may bypass authorization:
    1. Passing no identity raises ValueError (fail-closed).
    2. An identity without access to the engine environment is rejected.
    3. An identity with insufficient permission level is rejected.
    4. A valid DEMO_OPERATOR identity can execute in DEMO.
    5. SYSTEM identity (both environments) can execute autonomously.
    """

    @pytest.mark.asyncio
    async def test_missing_identity_raises_value_error(self):
        """[A-H12] execute_order without identity raises ValueError (fail-closed)."""
        engine = _make_engine()

        with pytest.raises(ValueError, match="identity is required"):
            await engine.execute_order(
                market_id="BTC-USDT",
                side="BUY",
                quantity=Decimal("0.01"),
                price=Decimal("50000"),
            )

    @pytest.mark.asyncio
    async def test_identity_without_environment_access_rejected(self):
        """[A-H12] Identity not allowed in DEMO is rejected locally."""
        adapter = _make_adapter(mode="DEMO")
        engine = _make_engine(adapter=adapter)

        # LIVE-only identity cannot access DEMO
        live_only = Identity(
            identity_id="live-only-user",
            identity_type="HUMAN",
            role=Role.LIVE_OPERATOR,
            allowed_environments=("LIVE",),
        )

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=live_only,
        )

        assert result.success is False
        assert "Authorization denied" in (result.error_message or "")
        assert "not allowed in DEMO" in (result.error_message or "")
        # Order must NOT reach the exchange
        adapter.place_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_insufficient_permission_level_rejected(self):
        """[A-H12] Identity below DEMO_OPERATOR is rejected in DEMO."""
        adapter = _make_adapter(mode="DEMO")
        engine = _make_engine(adapter=adapter)

        # VIEWER level (0) < DEMO_OPERATOR (2)
        viewer = Identity(
            identity_id="viewer-user",
            identity_type="HUMAN",
            role=Role.VIEWER,
            allowed_environments=("DEMO",),
        )

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=viewer,
        )

        assert result.success is False
        assert "Authorization denied" in (result.error_message or "")
        assert "Insufficient permission level" in (result.error_message or "")
        adapter.place_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_demo_operator_identity_executes(self):
        """[A-H12] A valid DEMO_OPERATOR identity can execute in DEMO."""
        adapter = _make_adapter(mode="DEMO")
        engine = _make_engine(adapter=adapter)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,
        )

        assert result.success is True
        adapter.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_system_identity_can_execute_in_both_environments(self):
        """[A-H12] SYSTEM identity (DEMO+LIVE) can execute in DEMO and LIVE."""
        from trading_grid.application.services.authorization import SYSTEM_IDENTITY

        for mode in ("DEMO", "LIVE"):
            adapter = _make_adapter(mode=mode)
            engine = _make_engine(adapter=adapter)

            result = await engine.execute_order(
                market_id="BTC-USDT",
                side="BUY",
                quantity=Decimal("0.01"),
                price=Decimal("50000"),
                identity=SYSTEM_IDENTITY,
            )

            assert result.success is True, f"SYSTEM identity failed in {mode}"
            adapter.place_order.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_identity_metadata_is_stored_on_order(self):
        """[A-H12] The caller identity is recorded in order metadata for audit."""
        engine = _make_engine()

        identity = Identity(
            identity_id="audit-user",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
            allowed_environments=("DEMO",),
            metadata={"source": "test-audit"},
        )

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=identity,
            metadata={"grid_level": 1},
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.metadata == {"grid_level": 1}


class TestExecuteOrderTenantLimits:
    """Tests for per-user limits enforcement in execute_order."""

    @pytest.mark.asyncio
    async def test_check_can_trade_called_with_user_id(self):
        """check_can_trade is called with user_id and active_grid_count."""
        tenant_limits = _make_tenant_limits()
        engine = _make_engine(tenant_limits=tenant_limits)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            active_grid_count=2,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        tenant_limits.check_can_trade.assert_called_once_with(
            user_id="usr_1",
            active_grid_count=2,
            skip_rate_limit=False,
        )

    @pytest.mark.asyncio
    async def test_check_can_trade_not_called_without_user_id(self):
        """check_can_trade is NOT called when user_id is None."""
        tenant_limits = _make_tenant_limits()
        engine = _make_engine(tenant_limits=tenant_limits)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        tenant_limits.check_can_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_loud_skip_when_tenant_limits_configured_but_no_user_id(self):
        """When tenant_limits is configured but user_id is None, a warning is logged."""
        from unittest.mock import patch

        tenant_limits = _make_tenant_limits()
        engine = _make_engine(tenant_limits=tenant_limits)

        with patch(
            "trading_grid.application.services.execution_engine.logger.warning"
        ) as mock_warning:
            result = await engine.execute_order(
                market_id="BTC-USDT",
                side="BUY",
                quantity=Decimal("0.01"),
                price=Decimal("50000"),
                identity=DEMO_IDENTITY,  # [A-H12] required
            )

        # Order still succeeds (soft enforcement)
        assert result.success is True
        # Warning is logged for the "loud skip"
        mock_warning.assert_any_call(
            "tenant_limits_skipped_missing_user_id",
            order_id=result.order_id,
            market_id="BTC-USDT",
            side="BUY",
            quantity="0.01",
        )
        # check_can_trade is NOT called
        tenant_limits.check_can_trade.assert_not_called()

    @pytest.mark.asyncio
    async def test_emergency_stop_rejects_order_locally(self):
        """Emergency stop rejects order locally, never reaches exchange."""
        adapter = _make_adapter()
        tenant_limits = _make_tenant_limits()
        tenant_limits.check_can_trade = MagicMock(
            side_effect=UserEmergencyStoppedError("User usr_1 is under emergency stop: Stop")
        )
        engine = _make_engine(adapter=adapter, tenant_limits=tenant_limits)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "User emergency stopped" in result.error_message
        # Order must NOT reach the exchange
        adapter.place_order.assert_not_awaited()
        # Order is stored as REJECTED
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_rate_limit_rejects_order_locally(self):
        """Rate limit exceeded rejects order locally, never reaches exchange."""
        adapter = _make_adapter()
        tenant_limits = _make_tenant_limits()
        tenant_limits.check_can_trade = MagicMock(
            side_effect=RateLimitExceededError("usr_1", retry_after_seconds=30.0)
        )
        engine = _make_engine(adapter=adapter, tenant_limits=tenant_limits)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "Rate limit exceeded" in result.error_message
        # Order must NOT reach the exchange
        adapter.place_order.assert_not_awaited()
        # Order is stored as REJECTED
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_max_grids_rejects_order_locally(self):
        """Max grids exceeded rejects order locally, never reaches exchange."""
        adapter = _make_adapter()
        tenant_limits = _make_tenant_limits()
        tenant_limits.check_can_trade = MagicMock(
            side_effect=MaxGridsExceededError("User usr_1 has 5 active grids (max: 3)")
        )
        engine = _make_engine(adapter=adapter, tenant_limits=tenant_limits)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            active_grid_count=5,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "Max grids exceeded" in result.error_message
        # Order must NOT reach the exchange
        adapter.place_order.assert_not_awaited()
        # Order is stored as REJECTED
        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_tenant_limits_checked_before_risk_validation(self):
        """Per-user limits are checked BEFORE risk validation."""
        tenant_limits = _make_tenant_limits()
        validator = _make_risk_validator()
        engine = _make_engine(risk_validator=validator, tenant_limits=tenant_limits)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        # Both are called, but check_can_trade must be called first
        tenant_limits.check_can_trade.assert_called_once()
        validator.validate_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_risk_validation_not_called_when_tenant_limits_fail(self):
        """Risk validation is NOT called when per-user limits fail."""
        tenant_limits = _make_tenant_limits()
        tenant_limits.check_can_trade = MagicMock(
            side_effect=UserEmergencyStoppedError("User usr_1 is under emergency stop: Stop")
        )
        validator = _make_risk_validator()
        engine = _make_engine(risk_validator=validator, tenant_limits=tenant_limits)

        await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        tenant_limits.check_can_trade.assert_called_once()
        validator.validate_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_rate_limit_forwarded_to_check_can_trade(self):
        """[A-M1] skip_rate_limit=True is forwarded to check_can_trade.

        Autonomous grid triggers (PriceMonitorService) pass skip_rate_limit=True
        so machine-generated orders bypass the interactive rate limit while
        emergency stop and max-grid checks remain enforced.
        """
        tenant_limits = _make_tenant_limits()
        engine = _make_engine(tenant_limits=tenant_limits)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            active_grid_count=1,
            skip_rate_limit=True,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is True
        tenant_limits.check_can_trade.assert_called_once_with(
            user_id="usr_1",
            active_grid_count=1,
            skip_rate_limit=True,
        )

    @pytest.mark.asyncio
    async def test_skip_rate_limit_true_still_enforces_emergency_stop(self):
        """[A-M1] Even with skip_rate_limit=True, emergency stop blocks orders."""
        adapter = _make_adapter()
        tenant_limits = _make_tenant_limits()
        tenant_limits.check_can_trade = MagicMock(
            side_effect=UserEmergencyStoppedError("User usr_1 is under emergency stop: Stop")
        )
        engine = _make_engine(adapter=adapter, tenant_limits=tenant_limits)

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            price=Decimal("50000"),
            user_id="usr_1",
            skip_rate_limit=True,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result.success is False
        assert "User emergency stopped" in result.error_message
        adapter.place_order.assert_not_awaited()


class TestCancelOrder:
    """Tests for cancel_order."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_order_returns_false(self):
        """Cancelling an unknown order returns False."""
        engine = _make_engine()
        result = await engine.cancel_order("ORD-NONEXISTENT")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_order_without_exchange_id_returns_false(self):
        """Cancelling an order with no exchange_order_id returns False."""
        engine = _make_engine()
        # Manually insert an order without exchange_order_id
        order = Order(
            order_id="ORD-NOEX",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
        )
        engine._orders["ORD-NOEX"] = order

        result = await engine.cancel_order("ORD-NOEX")
        assert result is False

    @pytest.mark.asyncio
    async def test_cancel_inactive_order_returns_false(self):
        """Cancelling a non-active order (e.g., FILLED) returns False."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-FILLED",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="FILLED",
            exchange_order_id="EX-999",
        )
        engine._orders["ORD-FILLED"] = order

        result = await engine.cancel_order("ORD-FILLED")
        assert result is False
        adapter.cancel_order.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancel_active_order_success(self):
        """Cancelling an active order calls adapter and updates status."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-ACTIVE",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            exchange_order_id="EX-ACTIVE",
        )
        engine._orders["ORD-ACTIVE"] = order

        result = await engine.cancel_order("ORD-ACTIVE")

        assert result is True
        adapter.cancel_order.assert_awaited_once_with("BTC-USDT", "EX-ACTIVE")
        assert order.status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_cancel_order_adapter_failure(self):
        """If adapter cancel fails, order status is unchanged."""
        adapter = _make_adapter()
        adapter.cancel_order = AsyncMock(return_value=False)
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-FAIL",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            exchange_order_id="EX-FAIL",
        )
        engine._orders["ORD-FAIL"] = order

        result = await engine.cancel_order("ORD-FAIL")

        assert result is False
        assert order.status == "SUBMITTED"

    @pytest.mark.asyncio
    async def test_cancel_pending_order(self):
        """PENDING orders are active and can be cancelled."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-PENDING",
            market_id="ETH-USDT",
            side="SELL",
            quantity=Decimal("2"),
            status="PENDING",
            exchange_order_id="EX-PENDING",
        )
        engine._orders["ORD-PENDING"] = order

        result = await engine.cancel_order("ORD-PENDING")
        assert result is True
        assert order.status == "CANCELLED"


class TestOrderQueries:
    """Tests for order query methods."""

    def test_get_order_returns_none_for_unknown(self):
        engine = _make_engine()
        assert engine.get_order("ORD-UNKNOWN") is None

    def test_get_order_returns_stored_order(self):
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
        )
        engine._orders["ORD-1"] = order
        assert engine.get_order("ORD-1") is order

    def test_get_active_orders_filters_correctly(self):
        engine = _make_engine()
        active = Order(
            order_id="ORD-A",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
        )
        filled = Order(
            order_id="ORD-F",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="FILLED",
        )
        cancelled = Order(
            order_id="ORD-C",
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("1"),
            status="CANCELLED",
        )
        partially = Order(
            order_id="ORD-P",
            market_id="ETH-USDT",
            side="BUY",
            quantity=Decimal("2"),
            status="PARTIALLY_FILLED",
        )
        engine._orders = {
            "ORD-A": active,
            "ORD-F": filled,
            "ORD-C": cancelled,
            "ORD-P": partially,
        }

        active_orders = engine.get_active_orders()
        active_ids = {o.order_id for o in active_orders}
        assert active_ids == {"ORD-A", "ORD-P"}

    def test_get_active_orders_empty(self):
        engine = _make_engine()
        assert engine.get_active_orders() == []

    def test_get_orders_for_market(self):
        engine = _make_engine()
        btc1 = Order(
            order_id="ORD-B1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
        )
        btc2 = Order(
            order_id="ORD-B2",
            market_id="BTC-USDT",
            side="SELL",
            quantity=Decimal("1"),
        )
        eth = Order(
            order_id="ORD-E1",
            market_id="ETH-USDT",
            side="BUY",
            quantity=Decimal("1"),
        )
        engine._orders = {"ORD-B1": btc1, "ORD-B2": btc2, "ORD-E1": eth}

        btc_orders = engine.get_orders_for_market("BTC-USDT")
        assert len(btc_orders) == 2
        assert all(o.market_id == "BTC-USDT" for o in btc_orders)

    def test_get_orders_for_market_no_match(self):
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
        )
        engine._orders["ORD-1"] = order
        assert engine.get_orders_for_market("SOL-USDT") == []


class TestPositionQueries:
    """Tests for position query methods."""

    def test_get_positions_empty(self):
        engine = _make_engine()
        assert engine.get_positions() == []

    def test_get_positions_returns_all(self):
        engine = _make_engine()
        pos1 = Position(
            position_id="POS-1",
            market_id="BTC-USDT",
            quantity=Decimal("0.5"),
        )
        pos2 = Position(
            position_id="POS-2",
            market_id="ETH-USDT",
            quantity=Decimal("10"),
        )
        engine._positions = {"BTC-USDT": pos1, "ETH-USDT": pos2}

        positions = engine.get_positions()
        assert len(positions) == 2

    def test_get_position_returns_matching(self):
        engine = _make_engine()
        pos = Position(
            position_id="POS-1",
            market_id="BTC-USDT",
            quantity=Decimal("0.5"),
        )
        engine._positions["BTC-USDT"] = pos
        assert engine.get_position("BTC-USDT") is pos

    def test_get_position_returns_none_for_unknown(self):
        engine = _make_engine()
        assert engine.get_position("UNKNOWN-USDT") is None


class TestReconcile:
    """Tests for reconcile."""

    @pytest.mark.asyncio
    async def test_reconcile_calls_adapter(self):
        """Reconcile delegates to adapter.reconcile()."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)

        result = await engine.reconcile()

        adapter.reconcile.assert_awaited_once()
        assert result["adapter"] == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_reconcile_updates_positions(self):
        """Reconcile syncs positions from exchange."""
        adapter = _make_adapter()
        exchange_pos = Position(
            position_id="POS-EX",
            market_id="BTC-USDT",
            quantity=Decimal("1.5"),
            average_entry_price=Decimal("45000"),
        )
        adapter.get_positions = AsyncMock(return_value=[exchange_pos])
        engine = _make_engine(adapter=adapter)

        result = await engine.reconcile()

        assert engine.get_position("BTC-USDT") is exchange_pos
        assert result["positions"] == 1

    @pytest.mark.asyncio
    async def test_reconcile_updates_active_order_status(self):
        """Reconcile checks status of active orders with exchange_order_id."""
        adapter = _make_adapter()
        adapter.get_order_status = AsyncMock(
            return_value={
                "status": "FILLED",
                "filled_quantity": "2.0",
                "average_price": "51000",
                "raw": {},
            }
        )
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-REC",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("2"),
            status="SUBMITTED",
            exchange_order_id="EX-REC",
        )
        engine._orders["ORD-REC"] = order

        result = await engine.reconcile()

        adapter.get_order_status.assert_awaited_once_with("BTC-USDT", "EX-REC")
        assert order.status == "FILLED"
        assert order.filled_quantity == Decimal("2.0")
        assert order.average_fill_price == Decimal("51000")
        assert result["active_orders"] == 0

    @pytest.mark.asyncio
    async def test_reconcile_skips_orders_without_exchange_id(self):
        """Orders without exchange_order_id are not checked."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-NOEX",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            exchange_order_id=None,
        )
        engine._orders["ORD-NOEX"] = order

        await engine.reconcile()

        adapter.get_order_status.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_handles_order_status_error(self):
        """If get_order_status raises, reconcile continues without crashing."""
        adapter = _make_adapter()
        adapter.get_order_status = AsyncMock(side_effect=RuntimeError("API down"))
        engine = _make_engine(adapter=adapter)
        order = Order(
            order_id="ORD-ERR",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            exchange_order_id="EX-ERR",
        )
        engine._orders["ORD-ERR"] = order

        result = await engine.reconcile()

        # Order status unchanged due to error
        assert order.status == "SUBMITTED"
        assert result["local_orders"] == 1

    @pytest.mark.asyncio
    async def test_reconcile_result_structure(self):
        """Reconcile returns expected summary keys."""
        engine = _make_engine()
        result = await engine.reconcile()

        assert "adapter" in result
        assert "local_orders" in result
        assert "active_orders" in result
        assert "positions" in result


class TestUpdateOrderFromExchange:
    """Tests for _update_order_from_exchange."""

    def test_status_update(self):
        """Status is updated when exchange reports different status."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
        )

        engine._update_order_from_exchange(
            order, {"status": "PARTIALLY_FILLED", "filled_quantity": "0.5"}
        )

        assert order.status == "PARTIALLY_FILLED"

    def test_no_status_change_when_same(self):
        """Status is not updated when exchange reports same status."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
        )
        engine._update_order_from_exchange(order, {"status": "SUBMITTED"})

        assert order.status == "SUBMITTED"

    def test_filled_quantity_update(self):
        """Filled quantity is updated from exchange data."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("2"),
            status="PARTIALLY_FILLED",
        )

        engine._update_order_from_exchange(
            order, {"status": "PARTIALLY_FILLED", "filled_quantity": "1.5"}
        )

        assert order.filled_quantity == Decimal("1.5")

    def test_average_price_update(self):
        """Average fill price is updated from exchange data."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="FILLED",
        )

        engine._update_order_from_exchange(
            order,
            {
                "status": "FILLED",
                "filled_quantity": "1.0",
                "average_price": "49500.50",
            },
        )

        assert order.average_fill_price == Decimal("49500.50")

    def test_fill_update_zero_string_overwrites(self):
        """Filled quantity '0' (non-empty string) overwrites existing value."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            filled_quantity=Decimal("0.3"),
        )

        engine._update_order_from_exchange(order, {"status": "SUBMITTED", "filled_quantity": "0"})

        # "0" is a non-empty (truthy) string, so it overwrites
        assert order.filled_quantity == Decimal("0")

    def test_no_fill_update_when_empty_string(self):
        """Empty string filled_quantity does not overwrite existing value."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            filled_quantity=Decimal("0.3"),
        )

        engine._update_order_from_exchange(order, {"status": "SUBMITTED", "filled_quantity": ""})

        # "" is falsy, so filled_quantity should not be overwritten
        assert order.filled_quantity == Decimal("0.3")

    def test_no_average_price_when_none(self):
        """Average price None does not overwrite existing value."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="PARTIALLY_FILLED",
            average_fill_price=Decimal("48000"),
        )

        engine._update_order_from_exchange(
            order,
            {
                "status": "PARTIALLY_FILLED",
                "filled_quantity": "0.5",
                "average_price": None,
            },
        )

        assert order.average_fill_price == Decimal("48000")

    def test_empty_data_defaults_fill_to_zero(self):
        """Empty data dict: filled_quantity defaults to '0' (overwrites), avg price preserved."""
        engine = _make_engine()
        order = Order(
            order_id="ORD-1",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1"),
            status="SUBMITTED",
            filled_quantity=Decimal("0.2"),
            average_fill_price=Decimal("47000"),
        )

        engine._update_order_from_exchange(order, {})

        # status preserved (no "status" key)
        assert order.status == "SUBMITTED"
        # filled_quantity defaults to "0" via data.get("filled_quantity", "0")
        assert order.filled_quantity == Decimal("0")
        # average_price preserved (no "average_price" key → None → falsy)
        assert order.average_fill_price == Decimal("47000")


class TestIdempotency:
    """Tests for idempotency key deduplication in execute_order.

    Idempotency ensures that if the same logical order request is sent
    twice (e.g., due to network timeout + retry), the second request
    returns the existing result instead of submitting a duplicate order.
    """

    @pytest.mark.asyncio
    async def test_same_key_returns_existing_order_no_duplicate_submit(self):
        """Calling execute_order twice with the same idempotency_key
        should only submit one order to the exchange."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        key = "GRID-1:0:3:BUY:12345"

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        assert result1.success is True

        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        assert result2.success is True
        assert result2.order_id == result1.order_id

        # Exchange adapter should only be called ONCE
        assert adapter.place_order.call_count == 1

    @pytest.mark.asyncio
    async def test_different_keys_submit_separate_orders(self):
        """Different idempotency keys should result in separate orders."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key="GRID-1:0:3:BUY:100",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key="GRID-1:0:4:BUY:100",
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result1.success is True
        assert result2.success is True
        assert result1.order_id != result2.order_id
        assert adapter.place_order.call_count == 2

    @pytest.mark.asyncio
    async def test_no_key_always_submits(self):
        """Without idempotency_key, every call submits a new order."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result1.success is True
        assert result2.success is True
        assert result1.order_id != result2.order_id
        assert adapter.place_order.call_count == 2

    @pytest.mark.asyncio
    async def test_dedup_returns_existing_exchange_order_id(self):
        """Deduplicated result should carry the original exchange_order_id."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        key = "GRID-1:0:3:BUY:999"

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result2.exchange_order_id == result1.exchange_order_id
        assert result2.exchange_order_id == "EX-12345"

    @pytest.mark.asyncio
    async def test_rejected_order_not_deduplicated(self):
        """A REJECTED order (risk validation failure) should NOT block
        a retry with the same key — the retry should attempt again."""
        adapter = _make_adapter()
        risk_validator = _make_risk_validator(passed=False)
        engine = _make_engine(adapter=adapter, risk_validator=risk_validator)
        key = "GRID-1:0:3:BUY:555"

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        assert result1.success is False

        # Retry with same key — should attempt again (not deduplicated)
        # because the first order was REJECTED, not active/filled
        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )
        assert result2.success is False
        # Both attempts should have been made (2 orders tracked)
        assert len(engine._orders) == 2

    @pytest.mark.asyncio
    async def test_order_stores_idempotency_key(self):
        """The Order object should store the idempotency_key."""
        engine = _make_engine()
        key = "GRID-1:0:3:BUY:777"

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        order = engine.get_order(result.order_id)
        assert order is not None
        assert order.idempotency_key == key

    @pytest.mark.asyncio
    async def test_find_order_by_idempotency_key_returns_none_for_unknown(self):
        """_find_order_by_idempotency_key returns None for unknown keys."""
        engine = _make_engine()
        assert engine._find_order_by_idempotency_key("nonexistent") is None

    @pytest.mark.asyncio
    async def test_find_order_by_idempotency_key_fills_after_execution(self):
        """_find_order_by_idempotency_key finds orders after execution."""
        engine = _make_engine()
        key = "GRID-1:0:3:BUY:888"

        result = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        found = engine._find_order_by_idempotency_key(key)
        assert found is not None
        assert found.order_id == result.order_id

    @pytest.mark.asyncio
    async def test_dedup_works_for_filled_status(self):
        """Orders in FILLED status should be deduplicated."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        key = "GRID-1:0:3:BUY:111"

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        # Manually set status to FILLED to simulate exchange fill
        order = engine.get_order(result1.order_id)
        order.status = "FILLED"

        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result2.success is True
        assert result2.order_id == result1.order_id
        assert adapter.place_order.call_count == 1

    @pytest.mark.asyncio
    async def test_dedup_works_for_partially_filled_status(self):
        """Orders in PARTIALLY_FILLED status should be deduplicated."""
        adapter = _make_adapter()
        engine = _make_engine(adapter=adapter)
        key = "GRID-1:0:3:BUY:222"

        result1 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        order = engine.get_order(result1.order_id)
        order.status = "PARTIALLY_FILLED"

        result2 = await engine.execute_order(
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
            reference_price=Decimal("50000"),
            idempotency_key=key,
            identity=DEMO_IDENTITY,  # [A-H12] required
        )

        assert result2.success is True
        assert result2.order_id == result1.order_id
        assert adapter.place_order.call_count == 1
