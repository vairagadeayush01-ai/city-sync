"""
CitySync — Redis token-bucket rate limiter.
10 requests per minute per citizen bearer token.
"""
import time
from fastapi import HTTPException, Request, status
from shared.redis_client import get_redis

RATE_LIMIT_MAX = 10          # max requests
RATE_LIMIT_WINDOW_SEC = 60   # per minute


async def check_rate_limit(token: str) -> dict:
    """
    Check rate limit for a citizen token.
    Uses Redis INCR + EXPIRE (atomic sliding window).

    Returns: {"allowed": bool, "count": int, "limit": int, "reset_in": int}
    Raises: HTTPException 429 if limit exceeded.
    """
    r = await get_redis()
    key = f"citysync:ratelimit:{token}"

    pipe = r.pipeline(transaction=True)
    pipe.incr(key)
    pipe.ttl(key)
    count, ttl = await pipe.execute()

    # Set TTL on first request
    if count == 1:
        await r.expire(key, RATE_LIMIT_WINDOW_SEC)
        ttl = RATE_LIMIT_WINDOW_SEC

    reset_in = max(ttl, 0)

    if count > RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "limit": RATE_LIMIT_MAX,
                "window_seconds": RATE_LIMIT_WINDOW_SEC,
                "retry_after_seconds": reset_in,
            },
            headers={"Retry-After": str(reset_in)},
        )

    return {
        "allowed": True,
        "count": count,
        "limit": RATE_LIMIT_MAX,
        "reset_in": reset_in,
    }


async def record_rate_limit_hit(r, token: str):
    """Increment rate limit hit counter for metrics."""
    await r.incr("citysync:metrics:rate_limit_hits")
