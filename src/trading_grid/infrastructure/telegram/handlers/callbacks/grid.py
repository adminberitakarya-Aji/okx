"""
[TD-1] Grid control callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_grid_detail: Handle grid detail button — show grid info + control buttons
- callback_grid_pause: Handle grid pause button
- callback_grid_resume: Handle grid resume button
- callback_grid_stop: Handle grid stop button
- callback_grid_orders_all: Handle grid:orders — show all recent orders
- callback_grid_pnl_all: Handle grid:pnl — show P&L summary
- callback_grid_risk: Handle grid:risk — show risk status
- callback_grid_orders_detail: Handle grid:orders:<grid_id> — show orders for a specific grid
- callback_grid_pnl_detail: Handle grid:pnl:<grid_id> — show P&L for a specific grid
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import structlog

from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    grid_detail_keyboard,
    grid_menu_keyboard,
    grid_paused_keyboard,
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery

logger = structlog.get_logger()


async def callback_grid_detail(callback: CallbackQuery) -> None:
    """Handle grid detail button — show grid info + control buttons."""
    if not await check_callback_authorization(callback):
        return

    grid_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    grid = container.grid_engine.get_grid(grid_id)
    if grid is None:
        await callback.answer("Grid not found")
        return

    session = container.demo_service.get_session_by_grid_id(grid_id)
    metrics = session.metrics if session else None

    orders_str = "0"
    if metrics:
        orders_str = str(metrics.orders_submitted)

    text = (
        f"📈 <b>Grid Detail</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Grid:</b> <code>{grid.grid_id}</code>\n"
        f"<b>Market:</b> {grid.market_id}\n"
        f"<b>Status:</b> {grid.status}\n"
        f"<b>Environment:</b> {grid.environment}\n\n"
        f"<b>Orders Submitted:</b> {orders_str}\n"
    )

    handlers_mod = sys.modules.get("trading_grid.infrastructure.telegram.handlers")
    if grid.status == "PAUSED":
        _kb_fn = (
            getattr(handlers_mod, "grid_paused_keyboard", grid_paused_keyboard)
            if handlers_mod
            else grid_paused_keyboard
        )
        keyboard = _kb_fn(grid_id)
    else:
        _kb_fn = (
            getattr(handlers_mod, "grid_detail_keyboard", grid_detail_keyboard)
            if handlers_mod
            else grid_detail_keyboard
        )
        keyboard = _kb_fn(grid_id)

    await msg.edit_text(text, reply_markup=keyboard)
    await callback.answer()


async def callback_grid_pause(callback: CallbackQuery) -> None:
    """Handle grid pause button."""
    if not await check_callback_authorization(callback):
        return

    grid_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()

    if container is None:
        await callback.answer("Service not available")
        return

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        await callback.answer("Grid session not found")
        return

    try:
        container.demo_service.pause_demo_grid(session.session_id)
        await callback.answer(f"Grid {grid_id} paused")
    except Exception as e:
        logger.error("grid_pause_failed", grid_id=grid_id, error=str(e))
        await callback.answer(f"Failed to pause: {e}")


async def callback_grid_resume(callback: CallbackQuery) -> None:
    """Handle grid resume button."""
    if not await check_callback_authorization(callback):
        return

    grid_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()

    if container is None:
        await callback.answer("Service not available")
        return

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        await callback.answer("Grid session not found")
        return

    try:
        container.demo_service.resume_demo_grid(session.session_id)
        await callback.answer(f"Grid {grid_id} resumed")
    except Exception as e:
        logger.error("grid_resume_failed", grid_id=grid_id, error=str(e))
        await callback.answer(f"Failed to resume: {e}")


async def callback_grid_stop(callback: CallbackQuery) -> None:
    """Handle grid stop button."""
    if not await check_callback_authorization(callback):
        return

    grid_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()

    if container is None:
        await callback.answer("Service not available")
        return

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        await callback.answer("Grid session not found")
        return

    try:
        container.demo_service.stop_demo_grid(
            session.session_id,
            reason=f"Stopped by Telegram user {callback.from_user.id}",
        )
        await callback.answer(f"Grid {grid_id} stopped")
    except Exception as e:
        logger.error("grid_stop_failed", grid_id=grid_id, error=str(e))
        await callback.answer(f"Failed to stop: {e}")


async def callback_grid_orders_all(callback: CallbackQuery) -> None:
    """Handle grid:orders — show all recent orders across active grids."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    sessions = container.demo_service.active_sessions
    lines = ["📋 <b>RECENT ORDERS</b>", "━━━━━━━━━━━━━━━━━━", ""]

    if not sessions:
        lines.append("No active grids.")
    else:
        for session in sessions[:5]:
            grid_id = session.grid_runtime.grid_id
            market_id = session.grid_runtime.market_id
            orders = container.execution_engine.get_orders_for_market(market_id)[-5:]
            lines.append(f"<b>Grid {grid_id}:</b>")
            if orders:
                for order in orders:
                    lines.append(
                        f"  • {order.side} {order.quantity} @ {order.price} [{order.status}]"
                    )
            else:
                lines.append("  No orders yet.")
            lines.append("")

    await msg.edit_text("\n".join(lines), reply_markup=grid_menu_keyboard())
    await callback.answer()


