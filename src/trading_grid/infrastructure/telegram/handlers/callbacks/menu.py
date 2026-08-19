"""
[TD-1] Main menu callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_menu_research: Handle RESEARCH menu button
- callback_menu_top10: Handle TOP 10 menu button
- callback_menu_blueprint: Handle BLUEPRINT menu button
- callback_menu_simulate: Handle SIMULATE menu button
- callback_menu_grid: Handle GRID menu button
- callback_menu_account: Handle ACCOUNT menu button
- callback_menu_settings: Handle SETTINGS menu button
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.infrastructure.telegram.formatters import (
    format_account_status,
    format_okx_not_connected,
    format_research_menu,
    format_settings,
    format_top10_list,
)
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    account_menu_keyboard,
    blueprint_menu_keyboard,
    grid_menu_keyboard,
    research_menu_keyboard,
    settings_menu_keyboard,
    simulate_menu_keyboard,
    top10_menu_keyboard,
)

logger = structlog.get_logger()


async def callback_menu_research(callback: CallbackQuery) -> None:
    """Handle RESEARCH menu button."""
    if not await check_callback_authorization(callback):
        return

    # Get last research update from service container
    container = get_service_container()
    last_update = None
    if container is not None:
        status = container.research_service.get_service_status()
        last_update = status.get("last_ranking_at")

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_research_menu(last_update=last_update),
            reply_markup=research_menu_keyboard(),
        )
    await callback.answer()


async def callback_menu_top10(callback: CallbackQuery) -> None:
    """Handle TOP 10 menu button."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    rankings: list[dict[str, object]] | None = None
    market_ids: list[str] | None = None

    if container is not None:
        # Run ranking (heuristic mode when no ML model available)
        try:
            result = await container.research_service.rank_markets(top_n=10)
            if result.recommendations:
                # Map risk level to suitability label for formatter
                risk_to_suitability: dict[str, str] = {
                    "LOW": "HIGH",
                    "MEDIUM": "MEDIUM",
                    "HIGH": "LOW",
                    "EXTREME": "AVOID",
                }
                rankings = [
                    {
                        "rank": r.rank,
                        "market_id": r.market_id,
                        "score": r.suitability_score.total_score,
                        "suitability": risk_to_suitability.get(
                            r.suitability_score.risk_level.value, "N/A"
                        ),
                        "action": r.action.value,
                    }
                    for r in result.recommendations
                ]
                market_ids = [r.market_id for r in result.recommendations]
        except Exception as e:
            logger.error("top10_ranking_failed", error=str(e))

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_top10_list(rankings=rankings),
            reply_markup=top10_menu_keyboard(market_ids=market_ids),
        )
    await callback.answer()


async def callback_menu_blueprint(callback: CallbackQuery) -> None:
    """Handle BLUEPRINT menu button — show generated blueprints."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    blueprint_ids: list[str] = []
    lines = [
        "🧠 <b>BLUEPRINTS</b>",
        "━━━━━━━━━━━━━━━━━━",
        "",
    ]

    if container is not None:
        blueprints = container.research_service.blueprints
        if blueprints:
            blueprint_ids = list(blueprints.keys())
            for bp_id, bp in blueprints.items():
                lines.append(
                    f"• <code>{bp_id}</code>\n"
                    f"  {bp.market_id} | {bp.section_count} sections | "
                    f"{bp.total_grid_count} levels | {bp.total_capital:.0f} USDT"
                )
            lines.append("")
            lines.append(f"Total: {len(blueprints)} blueprint(s)")
        else:
            lines.append("No blueprints generated yet.")
            lines.append("")
            lines.append(
                "💡 <i>Use GENERATE to create a blueprint\nfor a market, or run TOP 10 first.</i>"
            )
    else:
        lines.append("Service not available.")

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            "\n".join(lines),
            reply_markup=blueprint_menu_keyboard(blueprint_ids=blueprint_ids or None),
        )
    await callback.answer()


async def callback_menu_simulate(callback: CallbackQuery) -> None:
    """Handle SIMULATE menu button — show markets available for simulation."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    market_ids: list[str] = []

    if container is not None:
        # Use last ranking markets if available, else defaults
        last_ranking = container.research_service.last_ranking
        if last_ranking and last_ranking.recommendations:
            market_ids = [r.market_id for r in last_ranking.recommendations]
        else:
            from trading_grid.application.services.research_service import DEFAULT_MARKETS

            market_ids = list(DEFAULT_MARKETS)

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            "🧪 <b>SIMULATION</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "Select a market to simulate.\n\n"
            "Simulation runs the deterministic grid\n"
            "simulator over the last 7 days of 1H candles\n"
            "with a default blueprint.",
            reply_markup=simulate_menu_keyboard(market_ids=market_ids or None),
        )
    await callback.answer()


async def callback_menu_grid(callback: CallbackQuery) -> None:
    """Handle GRID menu button."""
    if not await check_callback_authorization(callback):
        return

    okx_connected = await _user_service.is_okx_connected(callback.from_user.id)
    msg = _get_editable_message(callback)

    if not okx_connected:
        if msg is not None:
            await msg.edit_text(
                format_okx_not_connected(),
            )
        await callback.answer("OKX not connected")
        return

    # Get active grids from service container
    container = get_service_container()
    grid_ids: list[str] = []
    if container is not None:
        active_grids = container.grid_engine.get_active_grids()
        grid_ids = [g.grid_id for g in active_grids]
        if grid_ids:
            grid_list = "\n".join(
                f"• <code>{g.grid_id}</code> — {g.market_id} ({g.status})" for g in active_grids
            )
            text = (
                f"📈 <b>GRID CONTROL</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"{grid_list}\n\n"
                f"Select a grid to control it."
            )
        else:
            text = (
                "📈 <b>GRID CONTROL</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                "No active grids.\n\n"
                "💡 <i>Grids are created from blueprints.\n"
                "Use the BLUEPRINT menu to get started.</i>"
            )
    else:
        text = "📈 <b>GRID CONTROL</b>\n━━━━━━━━━━━━━━━━━━\n\nNo active grids."

    if msg is not None:
        await msg.edit_text(
            text,
            reply_markup=grid_menu_keyboard(grid_ids=grid_ids or None),
        )
    await callback.answer()


async def callback_menu_account(callback: CallbackQuery) -> None:
    """Handle ACCOUNT menu button."""
    if not await check_callback_authorization(callback):
        return

    user = await _user_service.get_user_by_telegram(callback.from_user.id)
    if user is None:
        await callback.answer("Please /start first")
        return

    okx_connected = await _user_service.is_okx_connected(callback.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id)
    okx_verified = okx.status == "VERIFIED" if okx else False
    environment = okx.environment if okx else "DEMO"

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_account_status(environment, okx_connected, okx_verified),
            reply_markup=account_menu_keyboard(),
        )
    await callback.answer()


async def callback_menu_settings(callback: CallbackQuery) -> None:
    """Handle SETTINGS menu button."""
    if not await check_callback_authorization(callback):
        return

    user = await _user_service.get_user_by_telegram(callback.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id) if user else None
    environment = okx.environment if okx else "DEMO"

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_settings(environment),
            reply_markup=settings_menu_keyboard(),
        )
    await callback.answer()