"""Tests for Derived ML Features (F-ML layer)."""

from datetime import UTC, datetime

import pytest

from trading_grid.research.features.derived_ml import (
    DERIVED_ML_VERSION,
    DerivedMLExtractor,
    DerivedMLFeatures,
    FeatureAvailability,
    FeatureValue,
)


@pytest.fixture
def extractor() -> DerivedMLExtractor:
    return DerivedMLExtractor()


@pytest.fixture
def observation_ts() -> datetime:
    return datetime(2024, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def market_state_features() -> dict:
    """Typical F-MKT features for a corrective setup."""
    return {
        "monthly_price_position": 0.20,
        "weekly_price_position": 0.25,
        "daily_price_position": 0.30,
        "monthly_weekly_price_position_difference": 0.05,
        "weekly_daily_price_position_difference": 0.05,
        "distance_to_monthly_low_pct": 0.03,
        "distance_to_monthly_high_pct": 0.25,
        "distance_to_weekly_low_pct": 0.02,
        "distance_to_weekly_high_pct": 0.15,
        "distance_to_daily_low_pct": 0.01,
        "distance_to_daily_high_pct": 0.08,
        "current_volatility": 0.02,
        "historical_volatility": 0.025,
        "expected_market_movement": 0.04,
        "monthly_trend_direction": "BULLISH",
        "weekly_trend_direction": "BEARISH",
        "daily_trend_direction": "BEARISH",
        "monthly_trend_strength": 0.6,
        "weekly_trend_strength": 0.4,
        "daily_trend_strength": 0.3,
    }


@pytest.fixture
def execution_features() -> dict:
    """Typical F-EXE features."""
    return {
        "expected_gross_move": 0.04,
        "expected_round_trip_cost": 0.004,
        "expected_net_opportunity": 0.036,
        "fee_burden_ratio": 0.002,
        "spread_burden_ratio": 0.001,
        "slippage_burden_ratio": 0.001,
        "normal_execution_cost": 0.004,
        "stress_execution_cost": 0.008,
        "liquidity_score": 0.9,
    }


@pytest.fixture
def grid_behavior_features() -> dict:
    """Typical F-GRD features."""
    return {
        "grid_opportunity_frequency": 0.5,
        "positive_cycle_rate": 0.7,
        "grid_cycle_frequency": 0.4,
        "expected_grid_net_opportunity": 0.03,
        "gross_grid_capture": 0.05,
        "net_grid_capture": 0.04,
        "historical_drawdown": 0.20,
        "section_activation_depth": 0.15,
        "capital_deployed": 5000.0,
        "net_pnl": 150.0,
        "section_gap_utilization": 0.6,
        "section_transition_rate": 0.5,
        "uniform_grid_spacing": 0.01,
        "expected_grid_round_trip_cost": 0.004,
        "capital_deployment_velocity": 0.3,
        "peak_exposure": 0.6,
        "capital_exhaustion_frequency": 0.05,
        "minimum_capital_reserve": 0.3,
        "maximum_section_depth_frequency": 0.1,
        "recovery_rate": 0.65,
        "average_recovery_time": 10.0,
        "cost_basis_improvement_ratio": 0.05,
        "drawdown": 0.15,
        "section_activation_rate": 0.7,
        "coin_accumulated": 0.5,
        "recovery_failure_rate": 0.1,
        "maximum_strategy_drawdown": 0.25,
        "expected_net_opportunity": 0.03,
        "execution_cost_ratio": 0.1,
        "grid_capture_efficiency": 0.8,
        "section_2_activation_rate": 0.4,
        "section_3_activation_rate": 0.1,
    }


class TestDerivedMLExtractor:
    """Tests for DerivedMLExtractor."""

    def test_extract_returns_all_domains(
        self,
        extractor,
        observation_ts,
        market_state_features,
        execution_features,
        grid_behavior_features,
    ):
        """Extraction populates all 8 domains."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
            execution_features=execution_features,
            grid_behavior_features=grid_behavior_features,
        )

        assert isinstance(features, DerivedMLFeatures)
        assert features.market_id == "BTC-USDT"
        assert features.feature_version == DERIVED_ML_VERSION
        assert len(features.structural) > 0
        assert len(features.proximity) > 0
        assert len(features.trend) > 0
        assert len(features.volatility) > 0
        assert len(features.execution) > 0
        assert len(features.grid) > 0
        assert len(features.capital_recovery) > 0
        assert len(features.historical) > 0

    def test_structural_alignment_high_when_positions_similar(
        self,
        extractor,
        observation_ts,
        market_state_features,
    ):
        """Similar price positions produce high alignment."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
        )

        alignment = features.structural["multi_timeframe_price_alignment"]
        assert alignment.is_available
        assert alignment.value > 0.8  # Positions 0.20, 0.25, 0.30 are close

    def test_low_alignment_high_when_all_positions_low(
        self,
        extractor,
        observation_ts,
    ):
        """Very low price positions produce positive low-alignment."""
        low_positions = {
            "monthly_price_position": 0.05,
            "weekly_price_position": 0.08,
            "daily_price_position": 0.10,
        }
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=low_positions,
        )

        low_alignment = features.structural["multi_timeframe_low_alignment"]
        assert low_alignment.is_available
        assert low_alignment.value > 0.5

    def test_corrective_structure_context_detected(
        self,
        extractor,
        observation_ts,
        market_state_features,
    ):
        """Monthly bullish + weekly/daily bearish = corrective setup."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
        )

        corrective = features.trend["corrective_structure_context"]
        assert corrective.is_available
        assert corrective.value > 0.5

    def test_counter_trend_pressure_high(
        self,
        extractor,
        observation_ts,
        market_state_features,
    ):
        """Opposing timeframes produce counter-trend pressure."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
        )

        pressure = features.trend["counter_trend_pressure"]
        assert pressure.is_available
        assert pressure.value > 0.5  # Monthly vs weekly/daily opposition

    def test_execution_cost_adjusted_opportunity(
        self,
        extractor,
        observation_ts,
        execution_features,
    ):
        """Execution-cost-adjusted opportunity = gross - round trip cost."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            execution_features=execution_features,
        )

        adjusted = features.execution["execution_cost_adjusted_opportunity"]
        assert adjusted.is_available
        assert adjusted.value == pytest.approx(0.036, rel=0.01)

    def test_execution_retention_ratio(
        self,
        extractor,
        observation_ts,
        execution_features,
    ):
        """Retention ratio = net / gross."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            execution_features=execution_features,
        )

        retention = features.execution["execution_opportunity_retention_ratio"]
        assert retention.is_available
        assert retention.value == pytest.approx(0.9, rel=0.01)

    def test_grid_spacing_economic_fit_positive(
        self,
        extractor,
        observation_ts,
        grid_behavior_features,
    ):
        """Grid spacing exceeding costs produces positive fit."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            grid_behavior_features=grid_behavior_features,
        )

        fit = features.grid["grid_spacing_economic_fit"]
        assert fit.is_available
        assert fit.value > 0  # 0.01 spacing > 0.004 cost

    def test_missing_data_produces_insufficient_availability(
        self,
        extractor,
        observation_ts,
    ):
        """Missing upstream features produce INSUFFICIENT_DATA availability."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features={},
            execution_features={},
            grid_behavior_features={},
        )

        alignment = features.structural["multi_timeframe_price_alignment"]
        assert not alignment.is_available
        assert alignment.availability == FeatureAvailability.INSUFFICIENT_DATA
        assert alignment.value is None

    def test_to_flat_dict(self, extractor, observation_ts, market_state_features):
        """Flat dict contains domain-prefixed feature names."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
        )

        flat = features.to_flat_dict()
        assert "structural_multi_timeframe_price_alignment" in flat
        assert "trend_corrective_structure_context" in flat

    def test_available_feature_count(
        self,
        extractor,
        observation_ts,
        market_state_features,
        execution_features,
        grid_behavior_features,
    ):
        """Available feature count reflects populated features."""
        features = extractor.extract(
            observation_timestamp=observation_ts,
            market_id="BTC-USDT",
            market_state_features=market_state_features,
            execution_features=execution_features,
            grid_behavior_features=grid_behavior_features,
        )

        assert features.available_feature_count > 20

    def test_trend_encoding(self, extractor):
        """Trend directions encoded as -1, 0, +1."""
        assert extractor._encode_trend("BULLISH") == 1.0
        assert extractor._encode_trend("BEARISH") == -1.0
        assert extractor._encode_trend("NEUTRAL") == 0.0
        assert extractor._encode_trend(None) is None


class TestFeatureValue:
    """Tests for FeatureValue."""

    def test_is_available(self):
        fv = FeatureValue(value=0.5)
        assert fv.is_available

    def test_not_available_when_none(self):
        fv = FeatureValue(value=None)
        assert not fv.is_available

    def test_not_available_when_flagged(self):
        fv = FeatureValue(value=0.5, availability=FeatureAvailability.INSUFFICIENT_DATA)
        assert not fv.is_available
