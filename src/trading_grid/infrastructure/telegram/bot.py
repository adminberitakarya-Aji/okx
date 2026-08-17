"""
Telegram Bot setup.

This module provides:
- TelegramGateway: Main bot gateway using aiogram 3.x
- Bot initialization and lifecycle management

Security rules:
1. All commands require authorization
2. Dangerous operations require approval
3. All operations are audit logged
"""

from typing import Any

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from trading_grid.config.settings import TelegramSettings

logger = structlog.get_logger()


class TelegramGateway:
    """
    Telegram Gateway for bot interactions.

    Provides:
    - Bot lifecycle management
    - Command routing
    - Authorization middleware
    - Message formatting
    """

    def __init__(self, settings: TelegramSettings) -> None:
        """
        Initialize Telegram gateway.

        Args:
            settings: Telegram bot settings
        """
        self._settings = settings
        self._bot: Bot | None = None
        self._dispatcher: Dispatcher | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if gateway is running."""
        return self._running

    async def start(self) -> None:
        """Start the Telegram bot."""
        if self._running:
            logger.warning("telegram_gateway_already_running")
            return

        token = self._settings.bot_token.get_secret_value()
        if not token:
            raise TelegramGatewayError("Bot token not configured")

        self._bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self._dispatcher = Dispatcher()

        # Register handlers
        from trading_grid.infrastructure.telegram.handlers import register_handlers

        register_handlers(self._dispatcher)

        self._running = True
        logger.info("telegram_gateway_started")

        # Note: Polling is started via the dispatcher's start_polling method
        # which is called by the application lifecycle manager

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        if not self._running:
            return

        if self._dispatcher:
            await self._dispatcher.stop_polling()

        if self._bot:
            await self._bot.session.close()

        self._running = False
        logger.info("telegram_gateway_stopped")

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        """
        Send a message to a chat.

        Args:
            chat_id: Target chat ID
            text: Message text (HTML formatted)
            **kwargs: Additional aiogram parameters
        """
        if not self._bot:
            raise TelegramGatewayError("Bot not started")

        await self._bot.send_message(chat_id=chat_id, text=text, **kwargs)

    async def send_approval_request(
        self,
        chat_id: int,
        approval_id: str,
        operation: str,
        details: str,
    ) -> None:
        """
        Send an approval request message.

        Args:
            chat_id: Target chat ID
            approval_id: Approval request ID
            operation: Operation description
            details: Operation details
        """
        text = (
            f"🔐 <b>Approval Required</b>\n\n"
            f"<b>Operation:</b> {operation}\n"
            f"<b>ID:</b> <code>{approval_id}</code>\n\n"
            f"{details}\n\n"
            f"Reply with:\n"
            f"/approve {approval_id}\n"
            f"/reject {approval_id}"
        )
        await self.send_message(chat_id, text)


class TelegramGatewayError(Exception):
    """Telegram gateway error."""

    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        super().__init__(message)
        self.message = message
