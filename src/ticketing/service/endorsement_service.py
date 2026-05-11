"""Supplementary endorsements ("avizare suplimentară").

Lifecycle:
    1. Active assignee files a request, optionally targeted at a specific
       avizator user. If `assigned_to_user_id` is None, the request lands
       in the pool — every `tickora_avizator` sees it.
    2. An avizator approves or rejects. The decision is recorded
       (`decided_by_user_id`, `decided_at`, `decision_reason`) and the
       endorsement's `status` flips to `approved` / `rejected`.
    3. While any endorsement on a ticket is `pending`, the workflow
       service refuses `mark_done` and `close` — see
       `workflow_service._require_no_pending_endorsements`.

The service writes audit events + a system comment for every state
change so the ticket timeline tells the full story.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.common.errors import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.iam import rbac
from src.iam.models import User
from src.iam.principal import Principal
from src.audit import events as audit_events
from src.audit import service as audit_service
from src.ticketing.models import Ticket, TicketComment, TicketEndorsement
from src.ticketing.service import ticket_service

VALID_STATUSES = ("pending", "approved", "rejected")


# ── Public API ───────────────────────────────────────────────────────────────

def request(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    reason: str | None = None,
    assigned_to_user_id: str | None = None,
) -> TicketEndorsement:
    """File a new endorsement request on `ticket_id`.

    The caller must be the active assignee (or admin). A `None`
    `assigned_to_user_id` becomes a pool request — any avizator can act
    on it.
    """
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_request_endorsement(principal, ticket):
        audit_service.record(
            db, actor=principal, action=audit_events.ACCESS_DENIED,
            entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
            metadata={"attempted_action": "endorsement.request"},
        )
        raise PermissionDeniedError(
            "only the active assignee can request a supplementary endorsement"
        )

    if assigned_to_user_id:
        target = db.get(User, assigned_to_user_id)
        if target is None or not target.is_active:
            raise ValidationError("assigned_to_user_id is unknown or inactive")

    row = TicketEndorsement(
        ticket_id=ticket.id,
        requested_by_user_id=principal.user_id,
        assigned_to_user_id=assigned_to_user_id or None,
        status="pending",
        request_reason=(reason or "").strip() or None,
    )
    db.add(row)
    db.flush()

    # Public system comment so beneficiaries see "endorsement requested"
    # on the timeline; private metadata (target user) stays in the
    # endorsement record itself.
    _system_comment(db, principal, ticket.id, kind="endorsement_requested", payload={
        "endorsement_id": row.id,
        "actor_user_id":  principal.user_id,
        "actor_username": principal.username,
        "assigned_to_user_id": assigned_to_user_id,
        "reason": row.request_reason,
    })
    audit_service.record(
        db, actor=principal, action=audit_events.ENDORSEMENT_REQUESTED,
        entity_type="ticket_endorsement", entity_id=row.id, ticket_id=ticket.id,
        new_value={
            "status": "pending",
            "assigned_to_user_id": assigned_to_user_id,
            "reason": row.request_reason,
        },
    )
    return row


def decide(
    db: Session,
    principal: Principal,
    endorsement_id: str,
    *,
    decision: str,
    reason: str | None = None,
) -> TicketEndorsement:
    """Approve or reject a pending endorsement."""
    if decision not in ("approved", "rejected"):
        raise ValidationError("decision must be 'approved' or 'rejected'")

    row = db.get(TicketEndorsement, endorsement_id)
    if row is None:
        raise NotFoundError("endorsement not found")
    if row.status != "pending":
        raise BusinessRuleError("endorsement is no longer pending")

    if not rbac.can_decide_endorsement(principal, row):
        audit_service.record(
            db, actor=principal, action=audit_events.ACCESS_DENIED,
            entity_type="ticket_endorsement", entity_id=row.id, ticket_id=row.ticket_id,
            metadata={"attempted_action": f"endorsement.{decision}"},
        )
        raise PermissionDeniedError("not allowed to decide this endorsement")

    # Pool requests get auto-claimed at decision time so the audit trail
    # shows exactly who acted, even though the request wasn't targeted.
    if row.assigned_to_user_id is None:
        row.assigned_to_user_id = principal.user_id

    row.status            = decision
    row.decided_by_user_id = principal.user_id
    row.decided_at        = datetime.now(timezone.utc)
    row.decision_reason   = (reason or "").strip() or None
    db.flush()

    _system_comment(db, principal, row.ticket_id,
                    kind=f"endorsement_{decision}",
                    payload={
                        "endorsement_id": row.id,
                        "actor_user_id":  principal.user_id,
                        "actor_username": principal.username,
                        "reason":         row.decision_reason,
                    })
    action = (
        audit_events.ENDORSEMENT_APPROVED if decision == "approved"
        else audit_events.ENDORSEMENT_REJECTED
    )
    audit_service.record(
        db, actor=principal, action=action,
        entity_type="ticket_endorsement", entity_id=row.id, ticket_id=row.ticket_id,
        new_value={
            "status": decision,
            "decided_by_user_id": principal.user_id,
            "reason": row.decision_reason,
        },
    )
    return row


def list_for_ticket(
    db: Session, principal: Principal, ticket_id: str,
) -> list[TicketEndorsement]:
    """All endorsements on a single ticket. Visibility-checked via the ticket."""
    ticket_service.get(db, principal, ticket_id)
    return list(db.scalars(
        select(TicketEndorsement)
        .where(TicketEndorsement.ticket_id == ticket_id)
        .order_by(TicketEndorsement.created_at.desc())
    ))


def inbox(
    db: Session,
    principal: Principal,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[tuple[TicketEndorsement, Ticket]]:
    """Avizator inbox: pending pool + pending direct-to-me, plus recent
    history of decisions the principal made (when ``status`` is set).
    Admins see everything regardless of assignment."""
    if not (principal.is_admin or principal.is_avizator):
        raise PermissionDeniedError("avizator role required")
    limit = max(1, min(limit, 200))

    stmt = (
        select(TicketEndorsement, Ticket)
        .join(Ticket, Ticket.id == TicketEndorsement.ticket_id)
        .where(Ticket.is_deleted.is_(False))
        .order_by(TicketEndorsement.created_at.desc())
        .limit(limit)
    )
    if status:
        if status not in VALID_STATUSES:
            raise ValidationError(f"invalid status: {status}")
        stmt = stmt.where(TicketEndorsement.status == status)

    if not principal.is_admin:
        # Avizator scope: pool (assigned_to NULL) + direct assignments to me
        # + decisions I personally made (so the "recently decided" view
        # surfaces what the user just acted on).
        stmt = stmt.where(
            (TicketEndorsement.assigned_to_user_id.is_(None))
            | (TicketEndorsement.assigned_to_user_id == principal.user_id)
            | (TicketEndorsement.decided_by_user_id == principal.user_id)
        )

    return list(db.execute(stmt).all())


def has_pending(db: Session, ticket_id: str) -> bool:
    """Workflow guard: true if any endorsement on `ticket_id` is still pending."""
    count = db.scalar(
        select(func.count(TicketEndorsement.id))
        .where(
            TicketEndorsement.ticket_id == ticket_id,
            TicketEndorsement.status == "pending",
        )
    )
    return bool(count)


def avizator_can_view_ticket(db: Session, principal: Principal, ticket_id: str) -> bool:
    """True if the principal is an avizator and at least one endorsement on
    this ticket is pool or directly assigned to them."""
    if not principal.is_avizator:
        return False
    return bool(db.scalar(
        select(func.count(TicketEndorsement.id))
        .where(
            TicketEndorsement.ticket_id == ticket_id,
            (TicketEndorsement.assigned_to_user_id.is_(None))
            | (TicketEndorsement.assigned_to_user_id == principal.user_id)
            | (TicketEndorsement.decided_by_user_id == principal.user_id),
        )
    ))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _system_comment(db: Session, principal: Principal, ticket_id: str, *, kind: str, payload: dict[str, Any]) -> None:
    body = json.dumps({"kind": kind, **payload}, ensure_ascii=False)
    db.add(TicketComment(
        ticket_id=ticket_id,
        author_user_id=principal.user_id,
        visibility="public",
        comment_type="system",
        body=body,
    ))
