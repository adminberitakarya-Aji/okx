"""
Common API schemas for request/response normalization.

This module provides:
- Base response envelope
- Error response schema
- Operation model for async operations
- Pagination schemas
"""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

ErrorCategory = Literal[
    "AUTHENTICATION",
    "AUTHORIZATION",
    "VALIDATION",
    "CONFLICT",
    "NOT_FOUND",
    "RISK",
    "EXECUTION",
    "PROVIDER",
    "TIMEOUT",
    "SYSTEM",
]

OperationStatus = Literal[
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
]


class ErrorResponse(BaseModel):
    """
    Normalized API error response.

    Provider-specific errors (e.g., OKX) must not leak through this contract.
    """

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    category: ErrorCategory = Field(..., description="Error category")
    retryable: bool = Field(default=False, description="Whether the request can be retried")
    operation_id: str | None = Field(default=None, description="Associated operation ID")
    details: dict[str, Any] | None = Field(default=None, description="Additional error details")


class ResponseEnvelope(BaseModel, Generic[T]):  # noqa: UP046
    """
    Standard response envelope.

    All successful responses are wrapped in this envelope.
    """

    success: bool = Field(default=True)
    data: T | None = None
    error: ErrorResponse | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    request_id: str | None = None


class OperationResponse(BaseModel):
    """
    Response for long-running operations.

    Async operations return an operation ID for status polling.
    """

    operation_id: str = Field(..., description="Unique operation identifier")
    command_type: str = Field(..., description="Type of command")
    status: OperationStatus = Field(..., description="Current operation status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    initiated_by: str | None = None
    environment: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    error: str | None = None
    result_reference: str | None = None


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=50, ge=1, le=500, description="Items per page")


class PaginatedResponse(BaseModel, Generic[T]):  # noqa: UP046
    """Paginated list response."""

    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: dict[str, str] | None = None


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: Literal["READY", "NOT_READY", "DEGRADED", "BLOCKED"]
    checks: dict[str, bool] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
