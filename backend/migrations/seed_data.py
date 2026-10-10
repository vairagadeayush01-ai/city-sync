"""
CitySync — Seed data for wards, departments, routes, and severity overrides.
Uses realistic Mumbai ward boundaries and Indian municipal department structure.

Run: python backend/migrations/seed_data.py
"""
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from shared.config import settings
from shared.database import Base
import shared.models as m


# ── Mumbai Ward Boundaries (approximate, for demo) ────────────────────────────
# Using simplified polygon coordinates around Mumbai wards
WARDS = [
    {
        "id": "MUM-A",
        "name": "A Ward (Colaba & Fort)",
        "city": "Mumbai",
        "centroid": (72.8347, 18.9217),
        # Approximate bounding box polygon
        "boundary_wkt": "POLYGON((72.82 18.90, 72.85 18.90, 72.85 18.94, 72.82 18.94, 72.82 18.90))",
    },
    {
        "id": "MUM-D",
        "name": "D Ward (Malabar Hill)",
        "city": "Mumbai",
        "centroid": (72.7946, 18.9596),
        "boundary_wkt": "POLYGON((72.78 18.94, 72.81 18.94, 72.81 18.98, 72.78 18.98, 72.78 18.94))",
    },
    {
        "id": "MUM-K-E",
        "name": "K/E Ward (Andheri East)",
        "city": "Mumbai",
        "centroid": (72.8697, 19.1136),
        "boundary_wkt": "POLYGON((72.85 19.09, 72.89 19.09, 72.89 19.13, 72.85 19.13, 72.85 19.09))",
    },
    {
        "id": "MUM-K-W",
        "name": "K/W Ward (Andheri West)",
        "city": "Mumbai",
        "centroid": (72.8369, 19.1290),
        "boundary_wkt": "POLYGON((72.82 19.11, 72.85 19.11, 72.85 19.15, 72.82 19.15, 72.82 19.11))",
    },
    {
        "id": "MUM-H-E",
        "name": "H/E Ward (Santacruz East)",
        "city": "Mumbai",
        "centroid": (72.8447, 19.0770),
        "boundary_wkt": "POLYGON((72.83 19.06, 72.86 19.06, 72.86 19.10, 72.83 19.10, 72.83 19.06))",
    },
]

# ── Departments ────────────────────────────────────────────────────────────────
DEPARTMENTS = [
    {"id": str(uuid.uuid4()), "name": "Roads & Infrastructure", "code": "ROADS",
     "email": "roads@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/roads"},
    {"id": str(uuid.uuid4()), "name": "Storm Water Drains (SWD)", "code": "SWD",
     "email": "swd@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/swd"},
    {"id": str(uuid.uuid4()), "name": "Street Lighting", "code": "LIGHTS",
     "email": "lights@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/lights"},
    {"id": str(uuid.uuid4()), "name": "Solid Waste Management", "code": "SWM",
     "email": "swm@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/swm"},
    {"id": str(uuid.uuid4()), "name": "Hydraulic Engineering (Water Supply)", "code": "HYD",
     "email": "water@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/water"},
    {"id": str(uuid.uuid4()), "name": "Electricity Emergency Cell", "code": "ELEC_EMG",
     "email": "livewire@bestenergy.in", "webhook_url": "http://localhost:3000/webhook/emergency"},
    {"id": str(uuid.uuid4()), "name": "Fire Brigade & Rescue", "code": "FIRE",
     "email": "fire@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/fire"},
    {"id": str(uuid.uuid4()), "name": "Building & Factories", "code": "BLDG",
     "email": "buildings@bmc.gov.in", "webhook_url": "http://localhost:3000/webhook/buildings"},
]

# ── Category → Department mapping (category + NULL ward = default for all wards)
CATEGORY_DEPARTMENT_MAP = {
    "Pothole": "ROADS",
    "Flooding": "SWD",
    "Drainage": "SWD",
    "Street Light": "LIGHTS",
    "Garbage": "SWM",
    "Water Supply": "HYD",
    "Building Hazard": "BLDG",
    "Live Wire": "ELEC_EMG",
    "Noise": "ROADS",
    "Other": "ROADS",
}

