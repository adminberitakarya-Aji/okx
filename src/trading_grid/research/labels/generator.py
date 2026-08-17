"""
Label Generator for AI Research Pipeline.

Implements label generation per AI_RESEARCH_LABEL_SPEC.md.

Labels are generated from valid grid simulations:
- LBL-001: Positive Net P&L Probability (primary target)
- LBL-002: Expected Net P&L
- LBL-003: Expected Maximum Drawdown
- LBL-004: Peak Capital Utilization
- LBL-005: Recovery Probability
- LBL-007: Maximum Section Depth
- LBL-008: Capital Exhaustion Probability

Key principles:
- Labels come from VALID simulations only
- Failed simulation != negative outcome
- Every label has observation timestamp and horizon
- Blueprint identity is preserved
- Censoring is explicit (event_occurred flag)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from datetime import datetime

from trading_grid.research.simulator.grid_simulator import (
    EXECUTION_MODEL_VERSION,
    SIMULATOR_VERSION,
    SimulationResult,
)

logger = structlog.get_logger()

# Label version — bump when label definitions change
LABEL_VERSION = "label-v001"

# Supported horizons per spec §27
SUPPORTED_HORIZONS = ("7D", "30D", "60D", "90D")


class LabelType(StrEnum):
    """Label types per spec §18."""

    # Class A — Primary Decision Target
    POSITIVE_NET_PNL = "positive_net_pnl"

    # Class B — Economic Targets
    NET_PNL_RETURN = "net_pnl_return"
    CAPITAL_UTILIZATION = "capital_utilization"

    # Class C — Risk / Recovery Targets
    MAX_DRAWDOWN = "max_drawdown"
    RECOVERY_OCCURRED = "recovery_occurred"
    MAX_SECTION_DEPTH = "max_section_depth"
    CAPITAL_EXHAUSTION = "capital_exhaustion"


class SimulationStatus(StrEnum):
    """Simulation validity for label generation (spec §32, §39)."""

    VALID = "VALID"
    INVALID_BLUEPRINT = "INVALID_BLUEPRINT"
    FAILED = "FAILED"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"


class LabelClass(StrEnum):
    """Label classification per spec §18."""

    PRIMARY_DECISION = "PRIMARY_DECISION"
    ECONOMIC = "ECONOMIC"
    RISK_RECOVERY = "RISK_RECOVERY"


# Mapping from label type to class
LABEL_CLASS_MAP: dict[LabelType, LabelClass] = {
    LabelType.POSITIVE_NET_PNL: LabelClass.PRIMARY_DECISION,
    LabelType.NET_PNL_RETURN: LabelClass.ECONOMIC,
    LabelType.CAPITAL_UTILIZATION: LabelClass.ECONOMIC,
    LabelType.MAX_DRAWDOWN: LabelClass.RISK_RECOVERY,
    LabelType.RECOVERY_OCCURRED: LabelClass.RISK_RECOVERY,
    LabelType.MAX_SECTION_DEPTH: LabelClass.RISK_RECOVERY,
    LabelType.CAPITAL_EXHAUSTION: LabelClass.RISK_RECOVERY,
}


@dataclass(frozen=True)
class LabelDefinition:
    """Definition of a label type (spec §35)."""

    label_type: LabelType
    label_class: LabelClass
    description: str
    value_type: str  # "binary", "continuous", "ordinal"
    valid_range: tuple[float, float] | None = None
    requires_censoring: bool = False


# Label definitions registry
LABEL_DEFINITIONS: dict[LabelType, LabelDefinition] = {
    LabelType.POSITIVE_NET_PNL: LabelDefinition(
        label_type=LabelType.POSITIVE_NET_PNL,
        label_class=LabelClass.PRIMARY_DECISION,
        description="P(Net P&L > 0 | Market State, Execution Economics, Blueprint)",
        value_type="binary",
        valid_range=(0.0, 1.0),
    ),
    LabelType.NET_PNL_RETURN: LabelDefinition(
        label_type=LabelType.NET_PNL_RETURN,
        label_class=LabelClass.ECONOMIC,
        description="Future Net P&L / Starting Capital",
        value_type="continuous",
    ),
    LabelType.MAX_DRAWDOWN: LabelDefinition(
        label_type=LabelType.MAX_DRAWDOWN,
        label_class=LabelClass.RISK_RECOVERY,
        description="Maximum strategy drawdown as percentage of starting capital",
        value_type="continuous",
        valid_range=(0.0, 1.0),
    ),
    LabelType.CAPITAL_UTILIZATION: LabelDefinition(
        label_type=LabelType.CAPITAL_UTILIZATION,
        label_class=LabelClass.ECONOMIC,
        description="Peak capital deployment / starting capital",
        value_type="continuous",
        valid_range=(0.0, 1.0),
    ),
    LabelType.RECOVERY_OCCURRED: LabelDefinition(
        label_type=LabelType.RECOVERY_OCCURRED,
        label_class=LabelClass.RISK_RECOVERY,
        description="Whether recovery condition was achieved within horizon",
        value_type="binary",
        valid_range=(0.0, 1.0),
        requires_censoring=True,
    ),
    LabelType.MAX_SECTION_DEPTH: LabelDefinition(
        label_type=LabelType.MAX_SECTION_DEPTH,
        label_class=LabelClass.RISK_RECOVERY,
        description="Deepest section reached during simulation",
        value_type="ordinal",
    ),
    LabelType.CAPITAL_EXHAUSTION: LabelDefinition(
        label_type=LabelType.CAPITAL_EXHAUSTION,
        label_class=LabelClass.RISK_RECOVERY,
        description="Whether deployable capital was exhausted",
        value_type="binary",
        valid_range=(0.0, 1.0),
    ),
}


@dataclass
class LabelRecord:
    """
    A single generated label record (spec §35).

    Contains all metadata required for traceability and reproducibility.
    """

    label_id: str
    market_id: str
    universe_snapshot_id: str
    observation_timestamp: datetime
    blueprint_id: str
    horizon: str
    label_type: LabelType
    label_value: float | None
    label_class: LabelClass

    # Censoring support (spec §30)
    event_occurred: bool | None = None
    observed_until: datetime | None = None

    # Simulation metadata
    simulation_status: SimulationStatus = SimulationStatus.VALID
    simulation_run_id: str | None = None
    simulator_version: str = SIMULATOR_VERSION
    execution_model_version: str = EXECUTION_MODEL_VERSION
    label_version: str = LABEL_VERSION

    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Label is valid only if simulation was valid and value exists."""
        return self.simulation_status == SimulationStatus.VALID and self.label_value is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "label_id": self.label_id,
            "market_id": self.market_id,
            "universe_snapshot_id": self.universe_snapshot_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "blueprint_id": self.blueprint_id,
            "horizon": self.horizon,
            "label_type": self.label_type.value,
            "label_value": self.label_value,
            "label_class": self.label_class.value,
            "event_occurred": self.event_occurred,
            "observed_until": (self.observed_until.isoformat() if self.observed_until else None),
            "simulation_status": self.simulation_status.value,
            "simulation_run_id": self.simulation_run_id,
            "simulator_version": self.simulator_version,
            "execution_model_version": self.execution_model_version,
            "label_version": self.label_version,
            "metadata": self.metadata,
        }


