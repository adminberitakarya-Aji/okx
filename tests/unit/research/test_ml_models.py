"""Tests for ML model trainer, ranking, and registry."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from trading_grid.research.models.ranking import (
    MarketRanker,
    ModelPredictions,
    RankingEvaluator,
    RecommendationAction,
    RiskLevel,
    SuitabilityEngine,
    SuitabilityWeights,
)
from trading_grid.research.models.registry import (
    ModelRegistry,
)
from trading_grid.research.models.trainer import (
    ModelConfig,
    ModelFamily,
    ModelStatus,
    ModelTrainer,
    ModelType,
)


def make_classification_data(
    n_samples: int = 200, n_features: int = 5, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic classification data."""
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n_samples, n_features))
    # Label based on first feature with noise
    logits = X[:, 0] * 2 + rng.normal(scale=0.5, size=n_samples)
    y = (logits > 0).astype(int)
    return X, y


def make_config(model_type: ModelType = ModelType.PRIMARY_CLASSIFIER) -> ModelConfig:
    return ModelConfig(
        model_type=model_type,
        model_family=ModelFamily.GRADIENT_BOOSTING,
        feature_version="fml-v001",
        label_version="label-v001",
        dataset_version="dataset-v001",
        simulator_version="sim-v001",
        execution_model_version="exec-v001",
        horizon="30D",
        hyperparameters={"n_estimators": 20},
        calibration_enabled=False,
    )


class TestModelTrainer:
    """Tests for ModelTrainer."""

    def test_train_classifier(self, tmp_path):
        """Classifier trains and produces metrics."""
        trainer = ModelTrainer(model_dir=tmp_path)
        X, y = make_classification_data()
        config = make_config()

        model = trainer.train(X, y, config=config)

        assert model.status == ModelStatus.TRAINED
        assert model.train_metrics is not None
        assert model.train_metrics.accuracy > 0.5
        assert model.train_metrics.train_samples == len(X)

    def test_train_with_validation(self, tmp_path):
        """Validation metrics computed when provided."""
        trainer = ModelTrainer(model_dir=tmp_path)
        X, y = make_classification_data(n_samples=300)
        X_train, X_val = X[:200], X[200:]
        y_train, y_val = y[:200], y[200:]

        model = trainer.train(X_train, y_train, X_val, y_val, config=make_config())

        assert model.validation_metrics is not None
        assert model.validation_metrics.validation_samples == 100

    def test_train_regressor(self, tmp_path):
        """Regressor trains and produces regression metrics."""
        trainer = ModelTrainer(model_dir=tmp_path)
        rng = np.random.default_rng(42)
        X = rng.normal(size=(200, 5))
        y = X[:, 0] * 0.5 + rng.normal(scale=0.1, size=200)

        config = make_config(model_type=ModelType.NET_PNL_REGRESSOR)
        model = trainer.train(X, y, config=config)

        assert model.status == ModelStatus.TRAINED
        assert model.train_metrics is not None
        assert model.train_metrics.mae is not None
        assert model.train_metrics.r_squared is not None

    def test_feature_importance_extracted(self, tmp_path):
        """Feature importance extracted for tree models."""
        trainer = ModelTrainer(model_dir=tmp_path)
        X, y = make_classification_data()
        feature_names = [f"f{i}" for i in range(X.shape[1])]

        model = trainer.train(X, y, config=make_config(), feature_names=feature_names)

        assert len(model.feature_importance) == X.shape[1]
        assert "f0" in model.feature_importance

    def test_save_and_load_model(self, tmp_path):
        """Model round-trips through save/load."""
        trainer = ModelTrainer(model_dir=tmp_path)
        X, y = make_classification_data()

        model = trainer.train(X, y, config=make_config())
        trainer.save_model(model)

        loaded = trainer.load_model(model.model_id)
        assert loaded.model_id == model.model_id
        assert loaded.config.model_type == ModelType.PRIMARY_CLASSIFIER

        # Predictions match
        preds_orig = model.predict(X[:5])
        preds_loaded = loaded.predict(X[:5])
        np.testing.assert_array_equal(preds_orig, preds_loaded)

    def test_walk_forward_validate(self, tmp_path):
        """Walk-forward validation produces folds."""
        trainer = ModelTrainer(model_dir=tmp_path)
        n = 400
        X, y = make_classification_data(n_samples=n)
        base = datetime(2024, 1, 1, tzinfo=UTC)
        timestamps = np.array(
            [base + timedelta(hours=6 * i) for i in range(n)], dtype="datetime64[ns]"
        )

        result = trainer.walk_forward_validate(
            X,
            y,
            timestamps,
            config=make_config(),
            n_folds=3,
            train_window_days=30,
            test_window_days=15,
        )

        assert len(result.folds) >= 1
        assert result.folds[0].train_samples > 0
        assert result.folds[0].test_samples > 0

    def test_deterministic_training(self, tmp_path):
        """Same seed produces same predictions."""
        X, y = make_classification_data()
        config = make_config()

        trainer1 = ModelTrainer(model_dir=tmp_path / "m1")
        trainer2 = ModelTrainer(model_dir=tmp_path / "m2")

        model1 = trainer1.train(X, y, config=config)
        model2 = trainer2.train(X, y, config=config)

        np.testing.assert_array_equal(model1.predict(X), model2.predict(X))


