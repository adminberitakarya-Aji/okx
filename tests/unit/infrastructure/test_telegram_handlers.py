"""Tests for Telegram command and callback handlers."""

from unittest.mock import AsyncMock, MagicMock, patch

from trading_grid.infrastructure.telegram import handlers
from trading_grid.infrastructure.telegram.handlers import (
    _get_editable_message,
    callback_auth_create,
    callback_blueprint_detail,
    callback_grid_detail,
    callback_grid_pause,
    callback_grid_resume,
    callback_grid_start,
    callback_grid_stop,
    callback_menu_account,
    callback_menu_blueprint,
    callback_menu_grid,
    callback_menu_research,
    callback_menu_settings,
    callback_menu_simulate,
    callback_menu_top10,
    callback_nav_main,
    callback_noop,
    callback_settings_unlink,
    callback_simulate_history,
    callback_simulate_run,
    callback_unlink_confirm,
    check_authorization,
    check_callback_authorization,
    cmd_account,
    cmd_connect,
    cmd_disconnect,
    cmd_exchange,
    cmd_help,
    cmd_menu,
    cmd_start,
    cmd_status,
    cmd_stop_all,
    get_user_service,
    handle_unknown,
    is_authorized_user,
    register_handlers,
)


def _make_message(user_id=12345, first_name="Test", username="testuser", text="/start"):
    """Create a mock Message."""
    msg = AsyncMock()
    msg.from_user = MagicMock()
    msg.from_user.id = user_id
    msg.from_user.first_name = first_name
    msg.from_user.username = username
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_callback(user_id=12345, data="menu:research", first_name="Test"):
    """Create a mock CallbackQuery."""
    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.from_user.first_name = first_name
    cb.from_user.username = "testuser"
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = AsyncMock()
    cb.message.chat = MagicMock()
    cb.message.chat.id = 100
    cb.message.edit_text = AsyncMock()
    return cb


def _make_user(user_id="user-123"):
    """Create a mock user."""
    user = MagicMock()
    user.user_id = user_id
    return user


def _make_okx_integration(environment="DEMO", status="VERIFIED"):
    """Create a mock OKX integration."""
    okx = MagicMock()
    okx.environment = environment
    okx.status = status
    return okx


class TestGetEditableMessage:
    def test_returns_message(self):
        from aiogram.types import Message

        cb = MagicMock()
        msg = MagicMock(spec=Message)
        cb.message = msg
        assert _get_editable_message(cb) is msg

    def test_returns_none_for_none_message(self):
        cb = MagicMock()
        cb.message = None
        assert _get_editable_message(cb) is None

    def test_returns_none_for_non_message(self):
        cb = MagicMock()
        cb.message = "not a message"
        assert _get_editable_message(cb) is None


class TestGetUserService:
    def test_returns_user_service(self):
        service = get_user_service()
        assert service is not None


class TestIsAuthorizedUser:
    def test_authorized_when_in_allowlist(self):
        with patch(
            "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
        ) as mock_settings:
            mock_settings.return_value.telegram.allowed_user_ids = [12345]
            assert is_authorized_user(12345) is True

    def test_not_authorized_when_not_in_allowlist(self):
        with patch(
            "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
        ) as mock_settings:
            mock_settings.return_value.telegram.allowed_user_ids = [99999]
            assert is_authorized_user(12345) is False

    def test_not_authorized_when_allowlist_empty(self):
        with patch(
            "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
        ) as mock_settings:
            mock_settings.return_value.telegram.allowed_user_ids = []
            assert is_authorized_user(12345) is False


class TestCheckAuthorization:
    async def test_authorized_via_config(self):
        msg = _make_message(user_id=12345)
        with patch.object(handlers, "is_authorized_user", return_value=True):
            result = await check_authorization(msg)
        assert result is True

    async def test_authorized_via_database(self):
        msg = _make_message(user_id=12345)
        with (
            patch.object(handlers, "is_authorized_user", return_value=False),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=_make_user()),
        ):
            result = await check_authorization(msg)
        assert result is True

    async def test_not_authorized(self):
        msg = _make_message(user_id=12345)
        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
            ) as mock_settings,
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.is_authorized_user",
                return_value=False,
            ),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            mock_settings.return_value.telegram.open_access = False
            result = await check_authorization(msg)
        assert result is False
        msg.answer.assert_called_once()

    async def test_no_from_user(self):
        msg = _make_message()
        msg.from_user = None
        result = await check_authorization(msg)
        assert result is False


class TestCheckCallbackAuthorization:
    async def test_authorized_via_config(self):
        cb = _make_callback(user_id=12345)
        with patch.object(handlers, "is_authorized_user", return_value=True):
            result = await check_callback_authorization(cb)
        assert result is True

    async def test_authorized_via_database(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "is_authorized_user", return_value=False),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=_make_user()),
        ):
            result = await check_callback_authorization(cb)
        assert result is True

    async def test_not_authorized(self):
        cb = _make_callback(user_id=12345)
        with (
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.get_settings"
            ) as mock_settings,
            patch(
                "trading_grid.infrastructure.telegram.handlers._auth.is_authorized_user",
                return_value=False,
            ),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            mock_settings.return_value.telegram.open_access = False
            result = await check_callback_authorization(cb)
        assert result is False
        cb.answer.assert_called_once()


