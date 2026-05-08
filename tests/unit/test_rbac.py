"""Unit tests for src/iam/rbac.py — encodes the BRD §9.4 matrix."""
from dataclasses import dataclass
from typing import Optional

import pytest

from src.iam import rbac
from src.iam.principal import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DISTRIBUTOR,
    ROLE_EXTERNAL_USER,
    ROLE_INTERNAL_USER,
    Principal,
    SectorMembership,
)


@dataclass
class FakeTicket:
    id: str = "t-1"
    status: str = "in_progress"
    current_sector_code: Optional[str] = "s10"
    assignee_user_id: Optional[str] = None
    last_active_assignee_user_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    beneficiary_user_id: Optional[str] = None
    is_deleted: bool = False


def make_principal(
    user_id: str = "u-self",
    *,
    roles: tuple[str, ...] = (),
    user_type: str = "internal",
    memberships: tuple[SectorMembership, ...] = (),
) -> Principal:
    return Principal(
        user_id=user_id,
        keycloak_subject=f"kc-{user_id}",
        username=f"user-{user_id}",
        email=f"{user_id}@x",
        user_type=user_type,
        global_roles=frozenset(roles),
        sector_memberships=memberships,
    )


# ── Visibility ────────────────────────────────────────────────────────────────

class TestCanViewTicket:
    def test_admin_sees_everything(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        assert rbac.can_view_ticket(p, FakeTicket()) is True

    def test_auditor_sees_everything(self):
        p = make_principal(roles=(ROLE_AUDITOR,))
        assert rbac.can_view_ticket(p, FakeTicket()) is True

    def test_creator_sees_own(self):
        p = make_principal(user_id="u-creator", roles=(ROLE_INTERNAL_USER,))
        t = FakeTicket(created_by_user_id="u-creator", current_sector_code=None)
        assert rbac.can_view_ticket(p, t) is True

    def test_beneficiary_sees_own(self):
        p = make_principal(user_id="u-ben", roles=(ROLE_EXTERNAL_USER,))
        t = FakeTicket(beneficiary_user_id="u-ben", current_sector_code=None)
        assert rbac.can_view_ticket(p, t) is True

    def test_sector_member_sees_sector_ticket(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        assert rbac.can_view_ticket(p, FakeTicket(current_sector_code="s10")) is True

    def test_sector_chief_sees_sector_ticket(self):
        p = make_principal(memberships=(SectorMembership("s10", "chief"),))
        assert rbac.can_view_ticket(p, FakeTicket(current_sector_code="s10")) is True

    def test_member_of_other_sector_blocked(self):
        p = make_principal(memberships=(SectorMembership("s9", "member"),))
        assert rbac.can_view_ticket(p, FakeTicket(current_sector_code="s10")) is False

    def test_distributor_sees_pending(self):
        p = make_principal(roles=(ROLE_DISTRIBUTOR,))
        t = FakeTicket(status="pending", current_sector_code=None)
        assert rbac.can_view_ticket(p, t) is True

    def test_distributor_does_not_see_in_progress_other_sector(self):
        p = make_principal(roles=(ROLE_DISTRIBUTOR,))
        t = FakeTicket(status="in_progress", current_sector_code="s10")
        assert rbac.can_view_ticket(p, t) is False

    def test_random_internal_user_blocked(self):
        p = make_principal(roles=(ROLE_INTERNAL_USER,))
        assert rbac.can_view_ticket(p, FakeTicket()) is False


# ── Mutation ──────────────────────────────────────────────────────────────────

class TestCanModifyTicket:
    def test_admin_modifies(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        assert rbac.can_modify_ticket(p, FakeTicket()) is True

    def test_assignee_modifies(self):
        p = make_principal(user_id="u-assignee")
        t = FakeTicket(assignee_user_id="u-assignee")
        assert rbac.can_modify_ticket(p, t) is True

    def test_chief_of_current_sector_modifies(self):
        p = make_principal(memberships=(SectorMembership("s10", "chief"),))
        assert rbac.can_modify_ticket(p, FakeTicket(current_sector_code="s10")) is True

    def test_member_of_sector_but_not_assignee_blocked(self):
        p = make_principal(user_id="u-other", memberships=(SectorMembership("s10", "member"),))
        t = FakeTicket(current_sector_code="s10", assignee_user_id="u-someone-else")
        assert rbac.can_modify_ticket(p, t) is False

    def test_creator_alone_does_not_modify(self):
        p = make_principal(user_id="u-creator", roles=(ROLE_INTERNAL_USER,))
        t = FakeTicket(created_by_user_id="u-creator", current_sector_code=None)
        assert rbac.can_modify_ticket(p, t) is False


# ── Workflow predicates ───────────────────────────────────────────────────────

class TestAssignToMe:
    def test_member_of_sector_can(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        assert rbac.can_assign_to_me(p, FakeTicket(current_sector_code="s10")) is True

    def test_member_of_other_sector_cannot(self):
        p = make_principal(memberships=(SectorMembership("s9", "member"),))
        assert rbac.can_assign_to_me(p, FakeTicket(current_sector_code="s10")) is False

    def test_admin_can(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        assert rbac.can_assign_to_me(p, FakeTicket()) is True


class TestCloseAndReopen:
    @pytest.mark.parametrize("fn", [rbac.can_close, rbac.can_reopen])
    def test_creator_can(self, fn):
        p = make_principal(user_id="u-creator")
        t = FakeTicket(created_by_user_id="u-creator", status="done")
        assert fn(p, t) is True

    @pytest.mark.parametrize("fn", [rbac.can_close, rbac.can_reopen])
    def test_other_user_cannot(self, fn):
        p = make_principal(user_id="u-other")
        t = FakeTicket(created_by_user_id="u-creator")
        assert fn(p, t) is False

    @pytest.mark.parametrize("fn", [rbac.can_close, rbac.can_reopen])
    def test_admin_can(self, fn):
        p = make_principal(roles=(ROLE_ADMIN,))
        assert fn(p, FakeTicket()) is True


class TestPrivateComments:
    def test_external_beneficiary_blocked(self):
        p = make_principal(user_id="u-ben", roles=(ROLE_EXTERNAL_USER,), user_type="external")
        t = FakeTicket(beneficiary_user_id="u-ben", current_sector_code="s10")
        assert rbac.can_see_private_comments(p, t) is False

    def test_sector_member_can_see(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        assert rbac.can_see_private_comments(p, FakeTicket(current_sector_code="s10")) is True

    def test_distributor_can_see(self):
        p = make_principal(roles=(ROLE_DISTRIBUTOR,))
        assert rbac.can_see_private_comments(p, FakeTicket()) is True

    def test_auditor_can_see(self):
        p = make_principal(roles=(ROLE_AUDITOR,))
        assert rbac.can_see_private_comments(p, FakeTicket()) is True

    def test_random_internal_user_blocked(self):
        p = make_principal(roles=(ROLE_INTERNAL_USER,))
        t = FakeTicket(current_sector_code="s10")
        assert rbac.can_see_private_comments(p, t) is False


class TestAdminAndDashboard:
    def test_only_admin_administers(self):
        assert rbac.can_administer(make_principal(roles=(ROLE_ADMIN,))) is True
        assert rbac.can_administer(make_principal(roles=(ROLE_AUDITOR,))) is False
        assert rbac.can_administer(make_principal(roles=())) is False

    def test_global_dashboard(self):
        assert rbac.can_view_global_dashboard(make_principal(roles=(ROLE_ADMIN,))) is True
        assert rbac.can_view_global_dashboard(make_principal(roles=(ROLE_AUDITOR,))) is True
        assert rbac.can_view_global_dashboard(make_principal()) is False

    def test_sector_dashboard(self):
        chief = make_principal(memberships=(SectorMembership("s10", "chief"),))
        member = make_principal(memberships=(SectorMembership("s10", "member"),))
        outsider = make_principal(memberships=(SectorMembership("s9", "member"),))
        assert rbac.can_view_sector_dashboard(chief,    "s10") is True
        assert rbac.can_view_sector_dashboard(member,   "s10") is True
        assert rbac.can_view_sector_dashboard(outsider, "s10") is False
