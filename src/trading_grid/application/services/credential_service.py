"""
Credential management service (Phase 5: Multi-Tenant Beta).

This service manages encrypted storage and retrieval of user exchange API
credentials. It is the ONLY component that touches plaintext credentials.

Security rules (non-negotiable):
1. Credentials are ALWAYS encrypted at rest using Fernet (AES-128-CBC + HMAC)
2. Plaintext credentials are NEVER logged, NEVER stored, NEVER returned in API responses
3. Every credential access (read/write/delete) is audit logged
4. key_fingerprint is a non-reversible SHA-256 hash for audit correlation
5. DEMO and LIVE use separate credentials per exchange
6. CREDENTIAL_ENCRYPTION_KEY must be configured before any credential operation

Dependency rule:
    application/ may import domain/ and infrastructure/.
    This service uses infrastructure/database for persistence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING

import structlog
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from trading_grid.infrastructure.database.engine import get_session_factory
from trading_grid.infrastructure.database.models import (
    AuditLogModel,
    UserCredentialModel,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from trading_grid.config.settings import Settings

logger = structlog.get_logger()


class CredentialEncryptionError(Exception):
    """Raised when credential encryption/decryption fails."""


class CredentialNotConfiguredError(Exception):
    """Raised when CREDENTIAL_ENCRYPTION_KEY is not configured."""


class CredentialNotFoundError(Exception):
    """Raised when a requested credential does not exist."""


class DecryptedCredential:
    """
    In-memory decrypted credential container.

    This object holds plaintext credentials temporarily.
    It MUST NOT be logged, serialized, or persisted.
    Use it only to construct exchange adapter settings.
    """

    __slots__ = ("api_key", "api_secret", "environment", "exchange", "passphrase")

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        passphrase: str | None,
        exchange: str,
        environment: str,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.exchange = exchange
        self.environment = environment

    def __repr__(self) -> str:
        # NEVER expose secrets in repr
        return (
            f"DecryptedCredential(exchange={self.exchange!r}, "
            f"environment={self.environment!r}, api_key=***)"
        )


class CredentialService:
    """
    Encrypted credential storage and retrieval service.

    Usage:
        service = CredentialService(settings)
        await service.store_credential(user_id, "OKX", "DEMO", api_key, api_secret, passphrase)
        cred = await service.get_credential(user_id, "OKX", "DEMO")
        await service.revoke_credential(user_id, "OKX", "DEMO")
    """

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """
        Initialize credential service.

        Args:
            settings: Application settings (must have credential.encryption_key)
            session_factory: Async session factory (defaults to cached factory)

        Raises:
            CredentialNotConfiguredError: If encryption key is not configured
        """
        if not settings.credential.is_configured:
            raise CredentialNotConfiguredError(
                "CREDENTIAL_ENCRYPTION_KEY is not configured. "
                "Generate one with: python -c "
                '"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

        self._fernet = Fernet(settings.credential.get_key())
        self._session_factory = session_factory or get_session_factory()

    # =========================================================================
    # Encryption helpers
    # =========================================================================

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string. Returns base64-encoded ciphertext."""
        try:
            return self._fernet.encrypt(plaintext.encode()).decode()
        except Exception as exc:
            raise CredentialEncryptionError(f"Encryption failed: {exc}") from exc

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string. Returns plaintext."""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken as exc:
            raise CredentialEncryptionError(
                "Decryption failed: invalid token (wrong key or corrupted data)"
            ) from exc
        except Exception as exc:
            raise CredentialEncryptionError(f"Decryption failed: {exc}") from exc

    @staticmethod
    def _fingerprint(api_key: str) -> str:
        """
        Compute a non-reversible fingerprint of an API key.

        Used for audit correlation without exposing the key.
        Format: first 8 chars of SHA-256 hex digest.
        """
        return sha256(api_key.encode()).hexdigest()[:16]

    # =========================================================================
    # Audit logging
    # =========================================================================

    async def _audit_log(
        self,
        session: AsyncSession,
        actor: str,
        action: str,
        resource_id: str | None,
        details: dict[str, object] | None = None,
        success: bool = True,
    ) -> None:
        """Write an immutable audit log entry."""
        import json

        session.add(
            AuditLogModel(
                timestamp=datetime.now(UTC),
                actor=actor,
                action=action,
                resource_type="user_credential",
                resource_id=resource_id,
                details_json=json.dumps(details) if details else None,
                success=success,
            )
        )

    # =========================================================================
    # Public API
    # =========================================================================

    async def store_credential(
        self,
        user_id: str,
        exchange: str,
        environment: str,
        api_key: str,
        api_secret: str,
        passphrase: str | None = None,
        actor: str = "system",
    ) -> str:
        """
        Store (or replace) an encrypted credential for a user.

        Args:
            user_id: Application user ID
            exchange: Exchange ID ("OKX", "BINANCE", "BYBIT")
            environment: "DEMO" or "LIVE"
            api_key: Plaintext API key (encrypted before storage)
            api_secret: Plaintext API secret (encrypted before storage)
            passphrase: Plaintext passphrase (OKX only, encrypted before storage)
            actor: Who performed this action (for audit)

        Returns:
            credential_id of the stored credential

        Raises:
            ValueError: If exchange or environment is invalid
        """
        exchange_upper = exchange.upper()
        environment_upper = environment.upper()

        if exchange_upper not in ("OKX", "BINANCE", "BYBIT"):
            raise ValueError(f"Unsupported exchange: {exchange}")
        if environment_upper not in ("DEMO", "LIVE"):
            raise ValueError(f"Invalid environment: {environment}")
        if not api_key or not api_secret:
            raise ValueError("api_key and api_secret are required")
        if exchange_upper == "OKX" and not passphrase:
            raise ValueError("OKX requires a passphrase")

        credential_id = f"cred_{uuid.uuid4().hex[:12]}"
        fingerprint = self._fingerprint(api_key)
        now = datetime.now(UTC)

        # Encrypt before touching the database
        enc_api_key = self._encrypt(api_key)
        enc_api_secret = self._encrypt(api_secret)
        enc_passphrase = self._encrypt(passphrase) if passphrase else None

        async with self._session_factory() as session:
            # Check for existing credential (upsert)
            result = await session.execute(
                select(UserCredentialModel).where(
                    UserCredentialModel.user_id == user_id,
                    UserCredentialModel.exchange == exchange_upper,
                    UserCredentialModel.environment == environment_upper,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Replace existing credential
                existing.credential_id = credential_id
                existing.encrypted_api_key = enc_api_key
                existing.encrypted_api_secret = enc_api_secret
                existing.encrypted_passphrase = enc_passphrase
                existing.key_fingerprint = fingerprint
                existing.status = "ACTIVE"
                existing.revoked_at = None
                existing.verified_at = None
                existing.updated_at = now
                stored_id = existing.credential_id
                action = "credential_replaced"
            else:
                # Create new credential
                credential = UserCredentialModel(
                    credential_id=credential_id,
                    user_id=user_id,
                    exchange=exchange_upper,
                    environment=environment_upper,
                    encrypted_api_key=enc_api_key,
                    encrypted_api_secret=enc_api_secret,
                    encrypted_passphrase=enc_passphrase,
                    key_fingerprint=fingerprint,
                    status="ACTIVE",
                )
                session.add(credential)
                stored_id = credential_id
                action = "credential_stored"

            await self._audit_log(
                session,
                actor=actor,
                action=action,
                resource_id=stored_id,
                details={
                    "user_id": user_id,
                    "exchange": exchange_upper,
                    "environment": environment_upper,
                    "key_fingerprint": fingerprint,
                },
            )
            await session.commit()

        logger.info(
            "credential_stored",
            user_id=user_id,
            exchange=exchange_upper,
            environment=environment_upper,
            credential_id=stored_id,
            key_fingerprint=fingerprint,
        )
        return stored_id

    async def get_credential(
        self,
        user_id: str,
        exchange: str,
        environment: str,
        actor: str = "system",
    ) -> DecryptedCredential:
        """
        Retrieve and decrypt a credential for a user.

        Args:
            user_id: Application user ID
            exchange: Exchange ID ("OKX", "BINANCE", "BYBIT")
            environment: "DEMO" or "LIVE"
            actor: Who is accessing this credential (for audit)

        Returns:
            DecryptedCredential (in-memory only, never persist)

        Raises:
            CredentialNotFoundError: If no active credential exists
            CredentialEncryptionError: If decryption fails
        """
        exchange_upper = exchange.upper()
        environment_upper = environment.upper()

        async with self._session_factory() as session:
            result = await session.execute(
                select(UserCredentialModel).where(
                    UserCredentialModel.user_id == user_id,
                    UserCredentialModel.exchange == exchange_upper,
                    UserCredentialModel.environment == environment_upper,
                    UserCredentialModel.status == "ACTIVE",
                )
            )
            credential = result.scalar_one_or_none()

            if not credential:
                await self._audit_log(
                    session,
                    actor=actor,
                    action="credential_access_denied",
                    resource_id=None,
                    details={
                        "user_id": user_id,
                        "exchange": exchange_upper,
                        "environment": environment_upper,
                        "reason": "not_found",
                    },
                    success=False,
                )
                await session.commit()
                raise CredentialNotFoundError(
                    f"No active credential for user={user_id} "
                    f"exchange={exchange_upper} environment={environment_upper}"
                )

            # Decrypt
            api_key = self._decrypt(credential.encrypted_api_key)
            api_secret = self._decrypt(credential.encrypted_api_secret)
            passphrase = (
                self._decrypt(credential.encrypted_passphrase)
                if credential.encrypted_passphrase
                else None
            )

            # Update last_used_at
            credential.last_used_at = datetime.now(UTC)

            await self._audit_log(
                session,
                actor=actor,
                action="credential_accessed",
                resource_id=credential.credential_id,
                details={
                    "user_id": user_id,
                    "exchange": exchange_upper,
                    "environment": environment_upper,
                    "key_fingerprint": credential.key_fingerprint,
                },
            )
            await session.commit()

        logger.info(
            "credential_accessed",
            user_id=user_id,
            exchange=exchange_upper,
            environment=environment_upper,
            credential_id=credential.credential_id,
        )

        return DecryptedCredential(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            exchange=exchange_upper,
            environment=environment_upper,
        )

    async def revoke_credential(
        self,
        user_id: str,
        exchange: str,
        environment: str,
        actor: str = "system",
    ) -> bool:
        """
        Revoke (soft-delete) a credential.

        The encrypted data remains in the database for audit purposes,
        but the credential can no longer be used.

        Args:
            user_id: Application user ID
            exchange: Exchange ID
            environment: "DEMO" or "LIVE"
            actor: Who performed this action (for audit)

        Returns:
            True if a credential was revoked, False if not found
        """
        exchange_upper = exchange.upper()
        environment_upper = environment.upper()

        async with self._session_factory() as session:
            result = await session.execute(
                select(UserCredentialModel).where(
                    UserCredentialModel.user_id == user_id,
                    UserCredentialModel.exchange == exchange_upper,
                    UserCredentialModel.environment == environment_upper,
                    UserCredentialModel.status == "ACTIVE",
                )
            )
            credential = result.scalar_one_or_none()

            if not credential:
                return False

            credential.status = "REVOKED"
            credential.revoked_at = datetime.now(UTC)

            await self._audit_log(
                session,
                actor=actor,
                action="credential_revoked",
                resource_id=credential.credential_id,
                details={
                    "user_id": user_id,
                    "exchange": exchange_upper,
                    "environment": environment_upper,
                    "key_fingerprint": credential.key_fingerprint,
                },
            )
            await session.commit()

        logger.info(
            "credential_revoked",
            user_id=user_id,
            exchange=exchange_upper,
            environment=environment_upper,
        )
        return True

    async def has_credential(
        self,
        user_id: str,
        exchange: str,
        environment: str,
    ) -> bool:
        """
        Check if a user has an active credential (without decrypting).

        Args:
            user_id: Application user ID
            exchange: Exchange ID
            environment: "DEMO" or "LIVE"

        Returns:
            True if an active credential exists
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserCredentialModel.credential_id).where(
                    UserCredentialModel.user_id == user_id,
                    UserCredentialModel.exchange == exchange.upper(),
                    UserCredentialModel.environment == environment.upper(),
                    UserCredentialModel.status == "ACTIVE",
                )
            )
            return result.scalar_one_or_none() is not None

    async def mark_verified(
        self,
        user_id: str,
        exchange: str,
        environment: str,
    ) -> None:
        """
        Mark a credential as verified (API key validated against exchange).

        Args:
            user_id: Application user ID
            exchange: Exchange ID
            environment: "DEMO" or "LIVE"
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(UserCredentialModel).where(
                    UserCredentialModel.user_id == user_id,
                    UserCredentialModel.exchange == exchange.upper(),
                    UserCredentialModel.environment == environment.upper(),
                    UserCredentialModel.status == "ACTIVE",
                )
            )
            credential = result.scalar_one_or_none()

            if credential:
                credential.verified_at = datetime.now(UTC)
                await session.commit()

                logger.info(
                    "credential_verified",
                    user_id=user_id,
                    exchange=exchange.upper(),
                    environment=environment.upper(),
                )
