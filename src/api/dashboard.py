"""Dashboard endpoints with RBAC-aware aggregate data."""
from flask import request as flask_request

from src.core.db import get_db
from src.core.errors import ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import dashboard_service


def _sector_code(kwargs: dict) -> str:
    value = (
        kwargs.get("sector_id")
        or kwargs.get("sector_code")
        or flask_request.view_args.get("sector_id")
        or flask_request.view_args.get("sector_code")
    )
    if not value:
        raise ValidationError("sector_id is required")
    return value


def _user_id(kwargs: dict) -> str:
    value = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    if not value:
        raise ValidationError("user_id is required")
    return value


@require_authenticated
def overview(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.overview(db, principal), 200)


@require_authenticated
def global_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.global_(db, principal), 200)


@require_authenticated
def sectors_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": dashboard_service.sectors(db, principal)}, 200)


@require_authenticated
def sector_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.sector(db, principal, _sector_code(kwargs)), 200)


@require_authenticated
def user_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.personal(db, principal, _user_id(kwargs)), 200)


@require_authenticated
def beneficiary_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.beneficiary(db, principal), 200)


@require_authenticated
def sla_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (dashboard_service.sla(db, principal), 200)


@require_authenticated
def timeseries_dashboard(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": dashboard_service.timeseries(db, principal)}, 200)
