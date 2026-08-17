"""
Demo Trading API routes.

Endpoints for demo grid lifecycle management, metrics, and monitoring.

Note: Demo trading requires LEVEL 2+ authorization.
Demo environment is clearly labeled in all responses.
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException

from okx_trading.api.schemas.demo import (
    AlertListResponse,
    AlertResponse,
    AlertRuleCreateRequest,
    AlertRuleResponse,
    DemoGridControlRequest,
    DemoMetricsResponse,
    DemoOrderRequest,
    DemoOrderResponse,
    DemoServiceStatusResponse,
    DemoSessionListResponse,
    DemoSessionResponse,
    DemoValidationReportResponse,
    EmergencyStopRequest,
    EmergencyStopResponse,
    MonitoringDashboardResponse,
    MonitoringSummaryResponse,
)
from okx_trading.application.services.demo_trading import (
    DemoGridSession,
    DemoTradingError,
    DemoTradingService,
)
from okx_trading.application.services.monitoring import AlertRule, AlertSeverity, MonitoringService

logger = structlog.get_logger()

router = APIRouter()

# Service instances (in production, these would be injected via dependency injection)
_demo_service: DemoTradingService | None = None
_monitoring_service: MonitoringService | None = None


def get_demo_service() -> DemoTradingService:
    """Get demo trading service instance."""
    if _demo_service is None:
        raise HTTPException(
            status_code=503,
            detail="Demo trading service not initialized",
        )
    return _demo_service


def get_monitoring_service() -> MonitoringService:
    """Get monitoring service instance."""
    if _monitoring_service is None:
        raise HTTPException(
            status_code=503,
            detail="Monitoring service not initialized",
        )
    return _monitoring_service


def set_demo_service(service: DemoTradingService) -> None:
    """Set demo trading service instance (for initialization)."""
    global _demo_service
    _demo_service = service


def set_monitoring_service(service: MonitoringService) -> None:
    """Set monitoring service instance (for initialization)."""
    global _monitoring_service
    _monitoring_service = service


def _session_to_response(session: DemoGridSession) -> DemoSessionResponse:
    """Convert DemoGridSession to response schema."""
    metrics_data = session.metrics.to_dict()
    metrics = DemoMetricsResponse(**metrics_data)

    return DemoSessionResponse(
        session_id=session.session_id,
        grid_id=session.grid_runtime.grid_id,
        market_id=session.market_id,
        environment="DEMO",
        status=session.status,
        created_at=session.created_at,
        started_at=session.started_at,
        stopped_at=session.stopped_at,
        duration_seconds=session.duration_seconds,
        notes=session.notes,
        metrics=metrics,
    )


# =============================================================================
# Demo Session Management
# =============================================================================


@router.get("/sessions", response_model=DemoSessionListResponse)
async def list_demo_sessions() -> DemoSessionListResponse:
    """List all demo trading sessions."""
    service = get_demo_service()
    sessions = list(service._sessions.values())

    return DemoSessionListResponse(
        sessions=[_session_to_response(s) for s in sessions],
        total=len(sessions),
        active_count=len(service.active_sessions),
    )


@router.get("/sessions/{session_id}", response_model=DemoSessionResponse)
async def get_demo_session(session_id: str) -> DemoSessionResponse:
    """Get a specific demo session."""
    service = get_demo_service()
    session = service.get_session(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return _session_to_response(session)


@router.post("/sessions/{session_id}/start", response_model=DemoSessionResponse)
async def start_demo_session(session_id: str) -> DemoSessionResponse:
    """Start a demo grid session."""
    service = get_demo_service()

    try:
        session = await service.start_demo_grid(session_id)
        return _session_to_response(session)
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/sessions/{session_id}/pause", response_model=DemoSessionResponse)
async def pause_demo_session(session_id: str) -> DemoSessionResponse:
    """Pause a demo grid session."""
    service = get_demo_service()

    try:
        session = service.pause_demo_grid(session_id)
        return _session_to_response(session)
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/sessions/{session_id}/resume", response_model=DemoSessionResponse)
async def resume_demo_session(session_id: str) -> DemoSessionResponse:
    """Resume a paused demo grid session."""
    service = get_demo_service()

    try:
        session = service.resume_demo_grid(session_id)
        return _session_to_response(session)
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/sessions/{session_id}/stop", response_model=DemoSessionResponse)
async def stop_demo_session(
    session_id: str, request: DemoGridControlRequest | None = None
) -> DemoSessionResponse:
    """Stop a demo grid session."""
    service = get_demo_service()
    reason = request.reason if request and request.reason else "Manual stop via API"

    try:
        session = service.stop_demo_grid(session_id, reason=reason)
        return _session_to_response(session)
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/sessions/{session_id}/emergency-stop", response_model=DemoSessionResponse)
async def emergency_stop_demo_session(
    session_id: str, request: EmergencyStopRequest
) -> DemoSessionResponse:
    """Emergency stop a demo grid session."""
    service = get_demo_service()

    try:
        session = service.emergency_stop_demo_grid(session_id, reason=request.reason)
        return _session_to_response(session)
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


@router.post("/emergency-stop-all", response_model=EmergencyStopResponse)
async def emergency_stop_all_demo_sessions(request: EmergencyStopRequest) -> EmergencyStopResponse:
    """Emergency stop all active demo grid sessions."""
    service = get_demo_service()

    stopped = service.emergency_stop_all(reason=request.reason)

    return EmergencyStopResponse(
        stopped_count=len(stopped),
        session_ids=[s.session_id for s in stopped],
        reason=request.reason,
        timestamp=datetime.now(UTC),
    )


# =============================================================================
# Demo Orders
# =============================================================================


@router.post("/sessions/{session_id}/orders", response_model=DemoOrderResponse)
async def execute_demo_order(session_id: str, request: DemoOrderRequest) -> DemoOrderResponse:
    """Execute an order in a demo session."""
    service = get_demo_service()

    try:
        result = await service.execute_demo_order(
            session_id=session_id,
            market_id=request.market_id,
            side=request.side,
            quantity=request.quantity,
            price=request.price,
            metadata=request.metadata,
        )

        return DemoOrderResponse(
            success=result.success,
            order_id=result.order_id,
            exchange_order_id=result.exchange_order_id,
            error_message=result.error_message,
        )
    except DemoTradingError as e:
        raise HTTPException(status_code=400, detail=e.message) from e


# =============================================================================
# Demo Metrics and Reports
# =============================================================================


@router.get("/sessions/{session_id}/metrics", response_model=DemoMetricsResponse)
async def get_session_metrics(session_id: str) -> DemoMetricsResponse:
    """Get metrics for a specific demo session."""
    service = get_demo_service()
    metrics = service.get_session_metrics(session_id)

    if metrics is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    return DemoMetricsResponse(**metrics.to_dict())


@router.get("/metrics", response_model=DemoMetricsResponse)
async def get_all_demo_metrics() -> DemoMetricsResponse:
    """Get aggregated metrics from all demo sessions."""
    service = get_demo_service()
    metrics = service.get_all_metrics()

    return DemoMetricsResponse(**metrics.to_dict())


@router.get("/validation-report", response_model=DemoValidationReportResponse)
async def generate_validation_report() -> DemoValidationReportResponse:
    """Generate demo validation report for live trading readiness assessment."""
    service = get_demo_service()
    report = service.generate_validation_report()

    report_dict = report.to_dict()
    metrics = DemoMetricsResponse(**report.total_metrics.to_dict())

    return DemoValidationReportResponse(
        report_id=report.report_id,
        period_start=report.period_start,
        period_end=report.period_end,
        sessions_count=report_dict["sessions_count"],
        total_metrics=metrics,
        issues_found=report.issues_found,
        recommendations=report.recommendations,
        ready_for_live=report.ready_for_live,
        generated_at=report.generated_at,
    )


@router.get("/status", response_model=DemoServiceStatusResponse)
async def get_demo_service_status() -> DemoServiceStatusResponse:
    """Get demo trading service status."""
    service = get_demo_service()
    status = service.get_service_status()

    metrics = None
    if status.get("metrics"):
        metrics = DemoMetricsResponse(**status["metrics"])

    return DemoServiceStatusResponse(
        environment="DEMO",
        total_sessions=status.get("total_sessions", 0),
        active_sessions=status.get("active_sessions", 0),
        status_counts=status.get("status_counts", {}),
        metrics=metrics,
    )


# =============================================================================
# Monitoring Endpoints
# =============================================================================


@router.get("/monitoring/dashboard", response_model=MonitoringDashboardResponse)
async def get_monitoring_dashboard() -> MonitoringDashboardResponse:
    """Get monitoring dashboard data."""
    monitoring = get_monitoring_service()
    dashboard = monitoring.get_dashboard_data()

    # Convert health checks to response format
    health_checks = {}
    for component, check_data in dashboard.get("health_checks", {}).items():
        from okx_trading.api.schemas.demo import HealthCheckResponse

        health_checks[component] = HealthCheckResponse(
            component=check_data["component"],
            status=check_data["status"],
            message=check_data.get("message", ""),
            checked_at=datetime.fromisoformat(check_data["checked_at"]),
            latency_ms=check_data.get("latency_ms", 0.0),
        )

    # Convert alerts to response format
    active_alerts = []
    for alert_data in dashboard.get("active_alerts", []):
        active_alerts.append(
            AlertResponse(
                alert_id=alert_data["alert_id"],
                rule_id=alert_data["rule_id"],
                severity=alert_data["severity"],
                message=alert_data["message"],
                metric_name=alert_data["metric_name"],
                metric_value=alert_data["metric_value"],
                threshold=alert_data["threshold"],
                environment=alert_data.get("environment", "DEMO"),
                created_at=datetime.fromisoformat(alert_data["created_at"]),
                acknowledged=alert_data.get("acknowledged", False),
                acknowledged_at=(
                    datetime.fromisoformat(alert_data["acknowledged_at"])
                    if alert_data.get("acknowledged_at")
                    else None
                ),
            )
        )

    return MonitoringDashboardResponse(
        environment=dashboard.get("environment", "DEMO"),
        system_healthy=dashboard.get("system_healthy", True),
        health_checks=health_checks,
        active_alerts=active_alerts,
        critical_alerts=dashboard.get("critical_alerts", 0),
        total_alerts=dashboard.get("total_alerts", 0),
        metrics=dashboard.get("metrics", {}),
        generated_at=datetime.fromisoformat(dashboard["generated_at"]),
    )


@router.get("/monitoring/summary", response_model=MonitoringSummaryResponse)
async def get_monitoring_summary() -> MonitoringSummaryResponse:
    """Get monitoring summary."""
    monitoring = get_monitoring_service()
    summary = monitoring.get_monitoring_summary()

    return MonitoringSummaryResponse(**summary)


@router.get("/monitoring/alerts", response_model=AlertListResponse)
async def list_alerts(
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = 100,
) -> AlertListResponse:
    """List alerts with optional filtering."""
    monitoring = get_monitoring_service()

    severity_filter = None
    if severity:
        try:
            severity_filter = AlertSeverity(severity.upper())
        except ValueError as err:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}") from err

    alerts = monitoring.get_alerts(
        severity=severity_filter,
        acknowledged=acknowledged,
        limit=limit,
    )

    alert_responses = [
        AlertResponse(
            alert_id=a.alert_id,
            rule_id=a.rule_id,
            severity=a.severity.value,
            message=a.message,
            metric_name=a.metric_name,
            metric_value=a.metric_value,
            threshold=a.threshold,
            environment=a.environment,
            created_at=a.created_at,
            acknowledged=a.acknowledged,
            acknowledged_at=a.acknowledged_at,
        )
        for a in alerts
    ]

    return AlertListResponse(
        alerts=alert_responses,
        total=len(alerts),
        active_count=len(monitoring.active_alerts),
        critical_count=len(monitoring.critical_alerts),
    )


@router.post("/monitoring/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(alert_id: str) -> AlertResponse:
    """Acknowledge an alert."""
    monitoring = get_monitoring_service()
    alert = monitoring.acknowledge_alert(alert_id)

    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert not found: {alert_id}")

    return AlertResponse(
        alert_id=alert.alert_id,
        rule_id=alert.rule_id,
        severity=alert.severity.value,
        message=alert.message,
        metric_name=alert.metric_name,
        metric_value=alert.metric_value,
        threshold=alert.threshold,
        environment=alert.environment,
        created_at=alert.created_at,
        acknowledged=alert.acknowledged,
        acknowledged_at=alert.acknowledged_at,
    )


@router.post("/monitoring/alerts/acknowledge-all")
async def acknowledge_all_alerts() -> dict[str, int]:
    """Acknowledge all active alerts."""
    monitoring = get_monitoring_service()
    count = monitoring.acknowledge_all_alerts()
    return {"acknowledged_count": count}


@router.get("/monitoring/rules", response_model=list[AlertRuleResponse])
async def list_alert_rules() -> list[AlertRuleResponse]:
    """List all alert rules."""
    monitoring = get_monitoring_service()
    rules = monitoring.get_alert_rules()

    return [
        AlertRuleResponse(
            rule_id=r.rule_id,
            name=r.name,
            metric_name=r.metric_name,
            threshold=r.threshold,
            operator=r.operator,
            severity=r.severity.value,
            cooldown_minutes=r.cooldown_minutes,
            enabled=r.enabled,
        )
        for r in rules
    ]


@router.post("/monitoring/rules", response_model=AlertRuleResponse)
async def create_alert_rule(request: AlertRuleCreateRequest) -> AlertRuleResponse:
    """Create a new alert rule."""
    monitoring = get_monitoring_service()

    from uuid import uuid4

    rule = AlertRule(
        rule_id=f"RULE-{uuid4().hex[:8].upper()}",
        name=request.name,
        metric_name=request.metric_name,
        threshold=request.threshold,
        operator=request.operator,
        severity=AlertSeverity(request.severity),
        cooldown_minutes=request.cooldown_minutes,
    )

    monitoring.add_alert_rule(rule)

    return AlertRuleResponse(
        rule_id=rule.rule_id,
        name=rule.name,
        metric_name=rule.metric_name,
        threshold=rule.threshold,
        operator=rule.operator,
        severity=rule.severity.value,
        cooldown_minutes=rule.cooldown_minutes,
        enabled=rule.enabled,
    )


@router.delete("/monitoring/rules/{rule_id}")
async def delete_alert_rule(rule_id: str) -> dict[str, bool]:
    """Delete an alert rule."""
    monitoring = get_monitoring_service()
    deleted = monitoring.remove_alert_rule(rule_id)

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")

    return {"deleted": deleted}
