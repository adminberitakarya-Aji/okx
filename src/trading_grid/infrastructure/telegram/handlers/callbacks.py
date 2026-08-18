"""
[I-M8] Telegram callback query handlers.

Extracted from the monolithic handlers.py. Contains all inline keyboard
callback handlers organized by menu section:
- Navigation (auth:create, nav:main)
- Main menu (menu:research, menu:top10, etc.)
- Research sub-actions
- Blueprint (detail, view, refresh, grid:start)
- Simulation (run, history)
- Grid control (detail, pause, resume, stop, orders, pnl, risk)
- Account (balance, pnl, risk, okx)
- Settings (notifications, environment, unlink)
- Approval (approve:, reject:, confirm_live:) [I-H7]
"""

from __future__ import annotations

import structlog
from aiogram.types import CallbackQuery

from trading_grid.application.services.exchange_factory import ExchangeAdapterFactory
from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.formatters import (
    format_account_created,
    format_account_status,
    format_main_menu,
    format_okx_not_connected,
    format_research_menu,
    format_settings,
    format_success,
    format_top10_list,
    format_unlink_warning,
)
from trading_grid.infrastructure.telegram.handlers._auth import check_callback_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _get_editable_message,
    _user_service,
    get_container_for_exchange,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    account_menu_keyboard,
    blueprint_detail_keyboard,
    blueprint_menu_keyboard,
    grid_detail_keyboard,
    grid_menu_keyboard,
    grid_paused_keyboard,
    main_menu_keyboard,
    research_menu_keyboard,
    settings_menu_keyboard,
    simulate_menu_keyboard,
    top10_menu_keyboard,
    unlink_confirmation_keyboard,
    welcome_back_keyboard,
)

logger = structlog.get_logger()


# =============================================================================
# NAVIGATION
# =============================================================================


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


# =============================================================================
# MAIN MENU
# =============================================================================


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


# =============================================================================
# RESEARCH SUB-ACTIONS
# =============================================================================


async def callback_research_top10(callback: CallbackQuery) -> None:
    """Handle research:top10 — alias for menu:top10."""
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


# =============================================================================
# BLUEPRINT
# =============================================================================


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
        blueprint = await container.research_service.generate_blueprint(market_id=market_id)
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

    try:
        # Create demo grid session from blueprint on the selected exchange
        session = container.demo_service.create_demo_grid(
            blueprint=blueprint,
            notes=f"Started from Telegram by user {callback.from_user.id} on {exchange_id}",
            user_id=str(callback.from_user.id),
        )

        # Start the grid (wires price monitor for autonomous execution)
        session = await container.demo_service.start_demo_grid(session.session_id)

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


# =============================================================================
# SIMULATION
# =============================================================================


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


# =============================================================================
# GRID CONTROL
# =============================================================================


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

    if grid.status == "PAUSED":
        keyboard = grid_paused_keyboard(grid_id)
    else:
        keyboard = grid_detail_keyboard(grid_id)

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
            orders = session.grid_runtime.order_history[-5:] if session.grid_runtime.order_history else []
            lines.append(f"<b>Grid {grid_id}:</b>")
            if orders:
                for order in orders:
                    lines.append(f"  • {order.side} {order.quantity} @ {order.price} [{order.status}]")
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
            (s.grid_runtime.realized_pnl for s in sessions if s.grid_runtime.realized_pnl is not None),
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
        risk_status = container.risk_service.get_current_risk_summary()
        for key, val in risk_status.items():
            lines.append(f"<b>{key}:</b> {val}")
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
        (s for s in container.demo_service.active_sessions
         if s.grid_runtime.grid_id == grid_id),
        None,
    )

    if session is None:
        await callback.answer("Grid not found")
        return

    orders = session.grid_runtime.order_history[-10:] if session.grid_runtime.order_history else []
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
        (s for s in container.demo_service.active_sessions
         if s.grid_runtime.grid_id == grid_id),
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
        f"Market: {session.grid_runtime.market_id}\n"
        f"Cycles completed: {session.grid_runtime.completed_cycles}"
    )
    await msg.edit_text(text, reply_markup=grid_detail_keyboard(grid_id=grid_id))
    await callback.answer()


# =============================================================================
# ACCOUNT
# =============================================================================


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


# =============================================================================
# SETTINGS
# =============================================================================


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


# =============================================================================
# APPROVAL [I-H7]
# =============================================================================


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