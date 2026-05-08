from src.api import me as me_api
from src.iam.principal import Principal, ROLE_ADMIN


def test_admin_sector_payload_uses_dynamic_keycloak_group_tree(monkeypatch):
    monkeypatch.setattr(me_api, "_keycloak_sector_codes", lambda: ["s11", "s2"])
    monkeypatch.setattr(me_api, "_db_sector_codes", lambda: (_ for _ in ()).throw(AssertionError("db fallback not expected")))

    payload = me_api._sector_payload(Principal(
        user_id="user-1",
        keycloak_subject="kc-sub-1",
        global_roles=frozenset({ROLE_ADMIN}),
    ))

    assert payload == [
        {"sector_code": "s11", "role": "chief"},
        {"sector_code": "s11", "role": "member"},
        {"sector_code": "s2", "role": "chief"},
        {"sector_code": "s2", "role": "member"},
    ]


def test_keycloak_sector_codes_reads_group_children(monkeypatch):
    class FakeClient:
        def find_group_by_path(self, path):
            assert path == "/tickora/sectors"
            return {"id": "sectors-id", "name": "sectors", "subGroups": []}

        def group_children(self, group_id):
            assert group_id == "sectors-id"
            return [{"name": "s12"}, {"name": "s2"}]

    monkeypatch.setattr(me_api.KeycloakAdminClient, "get", lambda: FakeClient())

    assert me_api._keycloak_sector_codes() == ["s12", "s2"]
