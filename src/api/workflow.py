"""Workflow action endpoints — POST /api/tickets/<id>/<action>."""
from flask import request as flask_request
from pydantic import BaseModel, ConfigDict, ValidationError as PydValidationError

from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.serializers import serialize_ticket
from src.ticketing.service import workflow_service


def _payload() -> dict:
    return flask_request.get_json(force=True, silent=True) or {}


def _ticket_id(kwargs: dict) -> str:
    tid = kwargs.get("ticket_id") or flask_request.view_args.get("ticket_id")
    if not tid:
        raise ValidationError("ticket_id is required")
    return tid


# ── Schemas ──────────────────────────────────────────────────────────────────

class _AssignSectorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector_code: str
    reason: str | None = None


class _AssignToUserIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    reason: str | None = None


class _MarkDoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution: str | None = None


class _CloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feedback: dict | None = None


class _ReopenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class _CancelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


class _PriorityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: str
    reason: str | None = None


def _parse(model_cls, raw: dict):
    try:
        return model_cls(**raw)
    except PydValidationError as e:
        raise ValidationError("invalid payload", details={"errors": e.errors()})


# ── Endpoints ────────────────────────────────────────────────────────────────

@require_authenticated
def assign_sector(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AssignSectorIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.assign_sector(db, principal, tid, body.sector_code, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def assign_to_me(app, operation, request, *, principal: Principal, **kwargs):
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.assign_to_me(db, principal, tid)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def assign_to_user(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AssignToUserIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.assign_to_user(db, principal, tid, body.user_id, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def reassign(app, operation, request, *, principal: Principal, **kwargs):
    return assign_to_user(app, operation, request, principal=principal, **kwargs)


class _UnassignIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str | None = None


@require_authenticated
def unassign(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_UnassignIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.unassign(db, principal, tid, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


class _ChangeStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    reason: str | None = None


@require_authenticated
def change_status(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_ChangeStatusIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.change_status(db, principal, tid, body.status, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


class _AddSectorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sector_code: str


@require_authenticated
def add_sector(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AddSectorIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.add_sector(db, principal, tid, body.sector_code)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def remove_sector(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AddSectorIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.remove_sector(db, principal, tid, body.sector_code)
        return (serialize_ticket(t, principal), 200)


class _AddAssigneeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str


@require_authenticated
def add_assignee(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AddAssigneeIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.add_assignee(db, principal, tid, body.user_id)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def remove_assignee(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_AddAssigneeIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.remove_assignee(db, principal, tid, body.user_id)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def mark_done(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_MarkDoneIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.mark_done(db, principal, tid, resolution=body.resolution)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def close(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_CloseIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.close(db, principal, tid, feedback=body.feedback)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def reopen(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_ReopenIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.reopen(db, principal, tid, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def cancel(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_CancelIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.cancel(db, principal, tid, reason=body.reason)
        return (serialize_ticket(t, principal), 200)


@require_authenticated
def change_priority(app, operation, request, *, principal: Principal, **kwargs):
    body = _parse(_PriorityIn, _payload())
    tid = _ticket_id(kwargs)
    with get_db() as db:
        t = workflow_service.change_priority(db, principal, tid, body.priority, reason=body.reason)
        return (serialize_ticket(t, principal), 200)
