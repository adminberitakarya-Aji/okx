"""add user_id to blueprints, orders, fills, positions for per-user isolation

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-16 16:30:00.000000+00:00

Phase 5: Multi-Tenant Beta — Per-User Data Isolation (5C)

Changes:
1. Add nullable user_id column to blueprints, orders, fills, positions
2. Foreign key to users.user_id with ON DELETE SET NULL
3. Indexes on user_id for per-user query isolation

Design decisions:
- user_id is NULLABLE for backward compatibility with system-generated
  records from Phase 1-4 (single-tenant era)
- ON DELETE SET NULL preserves trading history when a user is deleted
  (audit/compliance requirement)
- fills.user_id is denormalized from orders for query efficiency
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("blueprints", "orders", "fills", "positions")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("user_id", sa.String(length=64), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_user_id_users",
            table,
            "users",
            ["user_id"],
            ["user_id"],
            ondelete="SET NULL",
        )
        op.create_index(f"ix_{table}_user", table, ["user_id"])


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_user", table_name=table)
        op.drop_constraint(f"fk_{table}_user_id_users", table, type_="foreignkey")
        op.drop_column(table, "user_id")