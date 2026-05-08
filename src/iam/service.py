"""User upsert from Keycloak claims + principal hydration."""
import json
import hashlib
import time
from typing import Any

from sqlalchemy import select

from src.core.db import get_db
from src.core.redis_client import get_redis
from src.iam.models import User
from src.iam.principal import (
    Principal,
    SectorMembership,
)
from framework.commons.logger import logger as log


# Keycloak group paths under /tickora/sectors/<code>/{members,chiefs}
_SECTOR_GROUP_PREFIX = "/tickora/sectors/"


def _parse_sector_groups(groups: list[str]) -> list[SectorMembership]:
    out: list[SectorMembership] = []
    for g in groups or []:
        if not g.startswith(_SECTOR_GROUP_PREFIX):
            continue
        rest = g[len(_SECTOR_GROUP_PREFIX):]                # e.g. "s10/members"
        parts = rest.strip("/").split("/")
        if len(parts) != 2:
            continue
        code, kind = parts
        if kind == "members":
            out.append(SectorMembership(sector_code=code, role="member"))
        elif kind == "chiefs":
            out.append(SectorMembership(sector_code=code, role="chief"))
    return out


def _user_type_from_claims(claims: dict[str, Any]) -> str:
    roles = set(((claims.get("realm_access") or {}).get("roles") or []))
    if "tickora_external_user" in roles:
        return "external"
    return "internal"


def _seconds_until_expiry(claims: dict[str, Any]) -> int:
    return max(0, int(claims.get("exp", 0) - time.time()))


def _principal_cache_key(claims: dict[str, Any]) -> str:
    token_id = claims.get("jti")
    if not token_id:
        material = json.dumps(
            {
                "sub": claims.get("sub"),
                "iat": claims.get("iat"),
                "exp": claims.get("exp"),
                "roles": (claims.get("realm_access") or {}).get("roles") or [],
                "groups": claims.get("groups") or [],
            },
            sort_keys=True,
        )
        token_id = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"tickora:principal:{claims.get('sub')}:{token_id}"


def _principal_to_cache(p: Principal) -> str:
    return json.dumps({
        "user_id": p.user_id,
        "keycloak_subject": p.keycloak_subject,
        "username": p.username,
        "email": p.email,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "user_type": p.user_type,
        "global_roles": sorted(p.global_roles),
        "sector_memberships": [
            {"sector_code": m.sector_code, "role": m.role}
            for m in p.sector_memberships
        ],
    })


def _principal_from_cache(raw: str) -> Principal:
    data = json.loads(raw)
    return Principal(
        user_id=data["user_id"],
        keycloak_subject=data["keycloak_subject"],
        username=data.get("username"),
        email=data.get("email"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        user_type=data.get("user_type") or "internal",
        global_roles=frozenset(data.get("global_roles") or []),
        sector_memberships=tuple(
            SectorMembership(sector_code=m["sector_code"], role=m["role"])
            for m in data.get("sector_memberships") or []
        ),
    )


def get_or_create_user_from_claims(claims: dict[str, Any]) -> User:
    """Upsert a `users` row keyed on `keycloak_subject`."""
    sub = claims.get("sub")
    if not sub:
        raise ValueError("claims missing sub")

    with get_db() as db:
        user = db.scalar(select(User).where(User.keycloak_subject == sub))
        if user is None:
            user = User(
                keycloak_subject=sub,
                username   = claims.get("preferred_username"),
                email      = claims.get("email"),
                first_name = claims.get("given_name"),
                last_name  = claims.get("family_name"),
                user_type  = _user_type_from_claims(claims),
            )
            db.add(user)
            db.flush()
            log.info("user provisioned", extra={"user_id": user.id, "sub": sub})
        else:
            # Refresh basic profile fields from the IdP.
            user.username   = claims.get("preferred_username") or user.username
            user.email      = claims.get("email")              or user.email
            user.first_name = claims.get("given_name")         or user.first_name
            user.last_name  = claims.get("family_name")        or user.last_name
            user.user_type  = _user_type_from_claims(claims)
        db.flush()
        # Detach a lightweight copy
        return User(
            id=user.id,
            keycloak_subject=user.keycloak_subject,
            username=user.username,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            user_type=user.user_type,
            is_active=user.is_active,
        )


def principal_from_claims(claims: dict[str, Any]) -> Principal:
    """Build a Principal from verified token claims, provisioning the user if needed."""
    rds = get_redis()
    cache_key = _principal_cache_key(claims)
    try:
        if rds is not None:
            cached = rds.get(cache_key)
            if cached and _seconds_until_expiry(claims) > 0:
                return _principal_from_cache(cached)
    except Exception:
        pass

    user = get_or_create_user_from_claims(claims)
    realm_roles = frozenset((claims.get("realm_access") or {}).get("roles") or [])
    memberships = _parse_sector_groups(claims.get("groups") or [])

    principal = Principal(
        user_id          = user.id,
        keycloak_subject = user.keycloak_subject,
        username         = user.username,
        email            = user.email,
        first_name       = user.first_name,
        last_name        = user.last_name,
        user_type        = user.user_type,
        global_roles     = realm_roles,
        sector_memberships = tuple(memberships),
    )
    try:
        ttl = _seconds_until_expiry(claims)
        if rds is not None and ttl > 0:
            rds.setex(cache_key, ttl, _principal_to_cache(principal))
    except Exception:
        pass
    return principal
