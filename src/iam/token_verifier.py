"""JWT verification against Keycloak JWKS, with Redis-backed caching."""
import json
import hashlib
import time
from typing import Any

import requests
from jose import jwt
from jose.exceptions import JWTError

from src.config import Config
from src.common.errors import AuthenticationError
from src.common.redis_client import get_redis
from src.common.spans import set_attr, span
from framework.commons.logger import logger as log


class _JwksCache:
    """In-process JWKS cache. Refreshed on `kid` miss."""

    def __init__(self) -> None:
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0

    def _jwks_url(self) -> str:
        return f"{Config.KEYCLOAK_ISSUER.rstrip('/')}/protocol/openid-connect/certs"

    def _stale(self) -> bool:
        return (time.time() - self._fetched_at) > Config.JWKS_CACHE_TTL

    def get(self, kid: str) -> dict | None:
        if kid in self._keys and not self._stale():
            return self._keys[kid]
        self._refresh()
        return self._keys.get(kid)

    def _refresh(self) -> None:
        url = self._jwks_url()
        log.info("fetching jwks", extra={"url": url})
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            data = r.json()
            self._keys = {k["kid"]: k for k in data.get("keys", [])}
            self._fetched_at = time.time()
        except Exception as e:
            log.warning("jwks fetch failed", extra={"error": str(e)})


_jwks = _JwksCache()


def _token_cache_key(token: str) -> str:
    return f"tickora:jwt:tok:{hashlib.sha256(token.encode('utf-8')).hexdigest()}"


def _seconds_until_expiry(claims: dict[str, Any]) -> int:
    return max(0, int(claims.get("exp", 0) - time.time()))


def verify_token(token: str) -> dict[str, Any]:
    """Verify a Bearer token and return its claims. Raise AuthenticationError on failure."""
    with span("iam.verify_token") as current:
        if not token:
            raise AuthenticationError("missing token")

        rds = get_redis()
        try:
            cache_key = _token_cache_key(token)
            if rds is not None:
                cached = rds.get(cache_key)
                if cached:
                    claims = json.loads(cached)
                    ttl = _seconds_until_expiry(claims)
                    if ttl > 0:
                        set_attr(current, "jwt.cache_hit", True)
                        set_attr(current, "jwt.sub", claims.get("sub"))
                        set_attr(current, "jwt.username", claims.get("preferred_username"))
                        set_attr(current, "jwt.ttl_seconds", ttl)
                        return claims
        except Exception:
            pass
        set_attr(current, "jwt.cache_hit", False)

        try:
            unverified_header = jwt.get_unverified_header(token)
        except JWTError as e:
            raise AuthenticationError(f"malformed token: {e}")

        kid = unverified_header.get("kid")
        set_attr(current, "jwt.kid", kid)
        if not kid:
            raise AuthenticationError("token missing kid")

        key = _jwks.get(kid)
        if key is None:
            raise AuthenticationError("unknown signing key")

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[key.get("alg", "RS256")],
                audience=Config.KEYCLOAK_AUDIENCE,
                issuer=Config.KEYCLOAK_ISSUER,
                options={"verify_at_hash": False},
            )
        except JWTError as e:
            raise AuthenticationError(f"token verification failed: {e}")

        set_attr(current, "jwt.sub", claims.get("sub"))
        set_attr(current, "jwt.username", claims.get("preferred_username"))
        set_attr(current, "jwt.ttl_seconds", _seconds_until_expiry(claims))
        try:
            if rds is not None:
                ttl = _seconds_until_expiry(claims)
                if ttl > 0:
                    rds.setex(cache_key, ttl, json.dumps(claims))
        except Exception:
            pass
        return claims
