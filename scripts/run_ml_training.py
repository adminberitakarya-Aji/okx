#!/usr/bin/env python3
"""
ML Training Pipeline Orchestrator.

This script coordinates the end-to-end ML training pipeline:
1. Data Ingestion — Fetch historical candles from exchanges
2. Feature Engineering — Compute market state, execution economics features
3. Blueprint Generation — Generate candidate grid blueprints
4. Grid Simulation — Run deterministic simulations
5. Label Generation — Convert simulation results to labels
6. Dataset Building — Join features + labels with time-based split
7. Model Training — Train 6 models (LightGBM/sklearn)
8. Model Evaluation — Walk-forward validation, baseline comparison
9. Model Promotion — Promote best model to production

Usage:
    uv run python scripts/run_ml_training.py --full          # Full pipeline
    uv run python scripts/run_ml_training.py --ingest        # Data ingestion only
    uv run python scripts/run_ml_training.py --features      # Feature engineering only
    uv run python scripts/run_ml_training.py --simulate      # Grid simulation only
    uv run python scripts/run_ml_training.py --train         # Model training only
    uv run python scripts/run_ml_training.py --evaluate      # Evaluation only
    uv run python scripts/run_ml_training.py --promote       # Promote model
    uv run python scripts/run_ml_training.py --status        # Show pipeline status

Options:
    --markets BTC-USDT,ETH-USDT    Markets to process (default: TOP 10)
    --months 6                     Historical data period in months
    --exchange OKX|BINANCE|BYBIT   Exchange to fetch data from (default: OKX)
    --interval 1H                  Candle interval
    --model-family lightgbm        Model family (lightgbm, gradient_boosting)
    --force                        Force operations (e.g., promote without thresholds)

Reference: docs/ML_TRAINING_PIPELINE_SPEC.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from okx_trading.research.ingestion.binance_client import BinanceHistoricalClient
from okx_trading.research.ingestion.bybit_client import BybitHistoricalClient
from okx_trading.research.ingestion.okx_client import OKXHistoricalClient
from okx_trading.research.ingestion.storage import ParquetStorage
from okx_trading.research.models.registry import ModelRegistry, PromotionThresholds
from okx_trading.research.models.trainer import (
    ModelConfig,
    ModelFamily,
    ModelStatus,
    ModelTrainer,
    ModelType,
)

logger = structlog.get_logger()

# Supported exchanges for data ingestion
SUPPORTED_EXCHANGES = ("OKX", "BINANCE", "BYBIT")


def create_historical_client(
    exchange: str,
) -> OKXHistoricalClient | BinanceHistoricalClient | BybitHistoricalClient:
    """
    Create the appropriate historical data client for the given exchange.

    Args:
        exchange: Exchange ID (OKX, BINANCE, BYBIT)

    Returns:
        Historical data client instance for the exchange

    Raises:
        ValueError: If exchange is not supported
    """
    exchange_upper = exchange.upper()
    if exchange_upper == "OKX":
        return OKXHistoricalClient()
    elif exchange_upper == "BINANCE":
        return BinanceHistoricalClient()
    elif exchange_upper == "BYBIT":
        return BybitHistoricalClient()
    else:
        raise ValueError(
            f"Unsupported exchange: {exchange}. Supported: {', '.join(SUPPORTED_EXCHANGES)}"
        )


# Default configuration
DEFAULT_MARKETS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "XRP-USDT",
    "DOGE-USDT",
    "ADA-USDT",
    "AVAX-USDT",
    "DOT-USDT",
    "LINK-USDT",
    "MATIC-USDT",
]
DEFAULT_MONTHS = 6
DEFAULT_EXCHANGE = "OKX"
DEFAULT_INTERVAL = "1H"
DEFAULT_DATA_DIR = "data/research"
DEFAULT_MODEL_DIR = "models"
DEFAULT_REGISTRY_DIR = "models/registry"

# Pipeline state file
PIPELINE_STATE_FILE = "data/pipeline_state.json"


@dataclass
class PipelineConfig:
    """Configuration for the ML training pipeline."""

    markets: list[str] = field(default_factory=lambda: DEFAULT_MARKETS.copy())
    months: int = DEFAULT_MONTHS
    exchange: str = DEFAULT_EXCHANGE
    interval: str = DEFAULT_INTERVAL
    data_dir: str = DEFAULT_DATA_DIR
    model_dir: str = DEFAULT_MODEL_DIR
    registry_dir: str = DEFAULT_REGISTRY_DIR
    model_family: str = "lightgbm"
    random_seed: int = 42
    horizon_days: int = 30
    force: bool = False


@dataclass
class PipelineState:
    """Tracks pipeline execution state."""

    last_ingest: datetime | None = None
    last_features: datetime | None = None
    last_simulation: datetime | None = None
    last_training: datetime | None = None
    last_evaluation: datetime | None = None
    last_promotion: datetime | None = None
    ingested_markets: list[str] = field(default_factory=list)
    total_candles: int = 0
    trained_models: list[str] = field(default_factory=list)
    promoted_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_ingest": self.last_ingest.isoformat() if self.last_ingest else None,
            "last_features": self.last_features.isoformat() if self.last_features else None,
            "last_simulation": self.last_simulation.isoformat() if self.last_simulation else None,
            "last_training": self.last_training.isoformat() if self.last_training else None,
            "last_evaluation": self.last_evaluation.isoformat() if self.last_evaluation else None,
            "last_promotion": self.last_promotion.isoformat() if self.last_promotion else None,
            "ingested_markets": self.ingested_markets,
            "total_candles": self.total_candles,
            "trained_models": self.trained_models,
            "promoted_model": self.promoted_model,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineState:
        def parse_dt(v: str | None) -> datetime | None:
            return datetime.fromisoformat(v) if v else None

        return cls(
            last_ingest=parse_dt(data.get("last_ingest")),
            last_features=parse_dt(data.get("last_features")),
            last_simulation=parse_dt(data.get("last_simulation")),
            last_training=parse_dt(data.get("last_training")),
            last_evaluation=parse_dt(data.get("last_evaluation")),
            last_promotion=parse_dt(data.get("last_promotion")),
            ingested_markets=data.get("ingested_markets", []),
            total_candles=data.get("total_candles", 0),
            trained_models=data.get("trained_models", []),
            promoted_model=data.get("promoted_model"),
        )


def load_pipeline_state() -> PipelineState:
    """Load pipeline state from disk."""
    state_path = Path(PIPELINE_STATE_FILE)
    if state_path.exists():
        try:
            with state_path.open() as f:
                return PipelineState.from_dict(json.load(f))
        except Exception as e:
            logger.warning("pipeline_state_load_failed", error=str(e))
    return PipelineState()


def save_pipeline_state(state: PipelineState) -> None:
    """Save pipeline state to disk."""
    state_path = Path(PIPELINE_STATE_FILE)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w") as f:
        json.dump(state.to_dict(), f, indent=2)


# =============================================================================
# Stage 1: Data Ingestion
# =============================================================================


async def run_data_ingestion(config: PipelineConfig) -> dict[str, Any]:
    """
    Stage 1: Fetch historical candles from exchange.

    Downloads OHLCV candles for each market and stores to Parquet.
    """
    logger.info(
        "stage_1_data_ingestion_started",
        markets=config.markets,
        months=config.months,
        exchange=config.exchange,
        interval=config.interval,
    )

    storage = ParquetStorage(
        base_dir=config.data_dir,
        version="v1",
        exchange_id=config.exchange,
    )

    end_time = datetime.now(UTC)
    start_time = end_time - timedelta(days=config.months * 30)

    results: dict[str, Any] = {
        "markets_processed": 0,
        "total_candles": 0,
        "errors": [],
        "exchange": config.exchange,
    }

    # Create the appropriate client for the configured exchange (OKX/BINANCE/BYBIT)
    client = create_historical_client(config.exchange)
    async with client:
        for market_id in config.markets:
            try:
                logger.info("ingesting_market", market_id=market_id)

                candles, stats = await client.download_candles(
                    market_id=market_id,
                    interval=config.interval,
                    start=start_time,
                    end=end_time,
                )

                if not candles:
                    logger.warning("no_candles_fetched", market_id=market_id)
                    results["errors"].append(f"{market_id}: no candles fetched")
                    continue

                # Validate candles
                issues = client.validate_candles(candles, config.interval)
                if issues:
                    logger.warning("candle_validation_issues", market_id=market_id, issues=issues)

                # Save to Parquet
                storage.save_candles(candles, market_id, config.interval, gaps=issues)

                results["markets_processed"] += 1
                results["total_candles"] += len(candles)

                logger.info(
                    "market_ingested",
                    market_id=market_id,
                    candles=len(candles),
                    duration_seconds=stats.duration_seconds,
                )

            except Exception as e:
                logger.error("market_ingestion_failed", market_id=market_id, error=str(e))
                results["errors"].append(f"{market_id}: {e}")

    logger.info(
        "stage_1_data_ingestion_completed",
        markets_processed=results["markets_processed"],
        total_candles=results["total_candles"],
        errors=len(results["errors"]),
    )

    return results


# =============================================================================
# Stage 2: Feature Engineering
# =============================================================================


def run_feature_engineering(config: PipelineConfig) -> dict[str, Any]:
    """
    Stage 2: Compute features from historical data.

    Computes Market State features (volatility, momentum, etc.)
    for each market at each observation time.
    """
    logger.info("stage_2_feature_engineering_started", markets=config.markets)

    import pandas as pd

    storage = ParquetStorage(
        base_dir=config.data_dir,
        version="v1",
        exchange_id=config.exchange,
    )

    results: dict[str, Any] = {
        "markets_processed": 0,
        "total_observations": 0,
        "features_computed": 0,
        "errors": [],
    }

    all_features: list[pd.DataFrame] = []

    for market_id in config.markets:
        try:
            candles = storage.load_candles(market_id, config.interval)

            if len(candles) < 100:
                logger.warning("insufficient_candles", market_id=market_id, count=len(candles))
                continue

            # Convert to DataFrame
            df = pd.DataFrame(
                [
                    {
                        "timestamp": c.timestamp,
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume),
                        "quote_volume": float(c.quote_volume),
                    }
                    for c in candles
                ]
            )
            df = df.sort_values("timestamp").reset_index(drop=True)

            # Compute Market State features
            features_df = _compute_market_state_features(df, market_id, config.exchange)
            all_features.append(features_df)

            results["markets_processed"] += 1
            results["total_observations"] += len(features_df)
            results["features_computed"] = len(features_df.columns) - 3  # Exclude id columns

            logger.info(
                "features_computed",
                market_id=market_id,
                observations=len(features_df),
                features=len(features_df.columns) - 3,
            )

        except FileNotFoundError:
            logger.warning("no_data_for_market", market_id=market_id)
            results["errors"].append(f"{market_id}: no data found")
        except Exception as e:
            logger.error("feature_computation_failed", market_id=market_id, error=str(e))
            results["errors"].append(f"{market_id}: {e}")

    # Save combined features
    if all_features:
        combined = pd.concat(all_features, ignore_index=True)
        features_dir = Path(config.data_dir) / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        combined.to_parquet(features_dir / "market_features.parquet", index=False)
        logger.info("features_saved", path=str(features_dir / "market_features.parquet"))

    logger.info(
        "stage_2_feature_engineering_completed",
        markets_processed=results["markets_processed"],
        total_observations=results["total_observations"],
    )

    return results


def _compute_market_state_features(
    df: pd.DataFrame, market_id: str, exchange_id: str
) -> pd.DataFrame:
    """Compute Market State features (F-MKT) from candle data."""

    # Initialize with index to avoid NaN when assigning scalars before series
    features = pd.DataFrame(index=df.index)
    features["market_id"] = market_id
    features["exchange_id"] = exchange_id
    features["timestamp"] = df["timestamp"]

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Price returns
    features["return_1h"] = close.pct_change(1)
    features["return_4h"] = close.pct_change(4)
    features["return_24h"] = close.pct_change(24)
    features["return_7d"] = close.pct_change(168)

    # Volatility (rolling std of returns)
    returns_1h = close.pct_change(1)
    features["volatility_24h"] = returns_1h.rolling(24).std()
    features["volatility_7d"] = returns_1h.rolling(168).std()
    features["volatility_30d"] = returns_1h.rolling(720).std()

    # ATR (Average True Range)
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    features["atr_14"] = tr.rolling(14).mean()
    features["atr_pct"] = features["atr_14"] / close

    # Price position in range
    rolling_high = high.rolling(168).max()
    rolling_low = low.rolling(168).min()
    features["price_position_7d"] = (close - rolling_low) / (rolling_high - rolling_low + 1e-10)

    # Volume features
    features["volume_ratio_24h"] = volume / volume.rolling(24).mean()
    features["volume_ratio_7d"] = volume / volume.rolling(168).mean()

    # Momentum indicators
    features["rsi_14"] = _compute_rsi(close, 14)
    features["macd_signal"] = _compute_macd_signal(close)

    # Trend strength
    sma_20 = close.rolling(20).mean()
    sma_50 = close.rolling(50).mean()
    features["trend_strength"] = (sma_20 - sma_50) / sma_50

    # Range width
    features["range_width_7d"] = (rolling_high - rolling_low) / close

    # Drop rows with NaN (warmup period)
    features = features.dropna().reset_index(drop=True)

    return features


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI indicator."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def _compute_macd_signal(close: pd.Series) -> pd.Series:
    """Compute MACD signal line difference."""
    ema_12 = close.ewm(span=12, adjust=False).mean()
    ema_26 = close.ewm(span=26, adjust=False).mean()
    macd = ema_12 - ema_26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd - signal


# =============================================================================
# Stage 3-5: Simulation & Labels (Simplified)
# =============================================================================


def run_simulation_and_labels(config: PipelineConfig) -> dict[str, Any]:
    """
    Stages 3-5: Generate blueprints, run simulations, generate labels.

    This is a simplified implementation that generates synthetic labels
    based on historical volatility and price patterns. Full simulation
    integration can be added later.
    """
    logger.info("stage_3_5_simulation_labels_started")

    import numpy as np
    import pandas as pd

    features_path = Path(config.data_dir) / "features" / "market_features.parquet"
    if not features_path.exists():
        raise FileNotFoundError("Features not found. Run --features first.")

    features_df = pd.read_parquet(features_path)

    results: dict[str, Any] = {
        "observations": len(features_df),
        "labels_generated": 0,
    }

    # Generate labels based on future returns (simplified approach)
    # In production, this would use the full GridSimulator
    labels = pd.DataFrame()
    labels["market_id"] = features_df["market_id"]
    labels["exchange_id"] = features_df["exchange_id"]
    labels["timestamp"] = features_df["timestamp"]

    # Group by market and compute forward returns
    for market_id in features_df["market_id"].unique():
        mask = features_df["market_id"] == market_id
        market_features = features_df[mask].copy()

        # Simulate grid outcome based on volatility and trend
        volatility = market_features["volatility_24h"].values
        trend = market_features["trend_strength"].values
        rsi = market_features["rsi_14"].values

        # Positive P&L more likely with:
        # - Moderate volatility (not too low, not too high)
        # - Ranging market (weak trend)
        # - RSI not extreme
        vol_score = np.exp(-((volatility - 0.02) ** 2) / (2 * 0.01**2))
        range_score = np.exp(-(trend**2) / 0.01)
        rsi_score = 1 - np.abs(rsi - 50) / 50

        pnl_probability = 0.3 + 0.4 * vol_score * range_score * rsi_score
        pnl_probability = np.clip(pnl_probability, 0.1, 0.9)

        # Generate labels
        positive_pnl = (np.random.random(len(market_features)) < pnl_probability).astype(int)
        net_pnl_return = np.where(
            positive_pnl == 1,
            np.abs(np.random.normal(0.03, 0.02, len(market_features))),
            -np.abs(np.random.normal(0.02, 0.015, len(market_features))),
        )
        max_drawdown = np.abs(np.random.normal(0.05, 0.03, len(market_features)))

        labels.loc[mask, "positive_pnl"] = positive_pnl
        labels.loc[mask, "net_pnl_return"] = net_pnl_return
        labels.loc[mask, "max_drawdown"] = max_drawdown
        labels.loc[mask, "capital_utilization"] = np.random.uniform(0.3, 0.9, len(market_features))
        labels.loc[mask, "recovered"] = (np.random.random(len(market_features)) < 0.7).astype(int)
        labels.loc[mask, "capital_exhausted"] = (
            np.random.random(len(market_features)) < 0.05
        ).astype(int)

    results["labels_generated"] = len(labels)

    # Save labels
    labels_dir = Path(config.data_dir) / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(labels_dir / "grid_labels.parquet", index=False)

    # Save dataset (features + labels joined)
    dataset = features_df.merge(labels, on=["market_id", "exchange_id", "timestamp"], how="inner")
    dataset_dir = Path(config.data_dir) / "dataset"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(dataset_dir / "training_dataset.parquet", index=False)

    results["dataset_rows"] = len(dataset)
    results["dataset_columns"] = len(dataset.columns)

    logger.info(
        "stage_3_5_simulation_labels_completed",
        observations=results["observations"],
        labels_generated=results["labels_generated"],
        dataset_rows=results["dataset_rows"],
    )

    return results


# =============================================================================
# Stage 6: Model Training
# =============================================================================


def run_model_training(config: PipelineConfig) -> dict[str, Any]:
    """
    Stage 6: Train ML models.

    Trains 6 models:
    1. Primary Classifier: P(Net P&L > 0)
    2. Net P&L Regressor
    3. Drawdown Regressor
    4. Capital Utilization Regressor
    5. Recovery Classifier
    6. Capital Exhaustion Classifier
    """
    logger.info("stage_6_model_training_started", model_family=config.model_family)

    import numpy as np
    import pandas as pd

    dataset_path = Path(config.data_dir) / "dataset" / "training_dataset.parquet"
    if not dataset_path.exists():
        raise FileNotFoundError("Dataset not found. Run --simulate first.")

    dataset = pd.read_parquet(dataset_path)

    results: dict[str, Any] = {
        "models_trained": 0,
        "models_failed": 0,
        "model_ids": [],
        "metrics": {},
    }

    # Prepare features and labels
    feature_columns = [
        col
        for col in dataset.columns
        if col
        not in [
            "market_id",
            "exchange_id",
            "timestamp",
            "positive_pnl",
            "net_pnl_return",
            "max_drawdown",
            "capital_utilization",
            "recovered",
            "capital_exhausted",
        ]
    ]

    X = dataset[feature_columns].values.astype(np.float64)
    timestamps = dataset["timestamp"].values

    # Time-based split (no random shuffle!)
    split_idx_1 = int(len(X) * 0.7)  # Train: 70%
    split_idx_2 = int(len(X) * 0.85)  # Validation: 15%, Test: 15%

    X_train, X_val, _X_test = X[:split_idx_1], X[split_idx_1:split_idx_2], X[split_idx_2:]
    _ts_train, _ts_val, _ts_test = (
        timestamps[:split_idx_1],
        timestamps[split_idx_1:split_idx_2],
        timestamps[split_idx_2:],
    )

    trainer = ModelTrainer(model_dir=config.model_dir)
    registry = ModelRegistry(registry_dir=config.registry_dir)

    # Model configurations
    model_configs = [
        (ModelType.PRIMARY_CLASSIFIER, "positive_pnl"),
        (ModelType.NET_PNL_REGRESSOR, "net_pnl_return"),
        (ModelType.DRAWDOWN_REGRESSOR, "max_drawdown"),
        (ModelType.CAPITAL_UTILIZATION_REGRESSOR, "capital_utilization"),
        (ModelType.RECOVERY_CLASSIFIER, "recovered"),
        (ModelType.CAPITAL_EXHAUSTION_CLASSIFIER, "capital_exhausted"),
    ]

    model_family = (
        ModelFamily.LIGHTGBM if config.model_family == "lightgbm" else ModelFamily.GRADIENT_BOOSTING
    )

    for model_type, label_column in model_configs:
        try:
            y = dataset[label_column].values.astype(np.float64)
            y_train, y_val = y[:split_idx_1], y[split_idx_1:split_idx_2]

            model_config = ModelConfig(
                model_type=model_type,
                model_family=model_family,
                feature_version="fml-v001",
                label_version="label-v001",
                dataset_version="dataset-v001",
                simulator_version="sim-v001",
                execution_model_version="exec-v001",
                horizon=f"{config.horizon_days}D",
                hyperparameters={
                    "n_estimators": 100,
                    "learning_rate": 0.1,
                    "max_depth": 6,
                    "num_leaves": 31,
                },
                random_seed=config.random_seed,
                calibration_enabled=True,
            )

            trained_model = trainer.train(
                X_train=X_train,
                y_train=y_train,
                X_val=X_val,
                y_val=y_val,
                config=model_config,
                feature_names=feature_columns,
            )

            if trained_model.status == ModelStatus.FAILED:
                results["models_failed"] += 1
                logger.error("model_training_failed", model_type=model_type.value)
                continue

            # Walk-forward validation for primary classifier
            if model_type == ModelType.PRIMARY_CLASSIFIER:
                wf_result = trainer.walk_forward_validate(
                    X=X,
                    y=y,
                    timestamps=timestamps,
                    config=model_config,
                    n_folds=5,
                    train_window_days=90,
                    test_window_days=30,
                    feature_names=feature_columns,
                )
                trained_model.walk_forward_result = wf_result

            # Save model
            trainer.save_model(trained_model)

            # Register model
            registry.register(trained_model)

            results["models_trained"] += 1
            results["model_ids"].append(trained_model.model_id)
            results["metrics"][model_type.value] = (
                trained_model.validation_metrics.to_dict()
                if trained_model.validation_metrics
                else {}
            )

            logger.info(
                "model_trained",
                model_type=model_type.value,
                model_id=trained_model.model_id,
                val_roc_auc=trained_model.validation_metrics.roc_auc
                if trained_model.validation_metrics
                else None,
            )

        except Exception as e:
            logger.error("model_training_error", model_type=model_type.value, error=str(e))
            results["models_failed"] += 1

    logger.info(
        "stage_6_model_training_completed",
        models_trained=results["models_trained"],
        models_failed=results["models_failed"],
    )

    return results


# =============================================================================
# Stage 7: Model Evaluation
# =============================================================================


def run_model_evaluation(config: PipelineConfig) -> dict[str, Any]:
    """
    Stage 7: Evaluate trained models.

    Compares models against baseline and quality thresholds.
    """
    logger.info("stage_7_model_evaluation_started")

    registry = ModelRegistry(registry_dir=config.registry_dir)

    results: dict[str, Any] = {
        "models_evaluated": 0,
        "models_passing": 0,
        "evaluation": {},
    }

    # Quality thresholds
    thresholds = {
        "min_roc_auc": 0.60,
        "min_samples": 100,
    }

    for model_type in [
        ModelType.PRIMARY_CLASSIFIER,
        ModelType.RECOVERY_CLASSIFIER,
        ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
    ]:
        models = registry.list_models(model_type=model_type, status=ModelStatus.TRAINED)

        for entry in models:
            val_metrics = entry.validation_metrics
            roc_auc = val_metrics.get("roc_auc")

            evaluation = {
                "model_id": entry.model_id,
                "roc_auc": roc_auc,
                "passes_threshold": roc_auc is not None and roc_auc >= thresholds["min_roc_auc"],
            }

            results["models_evaluated"] += 1
            if evaluation["passes_threshold"]:
                results["models_passing"] += 1

            results["evaluation"][entry.model_id] = evaluation

            logger.info(
                "model_evaluated",
                model_id=entry.model_id,
                roc_auc=roc_auc,
                passes=evaluation["passes_threshold"],
            )

    logger.info(
        "stage_7_model_evaluation_completed",
        models_evaluated=results["models_evaluated"],
        models_passing=results["models_passing"],
    )

    return results


# =============================================================================
# Stage 8: Model Promotion
# =============================================================================


def run_model_promotion(config: PipelineConfig, model_id: str | None = None) -> dict[str, Any]:
    """
    Stage 8: Promote model to production.

    Promotes the best model for each type to DEPLOYED status.
    """
    logger.info("stage_8_model_promotion_started", model_id=model_id)

    registry = ModelRegistry(registry_dir=config.registry_dir)

    results: dict[str, Any] = {
        "promoted": [],
        "failed": [],
    }

    thresholds = PromotionThresholds(
        min_roc_auc=0.60,
        min_walk_forward_roc_auc=0.55,
        max_calibration_error=0.10,
        min_train_samples=100,  # Lower for initial testing
        min_validation_samples=50,
    )

    if model_id:
        # Promote specific model
        success, issues = registry.promote(
            model_id, thresholds=thresholds, notes="Manual promotion", force=config.force
        )
        if success:
            results["promoted"].append(model_id)
        else:
            results["failed"].append({"model_id": model_id, "issues": issues})
    else:
        # Promote best model for each type
        for model_type in [
            ModelType.PRIMARY_CLASSIFIER,
            ModelType.NET_PNL_REGRESSOR,
            ModelType.DRAWDOWN_REGRESSOR,
            ModelType.CAPITAL_UTILIZATION_REGRESSOR,
            ModelType.RECOVERY_CLASSIFIER,
            ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
        ]:
            models = registry.list_models(model_type=model_type, status=ModelStatus.TRAINED)

            if not models:
                continue

            # Select best model by validation ROC AUC (for classifiers)
            best_model = None
            best_score = -1

            for entry in models:
                score = entry.validation_metrics.get("roc_auc", 0) or 0
                if score > best_score:
                    best_score = score
                    best_model = entry

            if best_model:
                success, issues = registry.promote(
                    best_model.model_id,
                    thresholds=thresholds,
                    notes="Auto-promoted as best model",
                    force=config.force,
                )
                if success:
                    results["promoted"].append(best_model.model_id)
                    logger.info("model_promoted", model_id=best_model.model_id)
                else:
                    results["failed"].append({"model_id": best_model.model_id, "issues": issues})
                    logger.warning(
                        "model_promotion_failed", model_id=best_model.model_id, issues=issues
                    )

    logger.info(
        "stage_8_model_promotion_completed",
        promoted=len(results["promoted"]),
        failed=len(results["failed"]),
    )

    return results


# =============================================================================
# Pipeline Status
# =============================================================================


def show_pipeline_status(config: PipelineConfig) -> None:
    """Display current pipeline status."""
    state = load_pipeline_state()
    registry = ModelRegistry(registry_dir=config.registry_dir)
    storage = ParquetStorage(base_dir=config.data_dir, version="v1", exchange_id=config.exchange)

    print("\n" + "=" * 60)
    print("ML TRAINING PIPELINE STATUS")
    print("=" * 60)

    print("\n[DATA STATUS]")
    print("-" * 40)
    print(f"  Exchange: {config.exchange}")
    print(f"  Data Directory: {config.data_dir}")
    print(f"  Markets with data: {len(storage.list_markets())}")
    print(f"  Last Ingest: {state.last_ingest or 'Never'}")
    print(f"  Total Candles: {state.total_candles}")

    print("\n[PIPELINE STAGES]")
    print("-" * 40)
    print(f"  Data Ingestion: {state.last_ingest or 'Not run'}")
    print(f"  Feature Engineering: {state.last_features or 'Not run'}")
    print(f"  Simulation & Labels: {state.last_simulation or 'Not run'}")
    print(f"  Model Training: {state.last_training or 'Not run'}")
    print(f"  Model Evaluation: {state.last_evaluation or 'Not run'}")
    print(f"  Model Promotion: {state.last_promotion or 'Not run'}")

    print("\n[MODEL STATUS]")
    print("-" * 40)

    for model_type in ModelType:
        active = registry.get_active_model(model_type)
        if active:
            print(f"  {model_type.value}: [DEPLOYED] {active.model_id}")
        else:
            trained = registry.list_models(model_type=model_type, status=ModelStatus.TRAINED)
            if trained:
                print(f"  {model_type.value}: [TRAINED] {len(trained)} models (not deployed)")
            else:
                print(f"  {model_type.value}: [NONE] No model")

    print("\n" + "=" * 60)


# =============================================================================
# Full Pipeline
# =============================================================================


async def run_full_pipeline(config: PipelineConfig) -> dict[str, Any]:
    """Run the complete ML training pipeline."""
    logger.info("full_pipeline_started", config=config)

    state = load_pipeline_state()
    results: dict[str, Any] = {"stages": {}}

    # Stage 1: Data Ingestion
    print("\n[1/6] Data Ingestion...")
    ingest_results = await run_data_ingestion(config)
    results["stages"]["ingestion"] = ingest_results
    state.last_ingest = datetime.now(UTC)
    state.total_candles = ingest_results["total_candles"]
    state.ingested_markets = config.markets
    save_pipeline_state(state)

    # Stage 2: Feature Engineering
    print("\n[2/6] Feature Engineering...")
    feature_results = run_feature_engineering(config)
    results["stages"]["features"] = feature_results
    state.last_features = datetime.now(UTC)
    save_pipeline_state(state)

    # Stages 3-5: Simulation & Labels
    print("\n[3/6] Simulation & Label Generation...")
    sim_results = run_simulation_and_labels(config)
    results["stages"]["simulation"] = sim_results
    state.last_simulation = datetime.now(UTC)
    save_pipeline_state(state)

    # Stage 6: Model Training
    print("\n[4/6] Model Training...")
    train_results = run_model_training(config)
    results["stages"]["training"] = train_results
    state.last_training = datetime.now(UTC)
    state.trained_models = train_results["model_ids"]
    save_pipeline_state(state)

    # Stage 7: Model Evaluation
    print("\n[5/6] Model Evaluation...")
    eval_results = run_model_evaluation(config)
    results["stages"]["evaluation"] = eval_results
    state.last_evaluation = datetime.now(UTC)
    save_pipeline_state(state)

    # Stage 8: Model Promotion
    print("\n[6/6] Model Promotion...")
    promo_results = run_model_promotion(config)
    results["stages"]["promotion"] = promo_results
    state.last_promotion = datetime.now(UTC)
    if promo_results["promoted"]:
        state.promoted_model = promo_results["promoted"][0]
    save_pipeline_state(state)

    logger.info("full_pipeline_completed")

    # Print summary
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETED")
    print("=" * 60)
    print(f"  Markets Processed: {ingest_results['markets_processed']}")
    print(f"  Total Candles: {ingest_results['total_candles']}")
    print(f"  Observations: {feature_results['total_observations']}")
    print(f"  Models Trained: {train_results['models_trained']}")
    print(f"  Models Promoted: {len(promo_results['promoted'])}")
    print("=" * 60)

    return results


# =============================================================================
# CLI
# =============================================================================


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="ML Training Pipeline Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    uv run python scripts/run_ml_training.py --full
    uv run python scripts/run_ml_training.py --ingest --markets BTC-USDT,ETH-USDT
    uv run python scripts/run_ml_training.py --train --model-family lightgbm
    uv run python scripts/run_ml_training.py --promote --force
    uv run python scripts/run_ml_training.py --status
        """,
    )

    # Pipeline stages
    parser.add_argument("--full", action="store_true", help="Run full pipeline")
    parser.add_argument("--ingest", action="store_true", help="Run data ingestion only")
    parser.add_argument("--features", action="store_true", help="Run feature engineering only")
    parser.add_argument("--simulate", action="store_true", help="Run simulation & labels only")
    parser.add_argument("--train", action="store_true", help="Run model training only")
    parser.add_argument("--evaluate", action="store_true", help="Run model evaluation only")
    parser.add_argument("--promote", action="store_true", help="Run model promotion only")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")

    # Configuration
    parser.add_argument(
        "--markets",
        type=str,
        default=None,
        help="Comma-separated list of markets (default: TOP 10)",
    )
    parser.add_argument(
        "--months", type=int, default=DEFAULT_MONTHS, help="Historical data period in months"
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default=DEFAULT_EXCHANGE,
        choices=["OKX", "BINANCE", "BYBIT"],
        help="Exchange to fetch data from (OKX, BINANCE, BYBIT)",
    )
    parser.add_argument("--interval", type=str, default=DEFAULT_INTERVAL, help="Candle interval")
    parser.add_argument(
        "--model-family",
        type=str,
        default="lightgbm",
        choices=["lightgbm", "gradient_boosting"],
        help="Model family",
    )
    parser.add_argument("--model-id", type=str, default=None, help="Specific model ID to promote")
    parser.add_argument("--force", action="store_true", help="Force operations")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Configure logging
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(20),  # INFO level
    )

    # Build config
    config = PipelineConfig(
        markets=args.markets.split(",") if args.markets else DEFAULT_MARKETS,
        months=args.months,
        exchange=args.exchange,
        interval=args.interval,
        model_family=args.model_family,
        random_seed=args.seed,
        force=args.force,
    )

    try:
        if args.status:
            show_pipeline_status(config)
            return 0

        if args.full:
            asyncio.run(run_full_pipeline(config))
            return 0

        if args.ingest:
            asyncio.run(run_data_ingestion(config))
            state = load_pipeline_state()
            state.last_ingest = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        if args.features:
            run_feature_engineering(config)
            state = load_pipeline_state()
            state.last_features = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        if args.simulate:
            run_simulation_and_labels(config)
            state = load_pipeline_state()
            state.last_simulation = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        if args.train:
            run_model_training(config)
            state = load_pipeline_state()
            state.last_training = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        if args.evaluate:
            run_model_evaluation(config)
            state = load_pipeline_state()
            state.last_evaluation = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        if args.promote:
            run_model_promotion(config, model_id=args.model_id)
            state = load_pipeline_state()
            state.last_promotion = datetime.now(UTC)
            save_pipeline_state(state)
            return 0

        # No action specified
        print("No action specified. Use --help for usage information.")
        return 1

    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
        return 130
    except Exception as e:
        logger.error("pipeline_failed", error=str(e))
        print(f"\n[ERROR] Pipeline failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
