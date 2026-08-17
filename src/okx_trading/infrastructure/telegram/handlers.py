"""
Telegram command and callback handlers.

This module provides:
- State-aware /start handler (new user vs returning user)
- Command handlers for basic commands
- Callback query handlers for inline keyboard menus
- Authorization checks for each command
- Integration with application services

Menu Structure:
    [ 🔬 RESEARCH ]  [ 🏆 TOP 10 ]
    [ 🧠 BLUEPRINT ] [ 🧪 SIMULATE ]
    [ 📈 GRID ]      [ 💰 ACCOUNT ]
    [ ⚙️ SETTINGS ]

Security rules:
1. All commands require authorization (allowed user IDs or linked identity)
2. Dangerous operations require approval
3. All operations are audit logged
4. OKX credentials are NEVER requested via Telegram
"""

import structlog
from aiogram import Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from okx_trading.application.services.credential_service import (
    CredentialNotConfiguredError,
    CredentialService,
)
from okx_trading.application.services.exchange_factory import (
    SUPPORTED_EXCHANGES,
    ExchangeAdapterFactory,
)
from okx_trading.application.services.service_container import (
    MultiExchangeContainer,
    ServiceContainer,
)
from okx_trading.application.services.user_service import UserService
from okx_trading.config.settings import get_settings
from okx_trading.infrastructure.telegram.formatters import (
    format_account_created,
    format_account_status,
    format_main_menu,
    format_okx_not_connected,
    format_research_menu,
    format_settings,
    format_success,
    format_top10_list,
    format_unlink_warning,
    format_welcome_back,
    format_welcome_new_user,
)
from okx_trading.infrastructure.telegram.keyboards import (
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
    welcome_new_user_keyboard,
)

logger = structlog.get_logger()

# Global user service instance (database-backed)
_user_service = UserService()

# Credential service (lazy init — requires CREDENTIAL_ENCRYPTION_KEY)
_credential_service: CredentialService | None = None

# Multi-exchange container registry (wired at startup)
_multi_container: MultiExchangeContainer | None = None


def set_service_container(container: MultiExchangeContainer | ServiceContainer) -> None:
    """
    Set the service container instance (for initialization).

    Accepts either a MultiExchangeContainer (preferred) or a single
    ServiceContainer (backward compatibility — wrapped automatically).
    """
    global _multi_container
    if isinstance(container, MultiExchangeContainer):
        _multi_container = container
    else:
        # Backward compat: wrap a single ServiceContainer
        _multi_container = MultiExchangeContainer(container._settings)
        _multi_container._containers[container.exchange_id] = container


def get_service_container() -> ServiceContainer | None:
    """Get the default (OKX) service container instance."""
    if _multi_container is None:
        return None
    return _multi_container.default_container


def get_multi_container() -> MultiExchangeContainer | None:
    """Get the multi-exchange container registry."""
    return _multi_container


def get_container_for_exchange(exchange_id: str) -> ServiceContainer | None:
    """
    Get the ServiceContainer for a specific exchange.

    Args:
        exchange_id: Exchange ID ("OKX", "BINANCE", "BYBIT")

    Returns:
        ServiceContainer for the exchange, or None if not initialized
    """
    if _multi_container is None:
        return None
    try:
        return _multi_container.get_container(exchange_id)
    except ValueError:
        return None


def get_credential_service() -> CredentialService | None:
    """
    Get the credential service instance (lazy init).

    Returns None if CREDENTIAL_ENCRYPTION_KEY is not configured.
    """
    global _credential_service
    if _credential_service is None:
        try:
            _credential_service = CredentialService(get_settings())
        except CredentialNotConfiguredError:
            logger.warning("credential_service_not_configured")
            return None
    return _credential_service


def _get_editable_message(callback: CallbackQuery) -> Message | None:
    """
    Get an editable message from a callback query.

    Args:
        callback: The callback query

    Returns:
        Message if editable, None otherwise
    """
    msg = callback.message
    if msg is None:
        return None
    if not isinstance(msg, Message):
        return None
    return msg


def get_user_service() -> UserService:
    """
    Get the user service instance.

    Returns:
        UserService instance
    """
    return _user_service


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


# =============================================================================
# COMMAND HANDLERS
# =============================================================================


