"""
Research feature computation modules.

Feature layers:
- market_state: F-MKT features (Market State)
- execution_economics: F-EXE features (Execution Economics)
- grid_behavior: F-GRD features (Grid Behavior)
- derived_ml: F-ML features (Derived ML)
"""

from trading_grid.research.features.derived_ml import (
    DERIVED_ML_VERSION,
    DerivedMLExtractor,
    DerivedMLFeatures,
    FeatureAvailability,
    FeatureValue,
)
from trading_grid.research.features.execution_economics import (
    ExecutionEconomicsExtractor,
    ExecutionEconomicsFeatures,
    GridEconomicViability,
    LiquidityStressLevel,
)
from trading_grid.research.features.grid_behavior import (
    GridBehaviorAvailability,
    GridBehaviorFeatures,
    extract_grid_behavior_features,
)
from trading_grid.research.features.market_state import (
    CandleStructure,
    MarketStateFeatureExtractor,
    MarketStateFeatures,
)

__all__ = [
    "DERIVED_ML_VERSION",
    "CandleStructure",
    "DerivedMLExtractor",
    "DerivedMLFeatures",
    "ExecutionEconomicsExtractor",
    "ExecutionEconomicsFeatures",
    "FeatureAvailability",
    "FeatureValue",
    "GridBehaviorAvailability",
    "GridBehaviorFeatures",
    "GridEconomicViability",
    "LiquidityStressLevel",
    "MarketStateFeatureExtractor",
    "MarketStateFeatures",
    "extract_grid_behavior_features",
]
