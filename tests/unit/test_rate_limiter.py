"""Unit tests for src/core/rate_limiter.

The Redis interactions are mocked — the goal here is to verify:
  * fail-open semantics when Redis is down or errors out;
  * `RateLimitError` is raised exactly when the in-window cardinality
    exceeds `limit`;
  * `limit <= 0` disables the check entirely.
"""
from unittest.mock import MagicMock

import pytest

from src.common import rate_limiter
from src.core.errors import RateLimitError


@pytest.fixture
def fake_redis(monkeypatch):
    rds = MagicMock()
    pipe = MagicMock()
    pipe.execute.return_value = [0, 1, 1, True]  # zrem, zadd, zcard=1, expire
    rds.pipeline.return_value = pipe
    monkeypatch.setattr(rate_limiter, "get_redis", lambda: rds)
    return rds, pipe


def test_disabled_when_limit_zero():
    # No Redis call should happen — the function returns immediately.
    rate_limiter.check(bucket="x", identity="u", limit=0, window_s=60)


def test_no_redis_is_fail_open(monkeypatch):
    monkeypatch.setattr(rate_limiter, "get_redis", lambda: None)
    rate_limiter.check(bucket="x", identity="u", limit=5, window_s=60)


def test_under_limit_passes(fake_redis):
    rds, pipe = fake_redis
    pipe.execute.return_value = [0, 1, 3, True]  # 3 in window, limit 5
    rate_limiter.check(bucket="ticket_create", identity="u-1", limit=5, window_s=60)


def test_at_limit_passes(fake_redis):
    rds, pipe = fake_redis
    pipe.execute.return_value = [0, 1, 5, True]  # 5 in window, limit 5 → ok
    rate_limiter.check(bucket="ticket_create", identity="u-1", limit=5, window_s=60)


def test_over_limit_raises(fake_redis):
    rds, pipe = fake_redis
    pipe.execute.return_value = [0, 1, 6, True]  # 6 in window, limit 5
    with pytest.raises(RateLimitError) as exc:
        rate_limiter.check(bucket="ticket_create", identity="u-1", limit=5, window_s=60)
    assert exc.value.details["bucket"] == "ticket_create"
    assert exc.value.details["limit"] == 5


def test_redis_error_is_fail_open(fake_redis):
    rds, pipe = fake_redis
    pipe.execute.side_effect = RuntimeError("redis blip")
    # Must not raise — outage falls open.
    rate_limiter.check(bucket="x", identity="u", limit=1, window_s=60)


def test_unique_member_per_call(fake_redis):
    """Two checks within the same millisecond must not collapse to a single
    sorted-set entry — otherwise the limiter would under-count bursts."""
    rds, pipe = fake_redis
    rate_limiter.check(bucket="x", identity="u", limit=10, window_s=60)
    rate_limiter.check(bucket="x", identity="u", limit=10, window_s=60)
    # `zadd` is the second pipeline op; check it received different members.
    zadd_calls = [c for c in pipe.zadd.call_args_list]
    members_seen = set()
    for call in zadd_calls:
        # signature: zadd(key, {member: score})
        members_seen.update(call.args[1].keys())
    assert len(members_seen) == 2
