"""Unit tests for src/core/cache — Redis JSON memoization."""
import json
from unittest.mock import MagicMock

import pytest

from src.common import cache


@pytest.fixture
def fake_redis(monkeypatch):
    rds = MagicMock()
    rds.get.return_value = None  # default: cache miss
    monkeypatch.setattr(cache, "get_redis", lambda: rds)
    return rds


def test_make_key_is_stable_and_namespaced():
    k1 = cache.make_key("foo", ["a", "b", 3])
    k2 = cache.make_key("foo", ["a", "b", 3])
    assert k1 == k2
    assert k1.startswith("tickora:cache:foo:")


def test_make_key_differs_by_inputs():
    a = cache.make_key("foo", ["a"])
    b = cache.make_key("foo", ["b"])
    assert a != b


def test_make_key_handles_none_components():
    # None components should not crash; they degrade to empty-string parts.
    k = cache.make_key("foo", [None, "x"])
    assert k.startswith("tickora:cache:foo:")


def test_cached_call_runs_producer_on_miss(fake_redis):
    producer = MagicMock(return_value={"v": 1})
    out = cache.cached_call(namespace="m", key_parts=["x"], ttl=30, producer=producer)
    assert out == {"v": 1}
    producer.assert_called_once()
    fake_redis.setex.assert_called_once()
    args, _ = fake_redis.setex.call_args
    assert args[1] == 30
    assert json.loads(args[2]) == {"v": 1}


def test_cached_call_returns_cached_on_hit(fake_redis):
    fake_redis.get.return_value = json.dumps({"v": 99})
    producer = MagicMock(return_value={"v": "fresh"})
    out = cache.cached_call(namespace="m", key_parts=["x"], ttl=30, producer=producer)
    assert out == {"v": 99}
    producer.assert_not_called()
    fake_redis.setex.assert_not_called()


def test_cached_call_falls_through_when_redis_down(monkeypatch):
    monkeypatch.setattr(cache, "get_redis", lambda: None)
    producer = MagicMock(return_value={"v": "live"})
    out = cache.cached_call(namespace="m", key_parts=["x"], ttl=30, producer=producer)
    assert out == {"v": "live"}
    producer.assert_called_once()


def test_cached_call_recovers_from_redis_get_error(fake_redis):
    fake_redis.get.side_effect = RuntimeError("redis blip")
    producer = MagicMock(return_value=[1, 2, 3])
    out = cache.cached_call(namespace="m", key_parts=["x"], ttl=30, producer=producer)
    assert out == [1, 2, 3]
    producer.assert_called_once()


def test_cached_call_serializes_datetime():
    """`_json_default` must serialize datetimes so caching aggregate payloads
    that include timestamps doesn't crash."""
    from datetime import datetime, timezone
    payload = {"generated_at": datetime(2026, 5, 9, tzinfo=timezone.utc)}
    raw = json.dumps(payload, default=cache._json_default)
    assert "2026-05-09" in raw
