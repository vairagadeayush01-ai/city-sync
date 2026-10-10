"""
CitySync — AI Pipeline Consumer (Layer 3)
Redis Stream consumer: reads raw.submissions → runs full AI pipeline →
writes classified ticket to DB → fires classified.complaints event.

Run: python -m ai_pipeline.main  (from backend/ directory)
"""
import asyncio
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.config import settings
from shared.logging_config import configure_logging, get_logger, set_trace_id, set_ticket_id
from shared.redis_client import (
    read_events, ack_event, create_consumer_group,
    publish_event, Streams, get_redis,
)
from shared.database import get_db
from shared.models import Ticket
from shared.privacy import apply_dp_noise, EPSILON_OFFICER
from sqlalchemy import text

from ai_pipeline.classifier import classify_complaint
from ai_pipeline.spatial import resolve_coordinates, get_ward_for_point
from ai_pipeline.dedup import run_dedup
from ai_pipeline.priority import calculate_priority
from ai_pipeline.frequency import track_complaint

configure_logging(settings.log_level)
log = get_logger("ai_pipeline")

CONSUMER_GROUP = "ai_pipeline"
CONSUMER_NAME = "worker-1"


async def process_submission(msg_id: str, data: dict):
    """
    Process a single raw submission event through the full AI pipeline:
    classify → spatial → dedup → priority → privacy → write DB → notify
    """
    ticket_id = data.get("ticket_id", "UNKNOWN")
    trace_id = data.get("trace_id", "")

    set_trace_id(trace_id)
    set_ticket_id(ticket_id)

    log.info("pipeline_start", ticket_id=ticket_id, trace_id=trace_id)

    try:
        description = data.get("description", "")
        language = data.get("language", "en")
        citizen_token = data.get("citizen_token", "")
        image_key = data.get("image_key") or None

        raw_lat_str = data.get("raw_lat", "")
        raw_lng_str = data.get("raw_lng", "")
        raw_lat = float(raw_lat_str) if raw_lat_str else None
        raw_lng = float(raw_lng_str) if raw_lng_str else None

        # ── Step 3: AI Classification ─────────────────────────────────────────
        log.info("step3_classify", ticket_id=ticket_id)
        classification = await classify_complaint(ticket_id, description, language)

        # Route non-complaints to human review / auto-reply
        if classification.intent in ("spam", "abuse"):
            log.info("complaint_rejected", ticket_id=ticket_id, intent=classification.intent)
            await _write_ticket_rejected(ticket_id, citizen_token, classification, data)
            return

        if classification.confidence < 0.70:
            log.info("low_confidence_human_review", ticket_id=ticket_id, confidence=classification.confidence)
            await _write_ticket_human_review(ticket_id, citizen_token, classification, data)
            return

        # ── Step 4: Spatial Validation ────────────────────────────────────────
        log.info("step4_spatial", ticket_id=ticket_id)
        lat, lng, gps_source = await resolve_coordinates(
            raw_lat, raw_lng, classification.location_mention
        )
        ward_id = None
        if lat and lng:
            ward_id = await get_ward_for_point(lat, lng)

        # ── Step 4.5: Write placeholder ticket to satisfy Foreign Key ─────────
        async with get_db() as session:
            existing = await session.get(Ticket, ticket_id)
            if not existing:
                placeholder = Ticket(
                    id=ticket_id,
                    category=classification.category,
                    severity=classification.severity,
                    severity_tier="Medium", # placeholder
                    priority_score=0.0,
                    status="Processing",
                    intent=classification.intent,
                    confidence=classification.confidence,
                    citizen_token=citizen_token,
                    description=description,
                )
                session.add(placeholder)
                await session.commit()

        # ── Step 5: Dedup + Cluster (on raw GPS — before DP noise) ────────────
        log.info("step5_dedup", ticket_id=ticket_id, lat=lat, lng=lng)
        submitted_at = datetime.now(timezone.utc)
        cluster_result = await run_dedup(ticket_id, lat, lng, classification.category, submitted_at)

        # ── Apply DP noise to GPS (AFTER dedup) ───────────────────────────────
        fuzzed_lat, fuzzed_lng = None, None
        if lat and lng:
            fuzzed_lat, fuzzed_lng = apply_dp_noise(lat, lng, EPSILON_OFFICER)

        # ── Step 6: Priority Scoring ──────────────────────────────────────────
        log.info("step6_priority", ticket_id=ticket_id)
        priority = await calculate_priority(
            ticket_id=ticket_id,
            severity=classification.severity,
            cluster_size=cluster_result.member_count,
            upvote_count=0,
            submitted_at=submitted_at,
            category=classification.category,
            citizen_token=citizen_token,
            lat=lat,
            lng=lng,
            description=description,
        )

        # ── Step 7: Frequency Monitor ─────────────────────────────────────────
        await track_complaint(classification.category, ward_id or "unknown")

        # ── Write ticket to PostgreSQL ─────────────────────────────────────────
        log.info("writing_ticket", ticket_id=ticket_id)
        await _write_ticket(
            ticket_id=ticket_id,
            citizen_token=citizen_token,
            classification=classification,
            ward_id=ward_id,
            cluster_result=cluster_result,
            priority=priority,
            image_key=image_key,
            fuzzed_lat=fuzzed_lat,
            fuzzed_lng=fuzzed_lng,
            submitted_at=submitted_at,
        )

        # ── Publish classified event for Routing service ──────────────────────
        await publish_event(Streams.CLASSIFIED_COMPLAINTS, {
            "ticket_id": ticket_id,
            "trace_id": trace_id,
            "citizen_token": citizen_token,
            "category": classification.category,
            "severity": str(classification.severity),
            "severity_tier": priority.tier,
            "priority_score": str(priority.score),
            "ward_id": ward_id or "",
            "is_duplicate": str(cluster_result.is_duplicate),
            "canonical_ticket_id": cluster_result.canonical_ticket_id or ticket_id,
            "cluster_id": cluster_result.cluster_id or "",
            "description": description,
        })

        # ── Publish status update for citizen dashboard ────────────────────────
        await publish_event(Streams.STATUS_UPDATES, {
            "ticket_id": ticket_id,
            "citizen_token": citizen_token,
            "status": "Pending",
            "category": classification.category,
            "severity_tier": priority.tier,
            "priority_score": str(priority.score),
            "ward_id": ward_id or "",
            "updated_by": "CitySync AI",
            "note": f"Complaint classified as {classification.category} with {priority.tier} priority.",
            "message": f"Your {classification.category} complaint has been classified (Priority: {priority.tier})",
        })

        log.info(
            "pipeline_complete",
            ticket_id=ticket_id,
            category=classification.category,
            severity=classification.severity,
            tier=priority.tier,
            score=priority.score,
            is_duplicate=cluster_result.is_duplicate,
            ward_id=ward_id,
        )

    except Exception as e:
        log.exception("pipeline_error", ticket_id=ticket_id, error=str(e))


