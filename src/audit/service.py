"""Audit ledger — single entry point for writing immutable audit events.

Module dependencies (the boundary that lets `src/audit/` ship as a
microservice):

  * `src.core` — `db`, `errors`, `correlation`. Required.
  * `src.iam`  — `rbac` predicates + `Principal`. Required.
  * `src.common.request_metadata` — for trusted-proxy IP extraction.
    Required (but `src.common` is a self-contained companion package).
  * **No coupling to `src.ticketing`.** Per-ticket visibility checks
    used to import `ticket_service.get` directly; that's now an
    injectable resolver (see `set_ticket_resolver` below). The host
    module registers it at boot.

A microservice extraction needs to:
  1. Copy `src/audit/`, `src/core/`, `src/common/`, `src/iam/`, and the
     migrations that own `audit_events` (and `users`, since `actor_user_id`
     references it).
  2. Either drop the `tickets.id` foreign key in the audit migration
     (so audit rows survive without the tickets table), or also bring
     a minimal `tickets` table.
  3. Optionally call `set_ticket_resolver(your_resolver)` if the new
     service still wants ticket-scoped visibility on
     `GET /api/tickets/<id>/audit`. Without it, only global / sector
     visibility checks apply.
"""
from typing import Any, Callable, Optional, Protocol

from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from src.core.correlation import get_correlation_id
from src.core.errors import NotFoundError, PermissionDeniedError
from src.iam import rbac
from src.iam.principal import Principal
from src.audit.models import AuditEvent


# ── Pluggable ticket resolver (decouples audit from ticketing) ──────────────
#
# `get_for_ticket` needs to look at the ticket to evaluate sector / global
# audit visibility. Rather than importing `ticket_service` (which would
# pull all of `src/ticketing/` into the audit module's import graph), we
# accept a resolver function the host registers at boot.

class _TicketLike(Protocol):
    """Minimum shape required from the resolver's return value."""
    id: str
    current_sector_code: Optional[str]


TicketResolver = Callable[[Session, Principal, str], "_TicketLike"]

_ticket_resolver: TicketResolver | None = None


def set_ticket_resolver(resolver: TicketResolver | None) -> None:
    """Register a resolver. In the modulith, `ticketing` does this at
    import time. In a standalone audit microservice, you can leave it
    unset — `get_for_ticket` then degrades to global / actor-side checks
    only.
    """
    global _ticket_resolver
    _ticket_resolver = resolver


def _resolve_ticket(db: Session, principal: Principal, ticket_id: str):
    if _ticket_resolver is None:
        return None
    try:
        return _ticket_resolver(db, principal, ticket_id)
    except NotFoundError:
        # Re-raise so the caller still gets a 404 — the resolver is the
        # canonical visibility check when it's wired up.
        raise


def _request_metadata() -> tuple[str | None, str | None]:
    # Delegate to the shared helper so X-Forwarded-For trust is consistent
    # everywhere (audit + ticket creation). See `src/core/request_metadata`.
    from src.common.request_metadata import request_metadata
    return request_metadata()


def record(
    db: Session,
    *,
    actor: Principal | None,
    action: str,
    entity_type: str,
    entity_id: str | None = None,
    ticket_id: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    ip, ua = _request_metadata()
    evt = AuditEvent(
        actor_user_id          = actor.user_id          if actor else None,
        actor_keycloak_subject = actor.keycloak_subject if actor else None,
        actor_username         = actor.username         if actor else None,
        action      = action,
        entity_type = entity_type,
        entity_id   = entity_id,
        ticket_id   = ticket_id,
        old_value   = old_value,
        new_value   = new_value,
        audit_metadata = metadata,
        request_ip  = ip,
        user_agent  = ua,
        correlation_id = get_correlation_id(),
    )
    db.add(evt)
    db.flush()
    return evt


def list_(
    db: Session,
    principal: Principal,
    *,
    action: str | None = None,
    actor_user_id: str | None = None,
    actor_username: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ticket_id: str | None = None,
    correlation_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    sort_by: str = "created_at",
    sort_dir: str = "desc",
    limit: int = 100,
) -> list[AuditEvent]:
    if not rbac.can_view_global_audit(principal):
        raise PermissionDeniedError("not allowed to view global audit")
    limit = max(1, min(limit, 200))
    stmt = select(AuditEvent)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if actor_user_id:
        stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
    if actor_username:
        stmt = stmt.where(AuditEvent.actor_username.ilike(f"%{actor_username}%"))
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if ticket_id:
        stmt = stmt.where(AuditEvent.ticket_id == ticket_id)
    if correlation_id:
        stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
    if created_after:
        stmt = stmt.where(AuditEvent.created_at >= created_after)
    if created_before:
        stmt = stmt.where(AuditEvent.created_at < created_before)

    col = getattr(AuditEvent, sort_by, AuditEvent.created_at)
    order = desc(col) if sort_dir == "desc" else asc(col)
    
    return list(db.scalars(stmt.order_by(order, desc(AuditEvent.id)).limit(limit)))


def get_for_ticket(db: Session, principal: Principal, ticket_id: str, *, limit: int = 100) -> list[AuditEvent]:
    """Return the audit timeline for one ticket.

    Visibility precedence:
      1. Global auditor / admin → always.
      2. Resolver hit → run sector + ticket-visibility checks against the
         resolved ticket. This is the standard modulith path.
      3. No resolver registered → fall back to "you must be a global
         auditor to read per-ticket audit". Microservice-mode default.
    """
    if rbac.can_view_global_audit(principal):
        ticket_obj_id = ticket_id
    else:
        ticket = _resolve_ticket(db, principal, ticket_id)
        if ticket is None:
            # Standalone audit service: refuse rather than leak.
            raise PermissionDeniedError(
                "per-ticket audit requires a ticket resolver "
                "(audit.service.set_ticket_resolver) or global audit role"
            )
        if not (
            (ticket.current_sector_code and rbac.can_view_sector_audit(principal, ticket.current_sector_code))
            or rbac.can_view_ticket(principal, ticket)
        ):
            raise NotFoundError("ticket not found")
        ticket_obj_id = ticket.id

    limit = max(1, min(limit, 200))
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.ticket_id == ticket_obj_id)
        .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        .limit(limit)
    )
    return list(db.scalars(stmt))


def get_for_user(db: Session, principal: Principal, user_id: str, *, limit: int = 100) -> list[AuditEvent]:
    if not rbac.can_view_global_audit(principal):
        raise PermissionDeniedError("not allowed to view user audit")
    limit = max(1, min(limit, 200))
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.actor_user_id == user_id)
        .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
        .limit(limit)
    )
    return list(db.scalars(stmt))
