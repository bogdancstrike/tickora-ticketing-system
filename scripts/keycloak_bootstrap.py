#!/usr/bin/env python3
"""Idempotently provision the Tickora realm in Keycloak.

Run after `docker compose up -d keycloak`. Creates:
- realm `tickora`
- confidential client `tickora-api` (service account on)
- public client `tickora-spa` (PKCE)
- realm roles for feature permissions
- hierarchical groups:
  - /tickora for full platform access
  - /tickora/sectors/<sN> for effective sector chief+member access
  - /tickora/sectors/<sN>/{members,chiefs} for narrower sector access

Idempotent: re-running is a no-op for already-existing entities.
"""
from __future__ import annotations

import sys
import time
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from src.config import Config

REALM = Config.KEYCLOAK_REALM
SECTORS = [
    code.strip().lower()
    for code in os.getenv("KEYCLOAK_BOOTSTRAP_SECTORS", ",".join(f"s{i}" for i in range(1, 11))).split(",")
    if code.strip()
]
SPA_ORIGINS = [origin.rstrip("/") for origin in Config.ALLOWED_ORIGINS]
SPA_REDIRECT_URIS = [f"{origin}/*" for origin in SPA_ORIGINS]

REALM_ROLES = [
    "tickora_admin",
    "tickora_auditor",
    "tickora_distributor",
    "tickora_avizator",
    "tickora_internal_user",
    "tickora_external_user",
    "tickora_service_account",
]

DEPRECATED_REALM_ROLES = [
    "tickora_sector_member",
    "tickora_sector_chief",
]


def admin() -> KeycloakAdmin:
    kc = KeycloakAdmin(
        server_url=Config.KEYCLOAK_SERVER_URL,
        username=Config.KEYCLOAK_ADMIN_USER,
        password=Config.KEYCLOAK_ADMIN_PASSWORD,
        realm_name="master",
        user_realm_name="master",
        verify=True,
    )
    return kc


def wait_for_keycloak(timeout_s: int = 90) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    while time.monotonic() < deadline:
        try:
            admin().get_realms()
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
    raise RuntimeError(f"Keycloak is not ready after {timeout_s}s: {last_error}")


def ensure_realm(kc: KeycloakAdmin) -> None:
    realms = {r["realm"] for r in kc.get_realms()}
    if REALM in realms:
        print(f"[realm] '{REALM}' exists")
    else:
        kc.create_realm({"realm": REALM, "enabled": True}, skip_exists=True)
        print(f"[realm] created '{REALM}'")
    kc.change_current_realm(REALM)


def cleanup_master_business_objects() -> None:
    """Remove Tickora application artifacts accidentally created in master.

    The master realm is only for Keycloak administration. Tickora roles,
    groups, and OIDC clients belong exclusively to the configured
    application realm. On a fresh KC install master is clean and every
    branch below is a quiet no-op.
    """
    try:
        kc = admin()
        kc.change_current_realm("master")
    except Exception as exc:
        print(f"[cleanup:master] cannot reach master realm: {exc}")
        return

    for client_id in (Config.KEYCLOAK_API_CLIENT_ID, Config.KEYCLOAK_SPA_CLIENT_ID):
        try:
            client_uuid = _client_uuid(kc, client_id)
            if client_uuid:
                kc.delete_client(client_uuid)
                print(f"[cleanup:master] deleted client '{client_id}'")
        except Exception:
            pass

    try:
        group = _get_group(kc, "/tickora")
        if group:
            kc.delete_group(group["id"])
            print("[cleanup:master] deleted group '/tickora'")
    except Exception:
        pass

    for role in REALM_ROLES + DEPRECATED_REALM_ROLES:
        try:
            kc.get_realm_role(role)
            kc.delete_realm_role(role)
            print(f"[cleanup:master] deleted role '{role}'")
        except Exception:
            pass


def ensure_role(kc: KeycloakAdmin, name: str) -> None:
    try:
        kc.create_realm_role({"name": name}, skip_exists=True)
        print(f"[role] {name}")
    except Exception as e:
        print(f"[role] {name}: {e}")


def delete_realm_role_if_exists(kc: KeycloakAdmin, name: str) -> None:
    try:
        kc.get_realm_role(name)
        kc.delete_realm_role(name)
        print(f"[role:deprecated] deleted {name}")
    except Exception:
        pass


def _get_group(kc: KeycloakAdmin, path: str) -> dict | None:
    try:
        return kc.get_group_by_path(path)
    except Exception:
        return None


def ensure_group(kc: KeycloakAdmin, path: str) -> None:
    parts = [p for p in path.split("/") if p]
    parent_id: str | None = None
    for depth, part in enumerate(parts):
        full = "/" + "/".join(parts[: depth + 1])
        existing = _get_group(kc, full)
        if existing:
            parent_id = existing["id"]
            continue
        payload = {"name": part}
        if parent_id is None:
            new_id = kc.create_group(payload, skip_exists=True)
        else:
            new_id = kc.create_group(payload, parent=parent_id, skip_exists=True)
        parent_id = new_id
        print(f"[group] {full}")


def _client_uuid(kc: KeycloakAdmin, client_id: str) -> str | None:
    try:
        return kc.get_client_id(client_id)
    except KeycloakGetError:
        return None


