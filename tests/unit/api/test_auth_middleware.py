"""
Unit tests for the authentication middleware security model.

These tests lock in the fixes for the auth-bypass vulnerability:

1. ``APP_DEBUG`` alone must NEVER bypass authentication.
2. Unauthenticated dev identity requires BOTH ``APP_DEV_AUTH_ENABLED=true``
   AND ``APP_ENV=development``.
3. The dev identity is DEMO-only and can never access LIVE trading.
4. Static dev API keys are only accepted in the development environment.
5. Unauthenticated requests are denied by default (401).
"""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from trading_grid.api.middleware.auth import DEV_API_KEYS, AuthMiddleware
from trading_grid.config.settings import AppSettings, Environment, Settings


def _make_settings(env: Environment, debug: bool, dev_auth_enabled: bool) -> Settings:
    """Build a Settings object with explicit security flags (no env file)."""
    app = AppSettings(
        env=env,
        debug=debug,
        dev_auth_enabled=dev_auth_enabled,
        _env_file=None,
    )
    return Settings(app=app, _env_file=None)


def _build_app() -> FastAPI:
    """Build a minimal FastAPI app protected by AuthMiddleware."""
    app = FastAPI()

    @app.get("/protected")
    async def protected(request: Request) -> dict[str, object]:
        identity = getattr(request.state, "identity", None)
        return {
            "identity_id": identity.identity_id if identity else None,
            "allowed_environments": (list(identity.allowed_environments) if identity else None),
        }

    app.add_middleware(AuthMiddleware)
    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Test client for the protected app."""
    yield TestClient(_build_app())


class TestDenyByDefault:
    """Authentication must be deny-by-default."""

    def test_unauthenticated_request_denied_by_default(self, client: TestClient) -> None:
        """With secure defaults, an unauthenticated request gets 401."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=False, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected")
        assert response.status_code == 401
        assert response.json()["code"] == "AUTHENTICATION_FAILED"

    def test_debug_true_alone_does_not_bypass_auth(self, client: TestClient) -> None:
        """SECURITY: APP_DEBUG=true must NOT grant an identity without auth."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=True, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected")
        assert response.status_code == 401


class TestDevAuthBypass:
    """The unauthenticated dev identity is an explicit, dev-only opt-in."""

    def test_dev_bypass_requires_explicit_flag(self, client: TestClient) -> None:
        """Dev identity granted only when dev_auth_enabled=true in development."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=False, dev_auth_enabled=True)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected")
        assert response.status_code == 200
        assert response.json()["identity_id"] == "dev-user"

    def test_dev_identity_is_demo_only(self, client: TestClient) -> None:
        """SECURITY: the dev identity must never be allowed LIVE access."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=False, dev_auth_enabled=True)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected")
        assert response.status_code == 200
        assert response.json()["allowed_environments"] == ["DEMO"]
        assert "LIVE" not in response.json()["allowed_environments"]


class TestDevApiKeys:
    """Static dev API keys are only accepted in the development environment."""

    def test_dev_api_key_accepted_in_development(self, client: TestClient) -> None:
        """A dev API key authenticates in the development environment."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=False, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected", headers={"X-API-Key": "dev-admin-key"})
        assert response.status_code == 200
        assert response.json()["identity_id"] == "dev-admin"

    def test_dev_api_key_rejected_in_production(self, client: TestClient) -> None:
        """SECURITY: a dev API key must NOT authenticate in production."""
        settings = _make_settings(env=Environment.PRODUCTION, debug=False, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected", headers={"X-API-Key": "dev-admin-key"})
        assert response.status_code == 401

    def test_unknown_api_key_rejected(self, client: TestClient) -> None:
        """An unknown API key is rejected."""
        settings = _make_settings(env=Environment.DEVELOPMENT, debug=False, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/protected", headers={"X-API-Key": "not-a-real-key"})
        assert response.status_code == 401

    def test_no_dev_key_grants_live_access(self) -> None:
        """SECURITY: no static dev key may grant LIVE environment access."""
        for identity in DEV_API_KEYS.values():
            assert "LIVE" not in identity.allowed_environments


class TestPublicPaths:
    """Public paths remain accessible."""

    def test_health_is_public(self) -> None:
        """The /health endpoint does not require authentication."""
        app = FastAPI()

        @app.get("/health")
        async def health() -> dict[str, str]:
            return {"status": "ok"}

        app.add_middleware(AuthMiddleware)
        client = TestClient(app)

        settings = _make_settings(env=Environment.PRODUCTION, debug=False, dev_auth_enabled=False)
        with patch("trading_grid.config.settings.get_settings", return_value=settings):
            response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
