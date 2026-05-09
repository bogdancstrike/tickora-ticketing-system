"""Customizable dashboards and widgets service."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam.principal import Principal
from src.ticketing.models import CustomDashboard, DashboardWidget


def _check_not_beneficiary(p: Principal) -> None:
    if p.user_type == "external" or "tickora_beneficiary" in p.global_roles:
         # Check if they have ANY operational role. If only beneficiary, deny.
         if not any(r in p.global_roles for r in ("tickora_admin", "tickora_auditor", "tickora_distributor", "tickora_internal_user")):
            raise PermissionDeniedError("custom dashboards are not available for beneficiaries")


def list_dashboards(db: Session, p: Principal) -> list[dict[str, Any]]:
    _check_not_beneficiary(p)
    stmt = select(CustomDashboard).where(CustomDashboard.owner_user_id == p.user_id).order_by(CustomDashboard.created_at.desc())
    rows = list(db.scalars(stmt))
    return [_serialize_dashboard(r) for r in rows]


def get_dashboard(db: Session, p: Principal, dashboard_id: str) -> dict[str, Any]:
    _check_not_beneficiary(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    return _serialize_dashboard(d, full=True)


def create_dashboard(db: Session, p: Principal, payload: dict[str, Any]) -> dict[str, Any]:
    _check_not_beneficiary(p)
    title = str(payload.get("title") or "New Dashboard").strip()
    
    d = CustomDashboard(
        owner_user_id=p.user_id,
        title=title,
        is_public=bool(payload.get("is_public", False))
    )
    db.add(d)
    db.flush()
    return _serialize_dashboard(d)


def update_dashboard(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _check_not_beneficiary(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    
    if "title" in payload:
        d.title = str(payload["title"]).strip()
    if "is_public" in payload:
        d.is_public = bool(payload["is_public"])
    
    db.flush()
    return _serialize_dashboard(d)


def delete_dashboard(db: Session, p: Principal, dashboard_id: str) -> None:
    _check_not_beneficiary(p)
    d = db.get(CustomDashboard, dashboard_id)
    if d is None or d.owner_user_id != p.user_id:
        raise NotFoundError("dashboard not found")
    db.delete(d)
    db.flush()


def upsert_widget(db: Session, p: Principal, dashboard_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _check_not_beneficiary(p)
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
    _check_not_beneficiary(p)
    w = db.get(DashboardWidget, widget_id)
    if w is None or w.dashboard_id != dashboard_id:
        raise NotFoundError("widget not found")
    
    d = db.get(CustomDashboard, w.dashboard_id)
    if d.owner_user_id != p.user_id:
        raise PermissionDeniedError("not allowed")
    
    db.delete(w)
    db.flush()


def _serialize_dashboard(d: CustomDashboard, full: bool = False) -> dict[str, Any]:
    res = {
        "id": d.id,
        "title": d.title,
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