class TestCmdStart:
    async def test_new_user(self):
        msg = _make_message(user_id=12345)
        with patch.object(handlers._user_service, "get_user_by_telegram", return_value=None):
            await cmd_start(msg)
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        assert "Welcome" in call_args[0][0]

    async def test_returning_user(self):
        msg = _make_message(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await cmd_start(msg)
        msg.answer.assert_called_once()
        call_args = msg.answer.call_args
        assert "Welcome back" in call_args[0][0]

    async def test_no_from_user(self):
        msg = _make_message()
        msg.from_user = None
        await cmd_start(msg)
        msg.answer.assert_not_called()

    async def test_deep_link_token(self):
        msg = _make_message(user_id=12345, text="/start sometoken123")
        with patch.object(handlers._user_service, "get_user_by_telegram", return_value=None):
            await cmd_start(msg)
        msg.answer.assert_called_once()


class TestCmdHelp:
    async def test_authorized(self):
        msg = _make_message()
        with patch(
            "trading_grid.infrastructure.telegram.handlers.commands.check_authorization",
            return_value=True,
        ):
            await cmd_help(msg)
        msg.answer.assert_called_once()
        assert "Available Commands" in msg.answer.call_args[0][0]

    async def test_not_authorized(self):
        msg = _make_message()
        with patch(
            "trading_grid.infrastructure.telegram.handlers.commands.check_authorization",
            return_value=False,
        ):
            await cmd_help(msg)
        msg.answer.assert_not_called()


class TestCmdMenu:
    async def test_authorized_with_user(self):
        msg = _make_message(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await cmd_menu(msg)
        msg.answer.assert_called_once()

    async def test_no_user(self):
        msg = _make_message(user_id=12345)
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await cmd_menu(msg)
        msg.answer.assert_called_once()
        assert "/start" in msg.answer.call_args[0][0]

    async def test_no_from_user(self):
        msg = _make_message()
        msg.from_user = None
        with patch.object(handlers, "check_authorization", return_value=True):
            await cmd_menu(msg)
        msg.answer.assert_not_called()


class TestCmdStatus:
    async def test_authorized(self):
        msg = _make_message()
        with patch.object(handlers, "check_authorization", return_value=True):
            await cmd_status(msg)
        msg.answer.assert_called_once()
        assert "System Status" in msg.answer.call_args[0][0]


class TestCmdAccount:
    async def test_authorized_with_user(self):
        msg = _make_message(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await cmd_account(msg)
        msg.answer.assert_called_once()

    async def test_no_user(self):
        msg = _make_message(user_id=12345)
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await cmd_account(msg)
        assert "/start" in msg.answer.call_args[0][0]


class TestCmdStopAll:
    async def test_authorized(self):
        msg = _make_message()
        mock_container = MagicMock()
        mock_container.demo_service.emergency_stop_all.return_value = []
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await cmd_stop_all(msg)
        msg.answer.assert_called_once()
        assert "Emergency Stop" in msg.answer.call_args[0][0]

    async def test_no_container(self):
        msg = _make_message()
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await cmd_stop_all(msg)
        msg.answer.assert_called_once()
        assert "not initialized" in msg.answer.call_args[0][0]


class TestCmdExchange:
    async def test_authorized(self):
        msg = _make_message()
        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers, "get_settings") as mock_settings,
            patch.object(
                handlers.ExchangeAdapterFactory, "get_configured_exchanges", return_value=["OKX"]
            ),
        ):
            mock_settings.return_value.okx.is_configured = True
            mock_settings.return_value.okx.demo_mode = True
            mock_settings.return_value.binance.is_configured = False
            mock_settings.return_value.binance.testnet_mode = True
            mock_settings.return_value.bybit.is_configured = False
            mock_settings.return_value.bybit.testnet_mode = True
            await cmd_exchange(msg)
        msg.answer.assert_called_once()
        text = msg.answer.call_args[0][0]
        assert "EXCHANGE STATUS" in text
        assert "OKX" in text


class TestHandleUnknown:
    async def test_authorized(self):
        msg = _make_message()
        with patch.object(handlers, "check_authorization", return_value=True):
            await handle_unknown(msg)
        msg.answer.assert_called_once()
        assert "Unknown command" in msg.answer.call_args[0][0]


class TestCallbackAuthCreate:
    async def test_new_account(self):
        cb = _make_callback(user_id=12345)
        user = _make_user()
        with (
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
            patch.object(handlers._user_service, "get_or_create_user", return_value=(user, True)),
        ):
            await callback_auth_create(cb)
        cb.answer.assert_called_once()

    async def test_existing_account(self):
        cb = _make_callback(user_id=12345)
        with patch.object(
            handlers._user_service, "get_user_by_telegram", return_value=_make_user()
        ):
            await callback_auth_create(cb)
        cb.answer.assert_called_once()
        assert "already exists" in cb.answer.call_args[0][0]


class TestCallbackNavMain:
    async def test_authorized_with_user(self):
        cb = _make_callback(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await callback_nav_main(cb)
        cb.answer.assert_called_once()

    async def test_no_user(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await callback_nav_main(cb)
        assert "/start" in cb.answer.call_args[0][0]


class TestCallbackMenuResearch:
    async def test_authorized(self):
        cb = _make_callback()
        with patch.object(handlers, "check_callback_authorization", return_value=True):
            await callback_menu_research(cb)
        cb.answer.assert_called_once()


class TestCallbackMenuTop10:
    async def test_authorized(self):
        cb = _make_callback()
        with patch.object(handlers, "check_callback_authorization", return_value=True):
            await callback_menu_top10(cb)
        cb.answer.assert_called_once()


class TestCallbackMenuBlueprint:
    async def test_authorized(self):
        cb = _make_callback()
        with patch.object(handlers, "check_callback_authorization", return_value=True):
            await callback_menu_blueprint(cb)
        cb.answer.assert_called_once()


class TestCallbackMenuSimulate:
    async def test_authorized(self):
        cb = _make_callback()
        with patch.object(handlers, "check_callback_authorization", return_value=True):
            await callback_menu_simulate(cb)
        cb.answer.assert_called_once()


class TestCallbackMenuGrid:
    async def test_okx_connected(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
        ):
            await callback_menu_grid(cb)
        cb.answer.assert_called_once()

    async def test_okx_not_connected(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "is_okx_connected", return_value=False),
        ):
            await callback_menu_grid(cb)
        assert "not connected" in cb.answer.call_args[0][0]


class TestCallbackMenuAccount:
    async def test_authorized_with_user(self):
        cb = _make_callback(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "is_okx_connected", return_value=True),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await callback_menu_account(cb)
        cb.answer.assert_called_once()

    async def test_no_user(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await callback_menu_account(cb)
        assert "/start" in cb.answer.call_args[0][0]


class TestCallbackMenuSettings:
    async def test_authorized(self):
        cb = _make_callback(user_id=12345)
        user = _make_user()
        okx = _make_okx_integration()
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers._user_service, "get_okx_integration", return_value=okx),
        ):
            await callback_menu_settings(cb)
        cb.answer.assert_called_once()


class TestCallbackSettingsUnlink:
    async def test_authorized(self):
        cb = _make_callback()
        with patch.object(handlers, "check_callback_authorization", return_value=True):
            await callback_settings_unlink(cb)
        cb.answer.assert_called_once()


class TestCallbackUnlinkConfirm:
    async def test_unlinked(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "unlink_telegram", return_value=True),
        ):
            await callback_unlink_confirm(cb)
        assert "unlinked" in cb.answer.call_args[0][0]

    async def test_not_linked(self):
        cb = _make_callback(user_id=12345)
        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers._user_service, "unlink_telegram", return_value=False),
        ):
            await callback_unlink_confirm(cb)
        cb.answer.assert_called_once()


