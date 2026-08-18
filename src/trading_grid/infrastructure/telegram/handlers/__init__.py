"""
[I-M8] Telegram handlers package.

Refactored from the monolithic handlers.py (1971 lines) into focused
sub-modules:

- _state.py       — Global state, service container helpers
- _auth.py        — Authorization checks
- commands.py     — /command handlers
- callbacks.py    — Inline keyboard callback handlers
- registration.py — Handler registration with the Dispatcher

This __init__.py re-exports the public API so that existing imports
like ``from trading_grid.infrastructure.telegram.handlers import register_handlers``
continue to work without changes.
"""

from trading_grid.infrastructure.telegram.handlers._auth import (
    check_authorization,
    check_callback_authorization,
    is_authorized_user,
)
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    get_container_for_exchange,
    get_credential_service,
    get_multi_container,
    get_service_container,
    get_user_service,
    set_service_container,
)
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
    handle_unknown,
)
from trading_grid.infrastructure.telegram.handlers.registration import register_handlers

__all__ = [
    # _state
    "_get_editable_message",
    "get_container_for_exchange",
    "get_credential_service",
    "get_multi_container",
    "get_service_container",
    "get_user_service",
    "set_service_container",
    # _auth
    "check_authorization",
    "check_callback_authorization",
    "is_authorized_user",
    # commands
    "cmd_account",
    "cmd_connect",
    "cmd_disconnect",
    "cmd_exchange",
    "cmd_help",
    "cmd_menu",
    "cmd_pair",
    "cmd_start",
    "cmd_status",
    "cmd_stop_all",
    "handle_unknown",
    # callbacks
    "callback_account_balance",
    "callback_account_okx",
    "callback_account_pnl",
    "callback_account_risk",
    "callback_approve_blueprint",
    "callback_auth_create",
    "callback_blueprint_detail",
    "callback_blueprint_refresh",
    "callback_blueprint_view",
    "callback_confirm_live",
    "callback_grid_detail",
    "callback_grid_orders_all",
    "callback_grid_orders_detail",
    "callback_grid_pause",
    "callback_grid_pnl_all",
    "callback_grid_pnl_detail",
    "callback_grid_resume",
    "callback_grid_risk",
    "callback_grid_start",
    "callback_grid_stop",
    "callback_market_detail",
    "callback_menu_account",
    "callback_menu_blueprint",
    "callback_menu_grid",
    "callback_menu_research",
    "callback_menu_settings",
    "callback_menu_simulate",
    "callback_menu_top10",
    "callback_nav_main",
    "callback_noop",
    "callback_reject_blueprint",
    "callback_research_markets",
    "callback_research_refresh",
    "callback_research_top10",
    "callback_settings_environment",
    "callback_settings_notifications",
    "callback_settings_unlink",
    "callback_simulate_history",
    "callback_simulate_run",
    "callback_unlink_confirm",
    # registration
    "register_handlers",
]