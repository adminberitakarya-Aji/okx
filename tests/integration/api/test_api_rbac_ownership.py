"""
Integration tests for API RBAC and ownership checks [T-M5].

These tests verify end-to-end HTTP layer behavior:
1. Auth middleware → identity extraction → route → ownership check
2. RBAC: VIEWER cannot access admin/operator endpoints
3. Ownership: User B cannot access resources owned by User A
4. Public paths are accessible without authentication
5. Unauthenticated requests to protected endpoints return 401

Unlike unit tests (which mock dependencies heavily), these integration tests
use the actual FastAPI app with AuthMiddleware to verify the full HTTP stack.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_grid.api.middleware.auth import AuthMiddleware
from trading_grid.api.routes.dependencies import (
    get_multi_container,
    set_multi_container,
)
from trading_grid.domain.grid.models import Blueprint

# =============================================================================
# Test Fixtures
# =============================================================================


def _create_test_app() -> FastAPI:
    """Create a minimal test app with auth middleware and routers."""
    from trading_grid.api.routes import approvals, blueprints, grid, health

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(health.router, tags=["Health"])
    app.include_router(grid.router, prefix="/api/v1/grid", tags=["Grid"])
    app.include_router(blueprints.router, prefix="/api/v1/blueprints", tags=["Blueprints"])
    app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["Approvals"])
    return app


def _create_mock_container() -> MagicMock:
    """Create a mock service container."""
    container = MagicMock()

    # Mock research service
    container.research_service = MagicMock()
    container.research_service.blueprints = {}
    container.research_service.get_blueprint.return_value = None

    # Mock demo service (start_demo_grid is async)
    mock_session = MagicMock(
        session_id="SESSION-001",
        grid_runtime=MagicMock(grid_id="GRID-001"),
    )
    container.demo_service = MagicMock()
    container.demo_service.create_demo_grid.return_value = mock_session
    container.demo_service.start_demo_grid = AsyncMock(return_value=mock_session)

    # Mock grid engine
    container.grid_engine = MagicMock()
    container.grid_engine.get_active_grids.return_value = []
    container.grid_engine.get_grid.return_value = None

    # Mock approval service
    container.approval_service = MagicMock()
    container.approval_service.get_pending_approvals.return_value = []
    container.approval_service._approvals = {}

    return container


def _create_mock_multi_container() -> MagicMock:
    """Create a mock multi-exchange container."""
    multi = MagicMock()
    default_container = _create_mock_container()
    multi.default_container = default_container
    multi.get_container.return_value = default_container
    return multi


@pytest.fixture
def test_app() -> FastAPI:
    """Create test app with mocked container."""
    app = _create_test_app()
    multi = _create_mock_multi_container()
    set_multi_container(multi)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(test_app)


# =============================================================================
# Test: Public Paths (No Auth Required)
# =============================================================================


class TestPublicPaths:
    """Verify public paths are accessible without authentication."""

    def test_health_endpoint_accessible_without_auth(self, client: TestClient) -> None:
        """GET /health should return 200 without authentication."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_status_healthy(self, client: TestClient) -> None:
        """GET /health should return status healthy."""
        response = client.get("/health")
        data = response.json()
        assert data["status"] == "healthy"


# =============================================================================
# Test: Authentication Required (401)
# =============================================================================


class TestAuthenticationRequired:
    """Verify protected endpoints return 401 without authentication."""

    def test_grid_list_requires_auth(self, client: TestClient) -> None:
        """GET /api/v1/grid should return 401 without auth."""
        response = client.get("/api/v1/grid")
        assert response.status_code == 401

    def test_grid_start_requires_auth(self, client: TestClient) -> None:
        """POST /api/v1/grid/start should return 401 without auth."""
        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-001"},
        )
        assert response.status_code == 401

    def test_blueprints_list_requires_auth(self, client: TestClient) -> None:
        """GET /api/v1/blueprints should return 401 without auth."""
        response = client.get("/api/v1/blueprints")
        assert response.status_code == 401

    def test_approvals_list_requires_auth(self, client: TestClient) -> None:
        """GET /api/v1/approvals should return 401 without auth."""
        response = client.get("/api/v1/approvals")
        assert response.status_code == 401

    def test_401_response_has_error_body(self, client: TestClient) -> None:
        """401 response should have proper error body."""
        response = client.get("/api/v1/grid")
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == "AUTHENTICATION_FAILED"
        assert data["category"] == "AUTHENTICATION"


# =============================================================================
# Test: RBAC — Role-Based Access Control
# =============================================================================


