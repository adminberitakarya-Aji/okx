"""
Admin API schemas.

This module provides schemas for admin dashboard endpoints:
- ML model status
- Training pipeline status
- Grid performance summary
- Alerts
- Data ingestion status

Authorization: SYSTEM_ADMIN (Level 5) only.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


# =============================================================================
# ML Model Status
# =============================================================================


class MLModelInfo(BaseModel):
    """Information about a single ML model."""

    model_id: str
    model_type: str
    status: str
    registered_at: datetime | None = None
    promoted_at: datetime | None = None
    train_metrics: dict[str, Any] = Field(default_factory=dict)
    validation_metrics: dict[str, Any] = Field(default_factory=dict)
    walk_forward_summary: dict[str, Any] = Field(default_factory=dict)


class MLModelStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/ml/status."""

    ml_available: bool = Field(description="Whether ML models are loaded")
    ranking_mode: str = Field(description="Current ranking mode (ml/heuristic)")
    models_loaded: int = Field(description="Number of models loaded")
    active_models: list[MLModelInfo] = Field(default_factory=list)
    last_ranking_at: datetime | None = None
    last_ranking_mode: str | None = None
    blueprints_generated: int = 0
    simulations_run: int = 0


# =============================================================================
# Training Pipeline Status
# =============================================================================


class TrainingStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/training/status."""

    last_training_at: datetime | None = None
    last_ingest_at: datetime | None = None
    last_features_at: datetime | None = None
    last_simulation_at: datetime | None = None
    last_evaluation_at: datetime | None = None
    last_promotion_at: datetime | None = None
    trained_models: list[str] = Field(default_factory=list)
    promoted_model: str | None = None
    dataset_observations: int = 0
    val_roc_auc: float | None = None
    walk_forward_mean_roc_auc: float | None = None
    notes: str | None = None
    pipeline_state_available: bool = False


class TrainingRunRequest(BaseModel):
    """Request to trigger a training run."""

    force: bool = Field(
        default=False,
        description="Force promotion even if metrics below threshold",
    )


class TrainingRunResponse(BaseModel):
    """Response for POST /api/v1/admin/training/run."""

    status: str = Field(description="Training run status (started/already_running)")
    message: str
    triggered_at: datetime
    task_id: str | None = None


# =============================================================================
# Grid Performance
# =============================================================================


class GridPerformanceSummary(BaseModel):
    """Summary of grid performance across all sessions."""

    total_sessions: int = 0
    active_sessions: int = 0
    stopped_sessions: int = 0
    total_orders_submitted: int = 0
    total_orders_filled: int = 0
    fill_rate_pct: Decimal = Decimal("0")
    avg_order_latency_ms: float = 0.0
    total_realized_pnl: Decimal = Decimal("0")
    total_unrealized_pnl: Decimal = Decimal("0")
    total_deployed_capital: Decimal = Decimal("0")
    error_count: int = 0
    error_rate_pct: Decimal = Decimal("0")
    emergency_stops: int = 0
    ws_reconnect_count: int = 0
    reconciliation_mismatches: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)


class GridPerformanceResponse(BaseModel):
    """Response for GET /api/v1/admin/performance/grids."""

    environment: str = "DEMO"
    summary: GridPerformanceSummary
    generated_at: datetime


# =============================================================================
# Alerts
# =============================================================================


class AdminAlertInfo(BaseModel):
    """Alert information for admin view."""

    alert_id: str
    rule_id: str
    severity: str
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    environment: str
    created_at: datetime
    acknowledged: bool = False
    acknowledged_at: datetime | None = None


class AdminAlertsResponse(BaseModel):
    """Response for GET /api/v1/admin/alerts."""

    environment: str
    system_healthy: bool
    total_alerts: int
    active_alerts: int
    critical_alerts: int
    alerts: list[AdminAlertInfo] = Field(default_factory=list)
    alert_rules_count: int = 0
    metrics_tracked: int = 0
    generated_at: datetime


# =============================================================================
# Ingestion Status
# =============================================================================


class IngestionStatusResponse(BaseModel):
    """Response for GET /api/v1/admin/ingestion/status."""

    last_ingest_at: datetime | None = None
    ingested_markets: list[str] = Field(default_factory=list)
    total_candles: int = 0
    candles_per_market: int = 0
    exchange: str | None = None
    interval: str | None = None
    data_freshness_hours: float | None = Field(
        default=None,
        description="Hours since last ingestion",
    )
    pipeline_state_available: bool = False


# =============================================================================
# Model Promotion
# =============================================================================


class ModelPromoteRequest(BaseModel):
    """Request to promote a model to deployment."""

    force: bool = Field(
        default=False,
        description="Force promotion even if metrics below threshold",
    )
    notes: str = Field(
        default="",
        max_length=500,
        description="Promotion notes for audit trail",
    )


class ModelPromoteResponse(BaseModel):
    """Response for POST /api/v1/admin/models/{model_id}/promote."""

    model_id: str
    success: bool
    issues: list[str] = Field(default_factory=list)
    message: str
    promoted_at: datetime | None = None


# =============================================================================
# ML Metrics
# =============================================================================


class MLMetricsResponse(BaseModel):
    """Response for GET /api/v1/admin/ml/metrics."""

    total_models: int = 0
    deployed_models: int = 0
    archived_models: int = 0
    trained_models: int = 0
    failed_models: int = 0
    models_by_type: dict[str, int] = Field(default_factory=dict)
    models_by_status: dict[str, int] = Field(default_factory=dict)
    avg_val_roc_auc: float | None = None
    best_val_roc_auc: float | None = None
    best_model_id: str | None = None
    generated_at: datetime


# =============================================================================
# Training History
# =============================================================================


class TrainingHistoryEntry(BaseModel):
    """A single training run entry."""

    run_id: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str = "unknown"
    models_trained: list[str] = Field(default_factory=list)
    val_roc_auc: float | None = None
    notes: str | None = None


class TrainingHistoryResponse(BaseModel):
    """Response for GET /api/v1/admin/training/history."""

    runs: list[TrainingHistoryEntry] = Field(default_factory=list)
    total_runs: int = 0
    generated_at: datetime


# =============================================================================
# Model List
# =============================================================================


class ModelListEntry(BaseModel):
    """A model entry in the admin model list."""

    model_id: str
    model_type: str
    model_family: str
    status: str
    registered_at: datetime | None = None
    promoted_at: datetime | None = None
    archived_at: datetime | None = None
    feature_version: str | None = None
    label_version: str | None = None
    dataset_version: str | None = None
    val_roc_auc: float | None = None
    train_samples: int = 0
    promotion_notes: str = ""


class ModelListResponse(BaseModel):
    """Response for GET /api/v1/admin/models."""

    models: list[ModelListEntry] = Field(default_factory=list)
    total: int = 0
    generated_at: datetime
