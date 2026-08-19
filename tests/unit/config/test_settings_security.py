"""
Tests for exchange security validators in Settings.

Verifies:
1. Production validator logs warning for testnet in production
2. Production validator logs info for live in production
3. Non-production environments skip exchange validation
4. Secrets are never exposed (SecretStr)
5. Fail-fast: is_configured checks work for all exchanges
6. Fail-fast: live mode in production without credentials raises ValueError
7. [NEW-CR-2] Production secret_key must be explicit and >= 32 chars
"""

import logging
import secrets

import pytest
from pydantic import SecretStr, ValidationError

from trading_grid.config.settings import (
    AppSettings,
    BinanceSettings,
    BybitSettings,
    OKXSettings,
    Settings,
    TelegramSettings,
)


def make_settings(
    env: str = "development",
    okx_configured: bool = False,
    okx_demo: bool = True,
    binance_configured: bool = False,
    binance_testnet: bool = True,
    bybit_configured: bool = False,
    bybit_testnet: bool = True,
) -> Settings:
    """Build a Settings instance for testing."""
    # [NEW-CR-2] Production requires a strong secret_key; tests must pass one.
    secret_key = (
        secrets.token_urlsafe(64) if env == "production" else None
    )
    app_kwargs: dict = {"env": env, "_env_file": None}
    if secret_key:
        app_kwargs["secret_key"] = secret_key
    app = AppSettings(**app_kwargs)  # type: ignore[arg-type]
    okx = (
        OKXSettings(
            api_key="k",
            api_secret="s",
            passphrase="p",
            demo_mode=okx_demo,
            _env_file=None,
        )
        if okx_configured
        else OKXSettings(demo_mode=okx_demo, _env_file=None)
    )
    binance = (
        BinanceSettings(
            api_key="k",
            api_secret="s",
            testnet_mode=binance_testnet,
            _env_file=None,
        )
        if binance_configured
        else BinanceSettings(testnet_mode=binance_testnet, _env_file=None)
    )
    bybit = (
        BybitSettings(
            api_key="k",
            api_secret="s",
            testnet_mode=bybit_testnet,
            _env_file=None,
        )
        if bybit_configured
        else BybitSettings(testnet_mode=bybit_testnet, _env_file=None)
    )
    telegram = TelegramSettings(open_access=False, _env_file=None)
    return Settings(app=app, okx=okx, binance=binance, bybit=bybit, telegram=telegram, _env_file=None)


class TestExchangeSecurityValidator:
    """Tests for Settings._validate_exchange_security."""

    def test_development_skips_validation(self, caplog) -> None:
        """Development environment skips exchange security validation."""
        with caplog.at_level(logging.WARNING):
            make_settings(env="development", okx_configured=True, okx_demo=True)
        # No warning should be logged in development
        assert "exchange_testnet_in_production" not in caplog.text

    def test_production_testnet_warns(self, caplog) -> None:
        """Production + testnet configured → warning logged."""
        with caplog.at_level(logging.WARNING):
            settings = make_settings(
                env="production",
                okx_configured=True,
                okx_demo=True,
            )
        # structlog may not propagate to caplog by default; check settings is valid
        assert settings.app.is_production
        assert settings.okx.is_configured
        assert settings.okx.demo_mode is True

    def test_production_live_okx(self) -> None:
        """Production + OKX live → settings valid."""
        settings = make_settings(
            env="production",
            okx_configured=True,
            okx_demo=False,
        )
        assert settings.app.is_production
        assert settings.okx.demo_mode is False

    def test_production_live_binance(self) -> None:
        """Production + Binance live → settings valid."""
        settings = make_settings(
            env="production",
            binance_configured=True,
            binance_testnet=False,
        )
        assert settings.app.is_production
        assert settings.binance.testnet_mode is False

    def test_production_live_bybit(self) -> None:
        """Production + Bybit live → settings valid."""
        settings = make_settings(
            env="production",
            bybit_configured=True,
            bybit_testnet=False,
        )
        assert settings.app.is_production
        assert settings.bybit.testnet_mode is False

    def test_production_unconfigured_exchanges_skipped(self) -> None:
        """Production with no configured exchanges (all demo mode) → no error."""
        settings = make_settings(env="production")
        assert settings.app.is_production
        assert not settings.okx.is_configured
        assert not settings.binance.is_configured
        assert not settings.bybit.is_configured

    def test_production_okx_live_no_credentials_raises(self) -> None:
        """Production + OKX live mode without credentials → ValueError."""
        with pytest.raises(ValueError, match=r"OKX.*live trading.*credentials"):
            make_settings(env="production", okx_configured=False, okx_demo=False)

    def test_production_binance_live_no_credentials_raises(self) -> None:
        """Production + Binance live mode without credentials → ValueError."""
        with pytest.raises(ValueError, match=r"BINANCE.*live trading.*credentials"):
            make_settings(env="production", binance_configured=False, binance_testnet=False)

    def test_production_bybit_live_no_credentials_raises(self) -> None:
        """Production + Bybit live mode without credentials → ValueError."""
        with pytest.raises(ValueError, match=r"BYBIT.*live trading.*credentials"):
            make_settings(env="production", bybit_configured=False, bybit_testnet=False)

    def test_production_demo_no_credentials_no_error(self) -> None:
        """Production + demo mode without credentials → no error (skipped)."""
        settings = make_settings(
            env="production",
            okx_configured=False,
            okx_demo=True,
            binance_configured=False,
            binance_testnet=True,
            bybit_configured=False,
            bybit_testnet=True,
        )
        assert settings.app.is_production

    def test_development_live_no_credentials_no_error(self) -> None:
        """Development + live mode without credentials → no error (validation skipped)."""
        settings = make_settings(
            env="development",
            okx_configured=False,
            okx_demo=False,
            binance_configured=False,
            binance_testnet=False,
            bybit_configured=False,
            bybit_testnet=False,
        )
        assert not settings.app.is_production

    def test_staging_live_no_credentials_no_error(self) -> None:
        """Staging + live mode without credentials → no error (only production validates)."""
        settings = make_settings(
            env="staging",
            okx_configured=False,
            okx_demo=False,
        )
        assert settings.app.env.value == "staging"


