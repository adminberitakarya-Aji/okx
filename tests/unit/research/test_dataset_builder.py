"""
Unit tests for Dataset Builder.

Tests dataset construction, causal integrity validation,
time-based splitting, quality metrics, and Parquet storage.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from okx_trading.research.dataset.builder import (
    CausalIntegrityValidator,
    DataQualityFlags,
    DatasetBuilder,
    DatasetManifest,
    DatasetRow,
    DatasetStorage,
    DataSplit,
    RowValidity,
    SimulationValidity,
    TimeSeriesSplitter,
    TimeSplitConfig,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def builder() -> DatasetBuilder:
    return DatasetBuilder(dataset_version="dataset-v001")


@pytest.fixture
def base_time() -> datetime:
    return datetime(2024, 1, 1)


def add_sample_rows(
    builder: DatasetBuilder,
    count: int = 5,
    start: datetime = datetime(2024, 1, 1),
    interval_hours: int = 24,
    market_id: str = "BTC-USDT",
) -> list[DatasetRow]:
    """Add sample rows with sequential timestamps."""
    rows = []
    for i in range(count):
        ts = start + timedelta(hours=i * interval_hours)
        row = builder.add_row(
            market_id=market_id,
            observation_timestamp=ts,
            blueprint_id=f"bp-{i:03d}",
            horizon="30D",
            market_state_features={"observation_timestamp": ts.isoformat()},
            labels={"positive_net_pnl": 1 if i % 2 == 0 else 0},
            quality_flags=DataQualityFlags(label_complete=True),
        )
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# DataQualityFlags
# ---------------------------------------------------------------------------


class TestDataQualityFlags:
    def test_default_quality_score(self):
        """Default flags: 4/5 complete (label_complete=False)."""
        flags = DataQualityFlags()
        assert flags.data_quality_score == pytest.approx(0.8)

    def test_all_complete(self):
        flags = DataQualityFlags(label_complete=True)
        assert flags.data_quality_score == pytest.approx(1.0)

    def test_none_complete(self):
        flags = DataQualityFlags(
            market_data_complete=False,
            execution_data_complete=False,
            feature_complete=False,
            simulation_complete=False,
            label_complete=False,
        )
        assert flags.data_quality_score == pytest.approx(0.0)

    def test_to_dict(self):
        flags = DataQualityFlags()
        d = flags.to_dict()
        assert d["market_data_complete"] is True
        assert d["label_complete"] is False
        assert "data_quality_score" in d


# ---------------------------------------------------------------------------
# DatasetRow
# ---------------------------------------------------------------------------


class TestDatasetRow:
    def test_is_trainable_valid_labeled(self):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
            quality_flags=DataQualityFlags(label_complete=True),
        )
        assert row.is_trainable is True

    def test_not_trainable_without_label(self):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
        )
        assert row.is_trainable is False

    def test_not_trainable_failed_simulation(self):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
            simulation_validity=SimulationValidity.FAILED,
            quality_flags=DataQualityFlags(label_complete=True),
        )
        assert row.is_trainable is False

    def test_not_trainable_invalid_row(self):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
            validity=RowValidity.INVALID_SIMULATION,
            quality_flags=DataQualityFlags(label_complete=True),
        )
        assert row.is_trainable is False

    def test_to_flat_dict_prefixes(self):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
            market_state_features={"volatility": 0.05},
            execution_economics_features={"spread_pct": 0.001},
            grid_behavior_features={"cycle_count": 3},
            derived_ml_features={"rank_score": 0.8},
            labels={"positive_net_pnl": 1},
        )
        d = row.to_flat_dict()
        assert d["mkt_volatility"] == 0.05
        assert d["exe_spread_pct"] == 0.001
        assert d["grd_cycle_count"] == 3
        assert d["ml_rank_score"] == 0.8
        assert d["label_positive_net_pnl"] == 1
        assert d["dataset_row_id"] == "ROW-000001"
        assert d["validity"] == "VALID"


# ---------------------------------------------------------------------------
# DatasetBuilder
# ---------------------------------------------------------------------------


class TestDatasetBuilder:
    def test_row_id_generation(self, builder: DatasetBuilder):
        assert builder.next_row_id() == "ROW-000001"
        assert builder.next_row_id() == "ROW-000002"

    def test_add_row(self, builder: DatasetBuilder, base_time: datetime):
        row = builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
        )
        assert row.dataset_row_id == "ROW-000001"
        assert row.market_id == "BTC-USDT"
        assert builder.row_count == 1

    def test_add_row_custom_id(self, builder: DatasetBuilder, base_time: datetime):
        row = builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            row_id="CUSTOM-001",
        )
        assert row.dataset_row_id == "CUSTOM-001"

    def test_build_manifest(self, builder: DatasetBuilder, base_time: datetime):
        add_sample_rows(builder, count=3, start=base_time)
        manifest = builder.build_manifest()

        assert manifest.dataset_version == "dataset-v001"
        assert manifest.row_count == 3
        assert manifest.valid_row_count == 3
        assert manifest.invalid_row_count == 0
        assert manifest.markets == ["BTC-USDT"]
        assert manifest.date_range_start == base_time
        assert manifest.date_range_end == base_time + timedelta(hours=48)

    def test_build_manifest_empty(self, builder: DatasetBuilder):
        manifest = builder.build_manifest()
        assert manifest.row_count == 0
        assert manifest.date_range_start is None

    def test_to_dataframe(self, builder: DatasetBuilder, base_time: datetime):
        add_sample_rows(builder, count=3, start=base_time)
        df = builder.to_dataframe()
        assert len(df) == 3
        assert "dataset_row_id" in df.columns
        assert "market_id" in df.columns

    def test_versioning_metadata(self, base_time: datetime):
        builder = DatasetBuilder(
            dataset_version="dataset-v002",
            feature_version="v2",
            label_version="v3",
            simulator_version="v4",
        )
        row = builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
        )
        assert row.feature_version == "v2"
        assert row.label_version == "v3"
        assert row.simulator_version == "v4"


# ---------------------------------------------------------------------------
# Quality Metrics
# ---------------------------------------------------------------------------


class TestQualityMetrics:
    def test_empty_metrics(self, builder: DatasetBuilder):
        metrics = builder.compute_quality_metrics()
        assert metrics.total_rows == 0

    def test_rows_per_market(self, builder: DatasetBuilder, base_time: datetime):
        add_sample_rows(builder, count=3, start=base_time, market_id="BTC-USDT")
        add_sample_rows(builder, count=2, start=base_time, market_id="ETH-USDT")
        metrics = builder.compute_quality_metrics()

        assert metrics.rows_per_market["BTC-USDT"] == 3
        assert metrics.rows_per_market["ETH-USDT"] == 2

    def test_outcome_rates(self, builder: DatasetBuilder, base_time: datetime):
        # add_sample_rows alternates positive/negative labels
        add_sample_rows(builder, count=4, start=base_time)
        metrics = builder.compute_quality_metrics()

        assert metrics.positive_outcome_rate == pytest.approx(0.5)
        assert metrics.negative_outcome_rate == pytest.approx(0.5)

    def test_simulation_failure_rate(self, builder: DatasetBuilder, base_time: datetime):
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            simulation_validity=SimulationValidity.FAILED,
        )
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time + timedelta(hours=1),
            blueprint_id="bp-002",
            horizon="30D",
        )
        metrics = builder.compute_quality_metrics()
        assert metrics.simulation_failure_rate == pytest.approx(0.5)

    def test_missing_feature_rate(self, builder: DatasetBuilder, base_time: datetime):
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            quality_flags=DataQualityFlags(feature_complete=False),
        )
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time + timedelta(hours=1),
            blueprint_id="bp-002",
            horizon="30D",
        )
        metrics = builder.compute_quality_metrics()
        assert metrics.missing_feature_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# TimeSeriesSplitter
# ---------------------------------------------------------------------------


class TestTimeSeriesSplitter:
    def test_split_config_validation(self):
        with pytest.raises(ValueError, match="train_end must be before"):
            TimeSplitConfig(
                train_end=datetime(2024, 6, 1),
                validation_end=datetime(2024, 1, 1),
            )

    def test_assign_split(self):
        config = TimeSplitConfig(
            train_end=datetime(2024, 3, 31),
            validation_end=datetime(2024, 6, 30),
        )
        splitter = TimeSeriesSplitter(config)

        assert splitter.assign_split(datetime(2024, 1, 15)) == DataSplit.TRAIN
        assert splitter.assign_split(datetime(2024, 3, 31)) == DataSplit.TRAIN
        assert splitter.assign_split(datetime(2024, 4, 1)) == DataSplit.VALIDATION
        assert splitter.assign_split(datetime(2024, 6, 30)) == DataSplit.VALIDATION
        assert splitter.assign_split(datetime(2024, 7, 1)) == DataSplit.TEST

    def test_split_rows(self, builder: DatasetBuilder):
        # 10 days of data, 1 day apart
        add_sample_rows(builder, count=10, start=datetime(2024, 1, 1))

        config = TimeSplitConfig(
            train_end=datetime(2024, 1, 5),
            validation_end=datetime(2024, 1, 8),
        )
        splitter = TimeSeriesSplitter(config)
        result = splitter.split_rows(builder.rows)

        assert len(result[DataSplit.TRAIN]) == 5  # Jan 1-5
        assert len(result[DataSplit.VALIDATION]) == 3  # Jan 6-8
        assert len(result[DataSplit.TEST]) == 2  # Jan 9-10

    def test_split_preserves_temporal_order(self, builder: DatasetBuilder):
        add_sample_rows(builder, count=10, start=datetime(2024, 1, 1))
        config = TimeSplitConfig(
            train_end=datetime(2024, 1, 5),
            validation_end=datetime(2024, 1, 8),
        )
        splitter = TimeSeriesSplitter(config)
        result = splitter.split_rows(builder.rows)

        for split_rows in result.values():
            timestamps = [r.observation_timestamp for r in split_rows]
            assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# CausalIntegrityValidator
# ---------------------------------------------------------------------------


class TestCausalIntegrityValidator:
    def test_valid_row_passes(self, base_time: datetime):
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            market_state_features={"observation_timestamp": base_time.isoformat()},
        )
        validator = CausalIntegrityValidator()
        violations = validator.validate_row(row)
        assert violations == []

    def test_future_feature_timestamp_detected(self, base_time: datetime):
        future_ts = base_time + timedelta(hours=1)
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            market_state_features={"observation_timestamp": future_ts.isoformat()},
        )
        validator = CausalIntegrityValidator()
        violations = validator.validate_row(row)
        assert len(violations) == 1
        assert "after observation timestamp" in violations[0]

    def test_label_start_before_observation_detected(self, base_time: datetime):
        past_ts = base_time - timedelta(hours=1)
        row = DatasetRow(
            dataset_row_id="ROW-000001",
            market_id="BTC-USDT",
            exchange_id="OKX",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            labels={"label_start": past_ts.isoformat()},
        )
        validator = CausalIntegrityValidator()
        violations = validator.validate_row(row)
        assert len(violations) == 1
        assert "before observation" in violations[0]

    def test_audit_passes_clean_dataset(self, builder: DatasetBuilder):
        add_sample_rows(builder, count=5, start=datetime(2024, 1, 1))
        dataset = builder.build()
        assert dataset.causal_audit_passed is True
        assert dataset.causal_violations == []

    def test_audit_fails_with_future_features(self, builder: DatasetBuilder, base_time: datetime):
        future_ts = base_time + timedelta(hours=1)
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=base_time,
            blueprint_id="bp-001",
            horizon="30D",
            market_state_features={"observation_timestamp": future_ts.isoformat()},
        )
        dataset = builder.build()
        assert dataset.causal_audit_passed is False
        assert len(dataset.causal_violations) > 0

    def test_no_test_in_train_validation(self):
        validator = CausalIntegrityValidator()
        rows = [
            DatasetRow(
                dataset_row_id="ROW-000001",
                market_id="BTC-USDT",
                exchange_id="OKX",
                observation_timestamp=datetime(2024, 1, 1),
                blueprint_id="bp-001",
                horizon="30D",
                split=DataSplit.TRAIN,
            ),
            DatasetRow(
                dataset_row_id="ROW-000002",
                market_id="BTC-USDT",
                exchange_id="OKX",
                observation_timestamp=datetime(2024, 6, 1),
                blueprint_id="bp-002",
                horizon="30D",
                split=DataSplit.TEST,
            ),
        ]
        assert validator.validate_no_test_in_train(rows) is True

    def test_test_in_train_detected(self):
        validator = CausalIntegrityValidator()
        rows = [
            DatasetRow(
                dataset_row_id="ROW-000001",
                market_id="BTC-USDT",
                exchange_id="OKX",
                observation_timestamp=datetime(2024, 6, 1),
                blueprint_id="bp-001",
                horizon="30D",
                split=DataSplit.TRAIN,
            ),
            DatasetRow(
                dataset_row_id="ROW-000002",
                market_id="BTC-USDT",
                exchange_id="OKX",
                observation_timestamp=datetime(2024, 1, 1),
                blueprint_id="bp-002",
                horizon="30D",
                split=DataSplit.TEST,
            ),
        ]
        assert validator.validate_no_test_in_train(rows) is False


# ---------------------------------------------------------------------------
# BuiltDataset
# ---------------------------------------------------------------------------


class TestBuiltDataset:
    def test_is_trainable_when_audit_passes(self, builder: DatasetBuilder):
        add_sample_rows(builder, count=3)
        dataset = builder.build()
        assert dataset.is_trainable is True

    def test_get_split(self, builder: DatasetBuilder):
        add_sample_rows(builder, count=10, start=datetime(2024, 1, 1))
        config = TimeSplitConfig(
            train_end=datetime(2024, 1, 5),
            validation_end=datetime(2024, 1, 8),
        )
        dataset = builder.build(split_config=config)

        train = dataset.get_split(DataSplit.TRAIN)
        assert len(train) == 5
        assert all(r.split == DataSplit.TRAIN for r in train)

    def test_to_dataframe_with_split(self, builder: DatasetBuilder):
        add_sample_rows(builder, count=10, start=datetime(2024, 1, 1))
        config = TimeSplitConfig(
            train_end=datetime(2024, 1, 5),
            validation_end=datetime(2024, 1, 8),
        )
        dataset = builder.build(split_config=config)

        df_train = dataset.to_dataframe(split=DataSplit.TRAIN)
        assert len(df_train) == 5

        df_all = dataset.to_dataframe()
        assert len(df_all) == 10


# ---------------------------------------------------------------------------
# DatasetManifest
# ---------------------------------------------------------------------------


class TestDatasetManifest:
    def test_to_dict_from_dict_round_trip(self):
        manifest = DatasetManifest(
            dataset_version="dataset-v001",
            generated_at=datetime(2024, 1, 1, 12, 0),
            date_range_start=datetime(2024, 1, 1),
            date_range_end=datetime(2024, 12, 31),
            markets=["BTC-USDT", "ETH-USDT"],
            row_count=100,
            valid_row_count=95,
            invalid_row_count=5,
        )
        d = manifest.to_dict()
        restored = DatasetManifest.from_dict(d)

        assert restored.dataset_version == manifest.dataset_version
        assert restored.markets == manifest.markets
        assert restored.row_count == manifest.row_count
        assert restored.valid_row_count == manifest.valid_row_count

    def test_from_dict_with_none_dates(self):
        data = {
            "dataset_version": "dataset-v001",
            "generated_at": "2024-01-01T12:00:00",
            "date_range_start": None,
            "date_range_end": None,
        }
        manifest = DatasetManifest.from_dict(data)
        assert manifest.date_range_start is None
        assert manifest.date_range_end is None


# ---------------------------------------------------------------------------
# DatasetStorage
# ---------------------------------------------------------------------------


class TestDatasetStorage:
    def test_save_and_load_round_trip(self, tmp_path: Path, builder: DatasetBuilder):
        add_sample_rows(builder, count=5, start=datetime(2024, 1, 1))
        dataset = builder.build()

        storage = DatasetStorage(tmp_path)
        version_dir = storage.save(dataset)

        assert (version_dir / "data.parquet").exists()
        assert (version_dir / "manifest.json").exists()
        assert (version_dir / "metrics.json").exists()

        # Load back
        manifest = storage.load_manifest("dataset-v001")
        assert manifest.row_count == 5

        df = storage.load_dataframe("dataset-v001")
        assert len(df) == 5

    def test_list_versions(self, tmp_path: Path):
        storage = DatasetStorage(tmp_path)
        assert storage.list_versions() == []

        builder = DatasetBuilder(dataset_version="dataset-v001")
        add_sample_rows(builder, count=2)
        storage.save(builder.build())

        builder2 = DatasetBuilder(dataset_version="dataset-v002")
        add_sample_rows(builder2, count=2)
        storage.save(builder2.build())

        versions = storage.list_versions()
        assert versions == ["dataset-v001", "dataset-v002"]

    def test_load_nonexistent_raises(self, tmp_path: Path):
        storage = DatasetStorage(tmp_path)
        with pytest.raises(FileNotFoundError):
            storage.load_manifest("nonexistent")
        with pytest.raises(FileNotFoundError):
            storage.load_dataframe("nonexistent")

    def test_delete_version(self, tmp_path: Path, builder: DatasetBuilder):
        add_sample_rows(builder, count=2)
        storage = DatasetStorage(tmp_path)
        storage.save(builder.build())

        assert "dataset-v001" in storage.list_versions()
        storage.delete_version("dataset-v001")
        assert "dataset-v001" not in storage.list_versions()


# ---------------------------------------------------------------------------
# Integration: Full Pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_build_with_split_and_audit(self):
        """Full pipeline: add rows, split, audit, save."""
        builder = DatasetBuilder(dataset_version="dataset-v001")
        add_sample_rows(builder, count=30, start=datetime(2024, 1, 1))

        config = TimeSplitConfig(
            train_end=datetime(2024, 1, 15),
            validation_end=datetime(2024, 1, 25),
        )
        dataset = builder.build(split_config=config)

        assert dataset.causal_audit_passed is True
        assert dataset.is_trainable is True
        assert len(dataset.get_split(DataSplit.TRAIN)) == 15
        assert len(dataset.get_split(DataSplit.VALIDATION)) == 10
        assert len(dataset.get_split(DataSplit.TEST)) == 5

        assert dataset.metrics.total_rows == 30
        assert dataset.metrics.valid_rows == 30

    def test_invalid_simulation_not_negative_label(self):
        """Spec §44: INVALID_SIMULATION != NEGATIVE_OUTCOME."""
        builder = DatasetBuilder(dataset_version="dataset-v001")

        # Failed simulation
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=datetime(2024, 1, 1),
            blueprint_id="bp-001",
            horizon="30D",
            validity=RowValidity.INVALID_SIMULATION,
            simulation_validity=SimulationValidity.FAILED,
        )

        # Negative outcome (valid simulation, bad result)
        builder.add_row(
            market_id="BTC-USDT",
            observation_timestamp=datetime(2024, 1, 2),
            blueprint_id="bp-002",
            horizon="30D",
            validity=RowValidity.VALID,
            simulation_validity=SimulationValidity.NEGATIVE_OUTCOME,
            labels={"positive_net_pnl": 0},
            quality_flags=DataQualityFlags(label_complete=True),
        )

        dataset = builder.build()
        assert dataset.metrics.valid_rows == 1
        assert dataset.metrics.invalid_rows == 1
        assert dataset.metrics.simulation_failure_rate == pytest.approx(0.5)
