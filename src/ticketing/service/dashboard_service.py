from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam.principal import Principal
from src.ticketing.models import CustomDashboard, DashboardWidget, WidgetDefinition, Ticket, SystemSetting
from src.ticketing.service.ticket_service import _visibility_filter
from src.ticketing.state_machine import ACTIVE_STATUSES


def get_setting(db: Session, key: str, default: Any = None) -> Any:
    """Helper to fetch a global system setting from the database."""
    s = db.get(SystemSetting, key)
    return s.value if s else default


def _visible_stmt(principal: Principal):
    """Helper to build a visible-ticket statement for the current principal."""
    stmt = select(Ticket).where(Ticket.is_deleted.is_(False))
    vis = _visibility_filter(principal)
    if vis is not None:
        stmt = stmt.where(vis)
    return stmt


def _check_dashboard_access(p: Principal) -> None:
    """RBAC check: currently all authenticated users can manage their own dashboards."""
    # Everyone is allowed to have dashboards now.
    pass


def list_dashboards(db: Session, p: Principal) -> list[dict[str, Any]]:
    """List all dashboards owned by the given principal."""
    _check_dashboard_access(p)
    stmt = (
        select(CustomDashboard)
        .where(CustomDashboard.owner_user_id == p.user_id)
        .order_by(CustomDashboard.created_at.desc())
    )
    rows = list(db.scalars(stmt))
    return [_serialize_dashboard(r) for r in rows]


def get_dashboard(db: Session, p: Principal, dashboard_id: str) -> dict[str, Any]:
    """Retrieve a full dashboard with all its widgets."""
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    return _serialize_dashboard(d, full=True)


