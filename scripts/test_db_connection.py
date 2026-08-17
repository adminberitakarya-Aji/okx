"""Test database connection to Supabase."""

import asyncio

from sqlalchemy import text

from okx_trading.infrastructure.database.engine import get_engine


async def main() -> None:
    """Test database connection."""
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(f"Connection OK: {result.scalar()}")
    except Exception as e:
        print(f"Connection FAILED: {type(e).__name__}: {e}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
