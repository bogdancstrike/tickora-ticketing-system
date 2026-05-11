"""Database-backed reference data used by ticket forms."""
from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from src.iam.models import User
from src.ticketing.models import (
    Category, MetadataKeyDefinition, Sector, SectorMembership, Subcategory,
    SubcategoryFieldDefinition, Ticket, TicketMetadata,
)

DEFAULT_PRIORITIES = ("low", "medium", "high", "critical")


def ticket_options(db: Session) -> dict:
    sectors = list(db.scalars(
        select(Sector)
        .where(Sector.is_active.is_(True))
        .order_by(Sector.code.asc())
    ))
    cats = list(db.scalars(
        select(Category)
        .where(Category.is_active.is_(True))
        .order_by(Category.name.asc())
    ))
    subs_by_cat: dict[str, list[Subcategory]] = {}
    for sub in db.scalars(
        select(Subcategory)
        .where(Subcategory.is_active.is_(True))
        .order_by(Subcategory.display_order.asc(), Subcategory.name.asc())
    ):
        subs_by_cat.setdefault(sub.category_id, []).append(sub)

    return {
        "sectors": [
            {"id": s.id, "code": s.code, "name": s.name}
            for s in sectors
        ],
        "priorities": _values(db, Ticket.priority, DEFAULT_PRIORITIES),
        "categories": [
            {
                "id":   c.id,
                "code": c.code,
                "name": c.name,
                "description": c.description,
                "subcategories": [
                    {"id": s.id, "code": s.code, "name": s.name, "description": s.description}
                    for s in subs_by_cat.get(c.id, [])
                ],
            }
            for c in cats
        ],
        "metadata_keys": _metadata_keys(db),
    }


def subcategory_fields(db: Session, subcategory_id: str) -> list[dict]:
    """Return the ordered field catalogue for a given subcategory.

    Used by the create-ticket form: when the user picks a subcategory, the
    UI fetches this list and renders one form item per field, marking the
    required ones with a red `*`.
    """
    rows = list(db.scalars(
        select(SubcategoryFieldDefinition)
        .where(SubcategoryFieldDefinition.subcategory_id == subcategory_id)
        .order_by(
            SubcategoryFieldDefinition.display_order.asc(),
            SubcategoryFieldDefinition.label.asc(),
        )
    ))
    return [
        {
            "id":            f.id,
            "key":           f.key,
            "label":         f.label,
            "value_type":    f.value_type,
            "options":       f.options,
            "is_required":   f.is_required,
            "display_order": f.display_order,
            "description":   f.description,
        }
        for f in rows
    ]


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
