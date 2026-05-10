"""GET /api/me — return the authenticated principal as JSON."""
from sqlalchemy import select

from src.common.db import get_db
from src.iam.decorators import require_authenticated
from src.iam.keycloak_admin import KeycloakAdminClient
from src.iam.models import User
from src.iam.principal import Principal
from src.ticketing.models import Sector
from framework.commons.logger import logger as log


def _subgroups(group: dict) -> list[dict]:
    return group.get("subGroups") or group.get("subgroups") or []


def _keycloak_sector_codes() -> list[str]:
    try:
        client = KeycloakAdminClient.get()
        sectors_group = client.find_group_by_path("/tickora/sectors")
        sector_children = client.group_children(sectors_group["id"]) if sectors_group else []
        if sectors_group and not sector_children:
            sector_children = _subgroups(
                _find_group_by_path(client.list_groups(), ["tickora", "sectors"]) or sectors_group
            )
        if not sectors_group:
            return []
        codes = [
            (group.get("name") or "").strip().lower()
            for group in sector_children or _subgroups(sectors_group)
            if (group.get("name") or "").strip()
        ]
        return sorted(set(codes))
    except Exception as exc:
        log.warning("keycloak_sector_tree_unavailable", extra={"error": str(exc)})
        return []


def _find_group_by_path(groups: list[dict], parts: list[str]) -> dict | None:
    if not parts:
        return None
    for group in groups:
        if group.get("name") != parts[0]:
            continue
        if len(parts) == 1:
            return group
        return _find_group_by_path(_subgroups(group), parts[1:])
    return None


def _db_sector_codes() -> list[str]:
    with get_db() as db:
        return db.scalars(
            select(Sector.code)
            .where(Sector.is_active.is_(True))
            .order_by(Sector.code.asc())
        ).all()


def _sector_payload(principal: Principal) -> list[dict[str, str]]:
    memberships = {
        (m.sector_code, m.role): {"sector_code": m.sector_code, "role": m.role}
        for m in principal.sector_memberships
    }
    if principal.is_admin:
        sector_codes = _keycloak_sector_codes() or _db_sector_codes()
        for code in sector_codes:
            memberships.setdefault((code, "chief"), {"sector_code": code, "role": "chief"})
            memberships.setdefault((code, "member"), {"sector_code": code, "role": "member"})
    return [
        memberships[key]
        for key in sorted(memberships, key=lambda item: (item[0], 0 if item[1] == "chief" else 1))
    ]


def _joined_at(user_id: str) -> str | None:
    with get_db() as db:
        created_at = db.scalar(select(User.created_at).where(User.id == user_id))
    return created_at.isoformat() if created_at else None


@require_authenticated
def me(app, operation, request, *, principal: Principal, **kwargs):
    return ({
        "user_id":          principal.user_id,
        "keycloak_subject": principal.keycloak_subject,
        "username":         principal.username,
        "email":            principal.email,
        "first_name":       principal.first_name,
        "last_name":        principal.last_name,
        "created_at":       _joined_at(principal.user_id),
        "user_type":        principal.user_type,
        "roles":            sorted(principal.global_roles),
        "sectors":          _sector_payload(principal),
        "has_root_group":   principal.has_root_group,
        "is_admin":       principal.is_admin,
        "is_auditor":     principal.is_auditor,
        "is_distributor": principal.is_distributor,
    }, 200)
