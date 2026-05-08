"""Workflow transitions. Each public function is one atomic UPDATE + audit.

The atomic-UPDATE pattern (architecture §6) prevents double-assignment under
concurrency: if the WHERE clause doesn't match (somebody else already moved the
ticket), the UPDATE returns 0 rows and we raise ConcurrencyConflictError.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from src.core.errors import (
    BusinessRuleError,
    ConcurrencyConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from src.core.spans import set_attr, span
from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing import events as audit_events
from src.ticketing import state_machine as sm
from src.ticketing.models import (
    Sector,
    SectorMembership as ORMSectorMembership,
    Ticket,
    TicketAssignee,
    TicketAssignmentHistory,
    TicketSectorAssignment,
    TicketSectorHistory,
    TicketStatusHistory,
)
from src.ticketing.service import audit_service, sla_service
from src.ticketing.service.ticket_service import _sector_code, _beneficiary_user_id
from src.tasking.producer import publish


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hydrate_for_rbac(db: Session, t: Ticket) -> Ticket:
    setattr(t, "current_sector_code", _sector_code(db, t.current_sector_id))
    setattr(t, "beneficiary_user_id", _beneficiary_user_id(db, t.beneficiary_id))
    return t


def _load(db: Session, ticket_id: str) -> Ticket:
    t = db.get(Ticket, ticket_id)
    if t is None or t.is_deleted:
        raise NotFoundError("ticket not found")
    return _hydrate_for_rbac(db, t)


def _check_visible(p: Principal, t: Ticket) -> None:
    if not rbac.can_view_ticket(p, t):
        # Don't leak existence
        raise NotFoundError("ticket not found")


def _record_status_change(db, t_id, old, new, by, reason):
    db.add(TicketStatusHistory(
        ticket_id=t_id, old_status=old, new_status=new,
        changed_by_user_id=by, reason=reason,
    ))


def _record_sector_change(db, t_id, old, new, by, reason):
    db.add(TicketSectorHistory(
        ticket_id=t_id, old_sector_id=old, new_sector_id=new,
        changed_by_user_id=by, reason=reason,
    ))


def _record_assignment_change(db, t_id, old, new, by, reason):
    db.add(TicketAssignmentHistory(
        ticket_id=t_id, old_assignee_user_id=old, new_assignee_user_id=new,
        changed_by_user_id=by, reason=reason,
    ))


def _denied(action: str, p: Principal, ticket_id: str, db: Session, reason: str) -> None:
    audit_service.record(
        db, actor=p, action=audit_events.ACCESS_DENIED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        metadata={"attempted_action": action, "reason": reason},
    )
    raise PermissionDeniedError(reason)


def _no_returned_row(result) -> bool:
    return result.first() is None


# ── Multi-assignment helpers ─────────────────────────────────────────────────

def _add_sector_assignment(db: Session, ticket_id: str, sector_id: str,
                           *, by_user_id: str | None, primary: bool) -> None:
    """Idempotent add to ``ticket_sectors``; promotes ``primary`` if asked."""
    existing = db.scalar(
        select(TicketSectorAssignment).where(
            TicketSectorAssignment.ticket_id == ticket_id,
            TicketSectorAssignment.sector_id == sector_id,
        )
    )
    if existing is None:
        db.add(TicketSectorAssignment(
            ticket_id=ticket_id, sector_id=sector_id,
            is_primary=primary, added_by_user_id=by_user_id,
        ))
    elif primary and not existing.is_primary:
        existing.is_primary = True
    if primary:
        db.execute(
            update(TicketSectorAssignment)
            .where(
                TicketSectorAssignment.ticket_id == ticket_id,
                TicketSectorAssignment.sector_id != sector_id,
            )
            .values(is_primary=False)
        )


def _add_user_assignment(db: Session, ticket_id: str, user_id: str,
                         *, by_user_id: str | None, primary: bool) -> None:
    existing = db.scalar(
        select(TicketAssignee).where(
            TicketAssignee.ticket_id == ticket_id,
            TicketAssignee.user_id == user_id,
        )
    )
    if existing is None:
        db.add(TicketAssignee(
            ticket_id=ticket_id, user_id=user_id,
            is_primary=primary, added_by_user_id=by_user_id,
        ))
    elif primary and not existing.is_primary:
        existing.is_primary = True
    if primary:
        db.execute(
            update(TicketAssignee)
            .where(
                TicketAssignee.ticket_id == ticket_id,
                TicketAssignee.user_id != user_id,
            )
            .values(is_primary=False)
        )


def _remove_user_assignment(db: Session, ticket_id: str, user_id: str) -> None:
    db.execute(
        TicketAssignee.__table__.delete()
        .where(TicketAssignee.ticket_id == ticket_id, TicketAssignee.user_id == user_id)
    )


def _promote_remaining_assignee(db: Session, ticket_id: str) -> str | None:
    """After removing a primary, pick the oldest remaining assignee (if any)
    and promote them. Returns the new primary user id (or None)."""
    row = db.scalar(
        select(TicketAssignee)
        .where(TicketAssignee.ticket_id == ticket_id)
        .order_by(TicketAssignee.added_at.asc())
        .limit(1)
    )
    if row is None:
        return None
    row.is_primary = True
    return row.user_id


# ── Transitions ──────────────────────────────────────────────────────────────

def assign_sector(db: Session, p: Principal, ticket_id: str, sector_code: str, *, reason: str | None = None) -> Ticket:
    with span("workflow.assign_sector", username=p.username, user_id=p.user_id, ticket_id=ticket_id, sector_code=sector_code) as current:
        ticket = _assign_sector(db, p, ticket_id, sector_code, reason=reason)
        set_attr(current, "ticket.status", ticket.status)
        return ticket


def _assign_sector(db: Session, p: Principal, ticket_id: str, sector_code: str, *, reason: str | None = None) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_assign_sector(p, t):
        _denied(sm.ACTION_ASSIGN_SECTOR, p, ticket_id, db, "not allowed to assign sector")

    if not sm.is_valid(sm.ACTION_ASSIGN_SECTOR, t.status):
        raise BusinessRuleError(f"cannot assign sector while status is {t.status}")

    sector = db.scalar(select(Sector).where(Sector.code == sector_code))
    if sector is None:
        raise BusinessRuleError(f"unknown sector: {sector_code}")
    if not sector.is_active:
        raise BusinessRuleError(f"sector {sector_code} is not active")

    old_sector_id = t.current_sector_id
    new_status = sm.target_status(sm.ACTION_ASSIGN_SECTOR, t.status)

    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.is_deleted.is_(False),
            Ticket.status.in_(tuple(sm._BY_ACTION[sm.ACTION_ASSIGN_SECTOR].from_statuses)),
        )
        .values(
            current_sector_id  = sector.id,
            sector_assigned_at = datetime.now(timezone.utc),
            status             = new_status,
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_sector_change(db, ticket_id, old_sector_id, sector.id, p.user_id, reason)
    _record_status_change(db, ticket_id, t.status, new_status, p.user_id, reason)
    _add_sector_assignment(db, ticket_id, sector.id, by_user_id=p.user_id, primary=True)
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_ASSIGNED_TO_SECTOR,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"current_sector_id": old_sector_id, "status": t.status},
        new_value={"current_sector_id": sector.id, "status": new_status},
        metadata={"reason": reason} if reason else None,
    )
    publish("notify_sector", {"ticket_id": ticket_id, "sector_id": sector.id})
    return _load(db, ticket_id)


def assign_to_me(db: Session, p: Principal, ticket_id: str) -> Ticket:
    with span("workflow.assign_to_me", username=p.username, user_id=p.user_id, ticket_id=ticket_id) as current:
        ticket = _assign_to_me(db, p, ticket_id)
        set_attr(current, "ticket.status", ticket.status)
        set_attr(current, "ticket.assignee_user_id", ticket.assignee_user_id)
        return ticket


def _assign_to_me(db: Session, p: Principal, ticket_id: str) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_assign_to_me(p, t):
        _denied(sm.ACTION_ASSIGN_TO_ME, p, ticket_id, db, "not in this sector")

    # The atomic UPDATE is the source of truth — guards against the concurrency race.
    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.current_sector_id == t.current_sector_id,
            Ticket.is_deleted.is_(False),
            Ticket.assignee_user_id.is_(None),
            Ticket.status.in_(("pending", "assigned_to_sector", "reopened")),
        )
        .values(
            assignee_user_id              = p.user_id,
            last_active_assignee_user_id  = p.user_id,
            status                        = sm.IN_PROGRESS,
            assigned_at                   = datetime.now(timezone.utc),
            first_response_at             = func.coalesce(Ticket.first_response_at, datetime.now(timezone.utc)),
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket already assigned or no longer assignable")

    _record_assignment_change(db, ticket_id, None, p.user_id, p.user_id, None)
    _record_status_change(db, ticket_id, t.status, sm.IN_PROGRESS, p.user_id, None)
    _add_user_assignment(db, ticket_id, p.user_id, by_user_id=p.user_id, primary=True)
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_ASSIGNED_TO_USER,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"assignee_user_id": None, "status": t.status},
        new_value={"assignee_user_id": p.user_id, "status": sm.IN_PROGRESS},
    )
    publish("notify_assignee", {"ticket_id": ticket_id, "user_id": p.user_id})
    return _load(db, ticket_id)


def assign_to_user(db: Session, p: Principal, ticket_id: str, target_user_id: str, *, reason: str | None = None) -> Ticket:
    with span("workflow.assign_to_user", username=p.username, user_id=p.user_id, ticket_id=ticket_id, target_user_id=target_user_id) as current:
        ticket = _assign_to_user(db, p, ticket_id, target_user_id, reason=reason)
        set_attr(current, "ticket.status", ticket.status)
        return ticket


def _assign_to_user(db: Session, p: Principal, ticket_id: str, target_user_id: str, *, reason: str | None = None) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_assign_to_user(p, t):
        _denied(sm.ACTION_ASSIGN_TO_USER, p, ticket_id, db, "not allowed to assign to user")

    # Target must be member or chief of the current sector.
    if t.current_sector_id is None:
        raise BusinessRuleError("ticket has no current sector")

    is_in_sector = db.scalar(
        select(ORMSectorMembership.id).where(
            ORMSectorMembership.user_id == target_user_id,
            ORMSectorMembership.sector_id == t.current_sector_id,
            ORMSectorMembership.is_active.is_(True),
        )
    )
    if is_in_sector is None and not p.is_admin:
        raise BusinessRuleError("target user is not a member of the current sector")

    new_status = sm.target_status(sm.ACTION_ASSIGN_TO_USER, t.status)
    if new_status is None:
        raise BusinessRuleError(f"cannot assign while status is {t.status}")

    old_assignee = t.assignee_user_id

    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.is_deleted.is_(False),
            Ticket.status.in_(tuple(sm._BY_ACTION[sm.ACTION_ASSIGN_TO_USER].from_statuses)),
        )
        .values(
            assignee_user_id             = target_user_id,
            last_active_assignee_user_id = target_user_id,
            status                       = new_status,
            assigned_at                  = datetime.now(timezone.utc),
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_assignment_change(db, ticket_id, old_assignee, target_user_id, p.user_id, reason)
    if t.status != new_status:
        _record_status_change(db, ticket_id, t.status, new_status, p.user_id, reason)
    _add_user_assignment(db, ticket_id, target_user_id, by_user_id=p.user_id, primary=True)
    audit_service.record(
        db, actor=p,
        action=audit_events.TICKET_REASSIGNED if old_assignee else audit_events.TICKET_ASSIGNED_TO_USER,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"assignee_user_id": old_assignee, "status": t.status},
        new_value={"assignee_user_id": target_user_id, "status": new_status},
        metadata={"reason": reason} if reason else None,
    )
    publish("notify_assignee", {"ticket_id": ticket_id, "user_id": target_user_id})
    return _load(db, ticket_id)


def add_sector(db: Session, p: Principal, ticket_id: str, sector_code: str) -> Ticket:
    """Add a *secondary* sector to the ticket without changing its primary."""
    with span("workflow.add_sector", username=p.username, user_id=p.user_id, ticket_id=ticket_id, sector_code=sector_code):
        t = _load(db, ticket_id)
        _check_visible(p, t)
        if not rbac.can_assign_sector(p, t):
            _denied(sm.ACTION_ASSIGN_SECTOR, p, ticket_id, db, "not allowed to add sector")
        sector = db.scalar(select(Sector).where(Sector.code == sector_code))
        if sector is None or not sector.is_active:
            raise BusinessRuleError(f"unknown or inactive sector: {sector_code}")
        already_primary = t.current_sector_id == sector.id
        _add_sector_assignment(db, ticket_id, sector.id, by_user_id=p.user_id, primary=already_primary)
        audit_service.record(
            db, actor=p, action=audit_events.TICKET_ASSIGNED_TO_SECTOR,
            entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
            new_value={"added_sector_id": sector.id, "primary": already_primary},
            metadata={"action": "add_sector"},
        )
        publish("notify_sector", {"ticket_id": ticket_id, "sector_id": sector.id})
        return _load(db, ticket_id)


def remove_sector(db: Session, p: Principal, ticket_id: str, sector_code: str) -> Ticket:
    """Detach a sector. Refuses to remove the *primary* sector — re-route it
    via assign_sector first."""
    with span("workflow.remove_sector", username=p.username, user_id=p.user_id, ticket_id=ticket_id, sector_code=sector_code):
        t = _load(db, ticket_id)
        _check_visible(p, t)
        if not rbac.can_assign_sector(p, t):
            _denied(sm.ACTION_ASSIGN_SECTOR, p, ticket_id, db, "not allowed to remove sector")
        sector = db.scalar(select(Sector).where(Sector.code == sector_code))
        if sector is None:
            raise BusinessRuleError(f"unknown sector: {sector_code}")
        if t.current_sector_id == sector.id:
            raise BusinessRuleError("cannot remove the primary sector — reassign it first")
        db.execute(
            TicketSectorAssignment.__table__.delete()
            .where(
                TicketSectorAssignment.ticket_id == ticket_id,
                TicketSectorAssignment.sector_id == sector.id,
            )
        )
        audit_service.record(
            db, actor=p, action=audit_events.TICKET_ASSIGNED_TO_SECTOR,
            entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
            old_value={"removed_sector_id": sector.id},
            metadata={"action": "remove_sector"},
        )
        return _load(db, ticket_id)


def add_assignee(db: Session, p: Principal, ticket_id: str, user_id: str) -> Ticket:
    """Add a *secondary* assignee. Useful for shared / pair work."""
    with span("workflow.add_assignee", username=p.username, user_id=p.user_id, ticket_id=ticket_id, target_user_id=user_id):
        t = _load(db, ticket_id)
        _check_visible(p, t)
        if not rbac.can_assign_to_user(p, t):
            _denied(sm.ACTION_ASSIGN_TO_USER, p, ticket_id, db, "not allowed to add assignee")
        if t.current_sector_id is None:
            raise BusinessRuleError("ticket has no current sector")
        in_sector = db.scalar(
            select(ORMSectorMembership.id).where(
                ORMSectorMembership.user_id == user_id,
                ORMSectorMembership.sector_id == t.current_sector_id,
                ORMSectorMembership.is_active.is_(True),
            )
        )
        if in_sector is None and not p.is_admin:
            raise BusinessRuleError("target user is not a member of the current sector")
        primary = t.assignee_user_id is None  # promote if there's no primary yet
        _add_user_assignment(db, ticket_id, user_id, by_user_id=p.user_id, primary=primary)
        if primary:
            db.execute(
                update(Ticket)
                .where(Ticket.id == ticket_id)
                .values(assignee_user_id=user_id, last_active_assignee_user_id=user_id)
            )
        audit_service.record(
            db, actor=p, action=audit_events.TICKET_ASSIGNED_TO_USER,
            entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
            new_value={"added_assignee": user_id, "primary": primary},
            metadata={"action": "add_assignee"},
        )
        publish("notify_assignee", {"ticket_id": ticket_id, "user_id": user_id})
        return _load(db, ticket_id)


def remove_assignee(db: Session, p: Principal, ticket_id: str, user_id: str) -> Ticket:
    """Detach a specific user. If they were the primary, promote the next."""
    with span("workflow.remove_assignee", username=p.username, user_id=p.user_id, ticket_id=ticket_id, target_user_id=user_id):
        t = _load(db, ticket_id)
        _check_visible(p, t)
        is_self = (user_id == p.user_id)
        is_chief = bool(t.current_sector_code and p.is_chief_of(t.current_sector_code))
        if not (is_self or p.is_admin or is_chief):
            _denied("remove_assignee", p, ticket_id, db, "not allowed to remove this assignee")

        _remove_user_assignment(db, ticket_id, user_id)
        if t.assignee_user_id == user_id:
            new_primary = _promote_remaining_assignee(db, ticket_id)
            db.execute(
                update(Ticket)
                .where(Ticket.id == ticket_id)
                .values(
                    assignee_user_id=new_primary,
                    status=t.status if new_primary else sm.target_status(sm.ACTION_UNASSIGN, t.status) or t.status,
                )
            )
            publish("notify_unassigned", {
                "ticket_id":        ticket_id,
                "previous_user_id": user_id,
                "actor_user_id":    p.user_id,
            })
        audit_service.record(
            db, actor=p, action=audit_events.TICKET_UNASSIGNED,
            entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
            old_value={"removed_assignee": user_id},
            metadata={"action": "remove_assignee", "self": is_self},
        )
        return _load(db, ticket_id)


def change_status(
    db: Session,
    p: Principal,
    ticket_id: str,
    target_status: str,
    *,
    reason: str | None = None,
) -> Ticket:
    """Convenience wrapper that maps a target status to the right transition.

    The frontend can call this for any allowed transition without having to
    pick the specific endpoint (assign-sector, mark-done, …) — easier to wire
    up an inline status switcher.
    """
    with span("workflow.change_status", username=p.username, user_id=p.user_id, ticket_id=ticket_id, target_status=target_status):
        t = _load(db, ticket_id)
        _check_visible(p, t)

        # Operator-side transitions require the caller to actually be working
        # the ticket (or be admin / sector chief). Close / reopen / cancel use
        # their own predicates further down.
        if target_status in (sm.IN_PROGRESS, sm.ASSIGNED_TO_SECTOR, sm.DONE):
            if not rbac.can_drive_status(p, t):
                _denied("change_status", p, ticket_id, db, "not allowed to drive ticket status")

        if target_status == sm.IN_PROGRESS:
            return _assign_to_me(db, p, ticket_id)
        if target_status == sm.ASSIGNED_TO_SECTOR:
            return _unassign(db, p, ticket_id, reason=reason)
        if target_status == sm.DONE:
            return _mark_done(db, p, ticket_id, resolution=reason)
        if target_status == sm.CLOSED:
            return _close(db, p, ticket_id)
        if target_status == sm.REOPENED:
            if not reason:
                raise BusinessRuleError("reopen requires a reason")
            return _reopen(db, p, ticket_id, reason=reason)
        if target_status == sm.CANCELLED:
            if not reason:
                raise BusinessRuleError("cancel requires a reason")
            return _cancel(db, p, ticket_id, reason=reason)
        raise BusinessRuleError(f"no transition wired up for status {target_status!r}")


def unassign(db: Session, p: Principal, ticket_id: str, *, reason: str | None = None) -> Ticket:
    """Clear the current assignee.

    Anyone may unassign themselves; admins and the current sector chief may
    unassign anyone. The ticket falls back to ``assigned_to_sector`` so it
    is visible in the sector queue and can be picked up again.
    """
    with span("workflow.unassign", username=p.username, user_id=p.user_id, ticket_id=ticket_id):
        return _unassign(db, p, ticket_id, reason=reason)


def _unassign(db: Session, p: Principal, ticket_id: str, *, reason: str | None = None) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)

    if t.assignee_user_id is None:
        return t  # idempotent

    # RBAC: self-unassign always allowed; otherwise require admin or sector chief.
    is_self = t.assignee_user_id == p.user_id
    is_chief = bool(t.current_sector_code and p.is_chief_of(t.current_sector_code))
    if not (is_self or p.is_admin or is_chief):
        _denied("unassign", p, ticket_id, db, "not allowed to unassign this ticket")

    new_status = sm.target_status(sm.ACTION_UNASSIGN, t.status)
    if new_status is None:
        # Fall back to current status if transition not defined.
        new_status = t.status

    old_assignee = t.assignee_user_id
    # Remove from the join table first; if there are still other assignees,
    # promote the oldest remaining one as the new primary instead of dropping
    # back to "no assignee".
    _remove_user_assignment(db, ticket_id, old_assignee)
    new_primary = _promote_remaining_assignee(db, ticket_id)

    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.is_deleted.is_(False),
            Ticket.assignee_user_id == old_assignee,
        )
        .values(
            assignee_user_id=new_primary,
            status=new_status if new_primary is None else sm.IN_PROGRESS,
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_assignment_change(db, ticket_id, old_assignee, None, p.user_id, reason)
    if t.status != new_status:
        _record_status_change(db, ticket_id, t.status, new_status, p.user_id, reason)
    audit_service.record(
        db, actor=p,
        action=audit_events.TICKET_UNASSIGNED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"assignee_user_id": old_assignee, "status": t.status},
        new_value={"assignee_user_id": None, "status": new_status},
        metadata={"reason": reason, "self": is_self} if reason or is_self else None,
    )
    publish("notify_unassigned", {
        "ticket_id":        ticket_id,
        "previous_user_id": old_assignee,
        "actor_user_id":    p.user_id,
    })
    return _load(db, ticket_id)


def mark_done(db: Session, p: Principal, ticket_id: str, *, resolution: str | None = None) -> Ticket:
    with span("workflow.mark_done", username=p.username, user_id=p.user_id, ticket_id=ticket_id) as current:
        ticket = _mark_done(db, p, ticket_id, resolution=resolution)
        set_attr(current, "ticket.status", ticket.status)
        return ticket


def _mark_done(db: Session, p: Principal, ticket_id: str, *, resolution: str | None = None) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_mark_done(p, t):
        _denied(sm.ACTION_MARK_DONE, p, ticket_id, db, "not the assignee")

    new_status = sm.target_status(sm.ACTION_MARK_DONE, t.status)
    if new_status is None:
        raise BusinessRuleError(f"cannot mark done while status is {t.status}")

    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.is_deleted.is_(False),
            Ticket.status.in_(tuple(sm._BY_ACTION[sm.ACTION_MARK_DONE].from_statuses)),
        )
        .values(
            status     = new_status,
            done_at    = datetime.now(timezone.utc),
            resolution = resolution or t.resolution,
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_status_change(db, ticket_id, t.status, new_status, p.user_id, None)
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_DONE,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"status": t.status}, new_value={"status": new_status},
    )
    publish("notify_beneficiary", {"ticket_id": ticket_id, "actor_user_id": p.user_id})
    return _load(db, ticket_id)


def close(db: Session, p: Principal, ticket_id: str, *, feedback: dict | None = None) -> Ticket:
    with span("workflow.close", username=p.username, user_id=p.user_id, ticket_id=ticket_id) as current:
        ticket = _close(db, p, ticket_id, feedback=feedback)
        set_attr(current, "ticket.status", ticket.status)
        return ticket


def _close(db: Session, p: Principal, ticket_id: str, *, feedback: dict | None = None) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not (rbac.can_close(p, t) or rbac.can_drive_status(p, t)):
        _denied(sm.ACTION_CLOSE, p, ticket_id, db, "only the beneficiary, admin or assignee can close")

    new_status = sm.target_status(sm.ACTION_CLOSE, t.status)
    if new_status is None:
        raise BusinessRuleError(f"cannot close while status is {t.status}")

    res = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status == "done", Ticket.is_deleted.is_(False))
        .values(status=new_status, closed_at=datetime.now(timezone.utc))
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_status_change(db, ticket_id, t.status, new_status, p.user_id, None)
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_CLOSED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"status": t.status}, new_value={"status": new_status},
        metadata={"feedback": feedback} if feedback else None,
    )
    publish("notify_beneficiary", {"ticket_id": ticket_id, "actor_user_id": p.user_id})
    return _load(db, ticket_id)


def reopen(db: Session, p: Principal, ticket_id: str, *, reason: str) -> Ticket:
    with span("workflow.reopen", username=p.username, user_id=p.user_id, ticket_id=ticket_id) as current:
        ticket = _reopen(db, p, ticket_id, reason=reason)
        set_attr(current, "ticket.status", ticket.status)
        set_attr(current, "ticket.reopened_count", ticket.reopened_count)
        return ticket


def _reopen(db: Session, p: Principal, ticket_id: str, *, reason: str) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_reopen(p, t):
        _denied(sm.ACTION_REOPEN, p, ticket_id, db, "only the beneficiary or admin can reopen")
    if not (reason or "").strip():
        raise BusinessRuleError("reason is required to reopen")

    new_status = sm.target_status(sm.ACTION_REOPEN, t.status)
    if new_status is None:
        raise BusinessRuleError(f"cannot reopen while status is {t.status}")

    target_assignee = t.last_active_assignee_user_id
    res = db.execute(
        update(Ticket)
        .where(Ticket.id == ticket_id, Ticket.status.in_(("done", "closed")), Ticket.is_deleted.is_(False))
        .values(
            status            = new_status,
            assignee_user_id  = target_assignee,
            reopened_at       = datetime.now(timezone.utc),
            reopened_count    = Ticket.reopened_count + 1,
            closed_at         = None,
            done_at           = None,
        )
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_status_change(db, ticket_id, t.status, new_status, p.user_id, reason)
    if target_assignee != t.assignee_user_id:
        _record_assignment_change(db, ticket_id, t.assignee_user_id, target_assignee, p.user_id, "reopen")
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_REOPENED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"status": t.status, "assignee_user_id": t.assignee_user_id},
        new_value={"status": new_status, "assignee_user_id": target_assignee},
        metadata={"reason": reason},
    )
    if target_assignee:
        publish("notify_assignee", {"ticket_id": ticket_id, "user_id": target_assignee})
    return _load(db, ticket_id)


def cancel(db: Session, p: Principal, ticket_id: str, *, reason: str) -> Ticket:
    with span("workflow.cancel", username=p.username, user_id=p.user_id, ticket_id=ticket_id) as current:
        ticket = _cancel(db, p, ticket_id, reason=reason)
        set_attr(current, "ticket.status", ticket.status)
        return ticket


def _cancel(db: Session, p: Principal, ticket_id: str, *, reason: str) -> Ticket:
    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_cancel(p, t):
        _denied(sm.ACTION_CANCEL, p, ticket_id, db, "not allowed to cancel")
    if not (reason or "").strip():
        raise BusinessRuleError("reason is required to cancel")

    new_status = sm.target_status(sm.ACTION_CANCEL, t.status)
    if new_status is None:
        raise BusinessRuleError(f"cannot cancel while status is {t.status}")

    res = db.execute(
        update(Ticket)
        .where(
            Ticket.id == ticket_id,
            Ticket.status.in_(tuple(sm._BY_ACTION[sm.ACTION_CANCEL].from_statuses)),
            Ticket.is_deleted.is_(False),
        )
        .values(status=new_status)
        .returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("ticket state changed; refresh and retry")

    _record_status_change(db, ticket_id, t.status, new_status, p.user_id, reason)
    audit_service.record(
        db, actor=p, action=audit_events.TICKET_CANCELLED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"status": t.status}, new_value={"status": new_status},
        metadata={"reason": reason},
    )
    publish("notify_beneficiary", {"ticket_id": ticket_id, "actor_user_id": p.user_id})
    return _load(db, ticket_id)


def change_priority(db: Session, p: Principal, ticket_id: str, priority: str, *, reason: str | None = None) -> Ticket:
    with span("workflow.change_priority", username=p.username, user_id=p.user_id, ticket_id=ticket_id, priority=priority) as current:
        ticket = _change_priority(db, p, ticket_id, priority, reason=reason)
        set_attr(current, "ticket.priority", ticket.priority)
        return ticket


def _change_priority(db: Session, p: Principal, ticket_id: str, priority: str, *, reason: str | None = None) -> Ticket:
    if priority not in ("low", "medium", "high", "critical"):
        raise BusinessRuleError(f"invalid priority: {priority}")

    t = _load(db, ticket_id)
    _check_visible(p, t)
    if not rbac.can_change_priority(p, t):
        _denied("change_priority", p, ticket_id, db, "not allowed to change priority")

    if t.priority == priority:
        return t

    res = db.execute(
        update(Ticket).where(Ticket.id == ticket_id, Ticket.priority == t.priority)
        .values(priority=priority).returning(Ticket.id)
    )
    if _no_returned_row(res):
        raise ConcurrencyConflictError("priority changed; refresh and retry")

    # Reload and evaluate SLA
    t = _load(db, ticket_id)
    sla_service.evaluate_sla(db, t)
    db.add(t)

    audit_service.record(
        db, actor=p, action=audit_events.TICKET_PRIORITY_CHANGED,
        entity_type="ticket", entity_id=ticket_id, ticket_id=ticket_id,
        old_value={"priority": t.priority}, new_value={"priority": priority},
        metadata={"reason": reason} if reason else None,
    )
    return _load(db, ticket_id)
