"""
Admin API routes.

Endpoints for admin dashboard: ML model status, training pipeline,
grid performance, alerts, and data ingestion status.

Authorization: SYSTEM_ADMIN (Level 5) only.

[Phase 12] Admin Dashboard — API-first implementation.
Telegram commands and Web UI will consume these endpoints.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from trading_grid.api.routes.dependencies import get_current_identity, get_default_container
from trading_grid.api.schemas.admin import (
    AdminAlertInfo,
    AdminAlertsResponse,
    GridPerformanceResponse,
    GridPerformanceSummary,
    IngestionStatusResponse,
    MLMetricsResponse,
    MLModelInfo,
    MLModelStatusResponse,
    ModelListEntry,
    ModelListResponse,
    ModelPromoteRequest,
    ModelPromoteResponse,
    TrainingHistoryEntry,
    TrainingHistoryResponse,
    TrainingRunRequest,
    TrainingRunResponse,
    TrainingStatusResponse,
)
from trading_grid.application.services.authorization import Identity, PermissionLevel

logger = structlog.get_logger()

router = APIRouter()

# Path to the ML pipeline state file (written by run_ml_training.py)
_PIPELINE_STATE_PATH = Path("data/pipeline_state.json")

# Background training task registry (prevents concurrent runs)
_training_tasks: dict[str, asyncio.Task[Any]] = {}


def require_system_admin(identity: Identity = Depends(get_current_identity)) -> Identity:
    """
    Dependency that enforces SYSTEM_ADMIN (Level 5) authorization.

    All admin endpoints MUST use this dependency. Deny-by-default:
    any role below SYSTEM_ADMIN receives 403.
    """
    if identity.permission_level < PermissionLevel.SYSTEM_ADMIN:
        logger.warning(
            "admin_access_denied",
            identity_id=identity.identity_id,
            permission_level=int(identity.permission_level),
            required_level=int(PermissionLevel.SYSTEM_ADMIN),
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: SYSTEM_ADMIN (Level 5) role required for admin endpoints",
        )
    return identity


def _load_pipeline_state() -> dict[str, Any] | None:
    """Load pipeline state from disk. Returns None if unavailable."""
    try:
        if _PIPELINE_STATE_PATH.exists():
            with _PIPELINE_STATE_PATH.open(encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("pipeline_state_load_failed", error=str(e))
    return None


def _parse_iso_datetime(value: Any) -> datetime | None:
    """Parse an ISO datetime string, returning None on failure."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# =============================================================================
# GET /ml/status — ML model status
# =============================================================================


