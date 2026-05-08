"""Dashboard aggregate queries.

The first implementation uses live indexed aggregates. Materialized views can
replace these helpers later without changing the API contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from framework.commons.logger import logger
from sqlalchemy import case, func, or_, select, text as sa_text
from sqlalchemy.orm import Session

from src.core.errors import NotFoundError, PermissionDeniedError
from src.core.spans import set_attr, span
from src.iam import rbac
from src.iam.principal import Principal
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, SectorMembership, Ticket
from src.ticketing.service.ticket_service import _visibility_filter

ACTIVE_STATUSES = ("pending", "assigned_to_sector", "in_progress", "waiting_for_user", "on_hold", "reopened")
DONE_STATUSES = ("done", "closed")


def overview(db: Session, principal: Principal) -> dict[str, Any]:
    with span("dashboard.overview", username=principal.username, user_id=principal.user_id) as current:
        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "global": None,
            "distributor": None,
            "sectors": [],
            "personal": personal(db, principal, principal.user_id),
            "beneficiary": beneficiary(db, principal),
            "timeseries": timeseries(db, principal),
        }
        if rbac.can_view_global_dashboard(principal):
            payload["global"] = global_(db, principal)
            payload["sectors"] = sectors(db, principal)
        elif principal.sector_memberships:
            payload["sectors"] = sectors(db, principal)

        if principal.is_distributor or principal.is_admin:
            payload["distributor"] = distributor(db, principal)

        set_attr(current, "dashboard.has_global", bool(payload["global"]))
        set_attr(current, "dashboard.sector_count", len(payload["sectors"]))
        return payload


def global_(db: Session, principal: Principal) -> dict[str, Any]:
    if not rbac.can_view_global_dashboard(principal):
        raise PermissionDeniedError("not allowed to view global dashboard")
    logger.info("dashboard global requested", username=principal.username)
    
    # Use materialized view for KPIs
    mv = db.execute(select(sa_text("*")).select_from(sa_text("mv_dashboard_global_kpis"))).first()
    
    kpis = {
        "total_tickets": int(mv.total_tickets) if mv else 0,
        "active_tickets": int(mv.active_tickets) if mv else 0,
        "new_today": int(mv.new_today) if mv else 0,
        "closed_today": int(mv.closed_today) if mv else 0,
        "sla_breached": int(mv.sla_breached) if mv else 0,
        "reopened": int(mv.reopened) if mv else 0,
        "avg_assignment_minutes": round(float(mv.avg_assignment_minutes), 1) if mv and mv.avg_assignment_minutes else None,
        "avg_resolution_minutes": round(float(mv.avg_resolution_minutes), 1) if mv and mv.avg_resolution_minutes else None,
    }
    
    return {
        "kpis": kpis,
        "by_status": _breakdown(db, Ticket.status),
        "by_priority": _breakdown(db, Ticket.priority),
        "by_beneficiary_type": _breakdown(db, Ticket.beneficiary_type),
        "by_category": _breakdown(db, Ticket.category),
        "by_sector": _sector_breakdown(db),
        "top_backlog_sectors": _sector_breakdown(db, active_only=True, limit=5),
    }


def distributor(db: Session, principal: Principal) -> dict[str, Any]:
    if not (principal.is_admin or principal.is_distributor):
        raise PermissionDeniedError("not allowed to view distributor dashboard")
    return {
        "kpis": {
            "pending_review": _count(db, _ticket_stmt().where(Ticket.status == "pending")),
            "assigned_to_sector": _count(db, _ticket_stmt().where(Ticket.status == "assigned_to_sector")),
            "unrouted": _count(db, _ticket_stmt().where(Ticket.current_sector_id.is_(None), Ticket.status == "pending")),
            "critical_pending": _count(db, _ticket_stmt().where(Ticket.priority == "critical", Ticket.status.in_(("pending", "assigned_to_sector")))),
        },
        "by_priority": _breakdown(db, Ticket.priority, status=("pending", "assigned_to_sector")),
        "by_category": _breakdown(db, Ticket.category, status=("pending", "assigned_to_sector")),
        "oldest": _oldest_tickets(db, status=("pending", "assigned_to_sector"), limit=8),
    }


def sectors(db: Session, principal: Principal) -> list[dict[str, Any]]:
    allowed_codes: set[str] | None = None
    if not rbac.can_view_global_dashboard(principal):
        allowed_codes = principal.all_sectors
    stmt = select(Sector).where(Sector.is_active.is_(True)).order_by(Sector.code.asc())
    if allowed_codes is not None:
        stmt = stmt.where(Sector.code.in_(allowed_codes))
    rows = list(db.scalars(stmt))
    return [sector(db, principal, s.code) for s in rows]


def sector(db: Session, principal: Principal, sector_code: str) -> dict[str, Any]:
    if not rbac.can_view_sector_dashboard(principal, sector_code):
        raise PermissionDeniedError("not allowed to view sector dashboard")
    sector_row = db.scalar(select(Sector).where(Sector.code == sector_code, Sector.is_active.is_(True)))
    if sector_row is None:
        raise NotFoundError("sector not found")
    # Use materialized view for KPIs
    mv = db.execute(
        select(sa_text("*"))
        .select_from(sa_text("mv_dashboard_sector_kpis"))
        .where(sa_text(f"current_sector_id = '{sector_row.id}'"))
    ).first()

    kpis = {
        "active": int(mv.active) if mv else 0,
        "unassigned": int(mv.unassigned) if mv else 0,
        "done": int(mv.done) if mv else 0,
        "sla_breached": int(mv.sla_breached) if mv else 0,
        "reopened": int(mv.reopened) if mv else 0,
        "avg_resolution_minutes": round(float(mv.avg_resolution_minutes), 1) if mv and mv.avg_resolution_minutes else None,
    }

    return {
        "sector_code": sector_row.code,
        "sector_name": sector_row.name,
        "kpis": kpis,
        "by_status": _breakdown(db, Ticket.status, sector_id=sector_row.id),
        "by_priority": _breakdown(db, Ticket.priority, sector_id=sector_row.id),
        "by_category": _breakdown(db, Ticket.category, sector_id=sector_row.id),
        "workload": _workload(db, sector_row.id),
        "oldest": _oldest_tickets(db, sector_id=sector_row.id, status=ACTIVE_STATUSES, limit=5),
    }


def personal(db: Session, principal: Principal, user_id: str) -> dict[str, Any]:
    if not _can_view_user_dashboard(db, principal, user_id):
        raise PermissionDeniedError("not allowed to view this user dashboard")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")
    return {
        "user_id": user_id,
        "username": user.username,
        "email": user.email,
        "kpis": {
            "assigned_active": _count(db, _visible_stmt(principal).where(Ticket.assignee_user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES))),
            "assigned_done": _count(db, _visible_stmt(principal).where(Ticket.assignee_user_id == user_id, Ticket.status.in_(DONE_STATUSES))),
            "created_active": _count(db, _visible_stmt(principal).where(Ticket.created_by_user_id == user_id, Ticket.status.in_(ACTIVE_STATUSES))),
            "created_closed": _count(db, _visible_stmt(principal).where(Ticket.created_by_user_id == user_id, Ticket.status == "closed")),
            "reopened": _count(db, _visible_stmt(principal).where(
                or_(Ticket.assignee_user_id == user_id, Ticket.created_by_user_id == user_id),
                Ticket.reopened_count > 0,
            )),
        },
        "by_status": _breakdown_visible(db, principal, Ticket.status, user_id=user_id),
        "oldest": _oldest_tickets(db, principal=principal, assignee_user_id=user_id, status=ACTIVE_STATUSES, limit=5),
    }


def beneficiary(db: Session, principal: Principal) -> dict[str, Any]:
    user_beneficiary_ids = select(Beneficiary.id).where(Beneficiary.user_id == principal.user_id)
    base = _visible_stmt(principal).where(
        or_(Ticket.created_by_user_id == principal.user_id, Ticket.beneficiary_id.in_(user_beneficiary_ids))
    )
    return {
        "kpis": {
            "active": _count(db, base.where(Ticket.status.in_(ACTIVE_STATUSES))),
            "closed": _count(db, base.where(Ticket.status == "closed")),
            "waiting_confirmation": _count(db, base.where(Ticket.status == "done")),
            "reopened": _count(db, base.where(Ticket.reopened_count > 0)),
        },
        "by_status": _breakdown_visible(db, principal, Ticket.status, requester_user_id=principal.user_id),
    }


def sla(db: Session, principal: Principal) -> dict[str, Any]:
    base = _visible_stmt(principal)
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    return {
        "breached": _count(db, base.where(Ticket.sla_status == "breached")),
        "due_24h": _count(db, base.where(Ticket.sla_due_at.is_not(None), Ticket.sla_due_at <= soon, Ticket.status.in_(ACTIVE_STATUSES))),
        "by_status": _breakdown_visible(db, principal, Ticket.sla_status),
    }


def timeseries(db: Session, principal: Principal, *, days: int = 14) -> list[dict[str, Any]]:
    start = _today_start() - timedelta(days=days - 1)
    created_rows = _daily_counts(db, _visible_stmt(principal), Ticket.created_at, start)
    closed_rows = _daily_counts(db, _visible_stmt(principal), Ticket.closed_at, start)
    points = []
    for i in range(days):
        day = (start + timedelta(days=i)).date().isoformat()
        points.append({"date": day, "created": created_rows.get(day, 0), "closed": closed_rows.get(day, 0)})
    return points


def _ticket_stmt():
    return select(Ticket).where(Ticket.is_deleted.is_(False))


def _visible_stmt(principal: Principal):
    stmt = _ticket_stmt()
    vis = _visibility_filter(principal)
    if vis is not None:
        stmt = stmt.where(vis)
    return stmt


def _count(db: Session, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _avg_minutes(db: Session, start_col, end_col, *, sector_id: str | None = None) -> float | None:
    stmt = select(func.avg(func.extract("epoch", end_col - start_col) / 60)).where(
        Ticket.is_deleted.is_(False),
        start_col.is_not(None),
        end_col.is_not(None),
    )
    if sector_id:
        stmt = stmt.where(Ticket.current_sector_id == sector_id)
    value = db.scalar(stmt)
    return round(float(value), 1) if value is not None else None


def _breakdown(db: Session, column, *, sector_id: str | None = None, status: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    stmt = select(column, func.count(Ticket.id)).where(Ticket.is_deleted.is_(False))
    if sector_id:
        stmt = stmt.where(Ticket.current_sector_id == sector_id)
    if status:
        stmt = stmt.where(Ticket.status.in_(status))
    stmt = stmt.group_by(column).order_by(func.count(Ticket.id).desc())
    return [{"key": key or "unset", "count": int(count)} for key, count in db.execute(stmt).all()]


def _breakdown_visible(
    db: Session,
    principal: Principal,
    column,
    *,
    user_id: str | None = None,
    requester_user_id: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(column, func.count(Ticket.id)).select_from(Ticket).where(Ticket.is_deleted.is_(False))
    vis = _visibility_filter(principal)
    if vis is not None:
        stmt = stmt.where(vis)
    if user_id:
        stmt = stmt.where(or_(Ticket.assignee_user_id == user_id, Ticket.created_by_user_id == user_id))
    if requester_user_id:
        beneficiary_ids = select(Beneficiary.id).where(Beneficiary.user_id == requester_user_id)
        stmt = stmt.where(or_(Ticket.created_by_user_id == requester_user_id, Ticket.beneficiary_id.in_(beneficiary_ids)))
    stmt = stmt.group_by(column).order_by(func.count(Ticket.id).desc())
    return [{"key": key or "unset", "count": int(count)} for key, count in db.execute(stmt).all()]


def _sector_breakdown(db: Session, *, active_only: bool = False, limit: int | None = None) -> list[dict[str, Any]]:
    stmt = (
        select(Sector.code, Sector.name, func.count(Ticket.id))
        .join(Ticket, Ticket.current_sector_id == Sector.id)
        .where(Ticket.is_deleted.is_(False))
        .group_by(Sector.code, Sector.name)
        .order_by(func.count(Ticket.id).desc())
    )
    if active_only:
        stmt = stmt.where(Ticket.status.in_(ACTIVE_STATUSES))
    if limit:
        stmt = stmt.limit(limit)
    return [{"sector_code": code, "sector_name": name, "count": int(count)} for code, name, count in db.execute(stmt).all()]


def _workload(db: Session, sector_id: str) -> list[dict[str, Any]]:
    assignee = func.coalesce(Ticket.assignee_user_id, "unassigned")
    done_count = func.sum(case((Ticket.status.in_(DONE_STATUSES), 1), else_=0))
    active_count = func.sum(case((Ticket.status.in_(ACTIVE_STATUSES), 1), else_=0))
    stmt = (
        select(assignee, active_count, done_count)
        .where(Ticket.is_deleted.is_(False), Ticket.current_sector_id == sector_id)
        .group_by(assignee)
        .order_by(active_count.desc())
    )
    return [
        {"assignee_user_id": assignee_id, "active": int(active or 0), "done": int(done or 0)}
        for assignee_id, active, done in db.execute(stmt).all()
    ]


def _oldest_tickets(
    db: Session,
    *,
    principal: Principal | None = None,
    sector_id: str | None = None,
    assignee_user_id: str | None = None,
    status: tuple[str, ...] = ACTIVE_STATUSES,
    limit: int = 5,
) -> list[dict[str, Any]]:
    stmt = _visible_stmt(principal) if principal else _ticket_stmt()
    stmt = stmt.where(Ticket.status.in_(status))
    if sector_id:
        stmt = stmt.where(Ticket.current_sector_id == sector_id)
    if assignee_user_id:
        stmt = stmt.where(Ticket.assignee_user_id == assignee_user_id)
    rows = db.scalars(stmt.order_by(Ticket.created_at.asc()).limit(limit))
    return [
        {
            "id": t.id,
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


def _daily_counts(db: Session, stmt, column, start: datetime) -> dict[str, int]:
    base = stmt.where(column.is_not(None), column >= start).subquery()
    col = base.c.get(column.key)
    day = func.date_trunc("day", col).label("day")
    rows = db.execute(select(day, func.count()).select_from(base).group_by(day)).all()
    return {value.date().isoformat(): int(count) for value, count in rows if value}


def _can_view_user_dashboard(db: Session, principal: Principal, user_id: str) -> bool:
    if user_id == principal.user_id or principal.is_admin or principal.is_auditor:
        return True
    if not principal.chief_sectors:
        return False
    membership = db.scalar(
        select(SectorMembership.id)
        .join(Sector, Sector.id == SectorMembership.sector_id)
        .where(
            SectorMembership.user_id == user_id,
            SectorMembership.is_active.is_(True),
            Sector.code.in_(principal.chief_sectors),
        )
    )
    return membership is not None