@dataclass
class LabelSet:
    """
    Complete label set for one observation (spec §26).

    Contains all labels generated from a single simulation run.
    """

    market_id: str
    observation_timestamp: datetime
    blueprint_id: str
    horizon: str
    universe_snapshot_id: str
    simulation_run_id: str
    simulation_status: SimulationStatus

    # Individual labels
    positive_net_pnl: int | None = None  # LBL-001
    net_pnl_return: float | None = None  # LBL-002
    max_drawdown: float | None = None  # LBL-003
    peak_capital_utilization: float | None = None  # LBL-004
    recovery_occurred: int | None = None  # LBL-005
    max_section_depth: int | None = None  # LBL-007
    capital_exhaustion: int | None = None  # LBL-008

    # Censoring flags
    recovery_censored: bool = False

    # Metadata
    label_version: str = LABEL_VERSION
    simulator_version: str = SIMULATOR_VERSION
    execution_model_version: str = EXECUTION_MODEL_VERSION

    @property
    def is_complete(self) -> bool:
        """All primary labels are present."""
        return (
            self.positive_net_pnl is not None
            and self.net_pnl_return is not None
            and self.max_drawdown is not None
        )

    @property
    def is_valid(self) -> bool:
        """Label set is valid only if simulation was valid."""
        return self.simulation_status == SimulationStatus.VALID

    def to_dict(self) -> dict[str, Any]:
        """Convert to flat dictionary for dataset builder."""
        return {
            "positive_net_pnl": self.positive_net_pnl,
            "net_pnl_return": self.net_pnl_return,
            "max_drawdown": self.max_drawdown,
            "peak_capital_utilization": self.peak_capital_utilization,
            "recovery_occurred": self.recovery_occurred,
            "recovery_censored": self.recovery_censored,
            "max_section_depth": self.max_section_depth,
            "capital_exhaustion": self.capital_exhaustion,
            "label_start": self.observation_timestamp.isoformat(),
            "horizon": self.horizon,
        }


