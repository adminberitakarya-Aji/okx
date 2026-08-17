"""
Research grid simulator package.

Provides the deterministic historical grid simulator used for:
- Grid Behavior feature extraction
- ML label generation
- Blueprint comparison research
"""

from okx_trading.research.simulator.grid_simulator import (
    EventType,
    GridLevelState,
    GridSimulator,
    ScenarioMode,
    SectionState,
    SimulationConfig,
    SimulationEvent,
    SimulationResult,
    TerminalCondition,
)

__all__ = [
    "EventType",
    "GridLevelState",
    "GridSimulator",
    "ScenarioMode",
    "SectionState",
    "SimulationConfig",
    "SimulationEvent",
    "SimulationResult",
    "TerminalCondition",
]
