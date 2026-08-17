"""
Tests for MonitoringService.

Tests cover:
- Alert rule evaluation
- Alert generation and acknowledgement
- Health check tracking
- Dashboard data generation
- System health assessment
"""

from datetime import UTC, datetime, timedelta

import pytest

from okx_trading.application.services.monitoring import (
    Alert,
    AlertRule,
    AlertSeverity,
    ComponentStatus,
    HealthCheck,
    MonitoringService,
)


class TestAlertRule:
    """Tests for AlertRule."""

    def test_evaluate_gt_operator(self) -> None:
        """Test greater-than operator evaluation."""
        rule = AlertRule(
            rule_id="TEST-001",
            name="Test Rule",
            metric_name="error_rate",
            threshold=5.0,
            operator="gt",
        )

        assert rule.evaluate(6.0) is True
        assert rule.evaluate(5.0) is False
        assert rule.evaluate(4.0) is False

    def test_evaluate_lt_operator(self) -> None:
        """Test less-than operator evaluation."""
        rule = AlertRule(
            rule_id="TEST-002",
            name="Test Rule",
            metric_name="fill_rate",
            threshold=50.0,
            operator="lt",
        )

        assert rule.evaluate(40.0) is True
        assert rule.evaluate(50.0) is False
        assert rule.evaluate(60.0) is False

    def test_evaluate_disabled_rule(self) -> None:
        """Test disabled rule never triggers."""
        rule = AlertRule(
            rule_id="TEST-003",
            name="Test Rule",
            metric_name="error_rate",
            threshold=5.0,
            operator="gt",
            enabled=False,
        )

        assert rule.evaluate(100.0) is False

    def test_evaluate_cooldown(self) -> None:
        """Test cooldown prevents repeated triggers."""
        rule = AlertRule(
            rule_id="TEST-004",
            name="Test Rule",
            metric_name="error_rate",
            threshold=5.0,
            operator="gt",
            cooldown_minutes=5,
        )

        # First evaluation triggers
        assert rule.evaluate(10.0) is True

        # Set last triggered to now
        rule.last_triggered_at = datetime.now(UTC)

        # Should not trigger again within cooldown
        assert rule.evaluate(10.0) is False

        # Set last triggered to past (beyond cooldown)
        rule.last_triggered_at = datetime.now(UTC) - timedelta(minutes=10)

        # Should trigger again
        assert rule.evaluate(10.0) is True

    def test_evaluate_unknown_operator(self) -> None:
        """Test unknown operator returns False."""
        rule = AlertRule(
            rule_id="TEST-005",
            name="Test Rule",
            metric_name="error_rate",
            threshold=5.0,
            operator="unknown",
        )

        assert rule.evaluate(10.0) is False


class TestAlert:
    """Tests for Alert."""

    def test_acknowledge(self) -> None:
        """Test alert acknowledgement."""
        alert = Alert(
            alert_id="ALERT-001",
            rule_id="RULE-001",
            severity=AlertSeverity.WARNING,
            message="Test alert",
            metric_name="error_rate",
            metric_value=10.0,
            threshold=5.0,
        )

        assert alert.acknowledged is False
        alert.acknowledge()
        assert alert.acknowledged is True
        assert alert.acknowledged_at is not None

    def test_to_dict(self) -> None:
        """Test alert serialization."""
        alert = Alert(
            alert_id="ALERT-002",
            rule_id="RULE-001",
            severity=AlertSeverity.CRITICAL,
            message="Test alert",
            metric_name="error_rate",
            metric_value=10.0,
            threshold=5.0,
            environment="DEMO",
        )

        data = alert.to_dict()
        assert data["alert_id"] == "ALERT-002"
        assert data["severity"] == "CRITICAL"
        assert data["environment"] == "DEMO"


class TestHealthCheck:
    """Tests for HealthCheck."""

    def test_to_dict(self) -> None:
        """Test health check serialization."""
        check = HealthCheck(
            component="okx_api",
            status=ComponentStatus.HEALTHY,
            message="API connected",
            latency_ms=150.0,
        )

        data = check.to_dict()
        assert data["component"] == "okx_api"
        assert data["status"] == "HEALTHY"
        assert data["latency_ms"] == 150.0


