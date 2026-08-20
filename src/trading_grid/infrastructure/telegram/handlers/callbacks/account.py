"""
[TD-1] Account callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_account_balance: Handle account:balance — fetch and display account balance
- callback_account_pnl: Handle account:pnl — show total P&L summary
- callback_account_risk: Handle account:risk — show account risk limits
- callback_account_okx: Handle account:okx — show OKX connection status
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import account_menu_keyboard

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery

logger = structlog.get_logger()


async def callback_account_balance(callback: CallbackQuery) -> None:
    """Handle account:balance — fetch and display account balance."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    try:
        balance = await container.adapter.get_balance()
        lines = ["💰 <b>ACCOUNT BALANCE</b>", "━━━━━━━━━━━━━━━━━━", ""]
        for asset, amounts in balance.items():
            total = amounts.get("total", 0)
            available = amounts.get("available", 0)
            if float(total) > 0:
                lines.append(f"<b>{asset}:</b> {total:.4f} (avail: {available:.4f})")
        if len(lines) == 3:
            lines.append("No balance data.")
        await msg.edit_text("\n".join(lines), reply_markup=account_menu_keyboard())
    except Exception as e:
        logger.error("account_balance_failed", error=str(e))
        await callback.answer("⚠️ Failed to fetch balance")
        return

    await callback.answer()


async def callback_account_pnl(callback: CallbackQuery) -> None:
    """Handle account:pnl — show total P&L summary across all grids."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    sessions = container.demo_service.active_sessions
    total_pnl = sum(
        (s.grid_runtime.realized_pnl or 0 for s in sessions),
        start=0,
    )
    emoji = "🟢" if total_pnl >= 0 else "🔴"
    text = (
        f"📊 <b>ACCOUNT P&L</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Total Realized P&L: {emoji} <b>{total_pnl:+.4f} USDT</b>\n"
        f"Active Grids: {len(sessions)}"
    )
    await msg.edit_text(text, reply_markup=account_menu_keyboard())
    await callback.answer()


async def callback_account_risk(callback: CallbackQuery) -> None:
    """Handle account:risk — show account risk limits."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    try:
        limits = container.risk_service.get_limits()
        lines = ["🛡 <b>RISK LIMITS</b>", "━━━━━━━━━━━━━━━━━━", ""]
        lines.append(f"Max Active Grids: {limits.max_active_grids}")
        lines.append(f"Max Capital/Grid: {limits.max_capital_per_grid} USDT")
        lines.append(f"Max Total Exposure: {limits.max_total_exposure} USDT")
        lines.append(f"Max Daily Loss: {limits.max_daily_loss_pct}%")
        await msg.edit_text("\n".join(lines), reply_markup=account_menu_keyboard())
    except Exception as e:
        logger.error("account_risk_failed", error=str(e))
        await msg.edit_text(
            "🛡 <b>RISK LIMITS</b>\n━━━━━━━━━━━━━━━━━━\n\nRisk limits unavailable.",
            reply_markup=account_menu_keyboard(),
        )

    await callback.answer()


async def callback_account_okx(callback: CallbackQuery) -> None:
    """Handle account:okx — show OKX connection status."""
    if not await check_callback_authorization(callback):
        return

    msg = _get_editable_message(callback)
    if msg is None:
        await callback.answer()
        return

    user = await _user_service.get_user_by_telegram(callback.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id) if user else None
    connected = okx is not None
    verified = okx.status == "VERIFIED" if okx else False
    environment = okx.environment if okx else "DEMO"

    status_emoji = "🟢" if verified else ("🟡" if connected else "🔴")
    text = (
        f"🔗 <b>OKX CONNECTION</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: {status_emoji} {'Verified' if verified else ('Connected' if connected else 'Not connected')}\n"
        f"Environment: {environment}\n\n"
        f"Use /connect to link your OKX API credentials."
    )
    await msg.edit_text(text, reply_markup=account_menu_keyboard())
    await callback.answer()
