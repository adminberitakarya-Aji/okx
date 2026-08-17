"""
Grid Behavior Feature Layer (F-GRD).

Implements the Grid Behavior features per AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md.

This layer measures how our specific Section-based, uniform-grid,
adaptive-Section-Gap, immediate-execution Grid Strategy behaves
across historical market conditions.

Pipeline:
    Market State + Execution Economics + Candidate Blueprint
        → Historical Grid Simulation
        → Grid Behavior Features

Features F-GRD-001 through F-GRD-090.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from okx_trading.research.simulator.grid_simulator import (
        SimulationConfig,
        SimulationEvent,
        SimulationResult,
    )

logger = structlog.get_logger()


class GridBehaviorAvailability(StrEnum):
    """Availability flags for feature groups."""

    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    REQUIRES_MULTI_RUN = "REQUIRES_MULTI_RUN"


@dataclass
class GridBehaviorFeatures:
    """
    Grid Behavior features (F-GRD-001 to F-GRD-090).

    Extracted from a single SimulationResult. Features that require
    multiple simulation runs (sensitivity) are set to None.
    """

    # Identity
    market_id: str
    observation_timestamp: datetime
    blueprint_id: str
    simulation_run_id: str
    simulation_window_candles: int

    # --- Grid Opportunity (F-GRD-001 to F-GRD-003) ---
    grid_opportunity_frequency: float | None = None  # F-GRD-001
    grid_event_count: int | None = None  # F-GRD-002
    grid_opportunity_density: float | None = None  # F-GRD-003

    # --- Grid Trigger / Hit (F-GRD-004 to F-GRD-006) ---
    grid_level_touch_count: int | None = None  # F-GRD-004
    grid_execution_trigger_count: int | None = None  # F-GRD-005
    grid_trigger_rate: float | None = None  # F-GRD-006

    # --- BUY Behavior (F-GRD-007 to F-GRD-010) ---
    buy_event_count: int | None = None  # F-GRD-007
    buy_frequency: float | None = None  # F-GRD-008
    average_buy_interval: float | None = None  # F-GRD-009
    maximum_buy_burst: int | None = None  # F-GRD-010

    # --- SELL Behavior (F-GRD-011 to F-GRD-014) ---
    sell_event_count: int | None = None  # F-GRD-011
    sell_frequency: float | None = None  # F-GRD-012
    average_sell_interval: float | None = None  # F-GRD-013
    buy_to_sell_completion_rate: float | None = None  # F-GRD-014

    # --- Grid Cycle (F-GRD-015 to F-GRD-019) ---
    grid_cycle_count: int | None = None  # F-GRD-015
    grid_cycle_frequency: float | None = None  # F-GRD-016
    average_cycle_duration: float | None = None  # F-GRD-017
    median_cycle_duration: float | None = None  # F-GRD-018
    cycle_completion_rate: float | None = None  # F-GRD-019

    # --- Cycle Quality (F-GRD-020 to F-GRD-025) ---
    average_cycle_net_pnl: float | None = None  # F-GRD-020
    median_cycle_net_pnl: float | None = None  # F-GRD-021
    positive_cycle_rate: float | None = None  # F-GRD-022
    negative_cycle_rate: float | None = None  # F-GRD-023
    average_positive_cycle: float | None = None  # F-GRD-024
    average_negative_cycle: float | None = None  # F-GRD-025

    # --- Section Activation (F-GRD-026 to F-GRD-030) ---
    section_1_activation_rate: float | None = None  # F-GRD-026
    section_2_activation_rate: float | None = None  # F-GRD-027
    section_3_activation_rate: float | None = None  # F-GRD-028
    section_activation_depth: int | None = None  # F-GRD-029
    maximum_section_depth_frequency: float | None = None  # F-GRD-030

    # --- Section Transition (F-GRD-031 to F-GRD-033) ---
    section_1_to_2_transition_rate: float | None = None  # F-GRD-031
    section_2_to_3_transition_rate: float | None = None  # F-GRD-032
    section_transition_speed: float | None = None  # F-GRD-033

    # --- Section Gap (F-GRD-034 to F-GRD-037) ---
    section_gap_reach_frequency: float | None = None  # F-GRD-034
    average_drawdown_to_section_2: float | None = None  # F-GRD-035
    average_drawdown_to_section_3: float | None = None  # F-GRD-036
    section_gap_utilization: float | None = None  # F-GRD-037

    # --- Capital Deployment (F-GRD-038 to F-GRD-043) ---
    capital_deployed: float | None = None  # F-GRD-038
    capital_deployment_ratio: float | None = None  # F-GRD-039
    peak_capital_deployment: float | None = None  # F-GRD-040
    capital_reserve_remaining: float | None = None  # F-GRD-041
    minimum_capital_reserve: float | None = None  # F-GRD-042
    capital_exhaustion_flag: int | None = None  # F-GRD-043

    # --- Deployment Speed (F-GRD-044 to F-GRD-047) ---
    capital_deployment_velocity: float | None = None  # F-GRD-044
    time_to_50pct_deployment: float | None = None  # F-GRD-045
    time_to_80pct_deployment: float | None = None  # F-GRD-046
    time_to_maximum_deployment: float | None = None  # F-GRD-047

    # --- Exposure (F-GRD-048 to F-GRD-051) ---
    average_exposure: float | None = None  # F-GRD-048
    peak_exposure: float | None = None  # F-GRD-049
    exposure_ratio: float | None = None  # F-GRD-050
    exposure_concentration: float | None = None  # F-GRD-051

    # --- Coin Accumulation (F-GRD-052 to F-GRD-055) ---
    total_coin_accumulated: float | None = None  # F-GRD-052
    average_acquisition_price: float | None = None  # F-GRD-053
    coin_accumulation_efficiency: float | None = None  # F-GRD-054
    additional_coin_from_drawdown: float | None = None  # F-GRD-055

    # --- Cost Basis (F-GRD-056 to F-GRD-058) ---
    average_cost_reduction: float | None = None  # F-GRD-056
    cost_basis_improvement_ratio: float | None = None  # F-GRD-057
    cost_basis_recovery_distance: float | None = None  # F-GRD-058

    # --- Drawdown (F-GRD-059 to F-GRD-062) ---
    max_market_drawdown: float | None = None  # F-GRD-059
    max_strategy_drawdown: float | None = None  # F-GRD-060
    avg_drawdown_at_section_activation: float | None = None  # F-GRD-061
    drawdown_to_max_exposure: float | None = None  # F-GRD-062

    # --- Recovery (F-GRD-063 to F-GRD-067) ---
    recovery_rate: float | None = None  # F-GRD-063
    average_recovery_time: float | None = None  # F-GRD-064
    median_recovery_time: float | None = None  # F-GRD-065
    recovery_after_section_2: float | None = None  # F-GRD-066
    recovery_after_section_3: float | None = None  # F-GRD-067

    # --- Grid Capture (F-GRD-068 to F-GRD-070) ---
    gross_grid_capture: float | None = None  # F-GRD-068
    net_grid_capture: float | None = None  # F-GRD-069
    grid_capture_efficiency: float | None = None  # F-GRD-070

    # --- Strategy Efficiency (F-GRD-071 to F-GRD-074) ---
    capital_efficiency: float | None = None  # F-GRD-071
    trade_efficiency: float | None = None  # F-GRD-072
    cycle_efficiency: float | None = None  # F-GRD-073
    deployment_efficiency: float | None = None  # F-GRD-074

    # --- Strategy Outcome (F-GRD-075 to F-GRD-079) ---
    historical_net_pnl: float | None = None  # F-GRD-075
    net_pnl_return: float | None = None  # F-GRD-076
    realized_pnl: float | None = None  # F-GRD-077
    unrealized_pnl: float | None = None  # F-GRD-078
    total_strategy_pnl: float | None = None  # F-GRD-079

    # --- Profitability Quality (F-GRD-080 to F-GRD-082) ---
    profit_factor: float | None = None  # F-GRD-080
    net_pnl_volatility: float | None = None  # F-GRD-081
    outcome_stability: float | None = None  # F-GRD-082

    # --- Stress Behavior (F-GRD-083 to F-GRD-086) ---
    maximum_capital_stress: float | None = None  # F-GRD-083
    maximum_section_stress: int | None = None  # F-GRD-084
    recovery_failure_rate: float | None = None  # F-GRD-085
    capital_exhaustion_frequency: float | None = None  # F-GRD-086

    # --- Blueprint Sensitivity (F-GRD-087 to F-GRD-090) ---
    # These require multiple simulation runs with varied blueprints
    grid_spacing_sensitivity: float | None = None  # F-GRD-087
    section_gap_sensitivity: float | None = None  # F-GRD-088
    allocation_sensitivity: float | None = None  # F-GRD-089
    section_count_sensitivity: float | None = None  # F-GRD-090

    # Availability flags
    availability: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Convert to flat dictionary for ML pipeline."""
        return {
            "market_id": self.market_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "blueprint_id": self.blueprint_id,
            "simulation_run_id": self.simulation_run_id,
            "simulation_window_candles": self.simulation_window_candles,
            # F-GRD-001 to F-GRD-003
            "grid_opportunity_frequency": self.grid_opportunity_frequency,
            "grid_event_count": self.grid_event_count,
            "grid_opportunity_density": self.grid_opportunity_density,
            # F-GRD-004 to F-GRD-006
            "grid_level_touch_count": self.grid_level_touch_count,
            "grid_execution_trigger_count": self.grid_execution_trigger_count,
            "grid_trigger_rate": self.grid_trigger_rate,
            # F-GRD-007 to F-GRD-010
            "buy_event_count": self.buy_event_count,
            "buy_frequency": self.buy_frequency,
            "average_buy_interval": self.average_buy_interval,
            "maximum_buy_burst": self.maximum_buy_burst,
            # F-GRD-011 to F-GRD-014
            "sell_event_count": self.sell_event_count,
            "sell_frequency": self.sell_frequency,
            "average_sell_interval": self.average_sell_interval,
            "buy_to_sell_completion_rate": self.buy_to_sell_completion_rate,
            # F-GRD-015 to F-GRD-019
            "grid_cycle_count": self.grid_cycle_count,
            "grid_cycle_frequency": self.grid_cycle_frequency,
            "average_cycle_duration": self.average_cycle_duration,
            "median_cycle_duration": self.median_cycle_duration,
            "cycle_completion_rate": self.cycle_completion_rate,
            # F-GRD-020 to F-GRD-025
            "average_cycle_net_pnl": self.average_cycle_net_pnl,
            "median_cycle_net_pnl": self.median_cycle_net_pnl,
            "positive_cycle_rate": self.positive_cycle_rate,
            "negative_cycle_rate": self.negative_cycle_rate,
            "average_positive_cycle": self.average_positive_cycle,
            "average_negative_cycle": self.average_negative_cycle,
            # F-GRD-026 to F-GRD-030
            "section_1_activation_rate": self.section_1_activation_rate,
            "section_2_activation_rate": self.section_2_activation_rate,
            "section_3_activation_rate": self.section_3_activation_rate,
            "section_activation_depth": self.section_activation_depth,
            "maximum_section_depth_frequency": self.maximum_section_depth_frequency,
            # F-GRD-031 to F-GRD-033
            "section_1_to_2_transition_rate": self.section_1_to_2_transition_rate,
            "section_2_to_3_transition_rate": self.section_2_to_3_transition_rate,
            "section_transition_speed": self.section_transition_speed,
            # F-GRD-034 to F-GRD-037
            "section_gap_reach_frequency": self.section_gap_reach_frequency,
            "average_drawdown_to_section_2": self.average_drawdown_to_section_2,
            "average_drawdown_to_section_3": self.average_drawdown_to_section_3,
            "section_gap_utilization": self.section_gap_utilization,
            # F-GRD-038 to F-GRD-043
            "capital_deployed": self.capital_deployed,
            "capital_deployment_ratio": self.capital_deployment_ratio,
            "peak_capital_deployment": self.peak_capital_deployment,
            "capital_reserve_remaining": self.capital_reserve_remaining,
            "minimum_capital_reserve": self.minimum_capital_reserve,
            "capital_exhaustion_flag": self.capital_exhaustion_flag,
            # F-GRD-044 to F-GRD-047
            "capital_deployment_velocity": self.capital_deployment_velocity,
            "time_to_50pct_deployment": self.time_to_50pct_deployment,
            "time_to_80pct_deployment": self.time_to_80pct_deployment,
            "time_to_maximum_deployment": self.time_to_maximum_deployment,
            # F-GRD-048 to F-GRD-051
            "average_exposure": self.average_exposure,
            "peak_exposure": self.peak_exposure,
            "exposure_ratio": self.exposure_ratio,
            "exposure_concentration": self.exposure_concentration,
            # F-GRD-052 to F-GRD-055
            "total_coin_accumulated": self.total_coin_accumulated,
            "average_acquisition_price": self.average_acquisition_price,
            "coin_accumulation_efficiency": self.coin_accumulation_efficiency,
            "additional_coin_from_drawdown": self.additional_coin_from_drawdown,
            # F-GRD-056 to F-GRD-058
            "average_cost_reduction": self.average_cost_reduction,
            "cost_basis_improvement_ratio": self.cost_basis_improvement_ratio,
            "cost_basis_recovery_distance": self.cost_basis_recovery_distance,
            # F-GRD-059 to F-GRD-062
            "max_market_drawdown": self.max_market_drawdown,
            "max_strategy_drawdown": self.max_strategy_drawdown,
            "avg_drawdown_at_section_activation": self.avg_drawdown_at_section_activation,
            "drawdown_to_max_exposure": self.drawdown_to_max_exposure,
            # F-GRD-063 to F-GRD-067
            "recovery_rate": self.recovery_rate,
            "average_recovery_time": self.average_recovery_time,
            "median_recovery_time": self.median_recovery_time,
            "recovery_after_section_2": self.recovery_after_section_2,
            "recovery_after_section_3": self.recovery_after_section_3,
            # F-GRD-068 to F-GRD-070
            "gross_grid_capture": self.gross_grid_capture,
            "net_grid_capture": self.net_grid_capture,
            "grid_capture_efficiency": self.grid_capture_efficiency,
            # F-GRD-071 to F-GRD-074
            "capital_efficiency": self.capital_efficiency,
            "trade_efficiency": self.trade_efficiency,
            "cycle_efficiency": self.cycle_efficiency,
            "deployment_efficiency": self.deployment_efficiency,
            # F-GRD-075 to F-GRD-079
            "historical_net_pnl": self.historical_net_pnl,
            "net_pnl_return": self.net_pnl_return,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_strategy_pnl": self.total_strategy_pnl,
            # F-GRD-080 to F-GRD-082
            "profit_factor": self.profit_factor,
            "net_pnl_volatility": self.net_pnl_volatility,
            "outcome_stability": self.outcome_stability,
            # F-GRD-083 to F-GRD-086
            "maximum_capital_stress": self.maximum_capital_stress,
            "maximum_section_stress": self.maximum_section_stress,
            "recovery_failure_rate": self.recovery_failure_rate,
            "capital_exhaustion_frequency": self.capital_exhaustion_frequency,
            # F-GRD-087 to F-GRD-090
            "grid_spacing_sensitivity": self.grid_spacing_sensitivity,
            "section_gap_sensitivity": self.section_gap_sensitivity,
            "allocation_sensitivity": self.allocation_sensitivity,
            "section_count_sensitivity": self.section_count_sensitivity,
        }


