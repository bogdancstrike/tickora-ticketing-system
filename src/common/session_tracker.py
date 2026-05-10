"""Active-session tracker.

Each authenticated request bumps a Redis key with a short TTL so we can
estimate "users with an active session" without having to query Keycloak's
/sessions endpoint (which doesn't scale and requires admin token).

The active-user count is the cardinality of the keyspace
`tickora:session:active:<user_id>` whose entries haven't expired yet.

Default presence window: 5 minutes. Tune via `Config.SESSION_PRESENCE_TTL`
if needed.
"""
from __future__ import annotations

from typing import Iterable

from src.common.redis_client import get_redis

_KEY_PREFIX = "tickora:session:active:"
_DEFAULT_TTL_SECONDS = 5 * 60  # 5 minutes


def mark_active(user_id: str | None, *, ttl: int = _DEFAULT_TTL_SECONDS) -> None:
    """Refresh the user's presence key. Cheap (`SETEX`) and idempotent."""
    if not user_id:
        return
    rds = get_redis()
    if not rds:
        return
    try:
        rds.setex(f"{_KEY_PREFIX}{user_id}", ttl, "1")
    except Exception:
        # Presence is non-critical — never let a Redis blip break a request.
        pass


def active_user_ids() -> set[str]:
    """Return the user IDs currently considered active.

    Uses `SCAN` to avoid blocking Redis on large keyspaces; a few hundred
    concurrent users is well within budget.
    """
    rds = get_redis()
    if not rds:
        return set()
    try:
        return {
            key[len(_KEY_PREFIX):]
            for key in _scan_keys(rds, f"{_KEY_PREFIX}*")
        }
    except Exception:
        return set()


def active_user_count() -> int:
    """Cheap count of active users (cardinality of the presence keyspace)."""
    return len(active_user_ids())


def _scan_keys(rds, pattern: str) -> Iterable[str]:
    cursor = 0
    while True:
        cursor, keys = rds.scan(cursor=cursor, match=pattern, count=500)
        for k in keys:
            yield k
        if cursor == 0:
            return
