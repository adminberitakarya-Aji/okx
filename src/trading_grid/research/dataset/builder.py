"""
Dataset Builder for AI Research Pipeline.

Assembles feature layers and simulation outcomes into versioned,
causally-ordered dataset rows per AI_RESEARCH_DATASET_SPEC.md.

Core principles:
- Every row has a causal observation timestamp T
- Features use only data <= T (no future leakage)
- Labels come from valid simulations only
- Invalid simulation != negative outcome
- Time-based train/validation/test splitting
- Dataset versions are reproducible
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DataSplit(StrEnum):
    """Dataset split assignment."""

    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class RowValidity(StrEnum):
    """Whether a dataset row is valid for training."""

    VALID = "VALID"
    INVALID_SIMULATION = "INVALID_SIMULATION"
    INVALID_MARKET_DATA = "INVALID_MARKET_DATA"
    INVALID_BLUEPRINT = "INVALID_BLUEPRINT"
    MISSING_FEATURES = "MISSING_FEATURES"


class SimulationValidity(StrEnum):
    """Distinguishes simulation failure from negative outcome."""

    VALID = "VALID"
    FAILED = "FAILED"
    NEGATIVE_OUTCOME = "NEGATIVE_OUTCOME"


# ---------------------------------------------------------------------------
# Data Quality Flags
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataQualityFlags:
    """Per-row data quality indicators (Spec §45)."""

    market_data_complete: bool = True
    execution_data_complete: bool = True
    feature_complete: bool = True
    simulation_complete: bool = True
    label_complete: bool = False

    @property
    def data_quality_score(self) -> float:
        """Fraction of quality checks passed (0.0 to 1.0)."""
        checks = [
            self.market_data_complete,
            self.execution_data_complete,
            self.feature_complete,
            self.simulation_complete,
            self.label_complete,
        ]
        return sum(1 for c in checks if c) / len(checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_data_complete": self.market_data_complete,
            "execution_data_complete": self.execution_data_complete,
            "feature_complete": self.feature_complete,
            "simulation_complete": self.simulation_complete,
            "label_complete": self.label_complete,
            "data_quality_score": self.data_quality_score,
        }


# ---------------------------------------------------------------------------
# Dataset Row
# ---------------------------------------------------------------------------


@dataclass
class DatasetRow:
    """
    A single dataset observation (Spec §58).

    Captures what was knowable at observation_timestamp T,
    plus the future simulation outcome used as label.
    """

    dataset_row_id: str
    market_id: str
    exchange_id: str
    observation_timestamp: datetime
    blueprint_id: str
    horizon: str  # e.g. "7D", "30D", "90D"

    # Feature layers (flattened dicts from feature extractors)
    market_state_features: dict[str, Any] = field(default_factory=dict)
    execution_economics_features: dict[str, Any] = field(default_factory=dict)
    grid_behavior_features: dict[str, Any] = field(default_factory=dict)
    derived_ml_features: dict[str, Any] = field(default_factory=dict)

    # Blueprint context (part of prediction input, Spec §6 rule 6)
    blueprint_config: dict[str, Any] = field(default_factory=dict)

    # Labels (from future simulation, Spec §3)
    labels: dict[str, Any] = field(default_factory=dict)

    # Validity and quality
    validity: RowValidity = RowValidity.VALID
    simulation_validity: SimulationValidity = SimulationValidity.VALID
    quality_flags: DataQualityFlags = field(default_factory=DataQualityFlags)

    # Split assignment
    split: DataSplit | None = None

    # Versioning metadata
    feature_version: str = "v1"
    label_version: str = "v1"
    simulator_version: str = "v1"

    @property
    def is_trainable(self) -> bool:
        """Row can be used for training only if valid and labeled."""
        return (
            self.validity == RowValidity.VALID
            and self.simulation_validity != SimulationValidity.FAILED
            and self.quality_flags.label_complete
        )

    def to_flat_dict(self) -> dict[str, Any]:
        """Flatten row into a single dict for DataFrame conversion."""
        result: dict[str, Any] = {
            "dataset_row_id": self.dataset_row_id,
            "market_id": self.market_id,
            "exchange_id": self.exchange_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "blueprint_id": self.blueprint_id,
            "horizon": self.horizon,
            "validity": self.validity.value,
            "simulation_validity": self.simulation_validity.value,
            "split": self.split.value if self.split else None,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "simulator_version": self.simulator_version,
        }

        # Prefix feature columns to avoid collisions
        for key, value in self.market_state_features.items():
            result[f"mkt_{key}"] = value
        for key, value in self.execution_economics_features.items():
            result[f"exe_{key}"] = value
        for key, value in self.grid_behavior_features.items():
            result[f"grd_{key}"] = value
        for key, value in self.derived_ml_features.items():
            result[f"ml_{key}"] = value
        for key, value in self.labels.items():
            result[f"label_{key}"] = value

        # Quality flags
        quality = self.quality_flags.to_dict()
        for key, value in quality.items():
            result[f"quality_{key}"] = value

        return result


# ---------------------------------------------------------------------------
# Dataset Manifest
# ---------------------------------------------------------------------------


@dataclass
class DatasetManifest:
    """Dataset version manifest (Spec §55)."""

    dataset_version: str
    generated_at: datetime
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    markets: list[str] = field(default_factory=list)
    universe_rule_version: str = "v1"
    feature_version: str = "v1"
    label_version: str = "v1"
    simulator_version: str = "v1"
    execution_model_version: str = "v1"
    blueprint_generator_version: str = "v1"
    row_count: int = 0
    valid_row_count: int = 0
    invalid_row_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "generated_at": self.generated_at.isoformat(),
            "date_range_start": (
                self.date_range_start.isoformat() if self.date_range_start else None
            ),
            "date_range_end": (self.date_range_end.isoformat() if self.date_range_end else None),
            "markets": self.markets,
            "universe_rule_version": self.universe_rule_version,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "simulator_version": self.simulator_version,
            "execution_model_version": self.execution_model_version,
            "blueprint_generator_version": self.blueprint_generator_version,
            "row_count": self.row_count,
            "valid_row_count": self.valid_row_count,
            "invalid_row_count": self.invalid_row_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DatasetManifest:
        return cls(
            dataset_version=data["dataset_version"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            date_range_start=(
                datetime.fromisoformat(data["date_range_start"])
                if data.get("date_range_start")
                else None
            ),
            date_range_end=(
                datetime.fromisoformat(data["date_range_end"])
                if data.get("date_range_end")
                else None
            ),
            markets=data.get("markets", []),
            universe_rule_version=data.get("universe_rule_version", "v1"),
            feature_version=data.get("feature_version", "v1"),
            label_version=data.get("label_version", "v1"),
            simulator_version=data.get("simulator_version", "v1"),
            execution_model_version=data.get("execution_model_version", "v1"),
            blueprint_generator_version=data.get("blueprint_generator_version", "v1"),
            row_count=data.get("row_count", 0),
            valid_row_count=data.get("valid_row_count", 0),
            invalid_row_count=data.get("invalid_row_count", 0),
        )


# ---------------------------------------------------------------------------
# Quality Metrics
# ---------------------------------------------------------------------------


@dataclass
class DatasetQualityMetrics:
    """Dataset quality report (Spec §59)."""

    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    rows_per_market: dict[str, int] = field(default_factory=dict)
    rows_per_blueprint: dict[str, int] = field(default_factory=dict)
    rows_per_horizon: dict[str, int] = field(default_factory=dict)
    positive_outcome_rate: float | None = None
    negative_outcome_rate: float | None = None
    missing_feature_rate: float = 0.0
    simulation_failure_rate: float = 0.0
    leakage_audit_passed: bool = False
    temporal_integrity_passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "valid_rows": self.valid_rows,
            "invalid_rows": self.invalid_rows,
            "rows_per_market": self.rows_per_market,
            "rows_per_blueprint": self.rows_per_blueprint,
            "rows_per_horizon": self.rows_per_horizon,
            "positive_outcome_rate": self.positive_outcome_rate,
            "negative_outcome_rate": self.negative_outcome_rate,
            "missing_feature_rate": self.missing_feature_rate,
            "simulation_failure_rate": self.simulation_failure_rate,
            "leakage_audit_passed": self.leakage_audit_passed,
            "temporal_integrity_passed": self.temporal_integrity_passed,
        }


# ---------------------------------------------------------------------------
# Time Series Splitter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeSplitConfig:
    """Configuration for time-based train/validation/test split (Spec §38)."""

    train_end: datetime
    validation_end: datetime
    # test_end is implicit: everything after validation_end up to dataset end

    def __post_init__(self) -> None:
        if self.train_end >= self.validation_end:
            raise ValueError("train_end must be before validation_end")


class TimeSeriesSplitter:
    """
    Assigns rows to TRAIN / VALIDATION / TEST based on observation timestamp.

    Time-based splitting preserves temporal causality (Spec §38).
    No random shuffling by default.
    """

    def __init__(self, config: TimeSplitConfig) -> None:
        self.config = config

    def assign_split(self, observation_timestamp: datetime) -> DataSplit:
        """Determine which split an observation belongs to."""
        if observation_timestamp <= self.config.train_end:
            return DataSplit.TRAIN
        if observation_timestamp <= self.config.validation_end:
            return DataSplit.VALIDATION
        return DataSplit.TEST

    def split_rows(self, rows: list[DatasetRow]) -> dict[DataSplit, list[DatasetRow]]:
        """Assign splits to all rows and group them."""
        result: dict[DataSplit, list[DatasetRow]] = {
            DataSplit.TRAIN: [],
            DataSplit.VALIDATION: [],
            DataSplit.TEST: [],
        }
        for row in rows:
            split = self.assign_split(row.observation_timestamp)
            row.split = split
            result[split].append(row)
        return result


# ---------------------------------------------------------------------------
# Causal Integrity Validator
# ---------------------------------------------------------------------------


class CausalIntegrityValidator:
    """
    Validates causal integrity of dataset rows (Spec §46-47).

    Checks:
    - Feature timestamps <= observation timestamp
    - No future data in features
    - Label window starts at observation timestamp
    - Temporal ordering within splits
    """

    @staticmethod
    def _normalize_tz(ts: datetime) -> datetime:
        """Normalize a datetime to UTC timezone-aware for safe comparison."""
        if ts.tzinfo is None:
            return ts.replace(tzinfo=UTC)
        return ts

    def validate_row(self, row: DatasetRow) -> list[str]:
        """Return list of violations for a single row (empty = pass)."""
        violations: list[str] = []

        obs_ts = self._normalize_tz(row.observation_timestamp)

        # Check feature timestamps if present [R-M3: normalize before comparison]
        for layer_name, features in [
            ("market_state", row.market_state_features),
            ("execution_economics", row.execution_economics_features),
            ("grid_behavior", row.grid_behavior_features),
        ]:
            feature_ts = features.get("observation_timestamp")
            if feature_ts is not None:
                if isinstance(feature_ts, str):
                    feature_ts = datetime.fromisoformat(feature_ts)
                if isinstance(feature_ts, datetime):
                    feature_ts = self._normalize_tz(feature_ts)
                    if feature_ts > obs_ts:
                        violations.append(
                            f"{layer_name} feature timestamp {feature_ts} "
                            f"is after observation timestamp {obs_ts}"
                        )

        # Check label window alignment (Spec §47)
        label_start = row.labels.get("label_start")
        if label_start is not None:
            if isinstance(label_start, str):
                label_start = datetime.fromisoformat(label_start)
            if isinstance(label_start, datetime):
                label_start = self._normalize_tz(label_start)
                if label_start < obs_ts:
                    violations.append(
                        f"Label start {label_start} is before observation timestamp {obs_ts}"
                    )

        return violations

    def validate_temporal_ordering(self, rows: list[DatasetRow], split: DataSplit) -> bool:
        """Verify rows within a split are temporally ordered per market_id.

        [R-M2] Validates ordering per market_id separately. A multi-market
        dataset interleaves timestamps across markets — global ordering would
        produce false positives whenever market-A and market-B timestamps
        alternate non-monotonically.
        """
        split_rows = [r for r in rows if r.split == split]
        if len(split_rows) <= 1:
            return True

        market_ids = {r.market_id for r in split_rows}
        for market_id in market_ids:
            market_rows = [r for r in split_rows if r.market_id == market_id]
            if len(market_rows) <= 1:
                continue
            timestamps = [r.observation_timestamp for r in market_rows]
            if not all(t1 <= t2 for t1, t2 in itertools.pairwise(timestamps)):
                return False
        return True

    def validate_no_test_in_train(self, rows: list[DatasetRow]) -> bool:
        """Ensure no test-period data appears in training split."""
        train_rows = [r for r in rows if r.split == DataSplit.TRAIN]
        test_rows = [r for r in rows if r.split == DataSplit.TEST]
        if not train_rows or not test_rows:
            return True
        max_train_ts = max(r.observation_timestamp for r in train_rows)
        min_test_ts = min(r.observation_timestamp for r in test_rows)
        return max_train_ts < min_test_ts

    def audit_dataset(self, rows: list[DatasetRow]) -> tuple[bool, list[str]]:
        """
        Full leakage audit (Spec §46).

        Returns (passed, list_of_all_violations).
        """
        all_violations: list[str] = []

        for row in rows:
            row_violations = self.validate_row(row)
            for v in row_violations:
                all_violations.append(f"[{row.dataset_row_id}] {v}")

        # Temporal ordering checks
        for split in DataSplit:
            if not self.validate_temporal_ordering(rows, split):
                all_violations.append(f"Temporal ordering violated in {split.value}")

        # No test leakage into train
        if not self.validate_no_test_in_train(rows):
            all_violations.append("Test period data found in training split")

        passed = len(all_violations) == 0
        if passed:
            logger.info("causal_audit_passed", row_count=len(rows))
        else:
            logger.warning(
                "causal_audit_failed",
                row_count=len(rows),
                violation_count=len(all_violations),
            )

        return passed, all_violations


# ---------------------------------------------------------------------------
# Dataset Builder
# ---------------------------------------------------------------------------


class DatasetBuilder:
    """
    Builds versioned datasets from feature layers and simulation results.

    Usage:
        builder = DatasetBuilder(dataset_version="dataset-v001")
        builder.add_row(row)
        ...
        dataset = builder.build()
    """

    def __init__(
        self,
        dataset_version: str,
        feature_version: str = "v1",
        label_version: str = "v1",
        simulator_version: str = "v1",
        execution_model_version: str = "v1",
        blueprint_generator_version: str = "v1",
        universe_rule_version: str = "v1",
    ) -> None:
        self.dataset_version = dataset_version
        self.feature_version = feature_version
        self.label_version = label_version
        self.simulator_version = simulator_version
        self.execution_model_version = execution_model_version
        self.blueprint_generator_version = blueprint_generator_version
        self.universe_rule_version = universe_rule_version
        self._rows: list[DatasetRow] = []
        self._row_counter = 0

    def next_row_id(self) -> str:
        """Generate sequential row ID."""
        self._row_counter += 1
        return f"ROW-{self._row_counter:06d}"

    def add_row(
        self,
        market_id: str,
        observation_timestamp: datetime,
        blueprint_id: str,
        horizon: str,
        market_state_features: dict[str, Any] | None = None,
        execution_economics_features: dict[str, Any] | None = None,
        grid_behavior_features: dict[str, Any] | None = None,
        derived_ml_features: dict[str, Any] | None = None,
        blueprint_config: dict[str, Any] | None = None,
        labels: dict[str, Any] | None = None,
        validity: RowValidity = RowValidity.VALID,
        simulation_validity: SimulationValidity = SimulationValidity.VALID,
        quality_flags: DataQualityFlags | None = None,
        exchange_id: str = "OKX",
        row_id: str | None = None,
    ) -> DatasetRow:
        """Add a dataset row."""
        row = DatasetRow(
            dataset_row_id=row_id or self.next_row_id(),
            market_id=market_id,
            exchange_id=exchange_id,
            observation_timestamp=observation_timestamp,
            blueprint_id=blueprint_id,
            horizon=horizon,
            market_state_features=market_state_features or {},
            execution_economics_features=execution_economics_features or {},
            grid_behavior_features=grid_behavior_features or {},
            derived_ml_features=derived_ml_features or {},
            blueprint_config=blueprint_config or {},
            labels=labels or {},
            validity=validity,
            simulation_validity=simulation_validity,
            quality_flags=quality_flags or DataQualityFlags(),
            feature_version=self.feature_version,
            label_version=self.label_version,
            simulator_version=self.simulator_version,
        )
        self._rows.append(row)
        return row

    @property
    def rows(self) -> list[DatasetRow]:
        """All rows added so far."""
        return list(self._rows)

    @property
    def row_count(self) -> int:
        return len(self._rows)

    def build_manifest(self) -> DatasetManifest:
        """Build manifest for current rows."""
        markets = sorted({r.market_id for r in self._rows})
        valid_count = sum(1 for r in self._rows if r.validity == RowValidity.VALID)
        timestamps = [r.observation_timestamp for r in self._rows]

        return DatasetManifest(
            dataset_version=self.dataset_version,
            generated_at=datetime.now(UTC),
            date_range_start=min(timestamps) if timestamps else None,
            date_range_end=max(timestamps) if timestamps else None,
            markets=markets,
            universe_rule_version=self.universe_rule_version,
            feature_version=self.feature_version,
            label_version=self.label_version,
            simulator_version=self.simulator_version,
            execution_model_version=self.execution_model_version,
            blueprint_generator_version=self.blueprint_generator_version,
            row_count=len(self._rows),
            valid_row_count=valid_count,
            invalid_row_count=len(self._rows) - valid_count,
        )

    def compute_quality_metrics(
        self, leakage_passed: bool = False, temporal_passed: bool = False
    ) -> DatasetQualityMetrics:
        """Compute quality metrics for current rows (Spec §59)."""
        rows = self._rows
        if not rows:
            return DatasetQualityMetrics()

        valid = [r for r in rows if r.validity == RowValidity.VALID]
        invalid = [r for r in rows if r.validity != RowValidity.VALID]

        rows_per_market: dict[str, int] = {}
        rows_per_blueprint: dict[str, int] = {}
        rows_per_horizon: dict[str, int] = {}
        for r in rows:
            rows_per_market[r.market_id] = rows_per_market.get(r.market_id, 0) + 1
            rows_per_blueprint[r.blueprint_id] = rows_per_blueprint.get(r.blueprint_id, 0) + 1
            rows_per_horizon[r.horizon] = rows_per_horizon.get(r.horizon, 0) + 1

        # Outcome rates (from labels)
        labeled = [r for r in valid if r.labels]
        positive_count = sum(1 for r in labeled if r.labels.get("positive_net_pnl", 0) == 1)
        negative_count = sum(1 for r in labeled if r.labels.get("positive_net_pnl", 0) == 0)

        # Missing feature rate
        missing_features = sum(1 for r in rows if not r.quality_flags.feature_complete)

        # Simulation failure rate
        sim_failures = sum(1 for r in rows if r.simulation_validity == SimulationValidity.FAILED)

        return DatasetQualityMetrics(
            total_rows=len(rows),
            valid_rows=len(valid),
            invalid_rows=len(invalid),
            rows_per_market=rows_per_market,
            rows_per_blueprint=rows_per_blueprint,
            rows_per_horizon=rows_per_horizon,
            positive_outcome_rate=(positive_count / len(labeled) if labeled else None),
            negative_outcome_rate=(negative_count / len(labeled) if labeled else None),
            missing_feature_rate=(missing_features / len(rows) if rows else 0.0),
            simulation_failure_rate=(sim_failures / len(rows) if rows else 0.0),
            leakage_audit_passed=leakage_passed,
            temporal_integrity_passed=temporal_passed,
        )

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all rows to a flat pandas DataFrame."""
        records = [row.to_flat_dict() for row in self._rows]
        return pd.DataFrame(records)

    def build(
        self,
        split_config: TimeSplitConfig | None = None,
        run_causal_audit: bool = True,
    ) -> BuiltDataset:
        """
        Build the final dataset.

        Args:
            split_config: Optional time split configuration.
            run_causal_audit: Whether to run causal integrity validation.

        Returns:
            BuiltDataset with rows, manifest, metrics, and audit results.
        """
        rows = self._rows

        # Assign splits if config provided
        if split_config is not None:
            splitter = TimeSeriesSplitter(split_config)
            splitter.split_rows(rows)

        # Run causal audit (conditionally — disabled for fast dev builds)
        if run_causal_audit:
            validator = CausalIntegrityValidator()
            leakage_passed, violations = validator.audit_dataset(rows)

            temporal_passed = True
            if split_config is not None:
                for split in DataSplit:
                    if not validator.validate_temporal_ordering(rows, split):
                        temporal_passed = False
                        break
        else:
            leakage_passed = True
            violations = []
            temporal_passed = True
            logger.warning("causal_audit_skipped", reason="run_causal_audit=False")

        manifest = self.build_manifest()
        metrics = self.compute_quality_metrics(
            leakage_passed=leakage_passed,
            temporal_passed=temporal_passed,
        )

        logger.info(
            "dataset_built",
            version=self.dataset_version,
            row_count=len(rows),
            valid_count=manifest.valid_row_count,
            leakage_passed=leakage_passed,
        )

        return BuiltDataset(
            rows=rows,
            manifest=manifest,
            metrics=metrics,
            causal_audit_passed=leakage_passed,
            causal_violations=violations,
        )


