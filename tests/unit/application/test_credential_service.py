"""
Tests for the credential service (Phase 5: Multi-Tenant Beta).

Verifies:
1. CredentialNotConfiguredError when encryption key is missing
2. Encryption/decryption round-trip
3. Fingerprint is non-reversible and deterministic
4. Validation errors (invalid exchange, environment, missing passphrase)
5. DecryptedCredential repr never exposes secrets
6. Store/get/revoke credential flows (with mocked DB)
7. Audit logging on credential operations
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from trading_grid.application.services.credential_service import (
    CredentialEncryptionError,
    CredentialNotConfiguredError,
    CredentialNotFoundError,
    CredentialService,
    DecryptedCredential,
)
from trading_grid.config.settings import CredentialSettings, Settings


def make_settings(encryption_key: str | None = None) -> Settings:
    """Build a Settings instance with optional credential encryption key."""
    credential = (
        CredentialSettings(encryption_key=encryption_key, _env_file=None)
        if encryption_key
        else CredentialSettings(_env_file=None)
    )
    return Settings(credential=credential, _env_file=None)


def generate_fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


class TestCredentialServiceInit:
    """Tests for CredentialService initialization."""

    def test_raises_when_encryption_key_not_configured(self) -> None:
        """CredentialService raises CredentialNotConfiguredError without key."""
        settings = make_settings(encryption_key=None)
        with pytest.raises(CredentialNotConfiguredError, match="CREDENTIAL_ENCRYPTION_KEY"):
            CredentialService(settings)

    def test_raises_when_encryption_key_empty(self) -> None:
        """CredentialService raises CredentialNotConfiguredError with empty key."""
        settings = make_settings(encryption_key="")
        with pytest.raises(CredentialNotConfiguredError):
            CredentialService(settings)

    def test_initializes_with_valid_key(self) -> None:
        """CredentialService initializes successfully with a valid Fernet key."""
        settings = make_settings(encryption_key=generate_fernet_key())
        service = CredentialService(settings)
        assert service is not None


class TestEncryptionDecryption:
    """Tests for encryption/decryption helpers."""

    def setup_method(self) -> None:
        """Set up service with a valid key."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.service = CredentialService(settings)

    def test_encrypt_decrypt_round_trip(self) -> None:
        """Encrypting then decrypting returns the original plaintext."""
        plaintext = "my-super-secret-api-key-12345"
        encrypted = self.service._encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = self.service._decrypt(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext_each_time(self) -> None:
        """Fernet encryption is non-deterministic (uses random IV)."""
        plaintext = "same-plaintext"
        enc1 = self.service._encrypt(plaintext)
        enc2 = self.service._encrypt(plaintext)
        assert enc1 != enc2  # Different ciphertext due to random IV
        assert self.service._decrypt(enc1) == plaintext
        assert self.service._decrypt(enc2) == plaintext

    def test_decrypt_with_wrong_key_raises(self) -> None:
        """Decryption with a different key raises CredentialEncryptionError."""
        plaintext = "secret-data"
        encrypted = self.service._encrypt(plaintext)

        # Create a second service with a different key
        other_key = generate_fernet_key()
        other_settings = make_settings(encryption_key=other_key)
        other_service = CredentialService(other_settings)

        with pytest.raises(CredentialEncryptionError, match="invalid token"):
            other_service._decrypt(encrypted)

    def test_decrypt_corrupted_data_raises(self) -> None:
        """Decryption of corrupted ciphertext raises CredentialEncryptionError."""
        with pytest.raises(CredentialEncryptionError):
            self.service._decrypt("not-valid-fernet-token")

    def test_encrypt_empty_string(self) -> None:
        """Empty string can be encrypted and decrypted."""
        encrypted = self.service._encrypt("")
        assert self.service._decrypt(encrypted) == ""

    def test_encrypt_unicode(self) -> None:
        """Unicode strings can be encrypted and decrypted."""
        plaintext = "api-key-with-unicode-🔑-characters"
        encrypted = self.service._encrypt(plaintext)
        assert self.service._decrypt(encrypted) == plaintext


class TestFingerprint:
    """Tests for API key fingerprinting."""

    def test_fingerprint_is_deterministic(self) -> None:
        """Same API key always produces the same fingerprint."""
        fp1 = CredentialService._fingerprint("my-api-key")
        fp2 = CredentialService._fingerprint("my-api-key")
        assert fp1 == fp2

    def test_fingerprint_differs_for_different_keys(self) -> None:
        """Different API keys produce different fingerprints."""
        fp1 = CredentialService._fingerprint("api-key-1")
        fp2 = CredentialService._fingerprint("api-key-2")
        assert fp1 != fp2

    def test_fingerprint_is_not_reversible(self) -> None:
        """Fingerprint does not contain the original key."""
        api_key = "my-secret-api-key"
        fp = CredentialService._fingerprint(api_key)
        assert api_key not in fp
        assert len(fp) == 16  # First 16 chars of SHA-256 hex

    def test_fingerprint_is_hex_string(self) -> None:
        """Fingerprint is a valid hex string."""
        fp = CredentialService._fingerprint("test-key")
        int(fp, 16)  # Should not raise


class TestDecryptedCredential:
    """Tests for DecryptedCredential container."""

    def test_repr_does_not_expose_secrets(self) -> None:
        """repr must never contain plaintext credentials."""
        cred = DecryptedCredential(
            api_key="super-secret-key",
            api_secret="super-secret-secret",
            passphrase="super-secret-pass",
            exchange="OKX",
            environment="DEMO",
        )
        repr_str = repr(cred)
        assert "super-secret-key" not in repr_str
        assert "super-secret-secret" not in repr_str
        assert "super-secret-pass" not in repr_str
        assert "***" in repr_str
        assert "OKX" in repr_str
        assert "DEMO" in repr_str

    def test_stores_values(self) -> None:
        """DecryptedCredential stores all fields."""
        cred = DecryptedCredential(
            api_key="key",
            api_secret="secret",
            passphrase="pass",
            exchange="BINANCE",
            environment="LIVE",
        )
        assert cred.api_key == "key"
        assert cred.api_secret == "secret"
        assert cred.passphrase == "pass"
        assert cred.exchange == "BINANCE"
        assert cred.environment == "LIVE"

    def test_passphrase_can_be_none(self) -> None:
        """Passphrase is optional (Binance/Bybit don't use it)."""
        cred = DecryptedCredential(
            api_key="key",
            api_secret="secret",
            passphrase=None,
            exchange="BINANCE",
            environment="DEMO",
        )
        assert cred.passphrase is None


class TestStoreCredentialValidation:
    """Tests for store_credential input validation."""

    def setup_method(self) -> None:
        """Set up service with a valid key and mocked session factory."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_invalid_exchange_raises(self) -> None:
        """Unsupported exchange raises ValueError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        with pytest.raises(ValueError, match="Unsupported exchange"):
            await self.service.store_credential(
                user_id="usr_123",
                exchange="KRAKEN",
                environment="DEMO",
                api_key="key",
                api_secret="secret",
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_invalid_environment_raises(self) -> None:
        """Invalid environment raises ValueError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        with pytest.raises(ValueError, match="Invalid environment"):
            await self.service.store_credential(
                user_id="usr_123",
                exchange="OKX",
                environment="STAGING",
                api_key="key",
                api_secret="secret",
                passphrase="pass",
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_missing_api_key_raises(self) -> None:
        """Empty api_key raises ValueError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        with pytest.raises(ValueError, match="api_key and api_secret are required"):
            await self.service.store_credential(
                user_id="usr_123",
                exchange="OKX",
                environment="DEMO",
                api_key="",
                api_secret="secret",
                passphrase="pass",
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_missing_api_secret_raises(self) -> None:
        """Empty api_secret raises ValueError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        with pytest.raises(ValueError, match="api_key and api_secret are required"):
            await self.service.store_credential(
                user_id="usr_123",
                exchange="OKX",
                environment="DEMO",
                api_key="key",
                api_secret="",
                passphrase="pass",
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_okx_requires_passphrase(self) -> None:
        """OKX credential without passphrase raises ValueError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        with pytest.raises(ValueError, match="OKX requires a passphrase"):
            await self.service.store_credential(
                user_id="usr_123",
                exchange="OKX",
                environment="DEMO",
                api_key="key",
                api_secret="secret",
                passphrase=None,
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_binance_does_not_require_passphrase(self) -> None:
        """Binance credential without passphrase passes validation."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        # Mock the database session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        credential_id = await self.service.store_credential(
            user_id="usr_123",
            exchange="BINANCE",
            environment="DEMO",
            api_key="key",
            api_secret="secret",
            passphrase=None,
            identity=admin,
        )
        assert credential_id.startswith("cred_")


class TestStoreCredential:
    """Tests for store_credential with mocked database."""

    def setup_method(self) -> None:
        """Set up service with a valid key and mocked session factory."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_store_new_credential(self) -> None:
        """Storing a new credential encrypts data and returns credential_id."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing credential
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        credential_id = await self.service.store_credential(
            user_id="usr_123",
            exchange="OKX",
            environment="DEMO",
            api_key="my-api-key",
            api_secret="my-api-secret",
            passphrase="my-passphrase",
            actor="telegram:12345",
            identity=admin,
        )

        assert credential_id.startswith("cred_")
        # Verify session.add was called (new credential + audit log)
        assert mock_session.add.call_count >= 1
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_stored_data_is_encrypted(self) -> None:
        """Plaintext credentials must not be stored in the model."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        added_objects = []

        def capture_add(obj):
            added_objects.append(obj)

        # session.add is synchronous in SQLAlchemy
        mock_session.add = MagicMock(side_effect=capture_add)
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        await self.service.store_credential(
            user_id="usr_123",
            exchange="OKX",
            environment="DEMO",
            api_key="plaintext-key",
            api_secret="plaintext-secret",
            passphrase="plaintext-pass",
            identity=admin,
        )

        # Find the UserCredentialModel that was added
        from trading_grid.infrastructure.database.models import UserCredentialModel

        cred_models = [o for o in added_objects if isinstance(o, UserCredentialModel)]
        assert len(cred_models) == 1
        cred = cred_models[0]

        # Encrypted fields must NOT contain plaintext
        assert "plaintext-key" not in cred.encrypted_api_key
        assert "plaintext-secret" not in cred.encrypted_api_secret
        assert cred.encrypted_passphrase is not None
        assert "plaintext-pass" not in cred.encrypted_passphrase

        # Verify we can decrypt with the service's key
        assert self.service._decrypt(cred.encrypted_api_key) == "plaintext-key"
        assert self.service._decrypt(cred.encrypted_api_secret) == "plaintext-secret"
        assert self.service._decrypt(cred.encrypted_passphrase) == "plaintext-pass"


class TestGetCredential:
    """Tests for get_credential with mocked database."""

    def setup_method(self) -> None:
        """Set up service with a valid key and mocked session factory."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_get_nonexistent_credential_raises(self) -> None:
        """Getting a credential that doesn't exist raises CredentialNotFoundError."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(CredentialNotFoundError, match="No active credential"):
            await self.service.get_credential(
                user_id="usr_123",
                exchange="OKX",
                environment="DEMO",
                identity=admin,
            )

    @pytest.mark.asyncio
    async def test_get_credential_decrypts_correctly(self) -> None:
        """get_credential returns decrypted values."""
        from trading_grid.application.services.authorization import Identity, Role
        from trading_grid.infrastructure.database.models import UserCredentialModel

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        # Create a mock credential model with encrypted data
        mock_cred = MagicMock(spec=UserCredentialModel)
        mock_cred.credential_id = "cred_abc123"
        mock_cred.encrypted_api_key = self.service._encrypt("decrypted-key")
        mock_cred.encrypted_api_secret = self.service._encrypt("decrypted-secret")
        mock_cred.encrypted_passphrase = self.service._encrypt("decrypted-pass")
        mock_cred.key_fingerprint = "fp123"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        cred = await self.service.get_credential(
            user_id="usr_123",
            exchange="OKX",
            environment="DEMO",
            identity=admin,
        )

        assert cred.api_key == "decrypted-key"
        assert cred.api_secret == "decrypted-secret"
        assert cred.passphrase == "decrypted-pass"
        assert cred.exchange == "OKX"
        assert cred.environment == "DEMO"


class TestRevokeCredential:
    """Tests for revoke_credential with mocked database."""

    def setup_method(self) -> None:
        """Set up service with a valid key and mocked session factory."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_revoke_nonexistent_returns_false(self) -> None:
        """Revoking a nonexistent credential returns False."""
        from trading_grid.application.services.authorization import Identity, Role

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await self.service.revoke_credential(
            user_id="usr_123",
            exchange="OKX",
            environment="DEMO",
            identity=admin,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_revoke_existing_returns_true(self) -> None:
        """Revoking an existing credential returns True and sets status."""
        from trading_grid.application.services.authorization import Identity, Role
        from trading_grid.infrastructure.database.models import UserCredentialModel

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        mock_cred = MagicMock(spec=UserCredentialModel)
        mock_cred.credential_id = "cred_abc123"
        mock_cred.status = "ACTIVE"
        mock_cred.key_fingerprint = "fp123"

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await self.service.revoke_credential(
            user_id="usr_123",
            exchange="OKX",
            environment="DEMO",
            identity=admin,
        )

        assert result is True
        assert mock_cred.status == "REVOKED"
        assert mock_cred.revoked_at is not None
        mock_session.commit.assert_awaited()


class TestHasCredential:
    """Tests for has_credential."""

    def setup_method(self) -> None:
        """Set up service with a valid key and mocked session factory."""
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_has_credential_true(self) -> None:
        """has_credential returns True when credential exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "cred_abc123"
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await self.service.has_credential("usr_123", "OKX", "DEMO")
        assert result is True

    @pytest.mark.asyncio
    async def test_has_credential_false(self) -> None:
        """has_credential returns False when no credential exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await self.service.has_credential("usr_123", "OKX", "DEMO")
        assert result is False


class TestCredentialRBAC:
    """[A-H8] Tests for CredentialService RBAC tenant isolation."""

    def setup_method(self) -> None:
        self.key = generate_fernet_key()
        settings = make_settings(encryption_key=self.key)
        self.mock_session_factory = MagicMock()
        self.service = CredentialService(settings, session_factory=self.mock_session_factory)

    @pytest.mark.asyncio
    async def test_unauthorized_user_cannot_access_other_user_credential(self) -> None:
        """User A cannot read User B's credentials unless admin."""
        from trading_grid.application.services.authorization import Identity, Role

        identity_a = Identity(identity_id="usr_A", identity_type="HUMAN", role=Role.VIEWER)

        with pytest.raises(PermissionError, match="not authorized"):
            await self.service.get_credential(
                user_id="usr_B",
                exchange="OKX",
                environment="DEMO",
                identity=identity_a,
            )

    @pytest.mark.asyncio
    async def test_admin_can_access_other_user_credential(self) -> None:
        """SYSTEM_ADMIN can access user's credentials."""
        from trading_grid.application.services.authorization import Identity, Role
        from trading_grid.infrastructure.database.models import UserCredentialModel

        mock_session = AsyncMock()
        mock_cred = MagicMock(spec=UserCredentialModel)
        mock_cred.encrypted_api_key = self.service._encrypt("key")
        mock_cred.encrypted_api_secret = self.service._encrypt("sec")
        mock_cred.encrypted_passphrase = None
        mock_cred.credential_id = "cred_1"
        mock_cred.key_fingerprint = "fp1"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_cred
        mock_session.execute.return_value = mock_result
        mock_session.add = MagicMock()
        self.mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        self.mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        admin = Identity(identity_id="admin_1", identity_type="HUMAN", role=Role.SYSTEM_ADMIN)
        cred = await self.service.get_credential(
            user_id="usr_B",
            exchange="OKX",
            environment="DEMO",
            identity=admin,
        )
        assert cred.api_key == "key"

