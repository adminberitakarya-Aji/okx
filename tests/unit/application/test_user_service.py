"""
Tests for UserService — user identity management.

Covers:
- get_or_create_user: new user creation, existing user retrieval
- get_user_by_telegram: found and not found
- get_telegram_identity: found and not found
- get_exchange_integration / get_okx_integration
- get_all_exchange_integrations
- is_exchange_connected / is_okx_connected
- update_exchange_status / update_okx_status
- unlink_telegram
- create_pairing_session
- verify_pairing_token: valid, invalid, expired, already used
"""

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import pytest

from trading_grid.application.services.user_service import UserService
from trading_grid.infrastructure.database.models import (
    ExchangeIntegrationModel,
    PairingSessionModel,
    TelegramIdentityModel,
    UserModel,
)


def _make_mock_session():
    """Create a mock AsyncSession with execute/add/commit."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_mock_session_factory(session):
    """Create a mock async_sessionmaker that returns the given session."""
    factory = MagicMock()
    # Make factory() return an async context manager
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    factory.return_value = cm
    return factory


def _make_user(user_id: str = "usr_abc123", display_name: str = "Test") -> MagicMock:
    """Create a mock UserModel."""
    user = MagicMock(spec=UserModel)
    user.user_id = user_id
    user.display_name = display_name
    user.role = "VIEWER"
    user.authorization_level = 0
    user.status = "ACTIVE"
    return user


def _make_identity(
    user_id: str = "usr_abc123",
    telegram_user_id: int = 12345,
    chat_id: int = 67890,
    status: str = "ACTIVE",
) -> MagicMock:
    """Create a mock TelegramIdentityModel."""
    identity = MagicMock(spec=TelegramIdentityModel)
    identity.user_id = user_id
    identity.telegram_user_id = telegram_user_id
    identity.chat_id = chat_id
    identity.username = "testuser"
    identity.first_name = "Test"
    identity.status = status
    identity.linked_at = datetime.now(UTC)
    identity.last_active_at = datetime.now(UTC)
    return identity


def _make_integration(
    user_id: str = "usr_abc123",
    exchange: str = "OKX",
    status: str = "NOT_CONNECTED",
) -> MagicMock:
    """Create a mock ExchangeIntegrationModel."""
    integration = MagicMock(spec=ExchangeIntegrationModel)
    integration.user_id = user_id
    integration.exchange = exchange
    integration.status = status
    integration.environment = "DEMO"
    integration.credential_ref = None
    integration.account_id = None
    integration.verified_at = None
    integration.last_error = None
    return integration


def _make_pairing(
    user_id: str = "usr_abc123",
    status: str = "PENDING",
    expires_at: datetime | None = None,
) -> MagicMock:
    """Create a mock PairingSessionModel."""
    pairing = MagicMock(spec=PairingSessionModel)
    pairing.pairing_id = "PAIR-ABCD1234"
    pairing.user_id = user_id
    pairing.token_hash = sha256(b"tg_connect_testtoken").hexdigest()
    pairing.status = status
    pairing.expires_at = expires_at or (datetime.now(UTC) + timedelta(minutes=10))
    pairing.used_at = None
    pairing.telegram_user_id = None
    return pairing


def _mock_scalar_result(value):
    """Create a mock result with scalar_one_or_none returning value."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(values):
    """Create a mock result with scalars().all() returning values."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = values
    result.scalars.return_value = scalars
    return result


class TestGetOrCreateUser:
    """Tests for get_or_create_user."""

    @pytest.mark.asyncio
    async def test_creates_new_user_when_no_identity(self):
        """New telegram user creates UserModel + TelegramIdentity + OKX integration."""
        session = _make_mock_session()
        # First query: no identity found
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        user, is_new = await service.get_or_create_user(
            telegram_user_id=12345,
            chat_id=67890,
            first_name="Alice",
            username="alice",
        )

        assert is_new is True
        assert user.user_id.startswith("usr_")
        assert user.display_name == "Alice"
        # Should add user, identity, OKX integration, and audit log [A-M4]
        assert session.add.call_count == 4
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_existing_user_when_identity_exists(self):
        """Existing telegram identity returns existing user without creating."""
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()

        # First query: identity found; second query: user found
        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result_user, is_new = await service.get_or_create_user(
            telegram_user_id=12345,
            chat_id=67890,
        )

        assert is_new is False
        assert result_user is user
        # No new objects added
        session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_last_active_for_existing_identity(self):
        """Existing identity gets last_active_at updated."""
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()
        old_active = identity.last_active_at

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.get_or_create_user(telegram_user_id=12345, chat_id=67890)

        assert identity.last_active_at >= old_active


class TestGetUserByTelegram:
    """Tests for get_user_by_telegram."""

    @pytest.mark.asyncio
    async def test_returns_user_when_found(self):
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_user_by_telegram(12345)
        assert result is user

    @pytest.mark.asyncio
    async def test_returns_none_when_no_identity(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_user_by_telegram(99999)
        assert result is None


class TestGetTelegramIdentity:
    """Tests for get_telegram_identity."""

    @pytest.mark.asyncio
    async def test_returns_identity_when_found(self):
        session = _make_mock_session()
        identity = _make_identity()
        session.execute.return_value = _mock_scalar_result(identity)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_telegram_identity(12345)
        assert result is identity

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_telegram_identity(99999)
        assert result is None


class TestGetExchangeIntegration:
    """Tests for get_exchange_integration and get_okx_integration."""

    @pytest.mark.asyncio
    async def test_returns_integration_when_found(self):
        session = _make_mock_session()
        integration = _make_integration(exchange="BINANCE", status="CONNECTED")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_exchange_integration("usr_abc123", "BINANCE")
        assert result is integration

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_exchange_integration("usr_abc123", "BYBIT")
        assert result is None

    @pytest.mark.asyncio
    async def test_okx_integration_wrapper(self):
        """get_okx_integration delegates to get_exchange_integration with OKX."""
        session = _make_mock_session()
        integration = _make_integration(exchange="OKX")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_okx_integration("usr_abc123")
        assert result is integration


class TestGetAllExchangeIntegrations:
    """Tests for get_all_exchange_integrations."""

    @pytest.mark.asyncio
    async def test_returns_all_integrations(self):
        session = _make_mock_session()
        okx = _make_integration(exchange="OKX")
        binance = _make_integration(exchange="BINANCE")
        session.execute.return_value = _mock_scalars_result([okx, binance])
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_all_exchange_integrations("usr_abc123")
        assert len(result) == 2
        assert okx in result
        assert binance in result

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalars_result([])
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.get_all_exchange_integrations("usr_abc123")
        assert result == []


class TestIsExchangeConnected:
    """Tests for is_exchange_connected and is_okx_connected."""

    @pytest.mark.asyncio
    async def test_returns_true_when_connected(self):
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()
        integration = _make_integration(status="CONNECTED")

        session.execute.side_effect = [
            _mock_scalar_result(identity),  # get_user_by_telegram: identity
            _mock_scalar_result(user),  # get_user_by_telegram: user
            _mock_scalar_result(integration),  # get_exchange_integration
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_exchange_connected(12345, "OKX")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_when_verified(self):
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()
        integration = _make_integration(status="VERIFIED")

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
            _mock_scalar_result(integration),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_exchange_connected(12345, "OKX")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_connected(self):
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()
        integration = _make_integration(status="NOT_CONNECTED")

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
            _mock_scalar_result(integration),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_exchange_connected(12345, "OKX")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_user(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_exchange_connected(99999, "OKX")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_no_integration(self):
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
            _mock_scalar_result(None),  # no integration
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_exchange_connected(12345, "BINANCE")
        assert result is False

    @pytest.mark.asyncio
    async def test_okx_connected_wrapper(self):
        """is_okx_connected delegates to is_exchange_connected with OKX."""
        session = _make_mock_session()
        identity = _make_identity()
        user = _make_user()
        integration = _make_integration(status="VERIFIED")

        session.execute.side_effect = [
            _mock_scalar_result(identity),
            _mock_scalar_result(user),
            _mock_scalar_result(integration),
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.is_okx_connected(12345)
        assert result is True


class TestUpdateExchangeStatus:
    """Tests for update_exchange_status and update_okx_status."""

    @pytest.mark.asyncio
    async def test_updates_existing_integration(self):
        session = _make_mock_session()
        integration = _make_integration(status="NOT_CONNECTED")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_exchange_status(
            user_id="usr_abc123",
            status="CONNECTED",
            exchange="OKX",
            environment="DEMO",
            credential_ref="vault://okx/creds",
            account_id="acct-123",
        )

        assert integration.status == "CONNECTED"
        assert integration.environment == "DEMO"
        assert integration.credential_ref == "vault://okx/creds"
        assert integration.account_id == "acct-123"
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_creates_new_integration_if_not_exists(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_exchange_status(
            user_id="usr_abc123",
            status="CONNECTED",
            exchange="BINANCE",
        )

        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, ExchangeIntegrationModel)
        assert added.exchange == "BINANCE"
        assert added.status == "CONNECTED"

    @pytest.mark.asyncio
    async def test_sets_verified_at_on_verified_status(self):
        session = _make_mock_session()
        integration = _make_integration(status="CONNECTED")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_exchange_status(
            user_id="usr_abc123",
            status="VERIFIED",
            exchange="OKX",
        )

        assert integration.status == "VERIFIED"
        assert integration.verified_at is not None

    @pytest.mark.asyncio
    async def test_sets_error_on_error_status(self):
        session = _make_mock_session()
        integration = _make_integration(status="CONNECTED")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_exchange_status(
            user_id="usr_abc123",
            status="ERROR",
            exchange="OKX",
            error="Invalid API key",
        )

        assert integration.status == "ERROR"
        assert integration.last_error == "Invalid API key"

    @pytest.mark.asyncio
    async def test_exchange_uppercased(self):
        session = _make_mock_session()
        integration = _make_integration(exchange="BYBIT")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_exchange_status(
            user_id="usr_abc123",
            status="CONNECTED",
            exchange="bybit",
        )

        assert integration.status == "CONNECTED"

    @pytest.mark.asyncio
    async def test_okx_status_wrapper(self):
        """update_okx_status delegates to update_exchange_status with OKX."""
        session = _make_mock_session()
        integration = _make_integration(status="NOT_CONNECTED")
        session.execute.return_value = _mock_scalar_result(integration)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.update_okx_status(
            user_id="usr_abc123",
            status="VERIFIED",
        )

        assert integration.status == "VERIFIED"


class TestUnlinkTelegram:
    """Tests for unlink_telegram."""

    @pytest.mark.asyncio
    async def test_unlinks_existing_identity(self):
        session = _make_mock_session()
        identity = _make_identity(status="ACTIVE")
        session.execute.return_value = _mock_scalar_result(identity)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.unlink_telegram(12345)

        assert result is True
        assert identity.status == "REVOKED"
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_returns_false_when_no_identity(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result = await service.unlink_telegram(99999)
        assert result is False


class TestCreatePairingSession:
    """Tests for create_pairing_session."""

    @pytest.mark.asyncio
    async def test_creates_pairing_session(self):
        session = _make_mock_session()
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        pairing_id, raw_token = await service.create_pairing_session("usr_abc123")

        assert pairing_id.startswith("PAIR-")
        assert raw_token.startswith("tg_connect_")
        assert session.add.call_count == 2
        session.commit.assert_awaited()

        pairing_model = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], PairingSessionModel))
        assert pairing_model.user_id == "usr_abc123"
        assert pairing_model.status == "PENDING"
        # Token hash matches raw token
        assert pairing_model.token_hash == sha256(raw_token.encode()).hexdigest()

    @pytest.mark.asyncio
    async def test_custom_expiry(self):
        session = _make_mock_session()
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        await service.create_pairing_session("usr_abc123", expiry_minutes=5)

        pairing_model = next(c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], PairingSessionModel))
        # Expiry should be ~5 minutes from now
        expected_expiry = datetime.now(UTC) + timedelta(minutes=5)
        assert abs((pairing_model.expires_at - expected_expiry).total_seconds()) < 5


class TestVerifyPairingToken:
    """Tests for verify_pairing_token."""

    @pytest.mark.asyncio
    async def test_valid_token_binds_new_identity(self):
        session = _make_mock_session()
        pairing = _make_pairing(status="PENDING")
        user = _make_user()

        session.execute.side_effect = [
            _mock_scalar_result(pairing),  # find pairing
            _mock_scalar_result(None),  # no existing identity
            _mock_scalar_result(user),  # pairing user
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result_user, is_new = await service.verify_pairing_token(
            raw_token="tg_connect_testtoken",
            telegram_user_id=12345,
            chat_id=67890,
        )

        assert result_user is user
        assert is_new is True
        assert pairing.status == "USED"
        assert pairing.telegram_user_id == 12345
        # New identity and audit log added
        assert session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        session = _make_mock_session()
        session.execute.return_value = _mock_scalar_result(None)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        with pytest.raises(ValueError, match="Invalid pairing token"):
            await service.verify_pairing_token(
                raw_token="tg_connect_invalid",
                telegram_user_id=12345,
                chat_id=67890,
            )

    @pytest.mark.asyncio
    async def test_already_used_token_raises(self):
        session = _make_mock_session()
        pairing = _make_pairing(status="USED")
        session.execute.return_value = _mock_scalar_result(pairing)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        with pytest.raises(ValueError, match="already used"):
            await service.verify_pairing_token(
                raw_token="tg_connect_testtoken",
                telegram_user_id=12345,
                chat_id=67890,
            )

    @pytest.mark.asyncio
    async def test_expired_token_raises_and_marks_expired(self):
        session = _make_mock_session()
        pairing = _make_pairing(
            status="PENDING",
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        session.execute.return_value = _mock_scalar_result(pairing)
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        with pytest.raises(ValueError, match="expired"):
            await service.verify_pairing_token(
                raw_token="tg_connect_testtoken",
                telegram_user_id=12345,
                chat_id=67890,
            )

        assert pairing.status == "EXPIRED"
        session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_existing_identity_updates_and_returns(self):
        session = _make_mock_session()
        pairing = _make_pairing(status="PENDING")
        existing_identity = _make_identity(user_id="usr_existing")
        existing_user = _make_user(user_id="usr_existing")

        session.execute.side_effect = [
            _mock_scalar_result(pairing),  # find pairing
            _mock_scalar_result(existing_identity),  # existing identity
            _mock_scalar_result(existing_user),  # existing user
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        result_user, is_new = await service.verify_pairing_token(
            raw_token="tg_connect_testtoken",
            telegram_user_id=12345,
            chat_id=67890,
        )

        assert result_user is existing_user
        assert is_new is False
        assert existing_identity.status == "ACTIVE"

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self):
        session = _make_mock_session()
        pairing = _make_pairing(status="PENDING")

        session.execute.side_effect = [
            _mock_scalar_result(pairing),  # find pairing
            _mock_scalar_result(None),  # no existing identity
            _mock_scalar_result(None),  # user not found
        ]
        factory = _make_mock_session_factory(session)
        service = UserService(session_factory=factory)

        with pytest.raises(ValueError, match="User not found"):
            await service.verify_pairing_token(
                raw_token="tg_connect_testtoken",
                telegram_user_id=12345,
                chat_id=67890,
            )
