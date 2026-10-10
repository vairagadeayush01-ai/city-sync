"""
CitySync — Priority Scorer
Explicit formula from the architecture doc:
score = (severity × 2.5) + (cluster_size × 4) + (upvote_count × 2)
      + time_age_boost + weather_boost + trust_modifier + keyword_urgency_boost

Tiers: Critical ≥85, High 60-84, Medium 35-59, Low <35
"""
import re
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from shared.config import settings
from shared.database import get_db
from shared.logging_config import get_logger
from shared.schemas import PriorityResult

log = get_logger("priority")

# ── Tier thresholds ────────────────────────────────────────────────────────────
TIERS = [
    (85.0, "Critical"),
    (60.0, "High"),
    (35.0, "Medium"),
    (0.0, "Low"),
]


def get_tier(score: float) -> str:
    for threshold, tier in TIERS:
        if score >= threshold:
            return tier
    return "Low"


# ── Keyword Urgency Scoring ────────────────────────────────────────────────────────
URGENCY_KEYWORDS = {
    # Tier 1 - Life threatening: adds 35 points if any matched
    "critical": [
        "death", "dead", "died", "dying", "kill", "killed", "murder",
        "collapse", "collapsed", "explosion", "exploded", "electrocution",
        "electrocuted", "drowning", "drowned", "trapped", "unconscious",
        "fatality", "fatal",
    ],
    # Tier 2 - High urgency: adds 20 points if any matched
    "high": [
        "accident", "accidental", "injured", "injury", "injuries", "bleeding",
        "fire", "burning", "burnt", "flood", "flooded", "flooding",
        "gas leak", "sewage overflow", "electric shock", "fallen tree",
        "sinkhole", "ambulance", "hospital", "urgent", "emergency", "immediate",
    ],
    # Tier 3 - Moderately severe: adds 10 points if any matched
    "medium": [
        "dangerous", "danger", "hazard", "hazardous", "severe", "severely",
        "major", "serious", "broken pipe", "no water", "no electricity",
        "power cut", "power outage", "overflow", "blocked drain",
    ],
}


def get_keyword_urgency_boost(description: Optional[str]) -> tuple[float, list]:
    """Scan description for urgency keywords. Returns (boost_points, matched_keywords)."""
    if not description:
        return 0.0, []

    text_lower = description.lower()
    matched = []
    boost = 0.0
    tier_points = {"critical": 35.0, "high": 20.0, "medium": 10.0}

    for tier, keywords in URGENCY_KEYWORDS.items():
        tier_matched = False
        for kw in keywords:
            if ' ' in kw:
                found = kw in text_lower
            else:
                found = bool(re.search(r'\b' + re.escape(kw) + r'\b', text_lower))
            if found:
                matched.append(kw)
                if not tier_matched:
                    boost += tier_points[tier]  # Add tier points only once per tier
                    tier_matched = True

    return min(boost, 65.0), matched  # Hard cap at 65


# ── Weather boost (mock — real integration would call Open-Meteo) ─────────────
async def get_weather_boost(lat: Optional[float], lng: Optional[float], category: str) -> float:
    """
    +10 if current weather is rain AND category is Flooding or Drainage.
    Uses Open-Meteo free API in production. Mock always returns 0 for hackathon.
    """
    if settings.mock_ai:
        # Mock: simulate rain weather for flooding categories occasionally
        import random
        if category in ("Flooding", "Drainage") and random.random() < 0.3:
            return 10.0
        return 0.0

    if not lat or not lng:
        return 0.0

    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lng,
                    "current": "weather_code",
                    "forecast_days": 1,
                },
            )
            data = resp.json()
            weather_code = data["current"]["weather_code"]
            # WMO codes 51-67, 71-77, 80-99 = precipitation
            is_raining = weather_code in range(51, 100)
            if is_raining and category in ("Flooding", "Drainage"):
                return 10.0
    except Exception as e:
        log.warning("weather_api_failed", error=str(e))

    return 0.0


# ── Citizen trust modifier ─────────────────────────────────────────────────────
async def get_trust_modifier(citizen_token: str) -> float:
    """
    Fetch citizen trust score (0.0–1.0) from DB.
    Contributes ±5 points: (trust_score - 0.5) × 10 → range -5 to +5.
    New citizens start at 0.5 (neutral).
    """
    # Trust score storage is a future feature — default 0.5 (neutral) for hackathon
    trust_score = 0.5
    modifier = (trust_score - 0.5) * 10.0  # -5 to +5
    return modifier


