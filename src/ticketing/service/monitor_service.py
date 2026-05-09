"""Monitor aggregate queries (previously Dashboard).

The first implementation uses live indexed aggregates. Materialized views can
replace these helpers later without changing the API contract.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from framework.commons.logger import logger
from sqlalchemy import case, func, or_, select, cast as sa_cast, Text as sa_Text
from sqlalchemy.orm import Session

from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.core.spans import set_attr, span
from src.iam import rbac
from src.iam.principal import Principal
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, SectorMembership, Ticket, TicketComment, TicketStatusHistory
from src.ticketing.service.ticket_service import _visibility_filter

ACTIVE_STATUSES = ("pending", "assigned_to_sector", "in_progress", "reopened")
DONE_STATUSES = ("done", "closed")


def monitor_overview(db: Session, principal: Principal, *, days: int = 30) -> dict[str, Any]:
    with span("monitor.overview", username=principal.username, user_id=principal.user_id) as current:
        payload: dict[str, Any] = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "global": None,
            "distributor": None,
            "sectors": [],
            "personal": monitor_personal(db, principal, principal.user_id),
            "timeseries": monitor_timeseries(db, principal, days=days),
            "stale_tickets": _stale_tickets(db, principal),
        }
        if rbac.can_view_global_dashboard(principal):
            payload["global"] = monitor_global(db, principal)
            payload["sectors"] = monitor_sectors(db, principal)
        elif principal.sector_memberships:
            payload["sectors"] = monitor_sectors(db, principal)

        if principal.is_distributor or principal.is_admin:
            payload["distributor"] = monitor_distributor(db, principal)

        set_attr(current, "monitor.has_global", bool(payload["global"]))
        set_attr(current, "monitor.sector_count", len(payload["sectors"]))
        return payload


def monitor_global(db: Session, principal: Principal) -> dict[str, Any]:
    if not rbac.can_view_global_dashboard(principal):
        raise PermissionDeniedError("not allowed to view global monitor")
    logger.info("monitor global requested", extra={"username": principal.username})

    return {
        "kpis": _global_kpis(db),
        "by_status": _breakdown(db, Ticket.status),
        "by_priority": _breakdown(db, Ticket.priority),
        "by_beneficiary_type": _breakdown(db, Ticket.beneficiary_type),
        "by_category": _breakdown(db, Ticket.category),
        "by_sector": _sector_breakdown(db),
        "top_backlog_sectors": _sector_breakdown(db, active_only=True, limit=5),
        "stale_tickets": _stale_tickets(db, principal, hours=24, limit=10),
        "bottleneck_analysis": _bottleneck_analysis(db, days=30),
    }


def monitor_distributor(db: Session, principal: Principal) -> dict[str, Any]:
    if not (principal.is_admin or principal.is_distributor):
        raise PermissionDeniedError("not allowed to view distributor monitor")

    threshold_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # Tickets transitioned out of pending today
    reviewed_today_sub = (
        select(TicketStatusHistory.ticket_id)
        .where(
            TicketStatusHistory.old_status == "pending",
            TicketStatusHistory.created_at >= threshold_24h
        )
        .distinct()
        .subquery()
    )

    reviewed_today_stmt = _ticket_stmt().where(Ticket.id.in_(reviewed_today_sub))

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
        "not_reviewed": _oldest_tickets(db, status=("pending",), limit=20),
        "reviewed_today": [
            {
                "id": t.id,
                "ticket_code": t.ticket_code,
                "title": t.title,
                "status": t.status,
                "priority": t.priority,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in db.scalars(reviewed_today_stmt.order_by(Ticket.updated_at.desc()).limit(20))
        ]
    }


def monitor_sectors(db: Session, principal: Principal) -> list[dict[str, Any]]:
    allowed_codes: set[str] | None = None
    if not rbac.can_view_global_dashboard(principal):
        allowed_codes = principal.all_sectors
    stmt = select(Sector).where(Sector.is_active.is_(True)).order_by(Sector.code.asc())
    if allowed_codes is not None:
        stmt = stmt.where(Sector.code.in_(allowed_codes))
    rows = list(db.scalars(stmt))
    return [monitor_sector(db, principal, s.code) for s in rows]


def monitor_sector(db: Session, principal: Principal, sector_code: str) -> dict[str, Any]:
    if not rbac.can_view_sector_dashboard(principal, sector_code):
        raise PermissionDeniedError("not allowed to view sector monitor")
    sector_row = db.scalar(select(Sector).where(Sector.code == sector_code, Sector.is_active.is_(True)))
    if sector_row is None:
        raise NotFoundError("sector not found")

    return {
        "sector_code": sector_row.code,
        "sector_name": sector_row.name,
        "kpis": _sector_kpis(db, sector_row.id),
        "by_status": _breakdown(db, Ticket.status, sector_id=sector_row.id),
        "by_priority": _breakdown(db, Ticket.priority, sector_id=sector_row.id),
        "by_category": _breakdown(db, Ticket.category, sector_id=sector_row.id),
        "workload": _workload(db, sector_row.id),
        "oldest": _oldest_tickets(db, sector_id=sector_row.id, status=ACTIVE_STATUSES, limit=5),
        "stale_tickets": _stale_tickets(db, principal, sector_id=sector_row.id, hours=24, limit=10),
        "bottleneck_analysis": _bottleneck_analysis(db, sector_id=sector_row.id, days=30),
    }


def monitor_personal(db: Session, principal: Principal, user_id: str) -> dict[str, Any]:
    if not _can_view_user_dashboard(db, principal, user_id):
        raise PermissionDeniedError("not allowed to view this user monitor")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")

    # Requester-side: tickets where user is creator or beneficiary
    user_beneficiary_ids = select(Beneficiary.id).where(Beneficiary.user_id == user_id)
    req_base = _visible_stmt(principal).where(
        or_(Ticket.created_by_user_id == user_id, Ticket.beneficiary_id.in_(user_beneficiary_ids))
    )

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
        "beneficiary_kpis": {
            "active": _count(db, req_base.where(Ticket.status.in_(ACTIVE_STATUSES))),
            "closed": _count(db, req_base.where(Ticket.status == "closed")),
            "waiting_confirmation": _count(db, req_base.where(Ticket.status == "done")),
            "reopened": _count(db, req_base.where(Ticket.reopened_count > 0)),
        },
        "by_status": _breakdown_visible(db, principal, Ticket.status, user_id=user_id),
        "beneficiary_by_status": _breakdown_visible(db, principal, Ticket.status, requester_user_id=user_id),
        "oldest": _oldest_tickets(db, principal=principal, assignee_user_id=user_id, status=ACTIVE_STATUSES, limit=5),
    }


def monitor_sla(db: Session, principal: Principal) -> dict[str, Any]:
    base = _visible_stmt(principal)
    now = datetime.now(timezone.utc)
    soon = now + timedelta(hours=24)
    return {
        "breached": _count(db, base.where(Ticket.sla_status == "breached")),
        "due_24h": _count(db, base.where(Ticket.sla_due_at.is_not(None), Ticket.sla_due_at <= soon, Ticket.status.in_(ACTIVE_STATUSES))),
        "by_status": _breakdown_visible(db, principal, Ticket.sla_status),
    }


def monitor_timeseries(db: Session, principal: Principal, *, days: int = 30) -> list[dict[str, Any]]:
    start = _today_start() - timedelta(days=days - 1)
    created_rows = _daily_counts(db, _visible_stmt(principal), Ticket.created_at, start)
    closed_rows = _daily_counts(db, _daily_stmt(principal, _closed_timestamp(), start), _closed_timestamp(), start)
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


def _daily_stmt(principal: Principal, column, start: datetime):
    return _visible_stmt(principal).where(column.is_not(None), column >= start)


def _count(db: Session, stmt) -> int:
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def _closed_timestamp():
    return func.coalesce(
        Ticket.done_at,
        Ticket.closed_at,
        case((Ticket.status == "closed", Ticket.updated_at), else_=None),
    ).label("closed_timestamp")


def _global_kpis(db: Session) -> dict[str, int | float | None]:
    today = _today_start()
    closed_timestamp = _closed_timestamp()
    active_count = func.sum(case((Ticket.status.in_(ACTIVE_STATUSES), 1), else_=0))
    new_today = func.sum(case((Ticket.created_at >= today, 1), else_=0))
    closed_today = func.sum(case((closed_timestamp >= today, 1), else_=0))
    sla_breached = func.sum(case((Ticket.sla_status == "breached", 1), else_=0))
    reopened = func.sum(case((Ticket.reopened_count > 0, 1), else_=0))
    avg_assignment = func.avg(
        case(
            (Ticket.assigned_at.is_not(None), func.extract("epoch", Ticket.assigned_at - Ticket.created_at) / 60),
            else_=None,
        )
    )
    avg_resolution = func.avg(
        case(
            (Ticket.done_at.is_not(None), func.extract("epoch", Ticket.done_at - Ticket.created_at) / 60),
            else_=None,
        )
    )
    row = db.execute(
        select(
            func.count(Ticket.id),
            active_count,
            new_today,
            closed_today,
            sla_breached,
            reopened,
            avg_assignment,
            avg_resolution,
        )
        .where(Ticket.is_deleted.is_(False))
    ).one()
    return {
        "total_tickets": int(row[0] or 0),
        "active_tickets": int(row[1] or 0),
        "new_today": int(row[2] or 0),
        "closed_today": int(row[3] or 0),
        "sla_breached": int(row[4] or 0),
        "reopened": int(row[5] or 0),
        "avg_assignment_minutes": round(float(row[6]), 1) if row[6] is not None else None,
        "avg_resolution_minutes": round(float(row[7]), 1) if row[7] is not None else None,
    }


def _sector_kpis(db: Session, sector_id: str) -> dict[str, int | float | None]:
    active_count = func.sum(case((Ticket.status.in_(ACTIVE_STATUSES), 1), else_=0))
    unassigned = func.sum(
        case(
            (
                Ticket.assignee_user_id.is_(None) & Ticket.status.in_(ACTIVE_STATUSES),
                1,
            ),
            else_=0,
        )
    )
    done_count = func.sum(case((Ticket.status.in_(DONE_STATUSES), 1), else_=0))
    sla_breached = func.sum(case((Ticket.sla_status == "breached", 1), else_=0))
    reopened = func.sum(case((Ticket.reopened_count > 0, 1), else_=0))
    avg_resolution = func.avg(
        case(
            (Ticket.done_at.is_not(None), func.extract("epoch", Ticket.done_at - Ticket.created_at) / 60),
            else_=None,
        )
    )
    row = db.execute(
        select(active_count, unassigned, done_count, sla_breached, reopened, avg_resolution)
        .where(
            Ticket.is_deleted.is_(False),
            Ticket.current_sector_id == sector_id,
        )
    ).one()
    return {
        "active": int(row[0] or 0),
        "unassigned": int(row[1] or 0),
        "done": int(row[2] or 0),
        "sla_breached": int(row[3] or 0),
        "reopened": int(row[4] or 0),
        "avg_resolution_minutes": round(float(row[5]), 1) if row[5] is not None else None,
    }


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
    assignee_id_col = sa_cast(Ticket.assignee_user_id, sa_Text)
    done_count = func.sum(case((Ticket.status.in_(DONE_STATUSES), 1), else_=0))
    active_count = func.sum(case((Ticket.status.in_(ACTIVE_STATUSES), 1), else_=0))
    
    # We join with User to get usernames. Use outer join to keep 'unassigned'.
    stmt = (
        select(assignee_id_col, User.username, active_count, done_count)
        .outerjoin(User, User.id == Ticket.assignee_user_id)
        .where(Ticket.is_deleted.is_(False), Ticket.current_sector_id == sector_id)
        .group_by(assignee_id_col, User.username)
        .order_by(active_count.desc())
    )
    return [
        {
            "assignee_user_id": assignee_id or "unassigned", 
            "username": username or "Unassigned",
            "active": int(active or 0), 
            "done": int(done or 0)
        }
        for assignee_id, username, active, done in db.execute(stmt).all()
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
    base = (
        stmt.with_only_columns(column.label("bucket_value"))
        .where(column.is_not(None), column >= start)
        .subquery()
    )
    col = base.c.bucket_value
    day = func.date_trunc("day", col).label("day")
    rows = db.execute(select(day, func.count()).select_from(base).group_by(day)).all()
    return {value.date().isoformat(): int(count) for value, count in rows if value}


def _stale_tickets(db: Session, principal: Principal, *, sector_id: str | None = None, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(hours=hours)

    # Subquery: find all ticket_ids that HAVE a recent activity (comments)
    recent_activity = select(TicketComment.ticket_id).where(
        TicketComment.created_at >= threshold,
        TicketComment.is_deleted.is_(False)
    )

    stmt = _visible_stmt(principal).where(
        Ticket.status.in_(ACTIVE_STATUSES),
        Ticket.created_at < threshold,
        ~Ticket.id.in_(recent_activity)
    )
    
    if sector_id:
        stmt = stmt.where(Ticket.current_sector_id == sector_id)

    rows = db.scalars(stmt.order_by(Ticket.created_at.asc()).limit(limit)).all()
    
    return [
        {
            "id": t.id,
            "ticket_code": t.ticket_code,
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat(),
            "last_activity_at": None,
        }
        for t in rows
    ]


def _bottleneck_analysis(db: Session, sector_id: str | None = None, days: int = 30) -> list[dict[str, Any]]:
    threshold = datetime.now(timezone.utc) - timedelta(days=days)

    # We want to find durations of each status.
    # For a given history entry h, the duration of h.old_status is
    # h.created_at - (previous h.created_at OR ticket.created_at).

    # Subquery to get history with previous timestamp
    h = TicketStatusHistory.__table__.alias("h")
    t = Ticket.__table__.alias("t")

    prev_at = func.lag(h.c.created_at).over(partition_by=h.c.ticket_id, order_by=h.c.created_at)
    # If prev_at is null, it means it's the first transition, so use ticket.created_at
    started_at = func.coalesce(prev_at, t.c.created_at)
    duration_sec = func.extract("epoch", h.c.created_at - started_at)

    inner_stmt = (
        select(
            h.c.old_status.label("status"),
            duration_sec.label("duration")
        )
        .join(t, t.c.id == h.c.ticket_id)
        .where(t.c.status == "closed")
        .where(t.c.closed_at >= threshold)
        .where(t.c.is_deleted.is_(False))
    )

    if sector_id:
        inner_stmt = inner_stmt.where(t.c.current_sector_id == sector_id)

    subq = inner_stmt.subquery()

    stmt = (
        select(
            subq.c.status,
            func.avg(subq.c.duration).label("avg_duration_sec"),
            func.count().label("transition_count")
        )
        .group_by(subq.c.status)
        .order_by(func.avg(subq.c.duration).desc())
    )

    results = db.execute(stmt).all()

    return [
        {
            "status": row.status or "pending",
            "avg_minutes": round(float(row.avg_duration_sec) / 60, 1) if row.avg_duration_sec is not None else 0,
            "count": int(row.transition_count)
        }
        for row in results
    ]


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
