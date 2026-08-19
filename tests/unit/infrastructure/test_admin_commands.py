"""
Tests for Admin Telegram commands [Phase 12].

Verifies:
1. Admin authorization (check_admin_authorization)
2. /admin sub-command dispatch
3. Each sub-command returns formatted output
4. Non-admin users are rejected
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading_grid.infrastructure.telegram.handlers._auth import check_admin_authorization
from trading_grid.infrastructure.telegram.handlers.admin_commands import (
    ADMIN_HELP_TEXT,
    _admin_alerts,
    _admin_ingestion,
    _admin_ml_status,
    _admin_performance,
    _admin_training,
    _fmt_dt,
    _load_pipeline_state,
    cmd_admin,
)


def _make_message(user_id=12345, text="/admin"):
    """Create a mock Message."""
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.first_name = "Admin"
    msg.from_user.username = "adminuser"
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_container():
    """Create a mock service container."""
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
    metrics = MagicMock()
    metrics.orders_submitted = 10
    metrics.orders_filled = 8
    metrics.fill_rate = Decimal("80")
    metrics.avg_order_latency_ms = 45.0
    metrics.error_count = 0
    metrics.emergency_stops = 0
    container.demo_service.get_all_metrics.return_value = metrics

    # Monitoring service
    container.monitoring_service = MagicMock()
    container.monitoring_service.get_dashboard_data.return_value = {
        "environment": "DEMO",
        "system_healthy": True,
        "active_alerts": [],
        "critical_alerts": 0,
    }

    return container


# =============================================================================
# Test: check_admin_authorization
# =============================================================================


class TestCheckAdminAuthorization:
    """Verify admin authorization logic."""

    @pytest.mark.asyncio
    async def test_admin_user_id_config_grants_access(self):
        """User matching TELEGRAM_ADMIN_USER_ID is granted admin access."""
        msg = _make_message(user_id=99999)

        with patch(
            "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
        ) as mock_settings:
            mock_settings.return_value.telegram.admin_user_id = 99999
            result = await check_admin_authorization(msg)

        assert result is True

    @pytest.mark.asyncio
    async def test_db_system_admin_grants_access(self):
        """User with authorization_level >= 5 in DB is granted admin access."""
        msg = _make_message(user_id=12345)

        mock_user = MagicMock()
        mock_user.authorization_level = 5

        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
            ) as mock_settings,
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth._user_service"
            ) as mock_user_service,
        ):
            mock_settings.return_value.telegram.admin_user_id = None
            mock_user_service.get_user_by_telegram = AsyncMock(return_value=mock_user)
            result = await check_admin_authorization(msg)

        assert result is True

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self):
        """Non-admin user is rejected with message."""
        msg = _make_message(user_id=12345)

        mock_user = MagicMock()
        mock_user.authorization_level = 2  # Below SYSTEM_ADMIN

        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
            ) as mock_settings,
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth._user_service"
            ) as mock_user_service,
        ):
            mock_settings.return_value.telegram.admin_user_id = None
            mock_user_service.get_user_by_telegram = AsyncMock(return_value=mock_user)
            result = await check_admin_authorization(msg)

        assert result is False
        msg.answer.assert_called_once()
        assert "Admin Access Required" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_open_access_does_not_grant_admin(self):
        """Open access mode does NOT grant admin access."""
        msg = _make_message(user_id=12345)

        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
            ) as mock_settings,
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth._user_service"
            ) as mock_user_service,
        ):
            mock_settings.return_value.telegram.admin_user_id = None
            mock_settings.return_value.telegram.open_access = True
            mock_user_service.get_user_by_telegram = AsyncMock(return_value=None)
            result = await check_admin_authorization(msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_no_from_user_rejected(self):
        """Message without from_user is rejected."""
        msg = AsyncMock()
        msg.from_user = None
        msg.answer = AsyncMock()

        result = await check_admin_authorization(msg)
        assert result is False


# =============================================================================
# Test: cmd_admin dispatch
# =============================================================================


class TestCmdAdminDispatch:
    """Verify /admin sub-command dispatch."""

    @pytest.mark.asyncio
    async def test_no_subcommand_shows_help(self):
        """/admin without sub-command shows help text."""
        msg = _make_message(text="/admin")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.check_admin_authorization",
            new=AsyncMock(return_value=True),
        ):
            await cmd_admin(msg)

        msg.answer.assert_called_once()
        assert "Admin Dashboard" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_unknown_subcommand_shows_help(self):
        """/admin unknown shows help text."""
        msg = _make_message(text="/admin unknown")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.check_admin_authorization",
            new=AsyncMock(return_value=True),
        ):
            await cmd_admin(msg)

        msg.answer.assert_called_once()
        assert "Admin Dashboard" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_non_admin_rejected(self):
        """Non-admin user cannot access /admin."""
        msg = _make_message(text="/admin ml_status")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.check_admin_authorization",
            new=AsyncMock(return_value=False),
        ):
            await cmd_admin(msg)

        # Should not proceed to sub-command
        msg.answer.assert_not_called()


# =============================================================================
# Test: _admin_ml_status
# =============================================================================


class TestAdminMLStatus:
    """Verify /admin ml_status output."""

    @pytest.mark.asyncio
    async def test_ml_status_shows_model_info(self):
        """ml_status displays ML model information."""
        msg = _make_message(text="/admin ml_status")
        container = _make_container()

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=container,
        ):
            await _admin_ml_status(msg)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "ML Model Status" in text
        assert "ML" in text  # ranking mode
        assert "6" in text  # models loaded

    @pytest.mark.asyncio
    async def test_ml_status_no_container(self):
        """ml_status handles missing container gracefully."""
        msg = _make_message(text="/admin ml_status")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=None,
        ):
            await _admin_ml_status(msg)

        msg.answer.assert_called_once()
        assert "not initialized" in msg.answer.call_args[0][0]


# =============================================================================
# Test: _admin_training
# =============================================================================


class TestAdminTraining:
    """Verify /admin training output."""

    @pytest.mark.asyncio
    async def test_training_shows_pipeline_state(self):
        """training displays pipeline state information."""
        msg = _make_message(text="/admin training")

        mock_state = {
            "last_training": "2026-08-17T17:31:51+00:00",
            "last_ingest": "2026-08-17T17:29:37+00:00",
            "last_promotion": "2026-08-17T17:32:56+00:00",
            "dataset_observations": 1200,
            "val_roc_auc": 0.559,
            "walk_forward_mean_roc_auc": 0.587,
            "trained_models": ["model-1", "model-2"],
            "promoted_model": "model-1",
        }

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands._load_pipeline_state",
            return_value=mock_state,
        ):
            await _admin_training(msg)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Training Pipeline" in text
        assert "1200" in text
        assert "0.559" in text

    @pytest.mark.asyncio
    async def test_training_no_state(self):
        """training handles missing pipeline state gracefully."""
        msg = _make_message(text="/admin training")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands._load_pipeline_state",
            return_value=None,
        ):
            await _admin_training(msg)

        msg.answer.assert_called_once()
        assert "No pipeline state found" in msg.answer.call_args[0][0]


# =============================================================================
# Test: _admin_performance
# =============================================================================


class TestAdminPerformance:
    """Verify /admin performance output."""

    @pytest.mark.asyncio
    async def test_performance_shows_summary(self):
        """performance displays grid performance summary."""
        msg = _make_message(text="/admin performance")
        container = _make_container()

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=container,
        ):
            await _admin_performance(msg)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Grid Performance" in text
        assert "8/10" in text  # orders filled/submitted

    @pytest.mark.asyncio
    async def test_performance_aggregates_pnl(self):
        """performance aggregates P&L from sessions."""
        msg = _make_message(text="/admin performance")
        container = _make_container()

        # Add a session with P&L
        session = MagicMock()
        session.status = "RUNNING"
        session.grid_runtime.realized_pnl = Decimal("10.5")
        session.grid_runtime.unrealized_pnl = Decimal("2.5")
        session.grid_runtime.deployed_capital = Decimal("500")
        container.demo_service.get_all_sessions.return_value = [session]

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=container,
        ):
            await _admin_performance(msg)

        text = msg.answer.call_args[0][0]
        assert "+10.50" in text  # realized P&L
        assert "+2.50" in text  # unrealized P&L


# =============================================================================
# Test: _admin_alerts
# =============================================================================


class TestAdminAlerts:
    """Verify /admin alerts output."""

    @pytest.mark.asyncio
    async def test_alerts_shows_healthy(self):
        """alerts displays healthy system status."""
        msg = _make_message(text="/admin alerts")
        container = _make_container()

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=container,
        ):
            await _admin_alerts(msg)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Monitoring Alerts" in text
        assert "Healthy" in text
        assert "No active alerts" in text

    @pytest.mark.asyncio
    async def test_alerts_shows_active_alerts(self):
        """alerts displays active alerts."""
        msg = _make_message(text="/admin alerts")
        container = _make_container()
        container.monitoring_service.get_dashboard_data.return_value = {
            "system_healthy": False,
            "active_alerts": [
                {"severity": "CRITICAL", "message": "High error rate detected"},
            ],
            "critical_alerts": 1,
        }

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands.get_service_container",
            return_value=container,
        ):
            await _admin_alerts(msg)

        text = msg.answer.call_args[0][0]
        assert "UNHEALTHY" in text
        assert "CRITICAL" in text
        assert "High error rate" in text


# =============================================================================
# Test: Helper functions
# =============================================================================


class TestHelperFunctions:
    """Verify helper functions."""

    def test_fmt_dt_valid(self):
        """_fmt_dt formats valid ISO datetime."""
        result = _fmt_dt("2026-08-17T17:31:51+00:00")
        assert "2026-08-17" in result
        assert "17:31" in result

    def test_fmt_dt_none(self):
        """_fmt_dt returns dash for None."""
        assert _fmt_dt(None) == "—"

    def test_fmt_dt_invalid(self):
        """_fmt_dt returns original for invalid format."""
        assert _fmt_dt("not-a-date") == "not-a-date"

    def test_load_pipeline_state_missing_file(self):
        """_load_pipeline_state returns None when file missing."""
        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands._PIPELINE_STATE_PATH"
        ) as mock_path:
            mock_path.exists.return_value = False
            result = _load_pipeline_state()
        assert result is None


# =============================================================================
# Test: _admin_ingestion
# =============================================================================


class TestAdminIngestion:
    """Verify /admin ingestion output."""

    @pytest.mark.asyncio
    async def test_ingestion_shows_freshness(self):
        """ingestion displays data freshness information."""
        msg = _make_message(text="/admin ingestion")

        mock_state = {
            "last_ingest": "2026-08-19T10:00:00+00:00",
            "ingested_markets": ["BTC-USDT", "ETH-USDT", "SOL-USDT"],
            "total_candles": 38880,
            "candles_per_market": 4320,
            "exchange": "BINANCE",
            "interval": "1H",
        }

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands._load_pipeline_state",
            return_value=mock_state,
        ):
            await _admin_ingestion(msg)

        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "Data Ingestion" in text
        assert "BINANCE" in text
        assert "38,880" in text  # total candles with comma
        assert "BTC-USDT" in text

    @pytest.mark.asyncio
    async def test_ingestion_no_state(self):
        """ingestion handles missing pipeline state gracefully."""
        msg = _make_message(text="/admin ingestion")

        with patch(
            "trading_grid.infrastructure.telegram.handlers.admin_commands._load_pipeline_state",
            return_value=None,
        ):
            await _admin_ingestion(msg)

        msg.answer.assert_called_once()
        assert "No pipeline state found" in msg.answer.call_args[0][0]

    @pytest.mark.asyncio
    async def test_ingestion_dispatch(self):
        """/admin ingestion dispatches to _admin_ingestion."""
        msg = _make_message(text="/admin ingestion")

        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers.admin_commands.check_admin_authorization",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "trading_grid.infrastructure.telegram.handlers.admin_commands._admin_ingestion",
                new=AsyncMock(),
            ) as mock_ingestion,
        ):
            await cmd_admin(msg)

        mock_ingestion.assert_called_once_with(msg)
