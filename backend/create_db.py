import asyncio
import asyncpg
from app.core.config import get_settings

settings = get_settings()

async def create_database():
    # Parse the DATABASE_URL to get credentials, but connect to 'postgres'
    # Assuming standard format: postgresql+asyncpg://user:pass@host:port/dbname
    # We want: postgresql://user:pass@host:port/postgres
    
    # Simple parsing logic for this specific default string
    # In production, use a library or better parsing.
    default_db_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql").replace("/printaria", "/postgres")
    
    print(f"Connecting to default DB to check 'printaria' database...")
    try:
        conn = await asyncpg.connect(default_db_url)
        
        # Check if db exists
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'printaria'")
        if not exists:
            print("Database 'printaria' not found. Creating...")
            await conn.execute('CREATE DATABASE printaria')
            print("Database 'printaria' created successfully.")
        else:
            print("Database 'printaria' already exists.")
            
        await conn.close()
    except Exception as e:
        print(f"Error creating database: {e}")
        print("Please ensure PostgreSQL is running and credentials are correct.")

if __name__ == "__main__":
    asyncio.run(create_database())
