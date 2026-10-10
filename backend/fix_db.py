import asyncio
from sqlalchemy import text
import sys
import os

# Add /app/backend to path to import shared
sys.path.append(os.path.join(os.getcwd(), "backend"))
from shared.database import engine

async def fix():
    try:
        async with engine.begin() as conn:
            print("Checking users table...")
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE"))
            await conn.execute(text("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL"))
        print("Database patched successfully.")
    except Exception as e:
        print(f"Error patching database: {e}")

if __name__ == "__main__":
    asyncio.run(fix())
