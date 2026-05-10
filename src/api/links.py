"""Ticket-link endpoints (Phase 7).

```
GET    /api/tickets/<ticket_id>/links     — list incoming + outgoing
POST   /api/tickets/<ticket_id>/links     — body: { target_ticket_id, link_type }
DELETE /api/links/<link_id>               — remove
```

The service layer enforces RBAC: you can only add/remove links from a
ticket you can modify, and only against a target ticket you can see.
"""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import link_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _ticket_id(kwargs: dict) -> str:
    tid = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    if not tid:
        raise ValidationError("ticket_id is required")
    return tid


@require_authenticated
def list_links(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        items = link_service.list_for_ticket(db, principal, _ticket_id(kwargs))
        return ({"items": items}, 200)


@require_authenticated
def add_link(app, operation, request, *, principal: Principal, **kwargs):
    body = _payload()
    target = body.get("target_ticket_id")
    link_type = body.get("link_type")
    if not target or not link_type:
        raise ValidationError("target_ticket_id and link_type are required")
    with get_db() as db:
        row = link_service.add(
            db, principal,
            source_ticket_id=_ticket_id(kwargs),
            target_ticket_id=target,
            link_type=link_type,
        )
        return ({
            "id": row.id,
            "source_ticket_id": row.source_ticket_id,
            "target_ticket_id": row.target_ticket_id,
            "link_type": row.link_type,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }, 201)


@require_authenticated
def remove_link(app, operation, request, *, principal: Principal, **kwargs):
    link_id = kwargs.get("link_id") or flask_request.view_args.get("link_id")
    if not link_id:
        raise ValidationError("link_id is required")
    with get_db() as db:
        link_service.remove(db, principal, link_id=link_id)
        return ("", 204)
