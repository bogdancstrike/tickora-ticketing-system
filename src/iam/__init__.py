"""IAM — identity, RBAC, Keycloak interface.

Importing this package is intentionally cheap. Pull individual symbols from
their submodules, e.g.::

    from src.iam.principal import Principal
    from src.iam.rbac import can_view_ticket
    from src.iam.decorators import require_authenticated
"""
