"""
[TD-1] Settings callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_settings_notifications: Handle settings:notifications — placeholder
- callback_settings_environment: Handle settings:environment — show current trading environment
- callback_settings_unlink: Handle UNLINK TELEGRAM button
- callback_unlink_confirm: Handle unlink confirmation
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.infrastructure.telegram.formatters import (
    format_success,
    format_unlink_warning,
)
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
)
from trading_grid.infrastructure.telegram.keyboards import (
    settings_menu_keyboard,
    unlink_confirmation_keyboard,
)

logger = structlog.get_logger()


async def callback_settings_notifications(callback: CallbackQuery) -> None:
    """Handle settings:notifications — placeholder (not yet configurable via Telegram)."""
    if not await check_callback_authorization(callback):
        return

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            "🔔 <b>NOTIFICATIONS</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Notification settings are managed via the web dashboard.\n\n"
            "Currently, all grid events (fills, stops, alerts) are sent to this chat.",
            reply_markup=settings_menu_keyboard(),
        )
    await callback.answer()


async def callback_settings_environment(callback: CallbackQuery) -> None:
    """Handle settings:environment — show current trading environment."""
    if not await check_callback_authorization(callback):
        return

    user = await _user_service.get_user_by_telegram(callback.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id) if user else None
    environment = okx.environment if okx else "DEMO"

    msg = _get_editable_message(callback)
    if msg is not None:
        env_emoji = "🧪" if environment == "DEMO" else "🚀"
        await msg.edit_text(
            f"🌐 <b>ENVIRONMENT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Current: {env_emoji} <b>{environment}</b>\n\n"
            f"To switch environments, update your API credentials via /connect\n"
            f"and set OKX_DEMO_MODE in your configuration.",
            reply_markup=settings_menu_keyboard(),
        )
    await callback.answer()


async def callback_settings_unlink(callback: CallbackQuery) -> None:
    """Handle UNLINK TELEGRAM button."""
    if not await check_callback_authorization(callback):
        return

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_unlink_warning(),
            reply_markup=unlink_confirmation_keyboard(),
        )
    await callback.answer()


async def callback_unlink_confirm(callback: CallbackQuery) -> None:
    """Handle unlink confirmation."""
    if not await check_callback_authorization(callback):
        return

    telegram_user_id = callback.from_user.id
    unlinked = await _user_service.unlink_telegram(telegram_user_id)
    msg = _get_editable_message(callback)

    if unlinked:
        logger.info(
            "telegram_unlinked",
            telegram_user_id=telegram_user_id,
        )
        if msg is not None:
            await msg.edit_text(
                format_success(
                    "Telegram unlinked.\n\n"
                    "Your account and OKX connection are preserved.\n"
                    "You can re-link via the application dashboard."
                )
            )
        await callback.answer("Telegram unlinked")
    else:
        if msg is not None:
            await msg.edit_text(format_success("No linked account found."))
        await callback.answer()