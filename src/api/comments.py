"""Comment endpoints."""
from flask import request as flask_request
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydValidationError

from src.core.db import get_db
from src.core.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.serializers import serialize_comment
from src.ticketing.service import comment_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _ticket_id(kwargs: dict) -> str:
    return kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")


def _comment_id(kwargs: dict) -> str:
    return kwargs.get("comment_id") or flask_request.view_args.get("comment_id")


class _CreateCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=2, max_length=10000)
    visibility: str = "public"


class _EditCommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=2, max_length=10000)


def _parse(model_cls, raw: dict):
    try:
        return model_cls(**raw)
    except PydValidationError as e:
        raise ValidationError("invalid payload", details={"errors": e.errors()})


@require_authenticated
def list_comments(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        comments = comment_service.list_(db, principal, _ticket_id(kwargs))
        return ({"items": [serialize_comment(c) for c in comments]}, 200)


@require_authenticated
def create_comment(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_CreateCommentIn, _payload())
    with get_db() as db:
        comment = comment_service.create(
            db,
            principal,
            _ticket_id(kwargs),
            body=body.body,
            visibility=body.visibility,
        )
        return (serialize_comment(comment), 201)


@require_authenticated
def edit_comment(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_EditCommentIn, _payload())
    with get_db() as db:
        comment = comment_service.edit(db, principal, _comment_id(kwargs), body=body.body)
        return (serialize_comment(comment), 200)


@require_authenticated
def delete_comment(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        comment_service.delete(db, principal, _comment_id(kwargs))
        return ({"status": "deleted"}, 200)
