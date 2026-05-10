"""Reference data endpoints for form dropdowns."""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import PermissionDeniedError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.service import reference_service


@require_authenticated
def ticket_options(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (reference_service.ticket_options(db), 200)


@require_authenticated
def assignable_users(app, operation, request, *, principal: Principal, **kwargs):
    sector_code = flask_request.args.get("sector_code")
    if not (principal.is_admin or principal.is_distributor or principal.chief_sectors or principal.member_sectors):
        raise PermissionDeniedError("not allowed to list assignable users")

    # Non-admins only see users in the requested sector, and only if they themselves
    # belong to it (or are a chief there). Distributors are allowed cross-sector
    # listing (they triage everything) but still restricted to a specific sector.
    if not principal.is_admin:
        if not sector_code:
            raise PermissionDeniedError("sector_code is required for non-admin users")
        if not principal.is_distributor and sector_code not in principal.all_sectors:
            raise PermissionDeniedError("not allowed to list users for this sector")

    with get_db() as db:
        return ({"items": reference_service.assignable_users(db, sector_code=sector_code)}, 200)