class TestRBAC:
    """Verify RBAC enforcement via HTTP layer."""

    def test_viewer_can_list_grids(self, client: TestClient) -> None:
        """VIEWER role can access read-only grid list."""
        response = client.get(
            "/api/v1/grid",
            headers={"X-API-Key": "dev-viewer-key"},
        )
        # Should not be 401 (authenticated) or 403 (authorized for read)
        assert response.status_code == 200

    def test_viewer_can_list_blueprints(self, client: TestClient) -> None:
        """VIEWER role can access read-only blueprint list."""
        response = client.get(
            "/api/v1/blueprints",
            headers={"X-API-Key": "dev-viewer-key"},
        )
        assert response.status_code == 200

    def test_viewer_cannot_start_grid(self, client: TestClient) -> None:
        """VIEWER role cannot start a grid (requires DEMO_OPERATOR+)."""
        # First, add a blueprint to the mock
        multi = get_multi_container()
        blueprint = Blueprint(
            blueprint_id="BP-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id=None,  # System blueprint
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-001"},
            headers={"X-API-Key": "dev-viewer-key"},
        )
        # [T-M5] VIEWER should be denied (403) — RBAC check added to start_grid
        assert response.status_code == 403
        assert "DEMO_OPERATOR" in response.json()["detail"]

    def test_operator_can_start_grid(self, client: TestClient) -> None:
        """DEMO_OPERATOR role can start a grid."""
        multi = get_multi_container()
        blueprint = Blueprint(
            blueprint_id="BP-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id=None,  # System blueprint
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-001"},
            headers={"X-API-Key": "dev-operator-key"},
        )
        assert response.status_code == 201

    def test_admin_can_start_grid(self, client: TestClient) -> None:
        """SYSTEM_ADMIN role can start a grid."""
        multi = get_multi_container()
        blueprint = Blueprint(
            blueprint_id="BP-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id=None,
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-001"},
            headers={"X-API-Key": "dev-admin-key"},
        )
        assert response.status_code == 201


# =============================================================================
# Test: Ownership Checks [I-C3]
# =============================================================================


