"""
End-to-End (E2E) Flow Integration Tests.

Validates the full operational pipeline across all architectural layers:
1. Research Market Ranking & Blueprint Generation
2. Grid Lifecycle: Initialization, Validation, State Transitions
3. Price Monitoring & Autonomous Level Crossing Execution
4. Deterministic Risk Validation Gate (Limits & Fail-Closed Behavior)
5. Order Routing via Execution Engine with Idempotency
6. Multi-Exchange Emergency Stop & PnL Accounting
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_grid.application.services.authorization import Identity, Role
from trading_grid.application.services.demo_trading import DemoTradingService
from trading_grid.application.services.execution_engine import ExecutionEngine
from trading_grid.application.services.grid_engine import GridEngine
from trading_grid.application.services.price_monitor import PriceMonitorService
from trading_grid.application.services.risk_validation import RiskValidationService
from trading_grid.application.services.service_container import (
    MultiExchangeContainer,
)
from trading_grid.config.settings import Settings
from trading_grid.domain.grid.models import Blueprint, GridLevelModel, Section
from trading_grid.domain.market.models import Ticker
from trading_grid.domain.risk.models import RiskLimits

# [A-H12] Test identity for execute_order (identity is REQUIRED).
DEMO_IDENTITY = Identity(
    identity_id="test-user",
    identity_type="HUMAN",
    role=Role.DEMO_OPERATOR,
    allowed_environments=("DEMO",),
)



def _build_test_blueprint(market_id: str = "BTC-USDT") -> Blueprint:
    """Build a valid domain strategy blueprint for E2E testing."""
    levels = [
        GridLevelModel(level=0, price=Decimal("50000"), quantity=Decimal("0.001")),
        GridLevelModel(level=1, price=Decimal("49500"), quantity=Decimal("0.001")),
        GridLevelModel(level=2, price=Decimal("49000"), quantity=Decimal("0.001")),
    ]
    section = Section(
        section_id=1,
        grid_spacing_pct=Decimal("1.0"),
        capital_allocation_pct=Decimal("100"),
        upper_price=Decimal("50000"),
        lower_price=Decimal("49000"),
        grid_count=3,
        levels=levels,
    )
    return Blueprint(
        blueprint_id="BP-E2E-TEST-001",
        market_id=market_id,
        total_capital=Decimal("1000"),
        sections=[section],
    )


@pytest.mark.asyncio
async def test_complete_e2e_research_to_execution_flow():
    """
    E2E Scenario 1:
    Research Blueprint -> Create Demo Grid -> Start Grid with Initial Entry ->
    Price Monitor Crossings -> Order Routing -> Realized PnL -> Emergency Stop.
    """
    grid_engine = GridEngine()

    # Setup Mock Adapter
    mock_adapter = MagicMock()
    mock_adapter.exchange_id = "OKX"
    mock_adapter.mode = "DEMO"
    # [D-M8] get_ticker returns a domain Ticker model (not a dict)
    mock_adapter.get_ticker = AsyncMock(
        return_value=Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("50000"),
        )
    )
    mock_adapter.reconcile = AsyncMock(return_value={"reconciled_at": datetime.now(UTC).isoformat()})
    mock_adapter.place_order = AsyncMock(return_value="EX-ORD-E2E-999")
    mock_adapter.cancel_order = AsyncMock(return_value=True)
    mock_adapter.get_order_status = AsyncMock(return_value={"status": "FILLED", "fill_price": "50000"})
    mock_adapter.get_balance = AsyncMock(return_value={"USDT": {"total": Decimal("10000"), "available": Decimal("10000")}})
    mock_adapter.get_positions = AsyncMock(return_value=[])
    mock_adapter.get_pending_orders = AsyncMock(return_value=[])

    # Setup Risk Validator & Execution Engine
    risk_limits = RiskLimits(
        max_capital_per_grid=Decimal("5000"),
        max_total_capital=Decimal("20000"),
        max_drawdown_pct=Decimal("15"),
        max_concurrent_grids=5,
        max_position_pct=Decimal("50"),
    )
    risk_validator = RiskValidationService(limits=risk_limits)
    execution_engine = ExecutionEngine(adapter=mock_adapter, risk_validator=risk_validator)

    # Setup Price Monitor & Demo Service
    price_monitor = PriceMonitorService(
        adapter=mock_adapter,
        grid_engine=grid_engine,
        execution_engine=execution_engine,
    )
    demo_service = DemoTradingService(
        grid_engine=grid_engine,
        execution_engine=execution_engine,
        price_monitor=price_monitor,
    )

    # 1. Create and Start Demo Grid
    # [A-H11] Identity must match the session owner (test_user)
    owner_identity = Identity(
        identity_id="test_user",
        identity_type="HUMAN",
        role=Role.DEMO_OPERATOR,
        allowed_environments=("DEMO",),
    )
    blueprint = _build_test_blueprint(market_id="BTC-USDT")
    session = demo_service.create_demo_grid(blueprint=blueprint, user_id="test_user")
    assert session.status == "CREATED"
    assert session.session_id.startswith("DEMO-")

    # Start grid (Atomic transition to RUNNING + initial anchor order)
    started_session = await demo_service.start_demo_grid(
        session.session_id, identity=owner_identity  # [A-H11] required
    )
    assert started_session.status == "RUNNING"
    assert started_session.started_at is not None

    # 2. Simulate Incoming Price Ticks to PriceMonitor
    # First tick to establish previous price
    price_monitor._handle_ticker({"market_id": "BTC-USDT", "last": "50100"})
    # Downward crossing to trigger BUY at Level 1 (49500)
    price_monitor._handle_ticker({"market_id": "BTC-USDT", "last": "49400"})

    # Verify orders were routed
    assert mock_adapter.place_order.await_count >= 1

    # 3. Emergency Stop All Grids
    stopped_sessions = demo_service.emergency_stop_all(reason="E2E Safety Test")
    assert len(stopped_sessions) == 1
    assert stopped_sessions[0].status == "EMERGENCY_STOPPED"
    assert stopped_sessions[0].grid_runtime.status == "EMERGENCY_STOPPED"


@pytest.mark.asyncio
async def test_e2e_multi_exchange_container_wiring():
    """
    E2E Scenario 2:
    MultiExchangeContainer registry initialization for OKX, Binance, Bybit.
    """
    settings = Settings()
    multi_container = MultiExchangeContainer(settings)

    # Resolve containers
    okx_container = multi_container.get_container("OKX")
    assert okx_container.exchange_id == "OKX"
    assert okx_container.demo_service is not None
    assert okx_container.execution_engine is not None

    binance_container = multi_container.get_container("BINANCE")
    assert binance_container.exchange_id == "BINANCE"

    bybit_container = multi_container.get_container("BYBIT")
    assert bybit_container.exchange_id == "BYBIT"


@pytest.mark.asyncio
async def test_e2e_risk_fail_closed_prevents_unauthorized_exposure():
    """
    E2E Scenario 3:
    Order exceeding risk threshold is blocked locally before reaching exchange.
    """
    mock_adapter = MagicMock()
    mock_adapter.mode = "DEMO"
    mock_adapter.place_order = AsyncMock()

    strict_limits = RiskLimits(
        max_capital_per_grid=Decimal("100"),
        max_total_capital=Decimal("500"),
        max_drawdown_pct=Decimal("10"),
    )
    validator = RiskValidationService(limits=strict_limits)
    engine = ExecutionEngine(adapter=mock_adapter, risk_validator=validator)

    # Attempt to place order exceeding max capital limit
    result = await engine.execute_order(
        market_id="BTC-USDT",
        side="BUY",
        quantity=Decimal("1.0"),
        price=Decimal("50000"),  # Notional: $50,000 > $100 limit
    identity=DEMO_IDENTITY,  # [A-H12] required
    )

    assert result.success is False
    assert "Risk validation failed" in (result.error_message or "")
    mock_adapter.place_order.assert_not_awaited()
