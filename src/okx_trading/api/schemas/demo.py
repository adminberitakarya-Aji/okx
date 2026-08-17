"""
Demo Trading API schemas.

This module provides schemas for:
- Demo grid session management
- Demo metrics and validation reports
- Monitoring dashboard and alerts
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class DemoMetricsResponse(BaseModel):
    """Demo operational metrics response."""

    orders_submitted: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    fill_rate_pct: str = "0"
    avg_order_latency_ms: float = 0.0
    ws_reconnect_count: int = 0
    reconciliation_count: int = 0
    reconciliation_mismatches: int = 0
    error_count: int = 0
    error_rate_pct: str = "0"
    errors_by_category: dict[str, int] = Field(default_factory=dict)
    grid_state_transitions: int = 0
    emergency_stops: int = 0
    pause_resume_cycles: int = 0
    started_at: str | None = None
    last_updated_at: str | None = None


class DemoSessionResponse(BaseModel):
    """Demo grid session response."""

    session_id: str
    grid_id: str
    market_id: str
    environment: Literal["DEMO", "LIVE"] = "DEMO"
    status: str
    created_at: datetime
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    duration_seconds: float | None = None
    notes: list[str] = Field(default_factory=list)
    metrics: DemoMetricsResponse | None = None


class DemoSessionListResponse(BaseModel):
    """List of demo sessions."""

    sessions: list[DemoSessionResponse] = Field(default_factory=list)
    total: int = 0
    active_count: int = 0


class DemoGridCreateRequest(BaseModel):
    """Request to create a demo grid."""

    blueprint_id: str = Field(..., description="Blueprint ID to execute")
    notes: str | None = Field(default=None, description="Optional session notes")


class DemoGridControlRequest(BaseModel):
    """Request for demo grid control operations."""

    reason: str | None = Field(default=None, description="Reason for the operation")


class DemoOrderRequest(BaseModel):
    """Request to execute a demo order."""

    market_id: str = Field(..., description="Market to trade")
    side: Literal["BUY", "SELL"] = Field(..., description="Order side")
    quantity: Decimal = Field(..., gt=0, description="Order quantity")
    price: Decimal | None = Field(default=None, gt=0, description="Limit price")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class DemoOrderResponse(BaseModel):
    """Demo order execution response."""

    success: bool
    order_id: str
    exchange_order_id: str | None = None
    error_message: str | None = None


class DemoValidationReportResponse(BaseModel):
    """Demo validation report response."""

    report_id: str
    period_start: datetime
    period_end: datetime
    sessions_count: int
    total_metrics: DemoMetricsResponse
    issues_found: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    ready_for_live: bool = False
    generated_at: datetime


class DemoServiceStatusResponse(BaseModel):
    """Demo trading service status response."""

    environment: Literal["DEMO", "LIVE"] = "DEMO"
    total_sessions: int = 0
    active_sessions: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    metrics: DemoMetricsResponse | None = None


class AlertResponse(BaseModel):
    """Alert response."""

    alert_id: str
    rule_id: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    environment: str = "DEMO"
    created_at: datetime
    acknowledged: bool = False
    acknowledged_at: datetime | None = None


class AlertListResponse(BaseModel):
    """List of alerts."""

    alerts: list[AlertResponse] = Field(default_factory=list)
    total: int = 0
    active_count: int = 0
    critical_count: int = 0


class AlertRuleResponse(BaseModel):
    """Alert rule response."""

    rule_id: str
    name: str
    metric_name: str
    threshold: float
    operator: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    cooldown_minutes: int
    enabled: bool


class AlertRuleCreateRequest(BaseModel):
    """Request to create an alert rule."""

    name: str = Field(..., description="Rule name")
    metric_name: str = Field(..., description="Metric to monitor")
    threshold: float = Field(..., description="Threshold value")
    operator: Literal["gt", "lt", "gte", "lte", "eq"] = Field(default="gt")
    severity: Literal["INFO", "WARNING", "CRITICAL"] = Field(default="WARNING")
    cooldown_minutes: int = Field(default=5, ge=1)


class HealthCheckResponse(BaseModel):
    """Health check response for a component."""

    component: str
    status: Literal["HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"]
    message: str = ""
    checked_at: datetime
    latency_ms: float = 0.0


class MonitoringDashboardResponse(BaseModel):
    """Monitoring dashboard response."""

    environment: str = "DEMO"
    system_healthy: bool = True
    health_checks: dict[str, HealthCheckResponse] = Field(default_factory=dict)
    active_alerts: list[AlertResponse] = Field(default_factory=list)
    critical_alerts: int = 0
    total_alerts: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    generated_at: datetime


class MonitoringSummaryResponse(BaseModel):
    """Monitoring summary response."""

    environment: str = "DEMO"
    system_healthy: bool = True
    active_alerts: int = 0
    critical_alerts: int = 0
    total_alerts: int = 0
    alert_rules: int = 0
    health_checks: int = 0
    metrics_tracked: int = 0


class EmergencyStopRequest(BaseModel):
    """Request for emergency stop."""

    reason: str = Field(..., min_length=1, description="Reason for emergency stop")


class EmergencyStopResponse(BaseModel):
    """Emergency stop response."""

    stopped_count: int
    session_ids: list[str] = Field(default_factory=list)
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
