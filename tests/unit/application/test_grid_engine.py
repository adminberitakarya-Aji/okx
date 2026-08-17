"""
Tests for GridEngine.

Tests cover:
- Grid runtime creation from blueprints
- State transitions (CREATED → RUNNING → PAUSED → STOPPED)
- Emergency stop
- Grid price calculation integration
"""

from decimal import Decimal

import pytest

from okx_trading.application.services.grid_engine import (
    GridEngine,
    GridEngineError,
    GridRuntime,
)
from okx_trading.domain.grid.models import Blueprint, Section


def create_test_blueprint(
    market_id: str = "BTC-USDT",
    total_capital: Decimal = Decimal("1000"),
) -> Blueprint:
    """Create a valid test blueprint with one section."""
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


def create_multi_section_blueprint() -> Blueprint:
    """Create a valid test blueprint with two sections."""
    section1 = Section(
        section_id=1,
        upper_price=Decimal("50000"),
        lower_price=Decimal("47000"),
        grid_count=4,
        grid_spacing_pct=Decimal("1.5"),
        capital_allocation_pct=Decimal("60"),
        gap_to_next_pct=Decimal("2"),
    )
    section2 = Section(
        section_id=2,
        upper_price=Decimal("46000"),
        lower_price=Decimal("43000"),
        grid_count=4,
        grid_spacing_pct=Decimal("1.5"),
        capital_allocation_pct=Decimal("40"),
    )
    return Blueprint(
        blueprint_id="BP-TEST-002",
        market_id="BTC-USDT",
        total_capital=Decimal("1000"),
        sections=[section1, section2],
    )


class TestGridRuntime:
    """Tests for GridRuntime state machine."""

    @pytest.fixture
    def runtime(self) -> GridRuntime:
        """Create a grid runtime for testing."""
        blueprint = create_test_blueprint()
        return GridRuntime(
            grid_id="GRID-TEST-001",
            blueprint=blueprint,
            environment="DEMO",
        )

    def test_initial_status_is_created(self, runtime: GridRuntime) -> None:
        """Test grid starts in CREATED status."""
        assert runtime.status == "CREATED"
        assert runtime.is_active is False

    def test_start_transitions_to_running(self, runtime: GridRuntime) -> None:
        """Test start transitions CREATED → RUNNING."""
        runtime.start()
        assert runtime.status == "RUNNING"
        assert runtime.is_active is True
        assert runtime.started_at is not None

    def test_pause_transitions_to_paused(self, runtime: GridRuntime) -> None:
        """Test pause transitions RUNNING → PAUSED."""
        runtime.start()
        runtime.pause()
        assert runtime.status == "PAUSED"
        assert runtime.is_active is False

    def test_resume_transitions_to_running(self, runtime: GridRuntime) -> None:
        """Test resume transitions PAUSED → RUNNING."""
        runtime.start()
        runtime.pause()
        runtime.resume()
        assert runtime.status == "RUNNING"
        assert runtime.is_active is True

    def test_stop_transitions_to_stopped(self, runtime: GridRuntime) -> None:
        """Test stop transitions RUNNING → STOPPED."""
        runtime.start()
        runtime.stop()
        assert runtime.status == "STOPPED"
        assert runtime.stopped_at is not None

    def test_cannot_start_twice(self, runtime: GridRuntime) -> None:
        """Test cannot start an already running grid."""
        runtime.start()
        with pytest.raises(GridEngineError):
            runtime.start()

    def test_cannot_pause_when_not_running(self, runtime: GridRuntime) -> None:
        """Test cannot pause a grid that is not running."""
        with pytest.raises(GridEngineError):
            runtime.pause()

    def test_cannot_resume_when_not_paused(self, runtime: GridRuntime) -> None:
        """Test cannot resume a grid that is not paused."""
        runtime.start()
        with pytest.raises(GridEngineError):
            runtime.resume()

    def test_emergency_stop_from_any_state(self, runtime: GridRuntime) -> None:
        """Test emergency stop works from any state."""
        runtime.emergency_stop()
        assert runtime.status == "EMERGENCY_STOPPED"

    def test_set_error(self, runtime: GridRuntime) -> None:
        """Test set_error transitions to ERROR state."""
        runtime.start()
        runtime.set_error("Test error")
        assert runtime.status == "ERROR"
        assert runtime.error_message == "Test error"

    def test_can_stop_from_error(self, runtime: GridRuntime) -> None:
        """Test can stop from ERROR state."""
        runtime.start()
        runtime.set_error("Test error")
        runtime.stop()
        assert runtime.status == "STOPPED"

    def test_market_id_property(self, runtime: GridRuntime) -> None:
        """Test market_id property returns blueprint market."""
        assert runtime.market_id == "BTC-USDT"

    def test_capital_utilization(self, runtime: GridRuntime) -> None:
        """Test capital utilization calculation."""
        assert runtime.capital_utilization == Decimal("0")
        runtime.deployed_capital = Decimal("500")
        assert runtime.capital_utilization == Decimal("50")

    def test_user_id_defaults_to_none(self, runtime: GridRuntime) -> None:
        """Test user_id defaults to None."""
        assert runtime.user_id is None

    def test_user_id_set(self) -> None:
        """Test user_id can be set."""
        blueprint = create_test_blueprint()
        runtime = GridRuntime(
            grid_id="GRID-TEST-002",
            blueprint=blueprint,
            environment="DEMO",
            user_id="usr_1",
        )
        assert runtime.user_id == "usr_1"


