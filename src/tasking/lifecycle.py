"""Task lifecycle persistence.

Every published task gets a row in `tasks`. The consumer (or the inline
runner in DEV mode) flips that row through `pending` → `running` →
`completed` / `failed`. Each transition is its own short transaction so a
crash mid-handler still leaves a queryable row pinned at `running` —
`recover_orphans` (run on worker startup) flips those back to `pending`
for re-publish.

Failure semantics: every public function below is best-effort. If the DB
is down or a row is missing, we log and continue rather than crash a
worker over bookkeeping. The Kafka delivery itself is the source of
truth for whether a task ran.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.common.db import get_db
from src.tasking.models import (
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    Task,
)
from framework.commons.logger import logger


def create(
    *,
    task_name: str,
    payload: Optional[dict[str, Any]],
    correlation_id: str | None,
    topic: str | None,
) -> str:
    """Insert a `pending` row and return its id.

    Returns the generated task id even if the persistence call fails — in
    that case the caller still gets a usable identifier and the Kafka
    publish proceeds; we just lose the operator-side row. This is the
    intentional trade-off (availability over completeness).
    """
    task_id = str(uuid.uuid4())
    try:
        with get_db() as db:
            db.add(Task(
                id=task_id,
                task_name=task_name,
                topic=topic,
                status=STATUS_PENDING,
                payload=payload,
                correlation_id=correlation_id,
            ))
    except Exception as exc:
        logger.warning(
            "task lifecycle insert failed",
            extra={"task_id": task_id, "task_name": task_name, "error": str(exc)},
        )
    return task_id


def mark_running(task_id: str | None) -> None:
    if not task_id:
        return
    _bump(task_id, fields={
        "status": STATUS_RUNNING,
        "started_at": datetime.now(timezone.utc),
        "last_heartbeat_at": datetime.now(timezone.utc),
        "attempts": Task.attempts + 1,
    })


def mark_completed(task_id: str | None) -> None:
    if not task_id:
        return
    _bump(task_id, fields={
        "status": STATUS_COMPLETED,
        "completed_at": datetime.now(timezone.utc),
        "last_heartbeat_at": datetime.now(timezone.utc),
        "last_error": None,
    })


def mark_failed(task_id: str | None, error: str) -> None:
    if not task_id:
        return
    _bump(task_id, fields={
        "status": STATUS_FAILED,
        "completed_at": datetime.now(timezone.utc),
        "last_heartbeat_at": datetime.now(timezone.utc),
        # Hard-cap the stored error so an unbounded traceback doesn't blow
        # up the row size.
        "last_error": (error or "")[:4000],
    })


def heartbeat(task_id: str | None) -> None:
    """Long-running handlers should ping this every ~30s so
    `recover_orphans` doesn't bring them back as zombies."""
    if not task_id:
        return
    _bump(task_id, fields={"last_heartbeat_at": datetime.now(timezone.utc)})


def _bump(task_id: str, *, fields: dict[str, Any]) -> None:
    try:
        with get_db() as db:
            db.execute(
                update(Task).where(Task.id == task_id).values(**fields)
            )
    except Exception as exc:
        logger.warning(
            "task lifecycle update failed",
            extra={"task_id": task_id, "fields": list(fields), "error": str(exc)},
        )


# ── Recovery on startup ─────────────────────────────────────────────────────

def recover_orphans(*, stuck_after_seconds: int = 600) -> int:
    """Flip `running` rows whose heartbeat is older than `stuck_after_seconds`
    back to `pending`. Returns how many rows were touched.

    Run this once on worker startup (after the consumer connects to Kafka)
    so a crashed previous instance doesn't leave jobs eternally `running`.
    """
    threshold = datetime.now(timezone.utc) - timedelta(seconds=stuck_after_seconds)
    try:
        with get_db() as db:
            res = db.execute(
                update(Task)
                .where(
                    Task.status == STATUS_RUNNING,
                    (Task.last_heartbeat_at == None) | (Task.last_heartbeat_at < threshold),  # noqa: E711
                )
                .values(status=STATUS_PENDING, last_error="recovered_from_stuck_running")
            )
            return int(res.rowcount or 0)
    except Exception as exc:
        logger.warning("task recover_orphans failed", extra={"error": str(exc)})
        return 0


# ── Read API for operators / admin UI ───────────────────────────────────────

def list_tasks(
    db: Session,
    *,
    status: str | None = None,
    task_name: str | None = None,
    limit: int = 100,
) -> list[Task]:
    """Return recent task rows.

    If the `tasks` table doesn't exist yet (migration `e7b34cd9f211`
    not applied), we return an empty list rather than 500. The admin
    "Background tasks" widget then renders its quiet empty state.
    """
    stmt = select(Task).order_by(Task.created_at.desc())
    if status:
        stmt = stmt.where(Task.status == status)
    if task_name:
        stmt = stmt.where(Task.task_name == task_name)
    try:
        return list(db.scalars(stmt.limit(max(1, min(limit, 500)))))
    except Exception as exc:
        logger.warning(
            "tasks table read failed (migration applied?)",
            extra={"error": str(exc)},
        )
        # Roll the session back to clear the failed transaction state so
        # subsequent queries on the same session don't error with
        # "current transaction is aborted".
        try:
            db.rollback()
        except Exception:
            pass
        return []


def get_task(db: Session, task_id: str) -> Task | None:
    try:
        return db.get(Task, task_id)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
