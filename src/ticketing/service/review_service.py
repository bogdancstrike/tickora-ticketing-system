"""Distributor review flow for ticket triage metadata and routing."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.core.errors import PermissionDeniedError, ValidationError
from src.common.spans import set_attr, span
from src.iam.principal import Principal
from src.ticketing import events
from src.ticketing.models import Ticket
from src.ticketing.service import audit_service, comment_service, ticket_service, workflow_service

ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}


def review(db: Session, principal: Principal, ticket_id: str, payload: dict[str, Any]) -> Ticket:
    with span("ticket.review", username=principal.username, user_id=principal.user_id, ticket_id=ticket_id) as current:
        if not (principal.is_admin or principal.is_distributor):
            raise PermissionDeniedError("only distributors or admins can review tickets")

        ticket = ticket_service.get(db, principal, ticket_id)
        old_metadata = {
            "category": ticket.category,
            "type": ticket.type,
            "priority": ticket.priority,
        }

        changed: dict[str, dict[str, str | None]] = {}
        category = _clean(payload.get("category"))
        ticket_type = _clean(payload.get("type"))
        priority = _clean(payload.get("priority"))

        if "category" in payload and category != ticket.category:
            changed["category"] = {"old": ticket.category, "new": category}
            ticket.category = category
        if "type" in payload and ticket_type != ticket.type:
            changed["type"] = {"old": ticket.type, "new": ticket_type}
            ticket.type = ticket_type
        if priority:
            if priority not in ALLOWED_PRIORITIES:
                raise ValidationError("priority must be low, medium, high, or critical")
            if priority != ticket.priority:
                ticket = workflow_service.change_priority(
                    db,
                    principal,
                    ticket_id,
                    priority,
                    reason=payload.get("reason"),
                )

        if changed:
            db.flush()
            audit_service.record(
                db,
                actor=principal,
                action=events.TICKET_UPDATED,
                entity_type="ticket",
                entity_id=ticket_id,
                ticket_id=ticket_id,
                old_value=old_metadata,
                new_value={**old_metadata, **{field: data["new"] for field, data in changed.items()}},
                metadata={"review_changes": changed},
            )

        sector_code = _clean(payload.get("sector_code"))
        if sector_code and sector_code != getattr(ticket, "current_sector_code", None):
            ticket = workflow_service.assign_sector(
                db,
                principal,
                ticket_id,
                sector_code,
                reason=payload.get("reason"),
            )

        assignee_user_id = _clean(payload.get("assignee_user_id"))
        if assignee_user_id:
            # Distributors (reviewers) only route to a sector — picking a specific
            # user is a sector-level action reserved for chiefs and admins. This
            # prevents distributors from cherry-picking individual operators
            # before the sector chief has had a chance to balance workload.
            target_sector = sector_code or getattr(ticket, "current_sector_code", None)
            if not (principal.is_admin or (target_sector and principal.is_chief_of(target_sector))):
                raise PermissionDeniedError(
                    "distributors may only assign sectors during review; "
                    "user-level assignment is performed by the sector chief"
                )
            ticket = workflow_service.assign_to_user(
                db,
                principal,
                ticket_id,
                assignee_user_id,
                reason=payload.get("reason"),
            )

        comment_body = _clean(payload.get("private_comment"))
        if comment_body:
            comment_service.create(
                db,
                principal,
                ticket_id,
                body=comment_body,
                visibility="private",
            )

        if payload.get("close"):
            # Distributor decided to close the ticket prematurely during review
            ticket = workflow_service.cancel(
                db,
                principal,
                ticket_id,
                reason=payload.get("reason") or "Closed prematurely during review",
            )

        ticket = ticket_service.get(db, principal, ticket_id)
        set_attr(current, "ticket.status", ticket.status)
        set_attr(current, "ticket.priority", ticket.priority)
        set_attr(current, "ticket.current_sector_code", getattr(ticket, "current_sector_code", None))
        set_attr(current, "ticket.assignee_user_id", ticket.assignee_user_id)
        return ticket


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None
