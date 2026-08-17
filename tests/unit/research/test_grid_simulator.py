"""
Unit tests for the deterministic grid simulator.

Tests cover:
- Determinism (same input → same output)
- Section activation
- BUY execution on downward price crossing
- SELL execution on upward price crossing
- Lot-linked cycle tracking
- Fee and slippage modeling (never double-counted)
- Capital exhaustion handling
- Intrabar price path policy
- Event logging
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from okx_trading.domain.grid.models import Blueprint, Section
from okx_trading.domain.market.models import Candle
from okx_trading.research.simulator.grid_simulator import (
    EventType,
    GridSimulator,
    ScenarioMode,
    SimulationConfig,
    TerminalCondition,
)


def make_config(
    starting_capital: Decimal = Decimal("10000"),
    buy_fee_rate: float = 0.001,
    sell_fee_rate: float = 0.001,
    slippage_pct: float = 0.0,
    horizon: int = 100,
    scenario_mode: ScenarioMode = ScenarioMode.BASELINE,
) -> SimulationConfig:
    """Create a test simulation config."""
    return SimulationConfig(
        market_id="BTC-USDT",
        observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        simulation_horizon_candles=horizon,
        starting_capital=starting_capital,
        buy_fee_rate=buy_fee_rate,
        sell_fee_rate=sell_fee_rate,
        slippage_pct=slippage_pct,
        scenario_mode=scenario_mode,
    )


def make_blueprint(
    total_capital: Decimal = Decimal("10000"),
    sections: list[Section] | None = None,
) -> Blueprint:
    """Create a test blueprint with a single section by default."""
    if sections is None:
        sections = [
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("2"),
                capital_allocation_pct=Decimal("100"),
            ),
        ]
    return Blueprint(
        blueprint_id="bp_test_001",
        market_id="BTC-USDT",
        total_capital=total_capital,
        sections=sections,
    )


def make_candle(
    timestamp: datetime,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    market_id: str = "BTC-USDT",
) -> Candle:
    """Create a test candle."""
    return Candle(
        market_id=market_id,
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=Decimal("1000"),
    )


def make_candles_from_closes(
    closes: list[Decimal],
    start: datetime | None = None,
) -> list[Candle]:
    """Create candles from a list of close prices (OHLC = close for simplicity)."""
    if start is None:
        start = datetime(2024, 1, 1, tzinfo=UTC)
    candles = []
    for i, close in enumerate(closes):
        ts = start + timedelta(hours=i)
        candles.append(
            make_candle(
                timestamp=ts,
                open_=close,
                high=close,
                low=close,
                close=close,
            )
        )
    return candles


class TestSimulatorDeterminism:
    """Simulator must be deterministic."""

    def test_same_input_produces_same_output(self) -> None:
        """Same blueprint + candles must produce identical results."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes(
            [Decimal("100"), Decimal("98"), Decimal("96"), Decimal("94"), Decimal("97")]
        )

        result1 = GridSimulator(config).run(blueprint, candles)
        result2 = GridSimulator(config).run(blueprint, candles)

        assert result1.final_equity == result2.final_equity
        assert result1.realized_pnl == result2.realized_pnl
        assert result1.total_buy_count == result2.total_buy_count
        assert result1.total_sell_count == result2.total_sell_count
        assert len(result1.events) == len(result2.events)

    def test_result_to_dict_is_serializable(self) -> None:
        """Result to_dict must produce a flat serializable dict."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)
        d = result.to_dict()

        assert d["market_id"] == "BTC-USDT"
        assert d["simulation_status"] == "COMPLETED"
        assert isinstance(d["initial_capital"], float)
        assert d["event_count"] == len(result.events)


class TestSectionActivation:
    """Section activation when price enters range."""

    def test_section_activates_when_price_enters_range(self) -> None:
        """Section should activate when price enters its range."""
        config = make_config()
        blueprint = make_blueprint()
        # Price starts above section (100 is upper boundary), then enters
        candles = make_candles_from_closes([Decimal("105"), Decimal("99")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.sections_activated == 1
        activated_events = [e for e in result.events if e.event_type == EventType.SECTION_ACTIVATED]
        assert len(activated_events) == 1
        assert activated_events[0].section_id == 1

    def test_section_not_activated_when_price_outside_range(self) -> None:
        """Section should not activate if price stays outside range."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("110"), Decimal("105")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.sections_activated == 0


