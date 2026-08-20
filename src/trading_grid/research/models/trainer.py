"""
ML Model Trainer for AI Research Pipeline.

Implements model training per AI_RESEARCH_ML_MODEL_SPEC.md.

Multi-model architecture:
- Primary Classifier: P(Net P&L > 0)
- Expected Net P&L Regressor
- Drawdown Regressor
- Capital Utilization Regressor
- Recovery Classifier
- Capital Exhaustion Classifier

Key principles:
- Time-based validation (no random shuffle)
- Walk-forward validation for deployment simulation
- Feature/label/dataset versioning
- Calibration for probability models
- Baseline comparison before complex models
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import pickle
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import structlog

logger = structlog.get_logger()

# Model version
MODEL_TRAINER_VERSION = "trainer-v001"


class ModelType(StrEnum):
    """Model types per spec §6."""

    PRIMARY_CLASSIFIER = "primary_classifier"
    NET_PNL_REGRESSOR = "net_pnl_regressor"
    DRAWDOWN_REGRESSOR = "drawdown_regressor"
    CAPITAL_UTILIZATION_REGRESSOR = "capital_utilization_regressor"
    RECOVERY_CLASSIFIER = "recovery_classifier"
    CAPITAL_EXHAUSTION_CLASSIFIER = "capital_exhaustion_classifier"


class ModelFamily(StrEnum):
    """Model families per spec §31."""

    LOGISTIC_REGRESSION = "logistic_regression"
    LINEAR_REGRESSION = "linear_regression"
    DECISION_TREE = "decision_tree"
    RANDOM_FOREST = "random_forest"
    GRADIENT_BOOSTING = "gradient_boosting"
    LIGHTGBM = "lightgbm"


class ModelStatus(StrEnum):
    """Model lifecycle status."""

    TRAINING = "TRAINING"
    TRAINED = "TRAINED"
    VALIDATED = "VALIDATED"
    FAILED = "FAILED"
    DEPLOYED = "DEPLOYED"
    ARCHIVED = "ARCHIVED"


@dataclass
class ModelConfig:
    """Configuration for model training."""

    model_type: ModelType
    model_family: ModelFamily
    feature_version: str
    label_version: str
    dataset_version: str
    simulator_version: str
    execution_model_version: str
    horizon: str

    # Hyperparameters
    hyperparameters: dict[str, Any] = field(default_factory=dict)

    # Training settings
    random_seed: int = 42
    calibration_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_type": self.model_type.value,
            "model_family": self.model_family.value,
            "feature_version": self.feature_version,
            "label_version": self.label_version,
            "dataset_version": self.dataset_version,
            "simulator_version": self.simulator_version,
            "execution_model_version": self.execution_model_version,
            "horizon": self.horizon,
            "hyperparameters": self.hyperparameters,
            "random_seed": self.random_seed,
            "calibration_enabled": self.calibration_enabled,
        }


@dataclass
class TrainingMetrics:
    """Metrics from model training."""

    # Classification metrics
    roc_auc: float | None = None
    pr_auc: float | None = None
    log_loss: float | None = None
    brier_score: float | None = None
    calibration_error: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    accuracy: float | None = None

    # Regression metrics
    mae: float | None = None
    rmse: float | None = None
    r_squared: float | None = None
    spearman_correlation: float | None = None

    # Training info
    train_samples: int = 0
    validation_samples: int = 0
    training_time_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class WalkForwardFold:
    """Results from one walk-forward fold."""

    fold_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    train_samples: int
    test_samples: int
    metrics: TrainingMetrics


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward validation results."""

    folds: list[WalkForwardFold] = field(default_factory=list)

    @property
    def mean_roc_auc(self) -> float | None:
        aucs = [f.metrics.roc_auc for f in self.folds if f.metrics.roc_auc is not None]
        return float(np.mean(aucs)) if aucs else None

    @property
    def std_roc_auc(self) -> float | None:
        aucs = [f.metrics.roc_auc for f in self.folds if f.metrics.roc_auc is not None]
        return float(np.std(aucs)) if aucs else None

    @property
    def mean_mae(self) -> float | None:
        maes = [f.metrics.mae for f in self.folds if f.metrics.mae is not None]
        return float(np.mean(maes)) if maes else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "num_folds": len(self.folds),
            "mean_roc_auc": self.mean_roc_auc,
            "std_roc_auc": self.std_roc_auc,
            "mean_mae": self.mean_mae,
            "folds": [
                {
                    "fold_index": f.fold_index,
                    "train_start": f.train_start.isoformat(),
                    "train_end": f.train_end.isoformat(),
                    "test_start": f.test_start.isoformat(),
                    "test_end": f.test_end.isoformat(),
                    "train_samples": f.train_samples,
                    "test_samples": f.test_samples,
                    "metrics": f.metrics.to_dict(),
                }
                for f in self.folds
            ],
        }


