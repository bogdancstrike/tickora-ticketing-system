"""Database-backed reference data used by ticket forms."""
from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from src.iam.models import User
from src.ticketing.models import (
    MetadataKeyDefinition, Sector, SectorMembership, Ticket, TicketMetadata,
)

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
        "metadata_keys": _metadata_keys(db),
    }


def _metadata_keys(db: Session) -> list[dict]:
    """Return the catalogue of metadata keys, with options if defined.

    Authoritative source is `metadata_key_definitions`. Any keys present in
    `ticket_metadatas` but missing a definition are surfaced as free-text keys
    so legacy data is still editable.
    """
    defs = list(db.scalars(
        select(MetadataKeyDefinition)
        .where(MetadataKeyDefinition.is_active.is_(True))
        .order_by(MetadataKeyDefinition.label.asc())
    ))
    out: list[dict] = [
        {
            "key":         d.key,
            "label":       d.label,
            "value_type":  d.value_type,
            "options":     d.options,
            "description": d.description,
        }
        for d in defs
    ]

    seen = {d.key for d in defs}
    legacy = db.execute(
        select(distinct(TicketMetadata.key), TicketMetadata.label)
        .order_by(TicketMetadata.key.asc())
    ).all()
    for k, label in legacy:
        if k not in seen:
            out.append({"key": k, "label": label or k, "value_type": "string", "options": None, "description": None})
    return out


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
