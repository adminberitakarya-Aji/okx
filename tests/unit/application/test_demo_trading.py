"""
Tests for DemoTradingService.

Tests cover:
- Demo grid session lifecycle (create, start, pause, resume, stop)
- Emergency stop functionality
- Demo metrics collection
- Demo validation report generation
- Demo/live mode isolation
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_grid.application.services.demo_trading import (
    DemoGridSession,
    DemoMetrics,
    DemoTradingError,
    DemoTradingService,
    DemoValidationReport,
)
from trading_grid.application.services.execution_engine import ExecutionEngine, ExecutionResult
from trading_grid.application.services.grid_engine import GridEngine
from trading_grid.domain.grid.models import Blueprint, Section
from trading_grid.domain.market.models import Ticker


def create_test_blueprint(
    market_id: str = "BTC-USDT",
    total_capital: Decimal = Decimal("1000"),
) -> Blueprint:
    """Create a valid test blueprint."""
    section = Section(
        section_id=1,
        upper_price=Decimal("50000"),
        lower_price=Decimal("45000"),
        grid_count=5,
        grid_spacing_pct=Decimal("2"),
        capital_allocation_pct=Decimal("100"),
    )
    return Blueprint(
        blueprint_id="BP-TEST-001",
        market_id=market_id,
        total_capital=total_capital,
        sections=[section],
    )


def create_mock_execution_engine(mode: str = "DEMO") -> MagicMock:
    """Create a mock execution engine with adapter for price fetching."""
    engine = MagicMock(spec=ExecutionEngine)
    engine.mode = mode
    engine.execute_order = AsyncMock(
        return_value=ExecutionResult(
            success=True,
            order_id="ORD-TEST-001",
            exchange_order_id="EX-001",
        )
    )
    # Mock adapter for _get_current_price fallback
    # [D-M8] get_ticker now returns a domain Ticker model
    mock_adapter = MagicMock()
    mock_adapter.get_ticker = AsyncMock(
        return_value=Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("50000"),
        )
    )
    engine._adapter = mock_adapter
    return engine


class TestDemoMetrics:
    """Tests for DemoMetrics."""

    def test_initial_values(self) -> None:
        """Test metrics start at zero."""
        metrics = DemoMetrics()
        assert metrics.orders_submitted == 0
        assert metrics.orders_filled == 0
        assert metrics.error_count == 0

    def test_fill_rate_calculation(self) -> None:
        """Test fill rate percentage calculation."""
        metrics = DemoMetrics()
        metrics.orders_submitted = 10
        metrics.orders_filled = 8
        assert metrics.fill_rate == Decimal("80")

    def test_fill_rate_zero_orders(self) -> None:
        """Test fill rate with no orders."""
        metrics = DemoMetrics()
        assert metrics.fill_rate == Decimal("0")

    def test_avg_order_latency(self) -> None:
        """Test average order latency calculation."""
        metrics = DemoMetrics()
        metrics.orders_submitted = 4
        metrics.total_order_latency_ms = 400.0
        assert metrics.avg_order_latency_ms == 100.0

    def test_error_rate_calculation(self) -> None:
        """Test error rate percentage calculation."""
        metrics = DemoMetrics()
        metrics.orders_submitted = 20
        metrics.error_count = 2
        assert metrics.error_rate == Decimal("10")

    def test_record_order_submitted(self) -> None:
        """Test recording order submission."""
        metrics = DemoMetrics()
        metrics.record_order_submitted(latency_ms=150.0)
        assert metrics.orders_submitted == 1
        assert metrics.total_order_latency_ms == 150.0

    def test_record_order_filled(self) -> None:
        """Test recording order fill."""
        metrics = DemoMetrics()
        metrics.record_order_filled()
        assert metrics.orders_filled == 1

    def test_record_order_rejected(self) -> None:
        """Test recording order rejection."""
        metrics = DemoMetrics()
        metrics.record_order_rejected("API_ERROR")
        assert metrics.orders_rejected == 1
        assert metrics.error_count == 1
        assert metrics.errors_by_category["API_ERROR"] == 1

    def test_record_reconciliation(self) -> None:
        """Test recording reconciliation."""
        metrics = DemoMetrics()
        metrics.record_reconciliation(mismatches=0)
        assert metrics.reconciliation_count == 1
        assert metrics.reconciliation_mismatches == 0

        metrics.record_reconciliation(mismatches=2)
        assert metrics.reconciliation_count == 2
        assert metrics.reconciliation_mismatches == 2

    def test_record_emergency_stop(self) -> None:
        """Test recording emergency stop."""
        metrics = DemoMetrics()
        metrics.record_emergency_stop()
        assert metrics.emergency_stops == 1

    def test_record_pause_resume(self) -> None:
        """Test recording pause/resume cycle."""
        metrics = DemoMetrics()
        metrics.record_pause_resume()
        assert metrics.pause_resume_cycles == 1

    def test_to_dict(self) -> None:
        """Test metrics serialization."""
        metrics = DemoMetrics()
        metrics.orders_submitted = 5
        metrics.orders_filled = 4

        data = metrics.to_dict()
        assert data["orders_submitted"] == 5
        assert data["orders_filled"] == 4
        assert "fill_rate_pct" in data
        assert "started_at" in data


class TestDemoGridSession:
    """Tests for DemoGridSession."""

    @pytest.fixture
    def session(self) -> DemoGridSession:
        """Create a demo session for testing."""
        grid_engine = GridEngine()
        blueprint = create_test_blueprint()
        grid_runtime = grid_engine.create_grid(blueprint, environment="DEMO")

        return DemoGridSession(
            session_id="DEMO-TEST-001",
            grid_runtime=grid_runtime,
        )

    def test_initial_status(self, session: DemoGridSession) -> None:
        """Test session starts in CREATED status."""
        assert session.status == "CREATED"
        assert session.started_at is None
        assert session.stopped_at is None

    def test_market_id_property(self, session: DemoGridSession) -> None:
        """Test market_id property."""
        assert session.market_id == "BTC-USDT"

    def test_duration_not_started(self, session: DemoGridSession) -> None:
        """Test duration is None when not started."""
        assert session.duration_seconds is None

    def test_add_note(self, session: DemoGridSession) -> None:
        """Test adding notes to session."""
        session.add_note("Test note")
        assert len(session.notes) == 1
        assert "Test note" in session.notes[0]


class TestDemoTradingService:
    """Tests for DemoTradingService."""

    @pytest.fixture
    def service(self) -> DemoTradingService:
        """Create demo trading service for testing."""
        grid_engine = GridEngine()
        execution_engine = create_mock_execution_engine(mode="DEMO")
        return DemoTradingService(
            grid_engine=grid_engine,
            execution_engine=execution_engine,
        )

    def test_requires_demo_mode(self) -> None:
        """Test service requires DEMO mode."""
        grid_engine = GridEngine()
        execution_engine = create_mock_execution_engine(mode="LIVE")

        with pytest.raises(DemoTradingError) as exc_info:
            DemoTradingService(
                grid_engine=grid_engine,
                execution_engine=execution_engine,
            )
        assert "DEMO mode" in str(exc_info.value)

    def test_environment_property(self, service: DemoTradingService) -> None:
        """Test environment is DEMO."""
        assert service.environment == "DEMO"

    def test_create_demo_grid(self, service: DemoTradingService) -> None:
        """Test creating a demo grid session."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint, notes="Test session")

        assert session.session_id.startswith("DEMO-")
        assert session.status == "CREATED"
        assert session.grid_runtime is not None
        assert len(session.notes) == 2  # Custom note + creation note

    def test_create_demo_grid_with_user_id(self, service: DemoTradingService) -> None:
        """Test creating a demo grid session with user_id."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint, user_id="usr_1")

        assert session.user_id == "usr_1"
        assert session.grid_runtime.user_id == "usr_1"

    @pytest.mark.asyncio
    async def test_start_demo_grid(self, service: DemoTradingService) -> None:
        """Test starting a demo grid."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        started = await service.start_demo_grid(session.session_id)
        assert started.status == "RUNNING"
        assert started.started_at is not None

    @pytest.mark.asyncio
    async def test_start_demo_grid_not_found(self, service: DemoTradingService) -> None:
        """Test starting non-existent session raises error."""
        with pytest.raises(DemoTradingError) as exc_info:
            await service.start_demo_grid("NONEXISTENT")
        assert "not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pause_demo_grid(self, service: DemoTradingService) -> None:
        """Test pausing a demo grid."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        paused = service.pause_demo_grid(session.session_id)
        assert paused.status == "PAUSED"
        assert paused.metrics.pause_resume_cycles == 1

    @pytest.mark.asyncio
    async def test_resume_demo_grid(self, service: DemoTradingService) -> None:
        """Test resuming a paused demo grid."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)
        service.pause_demo_grid(session.session_id)

        resumed = service.resume_demo_grid(session.session_id)
        assert resumed.status == "RUNNING"

    @pytest.mark.asyncio
    async def test_stop_demo_grid(self, service: DemoTradingService) -> None:
        """Test stopping a demo grid."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        stopped = service.stop_demo_grid(session.session_id, reason="Test complete")
        assert stopped.status == "STOPPED"
        assert stopped.stopped_at is not None

    @pytest.mark.asyncio
    async def test_emergency_stop_demo_grid(self, service: DemoTradingService) -> None:
        """Test emergency stopping a demo grid."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        stopped = service.emergency_stop_demo_grid(session.session_id, reason="Critical error")
        assert stopped.status == "EMERGENCY_STOPPED"
        assert stopped.metrics.emergency_stops == 1

    @pytest.mark.asyncio
    async def test_emergency_stop_all(self, service: DemoTradingService) -> None:
        """Test emergency stopping all demo grids."""
        bp1 = create_test_blueprint(market_id="BTC-USDT")
        bp2 = create_test_blueprint(market_id="ETH-USDT")

        session1 = service.create_demo_grid(bp1)
        session2 = service.create_demo_grid(bp2)
        await service.start_demo_grid(session1.session_id)
        await service.start_demo_grid(session2.session_id)

        stopped = service.emergency_stop_all(reason="System emergency")
        assert len(stopped) == 2
        assert session1.status == "EMERGENCY_STOPPED"
        assert session2.status == "EMERGENCY_STOPPED"

    @pytest.mark.asyncio
    async def test_active_sessions(self, service: DemoTradingService) -> None:
        """Test getting active sessions."""
        bp1 = create_test_blueprint(market_id="BTC-USDT")
        bp2 = create_test_blueprint(market_id="ETH-USDT")

        session1 = service.create_demo_grid(bp1)
        service.create_demo_grid(bp2)
        await service.start_demo_grid(session1.session_id)

        active = service.active_sessions
        assert len(active) == 2  # CREATED and RUNNING are both active

    @pytest.mark.asyncio
    async def test_execute_demo_order(self, service: DemoTradingService) -> None:
        """Test executing an order in demo mode.

        Note: start_demo_grid now executes an initial entry order,
        so orders_submitted will be 2 (1 initial + 1 manual).
        """
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        # Initial entry already submitted 1 order
        initial_orders = session.metrics.orders_submitted

        result = await service.execute_demo_order(
            session_id=session.session_id,
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
        )

        assert result.success is True
        # One more order submitted on top of initial entry
        assert session.metrics.orders_submitted == initial_orders + 1

    @pytest.mark.asyncio
    async def test_execute_demo_order_passes_user_id(self, service: DemoTradingService) -> None:
        """Test execute_demo_order passes user_id to execution engine."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint, user_id="usr_1")
        await service.start_demo_grid(session.session_id)

        await service.execute_demo_order(
            session_id=session.session_id,
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.01"),
        )

        # Verify user_id was passed to execute_order
        call_kwargs = service._execution_engine.execute_order.call_args.kwargs
        assert call_kwargs["user_id"] == "usr_1"

    @pytest.mark.asyncio
    async def test_execute_order_requires_running(self, service: DemoTradingService) -> None:
        """Test order execution requires RUNNING status."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        with pytest.raises(DemoTradingError) as exc_info:
            await service.execute_demo_order(
                session_id=session.session_id,
                market_id="BTC-USDT",
                side="BUY",
                quantity=Decimal("0.01"),
            )
        assert "RUNNING" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_session_metrics(self, service: DemoTradingService) -> None:
        """Test getting session metrics."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        metrics = service.get_session_metrics(session.session_id)
        assert metrics is not None
        assert metrics.grid_state_transitions == 1

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, service: DemoTradingService) -> None:
        """Test aggregating metrics from all sessions."""
        bp1 = create_test_blueprint(market_id="BTC-USDT")
        bp2 = create_test_blueprint(market_id="ETH-USDT")

        session1 = service.create_demo_grid(bp1)
        session2 = service.create_demo_grid(bp2)
        await service.start_demo_grid(session1.session_id)
        await service.start_demo_grid(session2.session_id)

        total = service.get_all_metrics()
        assert total.grid_state_transitions == 2

    @pytest.mark.asyncio
    async def test_generate_validation_report_not_ready(self, service: DemoTradingService) -> None:
        """Test validation report when not ready for live.

        [A-M3] After the readiness report fix, "Emergency stop not tested" is
        no longer a blocking issue — it's tracked as informational metadata.
        The blocking issue here is insufficient orders.
        """
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        report = service.generate_validation_report()

        assert report.ready_for_live is False
        assert len(report.issues_found) > 0
        # The actual blocking issue: insufficient orders submitted
        assert any("Insufficient orders submitted" in issue for issue in report.issues_found)

    @pytest.mark.asyncio
    async def test_generate_validation_report_ready(self, service: DemoTradingService) -> None:
        """Test validation report when ready for live."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        # Simulate sufficient orders
        for _ in range(10):
            session.metrics.record_order_submitted(100.0)
            session.metrics.record_order_filled()

        # Test pause/resume
        service.pause_demo_grid(session.session_id)
        service.resume_demo_grid(session.session_id)

        # Test emergency stop
        service.emergency_stop_demo_grid(session.session_id, reason="Test")

        report = service.generate_validation_report()

        assert report.ready_for_live is True
        assert len(report.issues_found) == 0

    @pytest.mark.asyncio
    async def test_get_service_status(self, service: DemoTradingService) -> None:
        """Test service status summary."""
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)
        await service.start_demo_grid(session.session_id)

        status = service.get_service_status()
        assert status["environment"] == "DEMO"
        assert status["total_sessions"] == 1
        assert status["active_sessions"] == 1


