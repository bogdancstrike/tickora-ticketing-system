"""Customizable dashboard endpoints."""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import dashboard_service


def _payload() -> dict:
    return flask_request.get_json() or {}


@require_authenticated
def list_dashboards(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": dashboard_service.list_dashboards(db, principal)}, 200)


@require_authenticated
def get_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    with get_db() as db:
        return (dashboard_service.get_dashboard(db, principal, dashboard_id), 200)


@require_authenticated
def create_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.create_dashboard(db, principal, _payload()), 201)


@require_authenticated
def update_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    with get_db() as db:
        return (dashboard_service.update_dashboard(db, principal, dashboard_id, _payload()), 200)


@require_authenticated
def delete_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    with get_db() as db:
        dashboard_service.delete_dashboard(db, principal, dashboard_id)
        return ({"status": "deleted"}, 200)


@require_authenticated
def upsert_widget(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    with get_db() as db:
        return (dashboard_service.upsert_widget(db, principal, dashboard_id, _payload()), 200)


@require_authenticated
def delete_widget(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    widget_id = kwargs.get("widget_id")
    with get_db() as db:
        dashboard_service.delete_widget(db, principal, dashboard_id, widget_id)
        return ({"status": "deleted"}, 200)


@require_authenticated
def auto_configure(app, operation, request, *, principal: Principal, **kwargs):
    dashboard_id = kwargs.get("dashboard_id")
    payload = _payload()
    mode = payload.get("mode", "append")
    primary_sector = payload.get("primary_sector")

    with get_db() as db:
        dashboard_service.auto_configure_dashboard(db, principal, dashboard_id, mode=mode, primary_sector=primary_sector)
        return (dashboard_service.get_dashboard(db, principal, dashboard_id), 200)
