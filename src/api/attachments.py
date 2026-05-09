"""Attachment endpoints."""
from flask import redirect, request as flask_request
from pydantic import BaseModel, ConfigDict, Field, ValidationError as PydValidationError

from src.core.db import get_db
from src.core.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.serializers import serialize_attachment
from src.ticketing.service import attachment_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _ticket_id(kwargs: dict) -> str:
    return kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")


def _attachment_id(kwargs: dict) -> str:
    return kwargs.get("attachment_id") or flask_request.view_args.get("attachment_id")


class _UploadUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str = Field(min_length=1, max_length=500)
    content_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(gt=0)


class _RegisterIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    storage_key: str = Field(min_length=1)
    file_name: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(gt=0)
    content_type: str | None = Field(default=None, max_length=255)
    checksum_sha256: str | None = Field(default=None, max_length=128)
    comment_id: str = Field(min_length=1)


def _parse(model_cls, raw: dict):
    try:
        return model_cls(**raw)
    except PydValidationError as e:
        raise ValidationError("invalid payload", details={"errors": e.errors()})


@require_authenticated
def request_upload_url(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_UploadUrlIn, _payload())
    with get_db() as db:
        out = attachment_service.request_upload_url(
            db,
            principal,
            _ticket_id(kwargs),
            file_name=body.file_name,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
        return (out, 200)


@require_authenticated
def register_attachment(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_RegisterIn, _payload())
    with get_db() as db:
        attachment = attachment_service.register(
            db,
            principal,
            _ticket_id(kwargs),
            storage_key=body.storage_key,
            file_name=body.file_name,
            size_bytes=body.size_bytes,
            content_type=body.content_type,
            checksum_sha256=body.checksum_sha256,
            comment_id=body.comment_id,
        )
        return (serialize_attachment(attachment), 201)


@require_authenticated
def list_attachments(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        attachments = attachment_service.list_(db, principal, _ticket_id(kwargs))
        return ({"items": [serialize_attachment(a) for a in attachments]}, 200)


@require_authenticated
def download_attachment(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        url = attachment_service.download_url(db, principal, _attachment_id(kwargs))
        return redirect(url, code=302)


@require_authenticated
def delete_attachment(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        attachment_service.delete(db, principal, _attachment_id(kwargs))
        return ({"status": "deleted"}, 200)