class TestMonitoringService:
    """Tests for MonitoringService."""

    @pytest.fixture
    def service(self) -> MonitoringService:
        """Create monitoring service for testing."""
        return MonitoringService(environment="DEMO")

    def test_environment_property(self, service: MonitoringService) -> None:
        """Test environment label."""
        assert service.environment == "DEMO"

    def test_default_rules_registered(self, service: MonitoringService) -> None:
        """Test default alert rules are registered."""
        rules = service.get_alert_rules()
        assert len(rules) >= 5

        rule_ids = [r.rule_id for r in rules]
        assert "RULE-ERR-RATE" in rule_ids
        assert "RULE-RECON-MISMATCH" in rule_ids

    def test_add_alert_rule(self, service: MonitoringService) -> None:
        """Test adding a custom alert rule."""
        rule = AlertRule(
            rule_id="CUSTOM-001",
            name="Custom Rule",
            metric_name="custom_metric",
            threshold=100.0,
        )

        service.add_alert_rule(rule)
        rules = service.get_alert_rules()

        assert any(r.rule_id == "CUSTOM-001" for r in rules)

    def test_remove_alert_rule(self, service: MonitoringService) -> None:
        """Test removing an alert rule."""
        assert service.remove_alert_rule("RULE-ERR-RATE") is True
        assert service.remove_alert_rule("NONEXISTENT") is False

    def test_update_metric_triggers_alert(self, service: MonitoringService) -> None:
        """Test metric update triggers alert."""
        alerts = service.update_metric("error_rate_pct", 10.0)

        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL
        assert alerts[0].metric_value == 10.0

    def test_update_metric_no_alert_below_threshold(self, service: MonitoringService) -> None:
        """Test metric below threshold does not trigger alert."""
        alerts = service.update_metric("error_rate_pct", 2.0)
        assert len(alerts) == 0

    def test_update_metrics_batch(self, service: MonitoringService) -> None:
        """Test batch metric update."""
        alerts = service.update_metrics(
            {
                "error_rate_pct": 10.0,
                "reconciliation_mismatches": 1.0,
            }
        )

        assert len(alerts) == 2

    def test_active_alerts(self, service: MonitoringService) -> None:
        """Test getting active (unacknowledged) alerts."""
        service.update_metric("error_rate_pct", 10.0)

        active = service.active_alerts
        assert len(active) == 1

    def test_acknowledge_alert(self, service: MonitoringService) -> None:
        """Test acknowledging an alert."""
        alerts = service.update_metric("error_rate_pct", 10.0)
        alert_id = alerts[0].alert_id

        acknowledged = service.acknowledge_alert(alert_id)
        assert acknowledged is not None
        assert acknowledged.acknowledged is True
        assert len(service.active_alerts) == 0

    def test_acknowledge_alert_not_found(self, service: MonitoringService) -> None:
        """Test acknowledging non-existent alert."""
        assert service.acknowledge_alert("NONEXISTENT") is None

    def test_acknowledge_all_alerts(self, service: MonitoringService) -> None:
        """Test acknowledging all alerts."""
        service.update_metrics(
            {
                "error_rate_pct": 10.0,
                "reconciliation_mismatches": 1.0,
            }
        )

        count = service.acknowledge_all_alerts()
        assert count == 2
        assert len(service.active_alerts) == 0

    def test_critical_alerts(self, service: MonitoringService) -> None:
        """Test getting critical alerts."""
        service.update_metric("error_rate_pct", 10.0)  # CRITICAL
        service.update_metric("ws_reconnect_count", 15.0)  # WARNING

        critical = service.critical_alerts
        assert len(critical) == 1
        assert critical[0].severity == AlertSeverity.CRITICAL

    def test_get_alerts_with_severity_filter(self, service: MonitoringService) -> None:
        """Test filtering alerts by severity."""
        service.update_metric("error_rate_pct", 10.0)  # CRITICAL
        service.update_metric("ws_reconnect_count", 15.0)  # WARNING

        critical = service.get_alerts(severity=AlertSeverity.CRITICAL)
        assert len(critical) == 1

        warnings = service.get_alerts(severity=AlertSeverity.WARNING)
        assert len(warnings) == 1

    def test_record_health_check(self, service: MonitoringService) -> None:
        """Test recording health check."""
        check = HealthCheck(
            component="okx_api",
            status=ComponentStatus.HEALTHY,
            message="Connected",
        )

        service.record_health_check(check)

        retrieved = service.get_component_health("okx_api")
        assert retrieved is not None
        assert retrieved.status == ComponentStatus.HEALTHY

    def test_is_system_healthy_all_healthy(self, service: MonitoringService) -> None:
        """Test system healthy when all components healthy."""
        service.record_health_check(
            HealthCheck(component="okx_api", status=ComponentStatus.HEALTHY)
        )
        service.record_health_check(
            HealthCheck(component="websocket", status=ComponentStatus.HEALTHY)
        )

        assert service.is_system_healthy() is True

    def test_is_system_healthy_with_unhealthy_component(self, service: MonitoringService) -> None:
        """Test system unhealthy when component is unhealthy."""
        service.record_health_check(
            HealthCheck(component="okx_api", status=ComponentStatus.UNHEALTHY)
        )

        assert service.is_system_healthy() is False

    def test_is_system_healthy_with_critical_alert(self, service: MonitoringService) -> None:
        """Test system unhealthy with critical alert."""
        service.record_health_check(
            HealthCheck(component="okx_api", status=ComponentStatus.HEALTHY)
        )
        service.update_metric("error_rate_pct", 10.0)

        assert service.is_system_healthy() is False

    def test_get_dashboard_data(self, service: MonitoringService) -> None:
        """Test dashboard data generation."""
        service.record_health_check(
            HealthCheck(component="okx_api", status=ComponentStatus.HEALTHY)
        )
        service.update_metric("error_rate_pct", 2.0)

        dashboard = service.get_dashboard_data()

        assert dashboard["environment"] == "DEMO"
        assert "system_healthy" in dashboard
        assert "health_checks" in dashboard
        assert "active_alerts" in dashboard
        assert "metrics" in dashboard
        assert dashboard["metrics"]["error_rate_pct"] == 2.0

    def test_get_monitoring_summary(self, service: MonitoringService) -> None:
        """Test monitoring summary."""
        service.update_metric("error_rate_pct", 10.0)

        summary = service.get_monitoring_summary()

        assert summary["environment"] == "DEMO"
        assert summary["total_alerts"] == 1
        assert summary["critical_alerts"] == 1
        assert summary["alert_rules"] >= 5

    def test_reconciliation_mismatch_alert(self, service: MonitoringService) -> None:
        """Test reconciliation mismatch triggers critical alert."""
        alerts = service.update_metric("reconciliation_mismatches", 1.0)

        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.CRITICAL

    def test_low_fill_rate_alert(self, service: MonitoringService) -> None:
        """Test low fill rate triggers warning."""
        alerts = service.update_metric("fill_rate_pct", 30.0)

        assert len(alerts) == 1
        assert alerts[0].severity == AlertSeverity.WARNING