class TestSuitabilityEngine:
    """Tests for SuitabilityEngine."""

    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError):
            SuitabilityEngine(SuitabilityWeights(positive_pnl=0.9))

    def test_high_quality_predictions_score_high(self):
        engine = SuitabilityEngine()
        predictions = ModelPredictions(
            market_id="BTC-USDT",
            blueprint_id="BP-001",
            observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            positive_pnl_probability=0.85,
            expected_net_pnl_return=0.05,
            expected_max_drawdown=0.10,
            expected_capital_utilization=0.55,
            recovery_probability=0.80,
            capital_exhaustion_probability=0.05,
        )

        score = engine.calculate_suitability(predictions)

        assert score.total_score > 70
        assert score.risk_level == RiskLevel.LOW

    def test_low_quality_predictions_score_low(self):
        engine = SuitabilityEngine()
        predictions = ModelPredictions(
            market_id="BAD-USDT",
            blueprint_id="BP-001",
            observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            positive_pnl_probability=0.20,
            expected_net_pnl_return=-0.05,
            expected_max_drawdown=0.45,
            expected_capital_utilization=0.95,
            recovery_probability=0.20,
            capital_exhaustion_probability=0.40,
        )

        score = engine.calculate_suitability(predictions)

        assert score.total_score < 40
        assert score.risk_level in (RiskLevel.HIGH, RiskLevel.EXTREME)

    def test_missing_predictions_handled(self):
        engine = SuitabilityEngine()
        predictions = ModelPredictions(
            market_id="BTC-USDT",
            blueprint_id="BP-001",
            observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            positive_pnl_probability=0.70,
        )

        score = engine.calculate_suitability(predictions)
        assert 0 <= score.total_score <= 100


class TestMarketRanker:
    """Tests for MarketRanker."""

    def test_rank_markets_orders_by_score(self):
        ranker = MarketRanker(min_score_threshold=0.0)
        ts = datetime(2024, 1, 1, tzinfo=UTC)

        predictions = {
            "BTC-USDT": [
                ModelPredictions(
                    market_id="BTC-USDT",
                    blueprint_id="BP-1",
                    observation_timestamp=ts,
                    positive_pnl_probability=0.85,
                    expected_net_pnl_return=0.05,
                    expected_max_drawdown=0.10,
                    expected_capital_utilization=0.55,
                    recovery_probability=0.80,
                    capital_exhaustion_probability=0.05,
                )
            ],
            "DOGE-USDT": [
                ModelPredictions(
                    market_id="DOGE-USDT",
                    blueprint_id="BP-1",
                    observation_timestamp=ts,
                    positive_pnl_probability=0.30,
                    expected_net_pnl_return=-0.04,
                    expected_max_drawdown=0.40,
                    expected_capital_utilization=0.90,
                    recovery_probability=0.25,
                    capital_exhaustion_probability=0.35,
                )
            ],
        }

        recommendations = ranker.rank_markets(predictions)

        assert len(recommendations) == 2
        assert recommendations[0].market_id == "BTC-USDT"
        assert recommendations[0].rank == 1
        assert recommendations[1].market_id == "DOGE-USDT"

    def test_best_blueprint_selected(self):
        ranker = MarketRanker(min_score_threshold=0.0)
        ts = datetime(2024, 1, 1, tzinfo=UTC)

        predictions = {
            "BTC-USDT": [
                ModelPredictions(
                    market_id="BTC-USDT",
                    blueprint_id="BP-LOW",
                    observation_timestamp=ts,
                    positive_pnl_probability=0.40,
                ),
                ModelPredictions(
                    market_id="BTC-USDT",
                    blueprint_id="BP-HIGH",
                    observation_timestamp=ts,
                    positive_pnl_probability=0.90,
                    expected_net_pnl_return=0.06,
                    expected_max_drawdown=0.08,
                    expected_capital_utilization=0.50,
                    recovery_probability=0.85,
                    capital_exhaustion_probability=0.03,
                ),
            ],
        }

        recommendations = ranker.rank_markets(predictions)
        assert recommendations[0].recommended_blueprint_id == "BP-HIGH"

    def test_action_levels(self):
        ranker = MarketRanker(min_score_threshold=0.0)
        ts = datetime(2024, 1, 1, tzinfo=UTC)

        predictions = {
            "STRONG-USDT": [
                ModelPredictions(
                    market_id="STRONG-USDT",
                    blueprint_id="BP-1",
                    observation_timestamp=ts,
                    positive_pnl_probability=0.92,
                    expected_net_pnl_return=0.07,
                    expected_max_drawdown=0.05,
                    expected_capital_utilization=0.55,
                    recovery_probability=0.90,
                    capital_exhaustion_probability=0.02,
                )
            ],
        }

        recommendations = ranker.rank_markets(predictions)
        assert recommendations[0].action == RecommendationAction.STRONG_BUY
        assert len(recommendations[0].primary_reasons) > 0


