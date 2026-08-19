"""
Application settings using pydantic-settings.

Configuration is loaded from environment variables and .env file.
Secrets are NEVER logged or exposed in responses.

Environment hierarchy:
1. Environment variables (highest priority)
2. .env file
3. Default values (lowest priority)
"""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

import structlog
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()


class Environment(StrEnum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AppSettings(BaseSettings):
    """
    Core application settings.

    Environment variables: APP_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    """

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = "OKX AI Trading Grid System"
    version: str = "0.1.0"
    env: Environment = Environment.DEVELOPMENT
    # SECURITY: debug defaults to False. It controls docs/CORS exposure only.
    # It must NEVER be used to gate authentication bypass.
    debug: bool = False
    # SECURITY: dev_auth_enabled defaults to False. When True (and only in the
    # development environment), unauthenticated requests receive a DEMO-only
    # identity. This is an explicit opt-in and is forbidden outside development.
    dev_auth_enabled: bool = False
    secret_key: SecretStr = SecretStr("dev-jwt-secret-key-change-in-production")
    log_level: str = "INFO"
    timezone: str = "UTC"

    @model_validator(mode="after")
    def _validate_security_defaults(self) -> "AppSettings":
        """Fail fast if security-sensitive flags are misconfigured for prod/staging."""
        # Dev auth bypass must never be enabled outside development.
        if self.dev_auth_enabled and not self.is_development:
            raise ValueError(
                "APP_DEV_AUTH_ENABLED=true is only permitted when APP_ENV=development. "
                "Refusing to start with dev auth bypass in "
                f"env={self.env.value!r}."
            )
        # Debug mode (docs + permissive CORS) must never be on in production.
        if self.debug and self.is_production:
            raise ValueError(
                "APP_DEBUG=true is not permitted when APP_ENV=production. "
                "Set APP_DEBUG=false for production deployments."
            )
        # [NEW-CR-2] Production must use a strong, non-default secret_key
        # (used for HS256 JWT signing). Default dev secret is unsafe for
        # production because JWTs could be forged by anyone with the source.
        if self.is_production:
            secret = self.secret_key.get_secret_value()
            _FORBIDDEN_SECRETS = (
                "",
                "change-me",
                "dev-jwt-secret-key-change-in-production",
            )
            if secret in _FORBIDDEN_SECRETS:
                raise ValueError(
                    "APP_SECRET_KEY must be explicitly set in production. "
                    "The default dev secret is unsafe for production. "
                    "Generate a strong random key with: "
                    "python -c 'import secrets; print(secrets.token_urlsafe(64))'"
                )
            if len(secret) < 32:
                raise ValueError(
                    "APP_SECRET_KEY must be at least 32 characters for HS256 "
                    f"JWT signing. Current length: {len(secret)}."
                )
        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.env == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.env == Environment.DEVELOPMENT


class DatabaseSettings(BaseSettings):
    """
    Database settings.

    Environment variables: DATABASE_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    Development: Supabase (PostgreSQL)
    Production: PostgreSQL + TimescaleDB (VPS)
    """

    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    url: SecretStr = SecretStr("postgresql+asyncpg://postgres:postgres@localhost:5432/trading_grid")
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30

    @field_validator("pool_size")
    @classmethod
    def validate_pool_size(cls, v: int) -> int:
        """Pool size must be positive."""
        if v < 1:
            raise ValueError("pool_size must be >= 1")
        return v

    def get_url(self) -> str:
        """Get database URL (for internal use only, never log)."""
        return self.url.get_secret_value()


class OKXSettings(BaseSettings):
    """
    OKX API settings.

    Environment variables: OKX_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    Security rules:
    - API keys: Read + Trade only, Withdraw DISABLED
    - DEMO and LIVE use separate credentials
    - Secrets never in logs
    """

    model_config = SettingsConfigDict(
        env_prefix="OKX_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    passphrase: SecretStr = SecretStr("")
    demo_mode: bool = True
    base_url: str = "https://www.okx.com"
    ws_url: str = "wss://ws.okx.com:8443/ws/v5"
    timeout: int = 30
    max_retries: int = 3

    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(
            self.api_key.get_secret_value()
            and self.api_secret.get_secret_value()
            and self.passphrase.get_secret_value()
        )


class BinanceSettings(BaseSettings):
    """
    Binance API settings.

    Environment variables: BINANCE_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    Security rules:
    - API keys: Read + Trade only, Withdraw DISABLED
    - Testnet (demo) and Live use separate credentials
    - Secrets never in logs

    Note: Binance auth uses HMAC-SHA256 with api_key + api_secret only
    (no passphrase). Demo trading uses the Binance Spot Testnet.
    """

    model_config = SettingsConfigDict(
        env_prefix="BINANCE_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    # testnet_mode=True → Binance Spot Testnet (demo). ALWAYS start with True.
    testnet_mode: bool = True
    base_url: str = "https://api.binance.com"
    testnet_base_url: str = "https://testnet.binance.vision"
    ws_url: str = "wss://stream.binance.com:9443/ws"
    testnet_ws_url: str = "wss://testnet.binance.vision/ws"
    timeout: int = 30
    max_retries: int = 3
    # [NEW-M-2] recvWindow for signed requests (ms). Configurable to handle
    # high network latency on VPS deployments. Default 5000ms per Binance spec.
    recv_window_ms: int = 5000

    @property
    def demo_mode(self) -> bool:
        """Alias for testnet_mode (consistent naming with other exchanges)."""
        return self.testnet_mode

    @property
    def effective_base_url(self) -> str:
        """Get base URL based on testnet mode."""
        return self.testnet_base_url if self.testnet_mode else self.base_url

    @property
    def effective_ws_url(self) -> str:
        """Get WebSocket URL based on testnet mode."""
        return self.testnet_ws_url if self.testnet_mode else self.ws_url

    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key.get_secret_value() and self.api_secret.get_secret_value())


class BybitSettings(BaseSettings):
    """
    Bybit API settings.

    Environment variables: BYBIT_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    Security rules:
    - API keys: Read + Trade only, Withdraw DISABLED
    - Testnet (demo) and Live use separate credentials
    - Secrets never in logs

    Note: Bybit auth uses HMAC-SHA256 with api_key + api_secret only
    (no passphrase). Demo trading uses the Bybit Testnet (API v5).
    """

    model_config = SettingsConfigDict(
        env_prefix="BYBIT_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_key: SecretStr = SecretStr("")
    api_secret: SecretStr = SecretStr("")
    # testnet_mode=True → Bybit Testnet (demo). ALWAYS start with True.
    testnet_mode: bool = True
    base_url: str = "https://api.bybit.com"
    testnet_base_url: str = "https://api-testnet.bybit.com"
    ws_url: str = "wss://stream.bybit.com/v5/private"
    testnet_ws_url: str = "wss://stream-testnet.bybit.com/v5/private"
    timeout: int = 30
    max_retries: int = 3

    @property
    def demo_mode(self) -> bool:
        """Alias for testnet_mode (consistent naming with other exchanges)."""
        return self.testnet_mode

    @property
    def effective_base_url(self) -> str:
        """Get base URL based on testnet mode."""
        return self.testnet_base_url if self.testnet_mode else self.base_url

    @property
    def effective_ws_url(self) -> str:
        """Get WebSocket URL based on testnet mode."""
        return self.testnet_ws_url if self.testnet_mode else self.ws_url

    @property
    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.api_key.get_secret_value() and self.api_secret.get_secret_value())


class TelegramSettings(BaseSettings):
    """
    Telegram bot settings.

    Environment variables: TELEGRAM_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    """

    model_config = SettingsConfigDict(
        env_prefix="TELEGRAM_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: SecretStr = SecretStr("")
    allowed_user_ids: list[int] = Field(default_factory=list)
    webhook_url: str | None = None
    polling_timeout: int = 30
    # Open access mode: any Telegram user can interact with the bot.
    # Intended for beta trial only. MUST be false in production.
    open_access: bool = False

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v: object) -> list[int]:
        """Parse comma-separated string, JSON list, or single int into list[int]."""
        if isinstance(v, str):
            # Handle comma-separated: "123,456,789"
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, list):
            return [int(x) for x in v]
        if isinstance(v, int):
            # pydantic-settings may parse a single numeric env value as int
            return [v]
        return []

    @property
    def is_configured(self) -> bool:
        """Check if bot token is configured."""
        return bool(self.bot_token.get_secret_value())


class CredentialSettings(BaseSettings):
    """
    Credential encryption settings (Phase 5: Multi-Tenant).

    Environment variables: CREDENTIAL_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)

    Security rules:
    - CREDENTIAL_ENCRYPTION_KEY is a Fernet key (base64-encoded 32 bytes)
    - Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    - NEVER log or expose this key
    - Required for multi-tenant credential storage
    """

    model_config = SettingsConfigDict(
        env_prefix="CREDENTIAL_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    encryption_key: SecretStr = SecretStr("")

    @property
    def is_configured(self) -> bool:
        """Check if encryption key is configured."""
        return bool(self.encryption_key.get_secret_value())

    def get_key(self) -> bytes:
        """Get encryption key as bytes (for internal use only, never log)."""
        return self.encryption_key.get_secret_value().encode()


class RiskSettings(BaseSettings):
    """
    Risk management settings.

    Environment variables: RISK_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    These are default limits, can be overridden per-user.
    """

    model_config = SettingsConfigDict(
        env_prefix="RISK_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    max_capital_per_grid: Decimal = Decimal("100")
    max_total_capital: Decimal = Decimal("500")
    max_drawdown_pct: Decimal = Decimal("10")
    max_concurrent_grids: int = 5
    max_position_pct: Decimal = Decimal("20")
    min_profitable_exit_pct: Decimal = Decimal("0.5")
    max_slippage_pct: Decimal = Decimal("1")
    max_execution_cost_pct: Decimal = Decimal("2")
    min_reserve_pct: Decimal = Decimal("10")
    max_exposure_pct: Decimal = Decimal("80")

    @field_validator(
        "max_drawdown_pct",
        "max_position_pct",
        "min_profitable_exit_pct",
        "max_slippage_pct",
        "max_execution_cost_pct",
        "min_reserve_pct",
        "max_exposure_pct",
    )
    @classmethod
    def validate_percentage(cls, v: Decimal) -> Decimal:
        """Percentage must be between 0 and 100."""
        if not (Decimal("0") < v <= Decimal("100")):
            raise ValueError("Percentage must be between 0 and 100")
        return v


class ResearchSettings(BaseSettings):
    """
    AI Research pipeline settings.

    Environment variables: RESEARCH_*
    Env files: .env (defaults), .env.local (secrets, overrides .env)
    """

    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_",
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    data_dir: str = "data/research"
    models_dir: str = "models"
    parquet_compression: str = "snappy"
    candle_interval: str = "1H"
    lookback_days: int = 365 * 3  # 3 years
    min_candles: int = 1000
    n_jobs: int = -1  # Use all CPU cores
    # [TD-7] Derived ML feature version — configurable via RESEARCH_DERIVED_ML_VERSION
    derived_ml_version: str = "fml-v001"


class Settings(BaseSettings):
    """
    Root settings aggregating all sub-settings.

    Env files: .env (defaults), .env.local (secrets, overrides .env)

    Usage:
        from trading_grid.config.settings import get_settings
        settings = get_settings()
        print(settings.app.name)
        print(settings.okx.demo_mode)
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    okx: OKXSettings = Field(default_factory=OKXSettings)
    binance: BinanceSettings = Field(default_factory=BinanceSettings)
    bybit: BybitSettings = Field(default_factory=BybitSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    credential: CredentialSettings = Field(default_factory=CredentialSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)

    @model_validator(mode="after")
    def _validate_exchange_security(self) -> "Settings":
        """
        Validate exchange security settings for production.

        Rules:
        1. In production, if an exchange is set to LIVE mode (testnet_mode=False
           / demo_mode=False) but credentials are missing, raise ValueError
           (fail-fast at startup).
        2. In production, if an exchange is configured with testnet_mode=True,
           log a warning (testnet in production is unusual but not forbidden,
           e.g., staging environments).
        3. In production, if an exchange is configured for LIVE trading with
           complete credentials, log confirmation.
        4. Secrets are never logged.
        """
        if not self.app.is_production:
            return self

        # FAIL-FAST: Open access is strictly forbidden in production
        if self.telegram.open_access:
            raise ValueError(
                "TELEGRAM_OPEN_ACCESS cannot be True in production environment. "
                "Open access is intended for beta trials only."
            )

        # Check each exchange for production security compliance.
        # Each entry contains: exchange name, configured flag, demo flag,
        # and the credential env var names for the error message.
        exchanges = [
            (
                "OKX",
                self.okx.is_configured,
                self.okx.demo_mode,
                "OKX_API_KEY/OKX_API_SECRET/OKX_PASSPHRASE",
            ),
            (
                "BINANCE",
                self.binance.is_configured,
                self.binance.testnet_mode,
                "BINANCE_API_KEY/BINANCE_API_SECRET",
            ),
            (
                "BYBIT",
                self.bybit.is_configured,
                self.bybit.testnet_mode,
                "BYBIT_API_KEY/BYBIT_API_SECRET",
            ),
        ]

        for exchange_name, is_configured, is_demo, cred_vars in exchanges:
            # FAIL-FAST: live mode in production requires complete credentials
            if not is_demo and not is_configured:
                raise ValueError(
                    f"{exchange_name}: production environment with live trading "
                    f"(testnet_mode=False / demo_mode=False) requires complete "
                    f"credentials, but none are configured. Either provide "
                    f"{cred_vars}, or set testnet/demo mode to true."
                )

            if not is_configured:
                continue

            if is_demo:
                # Testnet/demo mode in production — warn but allow (staging)
                logger.warning(
                    "exchange_testnet_in_production",
                    exchange=exchange_name,
                    env=self.app.env.value,
                    message=(
                        f"{exchange_name} is configured with testnet/demo mode in "
                        f"production environment. This is unusual — verify this is "
                        f"intentional (e.g., staging)."
                    ),
                )
            else:
                # Live mode in production — credentials already verified by
                # is_configured check. Log confirmation (no secrets).
                logger.info(
                    "exchange_live_in_production",
                    exchange=exchange_name,
                    env=self.app.env.value,
                    message=f"{exchange_name} is configured for LIVE trading in production.",
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Settings are loaded once and cached for performance.
    Call get_settings.cache_clear() or clear_settings_cache() to reload.
    """
    return Settings()


def clear_settings_cache() -> None:
    """Clear the cached settings instance for test isolation."""
    get_settings.cache_clear()

