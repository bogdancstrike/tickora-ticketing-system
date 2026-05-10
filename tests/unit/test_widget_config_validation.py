"""Unit tests for src/ticketing/service/dashboard_service._validate_widget_config.

The validator is the write-time gate that stops a sector-N user from
pinning a widget at sector-M data. The data endpoints already filter
results server-side, but rejecting at write time gives the UI a clean
error and closes the probe-by-config oracle.
"""
from unittest.mock import MagicMock

import pytest

from src.core.errors import PermissionDeniedError, ValidationError
from src.iam.principal import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_INTERNAL_USER,
    Principal,
    SectorMembership,
)
from src.ticketing.service import dashboard_service


def _principal(*, roles: tuple[str, ...] = (), sectors: tuple[str, ...] = ()) -> Principal:
    memberships = tuple(SectorMembership(code, "member") for code in sectors)
    return Principal(
        user_id="u-self",
        keycloak_subject="kc-self",
        username="self",
        email="self@x",
        user_type="internal",
        global_roles=frozenset(roles),
        sector_memberships=memberships,
    )


class TestValidateWidgetConfig:
    def test_none_or_empty_is_ok(self):
        p = _principal()
        dashboard_service._validate_widget_config(p, MagicMock(), None)
        dashboard_service._validate_widget_config(p, MagicMock(), {})

    def test_non_dict_rejected(self):
        p = _principal()
        with pytest.raises(ValidationError):
            dashboard_service._validate_widget_config(p, MagicMock(), "not a dict")

    def test_unknown_keys_pass_through(self):
        p = _principal()
        # Unknown keys must not break older clients.
        dashboard_service._validate_widget_config(p, MagicMock(), {"foo": 1, "bar": "x"})

    def test_valid_scope_accepted(self):
        p = _principal()
        for s in ("global", "sector", "personal", "my_requests"):
            dashboard_service._validate_widget_config(p, MagicMock(), {"scope": s})

    def test_invalid_scope_rejected(self):
        p = _principal()
        with pytest.raises(ValidationError):
            dashboard_service._validate_widget_config(p, MagicMock(), {"scope": "elsewhere"})

    def test_member_can_target_own_sector(self):
        p = _principal(sectors=("s10",))
        dashboard_service._validate_widget_config(p, MagicMock(), {"sector_code": "s10"})

    def test_camel_case_sectorCode_also_recognised(self):
        p = _principal(sectors=("s10",))
        dashboard_service._validate_widget_config(p, MagicMock(), {"sectorCode": "s10"})

    def test_member_blocked_from_foreign_sector(self):
        p = _principal(sectors=("s10",))
        with pytest.raises(PermissionDeniedError):
            dashboard_service._validate_widget_config(p, MagicMock(), {"sector_code": "s2"})

    def test_admin_can_target_any_sector(self):
        p = _principal(roles=(ROLE_ADMIN,))
        dashboard_service._validate_widget_config(p, MagicMock(), {"sector_code": "anywhere"})

    def test_auditor_can_target_any_sector(self):
        p = _principal(roles=(ROLE_AUDITOR,))
        dashboard_service._validate_widget_config(p, MagicMock(), {"sector_code": "anywhere"})

    def test_ticket_id_routes_through_visibility_check(self, monkeypatch):
        """ticket_service.get is the canonical visibility check; we delegate."""
        from src.core.errors import NotFoundError

        called = {}

        def fake_get(db, principal, ticket_id):
            called["args"] = (db, principal.user_id, ticket_id)
            raise NotFoundError("not visible")

        # Stub out ticket_service.get so we don't need a DB.
        from src.ticketing.service import ticket_service
        monkeypatch.setattr(ticket_service, "get", fake_get)

        p = _principal(roles=(ROLE_INTERNAL_USER,))
        with pytest.raises(NotFoundError):
            dashboard_service._validate_widget_config(p, MagicMock(), {"ticketId": "t-x"})
        assert called["args"][1] == "u-self"
        assert called["args"][2] == "t-x"