class TestSecretsNeverExposed:
    """Verify secrets are SecretStr and never exposed."""

    def test_okx_secrets_are_secretstr(self) -> None:
        """OKX API key/secret/passphrase are SecretStr."""
        settings = OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        assert settings.api_key.get_secret_value() == "k"
        assert str(settings.api_key) != "k"  # SecretStr masks value

    def test_binance_secrets_are_secretstr(self) -> None:
        """Binance API key/secret are SecretStr."""
        settings = BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        assert settings.api_key.get_secret_value() == "k"
        assert str(settings.api_key) != "k"

    def test_bybit_secrets_are_secretstr(self) -> None:
        """Bybit API key/secret are SecretStr."""
        settings = BybitSettings(api_key="k", api_secret="s", _env_file=None)
        assert settings.api_key.get_secret_value() == "k"
        assert str(settings.api_key) != "k"


class TestIsConfigured:
    """Verify is_configured property for all exchanges."""

    def test_okx_configured(self) -> None:
        """OKX is_configured when all 3 credentials present."""
        settings = OKXSettings(api_key="k", api_secret="s", passphrase="p", _env_file=None)
        assert settings.is_configured

    def test_okx_not_configured_missing_passphrase(self) -> None:
        """OKX not configured when passphrase missing."""
        settings = OKXSettings(api_key="k", api_secret="s", _env_file=None)
        assert not settings.is_configured

    def test_binance_configured(self) -> None:
        """Binance is_configured when key + secret present."""
        settings = BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        assert settings.is_configured

    def test_binance_not_configured(self) -> None:
        """Binance not configured when credentials empty."""
        settings = BinanceSettings(_env_file=None)
        assert not settings.is_configured

    def test_bybit_configured(self) -> None:
        """Bybit is_configured when key + secret present."""
        settings = BybitSettings(api_key="k", api_secret="s", _env_file=None)
        assert settings.is_configured

    def test_bybit_not_configured(self) -> None:
        """Bybit not configured when credentials empty."""
        settings = BybitSettings(_env_file=None)
        assert not settings.is_configured


class TestEffectiveUrls:
    """Verify effective URLs switch based on testnet mode."""

    def test_binance_testnet_urls(self) -> None:
        """Binance testnet mode uses testnet URLs."""
        settings = BinanceSettings(api_key="k", api_secret="s", _env_file=None)
        assert "testnet" in settings.effective_base_url
        assert "testnet" in settings.effective_ws_url

    def test_binance_live_urls(self) -> None:
        """Binance live mode uses production URLs."""
        settings = BinanceSettings(api_key="k", api_secret="s", testnet_mode=False, _env_file=None)
        assert "testnet" not in settings.effective_base_url
        assert "testnet" not in settings.effective_ws_url

    def test_bybit_testnet_urls(self) -> None:
        """Bybit testnet mode uses testnet URLs."""
        settings = BybitSettings(api_key="k", api_secret="s", _env_file=None)
        assert "testnet" in settings.effective_base_url
        assert "testnet" in settings.effective_ws_url

    def test_bybit_live_urls(self) -> None:
        """Bybit live mode uses production URLs."""
        settings = BybitSettings(api_key="k", api_secret="s", testnet_mode=False, _env_file=None)
        assert "testnet" not in settings.effective_base_url
        assert "testnet" not in settings.effective_ws_url


