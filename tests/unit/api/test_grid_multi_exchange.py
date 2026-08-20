"""
Tests for multi-exchange grid control (Phase 10.2 [I-H11-REV]).

Verifies:
1. Multi-exchange query support (list grids from all exchanges)
2. Exchange query parameter validation
3. RBAC per-user filtering
4. Backward compatibility with default OKX
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from trading_grid.api.routes.grid import (
    VALID_EXCHANGES,
    _find_session_for_grid,
    get_grid,
    list_grids,
)
from trading_grid.application.services.authorization import Identity, Role


def make_identity(user_id: str = "user-1") -> Identity:
    """Create a test identity."""
    return Identity(
        identity_id=user_id,
        identity_type="HUMAN",
        role=Role.DEMO_OPERATOR,
    )


def make_mock_grid(grid_id: str, user_id: str | None = None):
    """Create a mock grid runtime."""
    grid = MagicMock()
    grid.grid_id = grid_id
    grid.market_id = "BTC-USDT"
    grid.status = "RUNNING"
    grid.user_id = user_id
    grid.blueprint.blueprint_id = f"BP-{grid_id}"
    grid.blueprint.total_capital = 1000
    grid.blueprint.sections = [MagicMock(), MagicMock()]
    grid.deployed_capital = 500
    grid.capital_utilization = 0.5
    grid.unrealized_pnl = 10
    grid.realized_pnl = 5
    grid.started_at = None
    return grid


class TestValidExchanges:
    """Tests for VALID_EXCHANGES constant."""

    def test_valid_exchanges_contains_all(self) -> None:
        """VALID_EXCHANGES contains OKX, BINANCE, BYBIT."""
        assert VALID_EXCHANGES == ("OKX", "BINANCE", "BYBIT")


class TestListGridsMultiExchange:
    """Tests for list_grids multi-exchange support."""

    @pytest.mark.asyncio
    async def test_list_grids_invalid_exchange_raises_400(self) -> None:
        """Invalid exchange parameter raises 400."""
        identity = make_identity()
        with pytest.raises(HTTPException) as exc:
            await list_grids(exchange="KRAKEN", identity=identity)
        assert exc.value.status_code == 400
        assert "Invalid exchange" in exc.value.detail

    @pytest.mark.asyncio
    async def test_list_grids_case_insensitive_exchange(self) -> None:
        """Exchange parameter is case-insensitive."""
        identity = make_identity()
        mock_container = MagicMock()
        mock_container.grid_engine.get_active_grids.return_value = []

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            result = await list_grids(exchange="okx", identity=identity)
            assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_grids_filters_by_user_ownership(self) -> None:
        """Users only see grids they own."""
        identity = make_identity("user-1")

        # Grid owned by user-1, grid owned by user-2, system grid (None)
        grid_own = make_mock_grid("GRID-1", user_id="user-1")
        grid_other = make_mock_grid("GRID-2", user_id="user-2")
        grid_system = make_mock_grid("GRID-3", user_id=None)

        mock_container = MagicMock()
        mock_container.grid_engine.get_active_grids.return_value = [
            grid_own,
            grid_other,
            grid_system,
        ]

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            result = await list_grids(exchange="OKX", identity=identity)
            # Should see own grid + system grid, not other user's grid
            assert result.total == 2
            grid_ids = [g.grid_id for g in result.grids]
            assert "GRID-1" in grid_ids
            assert "GRID-3" in grid_ids
            assert "GRID-2" not in grid_ids

    @pytest.mark.asyncio
    async def test_list_grids_all_exchanges(self) -> None:
        """Without exchange param, queries all exchanges."""
        identity = make_identity()

        mock_container = MagicMock()
        mock_container.grid_engine.get_active_grids.return_value = []

        mock_multi = MagicMock()
        mock_multi.get_container.return_value = mock_container

        with patch("trading_grid.api.routes.grid.get_multi_container", return_value=mock_multi):
            await list_grids(exchange=None, identity=identity)
            # Should query all 3 exchanges
            assert mock_multi.get_container.call_count == 3


class TestGetGridMultiExchange:
    """Tests for get_grid multi-exchange support."""

    @pytest.mark.asyncio
    async def test_get_grid_invalid_exchange_raises_400(self) -> None:
        """Invalid exchange parameter raises 400."""
        identity = make_identity()
        with pytest.raises(HTTPException) as exc:
            await get_grid(grid_id="GRID-1", exchange="KRAKEN", identity=identity)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_grid_not_found_raises_404(self) -> None:
        """Grid not found raises 404."""
        identity = make_identity()
        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = None

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            with pytest.raises(HTTPException) as exc:
                await get_grid(grid_id="GRID-1", exchange="OKX", identity=identity)
            assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_grid_other_users_grid_raises_403(self) -> None:
        """Accessing another user's grid raises 403."""
        identity = make_identity("user-1")
        grid = make_mock_grid("GRID-1", user_id="user-2")

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = grid

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            with pytest.raises(HTTPException) as exc:
                await get_grid(grid_id="GRID-1", exchange="OKX", identity=identity)
            assert exc.value.status_code == 403
            assert "Not authorized" in exc.value.detail

    @pytest.mark.asyncio
    async def test_get_grid_own_grid_succeeds(self) -> None:
        """Accessing own grid succeeds."""
        identity = make_identity("user-1")
        grid = make_mock_grid("GRID-1", user_id="user-1")

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = grid

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            result = await get_grid(grid_id="GRID-1", exchange="OKX", identity=identity)
            assert result.grid_id == "GRID-1"

    @pytest.mark.asyncio
    async def test_get_grid_system_grid_accessible_to_all(self) -> None:
        """System grids (user_id=None) are accessible to all users."""
        identity = make_identity("any-user")
        grid = make_mock_grid("GRID-1", user_id=None)

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = grid

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            result = await get_grid(grid_id="GRID-1", exchange="OKX", identity=identity)
            assert result.grid_id == "GRID-1"


class TestFindSessionForGrid:
    """Tests for _find_session_for_grid helper."""

    def test_find_session_invalid_exchange_raises_400(self) -> None:
        """Invalid exchange raises 400."""
        with pytest.raises(HTTPException) as exc:
            _find_session_for_grid("GRID-1", exchange="KRAKEN")
        assert exc.value.status_code == 400

    def test_find_session_not_found_raises_404(self) -> None:
        """Session not found raises 404."""
        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            with pytest.raises(HTTPException) as exc:
                _find_session_for_grid("GRID-1", exchange="OKX")
            assert exc.value.status_code == 404

    def test_find_session_returns_session_and_container(self) -> None:
        """Found session returns (session, container) tuple."""
        mock_session = MagicMock()
        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = mock_session

        with patch("trading_grid.api.routes.grid.get_container", return_value=mock_container):
            session, container = _find_session_for_grid("GRID-1", exchange="OKX")
            assert session is mock_session
            assert container is mock_container

    def test_find_session_searches_all_exchanges_when_no_exchange(self) -> None:
        """Without exchange param, searches all exchanges."""
        mock_session = MagicMock()
        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = mock_session

        mock_multi = MagicMock()
        mock_multi.get_container.return_value = mock_container

        with patch("trading_grid.api.routes.grid.get_multi_container", return_value=mock_multi):
            session, _container = _find_session_for_grid("GRID-1", exchange=None)
            assert session is mock_session
            # Should have searched exchanges
            assert mock_multi.get_container.call_count >= 1
