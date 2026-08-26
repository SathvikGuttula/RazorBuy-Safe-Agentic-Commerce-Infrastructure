"""Reset the database to a clean, freshly-seeded factory state."""
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.database.connection import engine, Base
import seed_db


async def reset():
    print("Dropping all tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("Re-seeding fresh data...")
    await seed_db.seed()
    print("✅ Database reset to clean factory state.")


if __name__ == "__main__":
    asyncio.run(reset())