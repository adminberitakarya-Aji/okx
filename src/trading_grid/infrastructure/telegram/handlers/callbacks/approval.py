"""
[TD-1] Approval callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_approve_blueprint: Handle approve:<approval_id> — approve a pending request [I-H7]
- callback_reject_blueprint: Handle reject:<approval_id> — reject a pending request [I-H7]
- callback_confirm_live: Handle confirm_live:<approval_id> — final confirmation [I-H7]
- callback_noop: Handle no-operation callbacks (disabled buttons)
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    get_service_container,
)

logger = structlog.get_logger()


async def callback_approve_blueprint(callback: CallbackQuery) -> None:
    """
    [I-H7] Handle approve:<approval_id> — approve a pending blueprint/live trading request.

    Callback data format: approve:<approval_id>
    Only ADMIN-level users (TELEGRAM_ADMIN_USER_ID) may approve live trading.
    """
    if not await check_callback_authorization(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    approval_id = parts[1] if len(parts) > 1 else ""

    settings = get_settings()
    # Only admin may approve live trading
    if callback.from_user.id != settings.telegram.admin_user_id:
        await callback.answer("⛔ Only admin can approve live trading.", show_alert=True)
        return

    container = get_service_container()
    if container is None:
        await callback.answer("Service unavailable", show_alert=True)
        return

    msg = _get_editable_message(callback)

    try:
        await container.approval_service.approve(
            approval_id=approval_id,
            approver_id=str(callback.from_user.id),
        )
        logger.info(
            "blueprint_approved_via_telegram",
            approval_id=approval_id,
            approver=callback.from_user.id,
        )
        if msg is not None:
            await msg.edit_text(
                f"✅ <b>APPROVED</b>\n\n"
                f"Approval <code>{approval_id}</code> has been approved.\n"
                f"Grid execution may proceed.",
                parse_mode="HTML",
            )
        await callback.answer("✅ Approved")
    except Exception as e:
        logger.error("approval_failed", approval_id=approval_id, error=str(e))
        await callback.answer(f"❌ Approval failed: {e}", show_alert=True)


async def callback_reject_blueprint(callback: CallbackQuery) -> None:
    """
    [I-H7] Handle reject:<approval_id> — reject a pending blueprint/live trading request.

    Callback data format: reject:<approval_id>
    Only ADMIN-level users (TELEGRAM_ADMIN_USER_ID) may reject live trading.
    """
    if not await check_callback_authorization(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    approval_id = parts[1] if len(parts) > 1 else ""

    settings = get_settings()
    if callback.from_user.id != settings.telegram.admin_user_id:
        await callback.answer("⛔ Only admin can reject requests.", show_alert=True)
        return

    container = get_service_container()
    if container is None:
        await callback.answer("Service unavailable", show_alert=True)
        return

    msg = _get_editable_message(callback)

    try:
        await container.approval_service.reject(
            approval_id=approval_id,
            rejector_id=str(callback.from_user.id),
            reason="Rejected via Telegram",
        )
        logger.info(
            "blueprint_rejected_via_telegram",
            approval_id=approval_id,
            rejector=callback.from_user.id,
        )
        if msg is not None:
            await msg.edit_text(
                f"❌ <b>REJECTED</b>\n\n"
                f"Approval <code>{approval_id}</code> has been rejected.\n"
                f"Grid execution has been cancelled.",
                parse_mode="HTML",
            )
        await callback.answer("❌ Rejected")
    except Exception as e:
        logger.error("rejection_failed", approval_id=approval_id, error=str(e))
        await callback.answer(f"❌ Rejection failed: {e}", show_alert=True)


async def callback_confirm_live(callback: CallbackQuery) -> None:
    """
    [I-H7] Handle confirm_live:<approval_id> — final confirmation for live trading.

    Callback data format: confirm_live:<approval_id>
    This is the second step of the two-step live trading approval flow:
    1. approve:<id> — initial approval
    2. confirm_live:<id> — final confirmation (this handler)

    Only ADMIN-level users (TELEGRAM_ADMIN_USER_ID) may confirm live trading.
    """
    if not await check_callback_authorization(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    approval_id = parts[1] if len(parts) > 1 else ""

    settings = get_settings()
    # Only admin may confirm live trading
    if callback.from_user.id != settings.telegram.admin_user_id:
        await callback.answer("⛔ Only admin can confirm live trading.", show_alert=True)
        return

    container = get_service_container()
    if container is None:
        await callback.answer("Service unavailable", show_alert=True)
        return

    msg = _get_editable_message(callback)

    try:
        # Confirm the approval for live trading
        await container.approval_service.approve(
            approval_id=approval_id,
            approver_id=str(callback.from_user.id),
        )
        logger.info(
            "live_trading_confirmed_via_telegram",
            approval_id=approval_id,
            approver=callback.from_user.id,
        )
        if msg is not None:
            await msg.edit_text(
                f"🔴 <b>LIVE TRADING CONFIRMED</b>\n\n"
                f"Approval <code>{approval_id}</code> has been confirmed for LIVE trading.\n\n"
                f"⚠️ <i>Real funds are now at risk. Monitor the grid closely.</i>",
                parse_mode="HTML",
            )
        await callback.answer("🔴 Live trading confirmed")
    except Exception as e:
        logger.error("live_confirmation_failed", approval_id=approval_id, error=str(e))
        await callback.answer(f"❌ Confirmation failed: {e}", show_alert=True)


async def callback_noop(callback: CallbackQuery) -> None:
    """Handle no-operation callbacks (disabled buttons)."""
    await callback.answer()