class TestCallbackNoop:
    async def test_noop(self):
        cb = _make_callback()
        await callback_noop(cb)
        cb.answer.assert_called_once()


class TestRegisterHandlers:
    def test_registers_all_handlers(self):
        dp = MagicMock()
        dp.message = MagicMock()
        dp.message.register = MagicMock()
        dp.callback_query = MagicMock()
        dp.callback_query.register = MagicMock()

        register_handlers(dp)

        # 11 command handlers: /start /help /menu /status /account /stop_all /exchange
        # /connect /disconnect /pair (Phase 5) + /admin (Phase 12)
        assert dp.message.register.call_count == 11
        # 40 callback handlers (includes all menus, sub-actions, controls,
        # and 3 approval callbacks from I-H7: approve/reject/confirm_live)
        assert dp.callback_query.register.call_count == 40


class TestMultiExchangeContainer:
    def test_get_container_creates_per_exchange(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)

        okx = multi.get_container("OKX")
        binance = multi.get_container("BINANCE")
        bybit = multi.get_container("BYBIT")

        assert okx.exchange_id == "OKX"
        assert binance.exchange_id == "BINANCE"
        assert bybit.exchange_id == "BYBIT"
        assert okx is not binance
        assert binance is not bybit

    def test_get_container_returns_same_instance(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)

        c1 = multi.get_container("OKX")
        c2 = multi.get_container("OKX")
        assert c1 is c2

    def test_get_container_invalid_exchange(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)

        import pytest

        with pytest.raises(ValueError, match="Unsupported exchange"):
            multi.get_container("KRAKEN")

    def test_default_container_is_okx(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)

        assert multi.default_container.exchange_id == "OKX"

    def test_set_service_container_with_multi(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)

        handlers.set_service_container(multi)
        assert handlers.get_multi_container() is multi
        assert handlers.get_service_container() is multi.default_container

    def test_get_container_for_exchange(self):
        from trading_grid.application.services.service_container import MultiExchangeContainer

        mock_settings = MagicMock()
        multi = MultiExchangeContainer(mock_settings)
        handlers.set_service_container(multi)

        okx = handlers.get_container_for_exchange("OKX")
        assert okx is not None
        assert okx.exchange_id == "OKX"

        binance = handlers.get_container_for_exchange("BINANCE")
        assert binance is not None
        assert binance.exchange_id == "BINANCE"

        invalid = handlers.get_container_for_exchange("KRAKEN")
        assert invalid is None


def _make_blueprint(blueprint_id="BP-TEST-001", market_id="BTC-USDT"):
    """Create a mock Blueprint for grid start tests."""
    bp = MagicMock()
    bp.blueprint_id = blueprint_id
    bp.market_id = market_id
    bp.total_capital = MagicMock()
    bp.total_capital.__format__ = lambda self, spec: "1000.00"
    bp.section_count = 2
    bp.total_grid_count = 10
    return bp


def _make_session(session_id="DEMO-TEST-001", grid_id="GRID-TEST-001"):
    """Create a mock DemoGridSession for grid start tests."""
    session = MagicMock()
    session.session_id = session_id
    session.status = "RUNNING"
    session.grid_runtime = MagicMock()
    session.grid_runtime.grid_id = grid_id
    return session


def _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX"):
    """Create a mock CallbackQuery with a Message-spec message (passes isinstance check)."""
    from aiogram.types import Message

    cb = AsyncMock()
    cb.from_user = MagicMock()
    cb.from_user.id = user_id
    cb.from_user.first_name = "Test"
    cb.from_user.username = "testuser"
    cb.data = data
    cb.answer = AsyncMock()
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    return cb


