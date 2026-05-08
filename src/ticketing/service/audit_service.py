"""Audit ledger — single entry point for writing immutable audit events."""
from typing import Any

from flask import request as flask_request
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from src.core.correlation import get_correlation_id
from src.core.errors import NotFoundError, PermissionDeniedError
from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing.models import AuditEvent


def _request_metadata() -> tuple[str | None, str | None]:
    try:
        ip = flask_request.headers.get("X-Forwarded-For", flask_request.remote_addr) or None
        ua = flask_request.headers.get("User-Agent")
        return ip, ua
    except Exception:
        return None, None


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
    from src.ticketing.service import ticket_service

    ticket = ticket_service.get(db, principal, ticket_id)
    if not (
        rbac.can_view_global_audit(principal)
        or (ticket.current_sector_code and rbac.can_view_sector_audit(principal, ticket.current_sector_code))
        or rbac.can_view_ticket(principal, ticket)
    ):
        raise NotFoundError("ticket not found")
    limit = max(1, min(limit, 200))
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.ticket_id == ticket.id)
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
