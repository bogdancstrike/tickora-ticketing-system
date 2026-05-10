"""Lightweight Redis JSON cache helpers.

Used for short-TTL memoization of expensive read-only aggregate endpoints.
Failures (Redis down, serialization issues) silently fall back to a cache
miss so the API stays available.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Callable, Iterable

from src.core.redis_client import get_redis

_PREFIX = "tickora:cache:"


def _json_default(obj: Any):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Cannot serialize {type(obj).__name__}")


def make_key(namespace: str, parts: Iterable[Any]) -> str:
    """Stable, length-bounded cache key. Long components are hashed to keep
    keys under Redis's recommended 250-byte cap and to avoid leaking PII into
    key logs."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{_PREFIX}{namespace}:{digest}"


def get_json(key: str) -> Any | None:
    rds = get_redis()
    if not rds:
        return None
    try:
        raw = rds.get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def set_json(key: str, value: Any, *, ttl: int) -> None:
    rds = get_redis()
    if not rds:
        return
    try:
        rds.setex(key, ttl, json.dumps(value, default=_json_default))
    except Exception:
        pass


def cached_call(
    *,
    namespace: str,
    key_parts: Iterable[Any],
    ttl: int,
    producer: Callable[[], Any],
) -> Any:
    """Memoize `producer()` in Redis under `namespace:hash(key_parts)` for `ttl`
    seconds. On cache miss or failure, calls `producer` and stores the result.
    """
    key = make_key(namespace, key_parts)
    cached = get_json(key)
    if cached is not None:
        return cached
    fresh = producer()
    set_json(key, fresh, ttl=ttl)
    return fresh
