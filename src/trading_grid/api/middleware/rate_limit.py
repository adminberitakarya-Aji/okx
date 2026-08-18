"""
Rate limiting middleware. [I-M5]

Provides per-IP sliding-window rate limiting for the FastAPI application.
Limits are applied on all non-public paths.

Design:
- In-memory sliding window using collections.deque - no Redis required for Phase 0-2
- Each IP gets a deque of timestamps; entries older than the window are pruned on each request
- Exceeding the limit returns HTTP 429 with Retry-After header
- Public paths (health/docs) are excluded

Configuration (via Settings):
    RATE_LIMIT_REQUESTS_PER_MINUTE = 120   (default)
    RATE_LIMIT_BURST = 30                  (default, per 10-second burst)
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()

# Paths exempt from rate limiting
RATE_LIMIT_EXEMPT_PATHS = frozenset(
    {
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# In-memory store: ip -> deque of timestamps (float, seconds since epoch)
_window_store: dict[str, deque[float]] = {}

# Defaults - overridden when RateLimitMiddleware is instantiated
_DEFAULT_WINDOW_SECONDS = 60
_DEFAULT_MAX_REQUESTS = 120


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-IP sliding-window rate limiting middleware.

    Args:
        app: ASGI application
        max_requests: Maximum requests allowed in the window (default: 120)
        window_seconds: Window size in seconds (default: 60)
    """

    def __init__(
        self,
        app,  # type: ignore[type-arg]
        max_requests: int = _DEFAULT_MAX_REQUESTS,
        window_seconds: int = _DEFAULT_WINDOW_SECONDS,
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Apply rate limiting before processing the request."""
        # Skip rate limiting for public/exempt paths
        if request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - self._window_seconds

        # Get or create this IP's sliding window
        if client_ip not in _window_store:
            _window_store[client_ip] = deque()

        window = _window_store[client_ip]

        # Prune entries outside the window
        while window and window[0] < window_start:
            window.popleft()

        if len(window) >= self._max_requests:
            retry_after = int(self._window_seconds - (now - window[0])) + 1
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=request.url.path,
                count=len(window),
                max_requests=self._max_requests,
                window_seconds=self._window_seconds,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Too many requests. Maximum {self._max_requests} per {self._window_seconds}s.",
                    "category": "RATE_LIMIT",
                    "retryable": True,
                },
                headers={"Retry-After": str(retry_after)},
            )

        window.append(now)
        return await call_next(request)