async def callback_grid_pnl_all(callback: CallbackQuery) -> None:
    """Handle grid:pnl — show P&L summary across all active grids."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    sessions = container.demo_service.active_sessions
    lines = ["📊 <b>P&L SUMMARY</b>", "━━━━━━━━━━━━━━━━━━", ""]

    if not sessions:
        lines.append("No active grids.")
    else:
        total_pnl = sum(
            (
                s.grid_runtime.realized_pnl
                for s in sessions
                if s.grid_runtime.realized_pnl is not None
            ),
            start=0,
        )
        for session in sessions:
            pnl = session.grid_runtime.realized_pnl or 0
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(f"{emoji} <b>{session.grid_runtime.grid_id}</b>: {pnl:+.4f} USDT")
        lines.append("")
        lines.append(f"<b>Total:</b> {total_pnl:+.4f} USDT")

    await msg.edit_text("\n".join(lines), reply_markup=grid_menu_keyboard())
    await callback.answer()


async def callback_grid_risk(callback: CallbackQuery) -> None:
    """Handle grid:risk — show risk status for all active grids."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    lines = ["🛡 <b>RISK STATUS</b>", "━━━━━━━━━━━━━━━━━━", ""]
    try:
        portfolio = container.execution_engine.risk_validator.portfolio
        lines.append(f"<b>Active Grids:</b> {portfolio.active_grids}")
        lines.append(f"<b>Deployed Capital:</b> {portfolio.deployed_capital:.2f} USDT")
        lines.append(f"<b>Total Exposure:</b> {portfolio.total_exposure:.2f} USDT")
        lines.append(f"<b>Drawdown:</b> {portfolio.drawdown_pct:.2f}%")
        lines.append(f"<b>Risk Level:</b> {portfolio.risk_level}")
    except Exception:
        lines.append("Risk status unavailable.")

    await msg.edit_text("\n".join(lines), reply_markup=grid_menu_keyboard())
    await callback.answer()


async def callback_grid_orders_detail(callback: CallbackQuery) -> None:
    """Handle grid:orders:<grid_id> — show orders for a specific grid."""
    if not await check_callback_authorization(callback):
        return

    parts = (callback.data or "").split(":", 2)
    grid_id = parts[2] if len(parts) > 2 else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    session = next(
        (s for s in container.demo_service.active_sessions if s.grid_runtime.grid_id == grid_id),
        None,
    )

    if session is None:
        await callback.answer("Grid not found")
        return

    orders = container.execution_engine.get_orders_for_market(session.grid_runtime.market_id)[-10:]
    lines = [f"📋 <b>Orders — {grid_id}</b>", "━━━━━━━━━━━━━━━━━━", ""]
    if orders:
        for order in orders:
            lines.append(f"• {order.side} {order.quantity} @ {order.price} [{order.status}]")
    else:
        lines.append("No orders yet.")

    await msg.edit_text("\n".join(lines), reply_markup=grid_detail_keyboard(grid_id=grid_id))
    await callback.answer()


async def callback_grid_pnl_detail(callback: CallbackQuery) -> None:
    """Handle grid:pnl:<grid_id> — show P&L for a specific grid."""
    if not await check_callback_authorization(callback):
        return

    parts = (callback.data or "").split(":", 2)
    grid_id = parts[2] if len(parts) > 2 else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    session = next(
        (s for s in container.demo_service.active_sessions if s.grid_runtime.grid_id == grid_id),
        None,
    )

    if session is None:
        await callback.answer("Grid not found")
        return

    pnl = session.grid_runtime.realized_pnl or 0
    emoji = "🟢" if pnl >= 0 else "🔴"
    text = (
        f"📊 <b>P&L — {grid_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Realized P&L: {emoji} <b>{pnl:+.4f} USDT</b>\n"
        f"Market: {session.grid_runtime.market_id}"
    )
    await msg.edit_text(text, reply_markup=grid_detail_keyboard(grid_id=grid_id))
    await callback.answer()
