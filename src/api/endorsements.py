"""Supplementary endorsements ("avizare suplimentară") HTTP surface."""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import endorsement_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _serialize(row, ticket=None) -> dict:
    out = {
        "id":                   row.id,
        "ticket_id":            row.ticket_id,
        "requested_by_user_id": row.requested_by_user_id,
        "assigned_to_user_id":  row.assigned_to_user_id,
        "status":               row.status,
        "request_reason":       row.request_reason,
        "decided_by_user_id":   row.decided_by_user_id,
        "decision_reason":      row.decision_reason,
        "decided_at":           row.decided_at.isoformat() if row.decided_at else None,
        "created_at":           row.created_at.isoformat() if row.created_at else None,
        "updated_at":           row.updated_at.isoformat() if row.updated_at else None,
    }
    if ticket is not None:
        out["ticket_code"]  = ticket.ticket_code
        out["ticket_title"] = ticket.title
        out["ticket_status"] = ticket.status
        out["ticket_priority"] = ticket.priority
    return out


@require_authenticated
def request_endorsement(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    body = _payload()
    with get_db() as db:
        row = endorsement_service.request(
            db, principal, ticket_id,
            reason=body.get("reason"),
            assigned_to_user_id=body.get("assigned_to_user_id") or None,
        )
        return (_serialize(row), 201)


@require_authenticated
def list_for_ticket(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        rows = endorsement_service.list_for_ticket(db, principal, ticket_id)
        return ({"items": [_serialize(r) for r in rows]}, 200)


@require_authenticated
def decide(app, operation, request, *, principal: Principal, **kwargs):
    endorsement_id = kwargs.get("endorsement_id") or flask_request.view_args.get("endorsement_id")
    body = _payload()
    decision = (body.get("decision") or "").strip().lower()
    if decision not in ("approved", "rejected"):
        raise ValidationError("decision must be 'approved' or 'rejected'")
    with get_db() as db:
        row = endorsement_service.decide(
            db, principal, endorsement_id,
            decision=decision, reason=body.get("reason"),
        )
        return (_serialize(row), 200)


@require_authenticated
def claim(app, operation, request, *, principal: Principal, **kwargs):
    endorsement_id = kwargs.get("endorsement_id") or flask_request.view_args.get("endorsement_id")
    with get_db() as db:
        row = endorsement_service.claim(db, principal, endorsement_id)
        return (_serialize(row), 200)


@require_authenticated
def approve(app, operation, request, *, principal: Principal, **kwargs):
    endorsement_id = kwargs.get("endorsement_id") or flask_request.view_args.get("endorsement_id")
    body = _payload()
    with get_db() as db:
        row = endorsement_service.decide(
            db, principal, endorsement_id,
            decision="approved", reason=body.get("reason"),
        )
        return (_serialize(row), 200)


@require_authenticated
def reject(app, operation, request, *, principal: Principal, **kwargs):
    endorsement_id = kwargs.get("endorsement_id") or flask_request.view_args.get("endorsement_id")
    body = _payload()
    with get_db() as db:
        row = endorsement_service.decide(
            db, principal, endorsement_id,
            decision="rejected", reason=body.get("reason"),
        )
        return (_serialize(row), 200)


@require_authenticated
def inbox(app, operation, request, *, principal: Principal, **kwargs):
    status = flask_request.args.get("status")
    limit = int(flask_request.args.get("limit", 100) or 100)
    with get_db() as db:
        rows = endorsement_service.inbox(db, principal, status=status, limit=limit)
        return ({"items": [_serialize(r, t) for r, t in rows]}, 200)
