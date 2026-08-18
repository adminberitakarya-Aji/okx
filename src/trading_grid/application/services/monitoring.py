"""
Monitoring Service — Health checks, alerts, and metrics.

This module provides:
- MonitoringService: System health monitoring and alerting
- AlertRule: Configurable alert thresholds
- Alert: Alert instances with severity levels
- HealthCheck: Component health status tracking

Key domain rules:
1. All alerts are logged and can be routed to Telegram
2. Health checks cover API, WebSocket, reconciliation, and grid engine
3. Alert thresholds are configurable
4. Demo environment is clearly labeled in all monitoring output
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from collections.abc import Callable

import structlog

logger = structlog.get_logger()


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ComponentStatus(StrEnum):
    """Health status of a system component."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class AlertRule:
    """
    Configurable alert rule.

    Attributes:
        rule_id: Unique rule identifier
        name: Human-readable rule name
        metric_name: Metric to monitor
        threshold: Threshold value
        operator: Comparison operator (gt, lt, gte, lte, eq)
        severity: Alert severity when triggered
        cooldown_minutes: Minimum minutes between alerts
        enabled: Whether rule is active
    """

    rule_id: str
    name: str
    metric_name: str
    threshold: float
    operator: str = "gt"
    severity: AlertSeverity = AlertSeverity.WARNING
    cooldown_minutes: int = 5
    enabled: bool = True
    last_triggered_at: datetime | None = None

    def evaluate(self, value: float) -> bool:
        """
        Evaluate if the rule is triggered.

        Args:
            value: Current metric value

        Returns:
            True if alert should be triggered
        """
        if not self.enabled:
            return False

        # Check cooldown
        if self.last_triggered_at is not None:
            elapsed = datetime.now(UTC) - self.last_triggered_at
            if elapsed < timedelta(minutes=self.cooldown_minutes):
                return False

        operators: dict[str, Callable[[float, float], bool]] = {
            "gt": lambda v, t: v > t,
            "lt": lambda v, t: v < t,
            "gte": lambda v, t: v >= t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: v == t,
        }

        op_func = operators.get(self.operator)
        if op_func is None:
            logger.warning("unknown_alert_operator", operator=self.operator)
            return False

        return bool(op_func(value, self.threshold))


@dataclass
class Alert:
    """
    Alert instance.

    Attributes:
        alert_id: Unique alert identifier
        rule_id: Rule that triggered the alert
        severity: Alert severity
        message: Alert message
        metric_name: Metric that triggered the alert
        metric_value: Value at trigger time
        threshold: Rule threshold
        environment: Execution environment (DEMO/LIVE)
        created_at: Alert creation timestamp
        acknowledged: Whether alert has been acknowledged
        acknowledged_at: Acknowledgement timestamp
    """

    alert_id: str
    rule_id: str
    severity: AlertSeverity
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    environment: str = "DEMO"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    acknowledged_at: datetime | None = None

    def acknowledge(self) -> None:
        """Acknowledge the alert."""
        self.acknowledged = True
        self.acknowledged_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "environment": self.environment,
            "created_at": self.created_at.isoformat(),
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


