"""
Market Ranking and Recommendation Engine.

Implements market ranking per AI_RESEARCH_ML_MODEL_SPEC.md §38-45.

The Suitability Engine combines multiple model outputs:
- P(Positive Net P&L) — primary
- Expected Net P&L
- Expected Drawdown
- Capital Utilization
- Recovery Probability
- Capital Exhaustion Risk

Final output:
- Grid Suitability Score (0-100)
- Market Ranking
- Recommendation with explainability
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger()

RANKING_VERSION = "ranking-v001"


class RecommendationAction(StrEnum):
    """Recommendation action levels."""

    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    AVOID = "AVOID"


class RiskLevel(StrEnum):
    """Risk level classification."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class ModelPredictions:
    """Raw predictions from all models for one market+blueprint."""

    market_id: str
    blueprint_id: str
    observation_timestamp: datetime

    # Primary classifier output
    positive_pnl_probability: float | None = None

    # Regressor outputs
    expected_net_pnl_return: float | None = None
    expected_max_drawdown: float | None = None
    expected_capital_utilization: float | None = None

    # Risk classifier outputs
    recovery_probability: float | None = None
    capital_exhaustion_probability: float | None = None

    # Section depth distribution
    section_depth_probabilities: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "blueprint_id": self.blueprint_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "positive_pnl_probability": self.positive_pnl_probability,
            "expected_net_pnl_return": self.expected_net_pnl_return,
            "expected_max_drawdown": self.expected_max_drawdown,
            "expected_capital_utilization": self.expected_capital_utilization,
            "recovery_probability": self.recovery_probability,
            "capital_exhaustion_probability": self.capital_exhaustion_probability,
            "section_depth_probabilities": self.section_depth_probabilities,
        }


@dataclass
class SuitabilityWeights:
    """Weights for suitability score calculation."""

    positive_pnl: float = 0.35
    expected_return: float = 0.20
    drawdown_penalty: float = 0.15
    capital_efficiency: float = 0.10
    recovery: float = 0.10
    exhaustion_penalty: float = 0.10

    def validate(self) -> bool:
        total = (
            self.positive_pnl
            + self.expected_return
            + self.drawdown_penalty
            + self.capital_efficiency
            + self.recovery
            + self.exhaustion_penalty
        )
        return abs(total - 1.0) < 0.01


@dataclass
class SuitabilityScore:
    """Grid suitability score with component breakdown."""

    market_id: str
    blueprint_id: str
    observation_timestamp: datetime

    # Final score (0-100)
    total_score: float

    # Component scores (0-1 each, weighted)
    positive_pnl_score: float | None = None
    expected_return_score: float | None = None
    drawdown_score: float | None = None
    capital_efficiency_score: float | None = None
    recovery_score: float | None = None
    exhaustion_score: float | None = None

    # Risk assessment
    risk_level: RiskLevel = RiskLevel.MEDIUM

    # Metadata
    weights_used: SuitabilityWeights = field(default_factory=SuitabilityWeights)
    ranking_version: str = RANKING_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "blueprint_id": self.blueprint_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "total_score": self.total_score,
            "positive_pnl_score": self.positive_pnl_score,
            "expected_return_score": self.expected_return_score,
            "drawdown_score": self.drawdown_score,
            "capital_efficiency_score": self.capital_efficiency_score,
            "recovery_score": self.recovery_score,
            "exhaustion_score": self.exhaustion_score,
            "risk_level": self.risk_level.value,
            "ranking_version": self.ranking_version,
        }


@dataclass
class MarketRecommendation:
    """Final market recommendation with explainability."""

    market_id: str
    rank: int
    suitability_score: SuitabilityScore
    action: RecommendationAction
    confidence: float

    # Explainability (spec §38)
    primary_reasons: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)

    # Best blueprint for this market
    recommended_blueprint_id: str | None = None

    # Timestamp
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "rank": self.rank,
            "action": self.action.value,
            "confidence": self.confidence,
            "total_score": self.suitability_score.total_score,
            "risk_level": self.suitability_score.risk_level.value,
            "primary_reasons": self.primary_reasons,
            "risk_warnings": self.risk_warnings,
            "recommended_blueprint_id": self.recommended_blueprint_id,
            "generated_at": self.generated_at.isoformat(),
        }


