"""
[TD-1] Research and simulation callback handlers.

Extracted from the monolithic callbacks.py. Contains:
- callback_research_top10: Handle research:top10 — alias for menu:top10
- callback_research_markets: Handle research:markets — show all ranked markets
- callback_research_refresh: Handle research:refresh — trigger a fresh market ranking
- callback_market_detail: Handle market:<market_id> — show market detail
- callback_simulate_run: Handle simulate:run:<market_id> — run a grid simulation
- callback_simulate_history: Handle simulate:history — show recent simulation results
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.infrastructure.telegram.formatters import format_top10_list
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    simulate_menu_keyboard,
    top10_menu_keyboard,
)

logger = structlog.get_logger()


async def callback_research_top10(callback: CallbackQuery) -> None:
    """Handle research:top10 — alias for menu:top10."""
    from trading_grid.infrastructure.telegram.handlers.callbacks.menu import callback_menu_top10

    await callback_menu_top10(callback)


async def callback_research_markets(callback: CallbackQuery) -> None:
    """Handle research:markets — show all ranked markets."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    market_ids: list[str] | None = None

    if container is not None:
        try:
            result = await container.research_service.rank_markets(top_n=50)
            if result.recommendations:
                market_ids = [r.market_id for r in result.recommendations]
        except Exception as e:
            logger.error("research_markets_failed", error=str(e))

    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            format_top10_list(rankings=None),
            reply_markup=top10_menu_keyboard(market_ids=market_ids),
        )
    await callback.answer()


async def callback_research_refresh(callback: CallbackQuery) -> None:
    """Handle research:refresh — trigger a fresh market ranking."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    if container is not None:
        try:
            await container.research_service.rank_markets(top_n=10)
        except Exception as e:
            logger.error("research_refresh_failed", error=str(e))
            await callback.answer("⚠️ Refresh failed")
            return

    await callback.answer("✅ Research refreshed")
    from trading_grid.infrastructure.telegram.handlers.callbacks.menu import callback_menu_research

    await callback_menu_research(callback)


async def callback_market_detail(callback: CallbackQuery) -> None:
    """Handle market:<market_id> — show market detail with blueprint/simulate actions."""
    if not await check_callback_authorization(callback):
        return

    market_id = (callback.data or "").removeprefix("market:")
    msg = _get_editable_message(callback)
    if msg is not None:
        await msg.edit_text(
            f"📊 <b>Market: {market_id}</b>\n\nSelect an action:",
            reply_markup=top10_menu_keyboard(market_ids=[market_id]),
        )
    await callback.answer()


async def callback_simulate_run(callback: CallbackQuery) -> None:
    """Handle simulate:run:<market_id> — run a grid simulation."""
    if not await check_callback_authorization(callback):
        return

    market_id = callback.data.split(":")[2] if callback.data else ""
    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer("Service not available")
        return

    await callback.answer("Running simulation...")

    # Show progress
    await msg.edit_text(
        f"🧪 <b>Running simulation for {market_id}...</b>\n\n"
        "Fetching 7 days of 1H candles and\n"
        "running deterministic grid simulator.\n\n"
        "⏳ This may take a few seconds."
    )

    try:
        result = await container.research_service.run_simulation(
            market_id=market_id,
            interval="1H",
            candle_limit=168,
        )
    except Exception as e:
        logger.error("simulation_failed", market_id=market_id, error=str(e))
        await msg.edit_text(
            f"❌ <b>Simulation failed</b>\n\nMarket: {market_id}\nError: <code>{e}</code>",
            reply_markup=simulate_menu_keyboard(market_ids=[market_id]),
        )
        return

    # Format result
    pnl_emoji = "🟢" if result.total_pnl >= 0 else "🔴"
    text = (
        f"🧪 <b>SIMULATION RESULT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Market:</b> {result.market_id}\n"
        f"<b>Candles:</b> {result.candles_processed} (1H)\n"
        f"<b>Capital:</b> {result.initial_capital:.2f} USDT\n\n"
        f"{pnl_emoji} <b>Net P&L:</b> {result.total_pnl:+.4f} USDT "
        f"({result.net_pnl_return_pct:+.2f}%)\n"
        f"📊 <b>Realized:</b> {result.realized_pnl:+.4f}\n"
        f"📊 <b>Unrealized:</b> {result.unrealized_pnl:+.4f}\n\n"
        f"🔄 <b>Completed Cycles:</b> {result.completed_cycles}\n"
        f"🟢 <b>Buys:</b> {result.total_buy_count} | "
        f"🔴 <b>Sells:</b> {result.total_sell_count}\n"
        f"📦 <b>Open Lots:</b> {result.open_lots}\n"
        f"💸 <b>Fees:</b> {result.total_fees_paid:.4f}\n"
        f"📉 <b>Max Drawdown:</b> {result.max_drawdown_pct:.2f}%\n\n"
        f"<b>Status:</b> {result.simulation_status}"
    )

    await msg.edit_text(
        text,
        reply_markup=simulate_menu_keyboard(market_ids=[market_id]),
    )


async def callback_simulate_history(callback: CallbackQuery) -> None:
    """Handle simulate:history — show recent simulation results."""
    if not await check_callback_authorization(callback):
        return

    container = get_service_container()
    msg = _get_editable_message(callback)

    if container is None or msg is None:
        await callback.answer()
        return

    history = container.research_service.get_simulation_history(limit=5)

    if not history:
        text = (
            "📋 <b>SIMULATION HISTORY</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No simulations run yet.\n\n"
            "Select a market from the SIMULATE menu."
        )
    else:
        lines = [
            "📋 <b>SIMULATION HISTORY</b>",
            "━━━━━━━━━━━━━━━━━━",
            "",
        ]
        for r in reversed(history):
            pnl_emoji = "🟢" if r.total_pnl >= 0 else "🔴"
            lines.append(
                f"{pnl_emoji} <b>{r.market_id}</b> — "
                f"{r.net_pnl_return_pct:+.2f}% "
                f"({r.completed_cycles} cycles)"
            )
        lines.append("")
        lines.append(f"Total simulations: {len(history)}")

    await msg.edit_text(
        text if not history else "\n".join(lines),
        reply_markup=simulate_menu_keyboard(),
    )
    await callback.answer()