"""Tasking inspection endpoints (admin-only).

`GET /api/tasks?status=running&task_name=notify_distributors&limit=50`
lists recent tasks. `GET /api/tasks/<id>` fetches one. The data lives in
the `tasks` table populated by the producer/consumer lifecycle hooks
(`src/tasking/lifecycle.py`).

These endpoints are intentionally read-only — re-running a failed task
is a deliberate action that should go through a domain service, not a
generic "retry this row" button.
"""
from flask import request as flask_request

from src.core.db import get_db
from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.tasking import lifecycle
from src.tasking.models import ALL_STATUSES, Task


def _require_admin(p: Principal) -> None:
    if not p.is_admin:
        raise PermissionDeniedError("admin role required")


def _serialize(t: Task) -> dict:
    return {
        "id": t.id,
        "task_name": t.task_name,
        "topic": t.topic,
        "status": t.status,
        "payload": t.payload,
        "correlation_id": t.correlation_id,
        "attempts": t.attempts,
        "last_error": t.last_error,
        "created_at":        t.created_at.isoformat()        if t.created_at        else None,
        "started_at":        t.started_at.isoformat()        if t.started_at        else None,
        "completed_at":      t.completed_at.isoformat()      if t.completed_at      else None,
        "last_heartbeat_at": t.last_heartbeat_at.isoformat() if t.last_heartbeat_at else None,
    }


@require_authenticated
def list_tasks(app, operation, request, *, principal: Principal, **kwargs):
    _require_admin(principal)
    status = flask_request.args.get("status")
    if status and status not in ALL_STATUSES:
        raise ValidationError(
            f"status must be one of {sorted(ALL_STATUSES)}",
            details={"received": status},
        )
    task_name = flask_request.args.get("task_name")
    limit = int(flask_request.args.get("limit", 100) or 100)

    with get_db() as db:
        rows = lifecycle.list_tasks(db, status=status, task_name=task_name, limit=limit)
        return ({"items": [_serialize(t) for t in rows]}, 200)


@require_authenticated
def get_task(app, operation, request, *, principal: Principal, **kwargs):
    _require_admin(principal)
    task_id = kwargs.get("task_id") or flask_request.view_args.get("task_id")
    if not task_id:
        raise ValidationError("task_id is required")
    with get_db() as db:
        row = lifecycle.get_task(db, task_id)
        if row is None:
            raise NotFoundError("task not found")
        return (_serialize(row), 200)
