"""GET /api/me — return the authenticated principal as JSON."""
from src.iam.decorators import require_authenticated
from src.iam.principal import Principal


@require_authenticated
def me(app, operation, request, *, principal: Principal, **kwargs):
    return ({
        "user_id":          principal.user_id,
        "keycloak_subject": principal.keycloak_subject,
        "username":         principal.username,
        "email":            principal.email,
        "first_name":       principal.first_name,
        "last_name":        principal.last_name,
        "user_type":        principal.user_type,
        "roles":            sorted(principal.global_roles),
        "sectors": [
            {"sector_code": m.sector_code, "role": m.role}
            for m in principal.sector_memberships
        ],
        "is_admin":       principal.is_admin,
        "is_auditor":     principal.is_auditor,
        "is_distributor": principal.is_distributor,
    }, 200)
