"""Admin HTTP endpoints."""
from flask import request as flask_request

from src.common.db import get_db
from src.common.errors import PermissionDeniedError, ValidationError
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal
from src.ticketing.models import WidgetDefinition
from src.ticketing.service import admin_service, dashboard_service


def _payload() -> dict:
    data = flask_request.get_json(force=True, silent=True)
    return data or {}


def _arg(name: str, default=None):
    return flask_request.args.get(name, default)


@require_authenticated
def overview(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.overview(db, principal), 200)


@require_authenticated
def list_users(app, operation, request, *, principal: Principal, **kwargs):
    limit = int(_arg("limit", 100) or 100)
    with get_db() as db:
        return ({"items": admin_service.list_users(db, principal, search=_arg("search"), limit=limit)}, 200)


@require_authenticated
def get_user(app, operation, request, *, principal: Principal, **kwargs):
    user_id = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    with get_db() as db:
        return (admin_service.get_user(db, principal, user_id), 200)


@require_authenticated
def update_user(app, operation, request, *, principal: Principal, **kwargs):
    user_id = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    with get_db() as db:
        return (admin_service.update_user(db, principal, user_id, _payload()), 200)


@require_authenticated
def reset_password(app, operation, request, *, principal: Principal, **kwargs):
    from keycloak.exceptions import KeycloakError
    user_id = kwargs.get("user_id") or flask_request.view_args.get("user_id")
    reason = (_payload().get("reason") or "").strip() or None
    try:
        with get_db() as db:
            password = admin_service.reset_password(db, principal, user_id, reason=reason)
            return ({"status": "success", "temporary_password": password}, 200)
    except KeycloakError as exc:
        raise ValidationError(f"Keycloak rejected the password reset: {exc.error_message}") from exc


