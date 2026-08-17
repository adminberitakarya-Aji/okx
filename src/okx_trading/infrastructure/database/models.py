"""
SQLAlchemy ORM models for persistence.

These models map domain objects to database tables.
Domain models remain pure; these are infrastructure concerns.

Tables:
- users: Application users
- telegram_identities: Telegram identity bindings
- exchange_integrations: Exchange connection status (OKX, Binance, Bybit)
- pairing_sessions: One-time pairing tokens
- blueprints: Grid strategy blueprints
- sections: Blueprint sections
- orders: Order history
- fills: Trade fills
- positions: Position tracking
- audit_logs: Immutable audit trail
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from okx_trading.infrastructure.database.base import Base, TimestampMixin

# =============================================================================
# USER IDENTITY MODELS
# =============================================================================


class UserModel(Base, TimestampMixin):
    """
    Application user.

    The central user entity that owns:
    - Telegram identity (control channel)
    - OKX integration (exchange connection)
    - Grids, blueprints, positions

    Security rules:
    - User is created on first /start via Telegram
    - Telegram identity and OKX integration are separate relationships
    - Unlinking Telegram does NOT delete OKX credentials
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="VIEWER")
    authorization_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")

    # Relationships
    telegram_identity: Mapped["TelegramIdentityModel | None"] = relationship(
        "TelegramIdentityModel", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    exchange_integrations: Mapped[list["ExchangeIntegrationModel"]] = relationship(
        "ExchangeIntegrationModel", back_populates="user", cascade="all, delete-orphan"
    )
    credentials: Mapped[list["UserCredentialModel"]] = relationship(
        "UserCredentialModel", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_users_status", "status"),
        Index("ix_users_role", "role"),
    )


class TelegramIdentityModel(Base, TimestampMixin):
    """
    Telegram identity binding.

    Maps a Telegram user to an application user.
    Telegram is the identity + control channel only.
    OKX credentials are NEVER stored here.

    States:
    - PENDING: User started /start but not yet approved (if approval required)
    - ACTIVE: Identity is linked and usable
    - REVOKED: Admin revoked this identity (user lost Telegram, etc.)
    - BLOCKED: User blocked the bot or was blocked
    """

    __tablename__ = "telegram_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    telegram_user_id: Mapped[int] = mapped_column(unique=True, nullable=False, index=True)
    chat_id: Mapped[int] = mapped_column(nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="telegram_identity")

    __table_args__ = (Index("ix_telegram_identities_status", "status"),)


class ExchangeIntegrationModel(Base, TimestampMixin):
    """
    Exchange integration status (multi-exchange: OKX, Binance, Bybit).

    Tracks the connection state between a user and an exchange.

    IMPORTANT: API credentials are NOT stored in this table.
    Credentials are stored in a secure vault / secrets manager.
    This table only tracks:
    - Connection status
    - Environment (DEMO/LIVE)
    - Verification state
    - Reference to credential location (never the credentials themselves)

    States:
    - NOT_CONNECTED: No exchange connection
    - CONNECTED: Credentials provided
    - VERIFIED: API key validated against exchange
    - ERROR: Connection error
    - DISCONNECTED: User disconnected
    """

    __tablename__ = "exchange_integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(16), nullable=False, default="OKX")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_CONNECTED")
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="DEMO")
    credential_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="exchange_integrations")

    __table_args__ = (
        UniqueConstraint("user_id", "exchange", name="uq_exchange_integrations_user_exchange"),
        Index("ix_exchange_integrations_status", "status"),
        Index("ix_exchange_integrations_exchange", "exchange"),
    )