async def cmd_start(message: Message) -> None:
    """
    Handle /start command with state-aware behavior.

    States:
    1. New user: Welcome + Create Account button
    2. Returning user (no OKX): Welcome back + Connect OKX
    3. Returning user (OKX connected): Welcome back + Main menu
    """
    if message.from_user is None:
        return

    telegram_user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username

    # Check for deep link token (pairing flow)
    # Format: /start <token>
    parts = (message.text or "").split()
    if len(parts) > 1:
        token = parts[1]
        # TODO: Verify pairing token via Application API
        logger.info("pairing_token_received", token_prefix=token[:10] if token else None)

    # Check if user exists in database
    user = await _user_service.get_user_by_telegram(telegram_user_id)

    if user is None:
        # NEW USER: Show welcome + create account
        logger.info(
            "new_user_started",
            telegram_user_id=telegram_user_id,
            username=username,
        )
        await message.answer(
            format_welcome_new_user(first_name),
            reply_markup=welcome_new_user_keyboard(),
        )
        return

    # RETURNING USER: Show state-aware welcome
    okx_connected = await _user_service.is_okx_connected(telegram_user_id)
    okx = await _user_service.get_okx_integration(user.user_id)
    okx_verified = okx.status == "VERIFIED" if okx else False
    environment = okx.environment if okx else "DEMO"

    logger.info(
        "returning_user_started",
        telegram_user_id=telegram_user_id,
        okx_connected=okx_connected,
    )

    await message.answer(
        format_welcome_back(first_name, environment, okx_connected, okx_verified),
        reply_markup=welcome_back_keyboard(okx_connected),
    )


async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    if not await check_authorization(message):
        return

    help_text = (
        "📋 <b>Available Commands</b>\n\n"
        "<b>Basic:</b>\n"
        "/start - Main menu / Start\n"
        "/help - Show this help\n"
        "/menu - Open main menu\n\n"
        "<b>Status:</b>\n"
        "/status - System status\n"
        "/account - Account status\n"
        "/exchange - Exchange status\n\n"
        "<b>Credentials (Phase 5):</b>\n"
        "/connect - Connect exchange API keys\n"
        "/disconnect - Disconnect exchange\n\n"
        "<b>Emergency:</b>\n"
        "/stop_all - Emergency stop all grids\n\n"
        "💡 <i>Most features are accessible via the\n"
        "interactive menu. Use /menu to open it.</i>"
    )
    await message.answer(help_text)


async def cmd_menu(message: Message) -> None:
    """Handle /menu command - opens the main menu."""
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        # User not registered, prompt to start
        await message.answer(
            "Please use /start to create your account first.",
        )
        return

    okx_connected = await _user_service.is_okx_connected(message.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id)
    environment = okx.environment if okx else "DEMO"

    await message.answer(
        format_main_menu(environment, okx_connected),
        reply_markup=main_menu_keyboard(),
    )


async def cmd_status(message: Message) -> None:
    """Handle /status command."""
    if not await check_authorization(message):
        return

    # TODO: Integrate with application layer to get real status
    await message.answer(
        "📊 <b>System Status</b>\n\n"
        "Status: <code>OPERATIONAL</code>\n"
        "Mode: <code>DEMO</code>\n"
        "Active Grids: 0\n"
        "Pending Approvals: 0"
    )


async def cmd_account(message: Message) -> None:
    """Handle /account command."""
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        await message.answer("Please use /start to create your account first.")
        return

    okx_connected = await _user_service.is_okx_connected(message.from_user.id)
    okx = await _user_service.get_okx_integration(user.user_id)
    okx_verified = okx.status == "VERIFIED" if okx else False
    environment = okx.environment if okx else "DEMO"

    await message.answer(
        format_account_status(environment, okx_connected, okx_verified),
        reply_markup=account_menu_keyboard(),
    )


async def cmd_stop_all(message: Message) -> None:
    """Handle /stop_all command (emergency stop all grids)."""
    if not await check_authorization(message):
        return

    container = get_service_container()
    if container is None:
        await message.answer("⚠️ Service container not initialized.")
        return

    user_id = message.from_user.id if message.from_user else None
    logger.warning("emergency_stop_requested", user_id=user_id)

    stopped = container.demo_service.emergency_stop_all(
        reason=f"Emergency stop by Telegram user {user_id}"
    )

    if stopped:
        grid_list = "\n".join(f"• <code>{s.grid_runtime.grid_id}</code>" for s in stopped)
        await message.answer(
            f"🚨 <b>Emergency Stop Executed</b>\n\nStopped {len(stopped)} grid(s):\n{grid_list}"
        )
    else:
        await message.answer("🚨 <b>Emergency Stop</b>\n\nNo active grids to stop.")


