"""
[TD-1] Blueprint callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_blueprint_detail: Handle blueprint:detail:<id> — show blueprint details
- callback_blueprint_view: Handle blueprint:view:<market_id> — generate and show blueprint
- callback_blueprint_refresh: Handle blueprint:refresh — alias for menu:blueprint
- callback_grid_start: Handle grid:start:<blueprint_id>:<exchange> — create and start a demo grid
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import structlog

from trading_grid.application.services.authorization import Identity, Role
from trading_grid.application.services.exchange_factory import ExchangeAdapterFactory
from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
    get_container_for_exchange,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    blueprint_detail_keyboard,
    blueprint_menu_keyboard,
    grid_detail_keyboard,
)

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery

logger = structlog.get_logger()


async def callback_blueprint_detail(callback: CallbackQuery) -> None:
    """Handle blueprint:detail:<id> — show blueprint details."""
    if not await check_callback_authorization(callback):
        return

    bp_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    blueprint = container.research_service.get_blueprint(bp_id)
    if blueprint is None:
        await callback.answer("Blueprint not found")
        return

    # Build detail text
    lines = [
        "🧠 <b>Blueprint Detail</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
        f"<b>ID:</b> <code>{blueprint.blueprint_id}</code>",
        f"<b>Market:</b> {blueprint.market_id}",
        f"<b>Capital:</b> {blueprint.total_capital:.2f} USDT",
        f"<b>Status:</b> {blueprint.status}",
        f"<b>Sections:</b> {blueprint.section_count}",
        f"<b>Total Levels:</b> {blueprint.total_grid_count}",
        "",
    ]

    if blueprint.highest_price is not None and blueprint.lowest_price is not None:
        lines.append(
            f"<b>Price Range:</b> {blueprint.lowest_price:.4f} — {blueprint.highest_price:.4f}"
        )
        lines.append("")

    for section in blueprint.sections:
        lines.append(
            f"<b>Section {section.section_id}:</b> "
            f"{section.grid_count} levels, "
            f"spacing {section.grid_spacing_pct}%, "
            f"capital {section.capital_allocation_pct}%"
        )
        lines.append(f"  Range: {section.lower_price:.4f} — {section.upper_price:.4f}")

    lines.append("")
    lines.append(f"Created: {blueprint.created_at.strftime('%Y-%m-%d %H:%M UTC')}")

    # Get configured exchanges for the keyboard
    settings = get_settings()
    configured_exchanges = ExchangeAdapterFactory.get_configured_exchanges(settings)

    await msg.edit_text(
        "\n".join(lines),
        reply_markup=blueprint_detail_keyboard(
            blueprint_id=blueprint.blueprint_id,
            market_id=blueprint.market_id,
            configured_exchanges=configured_exchanges,
        ),
    )
    await callback.answer()


async def callback_blueprint_view(callback: CallbackQuery) -> None:
    """Handle blueprint:view:<market_id> — generate and show blueprint for a market."""
    if not await check_callback_authorization(callback):
        return

    parts = (callback.data or "").split(":", 2)
    market_id = parts[2] if len(parts) > 2 else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    try:
        ticker = await container.adapter.get_ticker(market_id)
        current_price = ticker.last_price
        blueprint = container.research_service.generate_default_blueprint(
            market_id=market_id,
            current_price=current_price,
        )
        text = (
            f"🧠 <b>Blueprint Generated</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Market:</b> {blueprint.market_id}\n"
            f"<b>Sections:</b> {blueprint.section_count}\n"
            f"<b>Levels:</b> {blueprint.total_grid_count}\n"
            f"<b>Capital:</b> {blueprint.total_capital:.2f} USDT\n\n"
            f"Use BLUEPRINT menu to view details and start trading."
        )
        await msg.edit_text(text, reply_markup=blueprint_menu_keyboard())
    except Exception as e:
        logger.error("blueprint_view_failed", market_id=market_id, error=str(e))
        await callback.answer(f"⚠️ Blueprint failed: {e}")
        return

    await callback.answer("✅ Blueprint generated")


async def callback_blueprint_refresh(callback: CallbackQuery) -> None:
    """Handle blueprint:refresh — alias for menu:blueprint."""
    from trading_grid.infrastructure.telegram.handlers.callbacks.menu import callback_menu_blueprint

    await callback_menu_blueprint(callback)


async def callback_grid_start(callback: CallbackQuery) -> None:
    """
    Handle grid:start:<blueprint_id>:<exchange> — create and start a demo grid.

    Callback data format: grid:start:BP-xxx:OKX (or BINANCE, BYBIT)
    Falls back to OKX if exchange is not specified (backward compat).
    """
    if not await check_callback_authorization(callback):
        return

    parts = callback.data.split(":") if callback.data else []
    bp_id = parts[2] if len(parts) > 2 else ""
    exchange_id = parts[3].upper() if len(parts) > 3 else "OKX"

    # Get the container for the selected exchange
    container = get_container_for_exchange(exchange_id)
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer(f"Exchange {exchange_id} not available")
        return

    # Blueprints are shared across exchanges (research uses default container)
    default_container = get_service_container()
    blueprint = (
        default_container.research_service.get_blueprint(bp_id) if default_container else None
    )
    if blueprint is None:
        await callback.answer("Blueprint not found")
        return

    # IDEMPOTENCY GUARD — prevent duplicate grid creation from double-tap.
    existing_session = None
    for s in container.demo_service.active_sessions:
        if s.grid_runtime.blueprint.blueprint_id == bp_id:
            existing_session = s
            break

    if existing_session is not None:
        await callback.answer(
            f"⚠️ Grid already running for this blueprint (session {existing_session.session_id})",
            show_alert=True,
        )
        logger.info(
            "grid_start_deduplicated",
            blueprint_id=bp_id,
            exchange=exchange_id,
            existing_session_id=existing_session.session_id,
            user_id=callback.from_user.id if callback.from_user else None,
        )
        return

    await callback.answer(f"Starting grid on {exchange_id}...")

    # [A-H11] Build identity from Telegram user for RBAC
    user = None
    with contextlib.suppress(Exception):
        user = await _user_service.get_user_by_telegram(callback.from_user.id)
    user_id_str = user.user_id if user is not None else str(callback.from_user.id)

    caller_identity = Identity(
        identity_id=user_id_str,
        identity_type="HUMAN",
        role=Role.DEMO_OPERATOR,
        allowed_environments=("DEMO",),
    )

    try:
        # Create demo grid session from blueprint on the selected exchange
        session = container.demo_service.create_demo_grid(
            blueprint=blueprint,
            notes=f"Started from Telegram by user {callback.from_user.id} on {exchange_id}",
            user_id=user_id_str,
        )

        # Start the grid (wires price monitor for autonomous execution)
        session = await container.demo_service.start_demo_grid(
            session.session_id,
            identity=caller_identity,  # [A-H11]
        )

        await msg.edit_text(
            f"🚀 <b>Grid Started!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<b>Exchange:</b> {exchange_id}\n"
            f"<b>Session:</b> <code>{session.session_id}</code>\n"
            f"<b>Grid:</b> <code>{session.grid_runtime.grid_id}</code>\n"
            f"<b>Market:</b> {blueprint.market_id}\n"
            f"<b>Capital:</b> {blueprint.total_capital:.2f} USDT\n"
            f"<b>Sections:</b> {blueprint.section_count}\n"
            f"<b>Levels:</b> {blueprint.total_grid_count}\n"
            f"<b>Status:</b> {session.status}\n\n"
            f"✅ Price monitor is now watching for\n"
            f"grid level triggers automatically.",
            reply_markup=grid_detail_keyboard(session.grid_runtime.grid_id),
        )

        logger.info(
            "grid_started_from_telegram",
            session_id=session.session_id,
            grid_id=session.grid_runtime.grid_id,
            blueprint_id=bp_id,
            exchange=exchange_id,
            user_id=callback.from_user.id,
        )

    except Exception as e:
        logger.error(
            "grid_start_failed",
            blueprint_id=bp_id,
            exchange=exchange_id,
            error=str(e),
        )
        settings = get_settings()
        configured_exchanges = ExchangeAdapterFactory.get_configured_exchanges(settings)
        await msg.edit_text(
            f"❌ <b>Failed to start grid on {exchange_id}</b>\n\n"
            f"Blueprint: <code>{bp_id}</code>\n"
            f"Error: <code>{e}</code>",
            reply_markup=blueprint_detail_keyboard(
                blueprint_id=bp_id,
                market_id=blueprint.market_id,
                configured_exchanges=configured_exchanges,
            ),
        )
