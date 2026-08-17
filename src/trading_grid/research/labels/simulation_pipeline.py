"""
Simulation-based Label Pipeline.

Replaces synthetic label generation with real GridSimulator runs.

This module implements the causal label generation pipeline:
1. For each observation timestamp T, use only data ≤ T for blueprint generation
2. Run GridSimulator on future data (T, T+horizon]
3. Extract labels from SimulationResult via LabelGenerator

Key principles (per AI_RESEARCH_LABEL_SPEC.md):
- Labels come from VALID simulations only
- No future data leakage in blueprint generation
- Deterministic: same inputs produce same outputs
- Blueprint identity is preserved for traceability

Usage:
    pipeline = SimulationLabelPipeline(config)
    results = pipeline.run(market_ids=["BTC-USDT"], interval="1H")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from trading_grid.domain.grid.models import Blueprint, Section
from trading_grid.research.labels.generator import (
    LABEL_VERSION,
    LabelGenerator,
    LabelQualityMetrics,
    LabelSet,
    SimulationStatus,
)
from trading_grid.research.simulator.grid_simulator import (
    GridSimulator,
    SimulationConfig,
)

if TYPE_CHECKING:
    from trading_grid.domain.market.models import Candle
    from trading_grid.research.ingestion.storage import ParquetStorage

logger = structlog.get_logger()

# Pipeline version — bump when pipeline logic changes
SIMULATION_PIPELINE_VERSION = "sim-pipeline-v001"

# Horizon to candles mapping (for 1H interval)
HORIZON_CANDLES_1H: dict[str, int] = {
    "7D": 168,
    "30D": 720,
    "60D": 1440,
    "90D": 2160,
}

# Minimum candles required before observation for blueprint generation
MIN_WARMUP_CANDLES = 168  # 7 days of 1H candles


@dataclass
class ResearchBlueprintConfig:
    """
    Configuration for research blueprint generation.

    Blueprint parameters are derived deterministically from
    historical market state (volatility, price level) to ensure
    causal integrity — no ML model outputs are used.
    """

    # Capital per simulation (USDT)
    starting_capital: Decimal = Decimal("1000")

    # Grid spacing based on volatility regime (percentage)
    spacing_low_vol: Decimal = Decimal("0.5")  # Low volatility: tight grid
    spacing_mid_vol: Decimal = Decimal("1.0")  # Moderate volatility
    spacing_high_vol: Decimal = Decimal("2.0")  # High volatility: wide grid

    # Volatility thresholds (24h rolling std of 1H returns)
    vol_threshold_low: float = 0.01
    vol_threshold_high: float = 0.03

    # Section configuration
    section_count: int = 2
    grids_per_section: int = 5

    # Price range as percentage of current price
    price_range_pct: Decimal = Decimal("8")  # ±8% around current price

    # Capital allocation per section (must sum to ~100)
    section_capital_pcts: tuple[Decimal, ...] = (Decimal("60"), Decimal("40"))

    # Gap between sections (percentage)
    section_gap_pct: Decimal = Decimal("1.0")


@dataclass
class SimulationLabelPipelineConfig:
    """Configuration for the simulation label pipeline."""

    # Prediction horizon
    horizon: str = "30D"

    # Stride between observations (in candles)
    # Smaller stride = more labels but slower
    observation_stride: int = 24  # Every 24 hours for 1H candles

    # Simulation economics
    buy_fee_rate: float = 0.001
    sell_fee_rate: float = 0.001
    slippage_pct: float = 0.0005

    # Blueprint configuration
    blueprint_config: ResearchBlueprintConfig = field(
        default_factory=ResearchBlueprintConfig
    )

    # Maximum observations per market (None = unlimited)
    max_observations_per_market: int | None = None

    # Label version
    label_version: str = LABEL_VERSION


@dataclass
class ObservationResult:
    """Result of a single observation simulation."""

    market_id: str
    observation_timestamp: datetime
    blueprint_id: str
    simulation_run_id: str
    label_set: LabelSet
    candles_simulated: int
    duration_ms: float | None = None


@dataclass
class PipelineResults:
    """Aggregated results from the pipeline run."""

    total_observations: int = 0
    valid_labels: int = 0
    invalid_simulations: int = 0
    failed_simulations: int = 0
    observations_per_market: dict[str, int] = field(default_factory=dict)
    label_sets: list[LabelSet] = field(default_factory=list)
    quality_metrics: LabelQualityMetrics = field(default_factory=LabelQualityMetrics)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Percentage of observations that produced valid labels."""
        if self.total_observations == 0:
            return 0.0
        return self.valid_labels / self.total_observations

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "pipeline_version": SIMULATION_PIPELINE_VERSION,
            "total_observations": self.total_observations,
            "valid_labels": self.valid_labels,
            "invalid_simulations": self.invalid_simulations,
            "failed_simulations": self.failed_simulations,
            "success_rate": self.success_rate,
            "observations_per_market": self.observations_per_market,
            "errors": self.errors[:10],  # Limit error list
            "quality_metrics": self.quality_metrics.to_dict(),
        }