def create_dashboard(db: Session, p: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new custom dashboard."""
    _check_dashboard_access(p)
    title = str(payload.get("title") or "New Dashboard").strip()
    
    d = CustomDashboard(
        owner_user_id=p.user_id,
        title=title,
        description=payload.get("description"),
    )
    db.add(d)
    db.flush()
    return _serialize_dashboard(d)


def update_dashboard(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Update dashboard metadata."""
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    
    if "title" in payload:
        d.title = str(payload["title"]).strip()
    if "description" in payload:
        d.description = payload["description"]

    db.flush()
    return _serialize_dashboard(d)


def delete_dashboard(db: Session, p: Principal, dashboard_id: str) -> None:
    """Permanently delete a dashboard and its widgets."""
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    db.delete(d)
    db.flush()


_ALLOWED_WIDGET_SCOPES = {"global", "sector", "personal", "my_requests"}


def _validate_widget_config(p: Principal, db: Session, config: Any) -> None:
    """Reject widget configurations that target data the principal can't see.

    The visibility predicates on the data endpoints already filter results
    server-side, so a bogus `config` produces empty payloads rather than a
    leak. But we still validate at write time so:

    1. The audit log shows who tried to point a widget at a foreign sector
       (a probe-by-config oracle is closed at the source).
    2. The UI gets clean 400s with a useful reason instead of mysteriously
       empty widgets.
    3. Admins and dashboards exporters can trust that a stored `config` is
       always referencing data the owner could see at write time.

    The check is intentionally permissive on unknown keys so the widget
    catalogue can grow without breaking older clients.
    """
    if not config:
        return
    if not isinstance(config, dict):
        raise ValidationError("widget config must be an object")

    scope = config.get("scope")
    if scope is not None and scope not in _ALLOWED_WIDGET_SCOPES:
        raise ValidationError(
            f"widget scope must be one of {sorted(_ALLOWED_WIDGET_SCOPES)}"
        )

    sector_code = config.get("sector_code") or config.get("sectorCode")
    if sector_code:
        # Admins / auditors keep cross-sector vision; everyone else must
        # reference a sector they actually belong to.
        if not (p.is_admin or p.is_auditor):
            if sector_code not in p.all_sectors:
                raise PermissionDeniedError(
                    f"not allowed to target sector {sector_code}"
                )

    ticket_id = config.get("ticketId") or config.get("ticket_id")
    if ticket_id:
        # Re-use the canonical ticket visibility check rather than
        # duplicating the SQL here. `ticket_service.get` raises NotFound
        # when the principal can't see the ticket, which is exactly the
        # signal we want.
        from src.ticketing.service import ticket_service
        ticket_service.get(db, p, ticket_id)


def _check_widget_required_roles(db: Session, p: Principal, widget_type: str) -> None:
    """Reject the write if `widget_definitions.required_roles` excludes the
    principal.

    Soft cases (no catalogue row, NULL/empty `required_roles`) pass through
    so adding a new widget type doesn't accidentally lock everyone out
    until the gate is configured. Admins also bypass — they own the
    catalogue and need to be able to demo every widget. Auditors get the
    same treatment for read-only inspection workflows.
    """
    if p.is_admin or p.is_auditor:
        return
    wd = db.get(WidgetDefinition, widget_type)
    if wd is None:
        return  # Unknown widget type — let the rest of the system reject it.
    required = wd.required_roles or []
    if not required:
        return
    if not any(p.has_role(role) for role in required):
        raise PermissionDeniedError(
            f"widget '{widget_type}' requires one of: {', '.join(sorted(required))}"
        )


def upsert_widget(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Create or update a widget configuration within a dashboard.

    The widget `config` blob is validated against the principal's visibility
    scope: a sector-3 user can't pin a widget at sector 2, and an attempt to
    watch a ticket the user can't see is rejected up-front. See
    `_validate_widget_config` for the rules and the rationale.
    """
    _check_dashboard_access(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")

    widget_id = payload.get("id")
    if widget_id:
        w = db.get(DashboardWidget, widget_id)
        if w is None or w.dashboard_id != d.id:
            raise NotFoundError("widget not found")
        widget_type = w.type
    else:
        widget_type = payload["type"]
        w = DashboardWidget(dashboard_id=d.id, type=widget_type)
        db.add(w)

    # Required-roles gate: if the widget catalogue declares a role list,
    # the principal must hold at least one of those roles. Admins always
    # pass — they manage the catalogue itself.
    _check_widget_required_roles(db, p, widget_type)

    if "config" in payload:
        _validate_widget_config(p, db, payload["config"])

    for field in ("title", "config", "x", "y", "w", "h"):
        if field in payload:
            setattr(w, field, payload[field])

    db.flush()
    return _serialize_widget(w)


def delete_widget(db: Session, p: Principal, dashboard_id: str, widget_id: str) -> None:
    """Remove a specific widget from a dashboard."""
    _check_dashboard_access(p)
    w = db.get(DashboardWidget, widget_id)
    if w is None or w.dashboard_id != dashboard_id:
        raise NotFoundError("widget not found")
    db.delete(w)
    db.flush()


def sync_widget_catalogue(db: Session) -> None:
    """Ensures the `widget_definitions` table is populated with the standard system widgets.

    This acts as a seed/sync function to keep the frontend catalogue in sync with backend capabilities.

    Args:
        db: Database session.
    """
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
    db.flush()


_AUTO_CONFIGURE_WATCHER_HARD_CAP = 50


def auto_configure_dashboard(db: Session, p: Principal, dashboard_id: str, mode: str = "append", primary_sector: str | None = None) -> None:
    """Heuristic logic to build a role-appropriate dashboard.

    Note on the watcher cap: the per-dashboard watcher count is taken from
    the system setting `autopilot_max_ticket_watchers`, which an
    administrator can edit at runtime. We *also* enforce a hard cap
    (`_AUTO_CONFIGURE_WATCHER_HARD_CAP`) so a typo or a malicious script
    that bumps the setting to a huge number can't paste hundreds of widgets
    onto a dashboard in a single call. The hard cap floors at 0 so a
    negative setting can't trigger an unbounded read.
    """
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")

    if mode == "replace":
        db.execute(delete(DashboardWidget).where(DashboardWidget.dashboard_id == d.id))
        db.flush()
        db.refresh(d)

    # Load limits — hard-capped regardless of system-setting value.
    raw_max = int(get_setting(db, "autopilot_max_ticket_watchers", 5))
    max_watchers = max(0, min(raw_max, _AUTO_CONFIGURE_WATCHER_HARD_CAP))

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
        # Include ticket code AND title in the widget header
        title = f"Comments: {t.ticket_code}"
        if t.title:
            title = f"{t.ticket_code}: {t.title}"

        widgets_to_add.append({
            "type": "recent_comments",
            "title": title,
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
    """Serialize a dashboard instance to a dict."""
    res = {
        "id": d.id,
        "title": d.title,
        "description": d.description,
        "widget_count": len(d.widgets),
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
    if full:
        res["widgets"] = [_serialize_widget(w) for w in d.widgets]
    return res


def _serialize_widget(w: DashboardWidget) -> dict[str, Any]:
    """Serialize a widget instance to a dict."""
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
