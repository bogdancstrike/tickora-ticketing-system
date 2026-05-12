"""Admin module service.

The admin surface intentionally composes existing Tickora state instead of
introducing new admin-only tables: users, sectors, memberships, audit, tickets,
notifications, and metadata definitions are the source of truth.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from framework.commons.logger import logger
from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.common.errors import BusinessRuleError, NotFoundError, PermissionDeniedError, ValidationError
from src.iam.keycloak_admin import KeycloakAdminClient
from src.iam.models import User
from src.iam.principal import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_AVIZATOR,
    ROLE_DISTRIBUTOR,
    ROLE_INTERNAL_USER,
    ROLE_EXTERNAL_USER,
    ROLE_SERVICE,
    Principal,
)
from src.audit import events
from src.ticketing.models import (
    AuditEvent,
    Category,
    MetadataKeyDefinition,
    Notification,
    Sector,
    SectorMembership,
    Subcategory,
    SubcategoryFieldDefinition,
    SystemSetting,
    Ticket,
    TicketMetadata,
)
from src.audit import service as audit_service
from src.ticketing.service import monitor_service
from src.ticketing.state_machine import ACTIVE_STATUSES

ADMIN_ROLES = {
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DISTRIBUTOR,
    ROLE_AVIZATOR,
    ROLE_INTERNAL_USER,
    ROLE_EXTERNAL_USER,
    ROLE_SERVICE,
}
MEMBERSHIP_ROLES = {"member", "chief"}


def require_admin(principal: Principal) -> None:
    if not principal.has_root_group:
        raise PermissionDeniedError("root /tickora group required")


def overview(db: Session, principal: Principal) -> dict[str, Any]:
    require_admin(principal)
    status_counts = _rows_to_breakdown(db.execute(
        select(Ticket.status, func.count(Ticket.id))
        .where(Ticket.is_deleted.is_(False))
        .group_by(Ticket.status)
    ))
    priority_counts = _rows_to_breakdown(db.execute(
        select(Ticket.priority, func.count(Ticket.id))
        .where(Ticket.is_deleted.is_(False))
        .group_by(Ticket.priority)
    ))
    sector_counts = [
        {"sector_code": code or "unassigned", "count": int(count or 0)}
        for code, count in db.execute(
            select(Sector.code, func.count(Ticket.id))
            .select_from(Ticket)
            .join(Sector, Sector.id == Ticket.current_sector_id, isouter=True)
            .where(Ticket.is_deleted.is_(False))
            .group_by(Sector.code)
            .order_by(desc(func.count(Ticket.id)))
            .limit(12)
        )
    ]
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_sectors = db.scalar(select(func.count(Sector.id)).where(Sector.is_active.is_(True))) or 0
    total_memberships = db.scalar(select(func.count(SectorMembership.id)).where(SectorMembership.is_active.is_(True))) or 0
    today = _today_start()
    # Active sessions = users currently signed in (presence-tracked in Redis,
    # 5-minute window). Falls back to 0 when Redis is unreachable so the
    # overview doesn't break — Redis is a soft dependency for this widget.
    from src.common.session_tracker import active_user_count
    try:
        active_sessions = active_user_count()
    except Exception:
        active_sessions = 0
    kpis = {
        "total_tickets": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False))),
        "active_tickets": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.status.in_(ACTIVE_STATUSES))),
        "new_today": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.created_at >= today)),
        "users": int(total_users),
        "active_users": int(active_users),
        "active_sessions": int(active_sessions),
        "active_sectors": int(active_sectors),
        "memberships": int(total_memberships),
        "unread_notifications": _count(db, select(Notification).where(Notification.is_read.is_(False))),
        "audit_events_today": _count(db, select(AuditEvent).where(AuditEvent.created_at >= today)),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kpis": kpis,
        "by_status": status_counts,
        "by_priority": priority_counts,
        "by_sector": sector_counts,
        "global_monitor": monitor_service.monitor_global(db, principal),
        "recent_audit": [_serialize_audit(a) for a in db.scalars(
            select(AuditEvent).order_by(desc(AuditEvent.created_at), desc(AuditEvent.id)).limit(12)
        )],
        "queues": _admin_queues(db),
        "system": {
            "metadata_keys": _count(db, select(MetadataKeyDefinition)),
            "inactive_sectors": _count(db, select(Sector).where(Sector.is_active.is_(False))),
        },
    }


def list_users(db: Session, principal: Principal, *, search: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    # Allow admins or chiefs. 
    if not principal.has_root_group and not principal.chief_sectors:
        raise PermissionDeniedError("admin or sector chief required")

    limit = max(1, min(limit, 250))
    stmt = select(User).order_by(User.username.asc().nulls_last(), User.email.asc().nulls_last()).limit(limit)

    if not principal.has_root_group:
        # Chiefs only see members of sectors they are chief of.
        stmt = (
            select(User)
            .join(SectorMembership, SectorMembership.user_id == User.id)
            .join(Sector, Sector.id == SectorMembership.sector_id)
            .where(
                Sector.code.in_(principal.chief_sectors),
                SectorMembership.is_active.is_(True)
            )
            .distinct()
            .order_by(User.username.asc().nulls_last(), User.email.asc().nulls_last())
            .limit(limit)
        )

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(User.username.ilike(term), User.email.ilike(term), User.first_name.ilike(term), User.last_name.ilike(term)))
    
    users = list(db.scalars(stmt))
    memberships = _memberships_by_user(db, [u.id for u in users])
    role_map = _keycloak_roles_by_subject(users)
    return [_serialize_user(u, memberships.get(u.id, []), role_map.get(u.keycloak_subject, [])) for u in users]


def get_user(db: Session, principal: Principal, user_id: str) -> dict[str, Any]:
    require_admin_or_chief(db, principal, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    return _serialize_user(user, _memberships_by_user(db, [user.id]).get(user.id, []), _keycloak_roles(user.keycloak_subject))


def update_user(db: Session, principal: Principal, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin_or_chief(db, principal, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    old = _serialize_user(user, _memberships_by_user(db, [user.id]).get(user.id, []), _keycloak_roles(user.keycloak_subject))

    if "is_active" in payload:
        new_active = bool(payload["is_active"])
        _run_keycloak(lambda kc: kc.set_user_enabled(user.keycloak_subject, new_active), "set_user_enabled")
        user.is_active = new_active
    for field in ("user_type", "first_name", "last_name", "email", "username"):
        if field in payload and payload[field] is not None:
            setattr(user, field, str(payload[field]).strip())

    if "roles" in payload:
        if not principal.has_root_group:
            raise PermissionDeniedError("root /tickora group required to manage realm roles")
        _set_realm_roles(user.keycloak_subject, payload["roles"])

    db.flush()
    new = _serialize_user(user, _memberships_by_user(db, [user.id]).get(user.id, []), _keycloak_roles(user.keycloak_subject))
    audit_service.record(
        db,
        actor=principal,
        action=events.ROLE_GRANTED if "roles" in payload else events.CONFIG_CHANGED,
        entity_type="user",
        entity_id=user.id,
        old_value=old,
        new_value=new,
        metadata={"operation": "admin_update_user"},
    )
    return new


def reset_password(db: Session, principal: Principal, user_id: str, reason: str | None = None) -> str:
    """Generate a random temporary password, push it to Keycloak, and return it so the
    caller can display it once to the admin performing the reset.

    Unlike other Keycloak operations this one raises on failure — a silent
    swallow here would return a password to the admin that was never set.
    """
    import secrets
    import string

    require_admin_or_chief(db, principal, user_id)
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")

    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = "".join(secrets.choice(alphabet) for _ in range(16))

    # Propagate the exception so the caller gets a 500 instead of a phantom success.
    KeycloakAdminClient.get().reset_password(user.keycloak_subject, password, temporary=True)

    meta: dict = {"operation": "admin_reset_password"}
    if reason:
        meta["reason"] = reason.strip()[:500]
    audit_service.record(
        db,
        actor=principal,
        action=events.CONFIG_CHANGED,
        entity_type="user",
        entity_id=user.id,
        metadata=meta,
    )
    return password


def require_admin_or_chief(db: Session, principal: Principal, target_user_id: str) -> None:
    """True if principal is global admin or chief of a sector the target user is in."""
    if principal.has_root_group:
        return

    # Check if principal is chief of ANY sector the target user belongs to.
    target_memberships = db.scalars(
        select(SectorMembership.sector_id)
        .where(SectorMembership.user_id == target_user_id, SectorMembership.is_active.is_(True))
    ).all()
    
    if not target_memberships:
        raise PermissionDeniedError("insufficient permissions to manage this user")

    # Get sector codes for these IDs
    target_sector_codes = db.scalars(
        select(Sector.code).where(Sector.id.in_(target_memberships))
    ).all()

    if any(principal.is_chief_of(code) for code in target_sector_codes):
        return

    raise PermissionDeniedError("insufficient permissions to manage this user")


def list_sectors(db: Session, principal: Principal) -> list[dict[str, Any]]:
    require_admin(principal)
    sectors = list(db.scalars(select(Sector).order_by(Sector.code.asc())))
    counts = {
        sector_id: count
        for sector_id, count in db.execute(
            select(SectorMembership.sector_id, func.count(SectorMembership.id))
            .where(SectorMembership.is_active.is_(True))
            .group_by(SectorMembership.sector_id)
        )
    }
    return [_serialize_sector(s, membership_count=int(counts.get(s.id, 0))) for s in sectors]


def upsert_sector(db: Session, principal: Principal, payload: dict[str, Any], *, sector_id: str | None = None) -> dict[str, Any]:
    require_admin(principal)
    code = str(payload.get("code") or "").strip().lower()
    if sector_id is None and not code:
        raise ValidationError("sector code is required")
    sector = db.get(Sector, sector_id) if sector_id else db.scalar(select(Sector).where(Sector.code == code))
    old = _serialize_sector(sector) if sector else None
    if sector is None:
        sector = Sector(code=code, name=str(payload.get("name") or code).strip(), description=payload.get("description"))
        db.add(sector)
        action = events.SECTOR_CREATED
    else:
        action = events.SECTOR_UPDATED
        if "code" in payload and code:
            sector.code = code
        if "name" in payload:
            sector.name = str(payload["name"]).strip()
        if "description" in payload:
            sector.description = payload.get("description")
        if "is_active" in payload:
            sector.is_active = bool(payload["is_active"])
    try:
        db.flush()
    except IntegrityError as exc:
        raise BusinessRuleError("sector code already exists") from exc

    new = _serialize_sector(sector)
    audit_service.record(db, actor=principal, action=action, entity_type="sector", entity_id=sector.id, old_value=old, new_value=new)
    return new


def memberships(db: Session, principal: Principal, *, sector_code: str | None = None) -> list[dict[str, Any]]:
    require_admin(principal)
    stmt = (
        select(SectorMembership, User, Sector)
        .join(User, User.id == SectorMembership.user_id)
        .join(Sector, Sector.id == SectorMembership.sector_id)
        .where(SectorMembership.is_active.is_(True))
        .order_by(Sector.code.asc(), SectorMembership.membership_role.asc(), User.username.asc().nulls_last())
    )
    if sector_code:
        stmt = stmt.where(Sector.code == sector_code)
    return [_serialize_membership(m, u, s) for m, u, s in db.execute(stmt)]


def grant_membership(db: Session, principal: Principal, user_id: str, sector_code: str, role: str) -> dict[str, Any]:
    require_admin(principal)
    role = _validate_membership_role(role)
    user = db.get(User, user_id)
    sector = db.scalar(select(Sector).where(Sector.code == sector_code))
    if user is None:
        raise NotFoundError("user not found")
    if sector is None:
        raise NotFoundError("sector not found")
    membership = db.scalar(select(SectorMembership).where(
        SectorMembership.user_id == user.id,
        SectorMembership.sector_id == sector.id,
        SectorMembership.membership_role == role,
    ))
    if membership:
        membership.is_active = True
    else:
        membership = SectorMembership(user_id=user.id, sector_id=sector.id, membership_role=role)
        db.add(membership)
    db.flush()
    _sync_keycloak_membership(user.keycloak_subject, sector.code, role, add=True)
    payload = _serialize_membership(membership, user, sector)
    audit_service.record(
        db,
        actor=principal,
        action=events.MEMBERSHIP_GRANTED,
        entity_type="sector_membership",
        entity_id=membership.id,
        new_value=payload,
    )
    return payload


def revoke_membership(db: Session, principal: Principal, membership_id: str) -> None:
    require_admin(principal)
    row = db.execute(
        select(SectorMembership, User, Sector)
        .join(User, User.id == SectorMembership.user_id)
        .join(Sector, Sector.id == SectorMembership.sector_id)
        .where(SectorMembership.id == membership_id)
    ).first()
    if row is None:
        raise NotFoundError("membership not found")
    membership, user, sector = row
    old = _serialize_membership(membership, user, sector)
    membership.is_active = False
    db.flush()
    _sync_keycloak_membership(user.keycloak_subject, sector.code, membership.membership_role, add=False)
    audit_service.record(
        db,
        actor=principal,
        action=events.MEMBERSHIP_REVOKED,
        entity_type="sector_membership",
        entity_id=membership.id,
        old_value=old,
        new_value=None,
    )


def group_hierarchy(db: Session, principal: Principal) -> dict[str, Any]:
    require_admin(principal)
    
    keycloak_tree = _keycloak_group_tree()
    if not keycloak_tree:
        return {
            "key": "root",
            "title": "Groups",
            "children": [],
        }

    # Since _keycloak_group_tree now returns the 'tickora' branch directly,
    # we can just return it as the root or wrapped in a generic Groups node.
    keycloak_tree["title"] = "SSO Groups (/tickora)"
    
    return {
        "key": "root",
        "title": "Groups",
        "children": [keycloak_tree],
    }


def metadata_keys(db: Session, principal: Principal) -> list[dict[str, Any]]:
    require_admin(principal)
    rows = list(db.scalars(select(MetadataKeyDefinition).order_by(MetadataKeyDefinition.key.asc())))
    return [_serialize_metadata_key(r) for r in rows]


def upsert_metadata_key(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    key = str(payload.get("key") or "").strip().lower()
    if not key:
        raise ValidationError("metadata key is required")
    row = db.get(MetadataKeyDefinition, key)
    old = _serialize_metadata_key(row) if row else None
    if row is None:
        row = MetadataKeyDefinition(key=key, label=str(payload.get("label") or key).strip())
        db.add(row)
    for field in ("label", "value_type", "description"):
        if field in payload:
            setattr(row, field, payload.get(field))
    if "options" in payload:
        row.options = payload.get("options") or None
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    db.flush()
    new = _serialize_metadata_key(row)
    audit_service.record(
        db,
        actor=principal,
        action=events.CONFIG_CHANGED,
        entity_type="metadata_key_definition",
        entity_id=None,
        old_value=old,
        new_value=new,
        metadata={"metadata_key": key},
    )
    return new


def ticket_metadatas(
    db: Session,
    principal: Principal,
    *,
    ticket_code: str | None = None,
    key: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    require_admin(principal)
    limit = max(1, min(limit, 250))
    stmt = (
        select(TicketMetadata, Ticket)
        .join(Ticket, Ticket.id == TicketMetadata.ticket_id)
        .where(Ticket.is_deleted.is_(False))
    )
    if ticket_code:
        stmt = stmt.where(Ticket.ticket_code.ilike(f"%{ticket_code.strip()}%"))
    if key:
        stmt = stmt.where(TicketMetadata.key == key.strip().lower())
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(
            TicketMetadata.key.ilike(term),
            TicketMetadata.value.ilike(term),
            TicketMetadata.label.ilike(term),
            Ticket.ticket_code.ilike(term),
            Ticket.title.ilike(term),
        ))
    
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    
    stmt = stmt.order_by(desc(TicketMetadata.updated_at), Ticket.ticket_code.asc(), TicketMetadata.key.asc())
    if offset is not None:
        stmt = stmt.offset(offset)
    stmt = stmt.limit(limit)

    results = [_serialize_ticket_metadata(row, ticket) for row, ticket in db.execute(stmt)]
    return results, total


def upsert_ticket_metadata(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    metadata_id = payload.get("id")
    ticket_ref = str(payload.get("ticket_id") or payload.get("ticket_code") or "").strip()
    key = str(payload.get("key") or "").strip().lower()
    value = payload.get("value")
    if metadata_id:
        row = db.get(TicketMetadata, metadata_id)
        if row is None:
            raise NotFoundError("ticket metadata not found")
        ticket = db.get(Ticket, row.ticket_id)
    else:
        if not ticket_ref or not key or value is None:
            raise ValidationError("ticket_id or ticket_code, key and value are required")
        ticket = _ticket_by_ref(db, ticket_ref)
        row = db.scalar(select(TicketMetadata).where(TicketMetadata.ticket_id == ticket.id, TicketMetadata.key == key))
    if ticket is None:
        raise NotFoundError("ticket not found")

    old = _serialize_ticket_metadata(row, ticket) if row else None
    if row is None:
        row = TicketMetadata(ticket_id=ticket.id, key=key, value=str(value), label=payload.get("label"))
        db.add(row)
    else:
        if key:
            row.key = key
        if value is not None:
            row.value = str(value)
        if "label" in payload:
            row.label = payload.get("label")
    try:
        db.flush()
    except IntegrityError as exc:
        raise BusinessRuleError("ticket metadata key already exists for this ticket") from exc
    new = _serialize_ticket_metadata(row, ticket)
    audit_service.record(
        db,
        actor=principal,
        action=events.CONFIG_CHANGED,
        entity_type="ticket_metadata",
        entity_id=row.id,
        ticket_id=ticket.id,
        old_value=old,
        new_value=new,
        metadata={"operation": "admin_upsert_ticket_metadata", "metadata_key": row.key},
    )
    return new


def delete_ticket_metadata(db: Session, principal: Principal, metadata_id: str) -> None:
    require_admin(principal)
    row = db.get(TicketMetadata, metadata_id)
    if row is None:
        raise NotFoundError("ticket metadata not found")
    ticket = db.get(Ticket, row.ticket_id)
    old = _serialize_ticket_metadata(row, ticket)
    db.delete(row)
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.CONFIG_CHANGED,
        entity_type="ticket_metadata",
        entity_id=metadata_id,
        ticket_id=ticket.id if ticket else None,
        old_value=old,
        new_value=None,
        metadata={"operation": "admin_delete_ticket_metadata", "metadata_key": old["key"] if old else None},
    )


def list_system_settings(db: Session, principal: Principal) -> list[dict[str, Any]]:
    require_admin(principal)
    rows = list(db.scalars(select(SystemSetting).order_by(SystemSetting.key.asc())))
    return [_serialize_system_setting(r) for r in rows]


def upsert_system_setting(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    key = str(payload.get("key") or "").strip().lower()
    if not key:
        raise ValidationError("key is required")
    value = payload.get("value")
    if value is None:
        raise ValidationError("value is required")

    row = db.get(SystemSetting, key)
    old = _serialize_system_setting(row) if row else None
    if row is None:
        row = SystemSetting(key=key, value=value, description=payload.get("description"))
        db.add(row)
    else:
        row.value = value
        if "description" in payload:
            row.description = payload.get("description")

    db.flush()
    new = _serialize_system_setting(row)
    audit_service.record(
        db,
        actor=principal,
        action=events.CONFIG_CHANGED,
        entity_type="system_setting",
        entity_id=None,
        old_value=old,
        new_value=new,
        metadata={"operation": "admin_upsert_system_setting", "key": key},
    )
    return new


def _admin_queues(db: Session) -> dict[str, int]:
    return {
        "pending_review": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.status == "pending")),
        "unassigned_active": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.status.in_(ACTIVE_STATUSES), Ticket.assignee_user_id.is_(None))),
        "reopened": _count(db, select(Ticket).where(Ticket.is_deleted.is_(False), Ticket.reopened_count > 0)),
    }


def _serialize_user(user: User, memberships_: list[dict[str, Any]], roles: list[str]) -> dict[str, Any]:
    data = _serialize_user_basic(user)
    data.update({
        "roles": sorted(set(roles)),
        "memberships": memberships_,
        "created_at": _dt(user.created_at),
        "updated_at": _dt(user.updated_at),
    })
    return data


def _serialize_user_basic(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "keycloak_subject": user.keycloak_subject,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "user_type": user.user_type,
        "is_active": user.is_active,
    }


def _serialize_sector(sector: Sector | None, *, membership_count: int | None = None) -> dict[str, Any] | None:
    if sector is None:
        return None
    data = {
        "id": sector.id,
        "code": sector.code,
        "name": sector.name,
        "description": sector.description,
        "is_active": sector.is_active,
        "created_at": _dt(sector.created_at),
        "updated_at": _dt(sector.updated_at),
    }
    if membership_count is not None:
        data["membership_count"] = membership_count
    return data


def _serialize_membership(m: SectorMembership, user: User, sector: Sector) -> dict[str, Any]:
    return {
        "id": m.id,
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "sector_id": sector.id,
        "sector_code": sector.code,
        "sector_name": sector.name,
        "role": m.membership_role,
        "is_active": m.is_active,
        "created_at": _dt(m.created_at),
        "updated_at": _dt(m.updated_at),
    }


def _serialize_metadata_key(row: MetadataKeyDefinition | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "key": row.key,
        "label": row.label,
        "value_type": row.value_type,
        "options": row.options or [],
        "description": row.description,
        "is_active": row.is_active,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def _serialize_ticket_metadata(row: TicketMetadata | None, ticket: Ticket | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "ticket_code": ticket.ticket_code if ticket else None,
        "ticket_title": ticket.title if ticket else None,
        "key": row.key,
        "value": row.value,
        "label": row.label,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


def _serialize_system_setting(row: SystemSetting | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "key": row.key,
        "value": row.value,
        "description": row.description,
        "updated_at": _dt(row.updated_at),
    }


def _serialize_audit(row: AuditEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "actor_username": row.actor_username,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "ticket_id": row.ticket_id,
        "created_at": _dt(row.created_at),
    }


def _memberships_by_user(db: Session, user_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not user_ids:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for m, u, s in db.execute(
        select(SectorMembership, User, Sector)
        .join(User, User.id == SectorMembership.user_id)
        .join(Sector, Sector.id == SectorMembership.sector_id)
        .where(SectorMembership.user_id.in_(user_ids), SectorMembership.is_active.is_(True))
        .order_by(Sector.code.asc(), SectorMembership.membership_role.asc())
    ):
        out.setdefault(u.id, []).append(_serialize_membership(m, u, s))
    return out


def _keycloak_roles_by_subject(users: list[User]) -> dict[str, list[str]]:
    return {u.keycloak_subject: _keycloak_roles(u.keycloak_subject) for u in users}


def _keycloak_roles(subject: str) -> list[str]:
    roles: list[str] = []
    def run(kc: KeycloakAdminClient) -> None:
        nonlocal roles
        roles = [r.get("name") for r in kc.get_user_realm_roles(subject) if r.get("name") in ADMIN_ROLES]
    _try_keycloak(run, "get_user_realm_roles")
    return sorted(set(roles))


def _keycloak_roles_strict(subject: str) -> list[str]:
    roles: list[str] = []

    def run(kc: KeycloakAdminClient) -> None:
        nonlocal roles
        roles = [r.get("name") for r in kc.get_user_realm_roles(subject) if r.get("name") in ADMIN_ROLES]

    _run_keycloak(run, "get_user_realm_roles")
    return sorted(set(roles))


def _set_realm_roles(subject: str, roles: Any) -> None:
    if not isinstance(roles, list):
        raise ValidationError("roles must be a list")
    requested = {str(r) for r in roles}
    invalid = requested - ADMIN_ROLES
    if invalid:
        raise ValidationError("unknown realm role", details={"roles": sorted(invalid)})
    desired = requested
    current = set(_keycloak_roles_strict(subject))
    for role in desired - current:
        _run_keycloak(lambda kc, role=role: kc.assign_realm_role(subject, role), "assign_realm_role")
    for role in current - desired:
        if role == ROLE_ADMIN:
            continue
        _run_keycloak(lambda kc, role=role: kc.remove_realm_role(subject, role), "remove_realm_role")


def _sync_keycloak_membership(subject: str, sector_code: str, role: str, *, add: bool) -> None:
    group_path = f"/tickora/sectors/{sector_code}/{'chiefs' if role == 'chief' else 'members'}"
    def run(kc: KeycloakAdminClient) -> None:
        group = kc.find_group_by_path(group_path)
        if not group:
            logger.warning("keycloak group not found", extra={"group_path": group_path})
            return
        if add:
            kc.add_user_to_group(subject, group["id"])
        else:
            kc.remove_user_from_group(subject, group["id"])
    _try_keycloak(run, "sync_membership")


def _keycloak_group_tree() -> dict[str, Any] | None:
    groups: list[dict[str, Any]] = []
    _try_keycloak(lambda kc: groups.extend(kc.list_groups()), "list_groups")
    if not groups:
        return None
    
    # Filter: only show the 'tickora' group branch
    tickora_branch = next((g for g in groups if g.get("name") == "tickora"), None)
    if not tickora_branch:
        return None

    return _normalize_group(tickora_branch)


def _normalize_group(group: dict[str, Any]) -> dict[str, Any]:
    children = group.get("subGroups") or group.get("subgroups") or []
    return {
        "key": group.get("id") or group.get("path") or group.get("name"),
        "title": group.get("path") or group.get("name"),
        "children": [_normalize_group(g) for g in children],
    }


def _try_keycloak(fn, operation: str) -> None:
    try:
        fn(KeycloakAdminClient.get())
    except Exception as exc:
        logger.warning("keycloak admin operation failed", extra={"operation": operation, "error": str(exc)})


def _run_keycloak(fn, operation: str) -> None:
    try:
        fn(KeycloakAdminClient.get())
    except Exception as exc:
        logger.warning("keycloak admin operation failed", extra={"operation": operation, "error": str(exc)})
        raise BusinessRuleError(
            f"keycloak admin operation failed: {operation}",
            details={"operation": operation},
        ) from exc


def _validate_membership_role(role: str) -> str:
    role = str(role or "").strip().lower()
    if role not in MEMBERSHIP_ROLES:
        raise ValidationError("role must be member or chief")
    return role


def _ticket_by_ref(db: Session, ticket_ref: str) -> Ticket:
    ticket = db.get(Ticket, ticket_ref) if _looks_like_uuid(ticket_ref) else None
    if ticket is None:
        ticket = db.scalar(select(Ticket).where(Ticket.ticket_code == ticket_ref))
    if ticket is None or ticket.is_deleted:
        raise NotFoundError("ticket not found")
    return ticket


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(str(value))
        return True
    except ValueError:
        return False


def _rows_to_breakdown(rows) -> list[dict[str, Any]]:
    return [{"key": key or "none", "count": int(count or 0)} for key, count in rows]


def _count(db: Session, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _dt(value) -> str | None:
    return value.isoformat() if value else None


# ── Categories / Subcategories / Subcategory Fields ─────────────────────────

def list_categories(db: Session, principal: Principal) -> list[dict[str, Any]]:
    """Admin view: every category (active and inactive) with their subcategories
    and the per-subcategory field catalogue. Returned as a single payload so
    the admin UI can render the full tree without N+1 round-trips."""
    require_admin(principal)
    cats = list(db.scalars(select(Category).order_by(Category.name.asc())))
    subs_by_cat: dict[str, list[Subcategory]] = {}
    for s in db.scalars(
        select(Subcategory).order_by(Subcategory.display_order.asc(), Subcategory.name.asc())
    ):
        subs_by_cat.setdefault(s.category_id, []).append(s)
    fields_by_sub: dict[str, list[SubcategoryFieldDefinition]] = {}
    for f in db.scalars(
        select(SubcategoryFieldDefinition).order_by(
            SubcategoryFieldDefinition.display_order.asc(),
            SubcategoryFieldDefinition.label.asc(),
        )
    ):
        fields_by_sub.setdefault(f.subcategory_id, []).append(f)
    return [
        {
            "id":          c.id,
            "code":        c.code,
            "name":        c.name,
            "description": c.description,
            "is_active":   c.is_active,
            "subcategories": [
                {
                    "id":            s.id,
                    "code":          s.code,
                    "name":          s.name,
                    "description":   s.description,
                    "display_order": s.display_order,
                    "is_active":     s.is_active,
                    "fields": [_serialize_subcategory_field(f) for f in fields_by_sub.get(s.id, [])],
                }
                for s in subs_by_cat.get(c.id, [])
            ],
        }
        for c in cats
    ]


def upsert_category(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    code = (payload.get("code") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        raise ValidationError("code and name are required")
    cat_id = payload.get("id")
    if cat_id:
        row = db.get(Category, cat_id)
        if row is None:
            raise NotFoundError("category not found")
    else:
        row = db.scalar(select(Category).where(Category.code == code))
        if row is None:
            row = Category(code=code, name=name)
            db.add(row)
    row.code = code
    row.name = name
    row.description = payload.get("description") or None
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessRuleError(f"a category with code '{code}' already exists") from exc
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="category", entity_id=row.id,
        new_value={"code": row.code, "name": row.name, "is_active": row.is_active},
    )
    return {"id": row.id, "code": row.code, "name": row.name, "description": row.description, "is_active": row.is_active}


def delete_category(db: Session, principal: Principal, category_id: str) -> None:
    require_admin(principal)
    row = db.get(Category, category_id)
    if row is None:
        raise NotFoundError("category not found")
    db.delete(row)
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="category", entity_id=category_id,
        old_value={"code": row.code, "name": row.name},
        metadata={"action": "delete"},
    )


def upsert_subcategory(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    category_id = payload.get("category_id")
    if not category_id:
        raise ValidationError("category_id is required")
    cat = db.get(Category, category_id)
    if cat is None:
        raise NotFoundError("category not found")
    code = (payload.get("code") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        raise ValidationError("code and name are required")
    sub_id = payload.get("id")
    if sub_id:
        row = db.get(Subcategory, sub_id)
        if row is None:
            raise NotFoundError("subcategory not found")
    else:
        existing = db.scalar(
            select(Subcategory).where(
                Subcategory.category_id == category_id, Subcategory.code == code,
            )
        )
        if existing is not None:
            row = existing
        else:
            row = Subcategory(category_id=category_id, code=code, name=name)
            db.add(row)
    row.category_id   = category_id
    row.code          = code
    row.name          = name
    row.description   = payload.get("description") or None
    if "display_order" in payload:
        row.display_order = int(payload.get("display_order") or 0)
    if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessRuleError(
            f"a subcategory with code '{code}' already exists in this category"
        ) from exc
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="subcategory", entity_id=row.id,
        new_value={"code": row.code, "name": row.name, "category_id": row.category_id},
    )
    return {
        "id":            row.id,
        "code":          row.code,
        "name":          row.name,
        "description":   row.description,
        "display_order": row.display_order,
        "is_active":     row.is_active,
        "category_id":   row.category_id,
    }


def delete_subcategory(db: Session, principal: Principal, subcategory_id: str) -> None:
    require_admin(principal)
    row = db.get(Subcategory, subcategory_id)
    if row is None:
        raise NotFoundError("subcategory not found")
    db.delete(row)
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="subcategory", entity_id=subcategory_id,
        old_value={"code": row.code, "name": row.name},
        metadata={"action": "delete"},
    )


def upsert_subcategory_field(db: Session, principal: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    require_admin(principal)
    subcategory_id = payload.get("subcategory_id")
    if not subcategory_id:
        raise ValidationError("subcategory_id is required")
    if db.get(Subcategory, subcategory_id) is None:
        raise NotFoundError("subcategory not found")
    key   = (payload.get("key") or "").strip().lower()
    label = (payload.get("label") or "").strip()
    if not key or not label:
        raise ValidationError("key and label are required")
    field_id = payload.get("id")
    if field_id:
        row = db.get(SubcategoryFieldDefinition, field_id)
        if row is None:
            raise NotFoundError("field not found")
    else:
        # Fall back to lookup-by-key so a stale UI that re-submits an
        # existing field (without `id`) still updates instead of tripping
        # the unique constraint with a confusing 500.
        existing = db.scalar(
            select(SubcategoryFieldDefinition).where(
                SubcategoryFieldDefinition.subcategory_id == subcategory_id,
                SubcategoryFieldDefinition.key == key,
            )
        )
        if existing is not None:
            row = existing
        else:
            row = SubcategoryFieldDefinition(subcategory_id=subcategory_id, key=key, label=label)
            db.add(row)
    row.subcategory_id = subcategory_id
    row.key            = key
    row.label          = label
    row.value_type     = (payload.get("value_type") or "string").strip()
    row.options        = payload.get("options") or None
    row.is_required    = bool(payload.get("is_required"))
    row.description    = payload.get("description") or None
    if "display_order" in payload:
        row.display_order = int(payload.get("display_order") or 0)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessRuleError(
            f"a field with key '{key}' already exists on this subcategory"
        ) from exc
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="subcategory_field_definition", entity_id=row.id,
        new_value={
            "key": row.key, "label": row.label, "value_type": row.value_type,
            "is_required": row.is_required, "subcategory_id": row.subcategory_id,
        },
    )
    return _serialize_subcategory_field(row)


def delete_subcategory_field(db: Session, principal: Principal, field_id: str) -> None:
    require_admin(principal)
    row = db.get(SubcategoryFieldDefinition, field_id)
    if row is None:
        raise NotFoundError("field not found")
    db.delete(row)
    audit_service.record(
        db, actor=principal, action=events.CONFIG_CHANGED,
        entity_type="subcategory_field_definition", entity_id=field_id,
        old_value={"key": row.key, "label": row.label},
        metadata={"action": "delete"},
    )


def _serialize_subcategory_field(f: SubcategoryFieldDefinition) -> dict[str, Any]:
    return {
        "id":            f.id,
        "subcategory_id": f.subcategory_id,
        "key":           f.key,
        "label":         f.label,
        "value_type":    f.value_type,
        "options":       f.options,
        "is_required":   f.is_required,
        "display_order": f.display_order,
        "description":   f.description,
    }
