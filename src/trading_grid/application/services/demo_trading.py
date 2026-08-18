"""
Demo Trading Service — Orchestrates demo grid lifecycle.

This module provides:
- DemoTradingService: Full demo grid lifecycle management
- Demo grid creation, start, pause, resume, stop
- Demo metrics collection
- Demo validation report generation

Key domain rules:
1. Demo trading uses separate API keys from live
2. Demo trading requires x-simulated-trading: 1 header
3. Demo and live environments are fully isolated
4. Demo execution results are NOT used for ML training
5. Demo P&L is operational validation, not economic validation
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import structlog

from trading_grid.application.services.execution_engine import ExecutionEngine, ExecutionResult
from trading_grid.application.services.grid_engine import GridEngine, GridEngineError, GridRuntime
from trading_grid.application.services.price_monitor import PriceMonitorService
from trading_grid.domain.grid.models import Blueprint
from trading_grid.domain.shared.types import ExecutionMode, MarketId

logger = structlog.get_logger()


@dataclass
class DemoMetrics:
    """
    Operational metrics collected during demo trading.

    These metrics validate operational readiness, not strategy performance.
    """

    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    total_order_latency_ms: float = 0.0
    ws_reconnect_count: int = 0
    reconciliation_count: int = 0
    reconciliation_mismatches: int = 0
    error_count: int = 0
    errors_by_category: dict[str, int] = field(default_factory=dict)
    grid_state_transitions: int = 0
    emergency_stops: int = 0
    pause_resume_cycles: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def fill_rate(self) -> Decimal:
        """Calculate fill rate percentage."""
        if self.orders_submitted == 0:
            return Decimal("0")
        return Decimal(self.orders_filled) / Decimal(self.orders_submitted) * 100

    @property
    def avg_order_latency_ms(self) -> float:
        """Calculate average order latency."""
        if self.orders_submitted == 0:
            return 0.0
        return self.total_order_latency_ms / self.orders_submitted

    @property
    def error_rate(self) -> Decimal:
        """Calculate error rate percentage."""
        if self.orders_submitted == 0:
            return Decimal("0")
        return Decimal(self.error_count) / Decimal(self.orders_submitted) * 100

    def record_order_submitted(self, latency_ms: float = 0.0) -> None:
        """Record an order submission."""
        self.orders_submitted += 1
        self.total_order_latency_ms += latency_ms
        self.last_updated_at = datetime.now(UTC)

    def record_order_filled(self) -> None:
        """Record an order fill."""
        self.orders_filled += 1
        self.last_updated_at = datetime.now(UTC)

    def record_order_rejected(self, category: str = "UNKNOWN") -> None:
        """Record an order rejection."""
        self.orders_rejected += 1
        self.error_count += 1
        self.errors_by_category[category] = self.errors_by_category.get(category, 0) + 1
        self.last_updated_at = datetime.now(UTC)

    def record_order_cancelled(self) -> None:
        """Record an order cancellation."""
        self.orders_cancelled += 1
        self.last_updated_at = datetime.now(UTC)

    def record_reconciliation(self, mismatches: int = 0) -> None:
        """Record a reconciliation event."""
        self.reconciliation_count += 1
        self.reconciliation_mismatches += mismatches
        self.last_updated_at = datetime.now(UTC)

    def record_ws_reconnect(self) -> None:
        """Record a WebSocket reconnection."""
        self.ws_reconnect_count += 1
        self.last_updated_at = datetime.now(UTC)

    def record_error(self, category: str) -> None:
        """Record an error."""
        self.error_count += 1
        self.errors_by_category[category] = self.errors_by_category.get(category, 0) + 1
        self.last_updated_at = datetime.now(UTC)

    def record_state_transition(self) -> None:
        """Record a grid state transition."""
        self.grid_state_transitions += 1
        self.last_updated_at = datetime.now(UTC)

    def record_emergency_stop(self) -> None:
        """Record an emergency stop."""
        self.emergency_stops += 1
        self.last_updated_at = datetime.now(UTC)

    def record_pause_resume(self) -> None:
        """Record a pause/resume cycle."""
        self.pause_resume_cycles += 1
        self.last_updated_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "orders_submitted": self.orders_submitted,
            "orders_filled": self.orders_filled,
            "orders_rejected": self.orders_rejected,
            "orders_cancelled": self.orders_cancelled,
            "fill_rate_pct": str(self.fill_rate),
            "avg_order_latency_ms": self.avg_order_latency_ms,
            "ws_reconnect_count": self.ws_reconnect_count,
            "reconciliation_count": self.reconciliation_count,
            "reconciliation_mismatches": self.reconciliation_mismatches,
            "error_count": self.error_count,
            "error_rate_pct": str(self.error_rate),
            "errors_by_category": self.errors_by_category,
            "grid_state_transitions": self.grid_state_transitions,
            "emergency_stops": self.emergency_stops,
            "pause_resume_cycles": self.pause_resume_cycles,
            "started_at": self.started_at.isoformat(),
            "last_updated_at": self.last_updated_at.isoformat(),
        }


@dataclass
class DemoGridSession:
    """
    A demo grid trading session.

    Tracks the complete lifecycle of a demo grid.
    """

    session_id: str
    grid_runtime: GridRuntime
    user_id: str | None = None
    metrics: DemoMetrics = field(default_factory=DemoMetrics)
    status: str = "CREATED"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def market_id(self) -> MarketId:
        """Get market ID."""
        return self.grid_runtime.market_id

    @property
    def duration_seconds(self) -> float | None:
        """Get session duration in seconds."""
        if self.started_at is None:
            return None
        end = self.stopped_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def add_note(self, note: str) -> None:
        """Add a note to the session."""
        timestamp = datetime.now(UTC).isoformat()
        self.notes.append(f"[{timestamp}] {note}")


@dataclass
class DemoValidationReport:
    """
    Demo validation report generated after demo period.

    This report validates operational readiness for live trading.
    """

    report_id: str
    period_start: datetime
    period_end: datetime
    sessions: list[DemoGridSession]
    total_metrics: DemoMetrics
    issues_found: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    ready_for_live: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def evaluate_readiness(self) -> bool:
        """
        Evaluate if demo validation passes for live trading.

        Criteria:
        - Zero reconciliation mismatches
        - Zero unhandled errors
        - Emergency stop tested
        - Pause/resume tested
        - Minimum orders executed
        """
        issues = []

        if self.total_metrics.reconciliation_mismatches > 0:
            issues.append(
                f"Reconciliation mismatches: {self.total_metrics.reconciliation_mismatches}"
            )

        if self.total_metrics.emergency_stops == 0:
            issues.append("Emergency stop not tested")

        if self.total_metrics.pause_resume_cycles == 0:
            issues.append("Pause/resume not tested")

        if self.total_metrics.orders_submitted < 10:
            issues.append(
                f"Insufficient orders submitted: {self.total_metrics.orders_submitted} (min 10)"
            )

        if self.total_metrics.error_rate > Decimal("5"):
            issues.append(f"Error rate too high: {self.total_metrics.error_rate}%")

        self.issues_found = issues
        self.ready_for_live = len(issues) == 0

        if self.ready_for_live:
            self.recommendations.append("Demo validation passed. Ready for live trading approval.")
        else:
            self.recommendations.append("Resolve issues before proceeding to live trading.")

        return self.ready_for_live

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "report_id": self.report_id,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "sessions_count": len(self.sessions),
            "total_metrics": self.total_metrics.to_dict(),
            "issues_found": self.issues_found,
            "recommendations": self.recommendations,
            "ready_for_live": self.ready_for_live,
            "generated_at": self.generated_at.isoformat(),
        }


class DemoTradingService:
    """
    Demo Trading Service.

    Orchestrates the complete demo grid lifecycle:
    - Create demo grid from blueprint
    - Start/pause/resume/stop demo grid
    - Execute orders in demo mode
    - Collect operational metrics
    - Generate validation report

    The service ensures demo trading is isolated from live trading
    and collects all metrics needed for demo-to-live transition.
    """

    def __init__(
        self,
        grid_engine: GridEngine,
        execution_engine: ExecutionEngine,
        price_monitor: PriceMonitorService | None = None,
    ) -> None:
        """
        Initialize demo trading service.

        Args:
            grid_engine: Grid engine for state management
            execution_engine: Execution engine for order management
            price_monitor: Price monitor for grid execution loop (optional)
        """
        self._grid_engine = grid_engine
        self._execution_engine = execution_engine
        self._price_monitor = price_monitor
        self._sessions: dict[str, DemoGridSession] = {}
        self._environment: ExecutionMode = "DEMO"

        # Verify we're in demo mode
        if execution_engine.mode != "DEMO":
            raise DemoTradingError(
                f"DemoTradingService requires DEMO mode. Current mode: {execution_engine.mode}"
            )

    @property
    def environment(self) -> ExecutionMode:
        """Get execution environment."""
        return self._environment

    @property
    def active_sessions(self) -> list[DemoGridSession]:
        """Get all active demo sessions."""
        return [s for s in self._sessions.values() if s.status in ("CREATED", "RUNNING", "PAUSED")]

    def create_demo_grid(
        self,
        blueprint: Blueprint,
        notes: str | None = None,
        user_id: str | None = None,
    ) -> DemoGridSession:
        """
        Create a new demo grid session.

        Args:
            blueprint: The strategy blueprint to execute
            notes: Optional notes for the session
            user_id: User identifier who owns this grid (for per-user limits)

        Returns:
            Created DemoGridSession

        Raises:
            DemoTradingError: If grid creation fails
        """
        try:
            grid_runtime = self._grid_engine.create_grid(
                blueprint=blueprint,
                environment=self._environment,
                user_id=user_id,
            )
        except GridEngineError as e:
            raise DemoTradingError(f"Failed to create demo grid: {e}") from e

        session_id = f"DEMO-{uuid4().hex[:12].upper()}"
        session = DemoGridSession(
            session_id=session_id,
            grid_runtime=grid_runtime,
            user_id=user_id,
        )

        if notes:
            session.add_note(notes)

        session.add_note(f"Demo grid created for {blueprint.market_id}")

        self._sessions[session_id] = session

        logger.info(
            "demo_grid_created",
            session_id=session_id,
            grid_id=grid_runtime.grid_id,
            market_id=blueprint.market_id,
            environment=self._environment,
        )

        return session

    async def start_demo_grid(self, session_id: str) -> DemoGridSession:
        """
        Start a demo grid session with IMMEDIATE FIRST ENTRY.

        Execution flow:
        1. IMMEDIATE FIRST ENTRY — market BUY at anchor level
           (Section 1, Level 0) using current real-time price.
           Idempotency key: f"{grid_id}:INITIAL_ENTRY" (no time-bucket,
           this order should only happen once per grid lifetime).
        2. grid_engine.start_grid() — transition to RUNNING
        3. price_monitor.monitor_grid() — wire crossing detection

        If the initial entry fails (e.g., risk validation), the grid
        still starts but without an initial position. This is NOT a
        fatal error — the grid can still trade on subsequent crossings.

        Args:
            session_id: Session to start

        Returns:
            Updated DemoGridSession

        Raises:
            DemoTradingError: If session not found or cannot start
        """
        session = self._get_session(session_id)

        # STEP 1: Start the grid (transition to RUNNING first for session state atomicity)
        try:
            self._grid_engine.start_grid(session.grid_runtime.grid_id)
        except GridEngineError as e:
            raise DemoTradingError(f"Failed to start demo grid: {e}") from e

        session.status = "RUNNING"
        session.started_at = datetime.now(UTC)
        session.metrics.record_state_transition()

        # STEP 2: IMMEDIATE FIRST ENTRY (market BUY at anchor level)
        initial_entry_result = await self._execute_initial_entry(session)

        if initial_entry_result is not None and initial_entry_result.success:
            session.add_note("Demo grid started with initial entry position")
        else:
            session.add_note("Demo grid started without initial entry (will trade on crossings)")

        # STEP 3: Wire price monitor to this grid for autonomous execution
        if self._price_monitor is not None:
            self._price_monitor.monitor_grid(session.grid_runtime)
            logger.info(
                "demo_grid_monitoring_started",
                session_id=session_id,
                grid_id=session.grid_runtime.grid_id,
            )

        logger.info(
            "demo_grid_started",
            session_id=session_id,
            grid_id=session.grid_runtime.grid_id,
            initial_entry_success=initial_entry_result.success if initial_entry_result else False,
        )

        return session

    async def _execute_initial_entry(self, session: DemoGridSession) -> ExecutionResult | None:
        """
        Execute the IMMEDIATE FIRST ENTRY for a grid.

        Anchor level: blueprint.sections[0].levels[0] — the topmost
        level of the first section. This is deterministic and does not
        require any "find nearest level" logic at runtime.

        The order is a MARKET BUY at the current real-time price.
        The idempotency key is f"{grid_id}:INITIAL_ENTRY" without a
        time-bucket, because this order should only happen once per
        grid lifetime (unlike level-crossing orders which can repeat).

        On success, the anchor level is marked FILLED with the actual
        fill price (which may differ from anchor.price due to slippage).

        On failure (risk validation, exchange error), returns the failed
        ExecutionResult. The grid can still start — initial entry failure
        is NOT a fatal error.

        Args:
            session: Demo session to execute initial entry for

        Returns:
            ExecutionResult if attempted, None if no anchor level found
        """
        grid = session.grid_runtime
        blueprint = grid.blueprint

        # Get anchor level: Section 1, Level 0
        if not blueprint.sections:
            logger.warning(
                "initial_entry_no_sections",
                grid_id=grid.grid_id,
            )
            return None

        first_section = blueprint.sections[0]
        if not first_section.levels:
            logger.warning(
                "initial_entry_no_levels",
                grid_id=grid.grid_id,
                section_id=first_section.section_id,
            )
            return None

        anchor = first_section.levels[0]

        if anchor.quantity <= 0:
            logger.warning(
                "initial_entry_zero_quantity",
                grid_id=grid.grid_id,
                level=anchor.level,
            )
            return None

        # Get current real-time price for reference
        current_price = await self._get_current_price(grid.market_id)
        if current_price is None:
            logger.error(
                "initial_entry_no_price",
                grid_id=grid.grid_id,
                market_id=grid.market_id,
            )
            # Return a failed result — grid can still start
            return ExecutionResult(
                success=False,
                order_id="INITIAL_ENTRY_NO_PRICE",
                error_message="Could not fetch current price for initial entry",
            )

        # Idempotency key: once per grid lifetime (no time-bucket)
        idempotency_key = f"{grid.grid_id}:INITIAL_ENTRY"

        logger.info(
            "initial_entry_executing",
            grid_id=grid.grid_id,
            market_id=grid.market_id,
            anchor_level=anchor.level,
            anchor_price=str(anchor.price),
            current_price=str(current_price),
            quantity=str(anchor.quantity),
            idempotency_key=idempotency_key,
        )

        result = await self._execution_engine.execute_order(
            market_id=grid.market_id,
            side="BUY",
            quantity=anchor.quantity,
            price=None,  # MARKET order — immediate execution
            metadata={
                "grid_id": grid.grid_id,
                "section_id": first_section.section_id,
                "level_index": 0,
                "trigger_type": "initial_entry",
                "demo_session_id": session.session_id,
            },
            reference_price=current_price,
            user_id=session.user_id,
            idempotency_key=idempotency_key,
        )

        if result.success:
            # Mark anchor level as FILLED with actual execution price.
            # Note: entry_price uses current_price (reference) since we
            # don't have the actual fill price from exchange yet.
            # In production, this should use the actual average fill
            # price from the order status response.
            anchor.mark_filled(anchor.quantity, current_price)

            session.metrics.record_order_submitted()
            session.add_note(f"Initial entry executed: BUY {anchor.quantity} @ ~{current_price}")

            logger.info(
                "initial_entry_success",
                grid_id=grid.grid_id,
                order_id=result.order_id,
                quantity=str(anchor.quantity),
                entry_price=str(current_price),
            )
        else:
            # Initial entry failed — grid can still start without position
            session.metrics.record_order_rejected("INITIAL_ENTRY_FAILED")
            session.add_note(
                f"Initial entry failed: {result.error_message}. Grid will trade on crossings only."
            )

            logger.warning(
                "initial_entry_failed",
                grid_id=grid.grid_id,
                error=result.error_message,
            )

        return result

    async def _get_current_price(self, market_id: MarketId) -> Decimal | None:
        """
        Get current market price from the exchange adapter.

        Uses the price monitor's cached price if available (faster),
        otherwise fetches from the exchange via REST API.

        Args:
            market_id: Market to get price for

        Returns:
            Current price or None if unavailable
        """
        # Try price monitor's cached price first
        if self._price_monitor is not None:
            cached_price = self._price_monitor.get_last_price(market_id)
            if cached_price is not None:
                return cached_price

        # Fallback: fetch from exchange via adapter
        try:
            # Access the adapter through execution engine
            ticker = await self._execution_engine._adapter.get_ticker(market_id)
            last_price_str = ticker.get("last") or ticker.get("price") or ticker.get("lastPrice")
            if last_price_str:
                return Decimal(str(last_price_str))
        except Exception as e:
            logger.warning(
                "get_current_price_failed",
                market_id=market_id,
                error=str(e),
            )

        return None

    def pause_demo_grid(self, session_id: str) -> DemoGridSession:
        """
        Pause a demo grid session.

        Args:
            session_id: Session to pause

        Returns:
            Updated DemoGridSession

        Raises:
            DemoTradingError: If session not found or cannot pause
        """
        session = self._get_session(session_id)

        try:
            self._grid_engine.pause_grid(session.grid_runtime.grid_id)
        except GridEngineError as e:
            raise DemoTradingError(f"Failed to pause demo grid: {e}") from e

        session.status = "PAUSED"
        session.metrics.record_state_transition()
        session.metrics.record_pause_resume()
        session.add_note("Demo grid paused")

        # Stop monitoring this grid while paused
        if self._price_monitor is not None:
            self._price_monitor.unmonitor_grid(session.grid_runtime.grid_id)

        logger.info("demo_grid_paused", session_id=session_id)

        return session

    def resume_demo_grid(self, session_id: str) -> DemoGridSession:
        """
        Resume a paused demo grid session.

        Args:
            session_id: Session to resume

        Returns:
            Updated DemoGridSession

        Raises:
            DemoTradingError: If session not found or cannot resume
        """
        session = self._get_session(session_id)

        try:
            self._grid_engine.resume_grid(session.grid_runtime.grid_id)
        except GridEngineError as e:
            raise DemoTradingError(f"Failed to resume demo grid: {e}") from e

        session.status = "RUNNING"
        session.metrics.record_state_transition()
        session.add_note("Demo grid resumed")

        # Re-wire price monitor for this grid
        if self._price_monitor is not None:
            self._price_monitor.monitor_grid(session.grid_runtime)
            logger.info(
                "demo_grid_monitoring_resumed",
                session_id=session_id,
                grid_id=session.grid_runtime.grid_id,
            )

        logger.info("demo_grid_resumed", session_id=session_id)

        return session

    def stop_demo_grid(self, session_id: str, reason: str = "Manual stop") -> DemoGridSession:
        """
        Stop a demo grid session.

        Args:
            session_id: Session to stop
            reason: Reason for stopping

        Returns:
            Updated DemoGridSession

        Raises:
            DemoTradingError: If session not found or cannot stop
        """
        session = self._get_session(session_id)

        try:
            self._grid_engine.stop_grid(session.grid_runtime.grid_id)
        except GridEngineError as e:
            raise DemoTradingError(f"Failed to stop demo grid: {e}") from e

        session.status = "STOPPED"
        session.stopped_at = datetime.now(UTC)
        session.metrics.record_state_transition()
        session.add_note(f"Demo grid stopped: {reason}")

        # Stop monitoring this grid
        if self._price_monitor is not None:
            self._price_monitor.unmonitor_grid(session.grid_runtime.grid_id)

        logger.info("demo_grid_stopped", session_id=session_id, reason=reason)

        return session

    def emergency_stop_demo_grid(self, session_id: str, reason: str) -> DemoGridSession:
        """
        Emergency stop a demo grid session.

        Args:
            session_id: Session to emergency stop
            reason: Reason for emergency stop

        Returns:
            Updated DemoGridSession

        Raises:
            DemoTradingError: If session not found
        """
        session = self._get_session(session_id)

        session.grid_runtime.emergency_stop()
        session.status = "EMERGENCY_STOPPED"
        session.stopped_at = datetime.now(UTC)
        session.metrics.record_emergency_stop()
        session.metrics.record_state_transition()
        session.add_note(f"EMERGENCY STOP: {reason}")

        # Stop monitoring this grid
        if self._price_monitor is not None:
            self._price_monitor.unmonitor_grid(session.grid_runtime.grid_id)

        logger.warning(
            "demo_grid_emergency_stopped",
            session_id=session_id,
            reason=reason,
        )

        return session

    def emergency_stop_all(self, reason: str) -> list[DemoGridSession]:
        """
        Emergency stop all active demo grids.

        Args:
            reason: Reason for emergency stop

        Returns:
            List of stopped sessions
        """
        stopped = []
        for session in self._sessions.values():
            if session.status in ("CREATED", "RUNNING", "PAUSED"):
                session.grid_runtime.emergency_stop()
                session.status = "EMERGENCY_STOPPED"
                session.stopped_at = datetime.now(UTC)
                session.metrics.record_emergency_stop()
                session.add_note(f"EMERGENCY STOP ALL: {reason}")
                # Stop monitoring this grid
                if self._price_monitor is not None:
                    self._price_monitor.unmonitor_grid(session.grid_runtime.grid_id)
                stopped.append(session)

        logger.warning("demo_emergency_stop_all", count=len(stopped), reason=reason)
        return stopped

    async def execute_demo_order(
        self,
        session_id: str,
        market_id: MarketId,
        side: str,
        quantity: Decimal,
        price: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """
        Execute an order in demo mode.

        Args:
            session_id: Demo session ID
            market_id: Market to trade
            side: Order side (BUY/SELL)
            quantity: Order quantity
            price: Limit price (None for market orders)
            metadata: Additional metadata

        Returns:
            ExecutionResult

        Raises:
            DemoTradingError: If session not found or not running
        """
        session = self._get_session(session_id)

        if session.status != "RUNNING":
            raise DemoTradingError(
                f"Cannot execute order: session status is {session.status}, expected RUNNING"
            )

        import time

        start_time = time.perf_counter()

        result = await self._execution_engine.execute_order(
            market_id=market_id,
            side=side,  # type: ignore[arg-type]
            quantity=quantity,
            price=price,
            metadata={**(metadata or {}), "demo_session_id": session_id},
            user_id=session.user_id,
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        if result.success:
            session.metrics.record_order_submitted(latency_ms)
            logger.info(
                "demo_order_executed",
                session_id=session_id,
                order_id=result.order_id,
                latency_ms=latency_ms,
            )
        else:
            session.metrics.record_order_rejected("EXECUTION_FAILED")
            logger.error(
                "demo_order_failed",
                session_id=session_id,
                error=result.error_message,
            )

        return result

    def record_order_filled(self, session_id: str) -> None:
        """Record an order fill for a session."""
        session = self._get_session(session_id)
        session.metrics.record_order_filled()

    def record_reconciliation(self, session_id: str, mismatches: int = 0) -> None:
        """Record a reconciliation event."""
        session = self._get_session(session_id)
        session.metrics.record_reconciliation(mismatches)

    def record_ws_reconnect(self, session_id: str) -> None:
        """Record a WebSocket reconnection."""
        session = self._get_session(session_id)
        session.metrics.record_ws_reconnect()

    def get_session(self, session_id: str) -> DemoGridSession | None:
        """Get a demo session by ID."""
        return self._sessions.get(session_id)

    def get_session_by_grid_id(self, grid_id: str) -> DemoGridSession | None:
        """
        Get a demo session by grid ID.

        Args:
            grid_id: The grid runtime ID

        Returns:
            DemoGridSession or None
        """
        for session in self._sessions.values():
            if session.grid_runtime.grid_id == grid_id:
                return session
        return None

    def get_all_sessions(self) -> list[DemoGridSession]:
        """Get all demo sessions."""
        return list(self._sessions.values())

    def get_session_metrics(self, session_id: str) -> DemoMetrics | None:
        """Get metrics for a session."""
        session = self._sessions.get(session_id)
        return session.metrics if session else None

    def get_all_metrics(self) -> DemoMetrics:
        """Aggregate metrics from all sessions."""
        total = DemoMetrics()

        for session in self._sessions.values():
            m = session.metrics
            total.orders_submitted += m.orders_submitted
            total.orders_filled += m.orders_filled
            total.orders_rejected += m.orders_rejected
            total.orders_cancelled += m.orders_cancelled
            total.total_order_latency_ms += m.total_order_latency_ms
            total.ws_reconnect_count += m.ws_reconnect_count
            total.reconciliation_count += m.reconciliation_count
            total.reconciliation_mismatches += m.reconciliation_mismatches
            total.error_count += m.error_count
            total.grid_state_transitions += m.grid_state_transitions
            total.emergency_stops += m.emergency_stops
            total.pause_resume_cycles += m.pause_resume_cycles

            for category, count in m.errors_by_category.items():
                total.errors_by_category[category] = (
                    total.errors_by_category.get(category, 0) + count
                )

        return total

    def generate_validation_report(self) -> DemoValidationReport:
        """
        Generate demo validation report.

        Returns:
            DemoValidationReport with readiness assessment
        """
        sessions = list(self._sessions.values())
        total_metrics = self.get_all_metrics()

        # Determine period
        if sessions:
            period_start = min(s.created_at for s in sessions)
            period_end = max(s.stopped_at or datetime.now(UTC) for s in sessions)
        else:
            period_start = datetime.now(UTC)
            period_end = datetime.now(UTC)

        report = DemoValidationReport(
            report_id=f"REPORT-{uuid4().hex[:12].upper()}",
            period_start=period_start,
            period_end=period_end,
            sessions=sessions,
            total_metrics=total_metrics,
        )

        report.evaluate_readiness()

        logger.info(
            "demo_validation_report_generated",
            report_id=report.report_id,
            ready_for_live=report.ready_for_live,
            sessions=len(sessions),
        )

        return report

    def get_service_status(self) -> dict[str, Any]:
        """Get demo trading service status."""
        status_counts: dict[str, int] = {}
        for session in self._sessions.values():
            status_counts[session.status] = status_counts.get(session.status, 0) + 1

        return {
            "environment": self._environment,
            "total_sessions": len(self._sessions),
            "active_sessions": len(self.active_sessions),
            "status_counts": status_counts,
            "metrics": self.get_all_metrics().to_dict(),
        }

    def _get_session(self, session_id: str) -> DemoGridSession:
        """Get session or raise error."""
        session = self._sessions.get(session_id)
        if session is None:
            raise DemoTradingError(f"Demo session not found: {session_id}")
        return session


class DemoTradingError(Exception):
    """Demo trading error."""

    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        super().__init__(message)
        self.message = message