@router.get("/ml/status", response_model=MLModelStatusResponse)
async def get_ml_status(
    identity: Identity = Depends(require_system_admin),
) -> MLModelStatusResponse:
    """
    Get ML model status.

    Returns active/deployed models, ranking mode, and research service state.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    service = container.research_service

    status = service.get_service_status()

    # Collect deployed models from registry
    active_models: list[MLModelInfo] = []
    try:
        from trading_grid.research.models.trainer import ModelStatus

        deployed_entries = service.registry.list_models(status=ModelStatus.DEPLOYED)
        for entry in deployed_entries:
            active_models.append(
                MLModelInfo(
                    model_id=entry.model_id,
                    model_type=entry.model_type.value,
                    status=entry.status.value,
                    registered_at=entry.registered_at,
                    promoted_at=entry.promoted_at,
                    train_metrics=entry.train_metrics,
                    validation_metrics=entry.validation_metrics,
                    walk_forward_summary=entry.walk_forward_summary,
                )
            )
    except Exception as e:
        logger.warning("ml_registry_read_failed", error=str(e))

    return MLModelStatusResponse(
        ml_available=status.get("ml_available", False),
        ranking_mode=status.get("last_ranking_mode")
        or ("ml" if status.get("ml_available") else "heuristic"),
        models_loaded=status.get("ml_models_loaded", 0),
        active_models=active_models,
        last_ranking_at=_parse_iso_datetime(status.get("last_ranking_at")),
        last_ranking_mode=status.get("last_ranking_mode"),
        blueprints_generated=status.get("blueprints_generated", 0),
        simulations_run=status.get("simulations_run", 0),
    )


# =============================================================================
# GET /training/status — Training pipeline status
# =============================================================================


@router.get("/training/status", response_model=TrainingStatusResponse)
async def get_training_status(
    identity: Identity = Depends(require_system_admin),
) -> TrainingStatusResponse:
    """
    Get training pipeline status.

    Reads pipeline state from data/pipeline_state.json (written by
    run_ml_training.py). Returns last run timestamps, metrics, and notes.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    state = await asyncio.to_thread(_load_pipeline_state)

    if state is None:
        return TrainingStatusResponse(pipeline_state_available=False)

    return TrainingStatusResponse(
        last_training_at=_parse_iso_datetime(state.get("last_training")),
        last_ingest_at=_parse_iso_datetime(state.get("last_ingest")),
        last_features_at=_parse_iso_datetime(state.get("last_features")),
        last_simulation_at=_parse_iso_datetime(state.get("last_simulation")),
        last_evaluation_at=_parse_iso_datetime(state.get("last_evaluation")),
        last_promotion_at=_parse_iso_datetime(state.get("last_promotion")),
        trained_models=state.get("trained_models", []),
        promoted_model=state.get("promoted_model"),
        dataset_observations=state.get("dataset_observations", 0),
        val_roc_auc=state.get("val_roc_auc"),
        walk_forward_mean_roc_auc=state.get("walk_forward_mean_roc_auc"),
        notes=state.get("notes"),
        pipeline_state_available=True,
    )


# =============================================================================
# POST /training/run — Trigger retraining
# =============================================================================


@router.post("/training/run", response_model=TrainingRunResponse, status_code=202)
async def trigger_training_run(
    request: TrainingRunRequest,
    identity: Identity = Depends(require_system_admin),
) -> TrainingRunResponse:
    """
    Trigger a background ML training run.

    Runs scripts/run_ml_training.py as a subprocess. The task is tracked
    to prevent concurrent runs. Returns 202 Accepted immediately.

    Authorization: SYSTEM_ADMIN (Level 5)
    Audit: All training triggers are logged with the actor identity.
    """
    # Prevent concurrent training runs
    running = [t for t in _training_tasks.values() if not t.done()]
    if running:
        return TrainingRunResponse(
            status="already_running",
            message="A training run is already in progress",
            triggered_at=datetime.now(UTC),
            task_id=None,
        )

    task_id = f"TRAIN-{uuid4().hex[:8].upper()}"

    # Build command
    cmd = [sys.executable, "scripts/run_ml_training.py"]
    if request.force:
        cmd.append("--force")

    async def _run_training() -> None:
        """Run training as a subprocess."""
        logger.info("admin_training_started", task_id=task_id, cmd=cmd)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            await proc.wait()
            if proc.returncode == 0:
                logger.info("admin_training_completed", task_id=task_id)
            else:
                logger.error(
                    "admin_training_failed",
                    task_id=task_id,
                    returncode=proc.returncode,
                )
        except Exception as e:
            logger.error("admin_training_error", task_id=task_id, error=str(e))

    task = asyncio.create_task(_run_training())
    _training_tasks[task_id] = task
    task.add_done_callback(lambda _t: _training_tasks.pop(task_id, None))

    # Audit log for sensitive operation
    logger.info(
        "admin_training_triggered",
        task_id=task_id,
        triggered_by=identity.identity_id,
        force=request.force,
    )

    return TrainingRunResponse(
        status="started",
        message=f"Training run started in background (task: {task_id})",
        triggered_at=datetime.now(UTC),
        task_id=task_id,
    )


# =============================================================================
# GET /performance/grids — Grid performance summary
# =============================================================================


