"""
[I-M8] Telegram command handlers.

Extracted from the monolithic handlers module. Contains all /command handlers:
- cmd_start (state-aware + pairing deep-link)
- cmd_help, cmd_menu, cmd_status, cmd_account
- cmd_stop_all (emergency stop)
- cmd_exchange, cmd_connect, cmd_disconnect, cmd_pair
- handle_unknown
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from trading_grid.application.services.authorization import Identity, Role
from trading_grid.application.services.exchange_factory import (
    SUPPORTED_EXCHANGES,
    ExchangeAdapterFactory,
)
from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.formatters import (
    format_main_menu,
    format_welcome_back,
    format_welcome_new_user,
)
from trading_grid.infrastructure.telegram.handlers._auth import check_authorization
from trading_grid.infrastructure.telegram.handlers._state import (
    _user_service,
    get_credential_service,
    get_multi_container,
    get_service_container,
)
from trading_grid.infrastructure.telegram.keyboards import (
    account_menu_keyboard,
    main_menu_keyboard,
    welcome_back_keyboard,
    welcome_new_user_keyboard,
)

if TYPE_CHECKING:
    from aiogram.types import Message

    from trading_grid.application.services.service_container import ServiceContainer

logger = structlog.get_logger()


async def cmd_start(message: Message) -> None:
    """
    Handle /start command with state-aware behavior.

    States:
    1. New user: Welcome + Create Account button
    2. Returning user (no OKX): Welcome + Connect OKX
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
        logger.info("pairing_token_received", token_prefix=token[:10] if token else None)
        # [I-H5] Actually verify the pairing token — no longer a TODO stub
        if _user_service is not None:
            try:
                user, is_new_binding = await _user_service.verify_pairing_token(
                    raw_token=token,
                    telegram_user_id=telegram_user_id,
                    chat_id=message.chat.id,
                )
                logger.info(
                    "pairing_token_verified",
                    user_id=user.user_id,
                    telegram_user_id=telegram_user_id,
                    is_new_binding=is_new_binding,
                )
                await message.answer(
                    f"✅ <b>Account Linked!</b>\n\n"
                    f"Telegram account linked to your trading account successfully.\n"
                    f"Welcome, <b>{first_name}</b>! Use /menu to get started.",
                    parse_mode="HTML",
                )
                return
            except ValueError as e:
                logger.warning("pairing_token_invalid", error=str(e), token_prefix=token[:10])
                await message.answer(
                    "❌ <b>Invalid or Expired Link</b>\n\n"
                    f"{e}\n"
                    "Please generate a new link using /pair.",
                    parse_mode="HTML",
                )
                return
            except Exception as e:
                logger.warning("pairing_token_error", error=str(e), token_prefix=token[:10])
                await message.answer(
                    "⚠️ <b>Pairing Failed</b>\n\n"
                    "Could not verify your pairing link. Please try again or use /connect.",
                    parse_mode="HTML",
                )
                return

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
        "/pair - Generate secure pairing link (RECOMMENDED)\n"
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
    """
    Handle /status command.

    [TD-2] Exchange-agnostic: shows status across all configured exchanges.
    """
    if not await check_authorization(message):
        return

    multi = get_multi_container()
    default_container = get_service_container()
    settings = get_settings()

    # Collect status from all exchanges
    total_active_grids = 0
    exchange_status: dict[str, int] = {}

    containers: list[tuple[str, ServiceContainer]] = []
    if multi is not None and getattr(multi, "_containers", None):
        containers.extend(multi._containers.items())
    elif default_container is not None:
        exchange_name = getattr(default_container, "exchange_id", "OKX")
        containers.append((exchange_name, default_container))

    for exchange_id, container in containers:
        try:
            active_grids = container.grid_engine.get_active_grids()
            exchange_status[exchange_id] = len(active_grids)
            total_active_grids += len(active_grids)
        except Exception:
            exchange_status[exchange_id] = 0

    # Get pending approvals count
    pending_approvals = 0
    if default_container is not None:
        try:
            pending = default_container.approval_service.get_pending_approvals()
            pending_approvals = len(pending) if pending else 0
        except Exception:
            pass

    # Build exchange status lines
    configured = ExchangeAdapterFactory.get_configured_exchanges(settings)
    exchange_lines = []
    for ex in SUPPORTED_EXCHANGES:
        if ex in configured:
            grid_count = exchange_status.get(ex, 0)
            exchange_lines.append(f"  ✅ {ex}: {grid_count} grid(s)")
        else:
            exchange_lines.append(f"  ⬜ {ex}: not configured")

    await message.answer(
        "📊 <b>System Status</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"Status: <code>OPERATIONAL</code>\n"
        f"Active Grids: <b>{total_active_grids}</b>\n"
        f"Pending Approvals: <b>{pending_approvals}</b>\n\n"
        "<b>Exchanges:</b>\n" + "\n".join(exchange_lines)
    )


