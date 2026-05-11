"""Ticket HTTP endpoints. Thin controllers → service."""
from flask import request as flask_request
from pydantic import ValidationError as PydValidationError

from src.config import Config
from src.common import rate_limiter
from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.audit import events as audit_events
from src.audit import service as audit_service
from src.ticketing.schemas import CreateTicketIn, ListTicketsQuery
from src.ticketing.serializers import list_response, serialize_ticket
from src.ticketing.service import ticket_service


def _payload() -> dict:
    data = flask_request.get_json(force=True, silent=True)
    return data or {}


def _qs() -> dict:
    return {k: v for k, v in flask_request.args.items()}


@require_authenticated
def create(app, operation, request, *, principal: Principal, **kwargs):
    # Throttle ticket creation to keep noisy clients (and abusive externals)
    # from drowning the triage queue. Authenticated users are bucketed by
    # their stable `user_id`; the limiter is fail-open if Redis is down so
    # that a Redis blackout never converts into a write outage.
    rate_limiter.check(
        bucket="ticket_create",
        identity=principal.user_id or "anon",
        limit=Config.RATE_LIMIT_TICKET_CREATE_PER_MIN,
        window_s=60,
    )
    raw = _payload()
    raw.setdefault(
        "beneficiary_type",
        "external" if principal.user_type == "external" else "internal",
    )
    try:
        body = CreateTicketIn(**raw)
    except PydValidationError as e:
        raise ValidationError("invalid payload", details={"errors": e.errors()})

    payload = body.model_dump(mode="json")
    with get_db() as db:
        t = ticket_service.create(db, principal, payload)
        # Hydrate fields used by the serializer
        from src.ticketing.service.ticket_service import _sector_code, _beneficiary_user_id
        setattr(t, "current_sector_code", _sector_code(db, t.current_sector_id))
        setattr(t, "beneficiary_user_id", _beneficiary_user_id(db, t.beneficiary_id))
        return (serialize_ticket(t, principal), 201)


@require_authenticated
def list_tickets(app, operation, request, *, principal: Principal, **kwargs):
    try:
        q = ListTicketsQuery(**_qs())
    except PydValidationError as e:
        raise ValidationError("invalid query", details={"errors": e.errors()})

    with get_db() as db:
        items, next_cursor, total = ticket_service.list_(
            db, principal,
            filters={
                k: v for k, v in q.model_dump(mode="json").items()
                if k not in ("cursor", "limit", "offset") and v is not None
            },
            cursor_token=q.cursor,
            limit=q.limit,
            offset=q.offset,
        )
        return (list_response(items, principal, next_cursor, total), 200)


@require_authenticated
def get_ticket(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        t = ticket_service.get(db, principal, ticket_id)
        # Audit every successful detail view. `ticket_service.get` already
        # enforces visibility (404 on hidden tickets), so an event here is
        # guaranteed to belong to a viewer that was actually allowed to
        # read the row. No client-side dedupe — the user wants every view
        # recorded for forensics.
        audit_service.record(
            db,
            actor=principal,
            action=audit_events.TICKET_VIEWED,
            entity_type="ticket",
            entity_id=t.id,
            ticket_id=t.id,
            metadata={"status": t.status},
        )
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def update(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    payload = _payload()
    with get_db() as db:
        t = ticket_service.update(db, principal, ticket_id, payload)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def delete_ticket(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        ticket_service.delete(db, principal, ticket_id)
        return ("", 204)
