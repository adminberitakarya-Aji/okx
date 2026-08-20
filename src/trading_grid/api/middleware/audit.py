"""
Audit logging middleware.

This module provides:
- Request/response audit logging
- Correlation ID generation and propagation
- Request timing
- [I-M2] DB persistence for state-changing operations (POST/PUT/PATCH/DELETE)

Security rules:
1. All requests are logged with correlation ID
2. Sensitive headers are never logged
3. State-changing operations create audit records in the database
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request, Response

logger = structlog.get_logger()

# Headers that should never be logged
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "x-api-key",
        "cookie",
        "set-cookie",
    }
)

# HTTP methods that change state and should be persisted in the audit log
STATE_CHANGING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Audit logging middleware.

    Adds correlation ID to all requests and logs request/response metadata.
    State-changing requests (POST/PUT/PATCH/DELETE) with successful responses
    are additionally persisted to the AuditLogModel database table.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with audit logging."""
        # Generate or propagate correlation ID
        header_id = request.headers.get("X-Correlation-ID")
        correlation_id = header_id or f"REQ-{uuid4().hex[:12].upper()}"
        request.state.correlation_id = correlation_id

        # Resolve actor from request state (set by AuthMiddleware)
        actor = getattr(request.state, "user_id", "anonymous")

        # Log request (without sensitive headers)
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
            client_ip=request.client.host if request.client else "unknown",
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Add correlation ID to response
            response.headers["X-Correlation-ID"] = correlation_id

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                correlation_id=correlation_id,
            )

            # [I-M2] Persist state-changing requests to DB audit log
            if request.method in STATE_CHANGING_METHODS and 200 <= response.status_code < 300:
                await _persist_audit_record(
                    actor=str(actor),
                    action=f"{request.method} {request.url.path}",
                    resource_id=correlation_id,
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": round(duration_ms, 2),
                    },
                    success=True,
                )

            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
                correlation_id=correlation_id,
            )
            # Persist failed state-changing requests too
            if request.method in STATE_CHANGING_METHODS:
                await _persist_audit_record(
                    actor=str(actor),
                    action=f"{request.method} {request.url.path}",
                    resource_id=correlation_id,
                    details={
                        "method": request.method,
                        "path": request.url.path,
                        "error": str(exc),
                        "duration_ms": round(duration_ms, 2),
                    },
                    success=False,
                )
            raise


async def _persist_audit_record(
    actor: str,
    action: str,
    resource_id: str | None,
    details: dict[str, object],
    success: bool,
) -> None:
    """
    Persist an audit record to the database.

    Gracefully swallows errors — audit logging must never break the request pipeline.
    Falls back to structlog-only if the database is unavailable.
    """
    try:
        # Lazy import to avoid circular dependency at module load time
        from trading_grid.infrastructure.database.engine import get_session_factory
        from trading_grid.infrastructure.database.models import AuditLogModel

        session_factory = get_session_factory()
        async with session_factory() as session:
            audit = AuditLogModel(
                timestamp=datetime.now(UTC),
                actor=actor,
                action=action,
                resource_type="http_request",
                resource_id=resource_id,
                details_json=json.dumps(details),
                success=success,
            )
            session.add(audit)
            await session.commit()
    except Exception as e:
        # Audit logging must never break the request pipeline
        logger.warning("audit_db_persist_failed", error=str(e), action=action)
