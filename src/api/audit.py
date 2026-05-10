"""Audit explorer endpoints."""
from flask import request as flask_request

from src.common.db import get_db
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.audit.serializers import serialize_audit_event
from src.audit import service as audit_service


def _limit() -> int:
    try:
        return int(flask_request.args.get("limit") or 100)
    except ValueError:
        return 100


@require_authenticated
def list_audit(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        events = audit_service.list_(
            db,
            principal,
            action=flask_request.args.get("action"),
            actor_user_id=flask_request.args.get("actor_user_id"),
            actor_username=flask_request.args.get("actor_username"),
            entity_type=flask_request.args.get("entity_type"),
            entity_id=flask_request.args.get("entity_id"),
            ticket_id=flask_request.args.get("ticket_id"),
            correlation_id=flask_request.args.get("correlation_id"),
            created_after=flask_request.args.get("created_after"),
            created_before=flask_request.args.get("created_before"),
            sort_by=flask_request.args.get("sort_by", "created_at"),
            sort_dir=flask_request.args.get("sort_dir", "desc"),
            limit=_limit(),
        )
        return ({"items": [serialize_audit_event(e) for e in events]}, 200)


@require_authenticated
def ticket_audit(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        events = audit_service.get_for_ticket(db, principal, ticket_id, limit=_limit())
        return ({"items": [serialize_audit_event(e) for e in events]}, 200)


@require_authenticated
def user_audit(app, operation, request, *, principal: Principal, **kwargs):
    user_id = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    with get_db() as db:
        events = audit_service.get_for_user(db, principal, user_id, limit=_limit())
        return ({"items": [serialize_audit_event(e) for e in events]}, 200)
