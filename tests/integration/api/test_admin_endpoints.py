"""
Integration tests for Admin API endpoints [Phase 12].

Verifies end-to-end HTTP layer behavior for admin dashboard endpoints:
1. Authentication required (401 without credentials)
2. RBAC: SYSTEM_ADMIN (Level 5) required — VIEWER/OPERATOR get 403
3. All 6 admin endpoints return correct data for admin
4. Training run trigger returns 202 and prevents concurrent runs
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from trading_grid.api.middleware.auth import AuthMiddleware
from trading_grid.api.routes.dependencies import set_multi_container
from trading_grid.application.services.demo_trading import DemoMetrics

# =============================================================================
# Test Fixtures
# =============================================================================


def _create_test_app() -> FastAPI:
    """Create a minimal test app with auth middleware and admin router."""
    from trading_grid.api.routes import admin, health

    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(health.router, tags=["Health"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
    return app


def _create_mock_container() -> MagicMock:
    """Create a mock service container with admin-relevant services."""
    container = MagicMock()

    # Research service
    container.research_service = MagicMock()
    container.research_service.get_service_status.return_value = {
        "last_ranking_at": "2026-08-19T10:00:00+00:00",
        "last_ranking_mode": "ml",
        "blueprints_generated": 5,
        "simulations_run": 3,
        "adapter_connected": True,
        "ml_available": True,
        "ml_models_loaded": 6,
    }
    container.research_service.registry.list_models.return_value = []

    # Demo service
    container.demo_service = MagicMock()
    container.demo_service.get_all_sessions.return_value = []
    container.demo_service.get_all_metrics.return_value = DemoMetrics()

    # Monitoring service
    container.monitoring_service = MagicMock()
    container.monitoring_service.get_dashboard_data.return_value = {
        "environment": "DEMO",
        "system_healthy": True,
        "health_checks": {},
        "active_alerts": [],
        "critical_alerts": 0,
        "total_alerts": 0,
        "metrics": {},
        "generated_at": "2026-08-19T10:00:00+00:00",
    }
    container.monitoring_service.get_monitoring_summary.return_value = {
        "environment": "DEMO",
        "system_healthy": True,
        "active_alerts": 0,
        "critical_alerts": 0,
        "total_alerts": 0,
        "alert_rules": 5,
        "health_checks": 0,
        "metrics_tracked": 2,
    }

    return container


def _create_mock_multi_container() -> MagicMock:
    """Create a mock multi-exchange container."""
    multi = MagicMock()
    default_container = _create_mock_container()
    multi.default_container = default_container
    multi.get_container.return_value = default_container
    return multi


@pytest.fixture
def client() -> TestClient:
    """Create test client with mocked container."""
    app = _create_test_app()
    multi = _create_mock_multi_container()
    set_multi_container(multi)
    return TestClient(app)


ADMIN_HEADERS = {"X-API-Key": "dev-admin-key"}
OPERATOR_HEADERS = {"X-API-Key": "dev-operator-key"}
VIEWER_HEADERS = {"X-API-Key": "dev-viewer-key"}

ADMIN_ENDPOINTS = [
    "/api/v1/admin/ml/status",
    "/api/v1/admin/ml/metrics",
    "/api/v1/admin/training/status",
    "/api/v1/admin/training/history",
    "/api/v1/admin/performance/grids",
    "/api/v1/admin/alerts",
    "/api/v1/admin/ingestion/status",
    "/api/v1/admin/models",
]


# =============================================================================
# Test: Authentication Required (401)
# =============================================================================


class TestAdminAuthentication:
    """Verify admin endpoints require authentication."""

    @pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
    def test_admin_endpoints_require_auth(self, client: TestClient, endpoint: str) -> None:
        """All admin GET endpoints return 401 without authentication."""
        response = client.get(endpoint)
        assert response.status_code == 401

    def test_training_run_requires_auth(self, client: TestClient) -> None:
        """POST /api/v1/admin/training/run returns 401 without auth."""
        response = client.post("/api/v1/admin/training/run", json={})
        assert response.status_code == 401


# =============================================================================
# Test: RBAC — SYSTEM_ADMIN Required (403)
# =============================================================================


class TestAdminRBAC:
    """Verify admin endpoints require SYSTEM_ADMIN (Level 5)."""

    @pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
    def test_viewer_denied_on_admin_endpoints(
        self, client: TestClient, endpoint: str
    ) -> None:
        """VIEWER role gets 403 on all admin endpoints."""
        response = client.get(endpoint, headers=VIEWER_HEADERS)
        assert response.status_code == 403
        assert "SYSTEM_ADMIN" in response.json()["detail"]

    @pytest.mark.parametrize("endpoint", ADMIN_ENDPOINTS)
    def test_operator_denied_on_admin_endpoints(
        self, client: TestClient, endpoint: str
    ) -> None:
        """DEMO_OPERATOR role gets 403 on all admin endpoints."""
        response = client.get(endpoint, headers=OPERATOR_HEADERS)
        assert response.status_code == 403
        assert "SYSTEM_ADMIN" in response.json()["detail"]

    def test_viewer_denied_training_run(self, client: TestClient) -> None:
        """VIEWER cannot trigger training runs."""
        response = client.post(
            "/api/v1/admin/training/run", json={}, headers=VIEWER_HEADERS
        )
        assert response.status_code == 403

    def test_operator_denied_training_run(self, client: TestClient) -> None:
        """DEMO_OPERATOR cannot trigger training runs."""
        response = client.post(
            "/api/v1/admin/training/run", json={}, headers=OPERATOR_HEADERS
        )
        assert response.status_code == 403


# =============================================================================
# Test: ML Status Endpoint
# =============================================================================


class TestMLStatusEndpoint:
    """Verify GET /api/v1/admin/ml/status."""

    def test_admin_can_get_ml_status(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access ML status."""
        response = client.get("/api/v1/admin/ml/status", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["ml_available"] is True
        assert data["ranking_mode"] == "ml"
        assert data["models_loaded"] == 6
        assert data["blueprints_generated"] == 5
        assert data["simulations_run"] == 3
        assert isinstance(data["active_models"], list)


# =============================================================================
# Test: Training Status Endpoint
# =============================================================================


class TestTrainingStatusEndpoint:
    """Verify GET /api/v1/admin/training/status."""

    def test_admin_can_get_training_status(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access training status."""
        response = client.get("/api/v1/admin/training/status", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        # pipeline_state.json exists in this repo
        assert "pipeline_state_available" in data

    def test_training_status_graceful_when_no_state(self, client: TestClient) -> None:
        """Training status returns gracefully when pipeline state missing."""
        with patch(
            "trading_grid.api.routes.admin._load_pipeline_state", return_value=None
        ):
            response = client.get("/api/v1/admin/training/status", headers=ADMIN_HEADERS)
            assert response.status_code == 200
            data = response.json()
            assert data["pipeline_state_available"] is False


# =============================================================================
# Test: Training Run Trigger Endpoint
# =============================================================================


class TestTrainingRunEndpoint:
    """Verify POST /api/v1/admin/training/run."""

    def test_admin_can_trigger_training(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can trigger a training run (202 Accepted)."""
        # Patch subprocess to avoid actually running training
        mock_proc = AsyncMock()
        mock_proc.wait = AsyncMock(return_value=None)
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=mock_proc)):
            response = client.post(
                "/api/v1/admin/training/run", json={}, headers=ADMIN_HEADERS
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] in ("started", "already_running")
        assert data["triggered_at"] is not None

    def test_concurrent_training_run_rejected(self, client: TestClient) -> None:
        """A second training run while one is running returns already_running."""
        import asyncio

        from trading_grid.api.routes import admin as admin_module

        # Simulate a running task
        async def _never_done() -> None:
            await asyncio.sleep(3600)

        loop_task = asyncio.get_event_loop_policy().new_event_loop().create_task(_never_done())
        admin_module._training_tasks["TRAIN-TEST"] = loop_task

        try:
            response = client.post(
                "/api/v1/admin/training/run", json={}, headers=ADMIN_HEADERS
            )
            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "already_running"
        finally:
            loop_task.cancel()
            admin_module._training_tasks.pop("TRAIN-TEST", None)


