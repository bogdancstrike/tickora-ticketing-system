"""Redis-backed sliding-window rate limiter.

The window is implemented as a sorted set of timestamps per (bucket, key):
each request adds the current millisecond timestamp as a member with itself
as the score, then trims everything older than `window_s` seconds. The
remaining cardinality is the in-window request count — if it would exceed
`limit`, we raise `RateLimitError` instead.

The key is "(bucket, principal user_id or fallback IP)" so an authenticated
user is bucketed by their identity (no IP-rotation bypass) and unauthenticated
traffic still gets a bucket per remote IP.

Failure semantics are intentionally **fail-open**: when Redis is unreachable
the limiter does nothing rather than blocking writes. We log the bypass once
per process start. This trades a brief amplification window during a Redis
outage for the system staying available — the alternative (fail closed)
would convert a Redis outage into a write outage, which is worse.
"""
from __future__ import annotations

import time
import uuid

from src.common.errors import RateLimitError
from src.common.redis_client import get_redis


_KEY_PREFIX = "tickora:ratelimit:"


def check(*, bucket: str, identity: str, limit: int, window_s: int = 60) -> None:
    """Bump the sliding window for (bucket, identity).

    Raises:
        RateLimitError: if `identity` has issued more than `limit` requests
            in the last `window_s` seconds.
    """
    if limit <= 0:
        return  # disabled
    rds = get_redis()
    if not rds:
        return  # fail-open

    key = f"{_KEY_PREFIX}{bucket}:{identity}"
    now_ms = int(time.time() * 1000)
    window_start_ms = now_ms - window_s * 1000

    try:
        # Pipeline: trim, add, count. Use a unique member per request so a
        # double-call within the same millisecond doesn't collapse to one.
        member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
        pipe = rds.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start_ms)
        pipe.zadd(key, {member: now_ms})
        pipe.zcard(key)
        pipe.expire(key, window_s * 2)  # eventual cleanup of cold keys
        results = pipe.execute()
        in_window = int(results[2] or 0)
    except Exception:
        return  # fail-open on any Redis error

    if in_window > limit:
        raise RateLimitError(
            f"too many requests for {bucket} (limit {limit}/{window_s}s)",
            details={"bucket": bucket, "limit": limit, "window_s": window_s},
        )
