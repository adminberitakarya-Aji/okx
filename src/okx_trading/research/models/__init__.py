"""
ML models for AI Research pipeline.

Modules:
- trainer: Model training with walk-forward validation
- ranking: Market ranking and recommendation engine
- registry: Model versioning and lifecycle management
"""

from okx_trading.research.models.ranking import (
    RANKING_VERSION,
    MarketRanker,
    MarketRecommendation,
    ModelPredictions,
    RankingEvaluator,
    RecommendationAction,
    RiskLevel,
    SuitabilityEngine,
    SuitabilityScore,
    SuitabilityWeights,
)
from okx_trading.research.models.registry import (
    REGISTRY_VERSION,
    ModelRegistry,
    PromotionCriteria,
    PromotionThresholds,
    RegistryEntry,
)
from okx_trading.research.models.trainer import (
    MODEL_TRAINER_VERSION,
    ModelConfig,
    ModelFamily,
    ModelStatus,
    ModelTrainer,
    ModelType,
    TrainedModel,
    TrainingMetrics,
    WalkForwardFold,
    WalkForwardResult,
)

__all__ = [
    "MODEL_TRAINER_VERSION",
    "RANKING_VERSION",
    "REGISTRY_VERSION",
    "MarketRanker",
    "MarketRecommendation",
    "ModelConfig",
    "ModelFamily",
    "ModelPredictions",
    "ModelRegistry",
    "ModelStatus",
    "ModelTrainer",
    "ModelType",
    "PromotionCriteria",
    "PromotionThresholds",
    "RankingEvaluator",
    "RecommendationAction",
    "RegistryEntry",
    "RiskLevel",
    "SuitabilityEngine",
    "SuitabilityScore",
    "SuitabilityWeights",
    "TrainedModel",
    "TrainingMetrics",
    "WalkForwardFold",
    "WalkForwardResult",
]
