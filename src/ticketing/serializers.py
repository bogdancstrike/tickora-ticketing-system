"""Permission-aware serializers. Convert ORM rows → API dicts based on Principal."""
from datetime import datetime
from typing import Any

from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing.models import AuditEvent, Ticket, TicketAttachment, TicketComment, TicketMetadata


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def serialize_ticket(t: Ticket, p: Principal, *, full: bool = True) -> dict[str, Any]:
    """Render a Ticket for API output, scrubbing fields the principal cannot see."""
    sector_code = getattr(t, "current_sector_code", None)
    can_see_internal = (
        p.is_admin or p.is_auditor or p.is_distributor
        or (sector_code and sector_code in p.all_sectors)
    )

    payload: dict[str, Any] = {
        "id":               t.id,
        "ticket_code":      t.ticket_code,
        "status":           t.status,
        "priority":         t.priority,
        "category":         t.category,
        "type":             t.type,
        "beneficiary_type": t.beneficiary_type,
        "title":            t.title,
        "current_sector_code": sector_code,
        "created_at":       _iso(t.created_at),
        "updated_at":       _iso(t.updated_at),
        "done_at":          _iso(t.done_at),
        "closed_at":        _iso(t.closed_at),
        "reopened_at":      _iso(t.reopened_at),
        "reopened_count":   t.reopened_count,
        "sla_due_at":       _iso(t.sla_due_at),
        "sla_status":       t.sla_status,
        "assignee_user_id": t.assignee_user_id,
    }

    if full:
        payload["txt"] = t.txt
        payload["resolution"] = t.resolution
        
        # Include metadata in full serialization
        metadatas = getattr(t, "metadatas", [])
        if metadatas:
            payload["metadata"] = {m.key: {"value": m.value, "label": m.label} for m in metadatas}

    if can_see_internal:
        payload.update({
            "requester_first_name":   t.requester_first_name,
            "requester_last_name":    t.requester_last_name,
            "requester_email":        t.requester_email,
            "requester_phone":        t.requester_phone,
            "requester_organization": t.requester_organization,
            "requester_ip":           t.requester_ip,
            "source_ip":              t.source_ip,
            "created_by_user_id":     t.created_by_user_id,
            "last_active_assignee_user_id": t.last_active_assignee_user_id,
            "assigned_at":            _iso(t.assigned_at),
            "sector_assigned_at":     _iso(t.sector_assigned_at),
            "first_response_at":      _iso(t.first_response_at),
        })

    return payload


def list_response(items: list[Ticket], p: Principal, next_cursor: str | None) -> dict[str, Any]:
    return {
        "items": [serialize_ticket(t, p, full=False) for t in items],
        "next_cursor": next_cursor,
    }


def serialize_comment(c: TicketComment) -> dict[str, Any]:
    return {
        "id": c.id,
        "ticket_id": c.ticket_id,
        "author_user_id":  c.author_user_id,
        "author_display":  getattr(c, "_author_display", None),
        "author_username": getattr(c, "_author_username", None),
        "author_email":    getattr(c, "_author_email", None),
        "visibility": c.visibility,
        "comment_type": c.comment_type,
        "body": c.body,
        "created_at": _iso(c.created_at),
        "updated_at": _iso(c.updated_at),
    }


def serialize_attachment(a: TicketAttachment) -> dict[str, Any]:
    return {
        "id": a.id,
        "ticket_id": a.ticket_id,
        "comment_id": a.comment_id,
        "uploaded_by_user_id": a.uploaded_by_user_id,
        "file_name": a.file_name,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "visibility": a.visibility,
        "checksum_sha256": a.checksum_sha256,
        "is_scanned": a.is_scanned,
        "scan_result": a.scan_result,
        "created_at": _iso(a.created_at),
    }


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


def serialize_metadata(m: TicketMetadata) -> dict[str, Any]:
    return {
        "key": m.key,
        "value": m.value,
        "label": m.label,
        "created_at": _iso(m.created_at),
        "updated_at": _iso(m.updated_at),
    }