class TestCallbackGridStart:
    """Tests for callback_grid_start — the critical user-facing grid start path."""

    async def test_happy_path_starts_grid(self):
        """Happy path: blueprint found, grid created and started, success message shown."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")
        blueprint = _make_blueprint()
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(return_value=session)

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        # Verify grid was created and started
        mock_container.demo_service.create_demo_grid.assert_called_once()
        mock_container.demo_service.start_demo_grid.assert_called_once()

        # Verify success message was shown
        cb.message.edit_text.assert_called_once()
        edit_text = cb.message.edit_text.call_args[0][0]
        assert "Grid Started" in edit_text
        assert "BTC-USDT" in edit_text

    async def test_blueprint_not_found(self):
        """Error path: blueprint not found shows error answer."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-NONEXISTENT:OKX")

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = None

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        mock_container = MagicMock()

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()
        # Grid should NOT be created
        mock_container.demo_service.create_demo_grid.assert_not_called()

    async def test_exchange_not_configured(self):
        """Error path: exchange container not available shows error."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:BYBIT")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=None),
        ):
            await callback_grid_start(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_no_message_in_callback(self):
        """Error path: callback without editable message shows answer only."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")
        cb.message = None  # No editable message

        mock_container = MagicMock()

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
        ):
            await callback_grid_start(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_create_demo_grid_fails(self):
        """Error path: create_demo_grid raises exception, error message shown."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")
        blueprint = _make_blueprint()

        mock_container = MagicMock()
        mock_container.demo_service.create_demo_grid.side_effect = Exception(
            "Risk validation failed"
        )

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
            patch.object(handlers, "get_settings") as mock_settings,
            patch.object(
                handlers.ExchangeAdapterFactory,
                "get_configured_exchanges",
                return_value=["OKX"],
            ),
        ):
            mock_settings.return_value.okx.is_configured = True
            await callback_grid_start(cb)

        # Error message should be shown
        cb.message.edit_text.assert_called_once()
        edit_text = cb.message.edit_text.call_args[0][0]
        assert "Failed to start grid" in edit_text
        assert "Risk validation failed" in edit_text

    async def test_start_demo_grid_fails(self):
        """Error path: start_demo_grid raises exception after creation, error shown."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")
        blueprint = _make_blueprint()
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(
            side_effect=Exception("Grid already running")
        )

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
            patch.object(handlers, "get_settings") as mock_settings,
            patch.object(
                handlers.ExchangeAdapterFactory,
                "get_configured_exchanges",
                return_value=["OKX"],
            ),
        ):
            mock_settings.return_value.okx.is_configured = True
            await callback_grid_start(cb)

        cb.message.edit_text.assert_called_once()
        edit_text = cb.message.edit_text.call_args[0][0]
        assert "Failed to start grid" in edit_text

    async def test_defaults_to_okx_when_no_exchange_specified(self):
        """Backward compat: grid:start:BP-xxx without exchange defaults to OKX."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001")
        blueprint = _make_blueprint()
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(return_value=session)

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(
                handlers, "get_container_for_exchange", return_value=mock_container
            ) as mock_get,
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        # Should have requested OKX container
        mock_get.assert_called_once_with("OKX")

    async def test_binance_exchange_selected(self):
        """Grid start on BINANCE uses the Binance container."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:BINANCE")
        blueprint = _make_blueprint()
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(return_value=session)

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(
                handlers, "get_container_for_exchange", return_value=mock_container
            ) as mock_get,
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        mock_get.assert_called_once_with("BINANCE")
        cb.message.edit_text.assert_called_once()
        edit_text = cb.message.edit_text.call_args[0][0]
        assert "BINANCE" in edit_text

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot start a grid."""
        cb = _make_callback_with_message(user_id=99999, data="grid:start:BP-TEST-001:OKX")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_grid_start(cb)

        # Should not proceed to container lookup
        cb.message.edit_text.assert_not_called()

    async def test_no_default_container(self):
        """Error path: no default container means blueprint lookup returns None."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")

        mock_container = MagicMock()

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_grid_start(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()

    async def test_double_tap_guard_prevents_duplicate_grid_creation(self):
        """Double-tapping the start button should NOT create a duplicate grid.

        If an active session already exists for the same blueprint_id,
        the handler should alert the user instead of calling create_demo_grid.
        """
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")

        # Create a mock existing session with matching blueprint_id
        existing_session = MagicMock()
        existing_session.session_id = "SESSION-EXISTING"
        existing_session.grid_runtime = MagicMock()
        existing_session.grid_runtime.blueprint = MagicMock()
        existing_session.grid_runtime.blueprint.blueprint_id = "BP-TEST-001"

        mock_container = MagicMock()
        mock_container.demo_service.active_sessions = [existing_session]
        mock_container.demo_service.create_demo_grid = MagicMock()

        mock_blueprint = _make_blueprint(blueprint_id="BP-TEST-001")

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = mock_blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        # create_demo_grid should NOT be called (deduplicated)
        mock_container.demo_service.create_demo_grid.assert_not_called()
        # User should be alerted about existing session
        cb.answer.assert_awaited()
        call_args = str(cb.answer.call_args)
        assert "already running" in call_args.lower()

    async def test_double_tap_guard_allows_different_blueprint(self):
        """Different blueprint_id should NOT be blocked by the guard."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-002:OKX")

        # Existing session for a DIFFERENT blueprint
        existing_session = MagicMock()
        existing_session.session_id = "SESSION-EXISTING"
        existing_session.grid_runtime = MagicMock()
        existing_session.grid_runtime.blueprint = MagicMock()
        existing_session.grid_runtime.blueprint.blueprint_id = "BP-001"  # Different!

        mock_container = MagicMock()
        mock_container.demo_service.active_sessions = [existing_session]

        session = _make_session(session_id="SESSION-NEW", grid_id="GRID-NEW")
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(return_value=session)

        mock_blueprint = _make_blueprint(blueprint_id="BP-002", market_id="ETH-USDT")

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = mock_blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        # create_demo_grid SHOULD be called (different blueprint)
        mock_container.demo_service.create_demo_grid.assert_called_once()

    async def test_double_tap_guard_no_active_sessions_allows_creation(self):
        """When no active sessions exist, grid creation should proceed."""
        cb = _make_callback_with_message(user_id=12345, data="grid:start:BP-TEST-001:OKX")

        mock_container = MagicMock()
        mock_container.demo_service.active_sessions = []  # No active sessions

        session = _make_session(session_id="SESSION-NEW", grid_id="GRID-NEW")
        mock_container.demo_service.create_demo_grid.return_value = session
        mock_container.demo_service.start_demo_grid = AsyncMock(return_value=session)

        mock_blueprint = _make_blueprint(blueprint_id="BP-TEST-001")

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = mock_blueprint

        mock_default_container = MagicMock()
        mock_default_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_container_for_exchange", return_value=mock_container),
            patch.object(handlers, "get_service_container", return_value=mock_default_container),
        ):
            await callback_grid_start(cb)

        # create_demo_grid SHOULD be called
        mock_container.demo_service.create_demo_grid.assert_called_once()


class TestCallbackBlueprintDetail:
    """Tests for callback_blueprint_detail — blueprint detail view."""

    async def test_blueprint_found(self):
        """Blueprint detail is shown when blueprint exists."""
        cb = _make_callback_with_message(user_id=12345, data="blueprint:detail:BP-TEST-001")
        blueprint = _make_blueprint()
        blueprint.status = "DRAFT"
        blueprint.highest_price = MagicMock()
        blueprint.highest_price.__format__ = lambda self, spec: "55000.0000"
        blueprint.lowest_price = MagicMock()
        blueprint.lowest_price.__format__ = lambda self, spec: "45000.0000"
        blueprint.sections = []
        blueprint.created_at = MagicMock()
        blueprint.created_at.strftime.return_value = "2026-08-17 05:00 UTC"

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = blueprint

        mock_container = MagicMock()
        mock_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
            patch.object(handlers, "get_settings") as mock_settings,
            patch.object(
                handlers.ExchangeAdapterFactory,
                "get_configured_exchanges",
                return_value=["OKX"],
            ),
        ):
            mock_settings.return_value.okx.is_configured = True
            await callback_blueprint_detail(cb)

        cb.message.edit_text.assert_called_once()
        edit_text = cb.message.edit_text.call_args[0][0]
        assert "Blueprint Detail" in edit_text
        assert "BP-TEST-001" in edit_text

    async def test_blueprint_not_found(self):
        """Error answer when blueprint not found."""
        cb = _make_callback_with_message(user_id=12345, data="blueprint:detail:BP-NONEXISTENT")

        mock_research = MagicMock()
        mock_research.get_blueprint.return_value = None

        mock_container = MagicMock()
        mock_container.research_service = mock_research

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_blueprint_detail(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()

    async def test_no_container(self):
        """No container: answers without error."""
        cb = _make_callback(user_id=12345, data="blueprint:detail:BP-TEST-001")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_blueprint_detail(cb)

        cb.answer.assert_called_once()


# =============================================================================
# BATCH 1: Grid Controls (safety-critical)
# =============================================================================


class TestCallbackGridPause:
    """Tests for callback_grid_pause — safety-critical grid pause control."""

    async def test_happy_path_pauses_grid(self):
        """Happy path: session found, grid paused, confirmation shown."""
        cb = _make_callback(user_id=12345, data="grid:pause:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_pause(cb)

        mock_container.demo_service.pause_demo_grid.assert_called_once_with("DEMO-TEST-001")
        cb.answer.assert_called_once()
        assert "paused" in cb.answer.call_args[0][0].lower()

    async def test_session_not_found(self):
        """Error path: no session for grid_id shows error answer."""
        cb = _make_callback(user_id=12345, data="grid:pause:GRID-NONEXISTENT")

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_pause(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()
        mock_container.demo_service.pause_demo_grid.assert_not_called()

    async def test_no_container(self):
        """Error path: no service container shows service unavailable."""
        cb = _make_callback(user_id=12345, data="grid:pause:GRID-TEST-001")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_grid_pause(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_pause_service_exception(self):
        """Error path: pause_demo_grid raises, error message shown."""
        cb = _make_callback(user_id=12345, data="grid:pause:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session
        mock_container.demo_service.pause_demo_grid.side_effect = Exception("Already paused")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_pause(cb)

        cb.answer.assert_called_once()
        assert "Failed to pause" in cb.answer.call_args[0][0]

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot pause a grid."""
        cb = _make_callback(user_id=99999, data="grid:pause:GRID-TEST-001")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_grid_pause(cb)

        cb.answer.assert_not_called()


class TestCallbackGridResume:
    """Tests for callback_grid_resume — safety-critical grid resume control."""

    async def test_happy_path_resumes_grid(self):
        """Happy path: session found, grid resumed, confirmation shown."""
        cb = _make_callback(user_id=12345, data="grid:resume:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_resume(cb)

        mock_container.demo_service.resume_demo_grid.assert_called_once_with("DEMO-TEST-001")
        cb.answer.assert_called_once()
        assert "resumed" in cb.answer.call_args[0][0].lower()

    async def test_session_not_found(self):
        """Error path: no session for grid_id shows error answer."""
        cb = _make_callback(user_id=12345, data="grid:resume:GRID-NONEXISTENT")

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_resume(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()
        mock_container.demo_service.resume_demo_grid.assert_not_called()

    async def test_no_container(self):
        """Error path: no service container shows service unavailable."""
        cb = _make_callback(user_id=12345, data="grid:resume:GRID-TEST-001")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_grid_resume(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_resume_service_exception(self):
        """Error path: resume_demo_grid raises, error message shown."""
        cb = _make_callback(user_id=12345, data="grid:resume:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session
        mock_container.demo_service.resume_demo_grid.side_effect = Exception("Not paused")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_resume(cb)

        cb.answer.assert_called_once()
        assert "Failed to resume" in cb.answer.call_args[0][0]

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot resume a grid."""
        cb = _make_callback(user_id=99999, data="grid:resume:GRID-TEST-001")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_grid_resume(cb)

        cb.answer.assert_not_called()


class TestCallbackGridStop:
    """Tests for callback_grid_stop — safety-critical grid stop control."""

    async def test_happy_path_stops_grid(self):
        """Happy path: session found, grid stopped with reason, confirmation shown."""
        cb = _make_callback(user_id=12345, data="grid:stop:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_stop(cb)

        mock_container.demo_service.stop_demo_grid.assert_called_once()
        call_kwargs = mock_container.demo_service.stop_demo_grid.call_args
        assert call_kwargs[0][0] == "DEMO-TEST-001"
        assert "12345" in call_kwargs[1]["reason"]
        cb.answer.assert_called_once()
        assert "stopped" in cb.answer.call_args[0][0].lower()

    async def test_session_not_found(self):
        """Error path: no session for grid_id shows error answer."""
        cb = _make_callback(user_id=12345, data="grid:stop:GRID-NONEXISTENT")

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_stop(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()
        mock_container.demo_service.stop_demo_grid.assert_not_called()

    async def test_no_container(self):
        """Error path: no service container shows service unavailable."""
        cb = _make_callback(user_id=12345, data="grid:stop:GRID-TEST-001")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_grid_stop(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_stop_service_exception(self):
        """Error path: stop_demo_grid raises, error message shown."""
        cb = _make_callback(user_id=12345, data="grid:stop:GRID-TEST-001")
        session = _make_session()

        mock_container = MagicMock()
        mock_container.demo_service.get_session_by_grid_id.return_value = session
        mock_container.demo_service.stop_demo_grid.side_effect = Exception("Already stopped")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_stop(cb)

        cb.answer.assert_called_once()
        assert "Failed to stop" in cb.answer.call_args[0][0]

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot stop a grid."""
        cb = _make_callback(user_id=99999, data="grid:stop:GRID-TEST-001")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_grid_stop(cb)

        cb.answer.assert_not_called()


# =============================================================================
# BATCH 2: Credential Management (security-critical)
# =============================================================================


class TestCmdConnect:
    """Tests for cmd_connect — security-critical credential storage handler."""

    async def test_happy_path_stores_credential(self):
        """Happy path: valid args → credential stored, status updated, success shown."""
        msg = _make_message(
            user_id=12345,
            text="/connect OKX DEMO my_api_key my_api_secret my_passphrase",
        )
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.store_credential.return_value = "CRED-123"

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
            patch.object(
                handlers._user_service, "update_exchange_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            await cmd_connect(msg)

        # Credential message must be deleted (security)
        msg.delete.assert_called_once()

        # Credential stored with correct args
        mock_cred_service.store_credential.assert_called_once()
        call_kwargs = mock_cred_service.store_credential.call_args[1]
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["exchange"] == "OKX"
        assert call_kwargs["environment"] == "DEMO"
        assert call_kwargs["api_key"] == "my_api_key"
        assert call_kwargs["api_secret"] == "my_api_secret"
        assert call_kwargs["passphrase"] == "my_passphrase"
        assert call_kwargs["actor"] == "telegram:12345"

        # Exchange status updated
        mock_update.assert_called_once()

        # Success message shown (without echoing credentials)
        msg.answer.assert_called_once()
        response_text = msg.answer.call_args[0][0]
        assert "OKX" in response_text
        assert "connected" in response_text.lower()
        assert "CRED-123" in response_text
        # Security: credentials must NOT appear in response
        assert "my_api_key" not in response_text
        assert "my_api_secret" not in response_text
        assert "my_passphrase" not in response_text

    async def test_binance_without_passphrase(self):
        """Binance connect works without passphrase (4 args after command)."""
        msg = _make_message(
            user_id=12345,
            text="/connect BINANCE DEMO binance_key binance_secret",
        )
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.store_credential.return_value = "CRED-456"

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
            patch.object(handlers._user_service, "update_exchange_status", new_callable=AsyncMock),
        ):
            await cmd_connect(msg)

        mock_cred_service.store_credential.assert_called_once()
        call_kwargs = mock_cred_service.store_credential.call_args[1]
        assert call_kwargs["exchange"] == "BINANCE"
        assert call_kwargs["passphrase"] is None

    async def test_insufficient_args_shows_usage(self):
        """Too few arguments shows usage help, no credential processing."""
        msg = _make_message(user_id=12345, text="/connect OKX DEMO")
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
        ):
            await cmd_connect(msg)

        msg.answer.assert_called_once()
        assert "Usage" in msg.answer.call_args[0][0]
        # Message should NOT be deleted (no credentials to protect)
        msg.delete.assert_not_called()
        mock_cred_service.store_credential.assert_not_called()

    async def test_unsupported_exchange(self):
        """Unsupported exchange shows error."""
        msg = _make_message(user_id=12345, text="/connect KRAKEN DEMO key secret pass")
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
        ):
            await cmd_connect(msg)

        msg.answer.assert_called_once()
        assert "Unsupported exchange" in msg.answer.call_args[0][0]
        mock_cred_service.store_credential.assert_not_called()

    async def test_invalid_environment(self):
        """Invalid environment (not DEMO/LIVE) shows error."""
        msg = _make_message(user_id=12345, text="/connect OKX PROD key secret pass")
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
        ):
            await cmd_connect(msg)

        msg.answer.assert_called_once()
        assert "Invalid environment" in msg.answer.call_args[0][0]
        mock_cred_service.store_credential.assert_not_called()

    async def test_no_user_redirects_to_start(self):
        """User without account is told to /start first."""
        msg = _make_message(user_id=12345, text="/connect OKX DEMO key secret pass")
        msg.delete = AsyncMock()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await cmd_connect(msg)

        msg.answer.assert_called_once()
        assert "/start" in msg.answer.call_args[0][0]

    async def test_credential_service_not_configured(self):
        """No credential service shows configuration error."""
        msg = _make_message(user_id=12345, text="/connect OKX DEMO key secret pass")
        msg.delete = AsyncMock()
        user = _make_user()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=None),
        ):
            await cmd_connect(msg)

        msg.answer.assert_called_once()
        assert "not configured" in msg.answer.call_args[0][0].lower()

    async def test_store_credential_value_error(self):
        """ValueError from credential service shows validation error."""
        msg = _make_message(user_id=12345, text="/connect OKX DEMO key secret pass")
        msg.delete = AsyncMock()
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.store_credential.side_effect = ValueError("API key too short")

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
        ):
            await cmd_connect(msg)

        # Message still deleted (had credentials)
        msg.delete.assert_called_once()
        # Error shown
        msg.answer.assert_called_once()
        assert "API key too short" in msg.answer.call_args[0][0]

    async def test_delete_message_failure_does_not_block(self):
        """If message.delete() fails, connect still proceeds (logged as warning)."""
        msg = _make_message(user_id=12345, text="/connect OKX DEMO key secret pass")
        msg.delete = AsyncMock(side_effect=Exception("Cannot delete"))
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.store_credential.return_value = "CRED-789"

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
            patch.object(handlers._user_service, "update_exchange_status", new_callable=AsyncMock),
        ):
            await cmd_connect(msg)

        # Should still proceed despite delete failure
        mock_cred_service.store_credential.assert_called_once()
        msg.answer.assert_called_once()
        assert "connected" in msg.answer.call_args[0][0].lower()

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot connect credentials."""
        msg = _make_message(user_id=99999, text="/connect OKX DEMO key secret pass")
        msg.delete = AsyncMock()

        with patch.object(handlers, "check_authorization", return_value=False):
            await cmd_connect(msg)

        msg.delete.assert_not_called()
        msg.answer.assert_not_called()

    async def test_no_from_user_returns_silently(self):
        """Message without from_user returns without action."""
        msg = _make_message(text="/connect OKX DEMO key secret pass")
        msg.from_user = None
        msg.delete = AsyncMock()

        with patch.object(handlers, "check_authorization", return_value=True):
            await cmd_connect(msg)

        msg.delete.assert_not_called()
        msg.answer.assert_not_called()


class TestCmdDisconnect:
    """Tests for cmd_disconnect — security-critical credential revocation handler."""

    async def test_happy_path_revokes_credential(self):
        """Happy path: credential revoked, status updated, success shown."""
        msg = _make_message(user_id=12345, text="/disconnect OKX DEMO")
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.revoke_credential.return_value = True

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
            patch.object(
                handlers._user_service, "update_exchange_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            await cmd_disconnect(msg)

        mock_cred_service.revoke_credential.assert_called_once()
        call_kwargs = mock_cred_service.revoke_credential.call_args[1]
        assert call_kwargs["user_id"] == "user-123"
        assert call_kwargs["exchange"] == "OKX"
        assert call_kwargs["environment"] == "DEMO"
        assert call_kwargs["actor"] == "telegram:12345"
        mock_update.assert_called_once()
        msg.answer.assert_called_once()
        assert "disconnected" in msg.answer.call_args[0][0].lower()

    async def test_no_active_credential(self):
        """No credential to revoke shows informational message."""
        msg = _make_message(user_id=12345, text="/disconnect OKX DEMO")
        user = _make_user()

        mock_cred_service = AsyncMock()
        mock_cred_service.revoke_credential.return_value = False

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
            patch.object(
                handlers._user_service, "update_exchange_status", new_callable=AsyncMock
            ) as mock_update,
        ):
            await cmd_disconnect(msg)

        msg.answer.assert_called_once()
        assert "No active credential" in msg.answer.call_args[0][0]
        mock_update.assert_not_called()

    async def test_insufficient_args_shows_usage(self):
        """Too few arguments shows usage help."""
        msg = _make_message(user_id=12345, text="/disconnect OKX")
        user = _make_user()

        mock_cred_service = AsyncMock()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=mock_cred_service),
        ):
            await cmd_disconnect(msg)

        msg.answer.assert_called_once()
        assert "Usage" in msg.answer.call_args[0][0]
        mock_cred_service.revoke_credential.assert_not_called()

    async def test_no_user_redirects_to_start(self):
        """User without account is told to /start first."""
        msg = _make_message(user_id=12345, text="/disconnect OKX DEMO")

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=None),
        ):
            await cmd_disconnect(msg)

        msg.answer.assert_called_once()
        assert "/start" in msg.answer.call_args[0][0]

    async def test_credential_service_not_configured(self):
        """No credential service shows configuration error."""
        msg = _make_message(user_id=12345, text="/disconnect OKX DEMO")
        user = _make_user()

        with (
            patch.object(handlers, "check_authorization", return_value=True),
            patch.object(handlers._user_service, "get_user_by_telegram", return_value=user),
            patch.object(handlers, "get_credential_service", return_value=None),
        ):
            await cmd_disconnect(msg)

        msg.answer.assert_called_once()
        assert "not configured" in msg.answer.call_args[0][0].lower()

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot disconnect credentials."""
        msg = _make_message(user_id=99999, text="/disconnect OKX DEMO")

        with patch.object(handlers, "check_authorization", return_value=False):
            await cmd_disconnect(msg)

        msg.answer.assert_not_called()

    async def test_no_from_user_returns_silently(self):
        """Message without from_user returns without action."""
        msg = _make_message(text="/disconnect OKX DEMO")
        msg.from_user = None

        with patch.object(handlers, "check_authorization", return_value=True):
            await cmd_disconnect(msg)

        msg.answer.assert_not_called()


