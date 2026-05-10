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
from src.common.spans import set_attr, span
from src.iam import rbac
from src.iam.principal import Principal
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, SectorMembership, Ticket, TicketComment, TicketStatusHistory
from src.ticketing.service.ticket_service import _visibility_filter
from src.ticketing.state_machine import ACTIVE_STATUSES, DONE_STATUSES


def monitor_overview(db: Session, principal: Principal, *, days: int = 30) -> dict[str, Any]:
    """Top-level monitor payload with per-principal aggregates.

    On large datasets (millions of tickets) the underlying aggregates take
    seconds. We memoize the response in Redis for 60s, keyed by the principal's
    visibility class so two users with the same access profile share the same
    cached payload. A blip in Redis falls back to a live computation.

    The cache key intentionally excludes things that don't change visibility
    (display name, last_login, etc.) so cardinality stays bounded.
    """
    cache_parts = (
        "v1",
        days,
        principal.user_id if not (principal.is_admin or principal.is_auditor) else "global",
        ",".join(sorted(principal.global_roles)),
        ",".join(sorted(principal.all_sectors)) if principal.all_sectors else "",
    )

    def _produce() -> dict[str, Any]:
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

    from src.common.cache import cached_call
    return cached_call(
        namespace="monitor.overview",
        key_parts=cache_parts,
        ttl=60,
        producer=_produce,
    )


def monitor_global(db: Session, principal: Principal) -> dict[str, Any]:
    """Global aggregate payload (admin / auditor only).

    The 9 sub-queries below each scan the full `tickets` table, so on
    1M+ rows this takes seconds when nothing is cached. We memoise the
    *entire* payload for 5 minutes — admins rarely need second-by-second
    freshness on a "total tickets" headline, and the cache is shared
    across every admin/auditor (no per-user variation).

    The `monitor.overview` outer cache (60 s) sits on top of this; with
    both warm, an overview hit is two Redis GETs.
    """
    if not rbac.can_view_global_dashboard(principal):
        raise PermissionDeniedError("not allowed to view global monitor")
    logger.info("monitor global requested", extra={"username": principal.username})

    def _produce() -> dict[str, Any]:
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

    from src.common.cache import cached_call
    return cached_call(
        namespace="monitor.global",
        key_parts=("v1",),  # global → single bucket
        ttl=300,
        producer=_produce,
    )


def monitor_distributor(db: Session, principal: Principal) -> dict[str, Any]:
    """Distributor triage view. Cached for 2 minutes globally — every
    distributor sees the same data (no per-user filter), and a 2-minute
    staleness window beats paying ~6 full-scan queries per overview.
    """
    if not (principal.is_admin or principal.is_distributor):
        raise PermissionDeniedError("not allowed to view distributor monitor")

    from src.common.cache import cached_call

    def _produce() -> dict[str, Any]:
        return _build_monitor_distributor(db)

    return cached_call(
        namespace="monitor.distributor",
        key_parts=("v1",),
        ttl=120,
        producer=_produce,
    )


def _build_monitor_distributor(db: Session) -> dict[str, Any]:
    threshold_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # Tickets transitioned out of pending in the last 24 h. Build the inner
    # query as a `select()` (not `.subquery()`) so SQLAlchemy can inline it
    # as a proper IN-list and we don't get the
    # "Coercing Subquery into a select() for use in IN()" warning.
    reviewed_today_select = (
        select(TicketStatusHistory.ticket_id)
        .where(
            TicketStatusHistory.old_status == "pending",
            TicketStatusHistory.created_at >= threshold_24h,
        )
        .distinct()
    )
    reviewed_today_stmt = _ticket_stmt().where(Ticket.id.in_(reviewed_today_select))

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
    """Cached entry to the per-sector aggregates (2-minute TTL).

    Cache key partitions on the principal's allowed sector set so admin
    (sees all) and a chief (sees their sectors only) get different
    payloads. The `_build_monitor_sectors` helper underneath does the
    grouped-aggregate work.
    """
    from src.common.cache import cached_call
    if rbac.can_view_global_dashboard(principal):
        scope_key = "global"
    else:
        scope_key = "sectors:" + ",".join(sorted(principal.all_sectors))

    return cached_call(
        namespace="monitor.sectors",
        key_parts=("v1", scope_key),
        ttl=120,
        producer=lambda: _build_monitor_sectors(db, principal),
    )