class TestGridEngine:
    """Tests for GridEngine."""

    @pytest.fixture
    def engine(self) -> GridEngine:
        """Create grid engine for testing."""
        return GridEngine()

    def test_create_grid(self, engine: GridEngine) -> None:
        """Test creating a grid from blueprint."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        assert grid.grid_id.startswith("GRID-")
        assert grid.status == "CREATED"
        assert grid.environment == "DEMO"
        assert grid.calculated_prices is not None

    def test_create_grid_with_user_id(self, engine: GridEngine) -> None:
        """Test creating a grid with user_id."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO", user_id="usr_1")

        assert grid.user_id == "usr_1"

    def test_create_grid_calculates_prices(self, engine: GridEngine) -> None:
        """Test grid creation calculates prices."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        assert grid.calculated_prices is not None
        prices = grid.calculated_prices.get_prices(1)
        assert len(prices) == 5
        # Prices should be descending
        assert prices[0] > prices[-1]

    def test_create_grid_populates_levels(self, engine: GridEngine) -> None:
        """Test grid creation populates section levels."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        section = grid.blueprint.get_section(1)
        assert section is not None
        assert len(section.levels) == 5

    def test_get_grid(self, engine: GridEngine) -> None:
        """Test retrieving a grid by ID."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        retrieved = engine.get_grid(grid.grid_id)
        assert retrieved is grid

    def test_get_grid_not_found(self, engine: GridEngine) -> None:
        """Test retrieving non-existent grid returns None."""
        assert engine.get_grid("NONEXISTENT") is None

    def test_start_grid(self, engine: GridEngine) -> None:
        """Test starting a grid via engine."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        started = engine.start_grid(grid.grid_id)
        assert started.status == "RUNNING"

    def test_start_grid_not_found(self, engine: GridEngine) -> None:
        """Test starting non-existent grid raises error."""
        with pytest.raises(GridEngineError):
            engine.start_grid("NONEXISTENT")

    def test_pause_grid(self, engine: GridEngine) -> None:
        """Test pausing a grid via engine."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")
        engine.start_grid(grid.grid_id)

        paused = engine.pause_grid(grid.grid_id)
        assert paused.status == "PAUSED"

    def test_resume_grid(self, engine: GridEngine) -> None:
        """Test resuming a grid via engine."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")
        engine.start_grid(grid.grid_id)
        engine.pause_grid(grid.grid_id)

        resumed = engine.resume_grid(grid.grid_id)
        assert resumed.status == "RUNNING"

    def test_stop_grid(self, engine: GridEngine) -> None:
        """Test stopping a grid via engine."""
        blueprint = create_test_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")
        engine.start_grid(grid.grid_id)

        stopped = engine.stop_grid(grid.grid_id)
        assert stopped.status == "STOPPED"

    def test_get_active_grids(self, engine: GridEngine) -> None:
        """Test getting active grids."""
        bp1 = create_test_blueprint()
        bp2 = create_multi_section_blueprint()

        grid1 = engine.create_grid(bp1, environment="DEMO")
        engine.create_grid(bp2, environment="DEMO")

        engine.start_grid(grid1.grid_id)

        active = engine.get_active_grids()
        assert len(active) == 1
        assert active[0].grid_id == grid1.grid_id

    def test_get_grids_for_market(self, engine: GridEngine) -> None:
        """Test getting grids for a specific market."""
        bp1 = create_test_blueprint(market_id="BTC-USDT")
        bp2 = create_test_blueprint(market_id="ETH-USDT")

        engine.create_grid(bp1, environment="DEMO")
        engine.create_grid(bp2, environment="DEMO")

        btc_grids = engine.get_grids_for_market("BTC-USDT")
        assert len(btc_grids) == 1
        assert btc_grids[0].market_id == "BTC-USDT"

    def test_emergency_stop_all(self, engine: GridEngine) -> None:
        """Test emergency stop all grids."""
        bp1 = create_test_blueprint()
        bp2 = create_multi_section_blueprint()

        grid1 = engine.create_grid(bp1, environment="DEMO")
        grid2 = engine.create_grid(bp2, environment="DEMO")

        engine.start_grid(grid1.grid_id)
        engine.start_grid(grid2.grid_id)

        stopped = engine.emergency_stop_all()
        assert len(stopped) == 2
        assert grid1.status == "EMERGENCY_STOPPED"
        assert grid2.status == "EMERGENCY_STOPPED"

    def test_get_engine_status(self, engine: GridEngine) -> None:
        """Test engine status summary."""
        bp1 = create_test_blueprint()
        bp2 = create_multi_section_blueprint()

        grid1 = engine.create_grid(bp1, environment="DEMO")
        engine.create_grid(bp2, environment="DEMO")
        engine.start_grid(grid1.grid_id)

        status = engine.get_engine_status()
        assert status["total_grids"] == 2
        assert status["active_grids"] == 1

    def test_multi_section_blueprint(self, engine: GridEngine) -> None:
        """Test creating grid with multiple sections."""
        blueprint = create_multi_section_blueprint()
        grid = engine.create_grid(blueprint, environment="DEMO")

        assert grid.calculated_prices is not None
        prices1 = grid.calculated_prices.get_prices(1)
        prices2 = grid.calculated_prices.get_prices(2)

        assert len(prices1) == 4
        assert len(prices2) == 4

        # Section 1 prices should be higher than section 2
        assert min(prices1) > max(prices2)
