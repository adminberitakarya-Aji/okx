"""Tests for audit service."""

from okx_trading.application.services.audit import (
    SENSITIVE_KEYS,
    AuditRecord,
    AuditService,
)


class TestAuditRecord:
    """Tests for AuditRecord."""

    def test_create_record(self):
        """Should create an audit record."""
        from datetime import UTC, datetime

        record = AuditRecord(
            audit_id="AUD-123",
            timestamp=datetime.now(UTC),
            actor_id="user",
            actor_type="HUMAN",
            action="START_GRID",
            resource="grid",
            result="SUCCESS",
        )
        assert record.audit_id == "AUD-123"
        assert record.actor_id == "user"
        assert record.actor_type == "HUMAN"
        assert record.result == "SUCCESS"

    def test_record_frozen(self):
        """AuditRecord should be immutable."""
        from datetime import UTC, datetime

        import pytest

        record = AuditRecord(
            audit_id="AUD-123",
            timestamp=datetime.now(UTC),
            actor_id="user",
            actor_type="HUMAN",
            action="START_GRID",
            resource="grid",
            result="SUCCESS",
        )
        with pytest.raises(AttributeError):
            record.result = "ERROR"  # type: ignore[misc]


class TestAuditService:
    """Tests for AuditService."""

    def test_record(self):
        """Should create and store audit record."""
        service = AuditService()
        record = service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="START_GRID",
            resource="grid",
            result="SUCCESS",
            resource_id="grid-123",
            environment="DEMO",
            correlation_id="corr-123",
            operation_id="op-123",
        )
        assert record.audit_id.startswith("AUD-")
        assert record.actor_id == "user"
        assert record.result == "SUCCESS"
        assert service.record_count == 1

    def test_record_success(self):
        """record_success should create SUCCESS record."""
        service = AuditService()
        record = service.record_success(
            actor_id="user",
            actor_type="HUMAN",
            action="START_GRID",
            resource="grid",
        )
        assert record.result == "SUCCESS"

    def test_record_denied(self):
        """record_denied should create DENIED record with reason."""
        service = AuditService()
        record = service.record_denied(
            actor_id="user",
            actor_type="HUMAN",
            action="START_LIVE_GRID",
            resource="grid",
            reason="Insufficient permissions",
        )
        assert record.result == "DENIED"
        assert record.error_message == "Insufficient permissions"

    def test_record_error(self):
        """record_error should create ERROR record."""
        service = AuditService()
        record = service.record_error(
            actor_id="service",
            actor_type="SERVICE",
            action="EXECUTE_ORDER",
            resource="order",
            error_message="Order rejected",
        )
        assert record.result == "ERROR"
        assert record.error_message == "Order rejected"

    def test_get_records_all(self):
        """Should return all records newest first."""
        service = AuditService()
        service.record(
            actor_id="user1",
            actor_type="HUMAN",
            action="ACTION_1",
            resource="grid",
            result="SUCCESS",
        )
        service.record(
            actor_id="user2",
            actor_type="HUMAN",
            action="ACTION_2",
            resource="grid",
            result="SUCCESS",
        )
        records = service.get_records()
        assert len(records) == 2
        # Newest first
        assert records[0].action == "ACTION_2"
        assert records[1].action == "ACTION_1"

    def test_get_records_filter_by_actor(self):
        """Should filter by actor_id."""
        service = AuditService()
        service.record(
            actor_id="user1",
            actor_type="HUMAN",
            action="ACTION_1",
            resource="grid",
            result="SUCCESS",
        )
        service.record(
            actor_id="user2",
            actor_type="HUMAN",
            action="ACTION_2",
            resource="grid",
            result="SUCCESS",
        )
        records = service.get_records(actor_id="user1")
        assert len(records) == 1
        assert records[0].actor_id == "user1"

    def test_get_records_filter_by_action(self):
        """Should filter by action."""
        service = AuditService()
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="START_GRID",
            resource="grid",
            result="SUCCESS",
        )
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="STOP_GRID",
            resource="grid",
            result="SUCCESS",
        )
        records = service.get_records(action="START_GRID")
        assert len(records) == 1
        assert records[0].action == "START_GRID"

    def test_get_records_filter_by_resource(self):
        """Should filter by resource."""
        service = AuditService()
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
        )
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="order",
            result="SUCCESS",
        )
        records = service.get_records(resource="grid")
        assert len(records) == 1
        assert records[0].resource == "grid"

    def test_get_records_filter_by_environment(self):
        """Should filter by environment."""
        service = AuditService()
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            environment="DEMO",
        )
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            environment="LIVE",
        )
        records = service.get_records(environment="LIVE")
        assert len(records) == 1
        assert records[0].environment == "LIVE"

    def test_get_records_filter_by_correlation_id(self):
        """Should filter by correlation_id."""
        service = AuditService()
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            correlation_id="corr-1",
        )
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            correlation_id="corr-2",
        )
        records = service.get_records(correlation_id="corr-1")
        assert len(records) == 1
        assert records[0].correlation_id == "corr-1"

    def test_get_records_limit(self):
        """Should respect limit."""
        service = AuditService()
        for i in range(10):
            service.record(
                actor_id="user",
                actor_type="HUMAN",
                action=f"ACTION_{i}",
                resource="grid",
                result="SUCCESS",
            )
        records = service.get_records(limit=5)
        assert len(records) == 5

    def test_get_records_for_operation(self):
        """Should return records for operation."""
        service = AuditService()
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION_1",
            resource="grid",
            result="SUCCESS",
            operation_id="op-123",
        )
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION_2",
            resource="grid",
            result="SUCCESS",
            operation_id="op-456",
        )
        records = service.get_records_for_operation("op-123")
        assert len(records) == 1
        assert records[0].operation_id == "op-123"

    def test_sensitive_data_filtered(self):
        """Sensitive keys should be redacted."""
        service = AuditService()
        record = service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            metadata={
                "api_key": "secret-key-123",
                "password": "secret-pass",
                "safe_key": "safe-value",
            },
        )
        assert record.metadata["api_key"] == "[REDACTED]"
        assert record.metadata["password"] == "[REDACTED]"
        assert record.metadata["safe_key"] == "safe-value"

    def test_nested_sensitive_data_filtered(self):
        """Nested sensitive keys should be redacted."""
        service = AuditService()
        record = service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            metadata={
                "config": {
                    "token": "secret-token",
                    "safe": "value",
                },
            },
        )
        nested = record.metadata["config"]
        assert isinstance(nested, dict)
        assert nested["token"] == "[REDACTED]"
        assert nested["safe"] == "value"

    def test_sensitive_key_substring_filtered(self):
        """Keys containing sensitive substrings should be redacted."""
        service = AuditService()
        record = service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
            metadata={
                "x_api_key_header": "secret",
                "my_password_field": "secret",
            },
        )
        assert record.metadata["x_api_key_header"] == "[REDACTED]"
        assert record.metadata["my_password_field"] == "[REDACTED]"

    def test_sensitive_keys_constant(self):
        """SENSITIVE_KEYS should contain expected keys."""
        assert "api_key" in SENSITIVE_KEYS
        assert "api_secret" in SENSITIVE_KEYS
        assert "password" in SENSITIVE_KEYS
        assert "token" in SENSITIVE_KEYS
        assert "passphrase" in SENSITIVE_KEYS

    def test_record_count(self):
        """record_count should track total records."""
        service = AuditService()
        assert service.record_count == 0
        service.record(
            actor_id="user",
            actor_type="HUMAN",
            action="ACTION",
            resource="grid",
            result="SUCCESS",
        )
        assert service.record_count == 1