# =============================================================================
# BATCH 3: Simulation & Grid Detail
# =============================================================================


class TestCallbackSimulateRun:
    """Tests for callback_simulate_run — simulation execution handler."""

    async def test_happy_path_shows_result(self):
        """Happy path: simulation runs, result formatted and shown."""
        cb = _make_callback_with_message(user_id=12345, data="simulate:run:BTC-USDT")

        mock_result = MagicMock()
        mock_result.market_id = "BTC-USDT"
        mock_result.candles_processed = 168
        mock_result.initial_capital = MagicMock()
        mock_result.initial_capital.__format__ = lambda self, spec: "1000.00"
        mock_result.total_pnl = 5.5
        mock_result.net_pnl_return_pct = 0.55
        mock_result.realized_pnl = 4.0
        mock_result.unrealized_pnl = 1.5
        mock_result.completed_cycles = 3
        mock_result.total_buy_count = 10
        mock_result.total_sell_count = 7
        mock_result.open_lots = 3
        mock_result.total_fees_paid = MagicMock()
        mock_result.total_fees_paid.__format__ = lambda self, spec: "0.1200"
        mock_result.max_drawdown_pct = 2.5
        mock_result.simulation_status = "COMPLETED"

        mock_container = MagicMock()
        mock_container.research_service.run_simulation = AsyncMock(return_value=mock_result)

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_simulate_run(cb)

        # Progress message then result message
        assert cb.message.edit_text.call_count == 2
        final_text = cb.message.edit_text.call_args_list[1][0][0]
        assert "SIMULATION RESULT" in final_text
        assert "BTC-USDT" in final_text

    async def test_simulation_failure_shows_error(self):
        """Error path: simulation raises, error message shown."""
        cb = _make_callback_with_message(user_id=12345, data="simulate:run:BTC-USDT")

        mock_container = MagicMock()
        mock_container.research_service.run_simulation = AsyncMock(
            side_effect=Exception("No candle data")
        )

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_simulate_run(cb)

        # Progress message then error message
        assert cb.message.edit_text.call_count == 2
        final_text = cb.message.edit_text.call_args_list[1][0][0]
        assert "Simulation failed" in final_text
        assert "No candle data" in final_text

    async def test_no_container_shows_error(self):
        """Error path: no service container shows service unavailable."""
        cb = _make_callback(user_id=12345, data="simulate:run:BTC-USDT")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_simulate_run(cb)

        cb.answer.assert_called_once()
        assert "not available" in cb.answer.call_args[0][0].lower()

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot run simulations."""
        cb = _make_callback(user_id=99999, data="simulate:run:BTC-USDT")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_simulate_run(cb)

        cb.answer.assert_not_called()


class TestCallbackSimulateHistory:
    """Tests for callback_simulate_history — simulation history view."""

    async def test_with_history(self):
        """History entries are formatted and shown."""
        cb = _make_callback_with_message(user_id=12345, data="simulate:history")

        mock_result = MagicMock()
        mock_result.market_id = "BTC-USDT"
        mock_result.total_pnl = 5.5
        mock_result.net_pnl_return_pct = 0.55
        mock_result.completed_cycles = 3

        mock_container = MagicMock()
        mock_container.research_service.get_simulation_history.return_value = [mock_result]

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_simulate_history(cb)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "SIMULATION HISTORY" in text
        assert "BTC-USDT" in text

    async def test_empty_history(self):
        """Empty history shows informational message."""
        cb = _make_callback_with_message(user_id=12345, data="simulate:history")

        mock_container = MagicMock()
        mock_container.research_service.get_simulation_history.return_value = []

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_simulate_history(cb)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "No simulations run yet" in text

    async def test_no_container(self):
        """No container: answers without error."""
        cb = _make_callback(user_id=12345, data="simulate:history")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_simulate_history(cb)

        cb.answer.assert_called_once()

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot view simulation history."""
        cb = _make_callback(user_id=99999, data="simulate:history")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_simulate_history(cb)

        cb.answer.assert_not_called()


