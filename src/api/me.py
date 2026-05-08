"""GET /api/me — return the authenticated principal as JSON."""
from sqlalchemy import select

from src.core.db import get_db
from src.iam.decorators import require_authenticated
from src.iam.models import User
from src.iam.principal import Principal
from src.ticketing.models import Sector


def _sector_payload(principal: Principal) -> list[dict[str, str]]:
    memberships = {
        (m.sector_code, m.role): {"sector_code": m.sector_code, "role": m.role}
        for m in principal.sector_memberships
    }
    if principal.is_admin:
        with get_db() as db:
            sector_codes = db.scalars(
                select(Sector.code)
                .where(Sector.is_active.is_(True))
                .order_by(Sector.code.asc())
            ).all()
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
        "is_admin":       principal.is_admin,
        "is_auditor":     principal.is_auditor,
        "is_distributor": principal.is_distributor,
    }, 200)