async def cmd_account(message: Message) -> None:
    """
    Handle /account command.

    [TD-2] Exchange-agnostic: shows account status across all exchanges.
    """
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        await message.answer("Please use /start to create your account first.")
        return

    # Get exchange integration status for all exchanges
    settings = get_settings()
    configured = ExchangeAdapterFactory.get_configured_exchanges(settings)

    # Check user's exchange integrations
    exchange_lines = []
    any_connected = False
    primary_environment = "DEMO"

    for exchange_id in SUPPORTED_EXCHANGES:
        if exchange_id not in configured:
            exchange_lines.append(f"  ⬜ {exchange_id}: not configured")
            continue

        try:
            integration = await _user_service.get_exchange_integration(
                user.user_id, exchange_id
            )
            if integration is not None:
                any_connected = True
                status_icon = "🟢" if integration.status == "VERIFIED" else "🟡"
                exchange_lines.append(
                    f"  {status_icon} {exchange_id}: {integration.environment} ({integration.status})"
                )
                if exchange_id == "OKX":
                    primary_environment = integration.environment
            else:
                exchange_lines.append(f"  🔴 {exchange_id}: not connected")
        except Exception:
            exchange_lines.append(f"  ⬜ {exchange_id}: unknown")

    # Fallback to OKX-specific check for backward compatibility
    if not any_connected:
        okx_connected = await _user_service.is_okx_connected(message.from_user.id)
        okx = await _user_service.get_okx_integration(user.user_id)
        if okx_connected or okx is not None:
            any_connected = True
            okx_verified = okx.status == "VERIFIED" if okx else False
            primary_environment = okx.environment if okx else "DEMO"
            status_icon = "🟢" if okx_verified else "🟡"
            exchange_lines = [f"  {status_icon} OKX: {primary_environment}"]

    await message.answer(
        "👤 <b>ACCOUNT STATUS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>User ID:</b> <code>{user.user_id}</code>\n"
        f"<b>Environment:</b> {primary_environment}\n\n"
        "<b>Exchange Connections:</b>\n" + "\n".join(exchange_lines),
        reply_markup=account_menu_keyboard(),
    )


