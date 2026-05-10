from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.common.errors import NotFoundError, PermissionDeniedError, ValidationError
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
        ("ticket_list", "Ticket List", "Versatile ticket list with customizable filters", "UnorderedListOutlined", []),
        ("monitor_kpi", "KPI Statistic", "Key performance indicators and metrics", "BarChartOutlined", []),
        ("audit_stream", "Audit Log", "Real-time stream of system events", "AuditOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor"]),
        ("profile_card", "My Profile", "Quick access to your user profile and settings", "UserOutlined", []),
        ("recent_comments", "Recent Comments", "Latest updates on tickets you follow", "MessageOutlined", []),
        ("sector_stats", "Sector Chart", "Distribution of tickets across sectors", "PieChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("user_workload", "User Workload", "Capacity and workload across team members", "TeamOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("stale_tickets", "Stale Tickets", "Tickets requiring immediate attention", "HistoryOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("workload_balancer", "Workload Balancer", "Optimize ticket distribution", "BarChartOutlined", ["tickora_admin", "tickora_distributor", "tickora_internal_user"]),
        ("bottleneck_analysis", "Bottleneck Analysis", "Identify delays in the workflow", "LineChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("shortcuts", "Quick Links", "Customizable action shortcuts", "SendOutlined", []),
        ("clock", "Clock", "Local and UTC time display", "FieldTimeOutlined", []),
        ("system_health", "System Health", "Backend services status monitor", "DatabaseOutlined", ["tickora_admin", "tickora_auditor"]),
        ("welcome_banner", "Welcome Banner", "Personalized greeting and tips", "SmileOutlined", []),
        ("not_reviewed", "Not Yet Reviewed", "Pending tickets waiting for distribution", "HourglassOutlined", ["tickora_admin", "tickora_distributor"]),
        ("reviewed_today", "Reviewed Today", "Tickets reviewed by distributors in the last 24h", "CheckCircleOutlined", ["tickora_admin", "tickora_distributor"]),
        # ── Phase 7 surfaces ─────────────────────────────────────────────
        ("my_watchlist", "My Watchlist", "Tickets you've subscribed to follow", "EyeOutlined", []),
        ("my_mentions", "My Mentions", "Comments where you were @mentioned", "BellOutlined", []),
        ("my_assigned", "My Assigned", "Tickets currently assigned to you", "UserOutlined", ["tickora_internal_user", "tickora_distributor", "tickora_admin"]),
        ("my_requests", "My Requests", "Tickets where you're the requester or beneficiary", "SendOutlined", []),
        ("linked_tickets", "Linked Tickets", "Parent / child / blocked-by relationships involving you", "LinkOutlined", []),
        # ── Operations ───────────────────────────────────────────────────
        ("task_health", "Task Health", "Counts of running / pending / failed background tasks", "DatabaseOutlined", ["tickora_admin"]),
        ("recent_failures", "Recent Task Failures", "Most recent failed background-task rows", "ExclamationCircleOutlined", ["tickora_admin"]),
        ("active_sessions", "Active Sessions", "Users currently signed in (5-minute window)", "TeamOutlined", ["tickora_admin"]),
        ("assignment_age", "Assignment Age", "Average time tickets stay with one assignee", "FieldTimeOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("global_kpi", "Global KPI", "Headline counts: total / active / new today / closed today", "BarChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor"]),
        ("notification_feed", "Notification Feed", "Recent in-app notifications", "BellOutlined", []),
        ("throughput_trend", "Throughput Trend", "Created vs closed tickets over time", "LineChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("backlog_by_sector", "Backlog by Sector", "Largest visible sector backlogs", "BarChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor"]),
        ("priority_mix", "Priority Mix", "Visible tickets grouped by priority", "PieChartOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("oldest_active", "Oldest Active", "Oldest visible tickets that still need movement", "HistoryOutlined", ["tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user"]),
        ("requester_status", "Requester Status", "Your submitted/requester tickets grouped by status", "PieChartOutlined", []),
    ]

    for w_type, name, desc, icon, required_roles in catalogue:
        wd = db.get(WidgetDefinition, w_type)
        if not wd:
            wd = WidgetDefinition(type=w_type)
            db.add(wd)
        wd.display_name = name
        wd.description = desc
        wd.icon = icon
        wd.required_roles = required_roles
    db.flush()


_AUTO_CONFIGURE_WATCHER_HARD_CAP = 50

# Layout primitives. The grid is 12 columns wide; rows are unbounded.
# Sizes are tuples of (width, height). Widgets pack left-to-right and
# wrap onto new rows when they don't fit on the current row.
_SIZES: dict[str, tuple[int, int]] = {
    "sm":   (4, 3),    # third-of-row, short
    "md":   (6, 4),    # half-row
    "lg":   (8, 4),    # two-thirds
    "xl":   (12, 4),   # full row, normal height
    "tall": (4, 6),    # narrow but tall (lists)
    "wide": (12, 6),   # full row, tall (charts)
}

_GRID_WIDTH = 12


def _pack(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Place each widget on a 12-col grid by row-major bin-packing.

    Mutates each widget dict to add `x` / `y` / `w` / `h` based on its
    declared `size` (defaults to `md` if absent or unknown). Honors any
    `x` / `y` already set on a widget — pre-positioned items skip the
    packer.

    The packer is intentionally simple — first-fit row-major. Adjacent
    widgets of the same row align by sharing the row's max height, so
    we don't end up with ragged rows where a 3-tall widget creates a
    visual hole next to a 6-tall one. Good enough for ~20 widgets; we
    don't need 2D bin-packing here.
    """
    placed: list[dict[str, Any]] = []
    cursor_y = 0
    row_x = 0
    row_h = 0

    for w in widgets:
        size_key = w.pop("size", None) or "md"
        if size_key not in _SIZES:
            size_key = "md"
        ww, hh = _SIZES[size_key]

        # Pre-positioned widgets respect the user's intent.
        if "x" in w and "y" in w and "w" in w and "h" in w:
            placed.append(w)
            continue

        # Wrap to next row if this widget doesn't fit on the current one.
        if row_x + ww > _GRID_WIDTH:
            cursor_y += row_h
            row_x = 0
            row_h = 0

        w["x"] = row_x
        w["y"] = cursor_y
        w["w"] = ww
        w["h"] = hh
        placed.append(w)

        row_x += ww
        if hh > row_h:
            row_h = hh

    return placed


# ── Recipes ─────────────────────────────────────────────────────────────────
# Each recipe is an ordered list of `WidgetSpec`s. The packer turns them
# into x/y/w/h. Recipes use the catalogue's widget types (and the new
# Phase 7 ones) so the frontend can decide how to render each.

def _recipe_admin() -> list[dict[str, Any]]:
    return [
        {"type": "welcome_banner",     "title": "Welcome", "size": "sm"},
        {"type": "global_kpi",         "size": "lg",  "config": {}},
        {"type": "active_sessions",    "size": "sm",  "config": {}},
        {"type": "task_health",        "size": "sm",  "config": {}},
        {"type": "system_health",      "size": "sm"},
        {"type": "throughput_trend",    "size": "wide","config": {"days": 30}},
        {"type": "backlog_by_sector",   "size": "md",  "config": {"limit": 10}},
        {"type": "stale_tickets",      "size": "md",  "config": {"hours": 48}},
        {"type": "recent_failures",    "size": "md",  "config": {"limit": 10}},
        {"type": "bottleneck_analysis","size": "wide","config": {"days": 30}},
        {"type": "audit_stream",       "size": "wide","config": {"limit": 30}},
    ]


def _recipe_auditor() -> list[dict[str, Any]]:
    return [
        {"type": "welcome_banner",      "title": "Welcome", "size": "sm"},
        {"type": "global_kpi",          "size": "lg"},
        {"type": "throughput_trend",     "size": "wide", "config": {"days": 30}},
        {"type": "priority_mix",         "size": "md"},
        {"type": "audit_stream",        "size": "wide", "config": {"limit": 50}},
        {"type": "bottleneck_analysis", "size": "md",   "config": {"days": 30}},
        {"type": "stale_tickets",       "size": "md",   "config": {"hours": 72}},
    ]


def _recipe_distributor() -> list[dict[str, Any]]:
    return [
        {"type": "welcome_banner",   "title": "Welcome", "size": "sm"},
        {"type": "monitor_kpi",      "size": "lg",  "config": {"scope": "global"}},
        {"type": "priority_mix",     "size": "md"},
        {"type": "oldest_active",    "size": "md",  "config": {"limit": 10}},
        {"type": "not_reviewed",     "size": "md"},
        {"type": "reviewed_today",   "size": "md"},
        {"type": "stale_tickets",    "size": "md",  "config": {"hours": 24, "scope": "global"}},
        {"type": "workload_balancer","size": "md"},
        {"type": "audit_stream",     "size": "wide", "config": {"limit": 20}},
    ]


def _recipe_chief(sector_code: str) -> list[dict[str, Any]]:
    cfg = {"scope": "sector", "sector_code": sector_code}
    return [
        {"type": "welcome_banner",      "title": f"Sector {sector_code}", "size": "sm"},
        {"type": "monitor_kpi",         "size": "lg",   "config": cfg},
        {"type": "user_workload",       "size": "sm",   "config": cfg},
        {"type": "workload_balancer",   "size": "md",   "config": cfg},
        {"type": "assignment_age",      "size": "md",   "config": cfg},
        {"type": "priority_mix",        "size": "md",   "config": cfg},
        {"type": "oldest_active",       "size": "md",   "config": {**cfg, "limit": 10}},
        {"type": "ticket_list",         "size": "md",   "title": f"Sector queue · {sector_code}", "config": cfg},
        {"type": "stale_tickets",       "size": "md",   "config": {**cfg, "hours": 24}},
        {"type": "bottleneck_analysis", "size": "wide", "config": {**cfg, "days": 14}},
        {"type": "sector_stats",        "size": "md",   "config": cfg},
        {"type": "audit_stream",        "size": "md",   "config": {"sector_code": sector_code, "limit": 20}},
    ]


def _recipe_member() -> list[dict[str, Any]]:
    return [
        {"type": "welcome_banner",  "title": "My day", "size": "sm"},
        {"type": "monitor_kpi",     "size": "lg", "config": {"scope": "personal"}},
        {"type": "my_assigned",     "size": "md"},
        {"type": "my_watchlist",    "size": "md"},
        {"type": "my_mentions",     "size": "md", "config": {"limit": 10}},
        {"type": "linked_tickets",  "size": "md"},
        {"type": "recent_comments", "size": "md", "config": {"scope": "personal"}},
        {"type": "notification_feed", "size": "md", "config": {"limit": 15}},
    ]


def _recipe_beneficiary() -> list[dict[str, Any]]:
    return [
        {"type": "welcome_banner",  "title": "Welcome", "size": "sm"},
        {"type": "profile_card",    "size": "sm"},
        {"type": "shortcuts",       "size": "sm"},
        {"type": "requester_status", "size": "md"},
        {"type": "my_requests",     "size": "lg"},
        {"type": "recent_comments", "size": "md",
         "config": {"visibility": "public", "scope": "my_requests"}},
        {"type": "notification_feed", "size": "md", "config": {"limit": 10}},
    ]


def _pick_recipe(p: Principal, primary_sector: str | None) -> list[dict[str, Any]]:
    """Choose the best recipe for the principal.

    Order matters: admin trumps everything, then auditor, then
    distributor, then chief, then member, then beneficiary. A user with
    multiple roles gets the most-privileged recipe — that's almost
    always what they want a "default" dashboard to look like.
    """
    if p.is_admin:
        return _recipe_admin()
    if p.is_auditor:
        return _recipe_auditor()
    if p.is_distributor:
        return _recipe_distributor()
    if p.chief_sectors:
        sc = primary_sector or sorted(p.chief_sectors)[0]
        return _recipe_chief(sc)
    if p.is_internal:
        return _recipe_member()
    return _recipe_beneficiary()


def auto_configure_dashboard(db: Session, p: Principal, dashboard_id: str, mode: str = "append", primary_sector: str | None = None) -> None:
    """Heuristically populate a dashboard with a sensible widget set.

    Steps:
      1. Pick a recipe based on the principal's role/sector profile.
      2. Pack the recipe onto a 12-column grid (`_pack`).
      3. Append a small "watch list" of recent visible tickets if the
         system setting `autopilot_max_ticket_watchers` says so. Hard-
         capped at `_AUTO_CONFIGURE_WATCHER_HARD_CAP`.
      4. Persist the widgets.

    The watcher widgets sit *under* the recipe widgets so they don't
    crowd the headline metrics. They're added at the next available row
    after the recipe finishes packing.

    `mode='replace'` clears existing widgets first; `mode='append'`
    leaves them and adds new ones (useful for a "suggest more widgets"
    button down the line).
    """
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")

    if mode == "replace":
        db.execute(delete(DashboardWidget).where(DashboardWidget.dashboard_id == d.id))
        db.flush()
        db.refresh(d)

    raw_max = int(get_setting(db, "autopilot_max_ticket_watchers", 5))
    max_watchers = max(0, min(raw_max, _AUTO_CONFIGURE_WATCHER_HARD_CAP))

    # Step 1+2: recipe → packed grid coordinates.
    recipe = _pick_recipe(p, primary_sector)
    placed = _pack(recipe)

    # Where does the recipe end? We'll start the watcher row beneath it.
    recipe_max_y = max((w["y"] + w["h"] for w in placed), default=0)

    # Step 3: watcher widgets (most-recent visible active tickets).
    watcher_specs: list[dict[str, Any]] = []
    if max_watchers > 0:
        recent_tickets = db.scalars(
            _visible_stmt(p)
            .where(Ticket.status.in_(ACTIVE_STATUSES))
            .order_by(Ticket.created_at.desc())
            .limit(max_watchers)
        ).all()
        for t in recent_tickets:
            label = f"{t.ticket_code}: {t.title}" if t.title else f"Comments: {t.ticket_code}"
            watcher_specs.append({
                "type":  "recent_comments",
                "title": label,
                "size":  "sm",
                "config": {"ticketId": t.id, "limit": 5},
            })
    # Pack the watchers onto their own row block, then offset y by the
    # recipe's depth so they don't overlap.
    watcher_placed = _pack(watcher_specs)
    for w in watcher_placed:
        w["y"] += recipe_max_y

    # Step 4: persist.
    for w in placed + watcher_placed:
        db.add(DashboardWidget(
            dashboard_id=d.id,
            type=w["type"],
            title=w.get("title"),
            x=w["x"], y=w["y"], w=w["w"], h=w["h"],
            config=w.get("config", {}),
        ))
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