# ── Time age boost ─────────────────────────────────────────────────────────────
def get_time_age_boost(submitted_at: datetime) -> float:
    """
    +0.5 per hour the ticket has been unactioned.
    Prevents stale tickets from being buried.
    """
    now = datetime.now(timezone.utc)
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    hours_old = (now - submitted_at).total_seconds() / 3600.0
    return min(hours_old * 0.5, 20.0)  # cap at 20 points (40 hours)


# ── Main priority scorer ───────────────────────────────────────────────────────
async def calculate_priority(
    ticket_id: str,
    severity: int,
    cluster_size: int,
    upvote_count: int,
    submitted_at: datetime,
    category: str,
    citizen_token: str,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    description: Optional[str] = None,
) -> PriorityResult:
    """
    Compute priority score using the explicit CitySync formula.
    """
    # ── Formula components ────────────────────────────────────────────────────
    severity_pts = severity * 2.5
    cluster_pts = cluster_size * 4.0
    upvote_pts = upvote_count * 2.0
    age_boost = get_time_age_boost(submitted_at)
    weather_boost = await get_weather_boost(lat, lng, category)
    trust_modifier = await get_trust_modifier(citizen_token)
    keyword_boost, matched_keywords = get_keyword_urgency_boost(description)

    total = severity_pts + cluster_pts + upvote_pts + age_boost + weather_boost + trust_modifier + keyword_boost
    total = max(0.0, total)
    tier = get_tier(total)

    breakdown = {
        "severity": round(severity_pts, 1),
        "cluster_size": round(cluster_pts, 1),
        "upvotes": round(upvote_pts, 1),
        "age_boost": round(age_boost, 1),
        "weather_boost": round(weather_boost, 1),
        "trust_modifier": round(trust_modifier, 1),
        "keyword_boost": round(keyword_boost, 1),
        "keywords_matched": matched_keywords,
        "total": round(total, 1),
    }

    log.info("priority_scored", ticket_id=ticket_id, score=round(total, 1), tier=tier,
             keyword_boost=round(keyword_boost, 1), keywords=matched_keywords)

    # ── Write to DB ───────────────────────────────────────────────────────────
    try:
        async with get_db() as session:
            await session.execute(
                text("""
                    UPDATE tickets
                    SET priority_score = :score, severity_tier = :tier, updated_at = NOW()
                    WHERE id = :ticket_id
                """),
                {"score": round(total, 2), "tier": tier, "ticket_id": ticket_id},
            )
    except Exception as e:
        log.error("priority_db_write_failed", error=str(e), ticket_id=ticket_id)

    # ── Update Redis sorted set ───────────────────────────────────────────────
    try:
        from shared.redis_client import get_redis
        r = await get_redis()
        ward_key = f"citysync:priority:ward:all"
        await r.zadd(ward_key, {ticket_id: round(total, 2)})
    except Exception as e:
        log.warning("redis_zadd_failed", error=str(e))

    return PriorityResult(score=round(total, 2), tier=tier, breakdown=breakdown)


async def recalculate_on_boost(ticket_id: str, reason: str):
    """Re-run priority calculation for a ticket after a boost event."""
    from shared.models import Ticket
    from sqlalchemy import select

    async with get_db() as session:
        ticket = await session.get(Ticket, ticket_id)
        if not ticket:
            log.warning("priority_boost_ticket_not_found", ticket_id=ticket_id)
            return

        # Get cluster size
        cluster_size = 1
        if ticket.cluster_id:
            result = await session.execute(
                text("SELECT member_count FROM ticket_clusters WHERE id = :id"),
                {"id": ticket.cluster_id},
            )
            row = result.fetchone()
            if row:
                cluster_size = row[0]

        return await calculate_priority(
            ticket_id=ticket_id,
            severity=ticket.severity or 5,
            cluster_size=cluster_size,
            upvote_count=ticket.upvote_count or 0,
            submitted_at=ticket.submitted_at,
            category=ticket.category or "Other",
            citizen_token=ticket.citizen_token,
        )
