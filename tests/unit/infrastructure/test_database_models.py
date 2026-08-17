"""
Unit tests for database ORM models.

Tests verify model structure without requiring a live database:
- Table names
- Column definitions
- Constraints and indexes
- Relationships
"""

from decimal import Decimal

from sqlalchemy import inspect

from okx_trading.infrastructure.database.base import Base
from okx_trading.infrastructure.database.models import (
    AuditLogModel,
    BlueprintModel,
    FillModel,
    OrderModel,
    PositionModel,
    SectionModel,
)


class TestBlueprintModel:
    """Tests for BlueprintModel."""

    def test_table_name(self) -> None:
        """Table name should be 'blueprints'."""
        assert BlueprintModel.__tablename__ == "blueprints"

    def test_columns_exist(self) -> None:
        """Required columns should exist."""
        mapper = inspect(BlueprintModel)
        column_names = {c.key for c in mapper.columns}

        required = {
            "id",
            "blueprint_id",
            "market_id",
            "status",
            "total_capital",
            "created_by",
            "approved_by",
            "approved_at",
            "metadata_json",
            "created_at",
            "updated_at",
        }
        assert required.issubset(column_names)

    def test_blueprint_id_unique(self) -> None:
        """blueprint_id should have unique constraint."""
        mapper = inspect(BlueprintModel)
        col = mapper.columns["blueprint_id"]
        assert col.unique is True

    def test_instantiation(self) -> None:
        """Model should be instantiable with valid values."""
        bp = BlueprintModel(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            status="DRAFT",
            total_capital=Decimal("1000"),
        )
        assert bp.blueprint_id == "bp-001"
        assert bp.market_id == "BTC-USDT"


class TestSectionModel:
    """Tests for SectionModel."""

    def test_table_name(self) -> None:
        """Table name should be 'sections'."""
        assert SectionModel.__tablename__ == "sections"

    def test_columns_exist(self) -> None:
        """Required columns should exist."""
        mapper = inspect(SectionModel)
        column_names = {c.key for c in mapper.columns}

        required = {
            "id",
            "blueprint_id",
            "section_id",
            "upper_price",
            "lower_price",
            "grid_count",
            "grid_spacing_pct",
            "capital_allocation_pct",
            "gap_to_next_pct",
            "status",
        }
        assert required.issubset(column_names)

    def test_foreign_key_to_blueprints(self) -> None:
        """blueprint_id should be FK to blueprints."""
        mapper = inspect(SectionModel)
        col = mapper.columns["blueprint_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "blueprints.blueprint_id"


class TestOrderModel:
    """Tests for OrderModel."""

    def test_table_name(self) -> None:
        """Table name should be 'orders'."""
        assert OrderModel.__tablename__ == "orders"

    def test_columns_exist(self) -> None:
        """Required columns should exist."""
        mapper = inspect(OrderModel)
        column_names = {c.key for c in mapper.columns}

        required = {
            "id",
            "order_id",
            "exchange_order_id",
            "market_id",
            "side",
            "order_type",
            "status",
            "quantity",
            "filled_quantity",
            "price",
            "average_fill_price",
            "fee",
            "idempotency_key",
        }
        assert required.issubset(column_names)

    def test_order_id_unique(self) -> None:
        """order_id should have unique constraint."""
        mapper = inspect(OrderModel)
        col = mapper.columns["order_id"]
        assert col.unique is True

    def test_idempotency_key_unique(self) -> None:
        """idempotency_key should have unique constraint."""
        mapper = inspect(OrderModel)
        col = mapper.columns["idempotency_key"]
        assert col.unique is True


class TestFillModel:
    """Tests for FillModel."""

    def test_table_name(self) -> None:
        """Table name should be 'fills'."""
        assert FillModel.__tablename__ == "fills"

    def test_foreign_key_to_orders(self) -> None:
        """order_id should be FK to orders."""
        mapper = inspect(FillModel)
        col = mapper.columns["order_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 1
        assert fks[0].target_fullname == "orders.order_id"


class TestPositionModel:
    """Tests for PositionModel."""

    def test_table_name(self) -> None:
        """Table name should be 'positions'."""
        assert PositionModel.__tablename__ == "positions"

    def test_columns_exist(self) -> None:
        """Required columns should exist."""
        mapper = inspect(PositionModel)
        column_names = {c.key for c in mapper.columns}

        required = {
            "id",
            "position_id",
            "market_id",
            "quantity",
            "average_entry_price",
            "realized_pnl",
            "total_fees",
            "status",
            "opened_at",
            "closed_at",
        }
        assert required.issubset(column_names)


class TestAuditLogModel:
    """Tests for AuditLogModel."""

    def test_table_name(self) -> None:
        """Table name should be 'audit_logs'."""
        assert AuditLogModel.__tablename__ == "audit_logs"

    def test_columns_exist(self) -> None:
        """Required columns should exist."""
        mapper = inspect(AuditLogModel)
        column_names = {c.key for c in mapper.columns}

        required = {
            "id",
            "timestamp",
            "actor",
            "action",
            "resource_type",
            "resource_id",
            "details_json",
            "ip_address",
            "success",
        }
        assert required.issubset(column_names)

    def test_no_updated_at(self) -> None:
        """Audit log should NOT have updated_at (immutable)."""
        mapper = inspect(AuditLogModel)
        column_names = {c.key for c in mapper.columns}
        assert "updated_at" not in column_names


class TestMetadata:
    """Tests for Base metadata."""

    def test_all_tables_registered(self) -> None:
        """All models should be registered in metadata."""
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "blueprints",
            "sections",
            "orders",
            "fills",
            "positions",
            "audit_logs",
        }
        assert expected.issubset(table_names)

    def test_naming_convention(self) -> None:
        """Metadata should use naming convention."""
        assert Base.metadata.naming_convention is not None
        assert "pk" in Base.metadata.naming_convention