class SuitabilityEngine:
    """
    Combines model predictions into grid suitability score.

    Usage:
        engine = SuitabilityEngine()
        score = engine.calculate_suitability(predictions)
    """

    def __init__(self, weights: SuitabilityWeights | None = None) -> None:
        self.weights = weights or SuitabilityWeights()
        if not self.weights.validate():
            raise ValueError("Suitability weights must sum to 1.0")

    def calculate_suitability(self, predictions: ModelPredictions) -> SuitabilityScore:
        """
        Calculate grid suitability score from model predictions.

        Score range: 0-100
        """
        w = self.weights

        # Component 1: Positive P&L probability (already 0-1)
        positive_pnl_score = predictions.positive_pnl_probability

        # Component 2: Expected return (normalize to 0-1)
        expected_return_score = self._normalize_return(predictions.expected_net_pnl_return)

        # Component 3: Drawdown (lower is better, invert)
        drawdown_score = self._normalize_drawdown(predictions.expected_max_drawdown)

        # Component 4: Capital efficiency (moderate utilization is best)
        capital_efficiency_score = self._normalize_capital_utilization(
            predictions.expected_capital_utilization
        )

        # Component 5: Recovery probability
        recovery_score = predictions.recovery_probability

        # Component 6: Exhaustion risk (lower is better, invert)
        exhaustion_score = self._invert_probability(predictions.capital_exhaustion_probability)

        # Calculate weighted total
        components = [
            (positive_pnl_score, w.positive_pnl),
            (expected_return_score, w.expected_return),
            (drawdown_score, w.drawdown_penalty),
            (capital_efficiency_score, w.capital_efficiency),
            (recovery_score, w.recovery),
            (exhaustion_score, w.exhaustion_penalty),
        ]

        total_weight = sum(wt for val, wt in components if val is not None)
        if total_weight == 0:
            total_score = 0.0
        else:
            weighted_sum = sum((val or 0.0) * wt for val, wt in components if val is not None)
            total_score = (weighted_sum / total_weight) * 100

        # Determine risk level
        risk_level = self._assess_risk_level(predictions)

        return SuitabilityScore(
            market_id=predictions.market_id,
            blueprint_id=predictions.blueprint_id,
            observation_timestamp=predictions.observation_timestamp,
            total_score=round(total_score, 2),
            positive_pnl_score=positive_pnl_score,
            expected_return_score=expected_return_score,
            drawdown_score=drawdown_score,
            capital_efficiency_score=capital_efficiency_score,
            recovery_score=recovery_score,
            exhaustion_score=exhaustion_score,
            risk_level=risk_level,
            weights_used=self.weights,
        )

    def _normalize_return(self, ret: float | None) -> float | None:
        """Normalize expected return to 0-1 scale."""
        if ret is None:
            return None
        # Assume typical range -10% to +10%
        # Map -0.10 -> 0, 0 -> 0.5, +0.10 -> 1
        normalized = 0.5 + ret / 0.20
        return max(0.0, min(1.0, normalized))

    def _normalize_drawdown(self, dd: float | None) -> float | None:
        """Normalize drawdown (lower is better)."""
        if dd is None:
            return None
        # 0% drawdown -> 1.0, 50%+ drawdown -> 0.0
        return max(0.0, 1.0 - dd / 0.50)

    def _normalize_capital_utilization(self, util: float | None) -> float | None:
        """
        Normalize capital utilization.

        Moderate utilization (40-70%) is optimal.
        Too low = inefficient, too high = risky.
        """
        if util is None:
            return None
        if util < 0.40:
            return 0.5 + util  # 0 -> 0.5, 0.4 -> 0.9
        if util <= 0.70:
            return 1.0  # Optimal range
        # Above 0.70, decreasing
        return max(0.0, 1.0 - (util - 0.70) / 0.30)

    def _invert_probability(self, prob: float | None) -> float | None:
        """Invert probability (risk -> safety)."""
        if prob is None:
            return None
        return 1.0 - prob

    def _assess_risk_level(self, predictions: ModelPredictions) -> RiskLevel:
        """Assess overall risk level."""
        risk_score = 0.0

        if predictions.expected_max_drawdown is not None:
            if predictions.expected_max_drawdown > 0.40:
                risk_score += 2
            elif predictions.expected_max_drawdown > 0.25:
                risk_score += 1

        if predictions.capital_exhaustion_probability is not None:
            if predictions.capital_exhaustion_probability > 0.30:
                risk_score += 2
            elif predictions.capital_exhaustion_probability > 0.15:
                risk_score += 1

        if (
            predictions.expected_capital_utilization is not None
            and predictions.expected_capital_utilization > 0.85
        ):
            risk_score += 1

        if risk_score >= 4:
            return RiskLevel.EXTREME
        if risk_score >= 3:
            return RiskLevel.HIGH
        if risk_score >= 1:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW


