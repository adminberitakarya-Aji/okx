"""
Audit logging middleware.

This module provides:
- Request/response audit logging
- Correlation ID generation and propagation
- Request timing

Security rules:
1. All requests are logged with correlation ID
2. Sensitive headers are never logged
3. State-changing operations create audit records
"""

import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

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


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Audit logging middleware.

    Adds correlation ID to all requests and logs request/response metadata.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request with audit logging."""
        # Generate or propagate correlation ID
        header_id = request.headers.get("X-Correlation-ID")
        correlation_id = header_id or f"REQ-{uuid4().hex[:12].upper()}"
        request.state.correlation_id = correlation_id

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
            raise
