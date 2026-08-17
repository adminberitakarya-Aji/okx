"""
Telegram Gateway infrastructure.

This package provides:
- TelegramGateway: Main bot gateway
- Command handlers (state-aware)
- Callback handlers (inline keyboard menus)
- Inline keyboard builders
- Message formatters
- Authorization checks

Menu Structure:
    [ 🔬 RESEARCH ]  [ 🏆 TOP 10 ]
    [ 🧠 BLUEPRINT ] [ 🧪 SIMULATE ]
    [ 📈 GRID ]      [ 💰 ACCOUNT ]
    [ ⚙️ SETTINGS ]

Security rules:
1. All commands require authorization (allowed user IDs or linked identity)
2. Dangerous operations require approval
3. All operations are audit logged
4. OKX credentials are NEVER requested via Telegram
"""

from trading_grid.infrastructure.telegram.bot import TelegramGateway, TelegramGatewayError
from trading_grid.infrastructure.telegram.handlers import (
    check_authorization,
    get_user_service,
    is_authorized_user,
    register_handlers,
)
from trading_grid.infrastructure.telegram.keyboards import (
    account_menu_keyboard,
    approval_keyboard,
    live_confirmation_keyboard,
    main_menu_keyboard,
    research_menu_keyboard,
    settings_menu_keyboard,
    simulate_menu_keyboard,
    top10_menu_keyboard,
    welcome_back_keyboard,
    welcome_new_user_keyboard,
)

__all__ = [
    "TelegramGateway",
    "TelegramGatewayError",
    "account_menu_keyboard",
    "approval_keyboard",
    "check_authorization",
    "get_user_service",
    "is_authorized_user",
    "live_confirmation_keyboard",
    "main_menu_keyboard",
    "register_handlers",
    "research_menu_keyboard",
    "settings_menu_keyboard",
    "simulate_menu_keyboard",
    "top10_menu_keyboard",
    "welcome_back_keyboard",
    "welcome_new_user_keyboard",
]
