"""Audit DTO serializers."""
from datetime import datetime
from typing import Any

from src.audit.models import AuditEvent


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def serialize_audit_event(e: AuditEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "actor_user_id": e.actor_user_id,
        "actor_keycloak_subject": e.actor_keycloak_subject,
        "actor_username": e.actor_username,
        "action": e.action,
        "entity_type": e.entity_type,
        "entity_id": e.entity_id,
        "ticket_id": e.ticket_id,
        "old_value": e.old_value,
        "new_value": e.new_value,
        "metadata": e.audit_metadata,
        "request_ip": e.request_ip,
        "user_agent": e.user_agent,
        "correlation_id": e.correlation_id,
        "created_at": _iso(e.created_at),
    }
