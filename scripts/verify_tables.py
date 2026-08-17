"""Verify database tables were created in Supabase."""

import asyncio

from sqlalchemy import text

from trading_grid.infrastructure.database.engine import get_engine

EXPECTED_TABLES = [
    "blueprints",
    "sections",
    "orders",
    "fills",
    "positions",
    "audit_logs",
    "alembic_version",
]


async def main() -> None:
    """Verify tables exist."""
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' ORDER BY table_name"
                )
            )
            tables = [row[0] for row in result.fetchall()]

            print(f"Tables in Supabase ({len(tables)}):")
            for t in tables:
                status = "[OK]" if t in EXPECTED_TABLES else "    "
                print(f"  {status} {t}")

            missing = set(EXPECTED_TABLES) - set(tables)
            if missing:
                print(f"\n[FAIL] Missing tables: {missing}")
            else:
                print("\n[OK] All expected tables exist!")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