async def cmd_stop_all(message: Message) -> None:
    """Handle /stop_all command (emergency stop all grids across all exchanges)."""
    if not await check_authorization(message):
        return

    multi = get_multi_container()
    default_container = get_service_container()

    if multi is None and default_container is None:
        await message.answer("⚠️ Service container not initialized.")
        return

    user_id = message.from_user.id if message.from_user else None
    reason = f"Emergency stop by Telegram user {user_id}"
    logger.warning("emergency_stop_requested", user_id=user_id)

    all_stopped: list[object] = []
    exchange_counts: dict[str, int] = {}

    containers_to_stop: list[tuple[str, ServiceContainer]] = []
    if multi is not None and getattr(multi, "_containers", None):
        containers_to_stop.extend(multi._containers.items())
    elif default_container is not None:
        exchange_name = getattr(default_container, "exchange_id", "OKX")
        containers_to_stop.append((exchange_name, default_container))

    for exchange_id, container in containers_to_stop:
        try:
            stopped = container.demo_service.emergency_stop(reason=reason)
            if stopped:
                all_stopped.extend(stopped)
                exchange_counts[exchange_id] = len(stopped)
        except Exception as e:
            logger.error("emergency_stop_exchange_failed", exchange=exchange_id, error=str(e))

    if all_stopped:
        exchange_summary = ", ".join(
            f"{ex}: {cnt}" for ex, cnt in exchange_counts.items() if cnt > 0
        )
        await message.answer(
            f"🚨 <b>Emergency Stop Executed</b>\n\n"
            f"Stopped <b>{len(all_stopped)}</b> grid(s) across exchanges.\n"
            f"{exchange_summary}"
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
            "🔐 <b>Exchange Credential Setup</b>\n\n"
            "🛡️ <i>Recommended (Most Secure):</i>\n"
            "Use <code>/pair</code> to generate a one-time pairing token and configure API credentials "
            "securely via the Web UI dashboard without sharing secrets in chat.\n\n"
            "📋 <b>Usage (Direct Chat Setup):</b>\n"
            "<code>/connect OKX DEMO api_key api_secret passphrase</code>\n"
            "<code>/connect BINANCE DEMO api_key api_secret</code>\n"
            "<code>/connect BYBIT DEMO api_key api_secret</code>\n\n"
            "⚠️ <i>Withdraw permission MUST remain DISABLED on all API keys. Your message will be deleted immediately.</i>"
        )
        return

    # SECURITY: Delete the user's credential message immediately before validation
    try:
        await message.delete()
    except Exception:
        logger.warning("failed_to_delete_credential_message", user_id=message.from_user.id)

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

    # Store encrypted credential
    # [A-H8] Build identity for RBAC — user managing their own credentials
    actor = f"telegram:{message.from_user.id}"
    caller_identity = Identity(
        identity_id=user.user_id,
        identity_type="HUMAN",
        role=Role.VIEWER,  # Users can manage their own credentials
    )
    try:
        credential_id = await cred_service.store_credential(
            user_id=user.user_id,
            exchange=exchange,
            environment=environment,
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            actor=actor,
            identity=caller_identity,
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

    # [A-H8] Build identity for RBAC — user managing their own credentials
    actor = f"telegram:{message.from_user.id}"
    caller_identity = Identity(
        identity_id=user.user_id,
        identity_type="HUMAN",
        role=Role.VIEWER,  # Users can manage their own credentials
    )
    revoked = await cred_service.revoke_credential(
        user_id=user.user_id,
        exchange=exchange,
        environment=environment,
        actor=actor,
        identity=caller_identity,
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


async def cmd_pair(message: Message) -> None:
    """
    Handle /pair command — generate a one-time pairing token for secure account linking.

    [I-H5] This is the RECOMMENDED secure alternative to /connect:
    - The pairing token contains NO credentials
    - The token is one-time use and expires after 10 minutes
    - Credentials are configured via the Web UI dashboard, never in chat

    Usage:
        /pair          - Generate a pairing link for the current user
        /pair 15       - Generate a pairing link with custom expiry (minutes)

    The generated deep link can be shared with the target Telegram user:
        t.me/<bot_username>?start=<token>
    """
    if not await check_authorization(message):
        return

    if message.from_user is None:
        return

    user = await _user_service.get_user_by_telegram(message.from_user.id)
    if user is None:
        await message.answer("Please use /start to create your account first.")
        return

    # Parse optional expiry argument
    parts = (message.text or "").split()
    expiry_minutes = 10
    if len(parts) > 1:
        try:
            expiry_minutes = int(parts[1])
            if expiry_minutes < 1 or expiry_minutes > 60:
                await message.answer("⚠️ Expiry must be between 1 and 60 minutes.")
                return
        except ValueError:
            await message.answer("⚠️ Invalid expiry. Usage: <code>/pair [minutes]</code>")
            return

    try:
        pairing_id, raw_token = await _user_service.create_pairing_session(
            user_id=user.user_id,
            expiry_minutes=expiry_minutes,
        )
    except Exception as e:
        logger.error("pairing_session_failed", user_id=user.user_id, error=str(e))
        await message.answer("⚠️ Failed to create pairing session. Please try again.")
        return

    # Build the deep link using the bot's username
    bot_username = message.bot.username if message.bot else None
    if bot_username:
        deep_link = f"https://t.me/{bot_username}?start={raw_token}"
    else:
        deep_link = f"/start {raw_token}"

    logger.info(
        "pairing_session_created_via_telegram",
        pairing_id=pairing_id,
        user_id=user.user_id,
        expiry_minutes=expiry_minutes,
    )

    await message.answer(
        "🔗 <b>Pairing Link Generated</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Pairing ID:</b> <code>{pairing_id}</code>\n"
        f"<b>Expires in:</b> {expiry_minutes} minutes\n\n"
        f"<b>Deep Link:</b>\n<code>{deep_link}</code>\n\n"
        "📋 <b>How to use:</b>\n"
        "1. Open this link on the target Telegram account\n"
        "2. The bot will automatically link the account\n"
        "3. Configure API credentials via the Web UI dashboard\n\n"
        "🔒 <i>This token is one-time use and contains no credentials.\n"
        "It will expire automatically after the specified time.</i>",
        parse_mode="HTML",
    )


async def handle_unknown(message: Message) -> None:
    """Handle unknown commands."""
    if not await check_authorization(message):
        return

    await message.answer("❓ Unknown command. Use /help to see available commands.")