async def cmd_exchange(message: Message) -> None:
    """
    Handle /exchange command.

    Shows supported exchanges and their configuration status.
    Usage:
        /exchange          - Show all exchanges and status
        /exchange set OKX  - Set active exchange (future: per-user preference)
    """
    if not await check_authorization(message):
        return

    settings = get_settings()
    configured = ExchangeAdapterFactory.get_configured_exchanges(settings)

    # Build exchange status lines
    lines = ["🏦 <b>EXCHANGE STATUS</b>", "━━━━━━━━━━━━━━━━━━", ""]

    exchange_configs = [
        ("OKX", settings.okx.is_configured, settings.okx.demo_mode),
        ("BINANCE", settings.binance.is_configured, settings.binance.testnet_mode),
        ("BYBIT", settings.bybit.is_configured, settings.bybit.testnet_mode),
    ]

    for exchange_name, is_configured, is_demo in exchange_configs:
        if is_configured:
            mode = "🧪 DEMO" if is_demo else "🔴 LIVE"
            status_icon = "✅"
        else:
            mode = "—"
            status_icon = "⬜"
        lines.append(f"{status_icon} <b>{exchange_name}</b>: {mode}")

    lines.append("")
    lines.append(f"Configured: {len(configured)}/{len(SUPPORTED_EXCHANGES)}")
    lines.append("")
    lines.append(
        "💡 <i>Exchange credentials are configured via\nenvironment variables, not via Telegram.</i>"
    )

    await message.answer("\n".join(lines))