# =============================================================================
# Test: Grid Performance Endpoint
# =============================================================================


class TestGridPerformanceEndpoint:
    """Verify GET /api/v1/admin/performance/grids."""

    def test_admin_can_get_grid_performance(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access grid performance summary."""
        response = client.get(
            "/api/v1/admin/performance/grids", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "DEMO"
        assert "summary" in data
        summary = data["summary"]
        assert summary["total_sessions"] == 0
        assert summary["total_orders_submitted"] == 0
        assert "generated_at" in data

    def test_grid_performance_aggregates_sessions(self, client: TestClient) -> None:
        """Grid performance aggregates P&L from sessions."""
        from trading_grid.api.routes.dependencies import get_multi_container

        multi = get_multi_container()

        # Create mock session with P&L
        session = MagicMock()
        session.status = "RUNNING"
        session.grid_runtime.realized_pnl = Decimal("10.5")
        session.grid_runtime.unrealized_pnl = Decimal("2.5")
        session.grid_runtime.deployed_capital = Decimal("500")

        multi.default_container.demo_service.get_all_sessions.return_value = [session]

        metrics = DemoMetrics()
        metrics.orders_submitted = 10
        metrics.orders_filled = 8
        multi.default_container.demo_service.get_all_metrics.return_value = metrics

        response = client.get(
            "/api/v1/admin/performance/grids", headers=ADMIN_HEADERS
        )
        assert response.status_code == 200
        summary = response.json()["summary"]
        assert summary["total_sessions"] == 1
        assert summary["active_sessions"] == 1
        assert Decimal(summary["total_realized_pnl"]) == Decimal("10.5")
        assert Decimal(summary["total_unrealized_pnl"]) == Decimal("2.5")
        assert summary["total_orders_submitted"] == 10
        assert summary["total_orders_filled"] == 8


# =============================================================================
# Test: Alerts Endpoint
# =============================================================================


class TestAlertsEndpoint:
    """Verify GET /api/v1/admin/alerts."""

    def test_admin_can_get_alerts(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access alerts."""
        response = client.get("/api/v1/admin/alerts", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["environment"] == "DEMO"
        assert data["system_healthy"] is True
        assert data["total_alerts"] == 0
        assert isinstance(data["alerts"], list)
        assert data["alert_rules_count"] == 5


# =============================================================================
# Test: Ingestion Status Endpoint
# =============================================================================


class TestIngestionStatusEndpoint:
    """Verify GET /api/v1/admin/ingestion/status."""

    def test_admin_can_get_ingestion_status(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access ingestion status."""
        response = client.get("/api/v1/admin/ingestion/status", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert "pipeline_state_available" in data

    def test_ingestion_status_graceful_when_no_state(self, client: TestClient) -> None:
        """Ingestion status returns gracefully when pipeline state missing."""
        with patch(
            "trading_grid.api.routes.admin._load_pipeline_state", return_value=None
        ):
            response = client.get(
                "/api/v1/admin/ingestion/status", headers=ADMIN_HEADERS
            )
            assert response.status_code == 200
            data = response.json()
            assert data["pipeline_state_available"] is False

    def test_ingestion_status_with_mocked_state(self, client: TestClient) -> None:
        """Ingestion status parses pipeline state correctly."""
        mock_state = {
            "last_ingest": "2026-08-17T17:29:37.824365+00:00",
            "ingested_markets": ["BTC-USDT", "ETH-USDT"],
            "total_candles": 8640,
            "candles_per_market": 4320,
            "exchange": "BINANCE",
            "interval": "1H",
        }
        with patch(
            "trading_grid.api.routes.admin._load_pipeline_state",
            return_value=mock_state,
        ):
            response = client.get(
                "/api/v1/admin/ingestion/status", headers=ADMIN_HEADERS
            )
            assert response.status_code == 200
            data = response.json()
            assert data["pipeline_state_available"] is True
            assert data["ingested_markets"] == ["BTC-USDT", "ETH-USDT"]
            assert data["total_candles"] == 8640
            assert data["exchange"] == "BINANCE"
            assert data["data_freshness_hours"] is not None


# =============================================================================
# Test: Model Promote Endpoint
# =============================================================================


class TestModelPromoteEndpoint:
    """Verify POST /api/v1/admin/models/{model_id}/promote."""

    def test_promote_requires_auth(self, client: TestClient) -> None:
        """Promote endpoint requires authentication."""
        response = client.post(
            "/api/v1/admin/models/test-model/promote", json={"force": False}
        )
        assert response.status_code == 401

    def test_promote_requires_admin(self, client: TestClient) -> None:
        """Promote endpoint requires SYSTEM_ADMIN."""
        response = client.post(
            "/api/v1/admin/models/test-model/promote",
            json={"force": False},
            headers=VIEWER_HEADERS,
        )
        assert response.status_code == 403

    def test_promote_model_not_found(self, client: TestClient) -> None:
        """Promote returns 404 for non-existent model."""
        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch(
            "trading_grid.api.routes.admin.get_default_container"
        ) as mock_container:
            mock_container.return_value.research_service.registry = mock_registry
            response = client.post(
                "/api/v1/admin/models/nonexistent-model/promote",
                json={"force": False},
                headers=ADMIN_HEADERS,
            )
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_promote_model_success(self, client: TestClient) -> None:
        """Promote succeeds when model passes validation."""
        from datetime import UTC, datetime

        mock_entry = MagicMock()
        mock_entry.model_id = "test-model"
        mock_entry.promoted_at = datetime.now(UTC)

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_entry
        mock_registry.promote.return_value = (True, [])

        with patch(
            "trading_grid.api.routes.admin.get_default_container"
        ) as mock_container:
            mock_container.return_value.research_service.registry = mock_registry
            response = client.post(
                "/api/v1/admin/models/test-model/promote",
                json={"force": False, "notes": "Test promotion"},
                headers=ADMIN_HEADERS,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["model_id"] == "test-model"
            assert data["promoted_at"] is not None

    def test_promote_model_blocked_by_thresholds(self, client: TestClient) -> None:
        """Promote blocked when metrics below threshold (force=False)."""
        mock_entry = MagicMock()
        mock_entry.model_id = "test-model"

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_entry
        mock_registry.promote.return_value = (False, ["ROC-AUC below threshold"])

        with patch(
            "trading_grid.api.routes.admin.get_default_container"
        ) as mock_container:
            mock_container.return_value.research_service.registry = mock_registry
            response = client.post(
                "/api/v1/admin/models/test-model/promote",
                json={"force": False},
                headers=ADMIN_HEADERS,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False
            assert "ROC-AUC below threshold" in data["issues"]

    def test_promote_model_force(self, client: TestClient) -> None:
        """Promote with force=True bypasses threshold validation."""
        from datetime import UTC, datetime

        mock_entry = MagicMock()
        mock_entry.model_id = "test-model"
        mock_entry.promoted_at = datetime.now(UTC)

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_entry
        mock_registry.promote.return_value = (True, ["ROC-AUC below threshold"])

        with patch(
            "trading_grid.api.routes.admin.get_default_container"
        ) as mock_container:
            mock_container.return_value.research_service.registry = mock_registry
            response = client.post(
                "/api/v1/admin/models/test-model/promote",
                json={"force": True, "notes": "Forced promotion"},
                headers=ADMIN_HEADERS,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            # Verify force was passed to registry
            mock_registry.promote.assert_called_once()
            call_kwargs = mock_registry.promote.call_args[1]
            assert call_kwargs["force"] is True


# =============================================================================
# Test: ML Metrics Endpoint
# =============================================================================


def _create_mock_registry_entry(
    model_id: str,
    model_type: str = "primary_classifier",
    model_family: str = "lightgbm",
    status: str = "DEPLOYED",
    val_roc_auc: float | None = 0.75,
    train_samples: int = 1000,
) -> MagicMock:
    """Create a mock registry entry with the attributes the endpoint reads."""
    from trading_grid.research.models.trainer import (
        ModelFamily,
        ModelStatus,
        ModelType,
    )

    entry = MagicMock()
    entry.model_id = model_id
    entry.model_type = ModelType(model_type)
    entry.status = ModelStatus(status)
    entry.registered_at = None
    entry.promoted_at = None
    entry.archived_at = None
    entry.config = MagicMock()
    entry.config.model_family = ModelFamily(model_family)
    entry.config.feature_version = "F-ML-001"
    entry.config.label_version = "L-001"
    entry.config.dataset_version = "D-001"
    entry.validation_metrics = {"roc_auc": val_roc_auc} if val_roc_auc else {}
    entry.train_metrics = {"train_samples": train_samples}
    entry.promotion_notes = ""
    return entry


class TestMLMetricsEndpoint:
    """Verify GET /api/v1/admin/ml/metrics."""

    def test_admin_can_get_ml_metrics(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access ML metrics."""
        response = client.get("/api/v1/admin/ml/metrics", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total_models"] == 0
        assert data["deployed_models"] == 0
        assert data["generated_at"] is not None

    def test_ml_metrics_aggregates_models(self, client: TestClient) -> None:
        """ML metrics aggregates model counts and ROC-AUC."""
        from trading_grid.api.routes.dependencies import get_multi_container

        multi = get_multi_container()
        registry = multi.default_container.research_service.registry

        entries = [
            _create_mock_registry_entry(
                "model-a", model_type="primary_classifier", status="DEPLOYED", val_roc_auc=0.80
            ),
            _create_mock_registry_entry(
                "model-b", model_type="net_pnl_regressor", status="TRAINED", val_roc_auc=0.70
            ),
            _create_mock_registry_entry(
                "model-c", model_type="primary_classifier", status="ARCHIVED", val_roc_auc=0.65
            ),
        ]
        registry.list_models.return_value = entries

        response = client.get("/api/v1/admin/ml/metrics", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total_models"] == 3
        assert data["deployed_models"] == 1
        assert data["archived_models"] == 1
        assert data["trained_models"] == 1
        assert data["models_by_type"]["primary_classifier"] == 2
        assert data["models_by_type"]["net_pnl_regressor"] == 1
        assert data["models_by_status"]["DEPLOYED"] == 1
        assert data["avg_val_roc_auc"] == 0.7167
        assert data["best_val_roc_auc"] == 0.80
        assert data["best_model_id"] == "model-a"


# =============================================================================
# Test: Training History Endpoint
# =============================================================================


class TestTrainingHistoryEndpoint:
    """Verify GET /api/v1/admin/training/history."""

    def test_admin_can_get_training_history(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can access training history."""
        response = client.get("/api/v1/admin/training/history", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total_runs"] >= 0
        assert isinstance(data["runs"], list)
        assert data["generated_at"] is not None

    def test_training_history_graceful_when_no_state(self, client: TestClient) -> None:
        """Training history returns empty when pipeline state missing."""
        with patch(
            "trading_grid.api.routes.admin._load_pipeline_state", return_value=None
        ):
            response = client.get(
                "/api/v1/admin/training/history", headers=ADMIN_HEADERS
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total_runs"] == 0
            assert data["runs"] == []

    def test_training_history_with_state(self, client: TestClient) -> None:
        """Training history parses pipeline state into a run entry."""
        mock_state = {
            "last_training": "2026-08-17T17:29:37.824365+00:00",
            "trained_models": ["model-a", "model-b"],
            "val_roc_auc": 0.53,
            "notes": "Synthetic labels",
        }
        with patch(
            "trading_grid.api.routes.admin._load_pipeline_state",
            return_value=mock_state,
        ):
            response = client.get(
                "/api/v1/admin/training/history", headers=ADMIN_HEADERS
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total_runs"] == 1
            run = data["runs"][0]
            assert run["run_id"] == "latest"
            assert run["status"] == "completed"
            assert run["models_trained"] == ["model-a", "model-b"]
            assert run["val_roc_auc"] == 0.53
            assert run["notes"] == "Synthetic labels"


# =============================================================================
# Test: Model List Endpoint
# =============================================================================


class TestModelListEndpoint:
    """Verify GET /api/v1/admin/models."""

    def test_admin_can_list_models(self, client: TestClient) -> None:
        """SYSTEM_ADMIN can list all models."""
        response = client.get("/api/v1/admin/models", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["models"] == []
        assert data["generated_at"] is not None

    def test_model_list_returns_entries(self, client: TestClient) -> None:
        """Model list returns registry entries with metadata."""
        from trading_grid.api.routes.dependencies import get_multi_container

        multi = get_multi_container()
        registry = multi.default_container.research_service.registry

        entries = [
            _create_mock_registry_entry(
                "model-a",
                model_type="primary_classifier",
                model_family="lightgbm",
                status="DEPLOYED",
                val_roc_auc=0.80,
                train_samples=32400,
            ),
            _create_mock_registry_entry(
                "model-b",
                model_type="net_pnl_regressor",
                model_family="lightgbm",
                status="TRAINED",
                val_roc_auc=0.70,
                train_samples=32400,
            ),
        ]
        registry.list_models.return_value = entries

        response = client.get("/api/v1/admin/models", headers=ADMIN_HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["models"]) == 2

        model_a = data["models"][0]
        assert model_a["model_id"] == "model-a"
        assert model_a["model_type"] == "primary_classifier"
        assert model_a["model_family"] == "lightgbm"
        assert model_a["status"] == "DEPLOYED"
        assert model_a["val_roc_auc"] == 0.80
        assert model_a["train_samples"] == 32400
        assert model_a["feature_version"] == "F-ML-001"
        assert model_a["label_version"] == "L-001"
        assert model_a["dataset_version"] == "D-001"
