"""multi-exchange integrations: rename okx_integrations to exchange_integrations

Revision ID: 0003
Revises: ff65aa59d738
Create Date: 2026-08-16 13:08:00.000000+00:00

Changes:
1. Rename table okx_integrations -> exchange_integrations
2. Add column 'exchange' (VARCHAR(16), NOT NULL, DEFAULT 'OKX')
3. Drop old unique constraint on user_id (one user can now have multiple exchanges)
4. Add new unique constraint on (user_id, exchange)
5. Add index on exchange column
6. Rename status index
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "ff65aa59d738"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table("okx_integrations", "exchange_integrations")

    # 2. Add exchange column with default 'OKX' for existing rows
    op.add_column(
        "exchange_integrations",
        sa.Column(
            "exchange",
            sa.String(length=16),
            nullable=False,
            server_default="OKX",
        ),
    )

    # 3. Drop old unique constraint on user_id alone
    # (one user can now have multiple exchange integrations)
    op.drop_constraint(
        "uq_okx_integrations_user_id", "exchange_integrations", type_="unique"
    )

    # 4. Add new unique constraint on (user_id, exchange)
    op.create_unique_constraint(
        "uq_exchange_integrations_user_exchange",
        "exchange_integrations",
        ["user_id", "exchange"],
    )

    # 5. Rename old status index
    op.drop_index("ix_okx_integrations_status", table_name="exchange_integrations")
    op.create_index(
        "ix_exchange_integrations_status",
        "exchange_integrations",
        ["status"],
        unique=False,
    )

    # 6. Add index on exchange column
    op.create_index(
        "ix_exchange_integrations_exchange",
        "exchange_integrations",
        ["exchange"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse order of upgrade

    # Drop new indexes
    op.drop_index(
        "ix_exchange_integrations_exchange", table_name="exchange_integrations"
    )
    op.drop_index(
        "ix_exchange_integrations_status", table_name="exchange_integrations"
    )

    # Restore old status index
    op.create_index(
        "ix_okx_integrations_status",
        "exchange_integrations",
        ["status"],
        unique=False,
    )

    # Drop new unique constraint, restore old one
    op.drop_constraint(
        "uq_exchange_integrations_user_exchange",
        "exchange_integrations",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_okx_integrations_user_id",
        "exchange_integrations",
        ["user_id"],
    )

    # Drop exchange column
    op.drop_column("exchange_integrations", "exchange")

    # Rename table back
    op.rename_table("exchange_integrations", "okx_integrations")