"""
Model Registry for AI Research Pipeline.

Implements model versioning per AI_RESEARCH_ML_MODEL_SPEC.md §17-21, §39-45.

Every registered model stores:
- model_id
- model_type, model_family
- feature_version
- label_version
- dataset_version
- simulator_version
- execution_model_version
- training metrics
- walk-forward results
- status lifecycle

Key principles:
- A model without recorded versions is not reproducible
- Promotion requires validation criteria
- Full audit trail
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from trading_grid.research.models.trainer import (
    ModelConfig,
    ModelFamily,
    ModelStatus,
    ModelType,
    TrainedModel,
)

logger = structlog.get_logger()

REGISTRY_VERSION = "registry-v001"


class PromotionCriteria(StrEnum):
    """Criteria for model promotion."""

    MIN_ROC_AUC = "min_roc_auc"
    MIN_WALK_FORWARD_ROC_AUC = "min_walk_forward_roc_auc"
    MAX_CALIBRATION_ERROR = "max_calibration_error"
    MIN_SAMPLES = "min_samples"


@dataclass
class RegistryEntry:
    """A model registry entry with full metadata."""

    model_id: str
    model_type: ModelType
    status: ModelStatus
    registered_at: datetime
    config: ModelConfig

    # Metrics
    train_metrics: dict[str, Any] = field(default_factory=dict)
    validation_metrics: dict[str, Any] = field(default_factory=dict)
    walk_forward_summary: dict[str, Any] = field(default_factory=dict)

    # Promotion tracking
    promoted_at: datetime | None = None
    archived_at: datetime | None = None
    promotion_notes: str = ""

    # Lineage
    parent_model_id: str | None = None
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "status": self.status.value,
            "registered_at": self.registered_at.isoformat(),
            "config": self.config.to_dict(),
            "train_metrics": self.train_metrics,
            "validation_metrics": self.validation_metrics,
            "walk_forward_summary": self.walk_forward_summary,
            "promoted_at": self.promoted_at.isoformat() if self.promoted_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "promotion_notes": self.promotion_notes,
            "parent_model_id": self.parent_model_id,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegistryEntry:
        config = ModelConfig(
            model_type=ModelType(data["config"]["model_type"]),
            model_family=ModelFamily(data["config"]["model_family"]),
            feature_version=data["config"]["feature_version"],
            label_version=data["config"]["label_version"],
            dataset_version=data["config"]["dataset_version"],
            simulator_version=data["config"]["simulator_version"],
            execution_model_version=data["config"]["execution_model_version"],
            horizon=data["config"]["horizon"],
            hyperparameters=data["config"].get("hyperparameters", {}),
            random_seed=data["config"].get("random_seed", 42),
            calibration_enabled=data["config"].get("calibration_enabled", True),
        )
        return cls(
            model_id=data["model_id"],
            model_type=ModelType(data["model_type"]),
            status=ModelStatus(data["status"]),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            config=config,
            train_metrics=data.get("train_metrics", {}),
            validation_metrics=data.get("validation_metrics", {}),
            walk_forward_summary=data.get("walk_forward_summary", {}),
            promoted_at=(
                datetime.fromisoformat(data["promoted_at"]) if data.get("promoted_at") else None
            ),
            archived_at=(
                datetime.fromisoformat(data["archived_at"]) if data.get("archived_at") else None
            ),
            promotion_notes=data.get("promotion_notes", ""),
            parent_model_id=data.get("parent_model_id"),
            tags=data.get("tags", []),
        )


@dataclass
class PromotionThresholds:
    """Thresholds for model promotion to deployment."""

    min_roc_auc: float = 0.60
    min_walk_forward_roc_auc: float = 0.55
    max_calibration_error: float = 0.10
    min_train_samples: int = 1000
    min_validation_samples: int = 200

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_roc_auc": self.min_roc_auc,
            "min_walk_forward_roc_auc": self.min_walk_forward_roc_auc,
            "max_calibration_error": self.max_calibration_error,
            "min_train_samples": self.min_train_samples,
            "min_validation_samples": self.min_validation_samples,
        }


class ModelRegistry:
    """
    Registry for model versioning and lifecycle management.

    Usage:
        registry = ModelRegistry("models/registry")
        registry.register(trained_model)
        registry.promote(model_id, notes="Passed walk-forward validation")
    """

    def __init__(self, registry_dir: Path | str = "models/registry") -> None:
        self.registry_dir = Path(registry_dir)
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.registry_dir / "index.json"
        self._entries: dict[str, RegistryEntry] = {}
        self._load_index()

    def register(
        self,
        trained_model: TrainedModel,
        parent_model_id: str | None = None,
        tags: list[str] | None = None,
    ) -> RegistryEntry:
        """Register a trained model."""
        entry = RegistryEntry(
            model_id=trained_model.model_id,
            model_type=trained_model.config.model_type,
            status=trained_model.status,
            registered_at=datetime.now(UTC),
            config=trained_model.config,
            train_metrics=(
                trained_model.train_metrics.to_dict() if trained_model.train_metrics else {}
            ),
            validation_metrics=(
                trained_model.validation_metrics.to_dict()
                if trained_model.validation_metrics
                else {}
            ),
            walk_forward_summary=(
                trained_model.walk_forward_result.to_dict()
                if trained_model.walk_forward_result
                else {}
            ),
            parent_model_id=parent_model_id,
            tags=tags or [],
        )

        self._entries[entry.model_id] = entry
        self._save_index()

        logger.info(
            "model_registered",
            model_id=entry.model_id,
            model_type=entry.model_type.value,
            status=entry.status.value,
        )

        return entry

    def get(self, model_id: str) -> RegistryEntry | None:
        """Get registry entry by model ID."""
        return self._entries.get(model_id)

    def list_models(
        self,
        model_type: ModelType | None = None,
        status: ModelStatus | None = None,
    ) -> list[RegistryEntry]:
        """List models with optional filtering."""
        entries = list(self._entries.values())

        if model_type is not None:
            entries = [e for e in entries if e.model_type == model_type]

        if status is not None:
            entries = [e for e in entries if e.status == status]

        return sorted(entries, key=lambda e: e.registered_at, reverse=True)

    def get_active_model(self, model_type: ModelType) -> RegistryEntry | None:
        """Get the currently deployed model for a type."""
        deployed = [
            e
            for e in self._entries.values()
            if e.model_type == model_type and e.status == ModelStatus.DEPLOYED
        ]
        if not deployed:
            return None
        return max(deployed, key=lambda e: e.promoted_at or e.registered_at)

    def promote(
        self,
        model_id: str,
        thresholds: PromotionThresholds | None = None,
        notes: str = "",
        force: bool = False,
    ) -> tuple[bool, list[str]]:
        """
        Promote a model to deployment.

        Returns:
            (success, list of issues)
        """
        entry = self._entries.get(model_id)
        if entry is None:
            return False, [f"Model {model_id} not found"]

        if thresholds is None:
            thresholds = PromotionThresholds()

        # Validate promotion criteria
        issues = self._validate_promotion(entry, thresholds)

        if issues and not force:
            logger.warning(
                "model_promotion_blocked",
                model_id=model_id,
                issues=issues,
            )
            return False, issues

        # Archive currently deployed model of same type
        current = self.get_active_model(entry.model_type)
        if current is not None and current.model_id != model_id:
            current.status = ModelStatus.ARCHIVED
            current.archived_at = datetime.now(UTC)

        # Promote
        entry.status = ModelStatus.DEPLOYED
        entry.promoted_at = datetime.now(UTC)
        entry.promotion_notes = notes

        self._save_index()

        logger.info(
            "model_promoted",
            model_id=model_id,
            model_type=entry.model_type.value,
            forced=force,
        )

        return True, issues

    def archive(self, model_id: str, reason: str = "") -> bool:
        """Archive a model."""
        entry = self._entries.get(model_id)
        if entry is None:
            return False

        entry.status = ModelStatus.ARCHIVED
        entry.archived_at = datetime.now(UTC)
        if reason:
            entry.promotion_notes += f" | Archived: {reason}"

        self._save_index()
        logger.info("model_archived", model_id=model_id)
        return True

    def compare_models(self, model_id_a: str, model_id_b: str) -> dict[str, Any] | None:
        """Compare two models' metrics."""
        entry_a = self._entries.get(model_id_a)
        entry_b = self._entries.get(model_id_b)

        if entry_a is None or entry_b is None:
            return None

        return {
            "model_a": {
                "model_id": model_id_a,
                "train_metrics": entry_a.train_metrics,
                "validation_metrics": entry_a.validation_metrics,
                "walk_forward_summary": entry_a.walk_forward_summary,
            },
            "model_b": {
                "model_id": model_id_b,
                "train_metrics": entry_b.train_metrics,
                "validation_metrics": entry_b.validation_metrics,
                "walk_forward_summary": entry_b.walk_forward_summary,
            },
            "version_diff": {
                "feature_version": (
                    entry_a.config.feature_version != entry_b.config.feature_version
                ),
                "label_version": (entry_a.config.label_version != entry_b.config.label_version),
                "dataset_version": (
                    entry_a.config.dataset_version != entry_b.config.dataset_version
                ),
            },
        }

    def _validate_promotion(
        self, entry: RegistryEntry, thresholds: PromotionThresholds
    ) -> list[str]:
        """Validate promotion criteria."""
        issues: list[str] = []

        # Check training samples
        train_samples = entry.train_metrics.get("train_samples", 0)
        if train_samples < thresholds.min_train_samples:
            issues.append(
                f"Insufficient training samples: {train_samples} < {thresholds.min_train_samples}"
            )

        # Check ROC AUC for classifiers
        if entry.model_type in (
            ModelType.PRIMARY_CLASSIFIER,
            ModelType.RECOVERY_CLASSIFIER,
            ModelType.CAPITAL_EXHAUSTION_CLASSIFIER,
        ):
            val_roc_auc = entry.validation_metrics.get("roc_auc")
            if val_roc_auc is not None and val_roc_auc < thresholds.min_roc_auc:
                issues.append(
                    f"Validation ROC AUC too low: {val_roc_auc:.3f} < {thresholds.min_roc_auc}"
                )

            wf_roc_auc = entry.walk_forward_summary.get("mean_roc_auc")
            if wf_roc_auc is not None and wf_roc_auc < thresholds.min_walk_forward_roc_auc:
                issues.append(
                    f"Walk-forward ROC AUC too low: {wf_roc_auc:.3f} < {thresholds.min_walk_forward_roc_auc}"
                )

        return issues

    def _load_index(self) -> None:
        """Load registry index from disk."""
        if not self.index_path.exists():
            return

        try:
            with self.index_path.open() as f:
                data = json.load(f)

            for entry_data in data.get("entries", []):
                entry = RegistryEntry.from_dict(entry_data)
                self._entries[entry.model_id] = entry

            logger.debug("registry_loaded", num_entries=len(self._entries))
        except Exception as e:
            logger.error("registry_load_failed", error=str(e))

    def _save_index(self) -> None:
        """Save registry index to disk."""
        data = {
            "registry_version": REGISTRY_VERSION,
            "updated_at": datetime.now(UTC).isoformat(),
            "entries": [entry.to_dict() for entry in self._entries.values()],
        }

        with self.index_path.open("w") as f:
            json.dump(data, f, indent=2)