class ResearchBlueprintGenerator:
    """
    Generates deterministic blueprints for research/label generation.

    Unlike the production BlueprintGenerator (which uses ML recommendations),
    this generator derives blueprint parameters purely from historical
    market state to maintain causal integrity during training.

    The blueprint is anchored to the observation price and uses
    volatility-based spacing to adapt grid density to market conditions.
    """

    def __init__(self, config: ResearchBlueprintConfig | None = None) -> None:
        self.config = config or ResearchBlueprintConfig()

    def generate(
        self,
        market_id: str,
        observation_price: Decimal,
        volatility_24h: float,
        observation_timestamp: datetime,
    ) -> Blueprint:
        """
        Generate a deterministic blueprint from market state.

        Args:
            market_id: Market identifier
            observation_price: Price at observation time (anchor)
            volatility_24h: 24h rolling volatility (std of 1H returns)
            observation_timestamp: Observation timestamp

        Returns:
            Blueprint ready for simulation
        """
        if observation_price <= 0:
            raise ValueError(f"Observation price must be positive, got {observation_price}")

        # Determine grid spacing from volatility regime
        spacing = self._get_spacing_for_volatility(volatility_24h)

        # Calculate price range around observation price
        range_pct = self.config.price_range_pct
        upper_price = observation_price * (1 + range_pct / 100)
        lower_price = observation_price * (1 - range_pct / 100)

        # Generate sections
        sections = self._generate_sections(
            upper_price=upper_price,
            lower_price=lower_price,
            spacing=spacing,
        )

        # Deterministic blueprint ID (no UUID for reproducibility)
        ts_str = observation_timestamp.strftime("%Y%m%d%H%M")
        blueprint_id = f"RBP-{market_id}-{ts_str}"

        blueprint = Blueprint(
            blueprint_id=blueprint_id,
            market_id=market_id,
            total_capital=self.config.starting_capital,
            sections=sections,
            status="DRAFT",
            metadata={
                "generator": "research-blueprint-generator",
                "pipeline_version": SIMULATION_PIPELINE_VERSION,
                "observation_price": str(observation_price),
                "volatility_24h": volatility_24h,
                "spacing_pct": str(spacing),
                "generated_at": observation_timestamp.isoformat(),
            },
        )

        return blueprint

    def _get_spacing_for_volatility(self, volatility: float) -> Decimal:
        """Map volatility to grid spacing."""
        if volatility < self.config.vol_threshold_low:
            return self.config.spacing_low_vol
        elif volatility < self.config.vol_threshold_high:
            return self.config.spacing_mid_vol
        else:
            return self.config.spacing_high_vol

    def _generate_sections(
        self,
        upper_price: Decimal,
        lower_price: Decimal,
        spacing: Decimal,
    ) -> list[Section]:
        """Generate sections with uniform spacing and proper gaps."""
        sections: list[Section] = []
        section_count = self.config.section_count

        # Calculate gap in price units
        gap = self.config.section_gap_pct / 100 * upper_price

        # Total gaps between sections
        total_gaps = gap * (section_count - 1)

        # Available range for actual sections (excluding gaps)
        total_range = upper_price - lower_price
        available_range = total_range - total_gaps

        # Each section gets equal portion of available range
        section_range = available_range / section_count

        # Build sections from top to bottom
        current_upper = upper_price

        for i in range(section_count):
            section_upper = current_upper
            section_lower = section_upper - section_range

            # Get capital allocation for this section
            capital_pct = (
                self.config.section_capital_pcts[i]
                if i < len(self.config.section_capital_pcts)
                else Decimal("100") / section_count
            )

            section = Section(
                section_id=i + 1,
                upper_price=section_upper,
                lower_price=section_lower,
                grid_count=self.config.grids_per_section,
                grid_spacing_pct=spacing,
                capital_allocation_pct=capital_pct,
                gap_to_next_pct=(
                    self.config.section_gap_pct if i < section_count - 1 else None
                ),
            )
            sections.append(section)

            # Move to next section (accounting for gap)
            current_upper = section_lower - gap

        return sections


