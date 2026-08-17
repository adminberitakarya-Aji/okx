"""
Unit tests for the simulation-based label pipeline.

Tests cover:
- ResearchBlueprintGenerator determinism and causal integrity
- SimulationLabelPipeline end-to-end flow
- Label extraction from simulation results
- Volatility computation causality
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from trading_grid.domain.grid.models import Blueprint
from trading_grid.domain.market.models import Candle
from trading_grid.research.labels.simulation_pipeline import (
    HORIZON_CANDLES_1H,
    SIMULATION_PIPELINE_VERSION,
    PipelineResults,
    ResearchBlueprintConfig,
    ResearchBlueprintGenerator,
    SimulationLabelPipeline,
    SimulationLabelPipelineConfig,
    labels_to_dataframe,
)

# =============================================================================
# Fixtures
# =============================================================================


def make_candle(
    timestamp: datetime,
    open_price: float = 50000.0,
    high: float = 51000.0,
    low: float = 49000.0,
    close: float = 50500.0,
    volume: float = 100.0,
    market_id: str = "BTC-USDT",
) -> Candle:
    """Create a test candle."""
    return Candle(
        market_id=market_id,
        timestamp=timestamp,
        open=Decimal(str(open_price)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
        quote_volume=Decimal(str(volume * close)),
    )


def make_candles(count: int, start_price: float = 50000.0) -> list[Candle]:
    """Create a list of test candles with slight price variation."""
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    candles = []
    price = start_price
    for i in range(count):
        # Simple sine wave pattern for price variation
        import math

        variation = math.sin(i / 24 * math.pi) * 0.02  # ±2% over 24h cycle
        current_price = start_price * (1 + variation)
        candles.append(
            make_candle(
                timestamp=base_time + timedelta(hours=i),
                open_price=price,
                high=current_price * 1.01,
                low=current_price * 0.99,
                close=current_price,
                volume=100 + i % 10,
            )
        )
        price = current_price
    return candles


@pytest.fixture
def blueprint_config() -> ResearchBlueprintConfig:
    """Default blueprint config for tests."""
    return ResearchBlueprintConfig(
        starting_capital=Decimal("1000"),
        section_count=2,
        grids_per_section=5,
        price_range_pct=Decimal("8"),
    )


@pytest.fixture
def blueprint_generator(blueprint_config: ResearchBlueprintConfig) -> ResearchBlueprintGenerator:
    """Blueprint generator instance."""
    return ResearchBlueprintGenerator(blueprint_config)


@pytest.fixture
def mock_storage() -> MagicMock:
    """Mock ParquetStorage."""
    storage = MagicMock()
    storage.load_candles.return_value = make_candles(1000)
    return storage


@pytest.fixture
def pipeline_config() -> SimulationLabelPipelineConfig:
    """Pipeline config for tests."""
    return SimulationLabelPipelineConfig(
        horizon="7D",  # Shorter horizon for faster tests
        observation_stride=168,  # Weekly observations
        max_observations_per_market=3,  # Limit for test speed
    )


# =============================================================================
# ResearchBlueprintGenerator Tests
# =============================================================================


class TestResearchBlueprintGenerator:
    """Tests for ResearchBlueprintGenerator."""

    def test_generate_returns_valid_blueprint(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Blueprint should have valid structure."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        assert isinstance(blueprint, Blueprint)
        assert blueprint.market_id == "BTC-USDT"
        assert blueprint.total_capital == Decimal("1000")
        assert len(blueprint.sections) == 2
        assert blueprint.status == "DRAFT"

    def test_blueprint_id_is_deterministic(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Same inputs should produce same blueprint ID."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        bp1 = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )
        bp2 = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        assert bp1.blueprint_id == bp2.blueprint_id
        assert "RBP-BTC-USDT-202606151200" in bp1.blueprint_id

    def test_low_volatility_uses_tight_spacing(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Low volatility should result in tighter grid spacing."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.005,  # Below threshold
            observation_timestamp=observation_time,
        )

        # Check spacing in metadata
        assert blueprint.metadata["spacing_pct"] == "0.5"

    def test_high_volatility_uses_wide_spacing(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """High volatility should result in wider grid spacing."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.05,  # Above threshold
            observation_timestamp=observation_time,
        )

        assert blueprint.metadata["spacing_pct"] == "2.0"

    def test_sections_are_ordered_top_to_bottom(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Sections should be ordered from highest to lowest price."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        for i in range(len(blueprint.sections) - 1):
            assert blueprint.sections[i].upper_price > blueprint.sections[i + 1].upper_price

    def test_section_prices_bracket_observation_price(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Grid range should bracket the observation price."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
        observation_price = Decimal("50000")

        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=observation_price,
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        top_price = blueprint.sections[0].upper_price
        bottom_price = blueprint.sections[-1].lower_price

        assert top_price > observation_price
        assert bottom_price < observation_price

    def test_invalid_price_raises_error(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Zero or negative price should raise ValueError."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        with pytest.raises(ValueError, match="positive"):
            blueprint_generator.generate(
                market_id="BTC-USDT",
                observation_price=Decimal("0"),
                volatility_24h=0.02,
                observation_timestamp=observation_time,
            )

    def test_metadata_contains_provenance(
        self, blueprint_generator: ResearchBlueprintGenerator
    ) -> None:
        """Blueprint metadata should contain provenance info."""
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        blueprint = blueprint_generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        assert blueprint.metadata["generator"] == "research-blueprint-generator"
        assert blueprint.metadata["pipeline_version"] == SIMULATION_PIPELINE_VERSION
        assert "observation_price" in blueprint.metadata
        assert "volatility_24h" in blueprint.metadata


# =============================================================================
# SimulationLabelPipeline Tests
# =============================================================================


class TestSimulationLabelPipeline:
    """Tests for SimulationLabelPipeline."""

    def test_pipeline_runs_without_error(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Pipeline should complete without exceptions."""
        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        results = pipeline.run(market_ids=["BTC-USDT"], interval="1H")

        assert isinstance(results, PipelineResults)
        assert results.total_observations >= 0

    def test_pipeline_respects_max_observations(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Pipeline should limit observations per market."""
        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        results = pipeline.run(market_ids=["BTC-USDT"], interval="1H")

        assert results.total_observations <= pipeline_config.max_observations_per_market

    def test_pipeline_handles_empty_candles(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Pipeline should handle markets with no data gracefully."""
        mock_storage.load_candles.return_value = []

        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        results = pipeline.run(market_ids=["BTC-USDT"], interval="1H")

        assert results.total_observations == 0
        assert len(results.errors) > 0

    def test_pipeline_handles_insufficient_candles(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Pipeline should handle insufficient data for warmup + horizon."""
        # Only 100 candles - not enough for warmup (168) + horizon (168)
        mock_storage.load_candles.return_value = make_candles(100)

        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        results = pipeline.run(market_ids=["BTC-USDT"], interval="1H")

        assert results.total_observations == 0
        assert any("insufficient candles" in e for e in results.errors)

    def test_volatility_computation_is_causal(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Volatility should only use data up to observation index."""
        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        candles = make_candles(200)

        # Volatility at index 100 should only use candles 77-100 (24h window)
        vol = pipeline._compute_volatility(candles, observation_index=100, window=24)

        assert isinstance(vol, float)
        assert vol >= 0

    def test_volatility_default_for_early_observations(
        self, mock_storage: MagicMock, pipeline_config: SimulationLabelPipelineConfig
    ) -> None:
        """Early observations should use default volatility."""
        pipeline = SimulationLabelPipeline(storage=mock_storage, config=pipeline_config)
        candles = make_candles(200)

        # Index 10 < window 24, should return default
        vol = pipeline._compute_volatility(candles, observation_index=10, window=24)

        assert vol == 0.02  # Default moderate volatility

    def test_horizon_candles_mapping(self) -> None:
        """Horizon strings should map to correct candle counts."""
        assert HORIZON_CANDLES_1H["7D"] == 168
        assert HORIZON_CANDLES_1H["30D"] == 720
        assert HORIZON_CANDLES_1H["60D"] == 1440
        assert HORIZON_CANDLES_1H["90D"] == 2160


# =============================================================================
# PipelineResults Tests
# =============================================================================


class TestPipelineResults:
    """Tests for PipelineResults dataclass."""

    def test_success_rate_calculation(self) -> None:
        """Success rate should be valid_labels / total_observations."""
        results = PipelineResults(
            total_observations=100,
            valid_labels=80,
            invalid_simulations=15,
            failed_simulations=5,
        )

        assert results.success_rate == 0.8

    def test_success_rate_zero_observations(self) -> None:
        """Success rate should be 0 when no observations."""
        results = PipelineResults(total_observations=0)

        assert results.success_rate == 0.0

    def test_to_dict_contains_required_fields(self) -> None:
        """to_dict should contain all required fields."""
        results = PipelineResults(
            total_observations=10,
            valid_labels=8,
        )

        d = results.to_dict()

        assert d["pipeline_version"] == SIMULATION_PIPELINE_VERSION
        assert d["total_observations"] == 10
        assert d["valid_labels"] == 8
        assert "success_rate" in d
        assert "quality_metrics" in d


# =============================================================================
# labels_to_dataframe Tests
# =============================================================================


class TestLabelsToDataframe:
    """Tests for labels_to_dataframe function."""

    def test_empty_label_sets_returns_empty_dataframe(self) -> None:
        """Empty label list should return empty DataFrame."""
        import pandas as pd

        df = labels_to_dataframe([])

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_invalid_labels_are_excluded(self) -> None:
        """Invalid label sets should not appear in DataFrame."""
        from trading_grid.research.labels.generator import LabelSet

        # Create a mock invalid label set
        invalid_label = MagicMock(spec=LabelSet)
        invalid_label.is_valid = False

        df = labels_to_dataframe([invalid_label])

        assert len(df) == 0


# =============================================================================
# Integration-style Tests
# =============================================================================


class TestPipelineIntegration:
    """Integration-style tests with real components."""

    def test_blueprint_to_simulation_flow(self) -> None:
        """Blueprint should be usable by GridSimulator."""
        from trading_grid.research.simulator.grid_simulator import (
            GridSimulator,
            SimulationConfig,
        )

        # Generate blueprint
        generator = ResearchBlueprintGenerator()
        observation_time = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)

        blueprint = generator.generate(
            market_id="BTC-USDT",
            observation_price=Decimal("50000"),
            volatility_24h=0.02,
            observation_timestamp=observation_time,
        )

        # Create future candles
        future_candles = make_candles(168, start_price=50000.0)

        # Run simulation
        config = SimulationConfig(
            market_id="BTC-USDT",
            observation_timestamp=observation_time,
            simulation_horizon_candles=168,
            starting_capital=Decimal("1000"),
        )

        simulator = GridSimulator(config)
        result = simulator.run(blueprint, future_candles)

        assert result.market_id == "BTC-USDT"
        assert result.blueprint_id == blueprint.blueprint_id
        assert result.candles_processed == 168

    def test_full_observation_flow(self) -> None:
        """Full flow from candles to labels should work."""
        from trading_grid.research.labels.generator import LabelGenerator

        # Setup
        candles = make_candles(500)
        observation_index = 200
        horizon_candles = 168

        observation_candle = candles[observation_index]

        # Generate blueprint
        generator = ResearchBlueprintGenerator()
        blueprint = generator.generate(
            market_id="BTC-USDT",
            observation_price=observation_candle.close,
            volatility_24h=0.02,
            observation_timestamp=observation_candle.timestamp,
        )

        # Get future candles
        future_candles = candles[observation_index + 1 : observation_index + 1 + horizon_candles]

        # Run simulation
        from trading_grid.research.simulator.grid_simulator import (
            GridSimulator,
            SimulationConfig,
        )

        config = SimulationConfig(
            market_id="BTC-USDT",
            observation_timestamp=observation_candle.timestamp,
            simulation_horizon_candles=horizon_candles,
            starting_capital=Decimal("1000"),
        )

        simulator = GridSimulator(config)
        sim_result = simulator.run(blueprint, future_candles)

        # Generate labels
        label_gen = LabelGenerator(
            universe_snapshot_id="test-universe",
            label_version="test-v1",
        )
        label_set = label_gen.generate_from_simulation(sim_result, horizon="7D")

        assert label_set.market_id == "BTC-USDT"
        assert label_set.blueprint_id == blueprint.blueprint_id
        assert label_set.horizon == "7D"
