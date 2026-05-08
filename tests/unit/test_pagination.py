"""Unit tests for src/core/pagination.py."""
from datetime import datetime, timezone

from src.core.pagination import Cursor, clamp_limit


def test_encode_decode_roundtrip_str():
    c = Cursor(sort_value="abc", id="id-1")
    out = Cursor.decode(c.encode())
    assert out is not None
    assert out.sort_value == "abc"
    assert out.id == "id-1"


def test_encode_decode_roundtrip_datetime():
    dt = datetime(2026, 5, 8, 10, 0, tzinfo=timezone.utc)
    c = Cursor(sort_value=dt, id="abc")
    out = Cursor.decode(c.encode())
    assert isinstance(out.sort_value, datetime)
    assert out.sort_value == dt
    assert out.id == "abc"


def test_decode_garbage_returns_none():
    assert Cursor.decode("not-a-cursor!!!") is None
    assert Cursor.decode(None) is None
    assert Cursor.decode("") is None


def test_clamp_limit():
    assert clamp_limit(None) == 50
    assert clamp_limit(10) == 10
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(9999, max_=200) == 200
    assert clamp_limit("not-a-number") == 50