# ---------------------------------------------------------------------------
# Built Dataset
# ---------------------------------------------------------------------------


@dataclass
class BuiltDataset:
    """Result of DatasetBuilder.build()."""

    rows: list[DatasetRow]
    manifest: DatasetManifest
    metrics: DatasetQualityMetrics
    causal_audit_passed: bool
    causal_violations: list[str] = field(default_factory=list)

    @property
    def is_trainable(self) -> bool:
        """Dataset can be used for training only if audit passed."""
        return self.causal_audit_passed

    def get_split(self, split: DataSplit) -> list[DatasetRow]:
        """Get rows for a specific split."""
        return [r for r in self.rows if r.split == split]

    def to_dataframe(self, split: DataSplit | None = None) -> pd.DataFrame:
        """Convert to DataFrame, optionally filtered by split."""
        rows = self.rows if split is None else self.get_split(split)
        records = [row.to_flat_dict() for row in rows]
        return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Dataset Storage (Parquet)
# ---------------------------------------------------------------------------


class DatasetStorage:
    """
    Persists datasets to Parquet with manifest (Spec §52-53).

    Directory layout:
        base_dir/
            dataset-v001/
                data.parquet
                manifest.json
                metrics.json
    """

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _version_dir(self, version: str) -> Path:
        return self.base_dir / version

    def save(self, dataset: BuiltDataset) -> Path:
        """Save dataset to Parquet + JSON manifest."""
        version_dir = self._version_dir(dataset.manifest.dataset_version)
        version_dir.mkdir(parents=True, exist_ok=True)

        # Save data
        df = dataset.to_dataframe()
        parquet_path = version_dir / "data.parquet"
        df.to_parquet(parquet_path, index=False)

        # Save manifest
        manifest_path = version_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(dataset.manifest.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        # Save metrics
        metrics_path = version_dir / "metrics.json"
        metrics_path.write_text(
            json.dumps(dataset.metrics.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        logger.info(
            "dataset_saved",
            version=dataset.manifest.dataset_version,
            path=str(version_dir),
            row_count=len(dataset.rows),
        )

        return version_dir

    def load_manifest(self, version: str) -> DatasetManifest:
        """Load manifest for a dataset version."""
        manifest_path = self._version_dir(version) / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found for {version}")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return DatasetManifest.from_dict(data)

    def load_dataframe(self, version: str) -> pd.DataFrame:
        """Load dataset DataFrame for a version."""
        parquet_path = self._version_dir(version) / "data.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"Data not found for {version}")
        return pd.read_parquet(parquet_path)

    def list_versions(self) -> list[str]:
        """List all dataset versions."""
        if not self.base_dir.exists():
            return []
        return sorted(
            d.name for d in self.base_dir.iterdir() if d.is_dir() and (d / "manifest.json").exists()
        )

    def delete_version(self, version: str) -> None:
        """Delete a dataset version."""
        import shutil

        version_dir = self._version_dir(version)
        if version_dir.exists():
            shutil.rmtree(version_dir)
            logger.info("dataset_version_deleted", version=version)
