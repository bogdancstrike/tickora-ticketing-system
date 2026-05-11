"""Snippets (procedures) HTTP surface."""
from flask import request as flask_request

from src.common.db import get_db
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import snippet_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


@require_authenticated
def list_snippets(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        items = snippet_service.list_(db, principal)
        return ({"items": [snippet_service.serialize(s) for s in items]}, 200)


@require_authenticated
def get_snippet(app, operation, request, *, principal: Principal, **kwargs):
    snippet_id = kwargs.get("snippet_id") or flask_request.view_args.get("snippet_id")
    with get_db() as db:
        return (snippet_service.serialize(snippet_service.get(db, principal, snippet_id)), 200)


@require_authenticated
def create_snippet(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (snippet_service.serialize(snippet_service.create(db, principal, _payload())), 201)


@require_authenticated
def update_snippet(app, operation, request, *, principal: Principal, **kwargs):
    snippet_id = kwargs.get("snippet_id") or flask_request.view_args.get("snippet_id")
    with get_db() as db:
        return (snippet_service.serialize(snippet_service.update(db, principal, snippet_id, _payload())), 200)


@require_authenticated
def delete_snippet(app, operation, request, *, principal: Principal, **kwargs):
    snippet_id = kwargs.get("snippet_id") or flask_request.view_args.get("snippet_id")
    with get_db() as db:
        snippet_service.delete(db, principal, snippet_id)
        return ("", 204)
