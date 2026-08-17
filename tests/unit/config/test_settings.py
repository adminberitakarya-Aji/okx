"""
Unit tests for configuration settings.

Tests verify:
1. Default values are sensible
2. Secrets are protected (SecretStr)
3. Validation works
4. Environment-based configuration
"""

from decimal import Decimal

import pytest

from trading_grid.config.settings import (
    AppSettings,
    DatabaseSettings,
    Environment,
    OKXSettings,
    ResearchSettings,
    RiskSettings,
    Settings,
    TelegramSettings,
    get_settings,
)


class TestAppSettings:
    """Tests for AppSettings."""

    def test_default_values(self) -> None:
        """Default values must be secure-by-default."""
        settings = AppSettings(_env_file=None)
        assert settings.name == "OKX AI Trading Grid System"
        assert settings.env == Environment.DEVELOPMENT
        # SECURITY: debug and dev auth bypass must default to False.
        assert settings.debug is False
        assert settings.dev_auth_enabled is False
        assert settings.log_level == "INFO"

    def test_is_development(self) -> None:
        """is_development should return True for development env."""
        settings = AppSettings(env=Environment.DEVELOPMENT, _env_file=None)
        assert settings.is_development is True
        assert settings.is_production is False

    def test_is_production(self) -> None:
        """is_production should return True for production env."""
        settings = AppSettings(env=Environment.PRODUCTION, _env_file=None)
        assert settings.is_production is True
        assert settings.is_development is False

    def test_debug_true_rejected_in_production(self) -> None:
        """SECURITY: APP_DEBUG=true must be rejected when APP_ENV=production."""
        with pytest.raises(ValueError, match="APP_DEBUG"):
            AppSettings(env=Environment.PRODUCTION, debug=True, _env_file=None)

    def test_debug_true_allowed_in_development(self) -> None:
        """APP_DEBUG=true is allowed in development (docs/CORS only)."""
        settings = AppSettings(env=Environment.DEVELOPMENT, debug=True, _env_file=None)
        assert settings.debug is True

    def test_dev_auth_enabled_rejected_in_production(self) -> None:
        """SECURITY: dev auth bypass must be rejected outside development."""
        with pytest.raises(ValueError, match="APP_DEV_AUTH_ENABLED"):
            AppSettings(env=Environment.PRODUCTION, dev_auth_enabled=True, _env_file=None)

    def test_dev_auth_enabled_rejected_in_staging(self) -> None:
        """SECURITY: dev auth bypass must be rejected in staging."""
        with pytest.raises(ValueError, match="APP_DEV_AUTH_ENABLED"):
            AppSettings(env=Environment.STAGING, dev_auth_enabled=True, _env_file=None)

    def test_dev_auth_enabled_allowed_in_development(self) -> None:
        """Dev auth bypass is only allowed with explicit opt-in in development."""
        settings = AppSettings(env=Environment.DEVELOPMENT, dev_auth_enabled=True, _env_file=None)
        assert settings.dev_auth_enabled is True


class TestDatabaseSettings:
    """Tests for DatabaseSettings."""

    def test_default_url(self) -> None:
        """Default URL should be localhost PostgreSQL."""
        settings = DatabaseSettings()
        assert "postgresql+asyncpg" in settings.get_url()

    def test_secret_url_not_exposed(self) -> None:
        """URL should be SecretStr and not exposed in repr."""
        settings = DatabaseSettings()
        repr_str = repr(settings.url)
        assert "postgres" not in repr_str or "SecretStr" in repr_str

    def test_pool_size_validation(self) -> None:
        """Pool size must be positive."""
        with pytest.raises(ValueError, match="pool_size"):
            DatabaseSettings(pool_size=0)


class TestOKXSettings:
    """Tests for OKXSettings."""

    def test_default_demo_mode(self) -> None:
        """Default should be demo mode (safety first)."""
        settings = OKXSettings(_env_file=None)
        assert settings.demo_mode is True

    def test_not_configured_by_default(self) -> None:
        """Should not be configured without API keys."""
        # _env_file=None isolates test from local .env/.env.local files
        settings = OKXSettings(_env_file=None)
        assert settings.is_configured is False

    def test_configured_with_keys(self) -> None:
        """Should be configured when all keys are set."""
        settings = OKXSettings(
            api_key="test-key",
            api_secret="test-secret",
            passphrase="test-passphrase",
        )
        assert settings.is_configured is True

    def test_secrets_not_exposed(self) -> None:
        """API secrets should not be exposed in repr."""
        settings = OKXSettings(
            api_key="super-secret-key",
            api_secret="super-secret-secret",
            passphrase="super-secret-passphrase",
        )
        repr_str = repr(settings)
        assert "super-secret-key" not in repr_str
        assert "super-secret-secret" not in repr_str
        assert "super-secret-passphrase" not in repr_str


class TestTelegramSettings:
    """Tests for TelegramSettings."""

    def test_not_configured_by_default(self) -> None:
        """Should not be configured without bot token."""
        # _env_file=None isolates test from local .env/.env.local files
        settings = TelegramSettings(_env_file=None)
        assert settings.is_configured is False

    def test_configured_with_token(self) -> None:
        """Should be configured when bot token is set."""
        settings = TelegramSettings(bot_token="123456:ABC-DEF")
        assert settings.is_configured is True


class TestRiskSettings:
    """Tests for RiskSettings."""

    def test_default_values(self) -> None:
        """Default risk limits should be conservative."""
        settings = RiskSettings()
        assert settings.max_capital_per_grid == Decimal("100")
        assert settings.max_total_capital == Decimal("500")
        assert settings.max_drawdown_pct == Decimal("10")
        assert settings.max_concurrent_grids == 5

    def test_percentage_validation(self) -> None:
        """Percentages must be between 0 and 100."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            RiskSettings(max_drawdown_pct=Decimal("150"))

    def test_zero_percentage_invalid(self) -> None:
        """Zero percentage should be invalid."""
        with pytest.raises(ValueError, match="between 0 and 100"):
            RiskSettings(max_drawdown_pct=Decimal("0"))


class TestResearchSettings:
    """Tests for ResearchSettings."""

    def test_default_values(self) -> None:
        """Default research settings should be sensible."""
        settings = ResearchSettings()
        assert settings.data_dir == "data/research"
        assert settings.candle_interval == "1H"
        assert settings.lookback_days == 365 * 3  # 3 years
        assert settings.min_candles == 1000


class TestSettings:
    """Tests for root Settings."""

    def test_aggregates_all_settings(self) -> None:
        """Settings should aggregate all sub-settings."""
        settings = Settings()
        assert settings.app is not None
        assert settings.database is not None
        assert settings.okx is not None
        assert settings.telegram is not None
        assert settings.risk is not None
        assert settings.research is not None

    def test_get_settings_cached(self) -> None:
        """get_settings should return cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_cache_clear(self) -> None:
        """cache_clear should allow reload."""
        settings1 = get_settings()
        get_settings.cache_clear()
        settings2 = get_settings()
        # After cache clear, should be new instance
        assert settings1 is not settings2