@router.get("/performance/grids", response_model=GridPerformanceResponse)
async def get_grid_performance(
    identity: Identity = Depends(require_system_admin),
) -> GridPerformanceResponse:
    """
    Get grid performance summary across all demo sessions.

    Aggregates operational metrics (orders, fill rate, errors) and
    P&L (realized/unrealized) from all sessions.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    demo_service = container.demo_service

    sessions = demo_service.get_all_sessions()
    total_metrics = demo_service.get_all_metrics()

    # Aggregate P&L from grid runtimes
    total_realized = Decimal("0")
    total_unrealized = Decimal("0")
    total_deployed = Decimal("0")
    status_counts: dict[str, int] = {}
    active_count = 0
    stopped_count = 0

    for session in sessions:
        grid = session.grid_runtime
        total_realized += grid.realized_pnl
        total_unrealized += grid.unrealized_pnl
        total_deployed += grid.deployed_capital
        status_counts[session.status] = status_counts.get(session.status, 0) + 1
        if session.status in ("CREATED", "RUNNING", "PAUSED"):
            active_count += 1
        elif session.status in ("STOPPED", "EMERGENCY_STOPPED", "ERROR"):
            stopped_count += 1

    summary = GridPerformanceSummary(
        total_sessions=len(sessions),
        active_sessions=active_count,
        stopped_sessions=stopped_count,
        total_orders_submitted=total_metrics.orders_submitted,
        total_orders_filled=total_metrics.orders_filled,
        fill_rate_pct=total_metrics.fill_rate,
        avg_order_latency_ms=total_metrics.avg_order_latency_ms,
        total_realized_pnl=total_realized,
        total_unrealized_pnl=total_unrealized,
        total_deployed_capital=total_deployed,
        error_count=total_metrics.error_count,
        error_rate_pct=total_metrics.error_rate,
        emergency_stops=total_metrics.emergency_stops,
        ws_reconnect_count=total_metrics.ws_reconnect_count,
        reconciliation_mismatches=total_metrics.reconciliation_mismatches,
        status_counts=status_counts,
    )

    return GridPerformanceResponse(
        environment="DEMO",
        summary=summary,
        generated_at=datetime.now(UTC),
    )


# =============================================================================
# GET /alerts — Active alerts
# =============================================================================


@router.get("/alerts", response_model=AdminAlertsResponse)
async def get_admin_alerts(
    identity: Identity = Depends(require_system_admin),
) -> AdminAlertsResponse:
    """
    Get monitoring alerts and system health.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    monitoring = container.monitoring_service

    dashboard = monitoring.get_dashboard_data()
    summary = monitoring.get_monitoring_summary()

    alerts = [
        AdminAlertInfo(
            alert_id=a["alert_id"],
            rule_id=a["rule_id"],
            severity=a["severity"],
            message=a["message"],
            metric_name=a["metric_name"],
            metric_value=a["metric_value"],
            threshold=a["threshold"],
            environment=a["environment"],
            created_at=datetime.fromisoformat(a["created_at"]),
            acknowledged=a["acknowledged"],
            acknowledged_at=(
                datetime.fromisoformat(a["acknowledged_at"]) if a["acknowledged_at"] else None
            ),
        )
        for a in dashboard.get("active_alerts", [])
    ]

    return AdminAlertsResponse(
        environment=dashboard.get("environment", "DEMO"),
        system_healthy=dashboard.get("system_healthy", True),
        total_alerts=dashboard.get("total_alerts", 0),
        active_alerts=summary.get("active_alerts", 0),
        critical_alerts=dashboard.get("critical_alerts", 0),
        alerts=alerts,
        alert_rules_count=summary.get("alert_rules", 0),
        metrics_tracked=summary.get("metrics_tracked", 0),
        generated_at=datetime.now(UTC),
    )


# =============================================================================
# GET /ingestion/status — Data ingestion status
# =============================================================================


