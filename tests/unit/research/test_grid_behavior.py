"""
Unit tests for Grid Behavior Feature Layer (F-GRD).

Tests the extract_grid_behavior_features function that extracts
F-GRD-001 through F-GRD-090 features from simulation results.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from okx_trading.research.features.grid_behavior import (
    GridBehaviorAvailability,
    extract_grid_behavior_features,
)
from okx_trading.research.simulator.grid_simulator import (
    EventType,
    SimulationConfig,
    SimulationEvent,
    SimulationResult,
    TerminalCondition,
)


def make_config(
    market_id: str = "BTC-USDT",
    starting_capital: Decimal = Decimal("10000"),
) -> SimulationConfig:
    """Create a test simulation config."""
    return SimulationConfig(
        market_id=market_id,
        observation_timestamp=datetime(2024, 1, 1),
        simulation_horizon_candles=100,
        starting_capital=starting_capital,
    )


def make_result(
    events: list[SimulationEvent] | None = None,
    completed_cycles: int = 0,
    total_buy_count: int = 0,
    total_sell_count: int = 0,
    realized_pnl: Decimal = Decimal("0"),
    unrealized_pnl: Decimal = Decimal("0"),
    total_pnl: Decimal = Decimal("0"),
    candles_processed: int = 100,
    max_section_depth: int = 0,
    sections_activated: int = 0,
    peak_capital_utilization: float = 0.0,
    capital_exhausted: bool = False,
    coin_accumulated: Decimal = Decimal("0"),
    average_acquisition_price: Decimal | None = None,
    final_quote_balance: Decimal = Decimal("10000"),
    max_drawdown: Decimal = Decimal("0"),
    net_pnl_return_pct: float = 0.0,
) -> SimulationResult:
    """Create a test simulation result."""
    return SimulationResult(
        simulation_run_id="test-run-001",
        market_id="BTC-USDT",
        observation_timestamp=datetime(2024, 1, 1),
        blueprint_id="bp-001",
        events=events or [],
        completed_cycles=completed_cycles,
        total_buy_count=total_buy_count,
        total_sell_count=total_sell_count,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_pnl=total_pnl,
        candles_processed=candles_processed,
        max_section_depth=max_section_depth,
        sections_activated=sections_activated,
        peak_capital_utilization=peak_capital_utilization,
        capital_exhausted=capital_exhausted,
        coin_accumulated=coin_accumulated,
        average_acquisition_price=average_acquisition_price,
        final_quote_balance=final_quote_balance,
        max_drawdown=max_drawdown,
        net_pnl_return_pct=net_pnl_return_pct,
        terminal_condition=TerminalCondition.HORIZON_END,
        simulation_status="COMPLETED",
    )


def make_buy_event(
    event_id: int,
    timestamp: datetime,
    section_id: int = 1,
    grid_level: int = 1,
    price: Decimal = Decimal("50000"),
    quantity: Decimal = Decimal("0.01"),
    capital_before: Decimal = Decimal("10000"),
    capital_after: Decimal = Decimal("9500"),
) -> SimulationEvent:
    """Create a BUY_EXECUTED event."""
    return SimulationEvent(
        event_id=event_id,
        timestamp=timestamp,
        event_type=EventType.BUY_EXECUTED,
        market_price=price,
        section_id=section_id,
        grid_level=grid_level,
        executed_quantity=quantity,
        execution_price=price,
        capital_before=capital_before,
        capital_after=capital_after,
    )


def make_sell_event(
    event_id: int,
    timestamp: datetime,
    section_id: int = 1,
    grid_level: int = 1,
    price: Decimal = Decimal("51000"),
    quantity: Decimal = Decimal("0.01"),
    realized_pnl: Decimal = Decimal("10"),
) -> SimulationEvent:
    """Create a SELL_EXECUTED event."""
    return SimulationEvent(
        event_id=event_id,
        timestamp=timestamp,
        event_type=EventType.SELL_EXECUTED,
        market_price=price,
        section_id=section_id,
        grid_level=grid_level,
        executed_quantity=quantity,
        execution_price=price,
        realized_pnl=realized_pnl,
    )


def make_section_activated_event(
    event_id: int,
    timestamp: datetime,
    section_id: int,
) -> SimulationEvent:
    """Create a SECTION_ACTIVATED event."""
    return SimulationEvent(
        event_id=event_id,
        timestamp=timestamp,
        event_type=EventType.SECTION_ACTIVATED,
        section_id=section_id,
    )


class TestExtractGridBehaviorFeatures:
    """Tests for extract_grid_behavior_features."""

    def test_empty_simulation(self):
        """No trades should produce zero counts and None for derived features."""
        config = make_config()
        result = make_result()

        features = extract_grid_behavior_features(result, config)

        assert features.market_id == "BTC-USDT"
        assert features.grid_event_count == 0
        assert features.buy_event_count == 0
        assert features.sell_event_count == 0
        assert features.grid_cycle_count == 0
        assert features.grid_opportunity_frequency == 0.0
        assert features.average_buy_interval is None
        assert features.average_cycle_duration is None

    def test_buy_and_sell_counts(self):
        """Buy and sell events should be counted correctly."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time),
            make_buy_event(2, base_time + timedelta(hours=1)),
            make_sell_event(3, base_time + timedelta(hours=2)),
        ]
        config = make_config()
        result = make_result(
            events=events,
            total_buy_count=2,
            total_sell_count=1,
            completed_cycles=1,
        )

        features = extract_grid_behavior_features(result, config)

        assert features.buy_event_count == 2
        assert features.sell_event_count == 1
        assert features.grid_event_count == 3
        assert features.grid_cycle_count == 1

    def test_grid_opportunity_frequency(self):
        """Opportunity frequency should be events / window."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time),
            make_sell_event(2, base_time + timedelta(hours=1)),
        ]
        config = make_config()
        result = make_result(events=events, candles_processed=100)

        features = extract_grid_behavior_features(result, config)

        assert features.grid_opportunity_frequency == pytest.approx(2 / 100)
        assert features.grid_opportunity_density == pytest.approx(2 / 100)

    def test_buy_frequency(self):
        """Buy frequency should be buy_count / window."""
        base_time = datetime(2024, 1, 1)
        events = [make_buy_event(1, base_time)]
        config = make_config()
        result = make_result(events=events, candles_processed=50)

        features = extract_grid_behavior_features(result, config)

        assert features.buy_frequency == pytest.approx(1 / 50)

    def test_cycle_completion_rate(self):
        """Cycle completion rate should be completed_cycles / buy_count."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time),
            make_buy_event(2, base_time + timedelta(hours=1)),
            make_sell_event(3, base_time + timedelta(hours=2)),
        ]
        config = make_config()
        result = make_result(events=events, completed_cycles=1)

        features = extract_grid_behavior_features(result, config)

        # 1 completed cycle / 2 buys initiated
        assert features.cycle_completion_rate == pytest.approx(0.5)

    def test_cycle_pnl_statistics(self):
        """Cycle PnL statistics should be computed from sell events."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time, grid_level=1),
            make_buy_event(2, base_time + timedelta(hours=1), grid_level=2),
            make_sell_event(
                3, base_time + timedelta(hours=2), grid_level=1, realized_pnl=Decimal("10")
            ),
            make_sell_event(
                4, base_time + timedelta(hours=3), grid_level=2, realized_pnl=Decimal("-5")
            ),
        ]
        config = make_config()
        result = make_result(events=events, completed_cycles=2)

        features = extract_grid_behavior_features(result, config)

        assert features.average_cycle_net_pnl == pytest.approx(2.5)  # (10 + -5) / 2
        assert features.positive_cycle_rate == pytest.approx(0.5)
        assert features.negative_cycle_rate == pytest.approx(0.5)
        assert features.average_positive_cycle == pytest.approx(10.0)
        assert features.average_negative_cycle == pytest.approx(-5.0)

    def test_section_activation_rates(self):
        """Section activation rates should reflect which sections activated."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_section_activated_event(1, base_time, section_id=1),
            make_section_activated_event(2, base_time + timedelta(hours=1), section_id=2),
        ]
        config = make_config()
        result = make_result(
            events=events,
            max_section_depth=2,
            sections_activated=2,
        )

        features = extract_grid_behavior_features(result, config)

        assert features.section_1_activation_rate == 1.0
        assert features.section_2_activation_rate == 1.0
        assert features.section_3_activation_rate == 0.0
        assert features.section_activation_depth == 2

    def test_section_transition_rates(self):
        """Section transition rates should reflect progression."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_section_activated_event(1, base_time, section_id=1),
            make_section_activated_event(2, base_time + timedelta(hours=1), section_id=2),
        ]
        config = make_config()
        result = make_result(events=events, sections_activated=2)

        features = extract_grid_behavior_features(result, config)

        assert features.section_1_to_2_transition_rate == 1.0
        # Section 2 activated but section 3 not → transition rate 0.0
        assert features.section_2_to_3_transition_rate == 0.0

    def test_capital_deployment(self):
        """Capital deployment features should reflect buy costs."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(
                1,
                base_time,
                capital_before=Decimal("10000"),
                capital_after=Decimal("9500"),
            ),
        ]
        config = make_config(starting_capital=Decimal("10000"))
        result = make_result(
            events=events,
            peak_capital_utilization=0.05,
            final_quote_balance=Decimal("9500"),
        )

        features = extract_grid_behavior_features(result, config)

        assert features.capital_deployed == pytest.approx(500.0)
        assert features.capital_deployment_ratio == pytest.approx(0.05)
        assert features.capital_reserve_remaining == pytest.approx(9500.0)
        assert features.capital_exhaustion_flag == 0

    def test_capital_exhaustion_flag(self):
        """Capital exhaustion flag should be set when capital exhausted."""
        config = make_config()
        result = make_result(capital_exhausted=True)

        features = extract_grid_behavior_features(result, config)

        assert features.capital_exhaustion_flag == 1
        assert features.capital_exhaustion_frequency == 1.0

    def test_coin_accumulation(self):
        """Coin accumulation features should reflect accumulated coins."""
        config = make_config()
        result = make_result(
            coin_accumulated=Decimal("0.5"),
            average_acquisition_price=Decimal("48000"),
        )

        features = extract_grid_behavior_features(result, config)

        assert features.total_coin_accumulated == pytest.approx(0.5)
        assert features.average_acquisition_price == pytest.approx(48000.0)

    def test_strategy_outcome(self):
        """Strategy outcome features should reflect PnL."""
        config = make_config()
        result = make_result(
            realized_pnl=Decimal("100"),
            unrealized_pnl=Decimal("50"),
            total_pnl=Decimal("150"),
            net_pnl_return_pct=1.5,
        )

        features = extract_grid_behavior_features(result, config)

        assert features.historical_net_pnl == pytest.approx(150.0)
        assert features.realized_pnl == pytest.approx(100.0)
        assert features.unrealized_pnl == pytest.approx(50.0)
        assert features.total_strategy_pnl == pytest.approx(150.0)
        assert features.net_pnl_return == pytest.approx(1.5)

    def test_profit_factor(self):
        """Profit factor should be gross_positive / abs(gross_negative)."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_sell_event(1, base_time, grid_level=1, realized_pnl=Decimal("20")),
            make_sell_event(
                2, base_time + timedelta(hours=1), grid_level=2, realized_pnl=Decimal("10")
            ),
            make_sell_event(
                3, base_time + timedelta(hours=2), grid_level=3, realized_pnl=Decimal("-5")
            ),
        ]
        config = make_config()
        result = make_result(events=events, completed_cycles=3)

        features = extract_grid_behavior_features(result, config)

        # gross_positive = 30, gross_negative = 5
        assert features.profit_factor == pytest.approx(6.0)

    def test_profit_factor_no_losses(self):
        """Profit factor should be inf when no losses."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_sell_event(1, base_time, realized_pnl=Decimal("10")),
        ]
        config = make_config()
        result = make_result(events=events, completed_cycles=1)

        features = extract_grid_behavior_features(result, config)

        assert features.profit_factor == float("inf")

    def test_stress_behavior(self):
        """Stress behavior features should reflect simulation stress."""
        config = make_config()
        result = make_result(
            peak_capital_utilization=0.85,
            max_section_depth=3,
        )

        features = extract_grid_behavior_features(result, config)

        assert features.maximum_capital_stress == pytest.approx(0.85)
        assert features.maximum_section_stress == 3

    def test_sensitivity_requires_multi_run(self):
        """Sensitivity features should be None for single run."""
        config = make_config()
        result = make_result()

        features = extract_grid_behavior_features(result, config)

        assert features.grid_spacing_sensitivity is None
        assert features.section_gap_sensitivity is None
        assert features.allocation_sensitivity is None
        assert features.section_count_sensitivity is None
        assert features.availability["sensitivity"] == GridBehaviorAvailability.REQUIRES_MULTI_RUN

    def test_to_dict(self):
        """to_dict should produce a flat dictionary."""
        config = make_config()
        result = make_result(
            realized_pnl=Decimal("100"),
            total_pnl=Decimal("100"),
        )

        features = extract_grid_behavior_features(result, config)
        d = features.to_dict()

        assert d["market_id"] == "BTC-USDT"
        assert d["blueprint_id"] == "bp-001"
        assert d["simulation_run_id"] == "test-run-001"
        assert d["realized_pnl"] == pytest.approx(100.0)
        assert "observation_timestamp" in d
        assert "grid_spacing_sensitivity" in d

    def test_cycle_duration_computation(self):
        """Cycle durations should be computed from matched buy-sell pairs."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time, section_id=1, grid_level=1),
            make_sell_event(2, base_time + timedelta(hours=2), section_id=1, grid_level=1),
        ]
        config = make_config()
        result = make_result(events=events, completed_cycles=1)

        features = extract_grid_behavior_features(result, config)

        # Duration should be 2 hours = 7200 seconds
        assert features.average_cycle_duration == pytest.approx(7200.0)
        assert features.median_cycle_duration == pytest.approx(7200.0)

    def test_buy_to_sell_completion_rate(self):
        """Buy to sell completion rate should be sells / buys."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time),
            make_buy_event(2, base_time + timedelta(hours=1)),
            make_sell_event(3, base_time + timedelta(hours=2)),
        ]
        config = make_config()
        result = make_result(events=events)

        features = extract_grid_behavior_features(result, config)

        assert features.buy_to_sell_completion_rate == pytest.approx(0.5)

    def test_grid_trigger_rate_with_rejections(self):
        """Grid trigger rate should account for rejected buys."""
        base_time = datetime(2024, 1, 1)
        events = [
            make_buy_event(1, base_time),
            SimulationEvent(
                event_id=2,
                timestamp=base_time + timedelta(hours=1),
                event_type=EventType.BUY_REJECTED,
                reason="INSUFFICIENT_CAPITAL",
            ),
        ]
        config = make_config()
        result = make_result(events=events)

        features = extract_grid_behavior_features(result, config)

        # 1 executed / (1 executed + 1 rejected) = 0.5
        assert features.grid_trigger_rate == pytest.approx(0.5)
        assert features.grid_level_touch_count == 2
        assert features.grid_execution_trigger_count == 1