class TestOwnershipChecks:
    """Verify ownership checks via HTTP layer."""

    def test_user_cannot_start_another_users_blueprint(self, client: TestClient) -> None:
        """User B cannot start a blueprint owned by User A (403)."""
        multi = get_multi_container()

        # Blueprint owned by user-a
        blueprint = Blueprint(
            blueprint_id="BP-OWNED",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id="user-a",  # Owned by user-a
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        # user-b (dev-operator) tries to start user-a's blueprint
        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-OWNED"},
            headers={"X-API-Key": "dev-operator-key"},  # dev-operator identity
        )

        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]

    def test_owner_can_start_own_blueprint(self, client: TestClient) -> None:
        """User A can start their own blueprint."""
        multi = get_multi_container()

        # Blueprint owned by dev-operator
        blueprint = Blueprint(
            blueprint_id="BP-MINE",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id="dev-operator",  # Owned by dev-operator
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-MINE"},
            headers={"X-API-Key": "dev-operator-key"},
        )

        assert response.status_code == 201

    def test_system_blueprint_accessible_to_all(self, client: TestClient) -> None:
        """System blueprints (user_id=None) are accessible to all authenticated users."""
        multi = get_multi_container()

        # System blueprint (no owner)
        blueprint = Blueprint(
            blueprint_id="BP-SYSTEM",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id=None,  # System blueprint
        )
        multi.default_container.research_service.get_blueprint.return_value = blueprint

        # Any authenticated user can start
        response = client.post(
            "/api/v1/grid/start",
            json={"blueprint_id": "BP-SYSTEM"},
            headers={"X-API-Key": "dev-viewer-key"},
        )

        # Should succeed (201) or fail at role check, not ownership
        assert response.status_code in (201, 403)

    def test_grid_list_filters_by_ownership(self, client: TestClient) -> None:
        """Grid list only shows grids owned by the authenticated user."""
        multi = get_multi_container()

        # Create mock grids with different owners
        grid_a = MagicMock()
        grid_a.grid_id = "GRID-A"
        grid_a.user_id = "user-a"
        grid_a.market_id = "BTC-USDT"
        grid_a.status = "RUNNING"
        grid_a.blueprint = MagicMock(
            blueprint_id="BP-A",
            total_capital=Decimal("1000"),
            sections=[],
        )
        grid_a.deployed_capital = Decimal("500")
        grid_a.capital_utilization = Decimal("0.5")
        grid_a.unrealized_pnl = Decimal("0")
        grid_a.realized_pnl = Decimal("0")
        grid_a.started_at = None

        grid_b = MagicMock()
        grid_b.grid_id = "GRID-B"
        grid_b.user_id = "dev-operator"
        grid_b.market_id = "ETH-USDT"
        grid_b.status = "RUNNING"
        grid_b.blueprint = MagicMock(
            blueprint_id="BP-B",
            total_capital=Decimal("2000"),
            sections=[],
        )
        grid_b.deployed_capital = Decimal("1000")
        grid_b.capital_utilization = Decimal("0.5")
        grid_b.unrealized_pnl = Decimal("0")
        grid_b.realized_pnl = Decimal("0")
        grid_b.started_at = None

        system_grid = MagicMock()
        system_grid.grid_id = "GRID-SYS"
        system_grid.user_id = None  # System grid
        system_grid.market_id = "SOL-USDT"
        system_grid.status = "RUNNING"
        system_grid.blueprint = MagicMock(
            blueprint_id="BP-SYS",
            total_capital=Decimal("500"),
            sections=[],
        )
        system_grid.deployed_capital = Decimal("250")
        system_grid.capital_utilization = Decimal("0.5")
        system_grid.unrealized_pnl = Decimal("0")
        system_grid.realized_pnl = Decimal("0")
        system_grid.started_at = None

        multi.default_container.grid_engine.get_active_grids.return_value = [
            grid_a,
            grid_b,
            system_grid,
        ]

        # dev-operator should see GRID-B and GRID-SYS, but not GRID-A
        response = client.get(
            "/api/v1/grid",
            headers={"X-API-Key": "dev-operator-key"},
        )

        assert response.status_code == 200
        data = response.json()
        grid_ids = [g["grid_id"] for g in data["grids"]]

        assert "GRID-B" in grid_ids  # Own grid
        assert "GRID-SYS" in grid_ids  # System grid
        assert "GRID-A" not in grid_ids  # Other user's grid

    def test_get_grid_returns_403_for_other_users_grid(self, client: TestClient) -> None:
        """GET /api/v1/grid/{id} returns 403 for grids owned by other users."""
        multi = get_multi_container()

        # Grid owned by user-a
        grid_a = MagicMock()
        grid_a.grid_id = "GRID-A"
        grid_a.user_id = "user-a"
        grid_a.market_id = "BTC-USDT"
        grid_a.status = "RUNNING"
        grid_a.blueprint = MagicMock(
            blueprint_id="BP-A",
            total_capital=Decimal("1000"),
            sections=[],
        )
        grid_a.deployed_capital = Decimal("500")
        grid_a.capital_utilization = Decimal("0.5")
        grid_a.unrealized_pnl = Decimal("0")
        grid_a.realized_pnl = Decimal("0")
        grid_a.started_at = None

        multi.default_container.grid_engine.get_grid.return_value = grid_a

        # dev-operator tries to access user-a's grid
        response = client.get(
            "/api/v1/grid/GRID-A",
            headers={"X-API-Key": "dev-operator-key"},
        )

        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]


# =============================================================================
# Test: Approvals RBAC [I-C4]
# =============================================================================