@router.get("/ingestion/status", response_model=IngestionStatusResponse)
async def get_ingestion_status(
    identity: Identity = Depends(require_system_admin),
) -> IngestionStatusResponse:
    """
    Get data ingestion status.

    Reads pipeline state to report last ingestion time, markets covered,
    and data freshness.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    state = await asyncio.to_thread(_load_pipeline_state)

    if state is None:
        return IngestionStatusResponse(pipeline_state_available=False)

    last_ingest = _parse_iso_datetime(state.get("last_ingest"))
    freshness_hours: float | None = None
    if last_ingest is not None:
        delta = datetime.now(UTC) - last_ingest
        freshness_hours = round(delta.total_seconds() / 3600, 2)

    return IngestionStatusResponse(
        last_ingest_at=last_ingest,
        ingested_markets=state.get("ingested_markets", []),
        total_candles=state.get("total_candles", 0),
        candles_per_market=state.get("candles_per_market", 0),
        exchange=state.get("exchange"),
        interval=state.get("interval"),
        data_freshness_hours=freshness_hours,
        pipeline_state_available=True,
    )


# =============================================================================
# POST /models/{model_id}/promote — Promote a model to deployment
# =============================================================================


@router.post("/models/{model_id}/promote", response_model=ModelPromoteResponse)
async def promote_model(
    model_id: str,
    request: ModelPromoteRequest,
    identity: Identity = Depends(require_system_admin),
) -> ModelPromoteResponse:
    """
    Promote a model to deployment (STAGING → DEPLOYED).

    Validates promotion criteria (ROC-AUC thresholds) unless force=True.
    Archives the currently deployed model of the same type.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    if container is None:
        raise HTTPException(status_code=503, detail="Service container not initialized")

    registry = container.research_service.registry
    if registry is None:
        raise HTTPException(status_code=503, detail="Model registry not available")

    # Check model exists
    entry = registry.get(model_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    # Promote
    success, issues = registry.promote(
        model_id=model_id,
        notes=request.notes,
        force=request.force,
    )

    # Audit log for sensitive operation
    logger.info(
        "admin_model_promotion",
        model_id=model_id,
        success=success,
        forced=request.force,
        issues=issues,
        actor=identity.identity_id,
    )

    if success:
        # Re-fetch to get promoted_at
        entry = registry.get(model_id)
        return ModelPromoteResponse(
            model_id=model_id,
            success=True,
            issues=issues,
            message=f"Model {model_id} promoted to DEPLOYED",
            promoted_at=entry.promoted_at if entry else None,
        )

    return ModelPromoteResponse(
        model_id=model_id,
        success=False,
        issues=issues,
        message=f"Promotion blocked: {'; '.join(issues)}",
        promoted_at=None,
    )


# =============================================================================
# GET /ml/metrics — ML model metrics summary
# =============================================================================


@router.get("/ml/metrics", response_model=MLMetricsResponse)
async def get_ml_metrics(
    identity: Identity = Depends(require_system_admin),
) -> MLMetricsResponse:
    """
    Get ML model metrics summary.

    Aggregates model counts by type/status, average and best ROC-AUC.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    if container is None:
        raise HTTPException(status_code=503, detail="Service container not initialized")

    registry = container.research_service.registry
    if registry is None:
        raise HTTPException(status_code=503, detail="Model registry not available")

    try:
        from trading_grid.research.models.trainer import ModelStatus

        all_models = registry.list_models()
    except Exception as e:
        logger.warning("ml_metrics_registry_read_failed", error=str(e))
        all_models = []

    total = len(all_models)
    deployed = 0
    archived = 0
    trained = 0
    failed = 0
    models_by_type: dict[str, int] = {}
    models_by_status: dict[str, int] = {}
    roc_aucs: list[float] = []

    for entry in all_models:
        # Count by type
        type_key = entry.model_type.value
        models_by_type[type_key] = models_by_type.get(type_key, 0) + 1

        # Count by status
        status_key = entry.status.value
        models_by_status[status_key] = models_by_status.get(status_key, 0) + 1

        # Status-specific counts
        if entry.status == ModelStatus.DEPLOYED:
            deployed += 1
        elif entry.status == ModelStatus.ARCHIVED:
            archived += 1
        elif entry.status == ModelStatus.TRAINED or entry.status == ModelStatus.VALIDATED:
            trained += 1
        elif entry.status == ModelStatus.FAILED:
            failed += 1

        # Collect ROC-AUC from validation metrics
        val_roc_auc = entry.validation_metrics.get("roc_auc")
        if val_roc_auc is not None:
            roc_aucs.append(float(val_roc_auc))

    avg_roc_auc = round(sum(roc_aucs) / len(roc_aucs), 4) if roc_aucs else None
    best_roc_auc = max(roc_aucs) if roc_aucs else None
    best_model_id = None
    if best_roc_auc is not None:
        for entry in all_models:
            val_roc_auc = entry.validation_metrics.get("roc_auc")
            if val_roc_auc is not None and float(val_roc_auc) == best_roc_auc:
                best_model_id = entry.model_id
                break

    return MLMetricsResponse(
        total_models=total,
        deployed_models=deployed,
        archived_models=archived,
        trained_models=trained,
        failed_models=failed,
        models_by_type=models_by_type,
        models_by_status=models_by_status,
        avg_val_roc_auc=avg_roc_auc,
        best_val_roc_auc=best_roc_auc,
        best_model_id=best_model_id,
        generated_at=datetime.now(UTC),
    )


# =============================================================================
# GET /training/history — Training run history
# =============================================================================


@router.get("/training/history", response_model=TrainingHistoryResponse)
async def get_training_history(
    identity: Identity = Depends(require_system_admin),
) -> TrainingHistoryResponse:
    """
    Get training run history.

    Reads pipeline state to report the most recent training run.
    Future: will read from a training_runs table once metrics storage
    is implemented (Task 8.3).

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    state = await asyncio.to_thread(_load_pipeline_state)

    runs: list[TrainingHistoryEntry] = []

    if state is not None:
        last_training = _parse_iso_datetime(state.get("last_training"))
        if last_training is not None:
            runs.append(
                TrainingHistoryEntry(
                    run_id="latest",
                    started_at=last_training,
                    completed_at=last_training,
                    status="completed",
                    models_trained=state.get("trained_models", []),
                    val_roc_auc=state.get("val_roc_auc"),
                    notes=state.get("notes"),
                )
            )

    return TrainingHistoryResponse(
        runs=runs,
        total_runs=len(runs),
        generated_at=datetime.now(UTC),
    )


# =============================================================================
# GET /models — List all models
# =============================================================================


@router.get("/models", response_model=ModelListResponse)
async def list_all_models(
    identity: Identity = Depends(require_system_admin),
) -> ModelListResponse:
    """
    List all registered models with metadata.

    Returns every model in the registry with its type, status, versions,
    and key metrics.

    Authorization: SYSTEM_ADMIN (Level 5)
    """
    container = get_default_container()
    if container is None:
        raise HTTPException(status_code=503, detail="Service container not initialized")

    registry = container.research_service.registry
    if registry is None:
        raise HTTPException(status_code=503, detail="Model registry not available")

    try:
        all_models = registry.list_models()
    except Exception as e:
        logger.warning("model_list_registry_read_failed", error=str(e))
        all_models = []

    models: list[ModelListEntry] = []
    for entry in all_models:
        models.append(
            ModelListEntry(
                model_id=entry.model_id,
                model_type=entry.model_type.value,
                model_family=entry.config.model_family.value,
                status=entry.status.value,
                registered_at=entry.registered_at,
                promoted_at=entry.promoted_at,
                archived_at=entry.archived_at,
                feature_version=entry.config.feature_version,
                label_version=entry.config.label_version,
                dataset_version=entry.config.dataset_version,
                val_roc_auc=entry.validation_metrics.get("roc_auc"),
                train_samples=entry.train_metrics.get("train_samples", 0),
                promotion_notes=entry.promotion_notes,
            )
        )

    return ModelListResponse(
        models=models,
        total=len(models),
        generated_at=datetime.now(UTC),
    )
