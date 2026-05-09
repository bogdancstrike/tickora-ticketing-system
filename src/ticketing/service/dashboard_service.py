"""Customizable dashboards and widgets service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam.principal import Principal
from src.ticketing.models import CustomDashboard, DashboardWidget, WidgetDefinition, Ticket
from src.ticketing.service.ticket_service import _visibility_filter


ACTIVE_STATUSES = ("pending", "assigned_to_sector", "in_progress", "reopened")


def _visible_stmt(principal: Principal):
    stmt = select(Ticket).where(Ticket.is_deleted.is_(False))
    vis = _visibility_filter(principal)
    if vis is not None:
        stmt = stmt.where(vis)
    return stmt


def _check_dashboard_access(p: Principal) -> None:
    # Everyone is allowed to have dashboards now.
    pass


def list_dashboards(db: Session, p: Principal) -> list[dict[str, Any]]:
    _check_dashboard_access(p)
    stmt = select(CustomDashboard).where(CustomDashboard.owner_user_id == p.user_id).order_by(CustomDashboard.created_at.desc())
    rows = list(db.scalars(stmt))
    return [_serialize_dashboard(r) for r in rows]


def get_dashboard(db: Session, p: Principal, dashboard_id: str) -> dict[str, Any]:
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    return _serialize_dashboard(d, full=True)


def create_dashboard(db: Session, p: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _check_dashboard_access(p)
    title = str(payload.get("title") or "New Dashboard").strip()
    
    d = CustomDashboard(
        owner_user_id=p.user_id,
        title=title,
        description=payload.get("description"),
        is_public=bool(payload.get("is_public", False))
    )
    db.add(d)
    db.flush()
    return _serialize_dashboard(d)


def update_dashboard(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    
    if "title" in payload:
        d.title = str(payload["title"]).strip()
    if "description" in payload:
        d.description = payload["description"]
    if "is_public" in payload:
        d.is_public = bool(payload["is_public"])
    
    db.flush()
    return _serialize_dashboard(d)


def delete_dashboard(db: Session, p: Principal, dashboard_id: str) -> None:
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    db.delete(d)
    db.flush()


def upsert_widget(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    
    widget_id = payload.get("id")
    w = None
    if widget_id:
        w = db.get(DashboardWidget, widget_id)
        if w and w.dashboard_id != d.id:
            w = None
    
    if w is None:
        w = DashboardWidget(dashboard_id=d.id, type=payload["type"])
        db.add(w)
    
    if "title" in payload:
        w.title = payload["title"]
    if "config" in payload:
        w.config = payload["config"] or {}
    if "x" in payload: w.x = int(payload["x"])
    if "y" in payload: w.y = int(payload["y"])
    if "w" in payload: w.w = int(payload["w"])
    if "h" in payload: w.h = int(payload["h"])
    
    db.flush()
    return _serialize_widget(w)


def delete_widget(db: Session, p: Principal, dashboard_id: str, widget_id: str) -> None:
    _check_dashboard_access(p)
    w = db.get(DashboardWidget, widget_id)
    if w is None or w.dashboard_id != dashboard_id:
        raise NotFoundError("widget not found")
    
    d = db.get(CustomDashboard, w.dashboard_id)
    if d.owner_user_id != p.user_id:
        raise PermissionDeniedError("not allowed")
    
    db.delete(w)
    db.flush()


def sync_widget_catalogue(db: Session) -> None:
    """Seed the database with the standard widget catalogue."""
    catalogue = [
        ("ticket_list", "Ticket List", "Versatile ticket list with customizable filters", "UnorderedListOutlined"),
        ("monitor_kpi", "KPI Statistic", "Key performance indicators and metrics", "BarChartOutlined"),
        ("audit_stream", "Audit Log", "Real-time stream of system events", "AuditOutlined"),
        ("profile_card", "My Profile", "Quick access to your user profile and settings", "UserOutlined"),
        ("recent_comments", "Recent Comments", "Latest updates on tickets you follow", "MessageOutlined"),
        ("sector_stats", "Sector Chart", "Distribution of tickets across sectors", "PieChartOutlined"),
        ("user_workload", "User Workload", "Capacity and workload across team members", "TeamOutlined"),
        ("stale_tickets", "Stale Tickets", "Tickets requiring immediate attention", "HistoryOutlined"),
        ("workload_balancer", "Workload Balancer", "Optimize ticket distribution", "BarChartOutlined"),
        ("bottleneck_analysis", "Bottleneck Analysis", "Identify delays in the workflow", "LineChartOutlined"),
        ("shortcuts", "Quick Links", "Customizable action shortcuts", "SendOutlined"),
        ("clock", "Clock", "Local and UTC time display", "FieldTimeOutlined"),
        ("system_health", "System Health", "Backend services status monitor", "DatabaseOutlined"),
        ("sla_overview", "SLA Overview", "Service level agreement compliance tracking", "CarryOutOutlined"),
        ("welcome_banner", "Welcome Banner", "Personalized greeting and tips", "SmileOutlined"),
        ("not_reviewed", "Not Yet Reviewed", "Pending tickets waiting for distribution", "HourglassOutlined"),
        ("reviewed_today", "Reviewed Today", "Tickets reviewed by distributors in the last 24h", "CheckCircleOutlined"),
    ]

    for w_type, name, desc, icon in catalogue:
        wd = db.get(WidgetDefinition, w_type)
        if not wd:
            wd = WidgetDefinition(type=w_type)
            db.add(wd)
        wd.display_name = name
        wd.description = desc
        wd.icon = icon
        wd.is_active = True
    
    db.flush()


def auto_configure_dashboard(db: Session, p: Principal, dashboard_id: str, mode: str = "append", primary_sector: str | None = None) -> None:
    """Heuristic logic to build a role-appropriate dashboard."""
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    
    if mode == "replace":
        db.execute(delete(DashboardWidget).where(DashboardWidget.dashboard_id == d.id))
        db.flush()
        db.refresh(d)
    
    # Load limits
    max_watchers = int(get_setting(db, "autopilot_max_ticket_watchers", 5))

    # Heuristics
    widgets_to_add = []
    
    # Base widget
    widgets_to_add.append({"type": "welcome_banner", "title": "Welcome!", "x": 0, "y": 0, "w": 4, "h": 3})

    if p.is_admin:
        widgets_to_add.extend([
            {"type": "system_health", "x": 4, "y": 0, "w": 4, "h": 3},
            {"type": "sla_overview", "x": 8, "y": 0, "w": 4, "h": 3},
            {"type": "stale_tickets", "x": 0, "y": 3, "w": 4, "h": 4, "config": {"hours": 48}},
            {"type": "bottleneck_analysis", "x": 4, "y": 3, "w": 8, "h": 4, "config": {"days": 30}},
            {"type": "audit_stream", "x": 0, "y": 7, "w": 12, "h": 4},
        ])
    elif p.chief_sectors:
        sector_code = primary_sector or list(p.chief_sectors)[0]
        widgets_to_add.extend([
            {"type": "workload_balancer", "x": 4, "y": 0, "w": 8, "h": 3, "config": {"sectorCode": sector_code}},
            {"type": "bottleneck_analysis", "x": 0, "y": 3, "w": 12, "h": 4, "config": {"scope": "sector", "sector_code": sector_code, "days": 14}},
            {"type": "ticket_list", "x": 0, "y": 7, "w": 6, "h": 4, "title": f"Sector Queue: {sector_code}", "config": {"scope": "sector", "sector_code": sector_code}},
            {"type": "stale_tickets", "x": 6, "y": 7, "w": 6, "h": 4, "config": {"scope": "sector", "sector_code": sector_code, "hours": 24}},
        ])
    elif p.is_internal:
        widgets_to_add.extend([
            {"type": "monitor_kpi", "x": 4, "y": 0, "w": 8, "h": 3, "config": {"scope": "personal"}},
            {"type": "ticket_list", "x": 0, "y": 3, "w": 8, "h": 4, "title": "My Active Queue", "config": {"scope": "personal"}},
            {"type": "recent_comments", "x": 8, "y": 3, "w": 4, "h": 4, "config": {"scope": "personal"}},
        ])
    else:  # Beneficiary
        widgets_to_add.extend([
            {"type": "profile_card", "x": 4, "y": 0, "w": 4, "h": 3},
            {"type": "shortcuts", "x": 8, "y": 0, "w": 4, "h": 3},
            {"type": "ticket_list", "x": 0, "y": 3, "w": 8, "h": 4, "title": "My Requests", "config": {"scope": "my_requests"}},
            {"type": "recent_comments", "x": 8, "y": 3, "w": 4, "h": 4, "config": {"visibility": "public", "scope": "my_requests"}},
        ])

    # Add dynamic watchers for most recent active tickets
    recent_tickets = db.scalars(
        _visible_stmt(p)
        .where(Ticket.status.in_(ACTIVE_STATUSES))
        .order_by(Ticket.created_at.desc())
        .limit(max_watchers)
    ).all()

    current_y = 11
    for idx, t in enumerate(recent_tickets):
        widgets_to_add.append({
            "type": "recent_comments",
            "title": f"Comments: {t.ticket_code}",
            "x": (idx % 3) * 4,
            "y": current_y + (idx // 3) * 4,
            "w": 4, "h": 4,
            "config": {"ticketId": t.id, "limit": 5}
        })

    for w_data in widgets_to_add:
        w = DashboardWidget(
            dashboard_id=d.id,
            type=w_data["type"],
            title=w_data.get("title"),
            x=w_data["x"],
            y=w_data["y"],
            w=w_data["w"],
            h=w_data["h"],
            config=w_data.get("config", {})
        )
        db.add(w)
    
    db.flush()


def _serialize_dashboard(d: CustomDashboard, full: bool = False) -> dict[str, Any]:
    res = {
        "id": d.id,
        "title": d.title,
        "description": d.description,
        "widget_count": len(d.widgets),
        "is_public": d.is_public,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
    if full:
        res["widgets"] = [_serialize_widget(w) for w in d.widgets]
    return res


def _serialize_widget(w: DashboardWidget) -> dict[str, Any]:
    return {
        "id": w.id,
        "type": w.type,
        "title": w.title,
        "config": w.config,
        "x": w.x,
        "y": w.y,
        "w": w.w,
        "h": w.h,
    }
 w.config,
        "x": w.x,
        "y": w.y,
        "w": w.w,
        "h": w.h,
    }