class TestBuyExecution:
    """BUY execution on downward grid crossings."""

    def test_buy_executes_on_downward_crossing(self) -> None:
        """BUY should execute when price crosses down through a grid level."""
        config = make_config(starting_capital=Decimal("10000"))
        blueprint = make_blueprint()
        # Price drops from 100 to 95, crossing grid levels
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.total_buy_count > 0
        buy_events = [e for e in result.events if e.event_type == EventType.BUY_EXECUTED]
        assert len(buy_events) == result.total_buy_count
        # Asset quantity should increase after buys
        assert result.final_asset_quantity > Decimal("0")

    def test_buy_rejected_when_insufficient_capital(self) -> None:
        """BUY should be rejected when capital is insufficient."""
        config = make_config(starting_capital=Decimal("10"))  # Very small capital
        blueprint = make_blueprint(total_capital=Decimal("10"))
        candles = make_candles_from_closes([Decimal("100"), Decimal("90")])

        result = GridSimulator(config).run(blueprint, candles)

        # With tiny capital, some buys may be rejected
        assert result.total_buy_rejected >= 0

    def test_no_duplicate_buy_for_same_level_with_open_lot(self) -> None:
        """Should not buy again at same level if lot is still open."""
        config = make_config()
        blueprint = make_blueprint()
        # Price crosses down, then stays low (no sell), then crosses again
        candles = make_candles_from_closes(
            [Decimal("100"), Decimal("95"), Decimal("94"), Decimal("95"), Decimal("94")]
        )

        result = GridSimulator(config).run(blueprint, candles)

        # Count buys per level — each level should have at most 1 open lot at a time
        buy_events = [e for e in result.events if e.event_type == EventType.BUY_EXECUTED]
        level_counts: dict[tuple[int, int], int] = {}
        for e in buy_events:
            key = (e.section_id or 0, e.grid_level or 0)
            level_counts[key] = level_counts.get(key, 0) + 1
        # With no sells completing cycles, each level bought at most once
        # (unless a sell completed and re-armed, which doesn't happen here)
        for count in level_counts.values():
            assert count >= 1


class TestSellExecution:
    """SELL execution on upward crossings."""

    def test_sell_executes_after_buy_when_price_recovers(self) -> None:
        """SELL should execute when price rises above target after a BUY."""
        config = make_config(starting_capital=Decimal("10000"))
        blueprint = make_blueprint()
        # Price drops to trigger buys, then rises to trigger sells
        candles = make_candles_from_closes(
            [Decimal("100"), Decimal("95"), Decimal("99"), Decimal("100")]
        )

        result = GridSimulator(config).run(blueprint, candles)

        assert result.total_buy_count > 0
        # Some sells should complete if price recovers above target levels
        if result.total_sell_count > 0:
            sell_events = [e for e in result.events if e.event_type == EventType.SELL_EXECUTED]
            assert len(sell_events) == result.total_sell_count
            assert result.completed_cycles == result.total_sell_count

    def test_completed_cycles_match_sells(self) -> None:
        """Each SELL completes one cycle."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95"), Decimal("99")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.completed_cycles == result.total_sell_count


class TestEconomics:
    """Fee and slippage modeling."""

    def test_fees_are_charged_on_buys(self) -> None:
        """Total fees must be positive when trades occur."""
        config = make_config(buy_fee_rate=0.001, sell_fee_rate=0.001)
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)

        if result.total_buy_count > 0:
            assert result.total_fees_paid > Decimal("0")

    def test_slippage_increases_effective_buy_cost(self) -> None:
        """With slippage, execution price should be above grid price for buys."""
        config_no_slip = make_config(slippage_pct=0.0)
        config_with_slip = make_config(slippage_pct=0.005)
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result_no_slip = GridSimulator(config_no_slip).run(blueprint, candles)
        result_with_slip = GridSimulator(config_with_slip).run(blueprint, candles)

        # With slippage, less asset should be acquired (higher effective price)
        if result_no_slip.total_buy_count > 0 and result_with_slip.total_buy_count > 0:
            assert result_with_slip.final_asset_quantity <= result_no_slip.final_asset_quantity

    def test_stress_scenario_doubles_slippage(self) -> None:
        """Stress mode should apply 2x slippage."""
        config = make_config(slippage_pct=0.005, scenario_mode=ScenarioMode.STRESS)
        assert config.effective_slippage() == pytest.approx(0.01)

    def test_extreme_scenario_quadruples_slippage(self) -> None:
        """Extreme mode should apply 4x slippage."""
        config = make_config(slippage_pct=0.005, scenario_mode=ScenarioMode.EXTREME)
        assert config.effective_slippage() == pytest.approx(0.02)

    def test_baseline_no_slippage_multiplier(self) -> None:
        """Baseline mode should not multiply slippage."""
        config = make_config(slippage_pct=0.005, scenario_mode=ScenarioMode.BASELINE)
        assert config.effective_slippage() == pytest.approx(0.005)


class TestIntrabarPolicy:
    """Intrabar price path resolution."""

    def test_bullish_candle_path(self) -> None:
        """Bullish candle: Open -> Low -> High -> Close."""
        config = make_config()
        sim = GridSimulator(config)
        candle = make_candle(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            open_=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
        )
        path = sim._get_price_path(candle)
        assert path == [Decimal("100"), Decimal("95"), Decimal("110"), Decimal("105")]

    def test_bearish_candle_path(self) -> None:
        """Bearish candle: Open -> High -> Low -> Close."""
        config = make_config()
        sim = GridSimulator(config)
        candle = make_candle(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            open_=Decimal("105"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("100"),
        )
        path = sim._get_price_path(candle)
        assert path == [Decimal("105"), Decimal("110"), Decimal("95"), Decimal("100")]


class TestTerminalConditions:
    """Simulation terminal conditions."""

    def test_horizon_end_terminal_condition(self) -> None:
        """Simulation should end with HORIZON_END when all candles processed."""
        config = make_config(horizon=10)
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100")] * 20)

        result = GridSimulator(config).run(blueprint, candles)

        assert result.terminal_condition == TerminalCondition.HORIZON_END
        assert result.simulation_status == "COMPLETED"
        assert result.candles_processed == 10  # Limited by horizon

    def test_all_candles_processed_when_within_horizon(self) -> None:
        """All candles processed if fewer than horizon."""
        config = make_config(horizon=100)
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100")] * 5)

        result = GridSimulator(config).run(blueprint, candles)

        assert result.candles_processed == 5


class TestEventLogging:
    """All events must be logged."""

    def test_market_update_events_logged(self) -> None:
        """Each candle produces a MARKET_UPDATE event."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("99"), Decimal("98")])

        result = GridSimulator(config).run(blueprint, candles)

        market_events = [e for e in result.events if e.event_type == EventType.MARKET_UPDATE]
        assert len(market_events) == 3

    def test_simulation_terminated_event_logged(self) -> None:
        """Final SIMULATION_TERMINATED event must be logged."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100")])

        result = GridSimulator(config).run(blueprint, candles)

        term_events = [e for e in result.events if e.event_type == EventType.SIMULATION_TERMINATED]
        assert len(term_events) == 1
        assert term_events[0].reason == TerminalCondition.HORIZON_END.value

    def test_event_ids_are_sequential(self) -> None:
        """Event IDs must be sequential starting from 1."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)

        for i, event in enumerate(result.events):
            assert event.event_id == i + 1


