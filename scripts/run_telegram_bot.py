"""
Telegram Bot Runner.

Starts the Telegram bot with polling mode.

Usage:
    uv run python scripts/run_telegram_bot.py

Environment:
    TELEGRAM_BOT_TOKEN       - Bot token from @BotFather
    TELEGRAM_ALLOWED_USER_IDS - Comma-separated allowed user IDs
    TELEGRAM_ADMIN_USER_ID   - Admin user ID for approvals
"""

import asyncio
import signal
import sys
from pathlib import Path

# Windows console fix: force UTF-8 output for emoji support
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from trading_grid.application.services.exchange_factory import ExchangeAdapterFactory
from trading_grid.application.services.service_container import MultiExchangeContainer
from trading_grid.config.settings import get_settings
from trading_grid.infrastructure.telegram.handlers import register_handlers

logger = structlog.get_logger()


async def main() -> None:
    """Run the Telegram bot with polling."""
    settings = get_settings()

    # Validate configuration
    if not settings.telegram.is_configured:
        logger.error("telegram_not_configured")
        print("ERROR: TELEGRAM_BOT_TOKEN is not configured.")
        print("Set it in .env.local or environment variables.")
        sys.exit(1)

    if not settings.telegram.allowed_user_ids:
        logger.warning("telegram_no_allowed_users")
        print("WARNING: TELEGRAM_ALLOWED_USER_IDS is empty. No users will be authorized.")

    token = settings.telegram.bot_token.get_secret_value()

    # Create bot with HTML parse mode
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Create multi-exchange container (wires all application services)
    container = MultiExchangeContainer(settings)

    # Log configured exchanges
    configured = ExchangeAdapterFactory.get_configured_exchanges(settings)
    logger.info("exchanges_configured", exchanges=configured)
    print(f"   Configured exchanges: {', '.join(configured) if configured else 'NONE'}")

    # Create dispatcher and register handlers
    dp = Dispatcher()
    register_handlers(dp, container=container)

    # Get bot info
    me = await bot.get_me()
    logger.info(
        "telegram_bot_starting",
        bot_username=me.username,
        bot_id=me.id,
        allowed_users=settings.telegram.allowed_user_ids,
    )
    print(f"🤖 Bot @{me.username} starting...")
    print(f"   Allowed users: {settings.telegram.allowed_user_ids}")
    print("   Press Ctrl+C to stop")
    print()

    # Setup graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal(sig: int) -> None:
        logger.info("telegram_bot_shutdown_signal", signal=sig)
        shutdown_event.set()

    # Windows doesn't support add_signal_handler for SIGTERM
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, handle_signal, sig)

    # Start background services (price monitor, etc.)
    # Only start containers for configured exchanges
    for exchange_id in configured:
        try:
            await container.get_container(exchange_id).start()
            logger.info("exchange_container_started", exchange=exchange_id)
        except Exception as e:
            logger.warning("exchange_container_start_failed", exchange=exchange_id, error=str(e))

    try:
        # Start polling (this blocks until stopped)
        await dp.start_polling(bot)
    except (KeyboardInterrupt, SystemExit):
        logger.info("telegram_bot_stopped_by_user")
    finally:
        await container.stop_all()
        await bot.session.close()
        logger.info("telegram_bot_session_closed")

    print("\n👋 Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user.")
