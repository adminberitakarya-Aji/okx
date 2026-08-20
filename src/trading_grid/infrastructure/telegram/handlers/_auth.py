"""
[I-M8] Authorization helpers for Telegram handlers.

Extracted from the monolithic handlers.py. Provides:
- is_authorized_user: config allowlist check
- check_authorization: message-level authorization
- check_callback_authorization: callback-level authorization
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.handlers._state import _user_service

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery, Message

logger = structlog.get_logger()


def is_authorized_user(user_id: int) -> bool:
    """
    Check if user is authorized via config allowlist.

    Note: Database-backed authorization is checked in async handlers
    via get_user_service().get_user_by_telegram().

    Args:
        user_id: Telegram user ID

    Returns:
        True if user is in the config allowlist
    """
    settings = get_settings()
    allowed_ids = settings.telegram.allowed_user_ids

    # Check config-based allowlist
    return bool(allowed_ids and user_id in allowed_ids)


async def check_authorization(message: Message) -> bool:
    """
    Check if message sender is authorized.

    Authorization is granted if:
    1. Open access mode is enabled (beta trial), OR
    2. User is in the config allowlist, OR
    3. User has a linked identity in the database

    Args:
        message: Incoming message

    Returns:
        True if authorized
    """
    if message.from_user is None:
        return False

    user_id = message.from_user.id

    # Open access mode: anyone can use the bot (beta trial)
    settings = get_settings()
    if settings.telegram.open_access:
        return True

    # Check config allowlist
    if is_authorized_user(user_id):
        return True

    # Check database for linked identity
    user = await _user_service.get_user_by_telegram(user_id)
    if user is not None:
        return True

    logger.warning(
        "unauthorized_access_attempt",
        user_id=user_id,
        username=message.from_user.username,
        command=message.text,
    )
    await message.answer("⛔ You are not authorized to use this bot.")
    return False


async def check_admin_authorization(message: Message) -> bool:
    """
    [Phase 12] Check if message sender is a SYSTEM_ADMIN.

    Admin authorization is granted if:
    1. User is the configured TELEGRAM_ADMIN_USER_ID, OR
    2. User has SYSTEM_ADMIN role in the database (authorization_level >= 5)

    This is stricter than check_authorization — open_access mode does NOT
    grant admin access. Admin commands are always restricted.

    Args:
        message: Incoming message

    Returns:
        True if user is admin
    """
    if message.from_user is None:
        return False

    user_id = message.from_user.id
    settings = get_settings()

    # Check configured admin user ID
    if settings.telegram.admin_user_id is not None and user_id == settings.telegram.admin_user_id:
        return True

    # Check database for SYSTEM_ADMIN role
    user = await _user_service.get_user_by_telegram(user_id)
    if user is not None and user.authorization_level >= 5:
        return True

    logger.warning(
        "admin_access_denied",
        user_id=user_id,
        username=message.from_user.username,
        command=message.text,
    )
    await message.answer(
        "⛔ <b>Admin Access Required</b>\n\n"
        "This command requires SYSTEM_ADMIN (Level 5) authorization.\n"
        "Contact the system administrator if you need admin access.",
        parse_mode="HTML",
    )
    return False


async def check_callback_authorization(callback: CallbackQuery) -> bool:
    """
    Check if callback query sender is authorized.

    Authorization is granted if:
    1. Open access mode is enabled (beta trial), OR
    2. User is in the config allowlist, OR
    3. User has a linked identity in the database

    Args:
        callback: Incoming callback query

    Returns:
        True if authorized
    """
    user_id = callback.from_user.id

    # Open access mode: anyone can use the bot (beta trial)
    settings = get_settings()
    if settings.telegram.open_access:
        return True

    # Check config allowlist
    if is_authorized_user(user_id):
        return True

    # Check database for linked identity
    user = await _user_service.get_user_by_telegram(user_id)
    if user is not None:
        return True

    logger.warning(
        "unauthorized_callback_attempt",
        user_id=user_id,
        callback_data=callback.data,
    )
    await callback.answer("⛔ Not authorized", show_alert=True)
    return False
