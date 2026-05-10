"""Unit tests for src/core/request_metadata.

Verifies that `X-Forwarded-For` is only honored when the immediate peer
(`remote_addr`) is in `Config.TRUSTED_PROXIES`. Otherwise the header is
ignored — a direct caller cannot forge their client IP.
"""
from unittest.mock import patch

import pytest
from flask import Flask

from src.common import request_metadata


@pytest.fixture
def app():
    return Flask(__name__)


def _set_trusted(monkeypatch, value):
    from src.config import Config
    monkeypatch.setattr(Config, "TRUSTED_PROXIES", value)


def test_no_xff_returns_remote_addr(app, monkeypatch):
    _set_trusted(monkeypatch, ())
    with app.test_request_context("/", environ_overrides={"REMOTE_ADDR": "10.0.0.5"}):
        assert request_metadata.client_ip() == "10.0.0.5"


def test_xff_ignored_when_no_trusted_proxies(app, monkeypatch):
    _set_trusted(monkeypatch, ())
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "203.0.113.5"},
        headers={"X-Forwarded-For": "1.2.3.4"},
    ):
        # Direct caller forged XFF — must be ignored.
        assert request_metadata.client_ip() == "203.0.113.5"


def test_xff_honored_from_trusted_proxy_ip(app, monkeypatch):
    _set_trusted(monkeypatch, ("10.0.0.10",))
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    ):
        assert request_metadata.client_ip() == "198.51.100.7"


def test_xff_first_entry_wins(app, monkeypatch):
    _set_trusted(monkeypatch, ("10.0.0.10",))
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
        headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.20, 10.0.0.10"},
    ):
        assert request_metadata.client_ip() == "198.51.100.7"


def test_xff_honored_from_trusted_cidr(app, monkeypatch):
    _set_trusted(monkeypatch, ("10.0.0.0/8",))
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "10.5.6.7"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    ):
        assert request_metadata.client_ip() == "198.51.100.7"


def test_xff_rejected_from_outside_trusted_cidr(app, monkeypatch):
    _set_trusted(monkeypatch, ("10.0.0.0/8",))
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "192.168.1.1"},
        headers={"X-Forwarded-For": "198.51.100.7"},
    ):
        # 192.168/16 is not in the trusted CIDR — ignore the header.
        assert request_metadata.client_ip() == "192.168.1.1"


def test_request_metadata_returns_tuple(app, monkeypatch):
    _set_trusted(monkeypatch, ())
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "10.0.0.5"},
        headers={"User-Agent": "TestBot/1.0"},
    ):
        ip, ua = request_metadata.request_metadata()
        assert ip == "10.0.0.5"
        assert ua == "TestBot/1.0"


def test_request_metadata_outside_request_context_is_safe():
    # No active Flask request: must not raise.
    ip, ua = request_metadata.request_metadata()
    assert ip is None
    assert ua is None


def test_invalid_xff_value_falls_back_to_peer(app, monkeypatch):
    _set_trusted(monkeypatch, ("10.0.0.10",))
    with app.test_request_context(
        "/",
        environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
        headers={"X-Forwarded-For": ""},
    ):
        # Empty header → fall back to peer (which is the trusted proxy).
        assert request_metadata.client_ip() == "10.0.0.10"
