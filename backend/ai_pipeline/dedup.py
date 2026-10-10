"""
CitySync — Dedup + Cluster Engine
CRITICAL: Runs on raw GPS BEFORE DP noise is applied.
PostGIS ST_DWithin 50m radius + category match + 7-day window.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, update

from shared.config import settings
from shared.database import get_db
from shared.logging_config import get_logger
from shared.models import Ticket, TicketCluster
from shared.redis_client import publish_event, Streams
from shared.schemas import ClusterResult

log = get_logger("dedup")

CLUSTER_RADIUS_METERS = 50    # 50m dedup radius
CLUSTER_TIME_WINDOW_DAYS = 7  # 7-day sliding window


async def find_cluster(
    lat: float,
    lng: float,
    category: str,
    submitted_at: datetime,
) -> Optional[TicketCluster]:
    """
    Query ticket_clusters using:
    - PostGIS ST_DWithin(raw_gps, cluster_centroid, 50m)
    - category match
    - submitted_at within 7 days of cluster creation

    Returns the matching TicketCluster or None.
    """
    cutoff_date = submitted_at - timedelta(days=CLUSTER_TIME_WINDOW_DAYS)

    async with get_db() as session:
        result = await session.execute(
            text("""
                SELECT tc.id, tc.canonical_ticket_id, tc.member_count,
                    ST_Distance(
                        tc.cluster_centroid::geography,
                        ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                    ) AS dist_meters
                FROM ticket_clusters tc
                WHERE tc.category = :category
                  AND tc.created_at >= :cutoff
                  AND ST_DWithin(
                      tc.cluster_centroid::geography,
                      ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                      :radius
                  )
                ORDER BY dist_meters ASC
                LIMIT 1
            """),
            {
                "lat": lat,
                "lng": lng,
                "category": category,
                "cutoff": cutoff_date,
                "radius": CLUSTER_RADIUS_METERS,
            }
        )
        row = result.fetchone()
        if row:
            return {
                "cluster_id": str(row[0]),
                "canonical_ticket_id": row[1],
                "member_count": row[2],
                "distance_meters": round(row[3], 1),
            }
    return None


async def create_cluster(
    ticket_id: str,
    lat: float,
    lng: float,
    category: str,
) -> str:
    """Create a new cluster for a canonical ticket. Returns cluster_id."""
    cluster_id = str(uuid.uuid4())

    async with get_db() as session:
        # Create cluster record
        await session.execute(
            text("""
                INSERT INTO ticket_clusters (id, cluster_centroid, category, canonical_ticket_id, member_count, created_at, updated_at)
                VALUES (
                    :id,
                    ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                    :category,
                    :ticket_id,
                    1,
                    NOW(),
                    NOW()
                )
            """),
            {"id": cluster_id, "lat": lat, "lng": lng, "category": category, "ticket_id": ticket_id},
        )
        # Link ticket to cluster
        await session.execute(
            text("UPDATE tickets SET cluster_id = :cluster_id WHERE id = :ticket_id"),
            {"cluster_id": cluster_id, "ticket_id": ticket_id},
        )

    log.info("cluster_created", cluster_id=cluster_id, ticket_id=ticket_id, category=category)
    return cluster_id


async def add_to_cluster(
    cluster_id: str,
    canonical_ticket_id: str,
    new_ticket_id: str,
    new_member_count: int,
) -> int:
    """
    Add a new submission to an existing cluster.
    Increments member_count and fires priority.boost event.
    Returns the new member_count.
    """
    new_count = new_member_count + 1

    async with get_db() as session:
        # Increment cluster member count
        await session.execute(
            text("""
                UPDATE ticket_clusters
                SET member_count = :count, updated_at = NOW()
                WHERE id = :cluster_id
            """),
            {"count": new_count, "cluster_id": cluster_id},
        )
        # Link the new ticket to the cluster
        await session.execute(
            text("UPDATE tickets SET cluster_id = :cluster_id WHERE id = :ticket_id"),
            {"cluster_id": cluster_id, "ticket_id": new_ticket_id},
        )

    log.info(
        "cluster_member_added",
        cluster_id=cluster_id,
        canonical_ticket_id=canonical_ticket_id,
        new_ticket_id=new_ticket_id,
        member_count=new_count,
    )

    # Fire priority.boost event to recalculate score for canonical ticket
    await publish_event(Streams.PRIORITY_BOOST, {
        "ticket_id": canonical_ticket_id,
        "reason": "cluster_member_added",
        "cluster_id": cluster_id,
        "member_count": str(new_count),
    })

    return new_count


async def run_dedup(
    ticket_id: str,
    lat: Optional[float],
    lng: Optional[float],
    category: str,
    submitted_at: datetime,
) -> ClusterResult:
    """
    Main dedup entry point.
    - If no GPS: skip dedup (can't cluster without coordinates)
    - If cluster found: add to cluster, return is_duplicate=True
    - If no cluster: create new cluster, return is_duplicate=False
    """
    if not lat or not lng:
        log.info("dedup_skipped_no_gps", ticket_id=ticket_id)
        return ClusterResult(
            is_duplicate=False,
            cluster_id=None,
            canonical_ticket_id=None,
            member_count=1,
            distance_meters=None,
        )

    existing_cluster = await find_cluster(lat, lng, category, submitted_at)

    if existing_cluster:
        canonical_ticket_id = existing_cluster["canonical_ticket_id"]
        new_count = await add_to_cluster(
            cluster_id=existing_cluster["cluster_id"],
            canonical_ticket_id=canonical_ticket_id,
            new_ticket_id=ticket_id,
            new_member_count=existing_cluster["member_count"],
        )
        log.info(
            "dedup_match",
            ticket_id=ticket_id,
            canonical=canonical_ticket_id,
            distance_m=existing_cluster["distance_meters"],
        )
        return ClusterResult(
            is_duplicate=True,
            cluster_id=existing_cluster["cluster_id"],
            canonical_ticket_id=canonical_ticket_id,
            member_count=new_count,
            distance_meters=existing_cluster["distance_meters"],
        )
    else:
        # New canonical complaint — create a cluster for it
        cluster_id = await create_cluster(ticket_id, lat, lng, category)
        return ClusterResult(
            is_duplicate=False,
            cluster_id=cluster_id,
            canonical_ticket_id=ticket_id,
            member_count=1,
            distance_meters=None,
        )