@dataclass
class HealthCheck:
    """
    Health check result for a component.

    Attributes:
        component: Component name
        status: Health status
        message: Status message
        checked_at: Check timestamp
        latency_ms: Check latency
    """

    component: str
    status: ComponentStatus
    message: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert health check to dictionary."""
        return {
            "component": self.component,
            "status": self.status.value,
            "message": self.message,
            "checked_at": self.checked_at.isoformat(),
            "latency_ms": self.latency_ms,
        }


class MonitoringService:
    """
    Monitoring Service for system health and alerting.

    Responsibilities:
    - Track component health status
    - Evaluate alert rules against metrics
    - Generate and store alerts
    - Provide health dashboard data
    """

    def __init__(self, environment: str = "DEMO") -> None:
        """
        Initialize monitoring service.

        Args:
            environment: Execution environment label
        """
        self._environment = environment
        self._alert_rules: dict[str, AlertRule] = {}
        self._alerts: deque[Alert] = deque(maxlen=1000)
        self._health_checks: dict[str, HealthCheck] = {}
        self._metrics: dict[str, float] = {}

        # Register default alert rules
        self._register_default_rules()

    @property
    def environment(self) -> str:
        """Get environment label."""
        return self._environment

    @property
    def active_alerts(self) -> list[Alert]:
        """Get unacknowledged alerts."""
        return [a for a in self._alerts if not a.acknowledged]

    @property
    def critical_alerts(self) -> list[Alert]:
        """Get unacknowledged critical alerts."""
        return [
            a for a in self._alerts if not a.acknowledged and a.severity == AlertSeverity.CRITICAL
        ]

    def _register_default_rules(self) -> None:
        """Register default alert rules."""
        default_rules = [
            AlertRule(
                rule_id="RULE-ERR-RATE",
                name="High Error Rate",
                metric_name="error_rate_pct",
                threshold=5.0,
                operator="gt",
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=5,
            ),
            AlertRule(
                rule_id="RULE-RECON-MISMATCH",
                name="Reconciliation Mismatch",
                metric_name="reconciliation_mismatches",
                threshold=0.0,
                operator="gt",
                severity=AlertSeverity.CRITICAL,
                cooldown_minutes=1,
            ),
            AlertRule(
                rule_id="RULE-WS-RECONNECT",
                name="Frequent WebSocket Reconnects",
                metric_name="ws_reconnect_count",
                threshold=10.0,
                operator="gt",
                severity=AlertSeverity.WARNING,
                cooldown_minutes=10,
            ),
            AlertRule(
                rule_id="RULE-LATENCY",
                name="High Order Latency",
                metric_name="avg_order_latency_ms",
                threshold=5000.0,
                operator="gt",
                severity=AlertSeverity.WARNING,
                cooldown_minutes=5,
            ),
            AlertRule(
                rule_id="RULE-FILL-RATE",
                name="Low Fill Rate",
                metric_name="fill_rate_pct",
                threshold=50.0,
                operator="lt",
                severity=AlertSeverity.WARNING,
                cooldown_minutes=15,
            ),
        ]

        for rule in default_rules:
            self._alert_rules[rule.rule_id] = rule

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add or update an alert rule."""
        self._alert_rules[rule.rule_id] = rule
        logger.info("alert_rule_added", rule_id=rule.rule_id, name=rule.name)

    def remove_alert_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        if rule_id in self._alert_rules:
            del self._alert_rules[rule_id]
            logger.info("alert_rule_removed", rule_id=rule_id)
            return True
        return False

    def get_alert_rules(self) -> list[AlertRule]:
        """Get all alert rules."""
        return list(self._alert_rules.values())

    def update_metric(self, metric_name: str, value: float) -> list[Alert]:
        """
        Update a metric value and evaluate alert rules.

        Args:
            metric_name: Metric name
            value: Metric value

        Returns:
            List of triggered alerts
        """
        self._metrics[metric_name] = value
        triggered_alerts = []

        for rule in self._alert_rules.values():
            if rule.metric_name != metric_name:
                continue

            if rule.evaluate(value):
                alert = self._create_alert(rule, value)
                triggered_alerts.append(alert)
                rule.last_triggered_at = datetime.now(UTC)

                logger.warning(
                    "alert_triggered",
                    alert_id=alert.alert_id,
                    rule_id=rule.rule_id,
                    severity=alert.severity.value,
                    metric_name=metric_name,
                    metric_value=value,
                    threshold=rule.threshold,
                    environment=self._environment,
                )

        return triggered_alerts

    def update_metrics(self, metrics: dict[str, float]) -> list[Alert]:
        """
        Update multiple metrics and evaluate alert rules.

        Args:
            metrics: Dictionary of metric names to values

        Returns:
            List of triggered alerts
        """
        all_alerts = []
        for name, value in metrics.items():
            alerts = self.update_metric(name, value)
            all_alerts.extend(alerts)
        return all_alerts

    def _create_alert(self, rule: AlertRule, value: float) -> Alert:
        """Create an alert from a triggered rule."""
        alert = Alert(
            alert_id=f"ALERT-{uuid4().hex[:12].upper()}",
            rule_id=rule.rule_id,
            severity=rule.severity,
            message=f"{rule.name}: {rule.metric_name} = {value} (threshold: {rule.threshold})",
            metric_name=rule.metric_name,
            metric_value=value,
            threshold=rule.threshold,
            environment=self._environment,
        )
        self._alerts.append(alert)
        return alert

    def acknowledge_alert(self, alert_id: str) -> Alert | None:
        """Acknowledge an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledge()
                logger.info("alert_acknowledged", alert_id=alert_id)
                return alert
        return None

    def acknowledge_all_alerts(self) -> int:
        """Acknowledge all active alerts."""
        count = 0
        for alert in self._alerts:
            if not alert.acknowledged:
                alert.acknowledge()
                count += 1
        logger.info("all_alerts_acknowledged", count=count)
        return count

    def get_alerts(
        self,
        severity: AlertSeverity | None = None,
        acknowledged: bool | None = None,
        limit: int = 100,
    ) -> list[Alert]:
        """
        Get alerts with optional filtering.

        Args:
            severity: Filter by severity
            acknowledged: Filter by acknowledgement status
            limit: Maximum number of alerts to return

        Returns:
            List of alerts
        """
        alerts = self._alerts

        if severity is not None:
            alerts = [a for a in alerts if a.severity == severity]

        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]

        return alerts[-limit:]

    def record_health_check(self, health_check: HealthCheck) -> None:
        """Record a health check result."""
        self._health_checks[health_check.component] = health_check

        if health_check.status == ComponentStatus.UNHEALTHY:
            logger.error(
                "component_unhealthy",
                component=health_check.component,
                message=health_check.message,
                environment=self._environment,
            )
        elif health_check.status == ComponentStatus.DEGRADED:
            logger.warning(
                "component_degraded",
                component=health_check.component,
                message=health_check.message,
                environment=self._environment,
            )

    def get_health_status(self) -> dict[str, HealthCheck]:
        """Get current health status for all components."""
        return dict(self._health_checks)

    def get_component_health(self, component: str) -> HealthCheck | None:
        """Get health status for a specific component."""
        return self._health_checks.get(component)

    def is_system_healthy(self) -> bool:
        """Check if all components are healthy."""
        for check in self._health_checks.values():
            if check.status in (ComponentStatus.UNHEALTHY, ComponentStatus.UNKNOWN):
                return False
        return len(self.critical_alerts) == 0

    def get_dashboard_data(self) -> dict[str, Any]:
        """
        Get dashboard data for monitoring UI.

        Returns:
            Complete dashboard data including health, alerts, and metrics
        """
        health_status = {
            component: check.to_dict() for component, check in self._health_checks.items()
        }

        return {
            "environment": self._environment,
            "system_healthy": self.is_system_healthy(),
            "health_checks": health_status,
            "active_alerts": [a.to_dict() for a in self.active_alerts],
            "critical_alerts": len(self.critical_alerts),
            "total_alerts": len(self._alerts),
            "metrics": dict(self._metrics),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def get_monitoring_summary(self) -> dict[str, Any]:
        """Get monitoring summary."""
        return {
            "environment": self._environment,
            "system_healthy": self.is_system_healthy(),
            "active_alerts": len(self.active_alerts),
            "critical_alerts": len(self.critical_alerts),
            "total_alerts": len(self._alerts),
            "alert_rules": len(self._alert_rules),
            "health_checks": len(self._health_checks),
            "metrics_tracked": len(self._metrics),
        }
