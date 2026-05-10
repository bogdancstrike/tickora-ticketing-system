"""Unit tests for src/core/session_tracker — Redis-backed presence keys."""
from unittest.mock import MagicMock

import pytest

from src.common import session_tracker


@pytest.fixture
def fake_redis(monkeypatch):
    """Drop-in Redis stub that captures setex/scan interactions."""
    rds = MagicMock()
    rds.scan.return_value = (0, [])
    monkeypatch.setattr(session_tracker, "get_redis", lambda: rds)
    return rds


def test_mark_active_no_redis_is_safe(monkeypatch):
    monkeypatch.setattr(session_tracker, "get_redis", lambda: None)
    # Must not raise — presence is non-critical and Redis is optional.
    session_tracker.mark_active("u-1")


def test_mark_active_writes_presence_key(fake_redis):
    session_tracker.mark_active("u-42", ttl=120)
    fake_redis.setex.assert_called_once_with("tickora:session:active:u-42", 120, "1")


def test_mark_active_ignores_blank_user(fake_redis):
    session_tracker.mark_active(None)
    session_tracker.mark_active("")
    fake_redis.setex.assert_not_called()


def test_mark_active_swallows_redis_error(fake_redis):
    fake_redis.setex.side_effect = RuntimeError("redis down")
    # Must not propagate — presence cannot break a request.
    session_tracker.mark_active("u-99")


def test_active_user_count_no_redis(monkeypatch):
    monkeypatch.setattr(session_tracker, "get_redis", lambda: None)
    assert session_tracker.active_user_count() == 0


def test_active_user_count_scans(fake_redis):
    fake_redis.scan.return_value = (
        0,
        [
            "tickora:session:active:u-1",
            "tickora:session:active:u-2",
            "tickora:session:active:u-3",
        ],
    )
    assert session_tracker.active_user_count() == 3


def test_active_user_ids_strips_prefix(fake_redis):
    fake_redis.scan.return_value = (
        0,
        ["tickora:session:active:u-1", "tickora:session:active:u-2"],
    )
    assert session_tracker.active_user_ids() == {"u-1", "u-2"}


def test_active_user_ids_swallows_redis_error(fake_redis):
    fake_redis.scan.side_effect = RuntimeError("scan failed")
    assert session_tracker.active_user_ids() == set()