class TestDemoValidationReport:
    """Tests for DemoValidationReport."""

    def test_evaluate_readiness_passes_without_emergency_stop(self) -> None:
        """[A-M3] Emergency stop is no longer a blocking readiness criterion.

        After the A-M3 fix, "Emergency stop not tested" is tracked as
        informational metadata rather than a blocking issue, so readiness
        passes when all other criteria are met.
        """
        from datetime import UTC, datetime

        metrics = DemoMetrics()
        metrics.orders_submitted = 20
        metrics.orders_filled = 20
        metrics.pause_resume_cycles = 1

        report = DemoValidationReport(
            report_id="REPORT-TEST",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            sessions=[],
            total_metrics=metrics,
        )

        ready = report.evaluate_readiness()
        assert ready is True
        assert "Emergency stop not tested" not in report.issues_found

    def test_evaluate_readiness_fails_with_reconciliation_mismatch(self) -> None:
        """Test readiness fails with reconciliation mismatches."""
        from datetime import UTC, datetime

        metrics = DemoMetrics()
        metrics.orders_submitted = 20
        metrics.orders_filled = 20
        metrics.emergency_stops = 1
        metrics.pause_resume_cycles = 1
        metrics.reconciliation_mismatches = 1

        report = DemoValidationReport(
            report_id="REPORT-TEST",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            sessions=[],
            total_metrics=metrics,
        )

        ready = report.evaluate_readiness()
        assert ready is False
        assert any("Reconciliation" in issue for issue in report.issues_found)

    def test_evaluate_readiness_passes(self) -> None:
        """Test readiness passes with all criteria met."""
        from datetime import UTC, datetime

        metrics = DemoMetrics()
        metrics.orders_submitted = 20
        metrics.orders_filled = 20
        metrics.emergency_stops = 1
        metrics.pause_resume_cycles = 1
        metrics.reconciliation_mismatches = 0

        report = DemoValidationReport(
            report_id="REPORT-TEST",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            sessions=[],
            total_metrics=metrics,
        )

        ready = report.evaluate_readiness()
        assert ready is True
        assert len(report.issues_found) == 0

    def test_to_dict(self) -> None:
        """Test report serialization."""
        from datetime import UTC, datetime

        metrics = DemoMetrics()
        report = DemoValidationReport(
            report_id="REPORT-TEST",
            period_start=datetime.now(UTC),
            period_end=datetime.now(UTC),
            sessions=[],
            total_metrics=metrics,
        )

        data = report.to_dict()
        assert data["report_id"] == "REPORT-TEST"
        assert "total_metrics" in data
        assert "ready_for_live" in data