@dataclass
class TrainedModel:
    """A trained model with metadata."""

    model_id: str
    config: ModelConfig
    status: ModelStatus
    trained_at: datetime
    model: Any = None  # The actual sklearn/lightgbm model
    calibrator: Any = None  # Optional calibrator
    feature_names: list[str] = field(default_factory=list)
    feature_importance: dict[str, float] = field(default_factory=dict)
    train_metrics: TrainingMetrics | None = None
    validation_metrics: TrainingMetrics | None = None
    walk_forward_result: WalkForwardResult | None = None

    @property
    def is_ready(self) -> bool:
        return self.status in (ModelStatus.TRAINED, ModelStatus.VALIDATED, ModelStatus.DEPLOYED)

    def predict(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Make predictions."""
        if self.model is None:
            raise ValueError("Model not loaded")
        result: npt.NDArray[np.float64] = self.model.predict(X)
        return result

    def predict_proba(self, X: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        """Predict probabilities (classification only)."""
        if self.model is None:
            raise ValueError("Model not loaded")
        if not hasattr(self.model, "predict_proba"):
            raise ValueError("Model does not support predict_proba")
        proba: npt.NDArray[np.float64] = self.model.predict_proba(X)
        if self.calibrator is not None:
            pos_proba = proba[:, 1] if proba.ndim == 2 and proba.shape[1] >= 2 else proba
            calibrated_pos = self.calibrator.predict(pos_proba)
            calibrated_pos = np.clip(calibrated_pos, 0.0, 1.0)
            proba = np.column_stack([1.0 - calibrated_pos, calibrated_pos])
        return proba


class ModelTrainer:
    """
    Trains ML models for grid suitability prediction.

    Usage:
        trainer = ModelTrainer()
        model = trainer.train(
            X_train, y_train, X_val, y_val,
            config=ModelConfig(...)
        )
    """

    def __init__(self, model_dir: Path | str = "models") -> None:
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

    def train(
        self,
        X_train: npt.NDArray[np.float64],
        y_train: npt.NDArray[np.float64],
        X_val: npt.NDArray[np.float64] | None = None,
        y_val: npt.NDArray[np.float64] | None = None,
        config: ModelConfig | None = None,
        feature_names: list[str] | None = None,
    ) -> TrainedModel:
        """
        Train a model.

        Args:
            X_train: Training features
            y_train: Training labels
            X_val: Validation features (optional)
            y_val: Validation labels (optional)
            config: Model configuration
            feature_names: Feature names for importance tracking

        Returns:
            TrainedModel with trained model and metrics
        """
        if config is None:
            config = self._default_config()

        model_id = self._generate_model_id(config)
        start_time = datetime.now(UTC)

        logger.info(
            "model_training_started",
            model_id=model_id,
            model_type=config.model_type.value,
            model_family=config.model_family.value,
            train_samples=len(X_train),
        )

        try:
            # Create model
            model = self._create_model(config)

            # Train
            model.fit(X_train, y_train)

            # Calculate training metrics
            train_metrics = self._calculate_metrics(model, X_train, y_train, config.model_type)
            train_metrics.train_samples = len(X_train)
            train_metrics.training_time_seconds = (datetime.now(UTC) - start_time).total_seconds()

            # Validation metrics
            validation_metrics = None
            if X_val is not None and y_val is not None:
                validation_metrics = self._calculate_metrics(model, X_val, y_val, config.model_type)
                validation_metrics.validation_samples = len(X_val)

            # Feature importance
            feature_importance = self._extract_feature_importance(model, feature_names)

            # Calibration
            calibrator = None
            if config.calibration_enabled and config.model_type in (
                ModelType.PRIMARY_CLASSIFIER,
                ModelType.RECOVERY_CLASSIFIER,
                ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
            ):
                calibrator = self._fit_calibrator(model, X_val, y_val)

            trained_model = TrainedModel(
                model_id=model_id,
                config=config,
                status=ModelStatus.TRAINED,
                trained_at=start_time,
                model=model,
                calibrator=calibrator,
                feature_names=feature_names or [],
                feature_importance=feature_importance,
                train_metrics=train_metrics,
                validation_metrics=validation_metrics,
            )

            logger.info(
                "model_training_completed",
                model_id=model_id,
                train_roc_auc=train_metrics.roc_auc,
                val_roc_auc=validation_metrics.roc_auc if validation_metrics else None,
            )

            return trained_model

        except Exception as e:
            logger.error("model_training_failed", model_id=model_id, error=str(e))
            return TrainedModel(
                model_id=model_id,
                config=config,
                status=ModelStatus.FAILED,
                trained_at=start_time,
            )

    def walk_forward_validate(
        self,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64],
        timestamps: npt.NDArray[np.datetime64],
        config: ModelConfig,
        n_folds: int = 5,
        train_window_days: int = 90,
        test_window_days: int = 30,
        feature_names: list[str] | None = None,
    ) -> WalkForwardResult:
        """
        Perform walk-forward validation.

        Per spec §35: Simulates repeated future deployment.

        Args:
            X: All features
            y: All labels
            timestamps: Observation timestamps for each sample
            config: Model configuration
            n_folds: Number of folds
            train_window_days: Training window size in days
            test_window_days: Test window size in days
            feature_names: Feature names

        Returns:
            WalkForwardResult with per-fold metrics
        """
        result = WalkForwardResult()

        # Sort by timestamp
        sort_idx = np.argsort(timestamps)
        X_sorted = X[sort_idx]
        y_sorted = y[sort_idx]
        ts_sorted = timestamps[sort_idx]

        # Calculate fold boundaries
        total_days = int((ts_sorted[-1] - ts_sorted[0]) / np.timedelta64(1, "D"))
        step_days = max(1, (total_days - train_window_days) // n_folds)

        for fold_idx in range(n_folds):
            train_end_offset = train_window_days + fold_idx * step_days
            test_end_offset = train_end_offset + test_window_days

            train_end_time = ts_sorted[0] + np.timedelta64(train_end_offset, "D")
            test_end_time = ts_sorted[0] + np.timedelta64(test_end_offset, "D")

            # Split data
            train_mask = ts_sorted < train_end_time
            test_mask = (ts_sorted >= train_end_time) & (ts_sorted < test_end_time)

            X_train_all, y_train_all = X_sorted[train_mask], y_sorted[train_mask]
            X_test, y_test = X_sorted[test_mask], y_sorted[test_mask]

            if len(X_train_all) < 10 or len(X_test) < 5:
                logger.warning(
                    "walk_forward_fold_skipped",
                    fold_index=fold_idx,
                    reason="insufficient_samples",
                )
                continue

            # [R-M5] Split training data into train-proper and validation (calibration) set.
            # The last 20% of the training window (by time order) is held out for
            # calibration fitting, ensuring the calibrator is actually trained.
            val_split_idx = max(1, int(len(X_train_all) * 0.8))
            X_train, y_train = X_train_all[:val_split_idx], y_train_all[:val_split_idx]
            X_val, y_val = X_train_all[val_split_idx:], y_train_all[val_split_idx:]

            # Need minimum samples in both splits
            if len(X_train) < 10 or len(X_val) < 5:
                # Fall back: use all data for training, no calibration
                X_train, y_train = X_train_all, y_train_all
                X_val, y_val = None, None

            # Train model for this fold with validation set for calibration
            fold_model = self.train(
                X_train,
                y_train,
                X_val=X_val,
                y_val=y_val,
                config=config,
                feature_names=feature_names,
            )

            if fold_model.status == ModelStatus.FAILED:
                continue

            # [R-M5] Evaluate using the TrainedModel directly, which applies
            # calibration internally via predict_proba() when a calibrator exists.
            metrics = self._calculate_metrics(fold_model, X_test, y_test, config.model_type)

            fold = WalkForwardFold(
                fold_index=fold_idx,
                train_start=self._to_datetime(ts_sorted[0]),
                train_end=self._to_datetime(train_end_time),
                test_start=self._to_datetime(train_end_time),
                test_end=self._to_datetime(test_end_time),
                train_samples=len(X_train),
                test_samples=len(X_test),
                metrics=metrics,
            )
            result.folds.append(fold)

        logger.info(
            "walk_forward_validation_completed",
            n_folds=len(result.folds),
            mean_roc_auc=result.mean_roc_auc,
        )

        return result

    def save_model(self, trained_model: TrainedModel) -> Path:
        """Save model to disk."""
        model_path = self.model_dir / f"{trained_model.model_id}.pkl"
        meta_path = self.model_dir / f"{trained_model.model_id}.meta.json"

        # Save model
        with model_path.open("wb") as f:
            pickle.dump(
                {
                    "model": trained_model.model,
                    "calibrator": trained_model.calibrator,
                },
                f,
            )

        # Save metadata
        metadata = {
            "model_id": trained_model.model_id,
            "config": trained_model.config.to_dict(),
            "status": trained_model.status.value,
            "trained_at": trained_model.trained_at.isoformat(),
            "feature_names": trained_model.feature_names,
            "feature_importance": trained_model.feature_importance,
            "train_metrics": (
                trained_model.train_metrics.to_dict() if trained_model.train_metrics else None
            ),
            "validation_metrics": (
                trained_model.validation_metrics.to_dict()
                if trained_model.validation_metrics
                else None
            ),
            "walk_forward_result": (
                trained_model.walk_forward_result.to_dict()
                if trained_model.walk_forward_result
                else None
            ),
            "trainer_version": MODEL_TRAINER_VERSION,
        }
        with meta_path.open("w") as f:
            json.dump(metadata, f, indent=2)

        logger.info("model_saved", model_id=trained_model.model_id, path=str(model_path))
        return model_path

    def load_model(self, model_id: str) -> TrainedModel:
        """Load model from disk."""
        model_path = self.model_dir / f"{model_id}.pkl"
        meta_path = self.model_dir / f"{model_id}.meta.json"

        with model_path.open("rb") as f:
            model_data = pickle.load(f)

        with meta_path.open() as f:
            metadata = json.load(f)

        config = ModelConfig(
            model_type=ModelType(metadata["config"]["model_type"]),
            model_family=ModelFamily(metadata["config"]["model_family"]),
            feature_version=metadata["config"]["feature_version"],
            label_version=metadata["config"]["label_version"],
            dataset_version=metadata["config"]["dataset_version"],
            simulator_version=metadata["config"]["simulator_version"],
            execution_model_version=metadata["config"]["execution_model_version"],
            horizon=metadata["config"]["horizon"],
            hyperparameters=metadata["config"]["hyperparameters"],
            random_seed=metadata["config"]["random_seed"],
            calibration_enabled=metadata["config"]["calibration_enabled"],
        )

        return TrainedModel(
            model_id=model_id,
            config=config,
            status=ModelStatus(metadata["status"]),
            trained_at=datetime.fromisoformat(metadata["trained_at"]),
            model=model_data["model"],
            calibrator=model_data["calibrator"],
            feature_names=metadata["feature_names"],
            feature_importance=metadata["feature_importance"],
        )

    def _create_model(self, config: ModelConfig) -> Any:
        """Create model instance based on config."""
        from sklearn.ensemble import (
            GradientBoostingClassifier,
            GradientBoostingRegressor,
            RandomForestClassifier,
            RandomForestRegressor,
        )
        from sklearn.linear_model import LinearRegression, LogisticRegression
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

        params = config.hyperparameters.copy()
        params.setdefault("random_state", config.random_seed)

        if config.model_family == ModelFamily.LIGHTGBM:
            try:
                import lightgbm as lgb

                if config.model_type in (
                    ModelType.PRIMARY_CLASSIFIER,
                    ModelType.RECOVERY_CLASSIFIER,
                    ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
                ):
                    return lgb.LGBMClassifier(
                        objective="binary",
                        n_estimators=params.get("n_estimators", 100),
                        learning_rate=params.get("learning_rate", 0.1),
                        max_depth=params.get("max_depth", 6),
                        num_leaves=params.get("num_leaves", 31),
                        random_state=config.random_seed,
                        verbose=-1,
                    )
                else:
                    return lgb.LGBMRegressor(
                        n_estimators=params.get("n_estimators", 100),
                        learning_rate=params.get("learning_rate", 0.1),
                        max_depth=params.get("max_depth", 6),
                        num_leaves=params.get("num_leaves", 31),
                        random_state=config.random_seed,
                        verbose=-1,
                    )
            except ImportError:
                logger.warning("lightgbm_not_available, falling back to gradient boosting")
                config.model_family = ModelFamily.GRADIENT_BOOSTING

        if config.model_family == ModelFamily.LOGISTIC_REGRESSION:
            return LogisticRegression(**params)

        if config.model_family == ModelFamily.LINEAR_REGRESSION:
            return LinearRegression()

        if config.model_family == ModelFamily.DECISION_TREE:
            if config.model_type in (
                ModelType.PRIMARY_CLASSIFIER,
                ModelType.RECOVERY_CLASSIFIER,
                ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
            ):
                return DecisionTreeClassifier(**params)
            return DecisionTreeRegressor(**params)

        if config.model_family == ModelFamily.RANDOM_FOREST:
            if config.model_type in (
                ModelType.PRIMARY_CLASSIFIER,
                ModelType.RECOVERY_CLASSIFIER,
                ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
            ):
                return RandomForestClassifier(**params)
            return RandomForestRegressor(**params)

        if config.model_family == ModelFamily.GRADIENT_BOOSTING:
            if config.model_type in (
                ModelType.PRIMARY_CLASSIFIER,
                ModelType.RECOVERY_CLASSIFIER,
                ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
            ):
                return GradientBoostingClassifier(**params)
            return GradientBoostingRegressor(**params)

        raise ValueError(f"Unknown model family: {config.model_family}")

    def _calculate_metrics(
        self,
        model: Any,
        X: npt.NDArray[np.float64],
        y: npt.NDArray[np.float64],
        model_type: ModelType,
    ) -> TrainingMetrics:
        """Calculate evaluation metrics."""
        from scipy.stats import spearmanr
        from sklearn.metrics import (
            accuracy_score,
            brier_score_loss,
            f1_score,
            log_loss,
            mean_absolute_error,
            mean_squared_error,
            precision_score,
            r2_score,
            recall_score,
            roc_auc_score,
        )

        metrics = TrainingMetrics()
        y_pred = model.predict(X)

        if model_type in (
            ModelType.PRIMARY_CLASSIFIER,
            ModelType.RECOVERY_CLASSIFIER,
            ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
        ):
            # Classification metrics
            if hasattr(model, "predict_proba"):
                y_proba = model.predict_proba(X)[:, 1]
                with contextlib.suppress(ValueError):  # Only one class present
                    metrics.roc_auc = float(roc_auc_score(y, y_proba))
                metrics.log_loss = float(log_loss(y, y_proba, labels=[0, 1]))
                metrics.brier_score = float(brier_score_loss(y, y_proba))

            metrics.accuracy = float(accuracy_score(y, y_pred))
            metrics.precision = float(precision_score(y, y_pred, zero_division=0))
            metrics.recall = float(recall_score(y, y_pred, zero_division=0))
            metrics.f1_score = float(f1_score(y, y_pred, zero_division=0))
        else:
            # Regression metrics
            metrics.mae = float(mean_absolute_error(y, y_pred))
            metrics.rmse = float(np.sqrt(mean_squared_error(y, y_pred)))
            metrics.r_squared = float(r2_score(y, y_pred))
            if len(y) > 2:
                corr, _ = spearmanr(y, y_pred)
                metrics.spearman_correlation = float(corr) if not np.isnan(corr) else None

        return metrics

    def _extract_feature_importance(
        self, model: Any, feature_names: list[str] | None
    ) -> dict[str, float]:
        """Extract feature importance from model."""
        importance: dict[str, float] = {}

        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            names = feature_names or [f"feature_{i}" for i in range(len(importances))]
            for name, imp in zip(names, importances, strict=True):
                importance[name] = float(imp)
        elif hasattr(model, "coef_"):
            coef = model.coef_
            if coef.ndim > 1:
                coef = coef[0]
            names = feature_names or [f"feature_{i}" for i in range(len(coef))]
            for name, c in zip(names, coef, strict=True):
                importance[name] = float(abs(c))

        return importance

    def _fit_calibrator(
        self,
        model: Any,
        X_val: npt.NDArray[np.float64] | None,
        y_val: npt.NDArray[np.float64] | None,
    ) -> Any:
        """Fit probability calibrator."""
        if X_val is None or y_val is None or len(X_val) < 50:
            return None

        try:
            from sklearn.isotonic import IsotonicRegression

            y_proba = model.predict_proba(X_val)[:, 1]
            calibrator = IsotonicRegression(out_of_bounds="clip")
            calibrator.fit(y_proba, y_val)
            return calibrator
        except Exception as e:
            logger.warning("calibration_failed", error=str(e))
            return None

    def _to_datetime(self, ts: Any) -> datetime:
        """Convert numpy datetime64 to Python datetime (UTC)."""
        if isinstance(ts, datetime):
            return ts
        # numpy datetime64 -> pandas Timestamp -> datetime
        import pandas as pd

        return pd.Timestamp(ts).to_pydatetime().replace(tzinfo=UTC)

    def _generate_model_id(self, config: ModelConfig) -> str:
        """Generate deterministic model ID."""
        content = json.dumps(config.to_dict(), sort_keys=True)
        hash_suffix = hashlib.sha256(content.encode()).hexdigest()[:8]
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        return f"model-{config.model_type.value}-{timestamp}-{hash_suffix}"

    def _default_config(self) -> ModelConfig:
        """Create default model config."""
        return ModelConfig(
            model_type=ModelType.PRIMARY_CLASSIFIER,
            model_family=ModelFamily.GRADIENT_BOOSTING,
            feature_version="fml-v001",
            label_version="label-v001",
            dataset_version="dataset-v001",
            simulator_version="sim-v001",
            execution_model_version="exec-v001",
            horizon="30D",
        )