class SimulationLabelPipeline:
    """
    Pipeline for generating labels via GridSimulator.

    For each market and observation timestamp:
    1. Load historical candles up to observation time (for blueprint)
    2. Generate deterministic blueprint from market state
    3. Run GridSimulator on future candles (horizon)
    4. Extract labels from simulation result

    This ensures causal integrity: blueprint uses only past data,
    labels come from actual simulated future outcomes.
    """

    def __init__(
        self,
        storage: ParquetStorage,
        config: SimulationLabelPipelineConfig | None = None,
    ) -> None:
        self.storage = storage
        self.config = config or SimulationLabelPipelineConfig()
        self.blueprint_generator = ResearchBlueprintGenerator(
            self.config.blueprint_config
        )
        self.label_generator = LabelGenerator(
            universe_snapshot_id=f"universe-{datetime.now(UTC).strftime('%Y%m')}",
            label_version=self.config.label_version,
        )

    def run(
        self,
        market_ids: list[str],
        interval: str = "1H",
    ) -> PipelineResults:
        """
        Run the simulation label pipeline for multiple markets.

        Args:
            market_ids: List of market identifiers
            interval: Candle interval (default "1H")

        Returns:
            PipelineResults with all label sets and metrics
        """
        results = PipelineResults()

        logger.info(
            "simulation_label_pipeline_started",
            markets=market_ids,
            horizon=self.config.horizon,
            stride=self.config.observation_stride,
            pipeline_version=SIMULATION_PIPELINE_VERSION,
        )

        horizon_candles = self._get_horizon_candles(interval)

        for market_id in market_ids:
            try:
                market_results = self._run_market(
                    market_id=market_id,
                    interval=interval,
                    horizon_candles=horizon_candles,
                )

                results.total_observations += market_results.total_observations
                results.valid_labels += market_results.valid_labels
                results.invalid_simulations += market_results.invalid_simulations
                results.failed_simulations += market_results.failed_simulations
                results.observations_per_market[market_id] = (
                    market_results.total_observations
                )
                results.label_sets.extend(market_results.label_sets)
                results.errors.extend(market_results.errors)

                # Merge quality metrics
                for ls in market_results.label_sets:
                    results.quality_metrics.add_label_set(ls)

            except Exception as e:
                logger.error("market_pipeline_failed", market_id=market_id, error=str(e))
                results.errors.append(f"{market_id}: {e}")

        results.completed_at = datetime.now(UTC)

        logger.info(
            "simulation_label_pipeline_completed",
            total_observations=results.total_observations,
            valid_labels=results.valid_labels,
            success_rate=results.success_rate,
        )

        return results

    def _run_market(
        self,
        market_id: str,
        interval: str,
        horizon_candles: int,
    ) -> PipelineResults:
        """Run pipeline for a single market."""
        results = PipelineResults()

        # Load all candles for this market
        candles = self.storage.load_candles(market_id, interval)
        if not candles:
            results.errors.append(f"{market_id}: no candles found")
            return results

        # Sort by timestamp
        candles = sorted(candles, key=lambda c: c.timestamp)

        # Determine observation indices
        # Start after warmup period, end before horizon runs out
        start_idx = MIN_WARMUP_CANDLES
        end_idx = len(candles) - horizon_candles

        if end_idx <= start_idx:
            results.errors.append(
                f"{market_id}: insufficient candles ({len(candles)}) "
                f"for warmup ({MIN_WARMUP_CANDLES}) + horizon ({horizon_candles})"
            )
            return results

        # Generate observations at stride intervals
        observation_indices = list(range(start_idx, end_idx, self.config.observation_stride))

        # Limit observations if configured
        if self.config.max_observations_per_market:
            observation_indices = observation_indices[
                : self.config.max_observations_per_market
            ]

        logger.info(
            "market_simulation_started",
            market_id=market_id,
            total_candles=len(candles),
            observations=len(observation_indices),
            horizon_candles=horizon_candles,
        )

        for obs_idx in observation_indices:
            try:
                obs_result = self._run_observation(
                    market_id=market_id,
                    candles=candles,
                    observation_index=obs_idx,
                    horizon_candles=horizon_candles,
                )

                results.total_observations += 1
                results.label_sets.append(obs_result.label_set)

                if obs_result.label_set.is_valid:
                    results.valid_labels += 1
                elif obs_result.label_set.simulation_status == SimulationStatus.FAILED:
                    results.failed_simulations += 1
                else:
                    results.invalid_simulations += 1

            except Exception as e:
                logger.warning(
                    "observation_failed",
                    market_id=market_id,
                    index=obs_idx,
                    error=str(e),
                )
                results.total_observations += 1
                results.failed_simulations += 1
                results.errors.append(f"{market_id}[{obs_idx}]: {e}")

        return results

    def _run_observation(
        self,
        market_id: str,
        candles: list[Candle],
        observation_index: int,
        horizon_candles: int,
    ) -> ObservationResult:
        """Run simulation for a single observation."""
        start_time = datetime.now(UTC)

        observation_candle = candles[observation_index]
        observation_timestamp = observation_candle.timestamp
        observation_price = observation_candle.close

        # Compute volatility from historical window (causal: only past data)
        volatility = self._compute_volatility(candles, observation_index)

        # Generate blueprint from market state at observation time
        blueprint = self.blueprint_generator.generate(
            market_id=market_id,
            observation_price=observation_price,
            volatility_24h=volatility,
            observation_timestamp=observation_timestamp,
        )

        # Future candles for simulation (T+1 to T+horizon)
        future_candles = candles[
            observation_index + 1 : observation_index + 1 + horizon_candles
        ]

        # Configure simulation
        sim_config = SimulationConfig(
            market_id=market_id,
            observation_timestamp=observation_timestamp,
            simulation_horizon_candles=horizon_candles,
            starting_capital=self.config.blueprint_config.starting_capital,
            buy_fee_rate=self.config.buy_fee_rate,
            sell_fee_rate=self.config.sell_fee_rate,
            slippage_pct=self.config.slippage_pct,
        )

        # Run simulation
        simulator = GridSimulator(sim_config)
        sim_result = simulator.run(blueprint, future_candles)

        # Generate labels from simulation result
        label_set = self.label_generator.generate_from_simulation(
            sim_result,
            horizon=self.config.horizon,
        )

        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

        return ObservationResult(
            market_id=market_id,
            observation_timestamp=observation_timestamp,
            blueprint_id=blueprint.blueprint_id,
            simulation_run_id=sim_result.simulation_run_id,
            label_set=label_set,
            candles_simulated=len(future_candles),
            duration_ms=duration_ms,
        )

    def _compute_volatility(
        self,
        candles: list[Candle],
        observation_index: int,
        window: int = 24,
    ) -> float:
        """
        Compute 24h rolling volatility from historical candles.

        Uses only data ≤ observation_index (causal).
        """
        if observation_index < window:
            return 0.02  # Default moderate volatility

        # Get close prices for the window
        window_candles = candles[observation_index - window + 1 : observation_index + 1]
        closes = [float(c.close) for c in window_candles]

        # Compute returns
        returns = [
            (closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes))
        ]

        if not returns:
            return 0.02

        # Standard deviation
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
        return variance**0.5

    def _get_horizon_candles(self, interval: str) -> int:
        """Get number of candles for the configured horizon."""
        if interval == "1H":
            return HORIZON_CANDLES_1H.get(self.config.horizon, 720)
        elif interval == "4H":
            # Scale down by 4
            base = HORIZON_CANDLES_1H.get(self.config.horizon, 720)
            return base // 4
        elif interval == "1D":
            # Scale down by 24
            base = HORIZON_CANDLES_1H.get(self.config.horizon, 720)
            return base // 24
        else:
            # Default to 30D of 1H
            return 720


def labels_to_dataframe(label_sets: list[LabelSet]) -> Any:
    """
    Convert label sets to pandas DataFrame for dataset building.

    Returns a DataFrame with columns matching the expected
    label schema for the dataset builder.
    """
    import pandas as pd

    records = []
    for ls in label_sets:
        if not ls.is_valid:
            continue

        record = {
            "market_id": ls.market_id,
            "timestamp": ls.observation_timestamp,
            "blueprint_id": ls.blueprint_id,
            "horizon": ls.horizon,
            "positive_pnl": ls.positive_net_pnl,
            "net_pnl_return": ls.net_pnl_return,
            "max_drawdown": ls.max_drawdown,
            "capital_utilization": ls.peak_capital_utilization,
            "recovered": ls.recovery_occurred,
            "recovery_censored": ls.recovery_censored,
            "max_section_depth": ls.max_section_depth,
            "capital_exhausted": ls.capital_exhaustion,
            "label_version": ls.label_version,
            "simulator_version": ls.simulator_version,
        }
        records.append(record)

    return pd.DataFrame(records)