"""
Audit logging service for immutable audit trail.

This module provides:
- Audit record creation for all state-changing operations
- Append-only audit log
- Correlation ID tracking
- Sensitive data exclusion

Security rules:
1. Every state-changing command creates an audit record
2. Audit logs are append-only (no modification)
3. Sensitive credentials are excluded from audit records
4. All security-relevant events are logged
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from trading_grid.domain.shared.types import ExecutionMode, Timestamp

ActorType = Literal["HUMAN", "SERVICE", "SYSTEM"]
AuditResult = Literal["SUCCESS", "DENIED", "ERROR", "PENDING"]

# Sensitive keys that must never appear in audit metadata
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "secret",
        "passphrase",
        "password",
        "token",
        "bot_token",
        "authorization",
        "x-api-key",
        "credentials",
        "private_key",
    }
)


@dataclass(frozen=True)
class AuditRecord:
    """
    Immutable audit record.

    Attributes:
        audit_id: Unique audit identifier
        timestamp: Event timestamp (UTC)
        actor_id: Identity that performed the action
        actor_type: Type of actor (HUMAN/SERVICE/SYSTEM)
        action: The action performed
        resource: The resource affected
        resource_id: The resource identifier
        environment: Target environment (DEMO/LIVE)
        result: Operation result
        correlation_id: Correlation ID for tracing
        operation_id: Associated operation ID (if any)
        error_message: Error message (if failed)
        metadata: Additional non-sensitive metadata
    """

    audit_id: str
    timestamp: Timestamp
    actor_id: str
    actor_type: ActorType
    action: str
    resource: str
    result: AuditResult
    resource_id: str | None = None
    environment: ExecutionMode | None = None
    correlation_id: str | None = None
    operation_id: str | None = None
    error_message: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class AuditService:
    """
    Service for maintaining an immutable audit trail.

    Provides:
    - Recording of all state-changing operations
    - Correlation ID propagation
    - Sensitive data filtering
    - Query capabilities for audit records
    """

    def __init__(self) -> None:
        """Initialize audit service with empty log."""
        self._records: list[AuditRecord] = []

    def record(
        self,
        actor_id: str,
        actor_type: ActorType,
        action: str,
        resource: str,
        result: AuditResult,
        resource_id: str | None = None,
        environment: ExecutionMode | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditRecord:
        """
        Create an audit record.

        Args:
            actor_id: Identity performing the action
            actor_type: Type of actor
            action: The action performed
            resource: The resource affected
            result: Operation result
            resource_id: Resource identifier
            environment: Target environment
            correlation_id: Correlation ID for tracing
            operation_id: Associated operation ID
            error_message: Error message if failed
            metadata: Additional metadata (sensitive keys filtered)

        Returns:
            The created AuditRecord
        """
        audit_id = f"AUD-{uuid4().hex[:12].upper()}"
        safe_metadata = self._filter_sensitive_data(metadata or {})

        record = AuditRecord(
            audit_id=audit_id,
            timestamp=datetime.now(UTC),
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource=resource,
            result=result,
            resource_id=resource_id,
            environment=environment,
            correlation_id=correlation_id,
            operation_id=operation_id,
            error_message=error_message,
            metadata=safe_metadata,
        )

        self._records.append(record)
        return record

    def record_success(
        self,
        actor_id: str,
        actor_type: ActorType,
        action: str,
        resource: str,
        resource_id: str | None = None,
        environment: ExecutionMode | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditRecord:
        """Record a successful operation."""
        return self.record(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource=resource,
            result="SUCCESS",
            resource_id=resource_id,
            environment=environment,
            correlation_id=correlation_id,
            operation_id=operation_id,
            metadata=metadata,
        )

    def record_denied(
        self,
        actor_id: str,
        actor_type: ActorType,
        action: str,
        resource: str,
        reason: str,
        resource_id: str | None = None,
        environment: ExecutionMode | None = None,
        correlation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditRecord:
        """Record a denied operation (authorization failure)."""
        return self.record(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource=resource,
            result="DENIED",
            resource_id=resource_id,
            environment=environment,
            correlation_id=correlation_id,
            error_message=reason,
            metadata=metadata,
        )

    def record_error(
        self,
        actor_id: str,
        actor_type: ActorType,
        action: str,
        resource: str,
        error_message: str,
        resource_id: str | None = None,
        environment: ExecutionMode | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> AuditRecord:
        """Record a failed operation."""
        return self.record(
            actor_id=actor_id,
            actor_type=actor_type,
            action=action,
            resource=resource,
            result="ERROR",
            resource_id=resource_id,
            environment=environment,
            correlation_id=correlation_id,
            operation_id=operation_id,
            error_message=error_message,
            metadata=metadata,
        )

    def get_records(
        self,
        actor_id: str | None = None,
        action: str | None = None,
        resource: str | None = None,
        environment: ExecutionMode | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditRecord]:
        """
        Query audit records with optional filters.

        Args:
            actor_id: Filter by actor
            action: Filter by action
            resource: Filter by resource
            environment: Filter by environment
            correlation_id: Filter by correlation ID
            limit: Maximum records to return

        Returns:
            List of matching audit records (newest first)
        """
        records = self._records

        if actor_id is not None:
            records = [r for r in records if r.actor_id == actor_id]
        if action is not None:
            records = [r for r in records if r.action == action]
        if resource is not None:
            records = [r for r in records if r.resource == resource]
        if environment is not None:
            records = [r for r in records if r.environment == environment]
        if correlation_id is not None:
            records = [r for r in records if r.correlation_id == correlation_id]

        # Return newest first
        return list(reversed(records[-limit:]))

    def get_records_for_operation(self, operation_id: str) -> list[AuditRecord]:
        """Get all audit records for an operation."""
        return [r for r in self._records if r.operation_id == operation_id]

    @property
    def record_count(self) -> int:
        """Get total number of audit records."""
        return len(self._records)

    def _filter_sensitive_data(self, metadata: dict[str, object]) -> dict[str, object]:
        """
        Filter sensitive keys from metadata.

        Args:
            metadata: Raw metadata dictionary

        Returns:
            Filtered metadata with sensitive keys removed
        """
        filtered: dict[str, object] = {}
        for key, value in metadata.items():
            key_lower = key.lower()
            if key_lower in SENSITIVE_KEYS or any(
                sensitive in key_lower for sensitive in SENSITIVE_KEYS
            ):
                filtered[key] = "[REDACTED]"
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive_data(value)
            elif isinstance(value, list):
                filtered[key] = [
                    self._filter_sensitive_data(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                filtered[key] = value
        return filtered
