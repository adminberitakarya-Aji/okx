"""
Unit tests for grid blueprint ownership checks [I-C3].

These tests verify:
1. ``get_current_identity`` dependency extracts identity from request state
2. ``get_current_identity`` raises 401 when no identity is attached
3. Blueprint model supports ``user_id`` ownership field
4. ``start_grid`` endpoint requires identity and checks ownership
5. User B cannot start a blueprint owned by User A (403)
6. User A can start their own blueprint
7. System-generated blueprints (user_id=None) are accessible to all
8. Blueprint generation sets owner from authenticated identity
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from trading_grid.api.routes.dependencies import get_current_identity
from trading_grid.application.services.authorization import Identity, Role
from trading_grid.domain.grid.models import Blueprint

# =============================================================================
# Test get_current_identity dependency
# =============================================================================


class TestGetCurrentIdentity:
    """Tests for the get_current_identity dependency."""

    def test_extracts_identity_from_request_state(self) -> None:
        """get_current_identity returns identity attached to request.state."""
        identity = Identity(
            identity_id="user-123",
            identity_type="HUMAN",
            role=Role.DEMO_OPERATOR,
            allowed_environments=("DEMO",),
        )

        mock_request = MagicMock(spec=Request)
        mock_request.state.identity = identity

        result = get_current_identity(mock_request)
        assert result is identity
        assert result.identity_id == "user-123"

    def test_raises_401_when_no_identity(self) -> None:
        """get_current_identity raises 401 when no identity is attached."""
        from fastapi import HTTPException

        mock_request = MagicMock(spec=Request)
        mock_request.state.identity = None

        with pytest.raises(HTTPException) as exc_info:
            get_current_identity(mock_request)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail

    def test_raises_401_when_state_missing_identity_attribute(self) -> None:
        """get_current_identity raises 401 when state has no identity attribute."""
        from fastapi import HTTPException

        mock_request = MagicMock(spec=Request)
        # state exists but has no identity attribute
        mock_request.state = MagicMock(spec=[])

        with pytest.raises(HTTPException) as exc_info:
            get_current_identity(mock_request)

        assert exc_info.value.status_code == 401


# =============================================================================
# Test Blueprint user_id field
# =============================================================================


class TestBlueprintOwnership:
    """Tests for Blueprint user_id ownership field."""

    def test_blueprint_user_id_defaults_to_none(self) -> None:
        """Blueprint user_id defaults to None (system-generated/legacy)."""
        blueprint = Blueprint(
            blueprint_id="BP-TEST-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
        )
        assert blueprint.user_id is None

    def test_blueprint_user_id_can_be_set(self) -> None:
        """Blueprint user_id can be set to an owner identity."""
        blueprint = Blueprint(
            blueprint_id="BP-TEST-002",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id="user-456",
        )
        assert blueprint.user_id == "user-456"

    def test_blueprint_user_id_is_mutable(self) -> None:
        """Blueprint user_id can be set after creation."""
        blueprint = Blueprint(
            blueprint_id="BP-TEST-003",
            market_id="ETH-USDT",
            total_capital=Decimal("500"),
        )
        assert blueprint.user_id is None

        blueprint.user_id = "user-789"
        assert blueprint.user_id == "user-789"


# =============================================================================
# Test start_grid ownership check via API
# =============================================================================


def _make_test_identity(identity_id: str) -> Identity:
    """Create a test identity."""
    return Identity(
        identity_id=identity_id,
        identity_type="HUMAN",
        role=Role.DEMO_OPERATOR,
        allowed_environments=("DEMO",),
    )


def _make_test_blueprint(blueprint_id: str, user_id: str | None) -> Blueprint:
    """Create a test blueprint with ownership."""
    return Blueprint(
        blueprint_id=blueprint_id,
        market_id="BTC-USDT",
        total_capital=Decimal("1000"),
        user_id=user_id,
    )


class TestStartGridOwnership:
    """Tests for start_grid endpoint ownership checks."""

    def _build_app_with_mock_container(
        self,
        blueprint: Blueprint | None,
        identity: Identity | None,
    ) -> FastAPI:
        """Build a test app with mocked container and identity."""
        from trading_grid.api.routes.grid import router

        app = FastAPI()
        app.include_router(router, prefix="/grid")

        # Mock the container
        mock_container = MagicMock()
        mock_container.research_service.get_blueprint.return_value = blueprint

        # Mock demo service for successful start
        mock_session = MagicMock()
        mock_session.session_id = "SESSION-001"
        mock_session.grid_runtime.grid_id = "GRID-001"
        mock_container.demo_service.create_demo_grid.return_value = mock_session
        mock_container.demo_service.start_demo_grid = MagicMock(return_value=mock_session)

        # Patch get_default_container
        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=mock_container,
        ):
            # Override get_current_identity to return test identity
            if identity is not None:
                app.dependency_overrides[get_current_identity] = lambda: identity

        return app

    def test_start_grid_requires_identity(self) -> None:
        """start_grid returns 401 when no identity is provided."""
        from trading_grid.api.routes.grid import router

        app = FastAPI()
        app.include_router(router, prefix="/grid")

        blueprint = _make_test_blueprint("BP-001", user_id=None)
        mock_container = MagicMock()
        mock_container.research_service.get_blueprint.return_value = blueprint

        # Don't override get_current_identity — it should fail without request.state
        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/grid/start",
                json={"blueprint_id": "BP-001"},
            )

        # Should get 401 because no identity in request state
        assert response.status_code == 401

    def test_user_cannot_start_other_users_blueprint(self) -> None:
        """User B cannot start a blueprint owned by User A (403)."""
        blueprint = _make_test_blueprint("BP-002", user_id="user-A")
        identity_b = _make_test_identity("user-B")

        app = self._build_app_with_mock_container(blueprint, identity_b)
        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=MagicMock(
                research_service=MagicMock(get_blueprint=MagicMock(return_value=blueprint))
            ),
        ):
            response = client.post(
                "/grid/start",
                json={"blueprint_id": "BP-002"},
            )

        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]

    def test_user_can_start_own_blueprint(self) -> None:
        """User A can start their own blueprint."""
        blueprint = _make_test_blueprint("BP-003", user_id="user-A")
        identity_a = _make_test_identity("user-A")

        mock_container = MagicMock()
        mock_container.research_service.get_blueprint.return_value = blueprint

        mock_session = MagicMock()
        mock_session.session_id = "SESSION-001"
        mock_session.grid_runtime.grid_id = "GRID-001"
        mock_container.demo_service.create_demo_grid.return_value = mock_session

        # Make start_demo_grid a coroutine
        async def mock_start(session_id: str, identity: Identity):
            """[A-H12] Router now passes the authenticated caller identity."""
            assert identity.identity_id == "user-A"
            return mock_session

        mock_container.demo_service.start_demo_grid = mock_start

        from trading_grid.api.routes.grid import router

        app = FastAPI()
        app.include_router(router, prefix="/grid")
        app.dependency_overrides[get_current_identity] = lambda: identity_a

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/grid/start",
                json={"blueprint_id": "BP-003"},
            )

        assert response.status_code == 201
        assert response.json()["status"] == "SUCCEEDED"
        assert response.json()["grid_id"] == "GRID-001"

    def test_system_blueprint_accessible_to_all(self) -> None:
        """System-generated blueprints (user_id=None) are accessible to all users."""
        blueprint = _make_test_blueprint("BP-004", user_id=None)
        identity_any = _make_test_identity("any-user")

        mock_container = MagicMock()
        mock_container.research_service.get_blueprint.return_value = blueprint

        mock_session = MagicMock()
        mock_session.session_id = "SESSION-002"
        mock_session.grid_runtime.grid_id = "GRID-002"
        mock_container.demo_service.create_demo_grid.return_value = mock_session

        async def mock_start(session_id: str, identity: Identity):
            """[A-H11] Router now passes the authenticated caller identity."""
            assert identity.identity_id == "any-user"
            return mock_session

        mock_container.demo_service.start_demo_grid = mock_start

        from trading_grid.api.routes.grid import router

        app = FastAPI()
        app.include_router(router, prefix="/grid")
        app.dependency_overrides[get_current_identity] = lambda: identity_any

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/grid/start",
                json={"blueprint_id": "BP-004"},
            )

        assert response.status_code == 201
        assert response.json()["status"] == "SUCCEEDED"

    def test_blueprint_not_found_returns_404(self) -> None:
        """start_grid returns 404 when blueprint doesn't exist."""
        identity = _make_test_identity("user-A")

        mock_container = MagicMock()
        mock_container.research_service.get_blueprint.return_value = None

        from trading_grid.api.routes.grid import router

        app = FastAPI()
        app.include_router(router, prefix="/grid")
        app.dependency_overrides[get_current_identity] = lambda: identity

        client = TestClient(app)

        with patch(
            "trading_grid.api.routes.grid.get_default_container",
            return_value=mock_container,
        ):
            response = client.post(
                "/grid/start",
                json={"blueprint_id": "BP-NONEXISTENT"},
            )

        assert response.status_code == 404
        assert "Blueprint not found" in response.json()["detail"]


