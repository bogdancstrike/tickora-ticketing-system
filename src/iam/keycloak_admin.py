"""Keycloak admin REST wrapper.

Authenticates as Tickora's API service account (client_credentials grant).
Used by admin endpoints to manage users/groups/roles and to mirror sector
membership changes from Tickora UI back to Keycloak.
"""
from typing import Any, Optional

from keycloak import KeycloakAdmin, KeycloakOpenIDConnection

from src.config import Config
from framework.commons.logger import logger as log


class KeycloakAdminClient:
    """Lazy-instantiated wrapper. One instance per process is sufficient."""

    _instance: Optional["KeycloakAdminClient"] = None

    def __init__(self) -> None:
        conn = KeycloakOpenIDConnection(
            server_url    = Config.KEYCLOAK_SERVER_URL,
            realm_name    = Config.KEYCLOAK_REALM,
            client_id     = Config.KEYCLOAK_API_CLIENT_ID,
            client_secret_key = Config.KEYCLOAK_API_CLIENT_SECRET,
            verify        = True,
        )
        self._kc = KeycloakAdmin(connection=conn)

    @classmethod
    def get(cls) -> "KeycloakAdminClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Users ─────────────────────────────────────────────────────────────
    def list_users(self, query: str | None = None, *, first: int = 0, max_: int = 100) -> list[dict]:
        params: dict[str, Any] = {"first": first, "max": max_}
        if query:
            params["search"] = query
        return self._kc.get_users(params)

    def get_user(self, user_id: str) -> dict:
        return self._kc.get_user(user_id)

    def set_user_enabled(self, user_id: str, enabled: bool) -> None:
        self._kc.update_user(user_id=user_id, payload={"enabled": enabled})

    # ── Groups ────────────────────────────────────────────────────────────
    def list_groups(self) -> list[dict]:
        return self._kc.get_groups(full_hierarchy=True)

    def find_group_by_path(self, path: str) -> dict | None:
        try:
            return self._kc.get_group_by_path(path)
        except Exception:
            return None

    def group_children(self, group_id: str) -> list[dict]:
        return self._kc.get_group_children(group_id, full_hierarchy=True)

    def add_user_to_group(self, user_id: str, group_id: str) -> None:
        self._kc.group_user_add(user_id, group_id)

    def remove_user_from_group(self, user_id: str, group_id: str) -> None:
        self._kc.group_user_remove(user_id, group_id)

    # ── Realm roles ───────────────────────────────────────────────────────
    def list_realm_roles(self) -> list[dict]:
        return self._kc.get_realm_roles()

    def assign_realm_role(self, user_id: str, role_name: str) -> None:
        role = self._kc.get_realm_role(role_name)
        self._kc.assign_realm_roles(user_id=user_id, roles=[role])

    def remove_realm_role(self, user_id: str, role_name: str) -> None:
        role = self._kc.get_realm_role(role_name)
        self._kc.delete_realm_roles_of_user(user_id=user_id, roles=[role])