class LabelGenerator:
    """
    Generates labels from simulation results.

    Usage:
        generator = LabelGenerator(universe_snapshot_id="universe-2024-01")
        label_set = generator.generate_from_simulation(
            sim_result, horizon="30D"
        )
    """

    def __init__(
        self,
        universe_snapshot_id: str,
        label_version: str = LABEL_VERSION,
    ) -> None:
        self.universe_snapshot_id = universe_snapshot_id
        self.label_version = label_version
        self._label_counter = 0

    def _next_label_id(self) -> str:
        """Generate sequential label ID."""
        self._label_counter += 1
        return f"LBL-{self._label_counter:08d}"

    def generate_from_simulation(
        self,
        sim_result: SimulationResult,
        horizon: str,
        recovery_threshold: float = 0.0,
    ) -> LabelSet:
        """
        Generate complete label set from a simulation result.

        Args:
            sim_result: Completed simulation result
            horizon: Prediction horizon (e.g., "7D", "30D", "90D")
            recovery_threshold: Net P&L threshold for recovery (default: break-even)

        Returns:
            LabelSet with all labels populated from simulation
        """
        if horizon not in SUPPORTED_HORIZONS:
            logger.warning("unsupported_horizon", horizon=horizon)

        # Determine simulation validity
        sim_status = self._determine_simulation_status(sim_result)

        # Create label set
        label_set = LabelSet(
            market_id=sim_result.market_id,
            observation_timestamp=sim_result.observation_timestamp,
            blueprint_id=sim_result.blueprint_id,
            horizon=horizon,
            universe_snapshot_id=self.universe_snapshot_id,
            simulation_run_id=sim_result.simulation_run_id,
            simulation_status=sim_status,
            label_version=self.label_version,
            simulator_version=sim_result.simulator_version,
            execution_model_version=sim_result.execution_model_version,
        )

        # Only generate labels from valid simulations (spec §32)
        if sim_status != SimulationStatus.VALID:
            logger.info(
                "label_generation_skipped",
                reason=sim_status.value,
                simulation_run_id=sim_result.simulation_run_id,
            )
            return label_set

        # LBL-001: Positive Net P&L (primary target)
        # 1 = Net P&L > 0, 0 = Net P&L <= 0
        label_set.positive_net_pnl = 1 if sim_result.total_pnl > 0 else 0

        # LBL-002: Expected Net P&L (normalized return)
        if sim_result.initial_capital > 0:
            label_set.net_pnl_return = float(sim_result.total_pnl / sim_result.initial_capital)
        else:
            label_set.net_pnl_return = 0.0

        # LBL-003: Maximum Drawdown (as percentage)
        label_set.max_drawdown = sim_result.max_drawdown_pct

        # LBL-004: Peak Capital Utilization
        label_set.peak_capital_utilization = sim_result.peak_capital_utilization

        # LBL-005: Recovery Occurred
        # Recovery = net P&L became positive at any point (approximated by final state)
        # In a full implementation, this would track intra-horizon recovery events
        recovery_occurred = sim_result.total_pnl > 0
        label_set.recovery_occurred = 1 if recovery_occurred else 0
        label_set.recovery_censored = not recovery_occurred

        # LBL-007: Maximum Section Depth
        label_set.max_section_depth = sim_result.max_section_depth

        # LBL-008: Capital Exhaustion
        label_set.capital_exhaustion = 1 if sim_result.capital_exhausted else 0

        logger.debug(
            "labels_generated",
            market_id=sim_result.market_id,
            blueprint_id=sim_result.blueprint_id,
            horizon=horizon,
            positive_net_pnl=label_set.positive_net_pnl,
            net_pnl_return=label_set.net_pnl_return,
        )

        return label_set

    def generate_label_records(
        self,
        sim_result: SimulationResult,
        horizon: str,
    ) -> list[LabelRecord]:
        """
        Generate individual label records from simulation.

        Returns one LabelRecord per label type for detailed storage.
        """
        label_set = self.generate_from_simulation(sim_result, horizon)
        records: list[LabelRecord] = []

        if not label_set.is_valid:
            # Return invalid records for traceability
            for label_type in LabelType:
                record = LabelRecord(
                    label_id=self._next_label_id(),
                    market_id=sim_result.market_id,
                    universe_snapshot_id=self.universe_snapshot_id,
                    observation_timestamp=sim_result.observation_timestamp,
                    blueprint_id=sim_result.blueprint_id,
                    horizon=horizon,
                    label_type=label_type,
                    label_value=None,
                    label_class=LABEL_CLASS_MAP[label_type],
                    simulation_status=label_set.simulation_status,
                    simulation_run_id=sim_result.simulation_run_id,
                    simulator_version=sim_result.simulator_version,
                    execution_model_version=sim_result.execution_model_version,
                    label_version=self.label_version,
                )
                records.append(record)
            return records

        # Generate valid records
        label_values: dict[LabelType, float | None] = {
            LabelType.POSITIVE_NET_PNL: (
                float(label_set.positive_net_pnl)
                if label_set.positive_net_pnl is not None
                else None
            ),
            LabelType.NET_PNL_RETURN: label_set.net_pnl_return,
            LabelType.MAX_DRAWDOWN: label_set.max_drawdown,
            LabelType.CAPITAL_UTILIZATION: label_set.peak_capital_utilization,
            LabelType.RECOVERY_OCCURRED: (
                float(label_set.recovery_occurred)
                if label_set.recovery_occurred is not None
                else None
            ),
            LabelType.MAX_SECTION_DEPTH: (
                float(label_set.max_section_depth)
                if label_set.max_section_depth is not None
                else None
            ),
            LabelType.CAPITAL_EXHAUSTION: (
                float(label_set.capital_exhaustion)
                if label_set.capital_exhaustion is not None
                else None
            ),
        }

        for label_type, value in label_values.items():
            definition = LABEL_DEFINITIONS[label_type]
            record = LabelRecord(
                label_id=self._next_label_id(),
                market_id=sim_result.market_id,
                universe_snapshot_id=self.universe_snapshot_id,
                observation_timestamp=sim_result.observation_timestamp,
                blueprint_id=sim_result.blueprint_id,
                horizon=horizon,
                label_type=label_type,
                label_value=value,
                label_class=definition.label_class,
                event_occurred=(bool(value == 1.0) if definition.value_type == "binary" else None),
                simulation_status=SimulationStatus.VALID,
                simulation_run_id=sim_result.simulation_run_id,
                simulator_version=sim_result.simulator_version,
                execution_model_version=sim_result.execution_model_version,
                label_version=self.label_version,
            )
            records.append(record)

        return records

    def _determine_simulation_status(self, sim_result: SimulationResult) -> SimulationStatus:
        """
        Determine simulation validity for label generation.

        Per spec §32: A label is valid only when:
        - Input data complete enough
        - Execution model valid
        - Blueprint valid
        - Simulation completed
        - Outcome calculation valid
        """
        if sim_result.simulation_status == "FAILED":
            return SimulationStatus.FAILED

        if sim_result.simulation_status != "COMPLETED":
            return SimulationStatus.INCOMPLETE_DATA

        if sim_result.candles_processed == 0:
            return SimulationStatus.INCOMPLETE_DATA

        # Check for invalid blueprint indicators
        if (
            sim_result.terminal_condition is not None
            and sim_result.terminal_condition.value == "INVALID_STATE"
        ):
            return SimulationStatus.INVALID_BLUEPRINT

        return SimulationStatus.VALID

    def validate_label_quality(self, label_set: LabelSet) -> list[str]:
        """
        Validate label quality and return list of issues.

        Per spec §32: Invalid simulation runs must be marked explicitly.
        """
        issues: list[str] = []

        if not label_set.is_valid:
            issues.append(f"Simulation status is {label_set.simulation_status.value}")
            return issues

        # Check primary labels
        if label_set.positive_net_pnl is None:
            issues.append("Missing primary label: positive_net_pnl")

        if label_set.net_pnl_return is None:
            issues.append("Missing label: net_pnl_return")

        if label_set.max_drawdown is None:
            issues.append("Missing label: max_drawdown")

        # Validate ranges
        if label_set.max_drawdown is not None and (
            label_set.max_drawdown < 0 or label_set.max_drawdown > 1
        ):
            issues.append(f"max_drawdown out of range: {label_set.max_drawdown}")

        if label_set.peak_capital_utilization is not None and (
            label_set.peak_capital_utilization < 0 or label_set.peak_capital_utilization > 1
        ):
            issues.append(
                f"peak_capital_utilization out of range: {label_set.peak_capital_utilization}"
            )

        return issues


