"""HTTP-level role × endpoint matrix.

The unit-level matrix in `tests/unit/test_role_matrix.py` exercises the
predicate functions in `iam.rbac`. This integration variant goes one layer
out: it calls the controller functions in `src/api/*` with a Flask request
context and a fully-shaped `Principal`, walking the same denial paths a
real wire request would take. We don't boot QF — that's heavy — but we go
through the decorators (`require_authenticated`), through the service
layer, and through the database.

If a controller forgets to enforce RBAC (e.g. a new endpoint copy-paste
that omits the predicate check), this matrix catches it without needing
the unit suite to know about every new endpoint.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import pytest
from flask import Flask
from sqlalchemy.orm import Session

from src.iam.principal import (
    Principal,
    SectorMembership,
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DISTRIBUTOR,
    ROLE_EXTERNAL_USER,
    ROLE_INTERNAL_USER,
)
from tests.integration.conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)


# ── Fake "wire" harness ─────────────────────────────────────────────────────
#
# We patch `src.iam.decorators._build_principal` so our test principal is
# injected verbatim — that way the decorator chain runs end-to-end (audit
# correlation, span enrichment, error mapping) without needing a real JWT.

@contextmanager
def _as_principal(monkeypatch, principal: Principal):
    from src.iam import decorators
    monkeypatch.setattr(decorators, "_build_principal", lambda: principal)
    yield


@contextmanager
def _patched_db(monkeypatch, db):
    from src.core import db as db_module

    @contextmanager
    def fake_get_db():
        try:
            yield db
            db.flush()
        except Exception:
            db.rollback()
            raise

    # Patch every module that imports get_db at module level.
    for mod_path in [
        "src.api.tickets",
        "src.api.review",
        "src.api.admin",
    ]:
        try:
            module = __import__(mod_path, fromlist=["get_db"])
            monkeypatch.setattr(module, "get_db", fake_get_db, raising=False)
        except ImportError:
            continue
    monkeypatch.setattr(db_module, "get_db", fake_get_db)
    yield


@pytest.fixture
def app():
    return Flask(__name__)


# ── Persona builder mirroring docs/RBAC.md ──────────────────────────────────

def _build_personas(db: Session) -> dict[str, Principal]:
    s10 = create_sector(db, code="s10")
    s2 = create_sector(db, code="s2")

    admin_u = create_user(db, "admin")
    auditor_u = create_user(db, "auditor")
    distributor_u = create_user(db, "distributor")
    chief_u = create_user(db, "chief.s10")
    member_u = create_user(db, "member.s10")
    member2_u = create_user(db, "member.s2")
    beneficiary_u = create_user(db, "beneficiary")
    external_u = create_user(db, "external.user", user_type="external")

    return {
        "admin": principal_for(admin_u, roles={ROLE_ADMIN}, has_root_group=True),
        "auditor": principal_for(auditor_u, roles={ROLE_AUDITOR, ROLE_INTERNAL_USER}),
        "distributor": principal_for(distributor_u, roles={ROLE_DISTRIBUTOR, ROLE_INTERNAL_USER}),
        "chief_s10": principal_for(
            chief_u,
            roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership(s10.code, "chief"),),
        ),
        "member_s10": principal_for(
            member_u,
            roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership(s10.code, "member"),),
        ),
        "member_s2": principal_for(
            member2_u,
            roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership(s2.code, "member"),),
        ),
        "beneficiary": principal_for(beneficiary_u, roles={ROLE_INTERNAL_USER}),
        "external_user": principal_for(external_u, roles={ROLE_EXTERNAL_USER}),
    }


# ── Helpers to invoke controllers in a Flask context ───────────────────────

def _call(handler, app, principal, *, monkeypatch, db, json=None, view_args=None):
    with _patched_db(monkeypatch, db), _as_principal(monkeypatch, principal):
        with app.test_request_context("/", json=json or {}):
            from flask import request as flask_request
            if view_args:
                flask_request.view_args = view_args
            return handler(None, None, flask_request)


def _status(result) -> int:
    if isinstance(result, tuple) and len(result) >= 2:
        return int(result[1])
    return 0  # framework's default — should never happen for our handlers


# ── The matrix itself ──────────────────────────────────────────────────────

@dataclass
class Case:
    persona: str
    expected_status: int   # canonical happy path
    # Some endpoints should specifically reject with a particular status.
    deny_status: int | None = None


class TestAdminOverviewMatrix:
    """`/api/admin/overview` requires admin."""

    @pytest.mark.parametrize("persona,expected_status", [
        ("admin", 200),
        ("auditor", 403),
        ("distributor", 403),
        ("chief_s10", 403),
        ("member_s10", 403),
        ("member_s2", 403),
        ("beneficiary", 403),
        ("external_user", 403),
    ])
    def test_admin_overview(self, app, db_session, monkeypatch, persona, expected_status):
        from src.api.admin import overview as overview_handler

        personas = _build_personas(db_session)
        result = _call(
            overview_handler,
            app,
            personas[persona],
            monkeypatch=monkeypatch,
            db=db_session,
        )
        assert _status(result) == expected_status


class TestAdminListUsersMatrix:
    """`/api/admin/users` is admin-only."""

    @pytest.mark.parametrize("persona,expected_status", [
        ("admin", 200),
        ("auditor", 403),
        ("distributor", 403),
        ("chief_s10", 403),
        ("member_s10", 403),
        ("member_s2", 403),
        ("beneficiary", 403),
        ("external_user", 403),
    ])
    def test_admin_list_users(self, app, db_session, monkeypatch, persona, expected_status):
        from src.api.admin import list_users
        personas = _build_personas(db_session)
        result = _call(
            list_users,
            app,
            personas[persona],
            monkeypatch=monkeypatch,
            db=db_session,
        )
        assert _status(result) == expected_status


class TestTicketCreateMatrix:
    """Authenticated users in any role may create a ticket — only the
    unauthenticated case is rejected, and that path is tested elsewhere
    (decorators). This case ensures every persona has the *capability*."""

    @pytest.mark.parametrize("persona", list({
        "admin", "auditor", "distributor", "chief_s10",
        "member_s10", "member_s2", "beneficiary", "external_user",
    }))
    def test_ticket_create_capability(self, app, db_session, monkeypatch, persona):
        from src.api.tickets import create
        personas = _build_personas(db_session)
        result = _call(
            create,
            app,
            personas[persona],
            monkeypatch=monkeypatch,
            db=db_session,
            json={
                "title": "test",
                "txt": "this is a long enough description to pass validation",
                "beneficiary_type": "external" if persona == "external_user" else "internal",
                "requester_email": "x@y.test",
            },
        )
        # 201 created OR 422 validation if the persona's profile is incomplete;
        # what we want to *prove* is that no persona gets a 401/403 here.
        assert _status(result) not in (401, 403)


class TestTicketListMatrix:
    """`/api/tickets` is open to all authenticated users — visibility is
    enforced inside the SQL filter, not at the controller. This test
    confirms the controller doesn't slap a role gate on the listing
    endpoint by mistake."""

    @pytest.mark.parametrize("persona", list({
        "admin", "auditor", "distributor", "chief_s10",
        "member_s10", "member_s2", "beneficiary", "external_user",
    }))
    def test_ticket_list_open_to_all(self, app, db_session, monkeypatch, persona):
        from src.api.tickets import list_tickets
        personas = _build_personas(db_session)
        result = _call(
            list_tickets,
            app,
            personas[persona],
            monkeypatch=monkeypatch,
            db=db_session,
        )
        assert _status(result) == 200


class TestReviewMatrix:
    """`/api/tickets/<id>/review` is admin + distributor only."""

    @pytest.mark.parametrize("persona,expected_status", [
        ("admin", 200),
        ("auditor", 403),
        ("distributor", 200),
        ("chief_s10", 403),
        ("member_s10", 403),
        ("member_s2", 403),
        ("beneficiary", 403),
        ("external_user", 403),
    ])
    def test_review_endpoint(self, app, db_session, monkeypatch, persona, expected_status):
        # Seed a pending ticket so review_service has something to act on.
        personas = _build_personas(db_session)
        beneficiary_u = db_session.query.__self__  # noqa
        from src.iam.models import User
        beneficiary_user = db_session.query(User).filter_by(username="beneficiary").one()
        beneficiary = create_beneficiary(db_session, beneficiary_user)
        ticket = create_ticket(
            db_session, beneficiary, created_by=beneficiary_user, status="pending",
        )
        db_session.commit()

        from src.api.review import review_ticket
        result = _call(
            review_ticket,
            app,
            personas[persona],
            monkeypatch=monkeypatch,
            db=db_session,
            view_args={"ticket_id": ticket.id},
            json={},
        )
        assert _status(result) == expected_status