def _build_monitor_sectors(db: Session, principal: Principal) -> list[dict[str, Any]]:
    """List per-sector KPIs and breakdowns.

    Used to be O(sectors × 7) queries — every visible sector triggered
    `monitor_sector`, which in turn issued ~7 separate aggregates. We now
    answer the headline KPIs and the by-status / by-priority / by-category
    breakdowns with **three** total grouped queries (KPI sums, status
    breakdown, priority breakdown), then hydrate per-sector workload
    individually because that join is sector-scoped by nature.

    The expensive bottleneck-analysis + stale-tickets queries used to run
    per sector; now they're computed only when an explicit
    `monitor_sector(code)` call requests them. The aggregate response keeps
    the same shape so existing frontend code doesn't break.
    """
    allowed_codes: set[str] | None = None
    if not rbac.can_view_global_dashboard(principal):
        allowed_codes = principal.all_sectors
    stmt = select(Sector).where(Sector.is_active.is_(True)).order_by(Sector.code.asc())
    if allowed_codes is not None:
        stmt = stmt.where(Sector.code.in_(allowed_codes))
    sectors = list(db.scalars(stmt))
    if not sectors:
        return []

    sector_ids = [s.id for s in sectors]
    kpis_by_sector = _bulk_sector_kpis(db, sector_ids)
    by_status_by_sector = _bulk_sector_breakdown(db, sector_ids, Ticket.status)
    by_priority_by_sector = _bulk_sector_breakdown(db, sector_ids, Ticket.priority)
    by_category_by_sector = _bulk_sector_breakdown(db, sector_ids, Ticket.category)

    out: list[dict[str, Any]] = []
    for s in sectors:
        out.append({
            "sector_code": s.code,
            "sector_name": s.name,
            "kpis": kpis_by_sector.get(s.id, _empty_sector_kpis()),
            "by_status":   by_status_by_sector.get(s.id, []),
            "by_priority": by_priority_by_sector.get(s.id, []),
            "by_category": by_category_by_sector.get(s.id, []),
            # `workload` is sector-local; the bulk path doesn't help much.
            # `oldest`/`stale_tickets`/`bottleneck_analysis` are deferred
            # until the user picks a specific sector — they were the most
            # expensive part of the per-sector loop.
            "workload": _workload(db, s.id),
            "oldest": [],
            "stale_tickets": [],
            "bottleneck_analysis": [],
        })
    return out


def _empty_sector_kpis() -> dict[str, int | float | None]:
    return {
        "active": 0,
        "unassigned": 0,
        "done": 0,
        "sla_breached": 0,
        "reopened": 0,
        "avg_resolution_minutes": None,
    }


def _bulk_sector_kpis(db: Session, sector_ids: list[str]) -> dict[str, dict[str, Any]]:
    """One grouped query producing every sector's KPIs at once."""
    if not sector_ids:
        return {}
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
    rows = db.execute(
        select(
            Ticket.current_sector_id,
            active_count, unassigned, done_count, sla_breached, reopened, avg_resolution,
        )
        .where(Ticket.is_deleted.is_(False), Ticket.current_sector_id.in_(sector_ids))
        .group_by(Ticket.current_sector_id)
    ).all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid, active, unas, done, breached, reop, avg = row
        out[sid] = {
            "active": int(active or 0),
            "unassigned": int(unas or 0),
            "done": int(done or 0),
            "sla_breached": int(breached or 0),
            "reopened": int(reop or 0),
            "avg_resolution_minutes": round(float(avg), 1) if avg is not None else None,
        }
    return out