class LabelQualityMetrics:
    """Metrics for label quality assessment (spec §31, §32)."""

    def __init__(self) -> None:
        self.total_labels = 0
        self.valid_labels = 0
        self.invalid_labels = 0
        self.positive_outcome_count = 0
        self.negative_outcome_count = 0
        self.labels_per_horizon: dict[str, int] = {}
        self.labels_per_market: dict[str, int] = {}
        self.simulation_failures = 0
        self.invalid_blueprints = 0

    def add_label_set(self, label_set: LabelSet) -> None:
        """Add a label set to metrics."""
        self.total_labels += 1

        if label_set.is_valid:
            self.valid_labels += 1
            if label_set.positive_net_pnl == 1:
                self.positive_outcome_count += 1
            elif label_set.positive_net_pnl == 0:
                self.negative_outcome_count += 1
        else:
            self.invalid_labels += 1
            if label_set.simulation_status == SimulationStatus.FAILED:
                self.simulation_failures += 1
            elif label_set.simulation_status == SimulationStatus.INVALID_BLUEPRINT:
                self.invalid_blueprints += 1

        self.labels_per_horizon[label_set.horizon] = (
            self.labels_per_horizon.get(label_set.horizon, 0) + 1
        )
        self.labels_per_market[label_set.market_id] = (
            self.labels_per_market.get(label_set.market_id, 0) + 1
        )

    @property
    def positive_rate(self) -> float | None:
        """Class balance: positive outcome rate (spec §31)."""
        labeled = self.positive_outcome_count + self.negative_outcome_count
        if labeled == 0:
            return None
        return self.positive_outcome_count / labeled

    @property
    def class_imbalance_ratio(self) -> float | None:
        """Ratio of negative to positive samples."""
        if self.positive_outcome_count == 0:
            return None
        return self.negative_outcome_count / self.positive_outcome_count

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_labels": self.total_labels,
            "valid_labels": self.valid_labels,
            "invalid_labels": self.invalid_labels,
            "positive_outcome_count": self.positive_outcome_count,
            "negative_outcome_count": self.negative_outcome_count,
            "positive_rate": self.positive_rate,
            "class_imbalance_ratio": self.class_imbalance_ratio,
            "labels_per_horizon": self.labels_per_horizon,
            "labels_per_market": self.labels_per_market,
            "simulation_failures": self.simulation_failures,
            "invalid_blueprints": self.invalid_blueprints,
        }