# =============================================================================
# Test blueprint generation sets owner
# =============================================================================


class TestBlueprintGenerationOwnership:
    """Tests for blueprint generation setting user_id."""

    def test_generate_default_blueprint_sets_user_id(self) -> None:
        """generate_default_blueprint sets user_id from parameter."""
        from trading_grid.application.services.research_service import ResearchService

        # Create service without adapter (will use defaults)
        with patch.object(ResearchService, "_load_deployed_models"):
            service = ResearchService(
                adapter=None, model_dir="models", registry_dir="models/registry"
            )

        blueprint = service.generate_default_blueprint(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
            capital=Decimal("1000"),
            user_id="user-owner-123",
        )

        assert blueprint.user_id == "user-owner-123"
        assert blueprint.market_id == "BTC-USDT"

    def test_generate_default_blueprint_without_user_id(self) -> None:
        """generate_default_blueprint without user_id leaves it None."""
        from trading_grid.application.services.research_service import ResearchService

        with patch.object(ResearchService, "_load_deployed_models"):
            service = ResearchService(
                adapter=None, model_dir="models", registry_dir="models/registry"
            )

        blueprint = service.generate_default_blueprint(
            market_id="ETH-USDT",
            current_price=Decimal("3000"),
            capital=Decimal("500"),
        )

        assert blueprint.user_id is None
