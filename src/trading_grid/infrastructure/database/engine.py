"""
SQLAlchemy async engine and session factory.

This module provides:
- create_engine(): Create async engine from settings
- get_session_factory(): Create async session factory
- get_session(): FastAPI dependency for database sessions

Usage:
    from trading_grid.infrastructure.database.engine import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Use session
        ...
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from trading_grid.config.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """
    Get cached async engine instance.

    Engine is created once and cached for performance.
    Uses DATABASE_URL from settings.

    Returns:
        AsyncEngine instance
    """
    settings = get_settings()
    database_url = settings.database.get_url()

    return create_async_engine(
        database_url,
        echo=settings.database.echo,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        pool_timeout=settings.database.pool_timeout,
        pool_pre_ping=True,  # Verify connections before use
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get cached async session factory.

    Returns:
        async_sessionmaker instance
    """
    engine = get_engine()

    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Prevent lazy load issues after commit
        autoflush=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.

    Yields a session and ensures it's closed after use.

    Usage in FastAPI:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...

    Yields:
        AsyncSession instance
    """
    session_factory = get_session_factory()

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    """
    Dispose the engine and close all connections.

    Call this on application shutdown.
    """
    try:
        engine = get_engine()
        await engine.dispose()
    except Exception:
        pass
    finally:
        get_engine.cache_clear()
        get_session_factory.cache_clear()


async def check_connection() -> bool:
    """
    Check if database connection is working.

    Returns:
        True if connection successful, False otherwise
    """
    from sqlalchemy import text

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
