"""
Authentication middleware.

This module provides:
- API key authentication for service-to-service calls
- JWT bearer token authentication for user sessions
- Identity extraction and request context

Security rules:
1. All non-public endpoints require authentication
2. Identity is extracted and attached to request state
3. Authentication failures return 401
4. Secrets are never logged
5. Authentication is deny-by-default:
   - APP_DEBUG does NOT bypass authentication (it only controls docs/CORS)
   - Unauthenticated dev identity requires explicit APP_DEV_AUTH_ENABLED=true
     AND APP_ENV=development, and is DEMO-only (never LIVE)
   - Static dev API keys are only accepted in the development environment
"""

from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from trading_grid.application.services.authorization import Identity, Role

logger = structlog.get_logger()

# Paths that don't require authentication
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/ready",
        "/docs",
        "/redoc",
        "/openapi.json",
    }
)

# Development API keys — ONLY accepted when APP_ENV=development.
# SECURITY: These identities are DEMO-only. No dev key grants LIVE access.
# In production, use proper key management (hashed keys / secret store).
DEV_API_KEYS: dict[str, Identity] = {
    "dev-admin-key": Identity(
        identity_id="dev-admin",
        identity_type="HUMAN",
        role=Role.SYSTEM_ADMIN,
        allowed_environments=("DEMO",),
    ),
    "dev-operator-key": Identity(
        identity_id="dev-operator",
        identity_type="HUMAN",
        role=Role.DEMO_OPERATOR,
        allowed_environments=("DEMO",),
    ),
    "dev-viewer-key": Identity(
        identity_id="dev-viewer",
        identity_type="HUMAN",
        role=Role.VIEWER,
        allowed_environments=("DEMO",),
    ),
}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware.

    Extracts identity from:
    - X-API-Key header (service-to-service)
    - Authorization: Bearer <token> (user sessions)

    Attaches Identity to request.state.identity
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request authentication."""
        from trading_grid.config.settings import get_settings

        settings = get_settings()
        path = request.url.path

        # Skip authentication for public paths (assigned unprivileged anonymous identity)
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            request.state.identity = self._get_anonymous_identity()
            response: Response = await call_next(request)
            return response

        # Try API key authentication
        api_key = request.headers.get("X-API-Key")
        if api_key:
            identity = self._authenticate_api_key(api_key, is_dev=settings.app.is_development)
            if identity:
                request.state.identity = identity
                logger.debug("authenticated", identity_id=identity.identity_id, path=path)
                response = await call_next(request)
                return response

        # Try Bearer token authentication
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]
            identity = self._authenticate_bearer(token)
            if identity:
                request.state.identity = identity
                logger.debug("authenticated", identity_id=identity.identity_id, path=path)
                response = await call_next(request)
                return response

        # SECURITY: Unauthenticated dev identity is an EXPLICIT opt-in.
        # It requires BOTH:
        #   1. APP_DEV_AUTH_ENABLED=true (defaults to false)
        #   2. APP_ENV=development
        # APP_DEBUG alone NEVER bypasses authentication.
        # The dev identity is DEMO-only and can never access LIVE trading.
        if settings.app.dev_auth_enabled and settings.app.is_development:
            request.state.identity = self._get_dev_identity()
            logger.warning(
                "dev_auth_bypass_active",
                path=path,
                identity_id="dev-user",
                note="Unauthenticated dev identity granted (APP_DEV_AUTH_ENABLED=true)",
            )
            response = await call_next(request)
            return response

        # Authentication failed
        logger.warning("authentication_failed", path=path)
        error_body = (
            '{"code":"AUTHENTICATION_FAILED",'
            '"message":"Authentication required",'
            '"category":"AUTHENTICATION","retryable":false}'
        )
        return Response(
            content=error_body,
            status_code=401,
            media_type="application/json",
        )

    def _authenticate_api_key(self, api_key: str, *, is_dev: bool) -> Identity | None:
        """
        Authenticate using API key.

        Static dev API keys are ONLY accepted in the development environment.
        In production, use hashed key comparison backed by a secret store.
        """
        if not is_dev:
            return None
        return DEV_API_KEYS.get(api_key)

    def _authenticate_bearer(self, token: str) -> Identity | None:
        """
        Authenticate using Bearer token.

        Decodes JWT token, verifies signature and expiry, and constructs Identity.
        """
        import jwt
        from trading_grid.config.settings import get_settings

        settings = get_settings()
        secret_key = settings.app.secret_key.get_secret_value()

        try:
            payload = jwt.decode(token, secret_key, algorithms=["HS256"])
            user_id = payload.get("sub") or payload.get("user_id")
            if not user_id:
                return None

            role_val = payload.get("role", "VIEWER")
            if isinstance(role_val, int):
                role = Role(role_val)
            elif hasattr(Role, str(role_val)):
                role = Role[str(role_val)]
            else:
                role = Role.VIEWER

            env_raw = payload.get("allowed_environments", ["DEMO"])
            if isinstance(env_raw, (list, tuple)):
                allowed_environments = tuple(env_raw)
            else:
                allowed_environments = ("DEMO",)

            return Identity(
                identity_id=str(user_id),
                identity_type="HUMAN",
                role=role,
                allowed_environments=allowed_environments,
            )
        except Exception as exc:
            logger.debug("jwt_auth_failed", error=str(exc))
            return None

    def _get_anonymous_identity(self) -> Identity:
        """Get unprivileged identity for public routes."""
        return Identity(
            identity_id="anonymous",
            identity_type="SYSTEM",
            role=Role.VIEWER,
            allowed_environments=(),
        )

    def _get_system_identity(self) -> Identity:
        """Get system identity for internal operations."""
        return Identity(
            identity_id="system",
            identity_type="SYSTEM",
            role=Role.SYSTEM_ADMIN,
            allowed_environments=("DEMO", "LIVE"),
        )

    def _get_dev_identity(self) -> Identity:
        """
        Get default development identity.

        SECURITY: DEMO-only. This identity can never access LIVE trading,
        even though it holds the SYSTEM_ADMIN role. Environment isolation
        is absolute.
        """
        return Identity(
            identity_id="dev-user",
            identity_type="HUMAN",
            role=Role.SYSTEM_ADMIN,
            allowed_environments=("DEMO",),
        )
