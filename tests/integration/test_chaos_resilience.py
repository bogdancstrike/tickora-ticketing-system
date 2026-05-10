"""Chaos / resilience tests.

Verifies that the system degrades gracefully when soft dependencies
disappear:
  * Redis blackout → presence widgets, monitor cache, rate limiter all
    fail open. The API stays available; data goes stale, never wrong.
  * Keycloak unreachable → cached principals keep working until JWT TTL.
  * Postgres restart simulation → the next request reconnects (handled by
    SQLAlchemy `pool_pre_ping=True` already enabled in `core.db.get_engine`).

These tests don't restart real infrastructure — they patch the boundaries
to simulate the failure modes. Real chaos drills run in staging.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Redis blackout ──────────────────────────────────────────────────────────

class TestRedisBlackout:
    """When `get_redis()` returns None, every Redis-aware module must
    silently degrade. None of these calls should raise."""

    def test_session_tracker_fails_open(self, monkeypatch):
        from src.common import session_tracker
        monkeypatch.setattr(session_tracker, "get_redis", lambda: None)
        session_tracker.mark_active("u-1")
        assert session_tracker.active_user_count() == 0
        assert session_tracker.active_user_ids() == set()

    def test_rate_limiter_fails_open(self, monkeypatch):
        from src.common import rate_limiter
        monkeypatch.setattr(rate_limiter, "get_redis", lambda: None)
        # Even past the nominal limit, the call must succeed.
        for _ in range(100):
            rate_limiter.check(bucket="x", identity="u", limit=5, window_s=60)

    def test_cache_falls_through_to_producer(self, monkeypatch):
        from src.common import cache
        monkeypatch.setattr(cache, "get_redis", lambda: None)
        producer = MagicMock(return_value={"v": "live"})
        out = cache.cached_call(
            namespace="m", key_parts=["x"], ttl=30, producer=producer,
        )
        assert out == {"v": "live"}
        producer.assert_called_once()


class TestRedisErrors:
    """Redis is reachable but every command errors — same fail-open
    contract as a full blackout."""

    def test_session_tracker_handles_setex_error(self, monkeypatch):
        from src.common import session_tracker
        rds = MagicMock()
        rds.setex.side_effect = RuntimeError("boom")
        monkeypatch.setattr(session_tracker, "get_redis", lambda: rds)
        session_tracker.mark_active("u-1")  # no raise

    def test_cache_handles_get_error(self, monkeypatch):
        from src.common import cache
        rds = MagicMock()
        rds.get.side_effect = RuntimeError("boom")
        monkeypatch.setattr(cache, "get_redis", lambda: rds)
        producer = MagicMock(return_value=[1])
        out = cache.cached_call(
            namespace="m", key_parts=["x_distinct"], ttl=30, producer=producer,
        )
        assert out == [1]


# ── Keycloak unreachable ────────────────────────────────────────────────────

class TestKeycloakUnreachable:
    """Token verification has a Redis cache; cached tokens keep working.
    Uncached tokens fail loudly (401), which is correct — we should not
    silently authorise someone we couldn't verify."""

    def test_redis_cache_path_exists_in_token_verifier(self):
        """Token verifier reads Redis on the cached path. If Keycloak is
        unreachable but the JWT is in the cache (within its TTL), the
        request still succeeds. We assert the cache hook is wired —
        deeper coverage lives in `test_auth_cache.py`.
        """
        from src.iam import token_verifier
        # The module must expose `get_redis` (the cache hook).
        assert hasattr(token_verifier, "get_redis")


# ── Postgres reconnect ──────────────────────────────────────────────────────

class TestPostgresReconnect:
    """`get_engine()` configures `pool_pre_ping=True`, so a stale
    connection from a Postgres restart is replaced transparently. We just
    verify the configuration is in place — the real reconnect happens
    inside SQLAlchemy."""

    def test_engine_configured_with_pre_ping(self):
        from src.core.db import get_engine
        engine = get_engine()
        # SQLAlchemy stores the flag on the pool.
        assert engine.pool._pre_ping is True


# ── Compound failure: multiple deps down ────────────────────────────────────

class TestCompoundOutage:
    def test_redis_blackout_does_not_cascade_to_monitor(self, monkeypatch):
        """`monitor_overview` falls back to a live computation when the
        cache layer is unreachable. The bug we're guarding against is a
        partial Redis outage propagating up as a 500."""
        from src.common import cache
        monkeypatch.setattr(cache, "get_redis", lambda: None)

        # Stub the inner computation: we just want to confirm the wrapper
        # invokes it and returns the result rather than crashing.
        called = {"hit": False}

        def producer():
            called["hit"] = True
            return {"ok": True}

        out = cache.cached_call(
            namespace="monitor.overview",
            key_parts=["v1", 30, "u-cascade-test"],
            ttl=60,
            producer=producer,
        )
        assert out == {"ok": True}
        assert called["hit"] is True