class TestRankingEvaluator:
    """Tests for RankingEvaluator."""

    def test_evaluate_perfect_ranking(self):
        evaluator = RankingEvaluator()
        predicted = ["A", "B", "C", "D"]
        actual = {"A": 1.0, "B": 0.8, "C": 0.5, "D": 0.2}

        metrics = evaluator.evaluate_ranking(predicted, actual, k=3)

        assert metrics["top_k_precision"] == 1.0
        assert metrics["ndcg"] == pytest.approx(1.0)
        assert metrics["top_k_lift"] > 0


class TestModelRegistry:
    """Tests for ModelRegistry."""

    def test_register_and_get(self, tmp_path):
        registry = ModelRegistry(registry_dir=tmp_path)
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data()

        model = trainer.train(X, y, config=make_config())
        entry = registry.register(model, tags=["test"])

        assert registry.get(model.model_id) is not None
        assert entry.tags == ["test"]

    def test_list_models_filter(self, tmp_path):
        registry = ModelRegistry(registry_dir=tmp_path)
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data()

        model = trainer.train(X, y, config=make_config())
        registry.register(model)

        classifiers = registry.list_models(model_type=ModelType.PRIMARY_CLASSIFIER)
        regressors = registry.list_models(model_type=ModelType.NET_PNL_REGRESSOR)

        assert len(classifiers) == 1
        assert len(regressors) == 0

    def test_promote_with_insufficient_samples_blocked(self, tmp_path):
        registry = ModelRegistry(registry_dir=tmp_path)
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data(n_samples=50)

        model = trainer.train(X, y, config=make_config())
        registry.register(model)

        success, issues = registry.promote(model.model_id)

        assert not success
        assert any("samples" in issue.lower() for issue in issues)

    def test_force_promote(self, tmp_path):
        registry = ModelRegistry(registry_dir=tmp_path)
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data(n_samples=50)

        model = trainer.train(X, y, config=make_config())
        registry.register(model)

        success, _ = registry.promote(model.model_id, force=True)

        assert success
        entry = registry.get(model.model_id)
        assert entry.status == ModelStatus.DEPLOYED
        assert registry.get_active_model(ModelType.PRIMARY_CLASSIFIER) is not None

    def test_archive_model(self, tmp_path):
        registry = ModelRegistry(registry_dir=tmp_path)
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data(n_samples=50)

        model = trainer.train(X, y, config=make_config())
        registry.register(model)

        assert registry.archive(model.model_id, reason="test")
        assert registry.get(model.model_id).status == ModelStatus.ARCHIVED

    def test_registry_persistence(self, tmp_path):
        """Registry reloads from disk."""
        trainer = ModelTrainer(model_dir=tmp_path / "models")
        X, y = make_classification_data()

        registry1 = ModelRegistry(registry_dir=tmp_path / "registry")
        model = trainer.train(X, y, config=make_config())
        registry1.register(model)

        # New instance loads from disk
        registry2 = ModelRegistry(registry_dir=tmp_path / "registry")
        assert registry2.get(model.model_id) is not None
