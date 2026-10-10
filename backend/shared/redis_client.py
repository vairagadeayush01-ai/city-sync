"""
CitySync — Redis client and Stream helpers.
Single connection pool shared across all services.
"""
import json
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from shared.config import settings

# ── Global Redis pool ─────────────────────────────────────────────────────────
_redis_pool: Redis | None = None


async def get_redis() -> Redis:
    """Get (or create) the global Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


async def close_redis():
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None


# ── Stream helpers ────────────────────────────────────────────────────────────
async def publish_event(stream: str, data: dict[str, Any]) -> str:
    """
    Publish an event to a Redis Stream.
    Returns the message ID assigned by Redis.
    """
    r = await get_redis()
    # Redis streams require string values — serialize nested dicts to JSON
    flat = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
    msg_id = await r.xadd(stream, flat)
    return msg_id


async def create_consumer_group(stream: str, group: str, start_id: str = "0"):
    """Create a consumer group if it doesn't already exist."""
    r = await get_redis()
    try:
        await r.xgroup_create(stream, group, id=start_id, mkstream=True)
    except Exception as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists — normal on restart
        else:
            raise


async def read_events(stream: str, group: str, consumer: str, count: int = 10):
    """
    Read new messages from a consumer group.
    Returns list of (msg_id, data_dict) tuples.
    """
    r = await get_redis()
    messages = await r.xreadgroup(
        groupname=group,
        consumername=consumer,
        streams={stream: ">"},
        count=count,
        block=5000,  # Block up to 5 seconds waiting for messages
    )
    if not messages:
        return []
    results = []
    for _stream, msgs in messages:
        for msg_id, fields in msgs:
            # Deserialize JSON fields back to Python objects
            parsed = {}
            for k, v in fields.items():
                try:
                    parsed[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed[k] = v
            results.append((msg_id, parsed))
    return results


async def ack_event(stream: str, group: str, msg_id: str):
    """Acknowledge a processed message."""
    r = await get_redis()
    await r.xack(stream, group, msg_id)


# ── Stream names (single source of truth) ────────────────────────────────────
class Streams:
    RAW_SUBMISSIONS = "citysync:raw.submissions"
    CLASSIFIED_COMPLAINTS = "citysync:classified.complaints"
    PRIORITY_BOOST = "citysync:priority.boost"
    VERIFICATION_EVENTS = "citysync:verification.events"
    RESOLUTION_CONFIRMED = "citysync:resolution.confirmed"
    STATUS_UPDATES = "citysync:status.updates"
    AUDIT_EVENTS = "citysync:audit.events"
    WEBHOOK_DISPATCH = "citysync:webhook.dispatch"


# ── Sorted set / frequency helpers ───────────────────────────────────────────
FREQ_KEY = "citysync:freq:category:ward"


async def increment_category_freq(category: str, ward_id: str) -> float:
    """ZINCRBY — increment frequency counter for category+ward combination."""
    r = await get_redis()
    member = f"{category.lower()}:{ward_id}"
    new_score = await r.zincrby(FREQ_KEY, 1, member)
    return new_score


async def get_top_categories(n: int = 10) -> list[tuple[str, float]]:
    """ZREVRANGE — get top N category+ward complaints by frequency."""
    r = await get_redis()
    results = await r.zrevrange(FREQ_KEY, 0, n - 1, withscores=True)
    return [(member, score) for member, score in results]
