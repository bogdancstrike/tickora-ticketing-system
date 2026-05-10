"""Trusted-proxy-aware client IP + user-agent extraction.

`X-Forwarded-For` is trivially forged by a direct caller. We only honour
it when the immediate peer (`remote_addr`) is in the configured trusted
proxy set; otherwise the header is ignored and we report the peer IP.

The trusted set is read from `Config.TRUSTED_PROXIES` and supports either
plain IPs or CIDR blocks. An empty set (the default) means "no proxies
trusted" — `remote_addr` wins every time.

This module is a small wrapper specifically because the same logic
previously lived inline in `ticket_service` and `audit_service` and had
already drifted between the two call sites.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from flask import request as flask_request

from src.config import Config


def _is_trusted_peer(peer_ip: str | None) -> bool:
    if not peer_ip or not Config.TRUSTED_PROXIES:
        return False
    try:
        peer = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    for entry in Config.TRUSTED_PROXIES:
        try:
            if "/" in entry:
                if peer in ipaddress.ip_network(entry, strict=False):
                    return True
            else:
                if peer == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            continue
    return False


def _client_ip_from_xff(xff_header: str | None) -> str | None:
    """`X-Forwarded-For` is `client, proxy1, proxy2, …`. The leftmost entry
    is the original client (assuming the header is trusted)."""
    if not xff_header:
        return None
    first = xff_header.split(",")[0].strip()
    return first or None


def client_ip() -> Optional[str]:
    """Return the best-guess client IP for the current request.

    * Trusted-peer + `X-Forwarded-For` present → leftmost entry of the header.
    * Otherwise → `remote_addr`.
    """
    try:
        peer = flask_request.remote_addr
        if _is_trusted_peer(peer):
            xff = _client_ip_from_xff(flask_request.headers.get("X-Forwarded-For"))
            if xff:
                return xff
        return peer
    except Exception:
        return None


def request_metadata() -> tuple[Optional[str], Optional[str]]:
    """`(client_ip, user_agent)` for audit trails. Both are `None`-safe and
    swallow exceptions so the request doesn't fail when no Flask context
    is active (e.g. background workers reusing the helper)."""
    try:
        return client_ip(), flask_request.headers.get("User-Agent")
    except Exception:
        return None, None