async def _write_ticket(
    ticket_id, citizen_token, classification, ward_id,
    cluster_result, priority, image_key, fuzzed_lat, fuzzed_lng, submitted_at,
):
    """Write a classified ticket to PostgreSQL."""
    async with get_db() as session:
        # Check if ticket row already exists (created by gateway)
        existing = await session.get(Ticket, ticket_id)
        if existing:
            # Update existing placeholder row
            await session.execute(
                text("""
                    UPDATE tickets SET
                        category = :category,
                        severity = :severity,
                        severity_tier = :tier,
                        priority_score = :score,
                        status = 'Pending',
                        intent = :intent,
                        confidence = :confidence,
                        ward_id = :ward_id,
                        cluster_id = :cluster_id,
                        citizen_token = :citizen_token,
                        image_key = :image_key,
                        fuzzed_gps = CASE WHEN :has_gps THEN ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography ELSE NULL END,
                        updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {
                    "ticket_id": ticket_id,
                    "category": classification.category,
                    "severity": classification.severity,
                    "tier": priority.tier,
                    "score": priority.score,
                    "intent": classification.intent,
                    "confidence": classification.confidence,
                    "ward_id": ward_id,
                    "cluster_id": cluster_result.cluster_id,
                    "citizen_token": citizen_token,
                    "image_key": image_key,
                    "has_gps": fuzzed_lat is not None and fuzzed_lng is not None,
                    "lat": fuzzed_lat or 0.0,
                    "lng": fuzzed_lng or 0.0,
                },
            )
        else:
            # Create new ticket row
            ticket = Ticket(
                id=ticket_id,
                category=classification.category,
                severity=classification.severity,
                severity_tier=priority.tier,
                priority_score=priority.score,
                status="Pending",
                intent=classification.intent,
                confidence=classification.confidence,
                ward_id=ward_id,
                cluster_id=cluster_result.cluster_id,
                citizen_token=citizen_token,
                image_key=image_key,
                submitted_at=submitted_at,
            )
            session.add(ticket)
            await session.flush()

            if fuzzed_lat and fuzzed_lng:
                await session.execute(
                    text("""
                        UPDATE tickets SET
                        fuzzed_gps = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
                        WHERE id = :ticket_id
                    """),
                    {"lat": fuzzed_lat, "lng": fuzzed_lng, "ticket_id": ticket_id},
                )


async def _write_ticket_rejected(ticket_id, citizen_token, classification, data):
    """Update an existing placeholder ticket to Rejected status."""
    async with get_db() as session:
        existing = await session.get(Ticket, ticket_id)
        if existing:
            await session.execute(
                text("""
                    UPDATE tickets SET
                        category = 'Other',
                        severity = 1,
                        severity_tier = 'Low',
                        priority_score = 0.0,
                        status = 'Rejected',
                        intent = :intent,
                        confidence = :confidence,
                        updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {"intent": classification.intent, "confidence": classification.confidence, "ticket_id": ticket_id},
            )
        else:
            session.add(Ticket(
                id=ticket_id,
                category="Other",
                severity=1,
                severity_tier="Low",
                priority_score=0.0,
                status="Rejected",
                intent=classification.intent,
                confidence=classification.confidence,
                citizen_token=citizen_token,
                description=data.get("description", ""),
            ))


async def _write_ticket_human_review(ticket_id, citizen_token, classification, data):
    """Update an existing placeholder ticket to Human Review status."""
    async with get_db() as session:
        existing = await session.get(Ticket, ticket_id)
        if existing:
            await session.execute(
                text("""
                    UPDATE tickets SET
                        category = :category,
                        severity = :severity,
                        severity_tier = 'Low',
                        priority_score = :score,
                        status = 'Human Review',
                        intent = :intent,
                        confidence = :confidence,
                        updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {
                    "category": classification.category,
                    "severity": classification.severity,
                    "score": classification.severity * 2.5,
                    "intent": classification.intent,
                    "confidence": classification.confidence,
                    "ticket_id": ticket_id,
                },
            )
        else:
            session.add(Ticket(
                id=ticket_id,
                category=classification.category,
                severity=classification.severity,
                severity_tier="Low",
                priority_score=classification.severity * 2.5,
                status="Human Review",
                intent=classification.intent,
                confidence=classification.confidence,
                citizen_token=citizen_token,
                description=data.get("description", ""),
            ))


async def priority_boost_consumer():
    """Consume priority.boost events and recalculate scores."""
    await create_consumer_group(Streams.PRIORITY_BOOST, "priority_boost", start_id="$")
    while True:
        events = await read_events(Streams.PRIORITY_BOOST, "priority_boost", "worker-1")
        for msg_id, data in events:
            ticket_id = data.get("ticket_id")
            if ticket_id:
                from ai_pipeline.priority import recalculate_on_boost
                await recalculate_on_boost(ticket_id, data.get("reason", "boost"))
            await ack_event(Streams.PRIORITY_BOOST, "priority_boost", msg_id)


async def main():
    """Main consumer loop."""
    log.info("ai_pipeline_starting")
    await create_consumer_group(Streams.RAW_SUBMISSIONS, CONSUMER_GROUP, start_id="0")

    # Run both consumers concurrently
    await asyncio.gather(
        _consume_submissions(),
        priority_boost_consumer(),
    )


async def _consume_submissions():
    log.info("submission_consumer_ready", stream=Streams.RAW_SUBMISSIONS)
    while True:
        try:
            events = await read_events(Streams.RAW_SUBMISSIONS, CONSUMER_GROUP, CONSUMER_NAME)
            for msg_id, data in events:
                await process_submission(msg_id, data)
                await ack_event(Streams.RAW_SUBMISSIONS, CONSUMER_GROUP, msg_id)
        except Exception as e:
            log.exception("consumer_loop_error", error=str(e))
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
