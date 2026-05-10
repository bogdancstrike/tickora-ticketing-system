"""Ticket watchers — voluntary subscriptions to a ticket's notifications.

A watcher is a user who isn't assigned but wants to follow the ticket's
activity. Notifications fan out to watchers exactly the same way they fan
out to assignees, with one exception: **visibility is still RBAC-gated at
delivery time**. A watcher cannot peek at a private comment they wouldn't
otherwise be allowed to read; the notification is simply suppressed.

Authorization rules:
  * **Self-subscribe / unsubscribe**: any authenticated user who can
    *view* the ticket. Watching is an opt-in interest, not a permission
    grant — you can only watch what you can already see.
  * **Subscribe / unsubscribe someone else**: admins only. (Future:
    sector chiefs adding their team members — TBD.)
  * **List watchers**: anyone who can view the ticket. The list is not
    sensitive — knowing who's interested in a public ticket is fine.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.audit import service as audit_service
from src.audit.events import (
    TICKET_WATCHER_ADDED,
    TICKET_WATCHER_REMOVED,
)
from src.core.errors import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
)
from src.iam.models import User
from src.iam.principal import Principal
from src.ticketing.models import TicketWatcher
from src.ticketing.service import ticket_service


def add(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    user_id: str | None = None,
) -> TicketWatcher:
    """Subscribe `user_id` (defaults to the principal) to the ticket.

    Idempotent: existing rows are returned as-is rather than re-inserted.
    Adding someone other than yourself requires admin.
    """
    target_user_id = user_id or principal.user_id
    if target_user_id != principal.user_id and not principal.is_admin:
        raise PermissionDeniedError("only admins can subscribe other users")

    # Visibility is the canonical gate. `ticket_service.get` raises
    # NotFound if the principal can't see the ticket — exactly what we
    # want. We intentionally don't disclose existence to non-watchers.
    ticket = ticket_service.get(db, principal, ticket_id)

    # Verify the target user actually exists. Skip when it's the self-
    # path because the principal is already proven by token verification.
    if target_user_id != principal.user_id:
        target = db.get(User, target_user_id)
        if target is None:
            raise NotFoundError("user not found")

    try:
        existing = db.scalar(
            select(TicketWatcher).where(
                TicketWatcher.ticket_id == ticket.id,
                TicketWatcher.user_id == target_user_id,
            )
        )
    except Exception:
        # `ticket_watchers` missing — migration not applied. Surface a
        # readable message to the operator instead of an opaque 500.
        try:
            db.rollback()
        except Exception:
            pass
        raise BusinessRuleError(
            "watcher table is not migrated yet — run `make migrate`"
        )
    if existing is not None:
        return existing

    row = TicketWatcher(
        ticket_id=ticket.id,
        user_id=target_user_id,
        created_by_user_id=principal.user_id,
    )
    db.add(row)
    db.flush()

    audit_service.record(
        db,
        actor=principal,
        action=TICKET_WATCHER_ADDED,
        entity_type="ticket_watcher",
        entity_id=row.id,
        ticket_id=ticket.id,
        new_value={"user_id": target_user_id},
    )
    return row


def remove(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    user_id: str | None = None,
) -> None:
    """Unsubscribe `user_id` (defaults to the principal). Idempotent.

    Removing someone other than yourself requires admin.
    """
    target_user_id = user_id or principal.user_id
    if target_user_id != principal.user_id and not principal.is_admin:
        raise PermissionDeniedError("only admins can unsubscribe other users")

    ticket = ticket_service.get(db, principal, ticket_id)

    row = db.scalar(
        select(TicketWatcher).where(
            TicketWatcher.ticket_id == ticket.id,
            TicketWatcher.user_id == target_user_id,
        )
    )
    if row is None:
        return  # idempotent — silent no-op

    db.delete(row)
    db.flush()

    audit_service.record(
        db,
        actor=principal,
        action=TICKET_WATCHER_REMOVED,
        entity_type="ticket_watcher",
        entity_id=row.id,
        ticket_id=ticket.id,
        old_value={"user_id": target_user_id},
    )


def list_for_ticket(
    db: Session,
    principal: Principal,
    ticket_id: str,
) -> list[dict[str, Any]]:
    """List the watchers of a ticket.

    Visibility-gated like every other read: if the principal can't see
    the ticket they get a NotFound. We hydrate the username/email so the
    UI doesn't need a second roundtrip.

    If the `ticket_watchers` table doesn't exist (migration
    `f48a2b1c93e0` not applied), we return an empty list and roll the
    transaction back. The Watch button on the frontend then shows
    "Watch · 0".
    """
    ticket = ticket_service.get(db, principal, ticket_id)
    try:
        rows = db.execute(
            select(
                TicketWatcher.id,
                TicketWatcher.user_id,
                TicketWatcher.created_at,
                User.username,
                User.email,
                User.first_name,
                User.last_name,
            )
            .join(User, User.id == TicketWatcher.user_id)
            .where(TicketWatcher.ticket_id == ticket.id)
            .order_by(TicketWatcher.created_at.asc())
        ).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return []
    return [
        {
            "id": row[0],
            "user_id": row[1],
            "created_at": row[2].isoformat() if row[2] else None,
            "username":   row[3],
            "email":      row[4],
            "display":    " ".join([n for n in (row[5], row[6]) if n]).strip() or row[3] or row[4] or row[1],
        }
        for row in rows
    ]


def watcher_user_ids(db: Session, ticket_id: str) -> set[str]:
    """Internal helper for the notification fan-out — returns the user_ids
    subscribed to this ticket. Bypasses RBAC because the caller is the
    notification task running with system credentials.

    Returns an empty set if the `ticket_watchers` table doesn't exist
    yet (migration `f48a2b1c93e0` not applied) so notification dispatch
    keeps working in environments that haven't migrated.
    """
    try:
        rows = db.execute(
            select(TicketWatcher.user_id).where(TicketWatcher.ticket_id == ticket_id)
        ).all()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return set()
    return {row[0] for row in rows}
