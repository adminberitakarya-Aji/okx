"""
Grid Engine — Runtime state machine for grid execution.

This module provides:
- GridRuntime: Runtime state for an executing grid
- GridEngine: Manages multiple grid runtimes
- State transitions: CREATED → RUNNING → PAUSED → STOPPED

Key domain rules:
1. Grid spacing is UNIFORM within each Section
2. BUY and SELL use immediate execution (not passive limit orders)
3. Spot-only: no shorting, no leverage
4. Reconciliation required after any disconnect
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import structlog

from trading_grid.domain.grid.calculator import (
    calculate_capital_per_grid,
    calculate_grid_prices,
    populate_section_levels,
)
from trading_grid.domain.grid.models import Blueprint, CalculatedGridPrices
from trading_grid.domain.shared.types import ExecutionMode, MarketId

logger = structlog.get_logger()

GridRuntimeStatus = Literal[
    "CREATED",
    "RUNNING",
    "PAUSED",
    "STOPPING",
    "STOPPED",
    "ERROR",
    "EMERGENCY_STOPPED",
]


@dataclass
class GridRuntime:
    """
    Runtime state for an executing grid.

    Attributes:
        grid_id: Unique grid runtime identifier
        blueprint: The strategy blueprint being executed
        environment: Execution environment (DEMO/LIVE)
        status: Current runtime status
        calculated_prices: Calculated grid prices
        deployed_capital: Capital currently deployed
        realized_pnl: Realized P&L from completed trades
        unrealized_pnl: Unrealized P&L from open positions
        created_at: Creation timestamp
        started_at: Start timestamp
        stopped_at: Stop timestamp
        error_message: Error message if in ERROR state
    """

    grid_id: str
    blueprint: Blueprint
    environment: ExecutionMode
    user_id: str | None = None
    status: GridRuntimeStatus = "CREATED"
    calculated_prices: CalculatedGridPrices | None = None
    deployed_capital: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    error_message: str | None = None

    @property
    def market_id(self) -> MarketId:
        """Get the market ID."""
        return self.blueprint.market_id

    @property
    def is_active(self) -> bool:
        """Check if grid is actively running."""
        return self.status == "RUNNING"

    @property
    def can_start(self) -> bool:
        """Check if grid can be started."""
        return self.status == "CREATED"

    @property
    def can_pause(self) -> bool:
        """Check if grid can be paused."""
        return self.status == "RUNNING"

    @property
    def can_resume(self) -> bool:
        """Check if grid can be resumed."""
        return self.status == "PAUSED"

    @property
    def can_stop(self) -> bool:
        """Check if grid can be stopped."""
        return self.status in ("RUNNING", "PAUSED", "ERROR")

    @property
    def capital_utilization(self) -> Decimal:
        """Calculate capital utilization percentage."""
        if self.blueprint.total_capital == 0:
            return Decimal("0")
        return (self.deployed_capital / self.blueprint.total_capital) * 100

    def start(self) -> None:
        """Transition to RUNNING state."""
        if not self.can_start:
            raise GridEngineError(f"Cannot start grid in status {self.status}")
        self.status = "RUNNING"
        self.started_at = datetime.now(UTC)
        logger.info("grid_started", grid_id=self.grid_id, market_id=self.market_id)

    def pause(self) -> None:
        """Transition to PAUSED state."""
        if not self.can_pause:
            raise GridEngineError(f"Cannot pause grid in status {self.status}")
        self.status = "PAUSED"
        logger.info("grid_paused", grid_id=self.grid_id)

    def resume(self) -> None:
        """Transition back to RUNNING state."""
        if not self.can_resume:
            raise GridEngineError(f"Cannot resume grid in status {self.status}")
        self.status = "RUNNING"
        logger.info("grid_resumed", grid_id=self.grid_id)

    def stop(self) -> None:
        """Transition to STOPPED state."""
        if not self.can_stop:
            raise GridEngineError(f"Cannot stop grid in status {self.status}")
        self.status = "STOPPED"
        self.stopped_at = datetime.now(UTC)
        logger.info("grid_stopped", grid_id=self.grid_id)

    def emergency_stop(self) -> None:
        """Immediately stop grid (bypasses normal checks)."""
        self.status = "EMERGENCY_STOPPED"
        self.stopped_at = datetime.now(UTC)
        logger.warning("grid_emergency_stopped", grid_id=self.grid_id)

    def set_error(self, message: str) -> None:
        """Transition to ERROR state."""
        self.status = "ERROR"
        self.error_message = message
        logger.error("grid_error", grid_id=self.grid_id, error=message)


class GridEngine:
    """
    Grid Engine managing multiple grid runtimes.

    Responsibilities:
    - Create grid runtimes from blueprints
    - Manage state transitions
    - Track grid statistics
    - Coordinate with execution engine
    """

    def __init__(self) -> None:
        """Initialize grid engine."""
        self._grids: dict[str, GridRuntime] = {}

    def create_grid(
        self,
        blueprint: Blueprint,
        environment: ExecutionMode,
        user_id: str | None = None,
    ) -> GridRuntime:
        """
        Create a new grid runtime from a blueprint.

        Args:
            blueprint: The strategy blueprint
            environment: Execution environment
            user_id: User identifier who owns this grid (for per-user limits)

        Returns:
            Created GridRuntime

        Raises:
            GridEngineError: If blueprint is invalid
        """
        # Calculate grid prices
        try:
            calculated_prices = calculate_grid_prices(blueprint)
        except Exception as e:
            raise GridEngineError(f"Failed to calculate grid prices: {e}") from e

        # Populate section levels
        for section in blueprint.sections:
            prices = calculated_prices.get_prices(section.section_id)
            capital_per_grid = calculate_capital_per_grid(blueprint, section.section_id)
            populate_section_levels(section, prices, capital_per_grid)

        grid_id = f"GRID-{uuid4().hex[:12].upper()}"

        grid = GridRuntime(
            grid_id=grid_id,
            blueprint=blueprint,
            environment=environment,
            user_id=user_id,
            calculated_prices=calculated_prices,
        )

        self._grids[grid_id] = grid
        logger.info(
            "grid_created",
            grid_id=grid_id,
            market_id=blueprint.market_id,
            environment=environment,
            sections=len(blueprint.sections),
            total_grids=blueprint.total_grid_count,
        )

        return grid

    def get_grid(self, grid_id: str) -> GridRuntime | None:
        """Get a grid runtime by ID."""
        return self._grids.get(grid_id)

    def get_active_grids(self) -> list[GridRuntime]:
        """Get all active (RUNNING) grids."""
        return [g for g in self._grids.values() if g.is_active]

    def get_grids_for_market(self, market_id: MarketId) -> list[GridRuntime]:
        """Get all grids for a market."""
        return [g for g in self._grids.values() if g.market_id == market_id]

    def start_grid(self, grid_id: str) -> GridRuntime:
        """
        Start a grid.

        Args:
            grid_id: Grid to start

        Returns:
            Updated GridRuntime

        Raises:
            GridEngineError: If grid not found or cannot start
        """
        grid = self.get_grid(grid_id)
        if grid is None:
            raise GridEngineError(f"Grid not found: {grid_id}")
        grid.start()
        return grid

    def pause_grid(self, grid_id: str) -> GridRuntime:
        """Pause a grid."""
        grid = self.get_grid(grid_id)
        if grid is None:
            raise GridEngineError(f"Grid not found: {grid_id}")
        grid.pause()
        return grid

    def resume_grid(self, grid_id: str) -> GridRuntime:
        """Resume a paused grid."""
        grid = self.get_grid(grid_id)
        if grid is None:
            raise GridEngineError(f"Grid not found: {grid_id}")
        grid.resume()
        return grid

    def stop_grid(self, grid_id: str) -> GridRuntime:
        """Stop a grid."""
        grid = self.get_grid(grid_id)
        if grid is None:
            raise GridEngineError(f"Grid not found: {grid_id}")
        grid.stop()
        return grid

    def emergency_stop_all(self) -> list[GridRuntime]:
        """
        Emergency stop all active grids.

        Returns:
            List of stopped grids
        """
        stopped = []
        for grid in self._grids.values():
            if grid.status in ("RUNNING", "PAUSED", "CREATED"):
                grid.emergency_stop()
                stopped.append(grid)
        logger.warning("emergency_stop_all", count=len(stopped))
        return stopped

    def get_engine_status(self) -> dict[str, object]:
        """Get engine status summary."""
        status_counts: dict[str, int] = {}
        for grid in self._grids.values():
            status_counts[grid.status] = status_counts.get(grid.status, 0) + 1

        return {
            "total_grids": len(self._grids),
            "status_counts": status_counts,
            "active_grids": len(self.get_active_grids()),
        }


class GridEngineError(Exception):
    """Grid engine error."""

    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        super().__init__(message)
        self.message = message
