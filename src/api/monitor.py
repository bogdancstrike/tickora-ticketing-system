"""Monitor endpoints with RBAC-aware aggregate data (previously Dashboard)."""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import monitor_service


def _user_id(kwargs) -> str:
    user_id = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    if not user_id:
        raise ValidationError("user_id is required")
    return user_id


@require_authenticated
def monitor_overview(app, operation, request, *, principal: Principal, **kwargs):
    days = int(flask_request.args.get("days", 30))
    with get_db() as db:
        return (monitor_service.monitor_overview(db, principal, days=days), 200)


@require_authenticated
def global_monitor(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (monitor_service.monitor_global(db, principal), 200)


@require_authenticated
def distributor_monitor(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (monitor_service.monitor_distributor(db, principal), 200)


@require_authenticated
def sectors_monitor(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": monitor_service.monitor_sectors(db, principal)}, 200)


@require_authenticated
def sector_monitor(app, operation, request, *, principal: Principal, **kwargs):
    sector_code = kwargs.get("sector_code") or flask_request.view_args.get("sector_code")
    if not sector_code:
        raise ValidationError("sector_code is required")
    with get_db() as db:
        return (monitor_service.monitor_sector(db, principal, sector_code), 200)


@require_authenticated
def user_monitor(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (monitor_service.monitor_personal(db, principal, _user_id(kwargs)), 200)


@require_authenticated
def timeseries_monitor(app, operation, request, *, principal: Principal, **kwargs):
    days = int(flask_request.args.get("days", 30))
    with get_db() as db:
        return ({"items": monitor_service.monitor_timeseries(db, principal, days=days)}, 200)
