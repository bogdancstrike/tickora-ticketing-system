"""Integration tests for `src.ticketing.service.comment_service`.

Covers the post-2026-05-09 self-assignment policy:
  * Active assignee can post both public and private comments.
  * Bystander chiefs/members cannot post until they self-assign.
  * Distributors keep the private-comment lane during triage.
  * Beneficiaries can post public, never private.
  * Admins keep the override.

Edit window (15 min) and visibility filtering on `list_` are also exercised.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from src.common.errors import BusinessRuleError, PermissionDeniedError, ValidationError
from src.iam.principal import (
    SectorMembership,
    ROLE_ADMIN,
    ROLE_DISTRIBUTOR,
    ROLE_INTERNAL_USER,
)
from src.ticketing.service import comment_service

from tests.integration.conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)


# ── Fixture factory: ticket routed to s10, assigned to a member ──────────────

@pytest.fixture
def world(db_session: Session):
    sector = create_sector(db_session, code="s10")

    admin_u = create_user(db_session, "admin")
    distributor_u = create_user(db_session, "distributor")
    chief_u = create_user(db_session, "chief.s10")
    member_u = create_user(db_session, "member.s10")
    bystander_u = create_user(db_session, "bystander.s10")
    other_u = create_user(db_session, "member.s2")
    beneficiary_u = create_user(db_session, "beneficiary")

    beneficiary = create_beneficiary(db_session, beneficiary_u)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_u,
        current_sector=sector,
        status="in_progress",
        assignee=member_u,
        last_active_assignee=member_u,
    )
    db_session.commit()

    return {
        "sector": sector,
        "ticket": ticket,
        "principals": {
            "admin": principal_for(admin_u, roles={ROLE_ADMIN}, has_root_group=True),
            "distributor": principal_for(distributor_u, roles={ROLE_DISTRIBUTOR}),
            "chief": principal_for(
                chief_u, roles={ROLE_INTERNAL_USER},
                sectors=(SectorMembership("s10", "chief"),),
            ),
            "assignee": principal_for(
                member_u, roles={ROLE_INTERNAL_USER},
                sectors=(SectorMembership("s10", "member"),),
            ),
            "bystander": principal_for(
                bystander_u, roles={ROLE_INTERNAL_USER},
                sectors=(SectorMembership("s10", "member"),),
            ),
            "outsider": principal_for(other_u, roles={ROLE_INTERNAL_USER}),
            "beneficiary": principal_for(beneficiary_u, roles={ROLE_INTERNAL_USER}),
        },
    }


# ── Validation ───────────────────────────────────────────────────────────────

class TestCreateValidation:
    def test_short_body_rejected(self, db_session, world):
        with pytest.raises(ValidationError, match="at least 2"):
            comment_service.create(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                body="x", visibility="public",
            )

    def test_long_body_rejected(self, db_session, world):
        with pytest.raises(ValidationError, match="too long"):
            comment_service.create(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                body="x" * 10001, visibility="public",
            )

    def test_unknown_visibility_rejected(self, db_session, world):
        with pytest.raises(ValidationError, match="public or private"):
            comment_service.create(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                body="hello world", visibility="restricted",
            )


# ── Self-assignment policy on writes ─────────────────────────────────────────

class TestPublicCommentRBAC:
    def test_active_assignee_can_post(self, db_session, world):
        c = comment_service.create(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            body="working on it", visibility="public",
        )
        assert c.visibility == "public"

    def test_admin_override(self, db_session, world):
        c = comment_service.create(
            db_session, world["principals"]["admin"], world["ticket"].id,
            body="admin note", visibility="public",
        )
        assert c.id is not None

    def test_beneficiary_can_post_public(self, db_session, world):
        c = comment_service.create(
            db_session, world["principals"]["beneficiary"], world["ticket"].id,
            body="thank you", visibility="public",
        )
        assert c.id is not None

    def test_bystander_member_cannot_post_public(self, db_session, world):
        with pytest.raises(PermissionDeniedError):
            comment_service.create(
                db_session, world["principals"]["bystander"], world["ticket"].id,
                body="butting in", visibility="public",
            )

    def test_chief_without_self_assignment_cannot_post_public(self, db_session, world):
        with pytest.raises(PermissionDeniedError):
            comment_service.create(
                db_session, world["principals"]["chief"], world["ticket"].id,
                body="chief commentary", visibility="public",
            )


class TestPrivateCommentRBAC:
    def test_active_assignee_can_post_private(self, db_session, world):
        c = comment_service.create(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            body="internal note", visibility="private",
        )
        assert c.visibility == "private"

    def test_distributor_keeps_private_lane(self, db_session):
        # Distributor's lane is the triage queue (`pending` /
        # `assigned_to_sector`). They can't see in-progress tickets, so
        # this test deliberately uses its own pending ticket fixture
        # rather than the shared `world` (which is in_progress).
        sector = create_sector(db_session, code="s11")
        beneficiary_user = create_user(db_session, "ben.tdistr")
        distributor_user = create_user(db_session, "distr.tdistr")
        beneficiary = create_beneficiary(db_session, beneficiary_user)
        ticket = create_ticket(
            db_session, beneficiary,
            created_by=beneficiary_user, current_sector=sector,
            status="assigned_to_sector",
        )
        db_session.commit()
        principal = principal_for(distributor_user, roles={ROLE_DISTRIBUTOR})
        c = comment_service.create(
            db_session, principal, ticket.id,
            body="triage note", visibility="private",
        )
        assert c.id is not None

    def test_bystander_cannot_post_private(self, db_session, world):
        with pytest.raises(PermissionDeniedError):
            comment_service.create(
                db_session, world["principals"]["bystander"], world["ticket"].id,
                body="snooping", visibility="private",
            )

    def test_beneficiary_cannot_post_private(self, db_session, world):
        with pytest.raises(PermissionDeniedError):
            comment_service.create(
                db_session, world["principals"]["beneficiary"], world["ticket"].id,
                body="external private", visibility="private",
            )


# ── Listing / visibility filtering ───────────────────────────────────────────

class TestListVisibility:
    def _seed(self, db, world):
        comment_service.create(
            db, world["principals"]["assignee"], world["ticket"].id,
            body="public update", visibility="public",
        )
        comment_service.create(
            db, world["principals"]["assignee"], world["ticket"].id,
            body="private internal note", visibility="private",
        )
        db.commit()

    def test_assignee_sees_both(self, db_session, world):
        self._seed(db_session, world)
        comments = comment_service.list_(
            db_session, world["principals"]["assignee"], world["ticket"].id,
        )
        assert {c.visibility for c in comments} == {"public", "private"}

    def test_beneficiary_sees_only_public(self, db_session, world):
        self._seed(db_session, world)
        comments = comment_service.list_(
            db_session, world["principals"]["beneficiary"], world["ticket"].id,
        )
        assert all(c.visibility == "public" for c in comments)
        assert len(comments) == 1

    def test_admin_sees_both(self, db_session, world):
        self._seed(db_session, world)
        comments = comment_service.list_(
            db_session, world["principals"]["admin"], world["ticket"].id,
        )
        assert {c.visibility for c in comments} == {"public", "private"}


# ── Edit window ──────────────────────────────────────────────────────────────

class TestEditWindow:
    def test_author_can_edit_within_window(self, db_session, world):
        comment = comment_service.create(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            body="initial body", visibility="public",
        )
        edited = comment_service.edit(
            db_session, world["principals"]["assignee"], comment.id,
            body="edited body",
        )
        assert edited.body == "edited body"

    def test_edit_after_window_rejected(self, db_session, world):
        comment = comment_service.create(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            body="initial body", visibility="public",
        )
        # Backdate created_at past the 15-minute window.
        comment.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)
        db_session.flush()
        # The service signals an expired edit window with `BusinessRuleError`,
        # not `PermissionDenied` — the user *would* have permission, the
        # window has just closed.
        with pytest.raises(BusinessRuleError, match="window"):
            comment_service.edit(
                db_session, world["principals"]["assignee"], comment.id,
                body="too late",
            )

    def test_other_user_cannot_edit(self, db_session, world):
        comment = comment_service.create(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            body="mine", visibility="public",
        )
        with pytest.raises(PermissionDeniedError):
            comment_service.edit(
                db_session, world["principals"]["beneficiary"], comment.id,
                body="hijack",
            )