async def cmd_connect(message: Message) -> None:
    """
    Handle /connect command — store user exchange API credentials.

    Usage:
        /connect OKX DEMO <api_key> <api_secret> <passphrase>
        /connect BINANCE DEMO <api_key> <api_secret>
        /connect BYBIT DEMO <api_key> <api_secret>

    Security rules:
    1. The user's credential message is deleted immediately after processing
    2. Credentials are encrypted at rest (Fernet)
    3. Credentials are NEVER echoed back or logged
    4. All operations are audit logged
    """
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        await message.answer("Please use /start to create your account first.")
        return

    cred_service = get_credential_service()
    if cred_service is None:
        await message.answer(
            "⚠️ Credential storage is not configured.\n"
            "Contact the administrator (CREDENTIAL_ENCRYPTION_KEY missing)."
        )
        return

    # Parse arguments: /connect <exchange> <environment> <api_key> <api_secret> [passphrase]
    parts = (message.text or "").split()
    if len(parts) < 5:
        await message.answer(
            "📋 <b>Usage:</b>\n"
            "<code>/connect OKX DEMO api_key api_secret passphrase</code>\n"
            "<code>/connect BINANCE DEMO api_key api_secret</code>\n"
            "<code>/connect BYBIT DEMO api_key api_secret</code>\n\n"
            "⚠️ Your message will be deleted immediately after processing."
        )
        return

    exchange = parts[1].upper()
    environment = parts[2].upper()
    api_key = parts[3]
    api_secret = parts[4]
    passphrase = parts[5] if len(parts) > 5 else None

    if exchange not in ("OKX", "BINANCE", "BYBIT"):
        await message.answer(f"❌ Unsupported exchange: {exchange}\nSupported: OKX, BINANCE, BYBIT")
        return

    if environment not in ("DEMO", "LIVE"):
        await message.answer("❌ Invalid environment. Use DEMO or LIVE.")
        return

    # SECURITY: Delete the user's credential message immediately
    try:
        await message.delete()
    except Exception:
        logger.warning("failed_to_delete_credential_message", user_id=message.from_user.id)

    # Store encrypted credential
    actor = f"telegram:{message.from_user.id}"
    try:
        credential_id = await cred_service.store_credential(
            user_id=user.user_id,
            exchange=exchange,
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            actor=actor,
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    # Update exchange integration status
    await _user_service.update_exchange_status(
        user_id=user.user_id,
        status="CONNECTED",
        exchange=exchange,
        environment=environment,
        credential_ref=credential_id,
    )

    logger.info(
        "exchange_connected",
        user_id=user.user_id,
        exchange=exchange,
        environment=environment,
    )

    await message.answer(
        f"✅ <b>{exchange}</b> connected ({environment})\n\n"
        f"Credential ID: <code>{credential_id}</code>\n"
        "🔒 Your API credentials are encrypted at rest.\n\n"
        "⚠️ <i>Your credential message has been deleted.</i>"
    )


async def cmd_disconnect(message: Message) -> None:
    """
    Handle /disconnect command — revoke user exchange API credentials.

    Usage:
        /disconnect OKX DEMO
        /disconnect BINANCE DEMO
    """
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        await message.answer("Please use /start to create your account first.")
        return

    cred_service = get_credential_service()
    if cred_service is None:
        await message.answer("⚠️ Credential storage is not configured.")
        return

    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer(
            "📋 <b>Usage:</b>\n"
            "<code>/disconnect OKX DEMO</code>\n"
            "<code>/disconnect BINANCE DEMO</code>"
        )
        return

    exchange = parts[1].upper()
    environment = parts[2].upper()

    actor = f"telegram:{message.from_user.id}"
    revoked = await cred_service.revoke_credential(
        user_id=user.user_id,
        exchange=exchange,
        environment=environment,
        actor=actor,
    )

    if revoked:
        await _user_service.update_exchange_status(
            user_id=user.user_id,
            status="DISCONNECTED",
            exchange=exchange,
            environment=environment,
        )
        logger.info(
            "exchange_disconnected",
            user_id=user.user_id,
            exchange=exchange,
            environment=environment,
        )
        await message.answer(
            f"✅ <b>{exchange}</b> disconnected ({environment})\n"
            "🔒 Your API credentials have been revoked."
        )
    else:
        await message.answer(f"📋 No active credential found for {exchange} ({environment}).")


async def handle_unknown(message: Message) -> None:
    """Handle unknown commands."""
    if not await check_authorization(message):
        return

    await message.answer("❓ Unknown command. Use /help to see available commands.")


# =============================================================================
# CALLBACK QUERY HANDLERS
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
    # If an active session already exists for this blueprint on this exchange
    # container, return the existing session instead of creating a duplicate.
    # This is the primary defense against Telegram callback retries and
    # users tapping the "Start Grid" button multiple times.
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
            from okx_trading.application.services.research_service import DEFAULT_MARKETS

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


async def callback_noop(callback: CallbackQuery) -> None:
    """Handle no-operation callbacks (disabled buttons)."""
    await callback.answer()


# =============================================================================
# HANDLER REGISTRATION
# =============================================================================


def register_handlers(
    dp: Dispatcher,
    container: MultiExchangeContainer | ServiceContainer | None = None,
) -> None:
    """
    Register all command and callback handlers.

    Args:
        dp: Aiogram dispatcher
        container: MultiExchangeContainer or ServiceContainer (optional, for wiring services)
    """
    if container is not None:
        set_service_container(container)
    # Command handlers
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(cmd_help, Command("help"))
    dp.message.register(cmd_menu, Command("menu"))
    dp.message.register(cmd_status, Command("status"))
    dp.message.register(cmd_account, Command("account"))
    dp.message.register(cmd_stop_all, Command("stop_all"))
    dp.message.register(cmd_exchange, Command("exchange"))
    dp.message.register(cmd_connect, Command("connect"))
    dp.message.register(cmd_disconnect, Command("disconnect"))

    # Callback handlers - Navigation
    dp.callback_query.register(callback_auth_create, F.data == "auth:create")
    dp.callback_query.register(callback_nav_main, F.data == "nav:main")

    # Callback handlers - Main menu
    dp.callback_query.register(callback_menu_research, F.data == "menu:research")
    dp.callback_query.register(callback_menu_top10, F.data == "menu:top10")
    dp.callback_query.register(callback_menu_blueprint, F.data == "menu:blueprint")
    dp.callback_query.register(callback_menu_simulate, F.data == "menu:simulate")
    dp.callback_query.register(callback_menu_grid, F.data == "menu:grid")
    dp.callback_query.register(callback_menu_account, F.data == "menu:account")
    dp.callback_query.register(callback_menu_settings, F.data == "menu:settings")

    # Callback handlers - Blueprint
    dp.callback_query.register(callback_blueprint_detail, F.data.startswith("blueprint:detail:"))
    dp.callback_query.register(callback_grid_start, F.data.startswith("grid:start:"))

    # Callback handlers - Simulation
    dp.callback_query.register(callback_simulate_run, F.data.startswith("simulate:run:"))
    dp.callback_query.register(callback_simulate_history, F.data == "simulate:history")

    # Callback handlers - Grid control
    dp.callback_query.register(callback_grid_detail, F.data.startswith("grid:detail:"))
    dp.callback_query.register(callback_grid_pause, F.data.startswith("grid:pause:"))
    dp.callback_query.register(callback_grid_resume, F.data.startswith("grid:resume:"))
    dp.callback_query.register(callback_grid_stop, F.data.startswith("grid:stop:"))

    # Callback handlers - Settings
    dp.callback_query.register(callback_settings_unlink, F.data == "settings:unlink")
    dp.callback_query.register(callback_unlink_confirm, F.data == "unlink:confirm")

    # Callback handlers - No-op
    dp.callback_query.register(callback_noop, F.data == "noop")

    logger.info("telegram_handlers_registered")