class TestCallbackGridDetail:
    """Tests for callback_grid_detail — grid detail view with controls."""

    async def test_grid_found_shows_detail(self):
        """Grid found: detail text shown with control keyboard."""
        cb = _make_callback_with_message(user_id=12345, data="grid:detail:GRID-TEST-001")

        mock_grid = MagicMock()
        mock_grid.grid_id = "GRID-TEST-001"
        mock_grid.market_id = "BTC-USDT"
        mock_grid.status = "RUNNING"
        mock_grid.environment = "DEMO"

        mock_session = MagicMock()
        mock_session.metrics = MagicMock()
        mock_session.metrics.orders_submitted = 5

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = mock_grid
        mock_container.demo_service.get_session_by_grid_id.return_value = mock_session

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_detail(cb)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "Grid Detail" in text
        assert "GRID-TEST-001" in text
        assert "BTC-USDT" in text
        assert "RUNNING" in text
        assert "5" in text  # orders submitted

    async def test_grid_not_found(self):
        """Grid not found: error answer shown."""
        cb = _make_callback_with_message(user_id=12345, data="grid:detail:GRID-NONEXISTENT")

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_detail(cb)

        cb.answer.assert_called_once()
        assert "not found" in cb.answer.call_args[0][0].lower()

    async def test_paused_grid_shows_paused_keyboard(self):
        """Paused grid uses grid_paused_keyboard (resume button)."""
        cb = _make_callback_with_message(user_id=12345, data="grid:detail:GRID-TEST-001")

        mock_grid = MagicMock()
        mock_grid.grid_id = "GRID-TEST-001"
        mock_grid.market_id = "BTC-USDT"
        mock_grid.status = "PAUSED"
        mock_grid.environment = "DEMO"

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = mock_grid
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
            patch.object(handlers, "grid_paused_keyboard") as mock_kb,
        ):
            mock_kb.return_value = MagicMock()
            await callback_grid_detail(cb)

        mock_kb.assert_called_once_with("GRID-TEST-001")

    async def test_no_container(self):
        """No container: answers without error."""
        cb = _make_callback(user_id=12345, data="grid:detail:GRID-TEST-001")

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=None),
        ):
            await callback_grid_detail(cb)

        cb.answer.assert_called_once()

    async def test_no_session_shows_zero_orders(self):
        """Grid without session shows 0 orders."""
        cb = _make_callback_with_message(user_id=12345, data="grid:detail:GRID-TEST-001")

        mock_grid = MagicMock()
        mock_grid.grid_id = "GRID-TEST-001"
        mock_grid.market_id = "BTC-USDT"
        mock_grid.status = "RUNNING"
        mock_grid.environment = "DEMO"

        mock_container = MagicMock()
        mock_container.grid_engine.get_grid.return_value = mock_grid
        mock_container.demo_service.get_session_by_grid_id.return_value = None

        with (
            patch.object(handlers, "check_callback_authorization", return_value=True),
            patch.object(handlers, "get_service_container", return_value=mock_container),
        ):
            await callback_grid_detail(cb)

        cb.message.edit_text.assert_called_once()
        text = cb.message.edit_text.call_args[0][0]
        assert "0" in text  # orders_str defaults to "0"

    async def test_unauthorized_user_blocked(self):
        """Unauthorized user cannot view grid detail."""
        cb = _make_callback(user_id=99999, data="grid:detail:GRID-TEST-001")

        with patch.object(handlers, "check_callback_authorization", return_value=False):
            await callback_grid_detail(cb)

        cb.answer.assert_not_called()
