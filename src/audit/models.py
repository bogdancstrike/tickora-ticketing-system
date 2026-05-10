"""Audit ORM — `audit_events` is the immutable ledger.

The schema lived under `src/ticketing/models.py` historically; moving it
into the audit module makes `src/audit/` self-sufficient (a microservice
can copy `src/audit/`, `src/core/`, `src/iam/`, and the migrations and
have everything it needs to record + serve audit data).

The `ticket_id` foreign key to `tickets.id` is intentionally retained for
the modulith: it stops orphaned ticket_ids in the local Postgres. If
extracting audit as a separate service over its own DB, drop the FK and
treat `ticket_id` as an opaque identifier (the constraint becomes
application-level, audit rows are never deleted anyway).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.common.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("idx_audit_events_ticket",        "ticket_id", "created_at"),
        Index("idx_audit_events_actor",         "actor_user_id", "created_at"),
        Index("idx_audit_events_action",        "action", "created_at"),
        Index("idx_audit_events_entity",        "entity_type", "entity_id", "created_at"),
        Index("idx_audit_events_created_at",    "created_at"),
        Index("idx_audit_events_correlation",   "correlation_id"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)

    actor_user_id:          Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    actor_keycloak_subject: Mapped[str | None] = mapped_column(String(255))
    actor_username:         Mapped[str | None] = mapped_column(String(255))

    action:      Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id:   Mapped[str | None] = mapped_column(UUID(as_uuid=False))

    # Convenience denormalisation: every audit row tied to a ticket carries
    # the ticket id so the timeline view can filter cheaply. Modulith FK;
    # drop it on a microservice extraction.
    ticket_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"))

    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    # `metadata` is a SQLAlchemy reserved attribute on Base; keep the column
    # name in DB but expose a different attribute name on the model.
    audit_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)

    request_ip:     Mapped[str | None] = mapped_column(INET)
    user_agent:     Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