@require_authenticated
def list_sectors(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": admin_service.list_sectors(db, principal)}, 200)


@require_authenticated
def create_sector(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_sector(db, principal, _payload()), 201)


@require_authenticated
def update_sector(app, operation, request, *, principal: Principal, **kwargs):
    sector_id = kwargs.get("sector_id") or flask_request.view_args.get("sector_id")
    with get_db() as db:
        return (admin_service.upsert_sector(db, principal, _payload(), sector_id=sector_id), 200)


@require_authenticated
def list_memberships(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": admin_service.memberships(db, principal, sector_code=_arg("sector_code"))}, 200)


@require_authenticated
def grant_membership(app, operation, request, *, principal: Principal, **kwargs):
    payload = _payload()
    user_id = payload.get("user_id")
    sector_code = payload.get("sector_code")
    role = payload.get("role")
    if not user_id or not sector_code or not role:
        raise ValidationError("user_id, sector_code and role are required")
    with get_db() as db:
        return (admin_service.grant_membership(db, principal, user_id, sector_code, role), 201)


@require_authenticated
def revoke_membership(app, operation, request, *, principal: Principal, **kwargs):
    membership_id = kwargs.get("membership_id") or flask_request.view_args.get("membership_id")
    with get_db() as db:
        admin_service.revoke_membership(db, principal, membership_id)
        return ("", 204)


@require_authenticated
def group_hierarchy(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.group_hierarchy(db, principal), 200)


@require_authenticated
def metadata_keys(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": admin_service.metadata_keys(db, principal)}, 200)


@require_authenticated
def upsert_metadata_key(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_metadata_key(db, principal, _payload()), 200)


@require_authenticated
def ticket_metadatas(app, operation, request, *, principal: Principal, **kwargs):
    limit = int(_arg("limit", 100) or 100)
    offset = int(_arg("offset", 0) or 0)
    with get_db() as db:
        items, total = admin_service.ticket_metadatas(
            db,
            principal,
            ticket_code=_arg("ticket_code"),
            key=_arg("key"),
            search=_arg("search"),
            limit=limit,
            offset=offset,
        )
        return ({"items": items, "total": total}, 200)


@require_authenticated
def upsert_ticket_metadata(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_ticket_metadata(db, principal, _payload()), 200)


@require_authenticated
def delete_ticket_metadata(app, operation, request, *, principal: Principal, **kwargs):
    metadata_id = kwargs.get("metadata_id") or flask_request.view_args.get("metadata_id")
    with get_db() as db:
        admin_service.delete_ticket_metadata(db, principal, metadata_id)
        return ("", 204)


@require_authenticated
def system_settings(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": admin_service.list_system_settings(db, principal)}, 200)


@require_authenticated
def upsert_system_setting(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_system_setting(db, principal, _payload()), 200)


@require_authenticated
def list_widget_definitions(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        items = dashboard_service.list_widget_definitions(db, principal)
        return ({"items": [_serialize_widget_definition(i) for i in items]}, 200)


@require_authenticated
def upsert_widget_definition(app, operation, request, *, principal: Principal, **kwargs):
    if not principal.is_admin:
        raise PermissionDeniedError("admin only")
    payload = _payload()
    w_type = payload.get("type")
    if not w_type:
        raise ValidationError("type is required")

    with get_db() as db:
        wd = db.get(WidgetDefinition, w_type)
        if not wd:
            wd = WidgetDefinition(type=w_type)
            db.add(wd)

        if "display_name" in payload:
            wd.display_name = payload["display_name"]
        if "description" in payload:
            wd.description = payload["description"]
        if "is_active" in payload:
            wd.is_active = bool(payload["is_active"])
        if "icon" in payload:
            wd.icon = payload["icon"]
        if "required_roles" in payload:
            wd.required_roles = payload["required_roles"]

        db.flush()
        return (_serialize_widget_definition(wd), 200)


@require_authenticated
def sync_widget_catalogue(app, operation, request, *, principal: Principal, **kwargs):
    if not principal.is_admin:
        raise PermissionDeniedError("admin only")
    with get_db() as db:
        dashboard_service.sync_widget_catalogue(db)
        return ({"status": "synchronized"}, 200)


# ── Categories / Subcategories / Subcategory fields ────────────────────────

@require_authenticated
def list_categories(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return ({"items": admin_service.list_categories(db, principal)}, 200)


@require_authenticated
def upsert_category(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_category(db, principal, _payload()), 200)


@require_authenticated
def delete_category(app, operation, request, *, principal: Principal, **kwargs):
    category_id = kwargs.get("category_id") or flask_request.view_args.get("category_id")
    with get_db() as db:
        admin_service.delete_category(db, principal, category_id)
        return ("", 204)


@require_authenticated
def upsert_subcategory(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_subcategory(db, principal, _payload()), 200)


@require_authenticated
def delete_subcategory(app, operation, request, *, principal: Principal, **kwargs):
    subcategory_id = kwargs.get("subcategory_id") or flask_request.view_args.get("subcategory_id")
    with get_db() as db:
        admin_service.delete_subcategory(db, principal, subcategory_id)
        return ("", 204)


@require_authenticated
def upsert_subcategory_field(app, operation, request, *, principal: Principal, **kwargs):
    with get_db() as db:
        return (admin_service.upsert_subcategory_field(db, principal, _payload()), 200)


@require_authenticated
def delete_subcategory_field(app, operation, request, *, principal: Principal, **kwargs):
    field_id = kwargs.get("field_id") or flask_request.view_args.get("field_id")
    with get_db() as db:
        admin_service.delete_subcategory_field(db, principal, field_id)
        return ("", 204)


def _serialize_widget_definition(wd: WidgetDefinition) -> dict:
    return {
        "type": wd.type,
        "display_name": wd.display_name,
        "description": wd.description,
        "is_active": wd.is_active,
        "icon": wd.icon,
        "required_roles": wd.required_roles,
        "created_at": wd.created_at.isoformat(),
        "updated_at": wd.updated_at.isoformat(),
    }
