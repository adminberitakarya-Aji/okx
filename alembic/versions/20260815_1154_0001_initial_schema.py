"""Initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-08-15 11:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Blueprints table
    op.create_table(
        'blueprints',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('blueprint_id', sa.String(length=64), nullable=False),
        sa.Column('market_id', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('total_capital', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=True),
        sa.Column('approved_by', sa.String(length=64), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_blueprints')),
        sa.UniqueConstraint('blueprint_id', name=op.f('uq_blueprints_blueprint_id')),
    )
    op.create_index(op.f('ix_blueprints_market_id'), 'blueprints', ['market_id'], unique=False)
    op.create_index('ix_blueprints_market_status', 'blueprints', ['market_id', 'status'], unique=False)

    # Sections table
    op.create_table(
        'sections',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('blueprint_id', sa.String(length=64), nullable=False),
        sa.Column('section_id', sa.Integer(), nullable=False),
        sa.Column('upper_price', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('lower_price', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('grid_count', sa.Integer(), nullable=False),
        sa.Column('grid_spacing_pct', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('capital_allocation_pct', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('gap_to_next_pct', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['blueprint_id'], ['blueprints.blueprint_id'], name=op.f('fk_sections_blueprint_id_blueprints'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sections')),
        sa.UniqueConstraint('blueprint_id', 'section_id', name='uq_sections_blueprint_section'),
    )

    # Orders table
    op.create_table(
        'orders',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('order_id', sa.String(length=64), nullable=False),
        sa.Column('exchange_order_id', sa.String(length=64), nullable=True),
        sa.Column('market_id', sa.String(length=32), nullable=False),
        sa.Column('side', sa.String(length=8), nullable=False),
        sa.Column('order_type', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('filled_quantity', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('average_fill_price', sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column('fee', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('blueprint_id', sa.String(length=64), nullable=True),
        sa.Column('section_id', sa.Integer(), nullable=True),
        sa.Column('grid_level', sa.Integer(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_orders')),
        sa.UniqueConstraint('order_id', name=op.f('uq_orders_order_id')),
        sa.UniqueConstraint('idempotency_key', name=op.f('uq_orders_idempotency_key')),
    )
    op.create_index(op.f('ix_orders_market_id'), 'orders', ['market_id'], unique=False)
    op.create_index('ix_orders_market_status', 'orders', ['market_id', 'status'], unique=False)
    op.create_index('ix_orders_blueprint', 'orders', ['blueprint_id'], unique=False)

    # Fills table
    op.create_table(
        'fills',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(length=64), nullable=False),
        sa.Column('order_id', sa.String(length=64), nullable=False),
        sa.Column('market_id', sa.String(length=32), nullable=False),
        sa.Column('side', sa.String(length=8), nullable=False),
        sa.Column('price', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('fee', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], name=op.f('fk_fills_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fills')),
        sa.UniqueConstraint('trade_id', name=op.f('uq_fills_trade_id')),
    )
    op.create_index(op.f('ix_fills_market_id'), 'fills', ['market_id'], unique=False)
    op.create_index('ix_fills_order', 'fills', ['order_id'], unique=False)

    # Positions table
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('position_id', sa.String(length=64), nullable=False),
        sa.Column('market_id', sa.String(length=32), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('average_entry_price', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('realized_pnl', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('total_fees', sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_positions')),
        sa.UniqueConstraint('position_id', name=op.f('uq_positions_position_id')),
    )
    op.create_index(op.f('ix_positions_market_id'), 'positions', ['market_id'], unique=False)
    op.create_index('ix_positions_market_status', 'positions', ['market_id', 'status'], unique=False)

    # Audit logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs')),
    )
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_index('ix_audit_logs_actor', 'audit_logs', ['actor'], unique=False)
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('positions')
    op.drop_table('fills')
    op.drop_table('orders')
    op.drop_table('sections')
    op.drop_table('blueprints')