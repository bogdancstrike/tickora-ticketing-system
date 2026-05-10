"""Ticket links — parent/child, blocks, duplicates, and free-form
"relates_to" relationships between tickets.

The `ticket_links` table is directional: each row is a `(source, target,
type)` triple. To present a clean UI, we materialise the *inverse* of
each canonical type when reading; e.g. a row `parent_of(A, B)` shows up
as "child" on B's detail page.

Authorization rules:
  * **Add a link**: principal must be able to *modify* the source ticket
    (`rbac.can_modify_ticket`) AND be able to *view* the target ticket
    (`ticket_service.get`). You can't link onto a ticket you don't
    control, and you can't reach into a ticket you can't see.
  * **Remove a link**: same rules — modify on source side.
  * **List links**: anyone who can view the source ticket. The target
    ticket is shown in a redacted form (id + code + title + status only)
    so even when the user can't see the target's details, the
    relationship is visible.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.audit import service as audit_service
from src.audit.events import TICKET_LINK_ADDED, TICKET_LINK_REMOVED
from src.common.errors import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing.models import Ticket, TicketLink
from src.ticketing.service import ticket_service


# Canonical link types. The inverse map drives the UI relabelling for
# the target side. New types: extend both maps in lock-step.
LINK_TYPES = {
    "parent_of":   "child_of",
    "blocks":      "blocked_by",
    "duplicates":  "duplicate_of",
    "relates_to":  "relates_to",   # symmetric
}
ALL_LINK_TYPES = set(LINK_TYPES) | set(LINK_TYPES.values())


def _check_modify(db: Session, principal: Principal, ticket_id: str) -> Ticket:
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_modify_ticket(principal, ticket):
        raise PermissionDeniedError("not allowed to modify this ticket")
    return ticket


def add(
    db: Session,
    principal: Principal,
    *,
    source_ticket_id: str,
    target_ticket_id: str,
    link_type: str,
) -> TicketLink:
    """Create a directional link from `source` → `target`.

    Idempotent: re-adding the same triple returns the existing row.
    Self-links are rejected (`A → A`) — they're never useful and lead to
    confusing UI.
    """
    if link_type not in LINK_TYPES:
        raise ValidationError(
            f"link_type must be one of {sorted(LINK_TYPES)}",
            details={"received": link_type},
        )
    if source_ticket_id == target_ticket_id:
        raise BusinessRuleError("a ticket cannot link to itself")

    source = _check_modify(db, principal, source_ticket_id)
    target = ticket_service.get(db, principal, target_ticket_id)

    existing = db.scalar(
        select(TicketLink).where(
            TicketLink.source_ticket_id == source.id,
            TicketLink.target_ticket_id == target.id,
            TicketLink.link_type == link_type,
        )
    )
    if existing is not None:
        return existing

    row = TicketLink(
        source_ticket_id=source.id,
        target_ticket_id=target.id,
        link_type=link_type,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    db.flush()

    audit_service.record(
        db,
        actor=principal,
        action=TICKET_LINK_ADDED,
        entity_type="ticket_link",
        entity_id=row.id,
        ticket_id=source.id,
        new_value={
            "source_ticket_id": source.id,
            "target_ticket_id": target.id,
            "link_type": link_type,
        },
    )
    return row


def remove(
    db: Session,
    principal: Principal,
    *,
    link_id: str,
) -> None:
    row = db.get(TicketLink, link_id)
    if row is None:
        raise NotFoundError("link not found")
    # Modify-permission on either end is sufficient — the user might be
    # the owner of one side and not the other; refusing because they
    # can't reach the other side would create dead-end links.
    source = ticket_service.get(db, principal, row.source_ticket_id)
    if not rbac.can_modify_ticket(principal, source):
        # Try the target-side modify permission as a fallback.
        target = ticket_service.get(db, principal, row.target_ticket_id)
        if not rbac.can_modify_ticket(principal, target):
            raise PermissionDeniedError("not allowed to remove this link")

    snapshot = {
        "source_ticket_id": row.source_ticket_id,
        "target_ticket_id": row.target_ticket_id,
        "link_type": row.link_type,
    }
    db.delete(row)
    db.flush()

    audit_service.record(
        db,
        actor=principal,
        action=TICKET_LINK_REMOVED,
        entity_type="ticket_link",
        entity_id=link_id,
        ticket_id=snapshot["source_ticket_id"],
        old_value=snapshot,
    )


def list_for_ticket(
    db: Session,
    principal: Principal,
    ticket_id: str,
) -> list[dict[str, Any]]:
    """Return links *involving* the ticket — both as source and target.

    Each row is presented from the *current ticket's* perspective:
      * a row where `source == ticket_id` keeps `link_type`
      * a row where `target == ticket_id` shows `LINK_TYPES[link_type]`
        (the inverse) so "A blocks B" is presented as "blocked_by" on
        B's page.
    """
    ticket = ticket_service.get(db, principal, ticket_id)
    rows = db.execute(
        select(
            TicketLink.id,
            TicketLink.source_ticket_id,
            TicketLink.target_ticket_id,
            TicketLink.link_type,
            TicketLink.created_at,
        )
        .where(or_(
            TicketLink.source_ticket_id == ticket.id,
            TicketLink.target_ticket_id == ticket.id,
        ))
        .order_by(TicketLink.created_at.asc())
    ).all()

    other_ids = {
        (r[2] if r[1] == ticket.id else r[1])
        for r in rows
    }
    if not other_ids:
        return []

    # Hydrate redacted summaries of the linked tickets. We deliberately
    # surface only id / code / title / status so a private cross-sector
    # link doesn't leak details.
    others = db.execute(
        select(Ticket.id, Ticket.ticket_code, Ticket.title, Ticket.status)
        .where(Ticket.id.in_(other_ids))
    ).all()
    summaries = {
        row[0]: {
            "id":          row[0],
            "ticket_code": row[1],
            "title":       row[2],
            "status":      row[3],
        }
        for row in others
    }

    out: list[dict[str, Any]] = []
    for r in rows:
        link_id, src, tgt, link_type, created_at = r
        is_outgoing = src == ticket.id
        other_id = tgt if is_outgoing else src
        relation = link_type if is_outgoing else LINK_TYPES.get(link_type, link_type)
        other = summaries.get(other_id)
        if other is None:
            continue  # racey delete — skip
        out.append({
            "id":         link_id,
            "direction":  "outgoing" if is_outgoing else "incoming",
            "relation":   relation,
            "other":      other,
            "created_at": created_at.isoformat() if created_at else None,
        })
    return out
