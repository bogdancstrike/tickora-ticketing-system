"""Metadata HTTP endpoints."""
from flask import request as flask_request
from src.common.db import get_db
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.serializers import serialize_metadata
from src.ticketing.service import metadata_service

def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}

@require_authenticated
def list_metadata(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    with get_db() as db:
        items = metadata_service.list_by_ticket(db, principal, ticket_id)
        return ({"items": [serialize_metadata(m) for m in items]}, 200)

@require_authenticated
def set_metadata(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    payload = _payload()
    key = payload.get("key")
    value = payload.get("value")
    label = payload.get("label")
    
    if not key or value is None:
        return ({"error": "key and value are required"}, 400)
        
    with get_db() as db:
        m = metadata_service.set_metadata(db, principal, ticket_id, key, value, label)
        return (serialize_metadata(m), 200)

@require_authenticated
def delete_metadata(app, operation, request, *, principal: Principal, **kwargs):
    ticket_id = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    key = flask_request.args.get("key")
    
    if not key:
        return ({"error": "key is required as query param"}, 400)
        
    with get_db() as db:
        metadata_service.delete_metadata(db, principal, ticket_id, key)
        return ("", 204)
