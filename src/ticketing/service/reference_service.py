"""Database-backed reference data used by ticket forms."""
from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from src.iam.models import User
from src.ticketing.models import Sector, SectorMembership, Ticket

DEFAULT_PRIORITIES = ("low", "medium", "high", "critical")
DEFAULT_CATEGORIES = ("access", "hardware", "network", "software", "facilities")
DEFAULT_TYPES = ("request", "incident", "task", "question")


def ticket_options(db: Session) -> dict:
    sectors = list(db.scalars(
        select(Sector)
        .where(Sector.is_active.is_(True))
        .order_by(Sector.code.asc())
    ))
    return {
        "sectors": [
            {"id": s.id, "code": s.code, "name": s.name}
            for s in sectors
        ],
        "priorities": _values(db, Ticket.priority, DEFAULT_PRIORITIES),
        "categories": _values(db, Ticket.category, DEFAULT_CATEGORIES),
        "types": _values(db, Ticket.type, DEFAULT_TYPES),
    }


def assignable_users(db: Session, *, sector_code: str | None = None) -> list[dict]:
    stmt = (
        select(User, Sector.code, SectorMembership.membership_role)
        .join(SectorMembership, SectorMembership.user_id == User.id)
        .join(Sector, Sector.id == SectorMembership.sector_id)
        .where(User.is_active.is_(True), SectorMembership.is_active.is_(True), Sector.is_active.is_(True))
        .order_by(Sector.code.asc(), User.username.asc())
    )
    if sector_code:
        stmt = stmt.where(Sector.code == sector_code)

    rows = db.execute(stmt).all()
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "sector_code": code,
            "membership_role": role,
        }
        for user, code, role in rows
    ]


def _values(db: Session, column, defaults: tuple[str, ...]) -> list[str]:
    existing = [
        value for value in db.scalars(
            select(distinct(column)).where(column.is_not(None)).order_by(column.asc())
        )
        if value
    ]
    seen = set(existing)
    return existing + [value for value in defaults if value not in seen]
