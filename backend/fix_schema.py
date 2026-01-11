import asyncio
import sys
import os

# Add the current directory to sys.path to allow imports
sys.path.append(os.getcwd())

from app.core.database import engine, Base
from app.models import Shop, Order, Payment, PrintJob

async def reset_db():
    print("Resetting database schema to enforce UUIDs...")
    try:
        async with engine.begin() as conn:
            # Drop all tables to remove incompatible VARCHAR columns
            print("Dropping existing tables...")
            await conn.run_sync(Base.metadata.drop_all)
            
            # Recreate tables with correct UUID definitions
            print("Creating new tables...")
            await conn.run_sync(Base.metadata.create_all)
            
        print("Database schema reset successfully. All IDs are now UUIDs.")
    except Exception as e:
        print(f"Error resetting database: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(reset_db())
