"""add user_credentials table for multi-tenant credential storage

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16 16:20:00.000000+00:00

Phase 5: Multi-Tenant Beta — Credential Storage (5A)

Changes:
1. Create user_credentials table with Fernet-encrypted credential columns
2. Unique constraint on (user_id, exchange, environment)
3. Indexes on user_id and status

Security rules:
- API credentials are ALWAYS encrypted at rest (Fernet symmetric encryption)
- Plaintext credentials are NEVER stored or logged
- key_fingerprint is a non-reversible SHA-256 hash for audit correlation
- DEMO and LIVE use separate credentials per exchange
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("credential_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("exchange", sa.String(length=16), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False, server_default="DEMO"),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("encrypted_api_secret", sa.Text(), nullable=False),
        sa.Column("encrypted_passphrase", sa.Text(), nullable=True),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ACTIVE"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
        sa.UniqueConstraint(
            "user_id", "exchange", "environment",
            name="uq_user_credentials_user_exchange_env",
        ),
    )
    op.create_index("ix_user_credentials_user", "user_credentials", ["user_id"], unique=False)
    op.create_index("ix_user_credentials_status", "user_credentials", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_credentials_status", table_name="user_credentials")
    op.drop_index("ix_user_credentials_user", table_name="user_credentials")
    op.drop_table("user_credentials")