# ---------------------------------------------------------------------------
# Immediate First Entry Tests
# ---------------------------------------------------------------------------


class TestImmediateFirstEntry:
    """Tests for IMMEDIATE FIRST ENTRY in start_demo_grid().

    The immediate first entry executes a MARKET BUY at the anchor level
    (Section 1, Level 0) when the grid starts. This provides an initial
    position for the grid to trade against.

    Key behaviors:
    - Anchor level is blueprint.sections[0].levels[0]
    - Idempotency key: f"{grid_id}:INITIAL_ENTRY" (no time-bucket)
    - On success: anchor marked FILLED with actual fill price
    - On failure: grid still starts without initial position
    """

    @pytest.fixture
    def service(self) -> DemoTradingService:
        """Create demo trading service for testing."""
        grid_engine = GridEngine()
        execution_engine = create_mock_execution_engine(mode="DEMO")
        return DemoTradingService(
            grid_engine=grid_engine,
            execution_engine=execution_engine,
        )

    @pytest.mark.asyncio
    async def test_immediate_first_entry_success(self, service: DemoTradingService) -> None:
        """Market BUY occurs once at anchor level, anchor marked FILLED.

        This is the primary test for immediate first entry:
        - Order is executed via execution engine
        - Anchor level (Section 1, Level 0) is marked FILLED
        - entry_price is set to the execution price
        """
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        started = await service.start_demo_grid(session.session_id)

        # Verify order was executed
        assert started.status == "RUNNING"
        assert started.metrics.orders_submitted == 1

        # Verify anchor level is marked FILLED
        anchor = started.grid_runtime.blueprint.sections[0].levels[0]
        assert anchor.is_filled
        assert anchor.status == "FILLED"
        assert anchor.position_quantity > 0
        assert anchor.entry_price is not None

        # Verify execution engine was called with correct parameters
        call_kwargs = service._execution_engine.execute_order.call_args.kwargs
        assert call_kwargs["side"] == "BUY"
        assert call_kwargs["price"] is None  # MARKET order
        assert call_kwargs["metadata"]["trigger_type"] == "initial_entry"

    @pytest.mark.asyncio
    async def test_immediate_first_entry_idempotent(self, service: DemoTradingService) -> None:
        """Calling start_demo_grid twice should not double-execute initial entry.

        The idempotency key f"{grid_id}:INITIAL_ENTRY" ensures that
        retries of start_demo_grid do not submit duplicate orders.
        """
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        # First start — executes initial entry
        await service.start_demo_grid(session.session_id)

        # Verify idempotency key was passed
        call_kwargs = service._execution_engine.execute_order.call_args.kwargs
        idempotency_key = call_kwargs["idempotency_key"]
        assert idempotency_key is not None
        assert ":INITIAL_ENTRY" in idempotency_key
        assert "GRID-" in idempotency_key

        # Note: In a real scenario, calling start_demo_grid again would
        # raise GridEngineError because grid is already RUNNING.
        # The idempotency is enforced by ExecutionEngine deduplication.

    @pytest.mark.asyncio
    async def test_immediate_entry_respects_risk_validator(self) -> None:
        """If risk check fails, anchor stays PENDING, grid still starts.

        Initial entry failure is NOT a fatal error — the grid can still
        start and trade on subsequent crossings.
        """
        grid_engine = GridEngine()
        execution_engine = create_mock_execution_engine(mode="DEMO")

        # Make execution fail (simulating risk validation failure)
        execution_engine.execute_order = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                order_id="ORD-REJECTED",
                error_message="Risk validation failed: insufficient balance",
            )
        )

        service = DemoTradingService(
            grid_engine=grid_engine,
            execution_engine=execution_engine,
        )

        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        # Grid should still start despite initial entry failure
        started = await service.start_demo_grid(session.session_id)

        assert started.status == "RUNNING"
        assert started.started_at is not None

        # Anchor level should remain PENDING (not filled)
        anchor = started.grid_runtime.blueprint.sections[0].levels[0]
        assert not anchor.is_filled
        assert anchor.status == "PENDING"

        # Metrics should record the rejection
        assert started.metrics.orders_rejected == 1

        # Session note should indicate no initial entry
        assert any("without initial entry" in note for note in started.notes)

    @pytest.mark.asyncio
    async def test_immediate_entry_uses_current_price(self, service: DemoTradingService) -> None:
        """Initial entry should use current real-time price, not anchor.price.

        The anchor.price is the blueprint design price. The actual entry
        uses the current market price (which may differ due to slippage
        or time delay between blueprint creation and grid start).
        """
        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        await service.start_demo_grid(session.session_id)

        # Verify reference_price was passed (current market price)
        call_kwargs = service._execution_engine.execute_order.call_args.kwargs
        assert call_kwargs["reference_price"] is not None
        assert call_kwargs["reference_price"] == Decimal("50000")  # From mock ticker

    @pytest.mark.asyncio
    async def test_immediate_entry_no_price_graceful(self) -> None:
        """If price cannot be fetched, grid starts without initial entry."""
        grid_engine = GridEngine()
        execution_engine = create_mock_execution_engine(mode="DEMO")

        # Make ticker fetch fail
        execution_engine._adapter.get_ticker = AsyncMock(side_effect=Exception("API error"))

        service = DemoTradingService(
            grid_engine=grid_engine,
            execution_engine=execution_engine,
        )

        blueprint = create_test_blueprint()
        session = service.create_demo_grid(blueprint)

        # Grid should still start despite price fetch failure
        started = await service.start_demo_grid(session.session_id)

        assert started.status == "RUNNING"

        # Anchor level should remain PENDING
        anchor = started.grid_runtime.blueprint.sections[0].levels[0]
        assert not anchor.is_filled
