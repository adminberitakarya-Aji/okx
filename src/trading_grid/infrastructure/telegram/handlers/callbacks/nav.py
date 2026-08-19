"""
[TD-1] Navigation callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_auth_create: Handle 'Create Account' button click
- callback_nav_main: Handle navigation to main menu
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.infrastructure.telegram.formatters import (
    format_account_created,
    format_main_menu,
)
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
)
from trading_grid.infrastructure.telegram.keyboards import (
    main_menu_keyboard,
    welcome_back_keyboard,
)

logger = structlog.get_logger()


async def callback_auth_create(callback: CallbackQuery) -> None:
    """Handle 'Create Account' button click."""
    telegram_user_id = callback.from_user.id
    msg = _get_editable_message(callback)
    chat_id = msg.chat.id if msg else 0
    first_name = callback.from_user.first_name
    username = callback.from_user.username

    # Check if already exists
    existing = await _user_service.get_user_by_telegram(telegram_user_id)
    if existing is not None:
        await callback.answer("Account already exists")
        return

    # Create user in database
    user, is_new = await _user_service.get_or_create_user(
        telegram_user_id, chat_id, first_name, username
    )

    logger.info(
        "account_created",
        user_id=user.user_id,
        telegram_user_id=telegram_user_id,
        is_new=is_new,
    )

    if msg is not None:
        await msg.edit_text(
            format_account_created(user.user_id, first_name),
            reply_markup=welcome_back_keyboard(okx_connected=False),
        )
    await callback.answer("Account created!")


async def callback_nav_main(callback: CallbackQuery) -> None:
    """Handle navigation to main menu."""
    if not await check_callback_authorization(callback):
        return

    user = await _user_service.get_user_by_telegram(callback.from_user.id)
    if user is None:
        await callback.answer("Please /start first")
        return

    okx_connected = await _user_service.is_okx_connected(callback.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id)
    environment = okx.environment if okx else "DEMO"

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_main_menu(environment, okx_connected),
            reply_markup=main_menu_keyboard(),
        )
    await callback.answer()