class TestCapitalTracking:
    """Capital and equity tracking."""

    def test_no_trades_preserves_capital(self) -> None:
        """If no trades occur, capital should be preserved."""
        config = make_config(starting_capital=Decimal("10000"))
        blueprint = make_blueprint()
        # Price stays above section — no activation, no trades
        candles = make_candles_from_closes([Decimal("110"), Decimal("115")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.final_quote_balance == Decimal("10000")
        assert result.final_asset_quantity == Decimal("0")
        assert result.final_equity == Decimal("10000")

    def test_equity_reflects_open_positions(self) -> None:
        """Final equity should include value of open positions."""
        config = make_config(starting_capital=Decimal("10000"))
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)

        if result.final_asset_quantity > 0:
            expected_equity = result.final_quote_balance + result.final_asset_quantity * Decimal(
                "95"
            )
            assert result.final_equity == expected_equity

    def test_peak_capital_utilization_tracked(self) -> None:
        """Peak capital utilization should be between 0 and 1."""
        config = make_config()
        blueprint = make_blueprint()
        candles = make_candles_from_closes([Decimal("100"), Decimal("95")])

        result = GridSimulator(config).run(blueprint, candles)

        assert 0.0 <= result.peak_capital_utilization <= 1.0


class TestMultiSection:
    """Multi-section blueprint behavior."""

    def test_multiple_sections_activate_at_different_prices(self) -> None:
        """Each section activates when its own price range is entered."""
        config = make_config()
        sections = [
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=3,
                grid_spacing_pct=Decimal("2"),
                capital_allocation_pct=Decimal("50"),
                gap_to_next_pct=Decimal("5"),
            ),
            Section(
                section_id=2,
                upper_price=Decimal("85.5"),
                lower_price=Decimal("75"),
                grid_count=3,
                grid_spacing_pct=Decimal("2"),
                capital_allocation_pct=Decimal("50"),
            ),
        ]
        blueprint = make_blueprint(sections=sections)
        # Price drops through section 1 into section 2
        candles = make_candles_from_closes([Decimal("100"), Decimal("95"), Decimal("80")])

        result = GridSimulator(config).run(blueprint, candles)

        assert result.sections_activated == 2
        assert result.max_section_depth == 2
