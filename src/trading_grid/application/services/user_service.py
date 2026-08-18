"""
User identity service.

This service manages:
- Application users
- Telegram identity bindings
- Exchange integration status (OKX, Binance, Bybit)
- Pairing sessions

Security rules:
1. Telegram identity and exchange integrations are separate relationships
2. Unlinking Telegram does NOT delete exchange credentials
3. Exchange credentials are NEVER stored in this service (only status + reference)
4. All operations are audit logged
"""

import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from trading_grid.infrastructure.database.engine import get_session_factory
from trading_grid.infrastructure.database.models import (
    AuditLogModel,
    ExchangeIntegrationModel,
    PairingSessionModel,
    TelegramIdentityModel,
    UserModel,
)

logger = structlog.get_logger()


class UserService:
    """
    User identity management service.

    Provides database-backed user operations for the Telegram gateway.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        """
        Initialize user service.

        Args:
            session_factory: Async session factory (defaults to cached factory)
        """
        self._session_factory = session_factory or get_session_factory()

    async def get_or_create_user(
        self,
        telegram_user_id: int,
        chat_id: int,
        first_name: str | None = None,
        username: str | None = None,
    ) -> tuple[UserModel, bool]:
        """
        Get existing user by telegram ID, or create a new one.

        Args:
            telegram_user_id: Telegram user ID
            chat_id: Telegram chat ID
            first_name: User's first name
            username: Telegram username

        Returns:
            Tuple of (UserModel, is_new_user)
        """
        async with self._session_factory() as session:
            # Check if telegram identity exists
            result = await session.execute(
                select(TelegramIdentityModel).where(
                    TelegramIdentityModel.telegram_user_id == telegram_user_id
                )
            )
            identity = result.scalar_one_or_none()

            if identity:
                # Update last active
                identity.last_active_at = datetime.now(UTC)
                await session.commit()

                # Get user
                user_result = await session.execute(
                    select(UserModel).where(UserModel.user_id == identity.user_id)
                )
                user = user_result.scalar_one_or_none()
                if user:
                    return user, False

            # Create new user
            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            now = datetime.now(UTC)

            user = UserModel(
                user_id=user_id,
                display_name=first_name,
                role="VIEWER",
                authorization_level=0,
                status="ACTIVE",
            )
            session.add(user)

            identity = TelegramIdentityModel(
                user_id=user_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                username=username,
                first_name=first_name,
                status="ACTIVE",
                linked_at=now,
                last_active_at=now,
            )
            session.add(identity)

            # Create default OKX exchange integration placeholder
            okx = ExchangeIntegrationModel(
                user_id=user_id,
                exchange="OKX",
                status="NOT_CONNECTED",
                environment="DEMO",
            )
            session.add(okx)

            # [A-M4] Security rule: All user operations are audit logged
            session.add(
                AuditLogModel(
                    timestamp=now,
                    actor=f"tg:{telegram_user_id}",
                    action="USER_CREATED",
                    resource_type="USER",
                    resource_id=user_id,
                    user_id=user_id,
                    success=True,
                )
            )

            await session.commit()

            logger.info(
                "user_created",
                user_id=user_id,
                telegram_user_id=telegram_user_id,
            )
            return user, True

    async def get_user_by_telegram(self, telegram_user_id: int) -> UserModel | None:
        """
        Get user by telegram user ID.

        Args:
            telegram_user_id: Telegram user ID

        Returns:
            UserModel or None if not found
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramIdentityModel).where(
                    TelegramIdentityModel.telegram_user_id == telegram_user_id
                )
            )
            identity = result.scalar_one_or_none()

            if not identity:
                return None

            user_result = await session.execute(
                select(UserModel).where(UserModel.user_id == identity.user_id)
            )
            return user_result.scalar_one_or_none()

    async def get_telegram_identity(self, telegram_user_id: int) -> TelegramIdentityModel | None:
        """
        Get telegram identity by telegram user ID.

        Args:
            telegram_user_id: Telegram user ID

        Returns:
            TelegramIdentityModel or None
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramIdentityModel).where(
                    TelegramIdentityModel.telegram_user_id == telegram_user_id
                )
            )
            return result.scalar_one_or_none()

    async def get_exchange_integration(
        self, user_id: str, exchange: str = "OKX"
    ) -> ExchangeIntegrationModel | None:
        """
        Get exchange integration for a user.

        Args:
            user_id: Application user ID
            exchange: Exchange ID ("OKX", "BINANCE", "BYBIT")

        Returns:
            ExchangeIntegrationModel or None
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExchangeIntegrationModel).where(
                    ExchangeIntegrationModel.user_id == user_id,
                    ExchangeIntegrationModel.exchange == exchange.upper(),
                )
            )
            return result.scalar_one_or_none()

    async def get_okx_integration(self, user_id: str) -> ExchangeIntegrationModel | None:
        """
        Get OKX integration for a user.

        Backward-compatible wrapper around get_exchange_integration.

        Args:
            user_id: Application user ID

        Returns:
            ExchangeIntegrationModel or None
        """
        return await self.get_exchange_integration(user_id, "OKX")

    async def get_all_exchange_integrations(self, user_id: str) -> list[ExchangeIntegrationModel]:
        """
        Get all exchange integrations for a user.

        Args:
            user_id: Application user ID

        Returns:
            List of ExchangeIntegrationModel
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(ExchangeIntegrationModel).where(ExchangeIntegrationModel.user_id == user_id)
            )
            return list(result.scalars().all())

    async def is_exchange_connected(self, telegram_user_id: int, exchange: str = "OKX") -> bool:
        """
        Check if a user's exchange is connected.

        Args:
            telegram_user_id: Telegram user ID
            exchange: Exchange ID ("OKX", "BINANCE", "BYBIT")

        Returns:
            True if exchange is connected and verified
        """
        user = await self.get_user_by_telegram(telegram_user_id)
        if not user:
            return False

        integration = await self.get_exchange_integration(user.user_id, exchange)
        if not integration:
            return False

        return integration.status in ("CONNECTED", "VERIFIED")

    async def is_okx_connected(self, telegram_user_id: int) -> bool:
        """
        Check if a user's OKX is connected.

        Backward-compatible wrapper around is_exchange_connected.

        Args:
            telegram_user_id: Telegram user ID

        Returns:
            True if OKX is connected and verified
        """
        return await self.is_exchange_connected(telegram_user_id, "OKX")

    async def update_exchange_status(
        self,
        user_id: str,
        status: str,
        exchange: str = "OKX",
        environment: str | None = None,
        credential_ref: str | None = None,
        account_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Update exchange integration status.

        Args:
            user_id: Application user ID
            status: New status (NOT_CONNECTED/CONNECTED/VERIFIED/ERROR/DISCONNECTED)
            exchange: Exchange ID ("OKX", "BINANCE", "BYBIT")
            environment: DEMO or LIVE
            credential_ref: Reference to credential location (never the credential itself)
            account_id: Exchange account ID
            error: Error message if status is ERROR
        """
        exchange_upper = exchange.upper()

        async with self._session_factory() as session:
            result = await session.execute(
                select(ExchangeIntegrationModel).where(
                    ExchangeIntegrationModel.user_id == user_id,
                    ExchangeIntegrationModel.exchange == exchange_upper,
                )
            )
            integration = result.scalar_one_or_none()

            if not integration:
                integration = ExchangeIntegrationModel(
                    user_id=user_id, exchange=exchange_upper, status=status
                )
                session.add(integration)
            else:
                integration.status = status
                if environment:
                    integration.environment = environment
                if credential_ref:
                    integration.credential_ref = credential_ref
                if account_id:
                    integration.account_id = account_id
                if error:
                    integration.last_error = error
                if status == "VERIFIED":
                    integration.verified_at = datetime.now(UTC)

            await session.commit()

            logger.info(
                "exchange_status_updated",
                user_id=user_id,
                exchange=exchange_upper,
                status=status,
            )

    async def update_okx_status(
        self,
        user_id: str,
        status: str,
        environment: str | None = None,
        credential_ref: str | None = None,
        account_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """
        Update OKX integration status.

        Backward-compatible wrapper around update_exchange_status.

        Args:
            user_id: Application user ID
            status: New status (NOT_CONNECTED/CONNECTED/VERIFIED/ERROR/DISCONNECTED)
            environment: DEMO or LIVE
            credential_ref: Reference to credential location (never the credential itself)
            account_id: OKX account ID
            error: Error message if status is ERROR
        """
        await self.update_exchange_status(
            user_id=user_id,
            status=status,
            exchange="OKX",
            environment=environment,
            credential_ref=credential_ref,
            account_id=account_id,
            error=error,
        )

    async def unlink_telegram(self, telegram_user_id: int) -> bool:
        """
        Unlink telegram identity.

        This does NOT delete the user or OKX integration.
        Only marks the telegram identity as REVOKED.

        Args:
            telegram_user_id: Telegram user ID

        Returns:
            True if unlinked successfully
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(TelegramIdentityModel).where(
                    TelegramIdentityModel.telegram_user_id == telegram_user_id
                )
            )
            identity = result.scalar_one_or_none()

            if not identity:
                return False

            identity.status = "REVOKED"
            session.add(
                AuditLogModel(
                    timestamp=datetime.now(UTC),
                    actor=f"tg:{telegram_user_id}",
                    action="TELEGRAM_UNLINKED",
                    resource_type="TELEGRAM_IDENTITY",
                    resource_id=identity.user_id,
                    user_id=identity.user_id,
                    success=True,
                )
            )
            await session.commit()

            logger.info(
                "telegram_unlinked",
                telegram_user_id=telegram_user_id,
                user_id=identity.user_id,
            )
            return True

    async def create_pairing_session(
        self, user_id: str, expiry_minutes: int = 10
    ) -> tuple[str, str]:
        """
        Create a one-time pairing session.

        Args:
            user_id: Application user ID
            expiry_minutes: Token expiry in minutes

        Returns:
            Tuple of (pairing_id, raw_token)
        """
        pairing_id = f"PAIR-{uuid.uuid4().hex[:8].upper()}"
        raw_token = f"tg_connect_{uuid.uuid4().hex[:24]}"
        token_hash = sha256(raw_token.encode()).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(minutes=expiry_minutes)

        async with self._session_factory() as session:
            session.add(
                PairingSessionModel(
                    pairing_id=pairing_id,
                    user_id=user_id,
                    token_hash=token_hash,
                    status="PENDING",
                    expires_at=expires_at,
                )
            )
            session.add(
                AuditLogModel(
                    timestamp=datetime.now(UTC),
                    actor=user_id,
                    action="PAIRING_SESSION_CREATED",
                    resource_type="PAIRING_SESSION",
                    resource_id=pairing_id,
                    user_id=user_id,
                    success=True,
                )
            )
            await session.commit()

        logger.info(
            "pairing_session_created",
            pairing_id=pairing_id,
            user_id=user_id,
            expires_at=expires_at.isoformat(),
        )
        return pairing_id, raw_token

    async def verify_pairing_token(
        self, raw_token: str, telegram_user_id: int, chat_id: int
    ) -> tuple[UserModel, bool]:
        """
        Verify a pairing token and bind telegram identity.

        Args:
            raw_token: The raw token from deep link
            telegram_user_id: Telegram user ID
            chat_id: Telegram chat ID

        Returns:
            Tuple of (UserModel, is_new_binding)

        Raises:
            ValueError: If token is invalid, expired, or already used
        """
        token_hash = sha256(raw_token.encode()).hexdigest()
        now = datetime.now(UTC)

        async with self._session_factory() as session:
            result = await session.execute(
                select(PairingSessionModel).where(PairingSessionModel.token_hash == token_hash)
            )
            pairing = result.scalar_one_or_none()

            if not pairing:
                raise ValueError("Invalid pairing token")

            if pairing.status != "PENDING":
                raise ValueError("Pairing token already used")

            if pairing.expires_at < now:
                pairing.status = "EXPIRED"
                await session.commit()
                raise ValueError("Pairing token expired")

            # Mark as used
            pairing.status = "USED"
            pairing.used_at = now
            pairing.telegram_user_id = telegram_user_id

            # Check if telegram already bound to another user
            existing = await session.execute(
                select(TelegramIdentityModel).where(
                    TelegramIdentityModel.telegram_user_id == telegram_user_id
                )
            )
            existing_identity = existing.scalar_one_or_none()

            if existing_identity:
                # Re-bind to pairing user and update status
                existing_identity.user_id = pairing.user_id
                existing_identity.status = "ACTIVE"
                existing_identity.chat_id = chat_id
                existing_identity.last_active_at = now
                await session.commit()

                existing_user_result = await session.execute(
                    select(UserModel).where(UserModel.user_id == pairing.user_id)
                )
                existing_user = existing_user_result.scalar_one_or_none()
                if existing_user:
                    return existing_user, False

            # Bind telegram to the pairing user
            pairing_user_result = await session.execute(
                select(UserModel).where(UserModel.user_id == pairing.user_id)
            )
            user = pairing_user_result.scalar_one_or_none()
            if not user:
                raise ValueError("User not found for pairing session")

            identity = TelegramIdentityModel(
                user_id=user.user_id,
                telegram_user_id=telegram_user_id,
                chat_id=chat_id,
                status="ACTIVE",
                linked_at=now,
                last_active_at=now,
            )
            session.add(identity)
            session.add(
                AuditLogModel(
                    timestamp=now,
                    actor=f"tg:{telegram_user_id}",
                    action="PAIRING_VERIFIED",
                    resource_type="PAIRING_SESSION",
                    resource_id=pairing.pairing_id,
                    user_id=user.user_id,
                    success=True,
                )
            )
            await session.commit()

            logger.info(
                "pairing_verified",
                pairing_id=pairing.pairing_id,
                user_id=user.user_id,
                telegram_user_id=telegram_user_id,
            )
            return user, True
