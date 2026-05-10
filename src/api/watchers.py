"""Ticket-watcher endpoints.

```
GET    /api/tickets/<ticket_id>/watchers              — list watchers
POST   /api/tickets/<ticket_id>/watchers              — self-subscribe
                                                         (admin: subscribe `user_id` body field)
DELETE /api/tickets/<ticket_id>/watchers/<user_id>    — unsubscribe
                                                         (self by default; admin can target others)
```

All visibility rules go through `ticket_service.get` inside the service
layer — a controller bug here can't leak existence.
"""
from flask import request as flask_request

from src.core.db import get_db
from src.core.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import watcher_service


def _ticket_id(kwargs: dict) -> str:
    tid = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    if not tid:
        raise ValidationError("ticket_id is required")
    return tid


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


@require_authenticated
def list_watchers(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        items = watcher_service.list_for_ticket(db, principal, _ticket_id(kwargs))
        return ({"items": items}, 200)


@require_authenticated
def add_watcher(app, operation, request, *, principal: Principal, **kwargs):
    body = _payload()
    target_user_id = body.get("user_id")  # None → self
    with get_db() as db:
        row = watcher_service.add(
            db, principal, _ticket_id(kwargs), user_id=target_user_id,
        )
        return ({
            "id": row.id,
            "ticket_id": row.ticket_id,
            "user_id": row.user_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }, 201)


@require_authenticated
def remove_watcher(app, operation, request, *, principal: Principal, **kwargs):
    target_user_id = (
        kwargs.get("user_id")
        or flask_request.view_args.get("user_id")
        or principal.user_id
    )
    with get_db() as db:
        watcher_service.remove(
            db, principal, _ticket_id(kwargs), user_id=target_user_id,
        )
        return ("", 204)
