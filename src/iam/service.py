"""User upsert from Keycloak claims + principal hydration."""
import json
import hashlib
import time
from typing import Any

from sqlalchemy import select

from src.common.db import get_db
from src.common.redis_client import get_redis
from src.iam.models import User
from src.iam.principal import (
    Principal,
    ROLE_ADMIN,
    SectorMembership,
)
from src.iam.keycloak_admin import KeycloakAdminClient
from framework.commons.logger import logger as log


# Keycloak group paths under /tickora/sectors/<code>/{members,chiefs}
_SECTOR_GROUP_PREFIX = "/tickora/sectors/"
_GLOBAL_TICKORA_GROUPS = {"tickora", "/tickora"}
_SECTOR_ROLE_GROUPS = {"members", "member", "chiefs", "chief"}


def _normalize_group(group: str) -> str:
    return (group or "").strip()


def _normalize_sector_code(code: str) -> str:
    value = (code or "").strip().lower()
    if value.startswith("sector") and value[len("sector"):].isdigit():
        return f"s{value[len('sector'):]}"
    return value


def _sector_membership_from_parts(parts: list[str]) -> list[SectorMembership]:
    if len(parts) == 1 and parts[0]:
        code = _normalize_sector_code(parts[0])
        return [
            SectorMembership(sector_code=code, role="chief"),
            SectorMembership(sector_code=code, role="member"),
        ]
    if len(parts) != 2:
        return []
    code, kind = _normalize_sector_code(parts[0]), parts[1]
    if not code or kind not in _SECTOR_ROLE_GROUPS:
        return []
    if kind in ("chiefs", "chief"):
        return [SectorMembership(sector_code=code, role="chief")]
    return [SectorMembership(sector_code=code, role="member")]


def _parse_sector_groups(groups: list[str]) -> list[SectorMembership]:
    out: dict[tuple[str, str], SectorMembership] = {}
    for g in groups or []:
        group = _normalize_group(g)
        memberships: list[SectorMembership] = []
        if group.startswith(_SECTOR_GROUP_PREFIX):
            rest = group[len(_SECTOR_GROUP_PREFIX):]          # e.g. "s10/members" or "s10"
            memberships = _sector_membership_from_parts(rest.strip("/").split("/"))
        elif group.startswith("/tickora/"):
            parts = [p for p in group.strip("/").split("/") if p]
            if len(parts) >= 2 and parts[0] == "tickora" and parts[1] != "sectors":
                memberships = _sector_membership_from_parts(parts[1:])
        elif group and group not in _GLOBAL_TICKORA_GROUPS:
            memberships = _sector_membership_from_parts([group])

        for membership in memberships:
            out[(membership.sector_code, membership.role)] = membership
    return list(out.values())


def _keycloak_group_paths(user_id: str | None) -> list[str]:
    if not user_id:
        return []
    try:
        groups = KeycloakAdminClient.get().get_user_groups(user_id)
        return [
            (group.get("path") or group.get("name") or "").strip()
            for group in groups
            if (group.get("path") or group.get("name") or "").strip()
        ]
    except Exception as exc:
        log.warning("keycloak_user_groups_unavailable", extra={"user_id": user_id, "error": str(exc)})
        return []


def _groups_for_claims(claims: dict[str, Any]) -> list[str]:
    groups = list(claims.get("groups") or [])
    if not groups or not {_normalize_group(g) for g in groups}.intersection(_GLOBAL_TICKORA_GROUPS):
        groups.extend(_keycloak_group_paths(claims.get("sub")))
    return sorted({_normalize_group(g) for g in groups if _normalize_group(g)})


def _effective_roles_from_claims(claims: dict[str, Any], groups: list[str] | None = None) -> frozenset[str]:
    roles = set((claims.get("realm_access") or {}).get("roles") or [])
    normalized_groups = {_normalize_group(g) for g in (groups if groups is not None else claims.get("groups") or [])}
    if normalized_groups.intersection(_GLOBAL_TICKORA_GROUPS):
        roles.add(ROLE_ADMIN)
    return frozenset(roles)


