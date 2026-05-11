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
    beneficiary_type: str = "internal"
    requester_email: Optional[str] = None
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

    def test_external_requester_sees_ticket_by_email(self):
        p = make_principal(user_id="u-ben", roles=(ROLE_EXTERNAL_USER,), user_type="external")
        t = FakeTicket(
            beneficiary_type="external",
            requester_email="u-ben@x",
            current_sector_code=None,
        )
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
    def test_admin_cannot_without_beneficiary_link(self, fn):
        p = make_principal(roles=(ROLE_ADMIN,))
        assert fn(p, FakeTicket()) is False

    @pytest.mark.parametrize("fn", [rbac.can_close, rbac.can_reopen])
    def test_external_requester_email_can(self, fn):
        p = make_principal(user_id="u-ben", roles=(ROLE_EXTERNAL_USER,), user_type="external")
        t = FakeTicket(beneficiary_type="external", requester_email="u-ben@x")
        assert fn(p, t) is True


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


# ── Self-assignment gate (added 2026-05-09) ──────────────────────────────────
#
# Comments and operator-side status transitions require the active-assignee
# link. Beneficiaries keep requester-side public comments and close/reopen.
class TestSelfAssignmentGate:
    def _ticket(self, *, assignee="u-other", status="in_progress",
               creator=None, beneficiary=None, sector="s10"):
        return FakeTicket(
            status=status,
            current_sector_code=sector,
            assignee_user_id=assignee,
            created_by_user_id=creator,
            beneficiary_user_id=beneficiary,
        )

    # ── can_post_public_comment ────────────────────────────────────────────
    def test_active_assignee_can_post_public(self):
        p = make_principal(user_id="u-self")
        t = self._ticket(assignee="u-self")
        assert rbac.can_post_public_comment(p, t) is True

    def test_admin_cannot_post_public_without_assignment(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        t = self._ticket(assignee="u-other")
        assert rbac.can_post_public_comment(p, t) is False

    def test_creator_can_post_public(self):
        p = make_principal(user_id="u-creator")
        t = self._ticket(assignee="u-other", creator="u-creator")
        assert rbac.can_post_public_comment(p, t) is True

    def test_beneficiary_user_can_post_public(self):
        p = make_principal(user_id="u-ben")
        t = self._ticket(assignee="u-other", beneficiary="u-ben")
        assert rbac.can_post_public_comment(p, t) is True

    def test_distributor_no_longer_posts_public(self):
        p = make_principal(roles=(ROLE_DISTRIBUTOR,))
        t = self._ticket(assignee="u-other")
        assert rbac.can_post_public_comment(p, t) is False

    def test_chief_no_longer_posts_public_without_assignment(self):
        p = make_principal(memberships=(SectorMembership("s10", "chief"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_post_public_comment(p, t) is False

    def test_member_no_longer_posts_public_without_assignment(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_post_public_comment(p, t) is False

    # ── can_post_private_comment ───────────────────────────────────────────
    def test_active_assignee_can_post_private(self):
        p = make_principal(user_id="u-self")
        t = self._ticket(assignee="u-self")
        assert rbac.can_post_private_comment(p, t) is True

    def test_distributor_cannot_post_private_without_assignment(self):
        p = make_principal(roles=(ROLE_DISTRIBUTOR,))
        t = self._ticket(assignee="u-other", status="pending")
        assert rbac.can_post_private_comment(p, t) is False

    def test_admin_cannot_post_private_without_assignment(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        t = self._ticket(assignee="u-other")
        assert rbac.can_post_private_comment(p, t) is False

    def test_unassigned_member_cannot_post_private(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_post_private_comment(p, t) is False

    def test_unassigned_chief_cannot_post_private(self):
        p = make_principal(memberships=(SectorMembership("s10", "chief"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_post_private_comment(p, t) is False

    # ── can_drive_status / can_mark_done ───────────────────────────────────
    def test_active_assignee_drives_status(self):
        p = make_principal(user_id="u-self")
        t = self._ticket(assignee="u-self")
        assert rbac.can_drive_status(p, t) is True
        assert rbac.can_mark_done(p, t) is True

    def test_admin_does_not_drive_status_without_assignment(self):
        p = make_principal(roles=(ROLE_ADMIN,))
        t = self._ticket(assignee="u-other")
        assert rbac.can_drive_status(p, t) is False
        assert rbac.can_mark_done(p, t) is False

    def test_chief_does_not_drive_status_without_assignment(self):
        p = make_principal(memberships=(SectorMembership("s10", "chief"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_drive_status(p, t) is False
        assert rbac.can_mark_done(p, t) is False

    def test_member_does_not_drive_status_without_assignment(self):
        p = make_principal(memberships=(SectorMembership("s10", "member"),))
        t = self._ticket(assignee="u-other", sector="s10")
        assert rbac.can_drive_status(p, t) is False
        assert rbac.can_mark_done(p, t) is False
