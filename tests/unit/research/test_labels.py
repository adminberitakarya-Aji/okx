"""Tests for Label Generator."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_grid.research.labels.generator import (
    LABEL_DEFINITIONS,
    LABEL_VERSION,
    LabelClass,
    LabelGenerator,
    LabelQualityMetrics,
    LabelType,
    SimulationStatus,
)
from trading_grid.research.simulator.grid_simulator import SimulationResult


def create_mock_simulation_result(
    total_pnl: float = 100.0,
    simulation_status: str = "COMPLETED",
    candles_processed: int = 100,
) -> SimulationResult:
    """Create a mock SimulationResult for testing."""
    return SimulationResult(
        simulation_run_id="sim-test-001",
        market_id="BTC-USDT",
        blueprint_id="BP-001",
        observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        simulation_status=simulation_status,
        candles_processed=candles_processed,
        total_pnl=Decimal(str(total_pnl)),
        initial_capital=Decimal("10000"),
        max_drawdown_pct=0.15,
        peak_capital_utilization=0.65,
        max_section_depth=2,
        capital_exhausted=False,
    )


class TestLabelGenerator:
    """Tests for LabelGenerator."""

    def test_generate_from_simulation_positive_pnl(self):
        """Labels generated from positive P&L simulation."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result(total_pnl=100.0)

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")

        assert label_set.is_valid
        assert label_set.positive_net_pnl == 1
        assert label_set.net_pnl_return == pytest.approx(0.01, rel=0.01)
        assert label_set.max_drawdown == 0.15
        assert label_set.peak_capital_utilization == 0.65
        assert label_set.recovery_occurred == 1
        assert label_set.capital_exhaustion == 0

    def test_generate_from_simulation_negative_pnl(self):
        """Labels generated from negative P&L simulation."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result(total_pnl=-50.0)

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")

        assert label_set.is_valid
        assert label_set.positive_net_pnl == 0
        assert label_set.net_pnl_return < 0
        assert label_set.recovery_occurred == 0
        assert label_set.recovery_censored is True

    def test_generate_from_failed_simulation(self):
        """Failed simulations produce invalid label sets."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result(simulation_status="FAILED")

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")

        assert not label_set.is_valid
        assert label_set.simulation_status == SimulationStatus.FAILED
        assert label_set.positive_net_pnl is None

    def test_generate_from_incomplete_simulation(self):
        """Simulations with no candles produce invalid labels."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result(candles_processed=0)

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")

        assert not label_set.is_valid
        assert label_set.simulation_status == SimulationStatus.INCOMPLETE_DATA

    def test_generate_label_records(self):
        """Label records generated for each label type."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result()

        records = generator.generate_label_records(sim_result, horizon="30D")

        assert len(records) == len(LabelType)
        for record in records:
            assert record.is_valid
            assert record.label_version == LABEL_VERSION

    def test_label_set_to_dict(self):
        """LabelSet serializes to dict correctly."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result()

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")
        d = label_set.to_dict()

        assert "positive_net_pnl" in d
        assert "net_pnl_return" in d
        assert "max_drawdown" in d
        assert d["horizon"] == "30D"

    def test_validate_label_quality_valid(self):
        """Valid label set has no quality issues."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result()

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")
        issues = generator.validate_label_quality(label_set)

        assert issues == []

    def test_validate_label_quality_invalid(self):
        """Invalid label set reports issues."""
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        sim_result = create_mock_simulation_result(simulation_status="FAILED")

        label_set = generator.generate_from_simulation(sim_result, horizon="30D")
        issues = generator.validate_label_quality(label_set)

        assert len(issues) > 0


class TestLabelQualityMetrics:
    """Tests for LabelQualityMetrics."""

    def test_metrics_tracking(self):
        """Metrics track valid/invalid labels correctly."""
        metrics = LabelQualityMetrics()
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")

        # Valid positive
        sim1 = create_mock_simulation_result(total_pnl=100.0)
        metrics.add_label_set(generator.generate_from_simulation(sim1, "30D"))

        # Valid negative
        sim2 = create_mock_simulation_result(total_pnl=-50.0)
        metrics.add_label_set(generator.generate_from_simulation(sim2, "30D"))

        # Invalid
        sim3 = create_mock_simulation_result(simulation_status="FAILED")
        metrics.add_label_set(generator.generate_from_simulation(sim3, "30D"))

        assert metrics.total_labels == 3
        assert metrics.valid_labels == 2
        assert metrics.invalid_labels == 1
        assert metrics.positive_outcome_count == 1
        assert metrics.negative_outcome_count == 1
        assert metrics.positive_rate == 0.5

    def test_class_imbalance_ratio(self):
        """Class imbalance ratio calculated correctly."""
        metrics = LabelQualityMetrics()
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")

        # 1 positive, 3 negative
        metrics.add_label_set(
            generator.generate_from_simulation(
                create_mock_simulation_result(total_pnl=100.0), "30D"
            )
        )
        for _ in range(3):
            metrics.add_label_set(
                generator.generate_from_simulation(
                    create_mock_simulation_result(total_pnl=-50.0), "30D"
                )
            )

        assert metrics.class_imbalance_ratio == 3.0


class TestLabelDefinitions:
    """Tests for label definitions."""

    def test_all_label_types_have_definitions(self):
        """Every LabelType has a definition."""
        for label_type in LabelType:
            assert label_type in LABEL_DEFINITIONS

    def test_primary_label_is_decision_class(self):
        """Primary label is PRIMARY_DECISION class."""
        definition = LABEL_DEFINITIONS[LabelType.POSITIVE_NET_PNL]
        assert definition.label_class == LabelClass.PRIMARY_DECISION
        assert definition.value_type == "binary"
