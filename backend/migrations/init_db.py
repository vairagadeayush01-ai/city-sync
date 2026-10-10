"""
CitySync — Database initialisation script.
Creates all tables, PostGIS extension, spatial indexes, and the
critical PG trigger that enforces two-step verification before Resolved.

Run: python backend/migrations/init_db.py
"""
import asyncio
import sys
import os

# Make shared/ importable from this script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from shared.config import settings
from shared.database import Base
import shared.models  # noqa — import all models so they register with Base


TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION enforce_resolution_log()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'Resolved' AND (OLD.status IS DISTINCT FROM 'Resolved') THEN
        IF NEW.resolution_log_id IS NULL THEN
            RAISE EXCEPTION 'Cannot set status=Resolved without a resolution_log_id. '
                'All resolutions must pass through the two-step Verification Engine.';
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM resolution_log WHERE id = NEW.resolution_log_id
        ) THEN
            RAISE EXCEPTION 'resolution_log_id % does not exist in resolution_log table. '
                'Create the resolution log record through the Verification Engine first.',
                NEW.resolution_log_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_DROP_SQL = """
DROP TRIGGER IF EXISTS trg_enforce_resolution ON tickets;
"""

TRIGGER_CREATE_SQL = """
CREATE TRIGGER trg_enforce_resolution
    BEFORE UPDATE ON tickets
    FOR EACH ROW
    EXECUTE FUNCTION enforce_resolution_log();
"""

SPATIAL_INDEXES_SQL = """
-- Spatial index on fuzzed_gps for officer map queries
CREATE INDEX IF NOT EXISTS idx_tickets_fuzzed_gps
    ON tickets USING GIST (fuzzed_gps);

-- Spatial index on cluster centroids for 50m dedup queries
CREATE INDEX IF NOT EXISTS idx_ticket_clusters_centroid
    ON ticket_clusters USING GIST (cluster_centroid);

-- Spatial index on ward boundaries for point-in-polygon queries
CREATE INDEX IF NOT EXISTS idx_wards_boundary
    ON wards USING GIST (boundary);

-- Covering index for dedup lookups: category + submitted_at
CREATE INDEX IF NOT EXISTS idx_tickets_category_submitted
    ON tickets (category, submitted_at);

-- Covering index for status + ward queries (officer dashboard)
CREATE INDEX IF NOT EXISTS idx_tickets_status_ward
    ON tickets (status, ward_id) INCLUDE (priority_score);
"""


async def init_database():
    print("CitySync - Database Initialisation")
    print(f"   Connecting to: {settings.database_url_sync.split('@')[1]}")

    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        # 1. Enable required Postgres extensions
        print("Enabling Postgres extensions...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis_topology;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        print("   Extensions enabled (postgis, postgis_topology, pg_trgm)")

        # 2. Create all ORM tables
        print("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        print("   All tables created")

        # 2.5 Add new columns if they are missing
        print("Running structural migrations (if any)...")
        try:
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(100);"))
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS officer_notes TEXT;"))
            await conn.execute(text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS status_history JSONB DEFAULT '[]'::jsonb;"))
            
            # Migration for 'Solved' status check constraint
            print("   Updating status check constraint...")
            await conn.execute(text("ALTER TABLE tickets DROP CONSTRAINT IF EXISTS ck_tickets_status;"))
            await conn.execute(text("""
                ALTER TABLE tickets ADD CONSTRAINT ck_tickets_status 
                CHECK (status IN ('Submitted','Pending','Processing','In Progress','Under Review','Solved','Work Complete','Resolved','Completed','Rejected','Human Review'));
            """))
            print("   Columns and constraints updated")
        except Exception as e:
            print(f"   Columns update error: {e}")

        # 3. Create spatial indexes
        print("Creating spatial indexes...")
        for stmt in SPATIAL_INDEXES_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await conn.execute(text(stmt + ";"))
        print("   Spatial indexes created")

        # 4. Install the resolution trigger
        print("Installing verification trigger...")
        await conn.execute(text(TRIGGER_FUNCTION_SQL))
        await conn.execute(text(TRIGGER_DROP_SQL))
        await conn.execute(text(TRIGGER_CREATE_SQL))
        print("   trg_enforce_resolution installed")
        print()
        print("Database initialisation complete!")
        print()
        print("Next step: python backend/migrations/seed_data.py")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_database())