def extract_grid_behavior_features(
    result: SimulationResult,
    config: SimulationConfig,
) -> GridBehaviorFeatures:
    """
    Extract Grid Behavior features from a simulation result.

    Args:
        result: Completed simulation result
        config: Simulation configuration used

    Returns:
        GridBehaviorFeatures with all computable features populated
    """
    from okx_trading.research.simulator.grid_simulator import EventType

    window = result.candles_processed
    features = GridBehaviorFeatures(
        market_id=result.market_id,
        observation_timestamp=result.observation_timestamp,
        blueprint_id=result.blueprint_id,
        simulation_run_id=result.simulation_run_id,
        simulation_window_candles=window,
    )

    events = result.events
    buy_events = [e for e in events if e.event_type == EventType.BUY_EXECUTED]
    sell_events = [e for e in events if e.event_type == EventType.SELL_EXECUTED]
    buy_rejected = [e for e in events if e.event_type == EventType.BUY_REJECTED]
    section_activated = [e for e in events if e.event_type == EventType.SECTION_ACTIVATED]

    # --- Grid Opportunity (F-GRD-001 to F-GRD-003) ---
    # Grid events = all trade executions (buys + sells)
    grid_event_count = len(buy_events) + len(sell_events)
    features.grid_event_count = grid_event_count
    if window > 0:
        features.grid_opportunity_frequency = grid_event_count / window
        features.grid_opportunity_density = grid_event_count / window

    # --- Grid Trigger / Hit (F-GRD-004 to F-GRD-006) ---
    # Touch = reached level (executed + rejected attempts)
    touch_count = grid_event_count + len(buy_rejected)
    features.grid_level_touch_count = touch_count
    features.grid_execution_trigger_count = grid_event_count
    if touch_count > 0:
        features.grid_trigger_rate = grid_event_count / touch_count

    # --- BUY Behavior (F-GRD-007 to F-GRD-010) ---
    features.buy_event_count = len(buy_events)
    if window > 0:
        features.buy_frequency = len(buy_events) / window
    features.average_buy_interval = _average_interval(buy_events)
    features.maximum_buy_burst = _max_burst(buy_events, burst_window=3)

    # --- SELL Behavior (F-GRD-011 to F-GRD-014) ---
    features.sell_event_count = len(sell_events)
    if window > 0:
        features.sell_frequency = len(sell_events) / window
    features.average_sell_interval = _average_interval(sell_events)
    if len(buy_events) > 0:
        features.buy_to_sell_completion_rate = len(sell_events) / len(buy_events)

    # --- Grid Cycle (F-GRD-015 to F-GRD-019) ---
    features.grid_cycle_count = result.completed_cycles
    if window > 0:
        features.grid_cycle_frequency = result.completed_cycles / window

    # Match buy→sell pairs by (section_id, grid_level) for cycle durations
    cycle_durations = _compute_cycle_durations(buy_events, sell_events)
    if cycle_durations:
        features.average_cycle_duration = sum(cycle_durations) / len(cycle_durations)
        features.median_cycle_duration = float(median(cycle_durations))

    total_initiated = len(buy_events)
    if total_initiated > 0:
        features.cycle_completion_rate = result.completed_cycles / total_initiated

    # --- Cycle Quality (F-GRD-020 to F-GRD-025) ---
    cycle_pnls = [float(e.realized_pnl) for e in sell_events if e.realized_pnl is not None]
    if cycle_pnls:
        features.average_cycle_net_pnl = sum(cycle_pnls) / len(cycle_pnls)
        features.median_cycle_net_pnl = float(median(cycle_pnls))
        positive = [p for p in cycle_pnls if p > 0]
        negative = [p for p in cycle_pnls if p < 0]
        features.positive_cycle_rate = len(positive) / len(cycle_pnls)
        features.negative_cycle_rate = len(negative) / len(cycle_pnls)
        if positive:
            features.average_positive_cycle = sum(positive) / len(positive)
        if negative:
            features.average_negative_cycle = sum(negative) / len(negative)

    # --- Section Activation (F-GRD-026 to F-GRD-030) ---
    activated_ids = {e.section_id for e in section_activated if e.section_id is not None}
    features.section_1_activation_rate = 1.0 if 1 in activated_ids else 0.0
    features.section_2_activation_rate = 1.0 if 2 in activated_ids else 0.0
    features.section_3_activation_rate = 1.0 if 3 in activated_ids else 0.0
    features.section_activation_depth = result.max_section_depth
    if result.max_section_depth > 0:
        features.maximum_section_depth_frequency = result.sections_activated / max(
            result.max_section_depth, 1
        )

    # --- Section Transition (F-GRD-031 to F-GRD-033) ---
    if 1 in activated_ids:
        features.section_1_to_2_transition_rate = 1.0 if 2 in activated_ids else 0.0
    if 2 in activated_ids:
        features.section_2_to_3_transition_rate = 1.0 if 3 in activated_ids else 0.0
    # Transition speed: candles between section activations
    features.section_transition_speed = _section_transition_speed(section_activated)

    # --- Section Gap (F-GRD-034 to F-GRD-037) ---
    if result.sections_activated > 1:
        features.section_gap_reach_frequency = (result.sections_activated - 1) / max(window, 1)

    # --- Capital Deployment (F-GRD-038 to F-GRD-043) ---
    total_buy_cost = sum(
        float(e.capital_before - e.capital_after)
        for e in buy_events
        if e.capital_before is not None and e.capital_after is not None
    )
    features.capital_deployed = total_buy_cost
    starting = float(config.starting_capital)
    if starting > 0:
        features.capital_deployment_ratio = total_buy_cost / starting
    features.peak_capital_deployment = float(result.peak_capital_utilization) * starting
    features.capital_reserve_remaining = float(result.final_quote_balance)
    features.minimum_capital_reserve = float(result.final_quote_balance)  # approximation
    features.capital_exhaustion_flag = 1 if result.capital_exhausted else 0

    # --- Deployment Speed (F-GRD-044 to F-GRD-047) ---
    if window > 0 and total_buy_cost > 0:
        features.capital_deployment_velocity = total_buy_cost / window

    # --- Exposure (F-GRD-048 to F-GRD-051) ---
    features.peak_exposure = float(result.peak_capital_utilization) * starting
    if starting > 0:
        features.exposure_ratio = features.peak_exposure / starting

    # --- Coin Accumulation (F-GRD-052 to F-GRD-055) ---
    features.total_coin_accumulated = float(result.coin_accumulated)
    if result.average_acquisition_price is not None:
        features.average_acquisition_price = float(result.average_acquisition_price)
    if total_buy_cost > 0 and result.coin_accumulated > 0:
        features.coin_accumulation_efficiency = float(result.coin_accumulated) / total_buy_cost

    # --- Drawdown (F-GRD-059 to F-GRD-062) ---
    features.max_strategy_drawdown = float(result.max_drawdown)
    features.max_market_drawdown = float(result.max_drawdown)  # context from simulation

    # --- Grid Capture (F-GRD-068 to F-GRD-070) ---
    gross_capture = sum(
        float(e.execution_price * e.executed_quantity)
        for e in sell_events
        if e.execution_price is not None and e.executed_quantity is not None
    )
    features.gross_grid_capture = gross_capture
    features.net_grid_capture = float(result.realized_pnl)
    if gross_capture > 0:
        features.grid_capture_efficiency = float(result.realized_pnl) / gross_capture

    # --- Strategy Efficiency (F-GRD-071 to F-GRD-074) ---
    if total_buy_cost > 0:
        features.capital_efficiency = float(result.total_pnl) / total_buy_cost
    total_executions = len(buy_events) + len(sell_events)
    if total_executions > 0:
        features.trade_efficiency = float(result.total_pnl) / total_executions
    if result.completed_cycles > 0:
        features.cycle_efficiency = float(result.realized_pnl) / result.completed_cycles

    # --- Strategy Outcome (F-GRD-075 to F-GRD-079) ---
    features.historical_net_pnl = float(result.total_pnl)
    features.net_pnl_return = result.net_pnl_return_pct
    features.realized_pnl = float(result.realized_pnl)
    features.unrealized_pnl = float(result.unrealized_pnl)
    features.total_strategy_pnl = float(result.total_pnl)

    # --- Profitability Quality (F-GRD-080 to F-GRD-082) ---
    if cycle_pnls:
        gross_positive = sum(p for p in cycle_pnls if p > 0)
        gross_negative = abs(sum(p for p in cycle_pnls if p < 0))
        if gross_negative > 0:
            features.profit_factor = gross_positive / gross_negative
        elif gross_positive > 0:
            features.profit_factor = float("inf")
        # Net PnL volatility (std dev of cycle PnLs)
        if len(cycle_pnls) > 1:
            mean_pnl = sum(cycle_pnls) / len(cycle_pnls)
            variance = sum((p - mean_pnl) ** 2 for p in cycle_pnls) / (len(cycle_pnls) - 1)
            features.net_pnl_volatility = variance**0.5

    # --- Stress Behavior (F-GRD-083 to F-GRD-086) ---
    features.maximum_capital_stress = float(result.peak_capital_utilization)
    features.maximum_section_stress = result.max_section_depth
    features.capital_exhaustion_frequency = 1.0 if result.capital_exhausted else 0.0

    # --- Sensitivity (F-GRD-087 to F-GRD-090) ---
    # Requires multiple simulation runs — left as None
    features.availability = {
        "sensitivity": GridBehaviorAvailability.REQUIRES_MULTI_RUN.value,
        "single_run": GridBehaviorAvailability.AVAILABLE.value,
    }

    return features