def _base_client_payload(*, client_id: str, public: bool) -> dict:
    payload = {
        "clientId": client_id,
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": public,
        "standardFlowEnabled": public,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": not public,
        "serviceAccountsEnabled": not public,
        "redirectUris": SPA_REDIRECT_URIS if public else [],
        "webOrigins": SPA_ORIGINS if public else [],
        "attributes": {
            "pkce.code.challenge.method": "S256" if public else "",
            "post.logout.redirect.uris": "+",
        },
    }
    if public:
        payload["rootUrl"] = SPA_ORIGINS[0] if SPA_ORIGINS else "http://localhost:5173"
        payload["baseUrl"] = "/"
    else:
        payload["clientAuthenticatorType"] = "client-secret"
        if Config.KEYCLOAK_API_CLIENT_SECRET:
            payload["secret"] = Config.KEYCLOAK_API_CLIENT_SECRET
    return payload


def ensure_client(kc: KeycloakAdmin, *, client_id: str, public: bool) -> str:
    client_uuid = _client_uuid(kc, client_id)
    payload = _base_client_payload(client_id=client_id, public=public)
    if client_uuid:
        current = kc.get_client(client_uuid)
        current.update(payload)
        kc.update_client(client_uuid, current)
        print(f"[client] updated '{client_id}'")
        return client_uuid

    kc.create_client(payload, skip_exists=True)
    client_uuid = _client_uuid(kc, client_id)
    if not client_uuid:
        raise RuntimeError(f"client was not created: {client_id}")
    print(f"[client] created '{client_id}' (public={public})")
    return client_uuid


def ensure_api_service_account_access(kc: KeycloakAdmin, *, api_uuid: str) -> None:
    """Allow the API service account to read the dynamic organization tree.

    Idempotent — assigning a client role that's already assigned is a
    no-op in Keycloak. Any role names missing from this realm version
    are skipped with a warning so we don't break a fresh install where
    the role names changed across Keycloak versions.
    """
    realm_management_uuid = _client_uuid(kc, "realm-management")
    if not realm_management_uuid:
        raise RuntimeError("realm-management client not found")
    service_account = kc.get_client_service_account_user(api_uuid)
    wanted = ("query-groups", "query-users", "view-users", "view-realm")
    roles = []
    for role in wanted:
        try:
            roles.append(kc.get_client_role(realm_management_uuid, role))
        except Exception as exc:
            print(f"[client:sa] missing realm-management role '{role}': {exc}")
    if roles:
        kc.assign_client_role(
            user_id=service_account["id"],
            client_id=realm_management_uuid,
            roles=roles,
        )
        print("[client] tickora-api service account can read groups/users")


def ensure_mapper(kc: KeycloakAdmin, *, client_uuid: str, name: str, payload: dict) -> None:
    existing = {m["name"]: m for m in kc.get_mappers_from_client(client_uuid)}
    if name in existing:
        mapper = existing[name]
        mapper.update(payload)
        kc.update_client_mapper(client_uuid, mapper["id"], mapper)
        print(f"[mapper] updated {name}")
        return
    kc.add_mapper_to_client(client_uuid, payload)
    print(f"[mapper] created {name}")


def ensure_spa_token_mappers(kc: KeycloakAdmin, *, spa_uuid: str) -> None:
    ensure_mapper(
        kc,
        client_uuid=spa_uuid,
        name="tickora-api-audience",
        payload={
            "name": "tickora-api-audience",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "consentRequired": False,
            "config": {
                "included.client.audience": Config.KEYCLOAK_API_CLIENT_ID,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        },
    )
    ensure_mapper(
        kc,
        client_uuid=spa_uuid,
        name="tickora-groups",
        payload={
            "name": "tickora-groups",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-group-membership-mapper",
            "consentRequired": False,
            "config": {
                "claim.name": "groups",
                "full.path": "true",
                "id.token.claim": "true",
                "access.token.claim": "true",
                "userinfo.token.claim": "true",
            },
        },
    )


def main() -> int:
    wait_for_keycloak()
    cleanup_master_business_objects()
    kc = admin()
    ensure_realm(kc)
    for r in REALM_ROLES:
        ensure_role(kc, r)
    for r in DEPRECATED_REALM_ROLES:
        delete_realm_role_if_exists(kc, r)
    ensure_group(kc, "/tickora")
    ensure_group(kc, "/tickora/beneficiaries")
    ensure_group(kc, "/tickora/beneficiaries/internal")
    ensure_group(kc, "/tickora/beneficiaries/external")
    ensure_group(kc, "/tickora/sectors")
    for code in SECTORS:
        ensure_group(kc, f"/tickora/sectors/{code}")
        ensure_group(kc, f"/tickora/sectors/{code}/member")
        ensure_group(kc, f"/tickora/sectors/{code}/chief")
    api_uuid = ensure_client(kc, client_id=Config.KEYCLOAK_API_CLIENT_ID, public=False)
    ensure_api_service_account_access(kc, api_uuid=api_uuid)
    spa_uuid = ensure_client(kc, client_id=Config.KEYCLOAK_SPA_CLIENT_ID, public=True)
    ensure_spa_token_mappers(kc, spa_uuid=spa_uuid)
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
