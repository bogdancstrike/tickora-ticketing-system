"""Ticket HTTP endpoints. Thin controllers → service."""
from flask import request as flask_request
from pydantic import ValidationError as PydValidationError

from src.core.db import get_db
from src.core.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
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
    raw = _payload()
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
        items, next_cursor = ticket_service.list_(
            db, principal,
            filters={
                k: v for k, v in q.model_dump(mode="json").items()
                if k not in ("cursor", "limit") and v is not None
            },
            cursor_token=q.cursor,
            limit=q.limit,
        )
        return (list_response(items, principal, next_cursor), 200)


@require_authenticated
def get_ticket(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        t = ticket_service.get(db, principal, ticket_id)
        return (serialize_ticket(t, principal), 200)