def _average_interval(events: Sequence[SimulationEvent]) -> float | None:
    """Compute average time interval between events in seconds."""
    if len(events) < 2:
        return None
    timestamps = [e.timestamp for e in events]
    intervals = [(t2 - t1).total_seconds() for t1, t2 in itertools.pairwise(timestamps)]
    if not intervals:
        return None
    return float(sum(intervals) / len(intervals))


def _max_burst(events: Sequence[SimulationEvent], burst_window: int = 3) -> int | None:
    """
    Maximum number of events within a sliding window of burst_window candles.

    Uses event index proximity as a proxy for time proximity.
    """
    if not events:
        return 0
    # Group events by timestamp and count max within burst_window consecutive
    timestamps = [e.timestamp for e in events]
    if len(timestamps) <= burst_window:
        return len(timestamps)

    max_count = 0
    for i in range(len(timestamps)):
        count = 0
        for j in range(i, len(timestamps)):
            if (timestamps[j] - timestamps[i]).total_seconds() <= burst_window * 3600:
                count += 1
            else:
                break
        max_count = max(max_count, count)
    return max_count


def _compute_cycle_durations(
    buy_events: Sequence[SimulationEvent], sell_events: Sequence[SimulationEvent]
) -> list[float]:
    """
    Match buy→sell pairs by (section_id, grid_level) and compute durations.

    Returns list of cycle durations in seconds.
    """
    durations: list[float] = []
    # Index buys by (section, level)
    buy_map: dict[tuple[int, int], list[SimulationEvent]] = {}
    for e in buy_events:
        key = (e.section_id or 0, e.grid_level or 0)
        buy_map.setdefault(key, []).append(e)

    for sell in sell_events:
        key = (sell.section_id or 0, sell.grid_level or 0)
        buys = buy_map.get(key, [])
        if buys:
            buy = buys.pop(0)
            duration = (sell.timestamp - buy.timestamp).total_seconds()
            if duration >= 0:
                durations.append(duration)

    return durations


def _section_transition_speed(section_events: Sequence[SimulationEvent]) -> float | None:
    """
    Compute average time between section activations in seconds.
    """
    if len(section_events) < 2:
        return None
    timestamps = [e.timestamp for e in section_events]
    intervals = [(t2 - t1).total_seconds() for t1, t2 in itertools.pairwise(timestamps)]
    if not intervals:
        return None
    return float(sum(intervals) / len(intervals))