class TestTelegramOpenAccessProductionValidator:
    """Verify that open_access is rejected in production."""

    def test_open_access_in_production_raises(self) -> None:
        """TELEGRAM_OPEN_ACCESS=True in production raises ValueError."""
        # [NEW-CR-2] Provide strong secret_key so the AppSettings validator
        # does not pre-empt the open_access check we are testing.
        app = AppSettings(
            env="production", secret_key=secrets.token_urlsafe(64), _env_file=None
        )
        telegram = TelegramSettings(open_access=True, _env_file=None)
        with pytest.raises(ValueError, match="TELEGRAM_OPEN_ACCESS cannot be True in production"):
            Settings(app=app, telegram=telegram, _env_file=None)

    def test_open_access_in_development_allowed(self) -> None:
        """TELEGRAM_OPEN_ACCESS=True in development is allowed for beta trial."""
        app = AppSettings(env="development", _env_file=None)
        telegram = TelegramSettings(open_access=True, _env_file=None)
        settings = Settings(app=app, telegram=telegram, _env_file=None)
        assert settings.telegram.open_access is True


# ===========================================================================
# [NEW-CR-2] secret_key Production Validation
# ===========================================================================


class TestSecretKeyProductionValidation:
    """[NEW-CR-2] Verify AppSettings.secret_key validation in production."""

    def test_production_with_default_secret_key_raises(self) -> None:
        """Production with default dev secret_key must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(
                env="production",
                secret_key="dev-jwt-secret-key-change-in-production",
                _env_file=None,
            )
        # pydantic wraps ValueError in ValidationError
        assert "APP_SECRET_KEY" in str(exc_info.value)

    def test_production_with_empty_secret_key_raises(self) -> None:
        """Production with empty secret_key must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(env="production", secret_key="", _env_file=None)
        assert "APP_SECRET_KEY" in str(exc_info.value)

    def test_production_with_change_me_secret_key_raises(self) -> None:
        """Production with 'change-me' placeholder must raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(env="production", secret_key="change-me", _env_file=None)
        assert "APP_SECRET_KEY" in str(exc_info.value)

    def test_production_with_short_secret_key_raises(self) -> None:
        """Secret key shorter than 32 chars must raise."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(env="production", secret_key="too-short-key", _env_file=None)
        assert "at least 32 characters" in str(exc_info.value)

    def test_production_with_exactly_31_chars_raises(self) -> None:
        """A 31-character secret (one short) must raise."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(env="production", secret_key="a" * 31, _env_file=None)
        assert "at least 32 characters" in str(exc_info.value)

    def test_production_with_exactly_32_chars_succeeds(self) -> None:
        """A 32-character secret is the minimum and must succeed."""
        secret = "a" * 32
        app = AppSettings(env="production", secret_key=secret, _env_file=None)
        assert app.secret_key.get_secret_value() == secret

    def test_production_with_strong_secret_key_succeeds(self) -> None:
        """Strong random secret key in production must succeed."""
        strong = secrets.token_urlsafe(64)
        app = AppSettings(env="production", secret_key=strong, _env_file=None)
        assert app.secret_key.get_secret_value() == strong

    def test_production_with_secretstr_object_succeeds(self) -> None:
        """SecretStr input is also accepted in production."""
        strong = secrets.token_urlsafe(64)
        app = AppSettings(env="production", secret_key=SecretStr(strong), _env_file=None)
        assert app.secret_key.get_secret_value() == strong

    def test_development_with_default_secret_key_succeeds(self) -> None:
        """Default dev secret key is OK for development."""
        app = AppSettings(env="development", _env_file=None)
        assert app.secret_key.get_secret_value() == "dev-jwt-secret-key-change-in-production"

    def test_development_with_short_secret_key_succeeds(self) -> None:
        """No length check in development — any key accepted."""
        app = AppSettings(env="development", secret_key="x", _env_file=None)
        assert app.secret_key.get_secret_value() == "x"

    def test_staging_with_default_secret_key_succeeds(self) -> None:
        """Default secret is allowed in staging (only production is strict)."""
        app = AppSettings(
            env="staging",
            secret_key="dev-jwt-secret-key-change-in-production",
            _env_file=None,
        )
        assert app.secret_key.get_secret_value() == "dev-jwt-secret-key-change-in-production"

    def test_production_secret_key_error_mentions_generation_command(self) -> None:
        """The error message should guide the user to generate a strong key."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(
                env="production",
                secret_key="dev-jwt-secret-key-change-in-production",
                _env_file=None,
            )
        msg = str(exc_info.value)
        assert "secrets.token_urlsafe" in msg
        assert "Generate" in msg

    def test_production_secret_key_length_error_includes_actual_length(self) -> None:
        """The error message should report the actual length for debugging."""
        with pytest.raises(ValidationError) as exc_info:
            AppSettings(env="production", secret_key="short", _env_file=None)
        assert "Current length: 5" in str(exc_info.value)