def _bulk_sector_breakdown(
    db: Session,
    sector_ids: list[str],
    column,
) -> dict[str, list[dict[str, Any]]]:
    """One grouped query producing `column` breakdowns for every sector."""
    if not sector_ids:
        return {}
    rows = db.execute(
        select(Ticket.current_sector_id, column, func.count(Ticket.id))
        .where(Ticket.is_deleted.is_(False), Ticket.current_sector_id.in_(sector_ids))
        .group_by(Ticket.current_sector_id, column)
    ).all()
    out: dict[str, list[dict[str, Any]]] = {}
    for sid, key, count in rows:
        out.setdefault(sid, []).append({"key": key or "unset", "count": int(count)})
    # Sort each sector's breakdown by count desc to match the per-sector helper.
    for sid in out:
        out[sid].sort(key=lambda r: r["count"], reverse=True)
    return out


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
    """Per-user monitor payload.

    Used to issue 9 separate `COUNT(*)` queries (5 operator-side, 4
    beneficiary-side). We now collapse each side into a single
    `SUM(CASE WHEN …)` query, dropping 9 round-trips to 2 plus the two
    breakdowns. On the 1M-row dataset this is the difference between
    "noticeable" and "instant" for the personal panel.
    """
    if not _can_view_user_dashboard(db, principal, user_id):
        raise PermissionDeniedError("not allowed to view this user monitor")
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("user not found")

    # ── Operator-side KPIs (one query) ─────────────────────────────────────
    op_base = _visible_stmt(principal).with_only_columns(Ticket.id).where(
        or_(Ticket.assignee_user_id == user_id, Ticket.created_by_user_id == user_id),
    ).subquery()
    # We re-query the underlying ticket rows to evaluate the SUM(CASE)s.
    op_stmt = (
        select(
            func.sum(case((
                (Ticket.assignee_user_id == user_id) & Ticket.status.in_(ACTIVE_STATUSES), 1
            ), else_=0)),
            func.sum(case((
                (Ticket.assignee_user_id == user_id) & Ticket.status.in_(DONE_STATUSES), 1
            ), else_=0)),
            func.sum(case((
                (Ticket.created_by_user_id == user_id) & Ticket.status.in_(ACTIVE_STATUSES), 1
            ), else_=0)),
            func.sum(case((
                (Ticket.created_by_user_id == user_id) & (Ticket.status == "closed"), 1
            ), else_=0)),
            func.sum(case((
                (
                    (Ticket.assignee_user_id == user_id)
                    | (Ticket.created_by_user_id == user_id)
                )
                & (Ticket.reopened_count > 0),
                1,
            ), else_=0)),
        )
        .where(Ticket.id.in_(select(op_base.c.id)))
    )
    op_row = db.execute(op_stmt).one()

    # ── Requester-side KPIs (one query) ────────────────────────────────────
    user_beneficiary_ids = select(Beneficiary.id).where(Beneficiary.user_id == user_id)
    req_base_stmt = _visible_stmt(principal).with_only_columns(Ticket.id).where(
        or_(Ticket.created_by_user_id == user_id, Ticket.beneficiary_id.in_(user_beneficiary_ids))
    ).subquery()
    req_stmt = (
        select(
            func.sum(case((Ticket.status.in_(ACTIVE_STATUSES), 1), else_=0)),
            func.sum(case((Ticket.status == "closed", 1), else_=0)),
            func.sum(case((Ticket.status == "done", 1), else_=0)),
            func.sum(case((Ticket.reopened_count > 0, 1), else_=0)),
        )
        .where(Ticket.id.in_(select(req_base_stmt.c.id)))
    )
    req_row = db.execute(req_stmt).one()

    return {
        "user_id": user_id,
        "username": user.username,
        "email": user.email,
        "kpis": {
            "assigned_active": int(op_row[0] or 0),
            "assigned_done":   int(op_row[1] or 0),
            "created_active":  int(op_row[2] or 0),
            "created_closed":  int(op_row[3] or 0),
            "reopened":        int(op_row[4] or 0),
        },
        "beneficiary_kpis": {
            "active":               int(req_row[0] or 0),
            "closed":               int(req_row[1] or 0),
            "waiting_confirmation": int(req_row[2] or 0),
            "reopened":             int(req_row[3] or 0),
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
    """Analyzes status transition history to identify stages where tickets linger longest.

    Calculates average time spent in each status for recently closed tickets.

    Args:
        db: Database session.
        sector_id: Optional filter for a specific sector.
        days: Historical lookback period.

    Returns:
        List of dictionaries with status keys and average duration in minutes.
    """
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
