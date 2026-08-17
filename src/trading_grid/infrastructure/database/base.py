"""
SQLAlchemy declarative base for ORM models.

All database models inherit from Base.
"""

from datetime import UTC, datetime
from typing import ClassVar

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Naming convention for constraints (important for Alembic migrations)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models.

    Uses naming convention for consistent constraint names.
    """

    metadata = MetaData(naming_convention=convention)
    type_annotation_map: ClassVar[dict[type, object]] = {
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at columns.

    All tables should include these for audit purposes.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
