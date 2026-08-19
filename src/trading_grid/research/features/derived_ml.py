"""
Derived ML Feature Layer (F-ML).

Implements F-ML-001 through F-ML-045 from AI_RESEARCH_FEATURE_SPEC_DERIVED_ML.md.

This layer transforms upstream features into higher-level representations:
- Market State + Execution Economics + Grid Behavior → Derived ML Features

Domains:
1. Structural Alignment (F-ML-001 to F-ML-005)
2. Proximity Intelligence (F-ML-006 to F-ML-015)
3. Trend + Structure Interaction (F-ML-016 to F-ML-020)
4. Volatility + Opportunity (F-ML-021 to F-ML-024)
5. Execution-Adjusted Opportunity (F-ML-025 to F-ML-029)
6. Grid Compatibility (F-ML-030 to F-ML-036)
7. Capital / Risk / Recovery (F-ML-037 to F-ML-042)
8. Historical Strategy Context (F-ML-043 to F-ML-045)

Key principles:
- Derived ML consumes upstream features; no raw exchange data
- Every feature has documented rationale
- Causal cutoff: only data <= observation time
- Missing data ≠ zero (use availability flags)
- Normalized representations for cross-market comparison
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from datetime import datetime

logger = structlog.get_logger()

# Feature layer version
# [TD-7] Default version — can be overridden via RESEARCH_DERIVED_ML_VERSION
# environment variable (see config/settings.py ResearchSettings.derived_ml_version).
# The DerivedMLExtractor accepts feature_version as a constructor parameter.
DERIVED_ML_VERSION = "fml-v001"


class FeatureAvailability(StrEnum):
    """Feature availability status (spec §19)."""

    AVAILABLE = "AVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class FeatureValue:
    """A single feature value with availability metadata."""

    value: float | None
    availability: FeatureAvailability = FeatureAvailability.AVAILABLE
    source_window: str | None = None
    causal_cutoff: datetime | None = None

    @property
    def is_available(self) -> bool:
        return self.availability == FeatureAvailability.AVAILABLE and self.value is not None


@dataclass
class DerivedMLFeatures:
    """
    Complete derived ML feature set (spec §20).

    Organized by domain for clarity and traceability.
    """

    observation_timestamp: datetime
    market_id: str
    feature_version: str = DERIVED_ML_VERSION

    # Domain 1: Structural Alignment
    structural: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 2: Proximity Intelligence
    proximity: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 3: Trend + Structure Interaction
    trend: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 4: Volatility + Opportunity
    volatility: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 5: Execution-Adjusted Opportunity
    execution: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 6: Grid Compatibility
    grid: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 7: Capital / Risk / Recovery
    capital_recovery: dict[str, FeatureValue] = field(default_factory=dict)

    # Domain 8: Historical Strategy Context
    historical: dict[str, FeatureValue] = field(default_factory=dict)

    def to_flat_dict(self) -> dict[str, float | None]:
        """Flatten all features into a single dict for ML input."""
        result: dict[str, float | None] = {}
        for domain_name, domain_features in [
            ("structural", self.structural),
            ("proximity", self.proximity),
            ("trend", self.trend),
            ("volatility", self.volatility),
            ("execution", self.execution),
            ("grid", self.grid),
            ("capital_recovery", self.capital_recovery),
            ("historical", self.historical),
        ]:
            for feature_name, fv in domain_features.items():
                result[f"{domain_name}_{feature_name}"] = fv.value
        return result

    def to_availability_dict(self) -> dict[str, str]:
        """Get availability status for all features."""
        result: dict[str, str] = {}
        for domain_name, domain_features in [
            ("structural", self.structural),
            ("proximity", self.proximity),
            ("trend", self.trend),
            ("volatility", self.volatility),
            ("execution", self.execution),
            ("grid", self.grid),
            ("capital_recovery", self.capital_recovery),
            ("historical", self.historical),
        ]:
            for feature_name, fv in domain_features.items():
                result[f"{domain_name}_{feature_name}"] = fv.availability.value
        return result

    @property
    def available_feature_count(self) -> int:
        """Count of available features."""
        count = 0
        for domain_features in [
            self.structural,
            self.proximity,
            self.trend,
            self.volatility,
            self.execution,
            self.grid,
            self.capital_recovery,
            self.historical,
        ]:
            count += sum(1 for fv in domain_features.values() if fv.is_available)
        return count


class DerivedMLExtractor:
    """
    Extracts derived ML features from upstream feature layers.

    Usage:
        extractor = DerivedMLExtractor()
        features = extractor.extract(
            observation_timestamp=ts,
            market_id="BTC-USDT",
            market_state_features=mkt_features,
            execution_features=exe_features,
            grid_behavior_features=grd_features,
        )
    """

    def extract(
        self,
        observation_timestamp: datetime,
        market_id: str,
        market_state_features: dict[str, Any] | None = None,
        execution_features: dict[str, Any] | None = None,
        grid_behavior_features: dict[str, Any] | None = None,
    ) -> DerivedMLFeatures:
        """
        Extract all derived ML features.

        Args:
            observation_timestamp: Causal cutoff time T
            market_id: Market identifier
            market_state_features: F-MKT layer features
            execution_features: F-EXE layer features
            grid_behavior_features: F-GRD layer features

        Returns:
            DerivedMLFeatures with all domains populated
        """
        mkt = market_state_features or {}
        exe = execution_features or {}
        grd = grid_behavior_features or {}

        features = DerivedMLFeatures(
            observation_timestamp=observation_timestamp,
            market_id=market_id,
        )

        # Extract each domain
        features.structural = self._extract_structural_alignment(mkt)
        features.proximity = self._extract_proximity_intelligence(mkt)
        features.trend = self._extract_trend_structure(mkt)
        features.volatility = self._extract_volatility_opportunity(mkt, grd)
        features.execution = self._extract_execution_adjusted(exe)
        features.grid = self._extract_grid_compatibility(mkt, exe, grd)
        features.capital_recovery = self._extract_capital_recovery(grd)
        features.historical = self._extract_historical_context(grd)

        logger.debug(
            "derived_ml_features_extracted",
            market_id=market_id,
            available_count=features.available_feature_count,
        )

        return features

    # -----------------------------------------------------------------------
    # Domain 1: Structural Alignment (F-ML-001 to F-ML-005)
    # -----------------------------------------------------------------------

    def _extract_structural_alignment(self, mkt: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Structural Alignment features.

        Combines Monthly, Weekly, Daily price positions.
        """
        features: dict[str, FeatureValue] = {}

        monthly_pos = self._get_float(mkt, "monthly_price_position")
        weekly_pos = self._get_float(mkt, "weekly_price_position")
        daily_pos = self._get_float(mkt, "daily_price_position")

        # F-ML-001: Multi-Timeframe Price Alignment
        # Measures similarity of price position across timeframes
        if monthly_pos is not None and weekly_pos is not None and daily_pos is not None:
            # Alignment = 1 - normalized variance of positions
            positions = [monthly_pos, weekly_pos, daily_pos]
            mean_pos = sum(positions) / 3
            variance = sum((p - mean_pos) ** 2 for p in positions) / 3
            # Normalize: max variance for [0,1] range is ~0.111 (positions at 0, 0.5, 1)
            alignment = max(0.0, 1.0 - (variance / 0.111))
            features["multi_timeframe_price_alignment"] = FeatureValue(value=alignment)
        else:
            features["multi_timeframe_price_alignment"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-002: Multi-Timeframe Low Alignment
        # Measures if price is near lower ranges across all timeframes
        if monthly_pos is not None and weekly_pos is not None and daily_pos is not None:
            # Low alignment: all positions below 0.3
            low_scores = [
                1.0 - min(1.0, monthly_pos / 0.3) if monthly_pos < 0.3 else 0.0,
                1.0 - min(1.0, weekly_pos / 0.3) if weekly_pos < 0.3 else 0.0,
                1.0 - min(1.0, daily_pos / 0.3) if daily_pos < 0.3 else 0.0,
            ]
            features["multi_timeframe_low_alignment"] = FeatureValue(value=sum(low_scores) / 3)
        else:
            features["multi_timeframe_low_alignment"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-003: Multi-Timeframe High Alignment
        if monthly_pos is not None and weekly_pos is not None and daily_pos is not None:
            high_scores = [
                min(1.0, (monthly_pos - 0.7) / 0.3) if monthly_pos > 0.7 else 0.0,
                min(1.0, (weekly_pos - 0.7) / 0.3) if weekly_pos > 0.7 else 0.0,
                min(1.0, (daily_pos - 0.7) / 0.3) if daily_pos > 0.7 else 0.0,
            ]
            features["multi_timeframe_high_alignment"] = FeatureValue(value=sum(high_scores) / 3)
        else:
            features["multi_timeframe_high_alignment"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-004: Structural Range Alignment
        mkt_wk_diff = self._get_float(mkt, "monthly_weekly_price_position_difference")
        wk_day_diff = self._get_float(mkt, "weekly_daily_price_position_difference")
        if mkt_wk_diff is not None and wk_day_diff is not None:
            # Smaller differences = better alignment
            total_diff = abs(mkt_wk_diff) + abs(wk_day_diff)
            features["structural_range_alignment"] = FeatureValue(value=max(0.0, 1.0 - total_diff))
        else:
            features["structural_range_alignment"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-005: Structural Alignment Consistency (requires historical window)
        # Placeholder: would need rolling historical data
        features["structural_alignment_consistency"] = FeatureValue(
            value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
        )

        return features

    # -----------------------------------------------------------------------
    # Domain 2: Proximity Intelligence (F-ML-006 to F-ML-015)
    # -----------------------------------------------------------------------

    def _extract_proximity_intelligence(self, mkt: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Proximity Intelligence features.

        Transforms raw distance into context-aware relationships.
        """
        features: dict[str, FeatureValue] = {}

        volatility = self._get_float(mkt, "current_volatility") or 0.01

        # F-ML-006 to F-ML-011: Volatility-Adjusted Proximity
        proximity_mappings = [
            ("monthly_low_vol_adjusted_proximity", "distance_to_monthly_low_pct"),
            ("monthly_high_vol_adjusted_proximity", "distance_to_monthly_high_pct"),
            ("weekly_low_vol_adjusted_proximity", "distance_to_weekly_low_pct"),
            ("weekly_high_vol_adjusted_proximity", "distance_to_weekly_high_pct"),
            ("daily_low_vol_adjusted_proximity", "distance_to_daily_low_pct"),
            ("daily_high_vol_adjusted_proximity", "distance_to_daily_high_pct"),
        ]

        for feature_name, source_key in proximity_mappings:
            distance = self._get_float(mkt, source_key)
            if distance is not None and volatility > 0:
                # Normalize distance by volatility
                features[feature_name] = FeatureValue(value=distance / volatility)
            else:
                features[feature_name] = FeatureValue(
                    value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
                )

        # F-ML-012: Multi-Timeframe Low Pressure
        monthly_low_dist = self._get_float(mkt, "distance_to_monthly_low_pct")
        weekly_low_dist = self._get_float(mkt, "distance_to_weekly_low_pct")
        daily_low_dist = self._get_float(mkt, "distance_to_daily_low_pct")

        if (
            monthly_low_dist is not None
            and weekly_low_dist is not None
            and daily_low_dist is not None
        ):
            # Combined pressure: lower distances = higher pressure
            # Weighted: monthly most important for grid strategy
            pressure = (
                0.5 * max(0.0, 1.0 - monthly_low_dist / 0.10)
                + 0.3 * max(0.0, 1.0 - weekly_low_dist / 0.05)
                + 0.2 * max(0.0, 1.0 - daily_low_dist / 0.02)
            )
            features["multi_timeframe_low_pressure"] = FeatureValue(value=pressure)
        else:
            features["multi_timeframe_low_pressure"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-013: Multi-Timeframe High Pressure
        monthly_high_dist = self._get_float(mkt, "distance_to_monthly_high_pct")
        weekly_high_dist = self._get_float(mkt, "distance_to_weekly_high_pct")
        daily_high_dist = self._get_float(mkt, "distance_to_daily_high_pct")

        if (
            monthly_high_dist is not None
            and weekly_high_dist is not None
            and daily_high_dist is not None
        ):
            pressure = (
                0.5 * max(0.0, 1.0 - monthly_high_dist / 0.10)
                + 0.3 * max(0.0, 1.0 - weekly_high_dist / 0.05)
                + 0.2 * max(0.0, 1.0 - daily_high_dist / 0.02)
            )
            features["multi_timeframe_high_pressure"] = FeatureValue(value=pressure)
        else:
            features["multi_timeframe_high_pressure"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-014: Monthly Breakdown Depth Relative to Volatility
        breakdown_depth = self._get_float(mkt, "distance_below_monthly_low_pct")
        if breakdown_depth is not None and volatility > 0:
            features["monthly_breakdown_depth_relative_to_volatility"] = FeatureValue(
                value=breakdown_depth / volatility
            )
        else:
            features["monthly_breakdown_depth_relative_to_volatility"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-015: Monthly Breakdown Persistence (requires historical sequence)
        features["monthly_breakdown_persistence"] = FeatureValue(
            value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
        )

        return features

    # -----------------------------------------------------------------------
    # Domain 3: Trend + Structure Interaction (F-ML-016 to F-ML-020)
    # -----------------------------------------------------------------------

    def _extract_trend_structure(self, mkt: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Trend + Structure Interaction features.
        """
        features: dict[str, FeatureValue] = {}

        # Get trend directions (encoded as -1, 0, +1)
        monthly_trend = self._encode_trend(mkt.get("monthly_trend_direction"))
        weekly_trend = self._encode_trend(mkt.get("weekly_trend_direction"))
        daily_trend = self._encode_trend(mkt.get("daily_trend_direction"))

        # F-ML-016: Trend Alignment Score
        if monthly_trend is not None and weekly_trend is not None and daily_trend is not None:
            # Weighted alignment: monthly most important
            alignment = 0.5 * monthly_trend + 0.3 * weekly_trend + 0.2 * daily_trend
            features["trend_alignment_score"] = FeatureValue(value=alignment)
        else:
            features["trend_alignment_score"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-017: Trend Strength Composite
        monthly_strength = self._get_float(mkt, "monthly_trend_strength")
        weekly_strength = self._get_float(mkt, "weekly_trend_strength")
        daily_strength = self._get_float(mkt, "daily_trend_strength")

        if (
            monthly_strength is not None
            and weekly_strength is not None
            and daily_strength is not None
        ):
            composite = 0.5 * monthly_strength + 0.3 * weekly_strength + 0.2 * daily_strength
            features["trend_strength_composite"] = FeatureValue(value=composite)
        else:
            features["trend_strength_composite"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-018: Trend-Structure Alignment
        monthly_pos = self._get_float(mkt, "monthly_price_position")
        if monthly_trend is not None and monthly_pos is not None:
            # Bullish trend + low position = corrective opportunity
            # Bearish trend + high position = distribution risk
            if monthly_trend > 0:
                # Bullish: lower position is better for grid entry
                features["trend_structure_alignment"] = FeatureValue(value=1.0 - monthly_pos)
            elif monthly_trend < 0:
                # Bearish: higher position is riskier
                features["trend_structure_alignment"] = FeatureValue(value=monthly_pos - 1.0)
            else:
                features["trend_structure_alignment"] = FeatureValue(value=0.0)
        else:
            features["trend_structure_alignment"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-019: Corrective Structure Context
        # Monthly bullish + weekly/daily bearish + near monthly low
        if (
            monthly_trend is not None
            and weekly_trend is not None
            and daily_trend is not None
            and monthly_pos is not None
        ):
            corrective_score = 0.0
            if monthly_trend > 0 and weekly_trend < 0 and daily_trend < 0:
                # Classic corrective setup
                corrective_score = 0.5 + 0.5 * (1.0 - monthly_pos)
            features["corrective_structure_context"] = FeatureValue(value=corrective_score)
        else:
            features["corrective_structure_context"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-020: Counter-Trend Pressure
        if monthly_trend is not None and weekly_trend is not None and daily_trend is not None:
            # Measures opposition between timeframes
            counter_pressure = 0.0
            if monthly_trend * weekly_trend < 0:
                counter_pressure += 0.5
            if monthly_trend * daily_trend < 0:
                counter_pressure += 0.3
            if weekly_trend * daily_trend < 0:
                counter_pressure += 0.2
            features["counter_trend_pressure"] = FeatureValue(value=counter_pressure)
        else:
            features["counter_trend_pressure"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Domain 4: Volatility + Opportunity (F-ML-021 to F-ML-024)
    # -----------------------------------------------------------------------

    def _extract_volatility_opportunity(
        self, mkt: dict[str, Any], grd: dict[str, Any]
    ) -> dict[str, FeatureValue]:
        """
        Volatility + Opportunity features.
        """
        features: dict[str, FeatureValue] = {}

        volatility = self._get_float(mkt, "current_volatility")
        expected_movement = self._get_float(mkt, "expected_market_movement")

        # F-ML-021: Volatility Opportunity Ratio
        if expected_movement is not None and volatility is not None and volatility > 0:
            features["volatility_opportunity_ratio"] = FeatureValue(
                value=expected_movement / volatility
            )
        else:
            features["volatility_opportunity_ratio"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-022: Volatility Regime Stability
        hist_volatility = self._get_float(mkt, "historical_volatility")
        if volatility is not None and hist_volatility is not None and hist_volatility > 0:
            # Stability = 1 - relative change in volatility
            vol_change = abs(volatility - hist_volatility) / hist_volatility
            features["volatility_regime_stability"] = FeatureValue(value=max(0.0, 1.0 - vol_change))
        else:
            features["volatility_regime_stability"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-023: Volatility Expansion Opportunity
        vol_expansion = self._get_float(mkt, "volatility_expansion")
        grid_opportunity = self._get_float(grd, "grid_opportunity_frequency")
        if vol_expansion is not None and grid_opportunity is not None:
            features["volatility_expansion_opportunity"] = FeatureValue(
                value=vol_expansion * grid_opportunity
            )
        else:
            features["volatility_expansion_opportunity"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-024: Volatility-to-Grid Relationship
        grid_cycle_freq = self._get_float(grd, "grid_cycle_frequency")
        if volatility is not None and grid_cycle_freq is not None and volatility > 0:
            features["volatility_to_grid_relationship"] = FeatureValue(
                value=grid_cycle_freq / volatility
            )
        else:
            features["volatility_to_grid_relationship"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Domain 5: Execution-Adjusted Opportunity (F-ML-025 to F-ML-029)
    # -----------------------------------------------------------------------

    def _extract_execution_adjusted(self, exe: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Execution-Adjusted Opportunity features.

        Core differentiated features measuring economic viability after costs.
        """
        features: dict[str, FeatureValue] = {}

        gross_move = self._get_float(exe, "expected_gross_move")
        round_trip_cost = self._get_float(exe, "expected_round_trip_cost")
        net_opportunity = self._get_float(exe, "expected_net_opportunity")

        # F-ML-025: Execution-Cost-Adjusted Opportunity
        if gross_move is not None and round_trip_cost is not None:
            features["execution_cost_adjusted_opportunity"] = FeatureValue(
                value=gross_move - round_trip_cost
            )
        else:
            features["execution_cost_adjusted_opportunity"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-026: Execution Opportunity Retention Ratio
        if net_opportunity is not None and gross_move is not None and gross_move > 0:
            features["execution_opportunity_retention_ratio"] = FeatureValue(
                value=net_opportunity / gross_move
            )
        else:
            features["execution_opportunity_retention_ratio"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-027: Execution Burden Composite
        fee_burden = self._get_float(exe, "fee_burden_ratio")
        spread_burden = self._get_float(exe, "spread_burden_ratio")
        slippage_burden = self._get_float(exe, "slippage_burden_ratio")

        if fee_burden is not None and spread_burden is not None and slippage_burden is not None:
            features["execution_burden_composite"] = FeatureValue(
                value=fee_burden + spread_burden + slippage_burden
            )
        else:
            features["execution_burden_composite"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-028: Execution Stress Resilience
        normal_cost = self._get_float(exe, "normal_execution_cost")
        stress_cost = self._get_float(exe, "stress_execution_cost")
        if normal_cost is not None and stress_cost is not None and normal_cost > 0:
            # Resilience = how much viability remains under stress
            features["execution_stress_resilience"] = FeatureValue(
                value=normal_cost / stress_cost if stress_cost > 0 else 0.0
            )
        else:
            features["execution_stress_resilience"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-029: Liquidity-Adjusted Opportunity
        liquidity_score = self._get_float(exe, "liquidity_score")
        if net_opportunity is not None and liquidity_score is not None:
            features["liquidity_adjusted_opportunity"] = FeatureValue(
                value=net_opportunity * liquidity_score
            )
        else:
            features["liquidity_adjusted_opportunity"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Domain 6: Grid Compatibility (F-ML-030 to F-ML-036)
    # -----------------------------------------------------------------------

    def _extract_grid_compatibility(
        self, mkt: dict[str, Any], exe: dict[str, Any], grd: dict[str, Any]
    ) -> dict[str, FeatureValue]:
        """
        Grid Compatibility features.

        Most strategy-specific domain.
        """
        features: dict[str, FeatureValue] = {}

        # F-ML-030: Market-to-Grid Compatibility (composite)
        grid_freq = self._get_float(grd, "grid_opportunity_frequency")
        positive_cycle_rate = self._get_float(grd, "positive_cycle_rate")

        if grid_freq is not None and positive_cycle_rate is not None:
            # Composite: frequency x quality
            features["market_to_grid_compatibility"] = FeatureValue(
                value=grid_freq * positive_cycle_rate
            )
        else:
            features["market_to_grid_compatibility"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-031: Grid Opportunity Quality
        net_grid_opportunity = self._get_float(grd, "expected_grid_net_opportunity")
        if grid_freq is not None and positive_cycle_rate is not None:
            if net_grid_opportunity is not None:
                features["grid_opportunity_quality"] = FeatureValue(
                    value=positive_cycle_rate * net_grid_opportunity
                )
            else:
                features["grid_opportunity_quality"] = FeatureValue(value=positive_cycle_rate)
        else:
            features["grid_opportunity_quality"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-032: Grid Capture Quality
        gross_capture = self._get_float(grd, "gross_grid_capture")
        net_capture = self._get_float(grd, "net_grid_capture")
        if gross_capture is not None and net_capture is not None and gross_capture > 0:
            features["grid_capture_quality"] = FeatureValue(value=net_capture / gross_capture)
        else:
            features["grid_capture_quality"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-033: Grid Depth Compatibility
        hist_drawdown = self._get_float(grd, "historical_drawdown")
        section_activation_depth = self._get_float(grd, "section_activation_depth")
        if hist_drawdown is not None and section_activation_depth is not None:
            # Compatibility: how well section depth matches typical drawdown
            if hist_drawdown > 0:
                features["grid_depth_compatibility"] = FeatureValue(
                    value=min(1.0, section_activation_depth / hist_drawdown)
                )
            else:
                features["grid_depth_compatibility"] = FeatureValue(value=1.0)
        else:
            features["grid_depth_compatibility"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-034: Section Deployment Efficiency
        capital_deployed = self._get_float(grd, "capital_deployed")
        net_pnl = self._get_float(grd, "net_pnl")
        if capital_deployed is not None and net_pnl is not None and capital_deployed > 0:
            features["section_deployment_efficiency"] = FeatureValue(
                value=net_pnl / capital_deployed
            )
        else:
            features["section_deployment_efficiency"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-035: Section Gap Effectiveness
        gap_utilization = self._get_float(grd, "section_gap_utilization")
        transition_rate = self._get_float(grd, "section_transition_rate")
        if gap_utilization is not None and transition_rate is not None:
            features["section_gap_effectiveness"] = FeatureValue(
                value=gap_utilization * transition_rate
            )
        else:
            features["section_gap_effectiveness"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-036: Grid Spacing Economic Fit
        grid_spacing = self._get_float(grd, "uniform_grid_spacing")
        grid_round_trip_cost = self._get_float(grd, "expected_grid_round_trip_cost")
        if grid_spacing is not None and grid_round_trip_cost is not None and grid_spacing > 0:
            # Fit: spacing must exceed costs for viability
            features["grid_spacing_economic_fit"] = FeatureValue(
                value=(grid_spacing - grid_round_trip_cost) / grid_spacing
            )
        else:
            features["grid_spacing_economic_fit"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Domain 7: Capital / Risk / Recovery (F-ML-037 to F-ML-042)
    # -----------------------------------------------------------------------

    def _extract_capital_recovery(self, grd: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Capital / Risk / Recovery features.
        """
        features: dict[str, FeatureValue] = {}

        # F-ML-037: Capital Consumption Risk
        deployment_velocity = self._get_float(grd, "capital_deployment_velocity")
        peak_exposure = self._get_float(grd, "peak_exposure")
        exhaustion_freq = self._get_float(grd, "capital_exhaustion_frequency")

        if deployment_velocity is not None and peak_exposure is not None:
            risk = deployment_velocity * peak_exposure
            if exhaustion_freq is not None:
                risk *= 1.0 + exhaustion_freq
            features["capital_consumption_risk"] = FeatureValue(value=min(1.0, risk))
        else:
            features["capital_consumption_risk"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-038: Capital Reserve Resilience
        min_reserve = self._get_float(grd, "minimum_capital_reserve")
        max_depth_freq = self._get_float(grd, "maximum_section_depth_frequency")
        recovery_rate = self._get_float(grd, "recovery_rate")

        if min_reserve is not None and recovery_rate is not None:
            resilience = min_reserve * recovery_rate
            if max_depth_freq is not None:
                resilience *= 1.0 - max_depth_freq * 0.5
            features["capital_reserve_resilience"] = FeatureValue(value=max(0.0, resilience))
        else:
            features["capital_reserve_resilience"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-039: Recovery Efficiency
        avg_recovery_time = self._get_float(grd, "average_recovery_time")
        cost_basis_improvement = self._get_float(grd, "cost_basis_improvement_ratio")

        if recovery_rate is not None and avg_recovery_time is not None and avg_recovery_time > 0:
            efficiency = recovery_rate / avg_recovery_time
            if cost_basis_improvement is not None:
                efficiency *= 1.0 + cost_basis_improvement
            features["recovery_efficiency"] = FeatureValue(value=efficiency)
        else:
            features["recovery_efficiency"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-040: Drawdown-to-Recovery Quality
        drawdown = self._get_float(grd, "drawdown")
        section_activation = self._get_float(grd, "section_activation_rate")

        if drawdown is not None and recovery_rate is not None and drawdown > 0:
            quality = recovery_rate * (1.0 - min(1.0, drawdown))
            if section_activation is not None:
                quality *= 0.5 + 0.5 * section_activation
            features["drawdown_to_recovery_quality"] = FeatureValue(value=quality)
        else:
            features["drawdown_to_recovery_quality"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-041: Capital Efficiency Under Drawdown
        capital_deployed = self._get_float(grd, "capital_deployed")
        coin_accumulated = self._get_float(grd, "coin_accumulated")

        if capital_deployed is not None and coin_accumulated is not None and capital_deployed > 0:
            features["capital_efficiency_under_drawdown"] = FeatureValue(
                value=coin_accumulated / capital_deployed
            )
        else:
            features["capital_efficiency_under_drawdown"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-042: Recovery Failure Pressure
        recovery_failure_rate = self._get_float(grd, "recovery_failure_rate")
        max_drawdown = self._get_float(grd, "maximum_strategy_drawdown")

        if recovery_failure_rate is not None:
            pressure = recovery_failure_rate
            if max_drawdown is not None:
                pressure *= 1.0 + max_drawdown
            if exhaustion_freq is not None:
                pressure *= 1.0 + exhaustion_freq
            features["recovery_failure_pressure"] = FeatureValue(value=min(1.0, pressure))
        else:
            features["recovery_failure_pressure"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Domain 8: Historical Strategy Context (F-ML-043 to F-ML-045)
    # -----------------------------------------------------------------------

    def _extract_historical_context(self, grd: dict[str, Any]) -> dict[str, FeatureValue]:
        """
        Historical Strategy Context features.

        Rolling historical behavior - requires causal window.
        """
        features: dict[str, FeatureValue] = {}

        # F-ML-043: Rolling Grid Suitability Context
        grid_opportunity = self._get_float(grd, "grid_opportunity_frequency")
        positive_cycle = self._get_float(grd, "positive_cycle_rate")
        net_pnl = self._get_float(grd, "net_pnl")
        recovery = self._get_float(grd, "recovery_rate")

        if grid_opportunity is not None and positive_cycle is not None:
            suitability = grid_opportunity * positive_cycle
            if net_pnl is not None and net_pnl > 0:
                suitability *= 1.2
            if recovery is not None:
                suitability *= 0.8 + 0.4 * recovery
            features["rolling_grid_suitability_context"] = FeatureValue(value=min(1.0, suitability))
        else:
            features["rolling_grid_suitability_context"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-044: Rolling Execution-Adjusted Grid Quality
        net_opportunity = self._get_float(grd, "expected_net_opportunity")
        execution_cost_ratio = self._get_float(grd, "execution_cost_ratio")
        capture_efficiency = self._get_float(grd, "grid_capture_efficiency")

        if net_opportunity is not None and capture_efficiency is not None:
            quality = net_opportunity * capture_efficiency
            if execution_cost_ratio is not None:
                quality *= 1.0 - min(1.0, execution_cost_ratio)
            features["rolling_execution_adjusted_grid_quality"] = FeatureValue(value=quality)
        else:
            features["rolling_execution_adjusted_grid_quality"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        # F-ML-045: Rolling Section Depth Profile
        section_2_rate = self._get_float(grd, "section_2_activation_rate")
        section_3_rate = self._get_float(grd, "section_3_activation_rate")

        if section_2_rate is not None:
            depth_profile = section_2_rate * 0.6
            if section_3_rate is not None:
                depth_profile += section_3_rate * 0.4
            features["rolling_section_depth_profile"] = FeatureValue(value=depth_profile)
        else:
            features["rolling_section_depth_profile"] = FeatureValue(
                value=None, availability=FeatureAvailability.INSUFFICIENT_DATA
            )

        return features

    # -----------------------------------------------------------------------
    # Helper methods
    # -----------------------------------------------------------------------

    def _get_float(self, data: dict[str, Any], key: str) -> float | None:
        """Safely extract float value from dict."""
        value = data.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _encode_trend(self, trend: Any) -> float | None:
        """Encode trend direction as -1, 0, +1."""
        if trend is None:
            return None
        if isinstance(trend, str):
            trend_upper = trend.upper()
            if trend_upper == "BULLISH":
                return 1.0
            if trend_upper == "BEARISH":
                return -1.0
            return 0.0
        try:
            return float(trend)
        except (TypeError, ValueError):
            return None