# ── Severity overrides (emergency bypass) ─────────────────────────────────────
SEVERITY_OVERRIDES = [
    {
        "category": "Live Wire",
        "min_severity": 7,
        "department_code": "ELEC_EMG",
        "bypass_ward": True,
        "reason": "Live wire is public safety emergency — bypass ward routing",
    },
    {
        "category": "Building Hazard",
        "min_severity": 9,
        "department_code": "FIRE",
        "bypass_ward": True,
        "reason": "Building collapse imminent — Fire & Rescue takes priority",
    },
    {
        "category": "Flooding",
        "min_severity": 8,
        "department_code": "SWD",
        "bypass_ward": False,
        "reason": "Severe flooding — escalated priority",
    },
]


async def seed():
    print("🌱 CitySync — Seeding Data")

    engine = create_async_engine(settings.database_url, echo=False)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as session:
        # ── 1. Seed wards ──────────────────────────────────────────────────────
        print("🗺  Seeding wards...")
        for ward_data in WARDS:
            existing = await session.get(m.Ward, ward_data["id"])
            if not existing:
                ward = m.Ward(
                    id=ward_data["id"],
                    name=ward_data["name"],
                    city=ward_data["city"],
                )
                session.add(ward)
        await session.flush()

        # Set boundaries using raw SQL (GeoAlchemy2 WKT)
        for ward_data in WARDS:
            await session.execute(
                text("""
                    UPDATE wards
                    SET boundary = ST_GeogFromText(:wkt)
                    WHERE id = :id
                """),
                {"wkt": ward_data["boundary_wkt"], "id": ward_data["id"]},
            )
        print(f"   ✓ {len(WARDS)} wards seeded")

        # ── 2. Seed departments ────────────────────────────────────────────────
        print("🏢 Seeding departments...")
        dept_by_code = {}
        for dept_data in DEPARTMENTS:
            existing = await session.execute(
                text("SELECT id FROM departments WHERE code = :code"),
                {"code": dept_data["code"]},
            )
            row = existing.fetchone()
            if row:
                dept_by_code[dept_data["code"]] = str(row[0])
            else:
                dept = m.Department(
                    id=dept_data["id"],
                    name=dept_data["name"],
                    code=dept_data["code"],
                    email=dept_data.get("email"),
                    webhook_url=dept_data.get("webhook_url"),
                )
                session.add(dept)
                dept_by_code[dept_data["code"]] = dept_data["id"]
        await session.flush()
        print(f"   ✓ {len(DEPARTMENTS)} departments seeded")

        # ── 3. Seed department routes ──────────────────────────────────────────
        print("🔀 Seeding department routes...")
        route_count = 0
        for category, dept_code in CATEGORY_DEPARTMENT_MAP.items():
            dept_id = dept_by_code[dept_code]
            # Check if route already exists
            existing = await session.execute(
                text("""
                    SELECT id FROM department_routes
                    WHERE category = :cat AND ward_id IS NULL
                """),
                {"cat": category},
            )
            if not existing.fetchone():
                route = m.DepartmentRoute(
                    id=str(uuid.uuid4()),
                    category=category,
                    ward_id=None,  # NULL = applies to all wards
                    primary_department_id=dept_id,
                    webhook_url=None,  # use department webhook_url
                )
                session.add(route)
                route_count += 1
        await session.flush()
        print(f"   ✓ {route_count} routes seeded")

        # ── 4. Seed severity overrides ─────────────────────────────────────────
        print("⚠️  Seeding severity overrides...")
        override_count = 0
        for override_data in SEVERITY_OVERRIDES:
            dept_id = dept_by_code[override_data["department_code"]]
            existing = await session.execute(
                text("""
                    SELECT id FROM severity_overrides
                    WHERE category = :cat AND min_severity = :sev
                """),
                {"cat": override_data["category"], "sev": override_data["min_severity"]},
            )
            if not existing.fetchone():
                override = m.SeverityOverride(
                    id=str(uuid.uuid4()),
                    category=override_data["category"],
                    min_severity=override_data["min_severity"],
                    department_id=dept_id,
                    bypass_ward=override_data["bypass_ward"],
                    reason=override_data["reason"],
                )
                session.add(override)
                override_count += 1
        await session.flush()
        print(f"   ✓ {override_count} severity overrides seeded")

        await session.commit()

    print()
    print("✅ Seed data complete!")
    print()
    print("Departments seeded:")
    for d in DEPARTMENTS:
        print(f"  • {d['code']:12} → {d['name']}")
    print()
    print("Ward → webhook URL:")
    print("  All categories route to → http://localhost:3000/webhook/{dept_code}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