class MarketRanker:
    """
    Ranks markets by grid suitability.

    Usage:
        ranker = MarketRanker()
        recommendations = ranker.rank_markets(market_predictions)
    """

    def __init__(
        self,
        suitability_engine: SuitabilityEngine | None = None,
        min_score_threshold: float = 40.0,
        max_recommendations: int = 10,
    ) -> None:
        self.engine = suitability_engine or SuitabilityEngine()
        self.min_score_threshold = min_score_threshold
        self.max_recommendations = max_recommendations

    def rank_markets(
        self,
        market_predictions: dict[str, list[ModelPredictions]],
    ) -> list[MarketRecommendation]:
        """
        Rank markets based on model predictions.

        Args:
            market_predictions: Dict of market_id -> list of predictions
                               (one per candidate blueprint)

        Returns:
            Sorted list of MarketRecommendation
        """
        market_scores: list[tuple[str, SuitabilityScore, str]] = []

        for market_id, predictions_list in market_predictions.items():
            # Evaluate all blueprints for this market
            best_score: SuitabilityScore | None = None
            best_blueprint_id: str | None = None

            for predictions in predictions_list:
                score = self.engine.calculate_suitability(predictions)
                if best_score is None or score.total_score > best_score.total_score:
                    best_score = score
                    best_blueprint_id = predictions.blueprint_id

            if best_score is not None:
                market_scores.append((market_id, best_score, best_blueprint_id or ""))

        # Sort by score descending
        market_scores.sort(key=lambda x: x[1].total_score, reverse=True)

        # Generate recommendations
        recommendations: list[MarketRecommendation] = []
        for rank, (market_id, score, blueprint_id) in enumerate(
            market_scores[: self.max_recommendations], start=1
        ):
            if score.total_score < self.min_score_threshold:
                continue

            action = self._determine_action(score)
            confidence = self._calculate_confidence(score)
            reasons = self._generate_reasons(score)
            warnings = self._generate_warnings(score)

            recommendation = MarketRecommendation(
                market_id=market_id,
                rank=rank,
                suitability_score=score,
                action=action,
                confidence=confidence,
                primary_reasons=reasons,
                risk_warnings=warnings,
                recommended_blueprint_id=blueprint_id,
            )
            recommendations.append(recommendation)

        logger.info(
            "markets_ranked",
            total_markets=len(market_predictions),
            recommended=len(recommendations),
            top_market=recommendations[0].market_id if recommendations else None,
        )

        return recommendations

    def _determine_action(self, score: SuitabilityScore) -> RecommendationAction:
        """Determine recommendation action from score."""
        if score.total_score >= 75 and score.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):
            return RecommendationAction.STRONG_BUY
        if score.total_score >= 60 and score.risk_level != RiskLevel.EXTREME:
            return RecommendationAction.BUY
        if score.total_score >= 40:
            return RecommendationAction.HOLD
        return RecommendationAction.AVOID

    def _calculate_confidence(self, score: SuitabilityScore) -> float:
        """Calculate recommendation confidence (0-1)."""
        # Based on score strength and risk level
        base_confidence = score.total_score / 100

        risk_modifier = {
            RiskLevel.LOW: 1.0,
            RiskLevel.MEDIUM: 0.9,
            RiskLevel.HIGH: 0.7,
            RiskLevel.EXTREME: 0.5,
        }

        return round(base_confidence * risk_modifier[score.risk_level], 2)

    def _generate_reasons(self, score: SuitabilityScore) -> list[str]:
        """Generate human-readable reasons for recommendation."""
        reasons: list[str] = []

        if score.positive_pnl_score is not None and score.positive_pnl_score > 0.70:
            reasons.append("High probability of positive net P&L")

        if score.expected_return_score is not None and score.expected_return_score > 0.65:
            reasons.append("Favorable expected return")

        if score.drawdown_score is not None and score.drawdown_score > 0.70:
            reasons.append("Controlled expected drawdown")

        if score.recovery_score is not None and score.recovery_score > 0.60:
            reasons.append("Good recovery characteristics")

        if score.capital_efficiency_score is not None and score.capital_efficiency_score > 0.80:
            reasons.append("Efficient capital utilization")

        if not reasons:
            reasons.append("Moderate overall suitability")

        return reasons[:3]  # Top 3 reasons

    def _generate_warnings(self, score: SuitabilityScore) -> list[str]:
        """Generate risk warnings."""
        warnings: list[str] = []

        if score.risk_level == RiskLevel.EXTREME:
            warnings.append("Extreme risk level detected")
        elif score.risk_level == RiskLevel.HIGH:
            warnings.append("High risk level - monitor closely")

        if score.drawdown_score is not None and score.drawdown_score < 0.40:
            warnings.append("High expected drawdown")

        if score.exhaustion_score is not None and score.exhaustion_score < 0.50:
            warnings.append("Elevated capital exhaustion risk")

        return warnings


