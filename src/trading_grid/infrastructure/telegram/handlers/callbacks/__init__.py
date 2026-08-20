"""
[TD-1] Telegram callback query handlers package.

Decoupled from the monolithic callbacks.py (1439 lines) into 8 focused
sub-modules organized by menu section:

- nav.py       — Navigation (auth:create, nav:main)
- menu.py      — Main menu handlers
- research.py  — Research sub-actions + simulation
- blueprint.py — Blueprint handlers (detail, view, refresh, grid:start)
- grid.py      — Grid control (detail, pause, resume, stop, orders, pnl, risk)
- account.py   — Account (balance, pnl, risk, okx)
- settings.py  — Settings (notifications, environment, unlink)
- approval.py  — Approval (approve:, reject:, confirm_live:) [I-H7]

This __init__.py re-exports all callback handlers so that existing imports
continue to work without changes.
"""

from trading_grid.infrastructure.telegram.handlers.callbacks.account import (
    callback_account_balance,
    callback_account_okx,
    callback_account_pnl,
    callback_account_risk,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.approval import (
    callback_approve_blueprint,
    callback_confirm_live,
    callback_noop,
    callback_reject_blueprint,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.blueprint import (
    callback_blueprint_detail,
    callback_blueprint_refresh,
    callback_blueprint_view,
    callback_grid_start,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.grid import (
    callback_grid_detail,
    callback_grid_orders_all,
    callback_grid_orders_detail,
    callback_grid_pause,
    callback_grid_pnl_all,
    callback_grid_pnl_detail,
    callback_grid_resume,
    callback_grid_risk,
    callback_grid_stop,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.menu import (
    callback_menu_account,
    callback_menu_blueprint,
    callback_menu_grid,
    callback_menu_research,
    callback_menu_settings,
    callback_menu_simulate,
    callback_menu_top10,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.nav import (
    callback_auth_create,
    callback_nav_main,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.research import (
    callback_market_detail,
    callback_research_markets,
    callback_research_refresh,
    callback_research_top10,
    callback_simulate_history,
    callback_simulate_run,
)
from trading_grid.infrastructure.telegram.handlers.callbacks.settings import (
    callback_settings_environment,
    callback_settings_notifications,
    callback_settings_unlink,
    callback_unlink_confirm,
)

__all__ = [
    # account
    "callback_account_balance",
    "callback_account_okx",
    "callback_account_pnl",
    "callback_account_risk",
    # approval
    "callback_approve_blueprint",
    # nav
    "callback_auth_create",
    # blueprint
    "callback_blueprint_detail",
    "callback_blueprint_refresh",
    "callback_blueprint_view",
    "callback_confirm_live",
    # grid
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
    # research
    "callback_market_detail",
    # menu
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
    # settings
    "callback_settings_environment",
    "callback_settings_notifications",
    "callback_settings_unlink",
    "callback_simulate_history",
    "callback_simulate_run",
    "callback_unlink_confirm",
]