class UserCredentialModel(Base, TimestampMixin):
    """
    Encrypted user exchange credentials (Phase 5: Multi-Tenant).

    Stores Fernet-encrypted API credentials per user per exchange.
    Security rules:
    - API key, secret, and passphrase are ALWAYS encrypted at rest
    - Plaintext credentials are NEVER stored or logged
    - key_fingerprint is a non-reversible hash for audit correlation
    - One credential per (user, exchange, environment) combination
    - DEMO and LIVE use separate credentials

    States:
    - ACTIVE: Credential is valid and usable
    - REVOKED: User revoked/disconnected this credential
    - ERROR: Credential failed verification
    """

    __tablename__ = "user_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    credential_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(16), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="DEMO")
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_api_secret: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["UserModel"] = relationship("UserModel", back_populates="credentials")

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "exchange",
            "environment",
            name="uq_user_credentials_user_exchange_env",
        ),
        Index("ix_user_credentials_user", "user_id"),
        Index("ix_user_credentials_status", "status"),
    )


# Backward-compatible alias
OKXIntegrationModel = ExchangeIntegrationModel


class PairingSessionModel(Base, TimestampMixin):
    """
    One-time pairing session for linking Telegram to application user.

    Used when pairing via deep link:
    1. Application creates pairing session with one-time token
    2. User clicks deep link: t.me/bot?start=<token>
    3. Telegram Gateway verifies token via Application API
    4. Identities are bound

    Security rules:
    - Token is single-use
    - Token has short expiry (default 10 minutes)
    - Token is bound to user_id
    - Token contains NO credentials
    """

    __tablename__ = "pairing_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pairing_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("ix_pairing_sessions_user", "user_id"),
        Index("ix_pairing_sessions_status", "status"),
    )


# =============================================================================
# TRADING MODELS
# =============================================================================


class BlueprintModel(Base, TimestampMixin):
    """
    Grid strategy blueprint persistence.

    Maps to domain/grid/models.py::Blueprint
    """

    __tablename__ = "blueprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blueprint_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Phase 5: per-user isolation. Nullable for backward compatibility with
    # system-generated blueprints (Phase 1-4).
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    market_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    total_capital: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    sections: Mapped[list["SectionModel"]] = relationship(
        "SectionModel", back_populates="blueprint", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_blueprints_market_status", "market_id", "status"),
        Index("ix_blueprints_user", "user_id"),
    )


class SectionModel(Base, TimestampMixin):
    """
    Blueprint section persistence.

    Maps to domain/grid/models.py::Section
    """

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    blueprint_id: Mapped[str] = mapped_column(
        ForeignKey("blueprints.blueprint_id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    upper_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    lower_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    grid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    grid_spacing_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    capital_allocation_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    gap_to_next_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INACTIVE")

    # Relationships
    blueprint: Mapped["BlueprintModel"] = relationship("BlueprintModel", back_populates="sections")

    __table_args__ = (
        UniqueConstraint("blueprint_id", "section_id", name="uq_sections_blueprint_section"),
    )


class OrderModel(Base, TimestampMixin):
    """
    Order persistence.

    Maps to domain/execution/models.py::Order
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Phase 5: per-user isolation. Nullable for backward compatibility.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    exchange_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="MARKET")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    filled_quantity: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    blueprint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_orders_market_status", "market_id", "status"),
        Index("ix_orders_blueprint", "blueprint_id"),
        Index("ix_orders_user", "user_id"),
    )


class FillModel(Base, TimestampMixin):
    """
    Trade fill persistence.

    Maps to domain/execution/models.py::Fill
    """

    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Phase 5: per-user isolation (denormalized for query efficiency).
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    market_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal("0"))
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_fills_order", "order_id"),
        Index("ix_fills_user", "user_id"),
    )


class PositionModel(Base, TimestampMixin):
    """
    Position persistence.

    Maps to domain/execution/models.py::Position
    """

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Phase 5: per-user isolation. Nullable for backward compatibility.
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )
    market_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    total_fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_positions_market_status", "market_id", "status"),
        Index("ix_positions_user", "user_id"),
    )


class AuditLogModel(Base):
    """
    Immutable audit log.

    Security rule: All operations are audit logged.
    Records are NEVER updated or deleted.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_audit_logs_actor", "actor"),
        Index("ix_audit_logs_action", "action"),
    )