class RankingEvaluator:
    """
    Evaluates ranking quality (spec §28).

    Metrics:
    - NDCG
    - Spearman Rank Correlation
    - Top-K Precision
    - Top-K Outcome Lift
    """

    def evaluate_ranking(
        self,
        predicted_ranks: list[str],
        actual_outcomes: dict[str, float],
        k: int = 3,
    ) -> dict[str, float]:
        """
        Evaluate ranking quality.

        Args:
            predicted_ranks: Market IDs in predicted order
            actual_outcomes: Actual outcomes per market
            k: Top-K for precision/lift

        Returns:
            Dict of evaluation metrics
        """
        from scipy.stats import spearmanr

        metrics: dict[str, float] = {}

        # Get common markets
        common_markets = [m for m in predicted_ranks if m in actual_outcomes]
        if len(common_markets) < 2:
            return metrics

        # Spearman correlation
        predicted_order = [predicted_ranks.index(m) for m in common_markets]
        actual_values = [actual_outcomes[m] for m in common_markets]
        corr, _ = spearmanr(predicted_order, [-v for v in actual_values])
        metrics["spearman_correlation"] = float(corr) if not np.isnan(corr) else 0.0

        # Top-K precision
        actual_sorted = sorted(common_markets, key=lambda m: actual_outcomes[m], reverse=True)
        top_k_predicted = set(predicted_ranks[:k])
        top_k_actual = set(actual_sorted[:k])
        metrics["top_k_precision"] = len(top_k_predicted & top_k_actual) / k

        # Top-K outcome lift
        top_k_outcomes = [actual_outcomes[m] for m in predicted_ranks[:k]]
        all_outcomes = [actual_outcomes[m] for m in common_markets]
        if all_outcomes:
            mean_all = np.mean(all_outcomes)
            mean_top_k = np.mean(top_k_outcomes) if top_k_outcomes else 0
            metrics["top_k_lift"] = float(mean_top_k - mean_all)

        # NDCG
        metrics["ndcg"] = self._calculate_ndcg(predicted_ranks, actual_outcomes, k)

        return metrics

    def _calculate_ndcg(
        self, predicted_ranks: list[str], actual_outcomes: dict[str, float], k: int
    ) -> float:
        """Calculate Normalized Discounted Cumulative Gain."""
        dcg = 0.0
        for i, market in enumerate(predicted_ranks[:k]):
            if market in actual_outcomes:
                relevance = max(0, actual_outcomes[market])
                dcg += relevance / np.log2(i + 2)

        # Ideal DCG
        ideal_sorted = sorted(
            [m for m in predicted_ranks if m in actual_outcomes],
            key=lambda m: actual_outcomes[m],
            reverse=True,
        )
        idcg = 0.0
        for i, market in enumerate(ideal_sorted[:k]):
            relevance = max(0, actual_outcomes[market])
            idcg += relevance / np.log2(i + 2)

        return dcg / idcg if idcg > 0 else 0.0
