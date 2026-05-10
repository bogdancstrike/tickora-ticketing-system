"""Tasking ORM — `tasks` is the persisted lifecycle row for every async job.

Every call to `producer.publish(...)` writes a `pending` row first; the
consumer flips it to `running` then `completed` / `failed`. This gives us:

  * an audit trail for jobs (who fired what, when, with what payload),
  * a recovery hook (a `running` row whose `last_heartbeat_at` is older
    than N seconds is a candidate for re-publish),
  * an operator UI surface (admins can see what's queued or stuck).

The table is intentionally separate from `audit_events` — audit captures
domain events (who-did-what), tasks capture infrastructure events (what
the system has been asked to do).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# Status constants — keep narrow; new states need explicit migration support.
STATUS_PENDING   = "pending"
STATUS_RUNNING   = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED    = "failed"

ALL_STATUSES = (STATUS_PENDING, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED)
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_RUNNING)
TERMINAL_STATUSES = (STATUS_COMPLETED, STATUS_FAILED)


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("idx_tasks_status_created", "status", "created_at"),
        Index("idx_tasks_task_name_created", "task_name", "created_at"),
        Index(
            "idx_tasks_active",
            "status",
            "last_heartbeat_at",
            postgresql_where="status IN ('pending','running')",
        ),
    )

    id:             Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    task_name:      Mapped[str] = mapped_column(String(120), nullable=False)
    topic:          Mapped[str | None] = mapped_column(String(120), nullable=True)
    status:         Mapped[str] = mapped_column(String(20), nullable=False, default=STATUS_PENDING)
    payload:        Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    attempts:       Mapped[int]  = mapped_column(Integer, nullable=False, default=0)
    last_error:     Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