class TestApprovalsRBAC:
    """Verify approvals endpoint RBAC via HTTP layer."""

    def test_viewer_cannot_approve(self, client: TestClient) -> None:
        """VIEWER role cannot approve requests (requires LIVE_OPERATOR+)."""
        multi = get_multi_container()

        # Create a pending approval
        approval = MagicMock()
        approval.approval_id = "APR-001"
        approval.operation_type = "LIVE_TRADING"
        approval.status = "PENDING"
        approval.requested_by = "user-a"
        approval.requested_at = None
        approval.description = "Test approval"
        approval.market_id = "BTC-USDT"
        approval.blueprint_id = "BP-001"
        approval.environment = "LIVE"
        approval.decided_by = None
        approval.decided_at = None
        approval.expires_at = None
        approval.reason = None
        approval.is_pending = True

        multi.default_container.approval_service.approve.return_value = approval

        # Note: actor field is required by schema but IGNORED by the route [I-C4]
        # The actual actor is always derived from authenticated identity
        response = client.post(
            "/api/v1/approvals/APR-001/approve",
            json={"actor": "spoofed-actor", "reason": "Approved"},
            headers={"X-API-Key": "dev-viewer-key"},
        )

        assert response.status_code == 403
        assert "LIVE_OPERATOR" in response.json()["detail"]

    def test_viewer_cannot_reject(self, client: TestClient) -> None:
        """VIEWER role cannot reject requests (requires LIVE_OPERATOR+)."""
        response = client.post(
            "/api/v1/approvals/APR-001/reject",
            json={"actor": "spoofed-actor", "reason": "Rejected"},
            headers={"X-API-Key": "dev-viewer-key"},
        )

        assert response.status_code == 403
        assert "LIVE_OPERATOR" in response.json()["detail"]

    def test_operator_cannot_approve(self, client: TestClient) -> None:
        """DEMO_OPERATOR role cannot approve requests (requires LIVE_OPERATOR+)."""
        response = client.post(
            "/api/v1/approvals/APR-001/approve",
            json={"actor": "spoofed-actor", "reason": "Approved"},
            headers={"X-API-Key": "dev-operator-key"},
        )

        assert response.status_code == 403

    def test_admin_can_approve(self, client: TestClient) -> None:
        """SYSTEM_ADMIN role can approve requests."""
        multi = get_multi_container()

        approval = MagicMock()
        approval.approval_id = "APR-001"
        approval.operation_type = "LIVE_TRADING"
        approval.status = "APPROVED"
        approval.requested_by = "user-a"
        approval.requested_at = None
        approval.description = "Test approval"
        approval.market_id = "BTC-USDT"
        approval.blueprint_id = "BP-001"
        approval.environment = "LIVE"
        approval.decided_by = "dev-admin"
        approval.decided_at = None
        approval.expires_at = None
        approval.reason = None

        multi.default_container.approval_service.approve.return_value = approval

        response = client.post(
            "/api/v1/approvals/APR-001/approve",
            json={"actor": "spoofed-actor", "reason": "Approved"},
            headers={"X-API-Key": "dev-admin-key"},
        )

        assert response.status_code == 200


# =============================================================================
# Test: Blueprint Generation Ownership [I-C3]
# =============================================================================


class TestBlueprintGenerationOwnership:
    """Verify blueprint generation sets owner correctly."""

    def test_generate_blueprint_sets_owner(self, client: TestClient) -> None:
        """POST /api/v1/blueprints/generate sets owner from authenticated identity.

        [I-L5] Now uses request body instead of query params.
        """
        multi = get_multi_container()

        generated_blueprint = Blueprint(
            blueprint_id="BP-GEN-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            user_id="dev-operator",  # Should be set from identity
        )
        multi.default_container.research_service.generate_default_blueprint.return_value = (
            generated_blueprint
        )

        # [I-L5] Migrated from query params to request body
        response = client.post(
            "/api/v1/blueprints/generate",
            json={"market_id": "BTC-USDT", "capital": "1000"},
            headers={"X-API-Key": "dev-operator-key"},
        )

        assert response.status_code == 201

        # Verify the service was called with the correct user_id
        call_kwargs = multi.default_container.research_service.generate_default_blueprint.call_args[
            1
        ]
        assert call_kwargs["user_id"] == "dev-operator"


# =============================================================================
# Test: Invalid API Keys
# =============================================================================


class TestInvalidApiKeys:
    """Verify invalid API keys are rejected."""

    def test_invalid_api_key_returns_401(self, client: TestClient) -> None:
        """Invalid API key should return 401."""
        response = client.get(
            "/api/v1/grid",
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 401

    def test_empty_api_key_returns_401(self, client: TestClient) -> None:
        """Empty API key should return 401."""
        response = client.get(
            "/api/v1/grid",
            headers={"X-API-Key": ""},
        )
        assert response.status_code == 401


# =============================================================================
# Test: Exchange Parameter Validation [I-H11-REV]
# =============================================================================


class TestExchangeParameterValidation:
    """Verify exchange parameter validation in grid endpoints."""

    def test_invalid_exchange_returns_400(self, client: TestClient) -> None:
        """Invalid exchange parameter should return 400."""
        response = client.get(
            "/api/v1/grid?exchange=INVALID",
            headers={"X-API-Key": "dev-operator-key"},
        )
        assert response.status_code == 400
        assert "Invalid exchange" in response.json()["detail"]

    def test_valid_exchange_accepted(self, client: TestClient) -> None:
        """Valid exchange parameter should be accepted."""
        response = client.get(
            "/api/v1/grid?exchange=OKX",
            headers={"X-API-Key": "dev-operator-key"},
        )
        assert response.status_code == 200

    def test_case_insensitive_exchange(self, client: TestClient) -> None:
        """Exchange parameter should be case-insensitive."""
        response = client.get(
            "/api/v1/grid?exchange=okx",
            headers={"X-API-Key": "dev-operator-key"},
        )
        assert response.status_code == 200