def _has_root_tickora_group(groups: list[str]) -> bool:
    groups = {_normalize_group(g) for g in groups or []}
    return bool(groups.intersection(_GLOBAL_TICKORA_GROUPS))


def _access_tree(principal: Principal) -> dict[str, Any]:
    sector_index: dict[str, set[str]] = {}
    for membership in principal.sector_memberships:
        sector_index.setdefault(membership.sector_code, set()).add(membership.role)
    return {
        "root": principal.username or principal.email or principal.user_id,
        "full_access": principal.is_admin,
        "roles": sorted(principal.global_roles),
        "sectors": [
            {
                "sector_code": code,
                "roles": sorted(roles),
                "can_see_members": principal.is_admin or "chief" in roles or "member" in roles,
            }
            for code, roles in sorted(sector_index.items())
        ],
    }


def access_tree_for_principal(principal: Principal) -> dict[str, Any]:
    return _access_tree(principal)


def _raw_realm_roles(claims: dict[str, Any]) -> set[str]:
    return set((claims.get("realm_access") or {}).get("roles") or [])


def _user_type_from_roles(roles: set[str]) -> str:
    if "tickora_external_user" in roles:
        return "external"
    return "internal"


def _role_names_for_user_type(claims: dict[str, Any]) -> set[str]:
    roles = _effective_roles_from_claims(claims)
    if roles:
        return set(roles)
    return _raw_realm_roles(claims)


def _dedupe_memberships(memberships: list[SectorMembership]) -> tuple[SectorMembership, ...]:
    return tuple(sorted(
        {(m.sector_code, m.role): m for m in memberships}.values(),
        key=lambda m: (m.sector_code, m.role),
    ))


def _legacy_parse_sector_groups(groups: list[str]) -> list[SectorMembership]:
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
    return _user_type_from_roles(_role_names_for_user_type(claims))


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
    return f"tickora:principal:v2:{claims.get('sub')}:{token_id}"


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
        "has_root_group": p.has_root_group,
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
        has_root_group=bool(data.get("has_root_group")),
        sector_memberships=tuple(
            SectorMembership(sector_code=m["sector_code"], role=m["role"])
            for m in data.get("sector_memberships") or []
        ),
    )


def get_or_create_user_from_claims(claims: dict[str, Any]) -> User:
    """
    Upsert a `users` row keyed on `keycloak_subject`.

    This function synchronizes the local database with the Identity Provider (Keycloak).
    It either creates a new user record or updates an existing one with the latest
    claims from the verified token, including username, email, and name fields.

    Args:
        claims: A dictionary containing verified JWT claims. Must contain 'sub'.

    Returns:
        A detached User model instance with the updated data.

    Raises:
        ValueError: If the 'sub' claim is missing.
    """
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
    """
    Build a Principal from verified token claims, provisioning the user if needed.

    This function is the primary entry point for hydrating a user's security context.
    It performs the following steps:
    1. Attempts to retrieve a cached Principal from Redis using a key derived from the token.
    2. If not cached, it ensures the user exists in the local database.
    3. Resolves the user's effective roles and sector memberships from token claims and Keycloak.
    4. Constructs a new Principal object and caches it in Redis for the duration of the token's validity.

    Args:
        claims: A dictionary containing verified JWT claims.

    Returns:
        A hydrated Principal object representing the authenticated user.
    """
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
    groups = _groups_for_claims(claims)
    realm_roles = _effective_roles_from_claims(claims, groups)
    memberships = _dedupe_memberships(_parse_sector_groups(groups))

    principal = Principal(
        user_id          = user.id,
        keycloak_subject = user.keycloak_subject,
        username         = user.username,
        email            = user.email,
        first_name       = user.first_name,
        last_name        = user.last_name,
        user_type        = user.user_type,
        global_roles     = realm_roles,
        sector_memberships = memberships,
        has_root_group    = _has_root_tickora_group(groups),
    )
    try:
        ttl = _seconds_until_expiry(claims)
        if rds is not None and ttl > 0:
            rds.setex(cache_key, ttl, _principal_to_cache(principal))
    except Exception:
        pass
    return principal
