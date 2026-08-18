"""
[I-M8] Handler registration for the Telegram dispatcher.

Extracted from the monolithic handlers.py. Contains the single
register_handlers() function that wires all command and callback
handlers to the aiogram Dispatcher.
"""

from __future__ import annotations

import structlog
from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart

from trading_grid.application.services.service_container import (
    MultiExchangeContainer,
    ServiceContainer,
)
from trading_grid.infrastructure.telegram.handlers._state import set_service_container
from trading_grid.infrastructure.telegram.handlers.callbacks import (
    callback_account_balance,
    callback_account_okx,
    callback_account_pnl,
    callback_account_risk,
    callback_approve_blueprint,
    callback_auth_create,
    callback_blueprint_detail,
    callback_blueprint_refresh,
    callback_blueprint_view,
    callback_confirm_live,
    callback_grid_detail,
    callback_grid_orders_all,
    callback_grid_orders_detail,
    callback_grid_pause,
    callback_grid_pnl_all,
    callback_grid_pnl_detail,
    callback_grid_resume,
    callback_grid_risk,
    callback_grid_start,
    callback_grid_stop,
    callback_market_detail,
    callback_menu_account,
    callback_menu_blueprint,
    callback_menu_grid,
    callback_menu_research,
    callback_menu_settings,
    callback_menu_simulate,
    callback_menu_top10,
    callback_nav_main,
    callback_noop,
    callback_reject_blueprint,
    callback_research_markets,
    callback_research_refresh,
    callback_research_top10,
    callback_settings_environment,
    callback_settings_notifications,
    callback_settings_unlink,
    callback_simulate_history,
    callback_simulate_run,
    callback_unlink_confirm,
)
from trading_grid.infrastructure.telegram.handlers.commands import (
    cmd_account,
    cmd_connect,
    cmd_disconnect,
    cmd_exchange,
    cmd_help,
    cmd_menu,
    cmd_pair,
    cmd_start,
    cmd_status,
    cmd_stop_all,
)

logger = structlog.get_logger()


def register_handlers(
    dp: Dispatcher,
    container: MultiExchangeContainer | ServiceContainer | None = None,
) -> None:
    """
    Register all command and callback handlers.

    Args:
        dp: Aiogram dispatcher
        container: MultiExchangeContainer or ServiceContainer (optional, for wiring services)
    """
    if container is not None:
        set_service_container(container)

    # Command handlers
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_account, Command("account"))
    dp.message.register(cmd_stop_all, Command("stop_all"))
    dp.message.register(cmd_exchange, Command("exchange"))
    dp.message.register(cmd_connect, Command("connect"))
    dp.message.register(cmd_disconnect, Command("disconnect"))
    dp.message.register(cmd_pair, Command("pair"))

    # Callback handlers - Navigation
    dp.callback_query.register(callback_auth_create, F.data == "auth:create")
    dp.callback_query.register(callback_nav_main, F.data == "nav:main")

    # Callback handlers - Main menu
    dp.callback_query.register(callback_menu_research, F.data == "menu:research")
    dp.callback_query.register(callback_menu_top10, F.data == "menu:top10")
    dp.callback_query.register(callback_menu_blueprint, F.data == "menu:blueprint")
    dp.callback_query.register(callback_menu_simulate, F.data == "menu:simulate")
    dp.callback_query.register(callback_menu_grid, F.data == "menu:grid")
    dp.callback_query.register(callback_menu_account, F.data == "menu:account")
    dp.callback_query.register(callback_menu_settings, F.data == "menu:settings")

    # Callback handlers - Research sub-actions
    dp.callback_query.register(callback_research_top10, F.data == "research:top10")
    dp.callback_query.register(callback_research_markets, F.data == "research:markets")
    dp.callback_query.register(callback_research_refresh, F.data == "research:refresh")
    dp.callback_query.register(callback_market_detail, F.data.startswith("market:"))

    # Callback handlers - Blueprint
    dp.callback_query.register(callback_blueprint_detail, F.data.startswith("blueprint:detail:"))
    dp.callback_query.register(callback_blueprint_view, F.data.startswith("blueprint:view:"))
    dp.callback_query.register(callback_blueprint_refresh, F.data == "blueprint:refresh")
    dp.callback_query.register(callback_grid_start, F.data.startswith("grid:start:"))

    # Callback handlers - Simulation
    dp.callback_query.register(callback_simulate_run, F.data.startswith("simulate:run:"))
    dp.callback_query.register(callback_simulate_history, F.data == "simulate:history")

    # Callback handlers - Grid control
    dp.callback_query.register(callback_grid_detail, F.data.startswith("grid:detail:"))
    dp.callback_query.register(callback_grid_pause, F.data.startswith("grid:pause:"))
    dp.callback_query.register(callback_grid_resume, F.data.startswith("grid:resume:"))
    dp.callback_query.register(callback_grid_stop, F.data.startswith("grid:stop:"))

    # Callback handlers - Grid aggregate views
    # NOTE: Order matters — specific patterns before generic ones
    dp.callback_query.register(callback_grid_orders_detail, F.data.startswith("grid:orders:"))
    dp.callback_query.register(callback_grid_pnl_detail, F.data.startswith("grid:pnl:"))
    dp.callback_query.register(callback_grid_orders_all, F.data == "grid:orders")
    dp.callback_query.register(callback_grid_pnl_all, F.data == "grid:pnl")
    dp.callback_query.register(callback_grid_risk, F.data == "grid:risk")

    # Callback handlers - Account
    dp.callback_query.register(callback_account_balance, F.data == "account:balance")
    dp.callback_query.register(callback_account_pnl, F.data == "account:pnl")
    dp.callback_query.register(callback_account_risk, F.data == "account:risk")
    dp.callback_query.register(callback_account_okx, F.data == "account:okx")

    # Callback handlers - Settings
    dp.callback_query.register(callback_settings_notifications, F.data == "settings:notifications")
    dp.callback_query.register(callback_settings_environment, F.data == "settings:environment")
    dp.callback_query.register(callback_settings_unlink, F.data == "settings:unlink")
    dp.callback_query.register(callback_unlink_confirm, F.data == "unlink:confirm")

    # Callback handlers - No-op
    dp.callback_query.register(callback_noop, F.data == "noop")

    # [I-H7] Callback handlers — Blueprint approval (approve:/reject: from approval keyboard)
    dp.callback_query.register(callback_approve_blueprint, F.data.startswith("approve:"))
    dp.callback_query.register(callback_reject_blueprint, F.data.startswith("reject:"))
    dp.callback_query.register(callback_confirm_live, F.data.startswith("confirm_live:"))

    logger.info("telegram_handlers_registered")