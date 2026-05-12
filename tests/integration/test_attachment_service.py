"""Integration tests for `src.ticketing.service.attachment_service`.

Covers the validation paths, RBAC gates, and visibility filtering. Object
storage (MinIO/S3) is mocked at the module boundary — these tests aren't
trying to verify boto3 plumbing, only that the service contracts hold.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.common.errors import PermissionDeniedError, ValidationError
from src.iam.principal import (
    SectorMembership,
    ROLE_ADMIN,
    ROLE_INTERNAL_USER,
)
from src.ticketing.service import attachment_service, comment_service

from tests.integration.conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)


@pytest.fixture(autouse=True)
def stub_object_storage(monkeypatch):
    """Mock MinIO so we can run without a live bucket. Successful presign +
    object-exists are the default; individual tests can override.
    """
    from src.common import object_storage
    monkeypatch.setattr(object_storage, "ensure_bucket", lambda _: None)
    monkeypatch.setattr(
        object_storage, "presigned_put_url",
        lambda bucket, key, **kw: f"https://stub.example/{bucket}/{key}",
    )
    monkeypatch.setattr(
        object_storage, "presigned_get_url",
        lambda bucket, key, **kw: f"https://stub.example/{bucket}/{key}",
    )
    monkeypatch.setattr(object_storage, "object_exists", lambda bucket, key: True)
    monkeypatch.setattr(
        object_storage,
        "object_info",
        lambda bucket, key: {"ContentLength": 200 if "report" in key else 10},
    )


@pytest.fixture
def world(db_session: Session):
    sector = create_sector(db_session, code="s10")

    admin_u = create_user(db_session, "admin")
    member_u = create_user(db_session, "member.s10")
    bystander_u = create_user(db_session, "bystander.s10")
    beneficiary_u = create_user(db_session, "beneficiary")
    outsider_u = create_user(db_session, "outsider")

    beneficiary = create_beneficiary(db_session, beneficiary_u)
    ticket = create_ticket(
        db_session, beneficiary,
        created_by=beneficiary_u, current_sector=sector,
        status="in_progress", assignee=member_u, last_active_assignee=member_u,
    )
    db_session.commit()

    principals = {
        "admin": principal_for(admin_u, roles={ROLE_ADMIN}, has_root_group=True),
        "assignee": principal_for(
            member_u, roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership("s10", "member"),),
        ),
        "bystander": principal_for(
            bystander_u, roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership("s10", "member"),),
        ),
        "beneficiary": principal_for(beneficiary_u, roles={ROLE_INTERNAL_USER}),
        "outsider": principal_for(outsider_u, roles={ROLE_INTERNAL_USER}),
    }

    # Pre-create a public comment to anchor attachments.
    public_comment = comment_service.create(
        db_session, principals["assignee"], ticket.id,
        body="opening update", visibility="public",
    )
    private_comment = comment_service.create(
        db_session, principals["assignee"], ticket.id,
        body="internal note", visibility="private",
    )
    db_session.commit()

    return {
        "ticket": ticket,
        "principals": principals,
        "public_comment": public_comment,
        "private_comment": private_comment,
    }


# ── request_upload_url ──────────────────────────────────────────────────────

class TestRequestUploadUrl:
    def test_assignee_gets_url(self, db_session, world):
        out = attachment_service.request_upload_url(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            file_name="report.pdf", content_type="application/pdf", size_bytes=100,
        )
        assert "upload_url" in out and "storage_key" in out

    def test_outsider_cannot_upload(self, db_session, world):
        # Outsider can't even *see* the ticket → NotFound, not 403.
        from src.common.errors import NotFoundError
        with pytest.raises(NotFoundError):
            attachment_service.request_upload_url(
                db_session, world["principals"]["outsider"], world["ticket"].id,
                file_name="x.pdf", content_type="application/pdf", size_bytes=100,
            )

    def test_zero_size_rejected(self, db_session, world):
        with pytest.raises(ValidationError, match="positive"):
            attachment_service.request_upload_url(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                file_name="x.pdf", content_type=None, size_bytes=0,
            )

    def test_oversized_rejected(self, db_session, world):
        from src.config import Config
        with pytest.raises(ValidationError, match="too large"):
            attachment_service.request_upload_url(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                file_name="x.pdf", content_type=None,
                size_bytes=Config.ATTACHMENT_MAX_SIZE_BYTES + 1,
            )

    def test_filename_sanitised(self, db_session, world):
        out = attachment_service.request_upload_url(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            file_name="../../etc/passwd", content_type=None, size_bytes=10,
        )
        # Path traversal must not appear in the storage_key.
        assert "../" not in out["storage_key"]


# ── register ────────────────────────────────────────────────────────────────

class TestRegister:
    def _upload(self, db, world, name="report.pdf"):
        out = attachment_service.request_upload_url(
            db, world["principals"]["assignee"], world["ticket"].id,
            file_name=name, content_type="application/pdf", size_bytes=200,
        )
        return out["storage_key"]

    def test_register_attaches_to_public_comment(self, db_session, world):
        key = self._upload(db_session, world)
        att = attachment_service.register(
            db_session, world["principals"]["assignee"], world["ticket"].id,
            storage_key=key, file_name="report.pdf",
            size_bytes=200, comment_id=world["public_comment"].id,
        )
        assert att.id is not None
        assert att.comment_id == world["public_comment"].id

    def test_register_rejects_declared_size_mismatch(self, db_session, world, monkeypatch):
        from src.common import object_storage
        monkeypatch.setattr(object_storage, "object_info", lambda b, k: {"ContentLength": 999})
        key = self._upload(db_session, world)

        with pytest.raises(ValidationError, match="size does not match"):
            attachment_service.register(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                storage_key=key, file_name="report.pdf",
                size_bytes=200, comment_id=world["public_comment"].id,
            )

    def test_register_rejects_foreign_storage_key(self, db_session, world):
        with pytest.raises(ValidationError, match="not valid for this ticket"):
            attachment_service.register(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                storage_key="tickets/other-ticket/file.pdf",
                file_name="file.pdf", size_bytes=100,
                comment_id=world["public_comment"].id,
            )

    def test_register_rejects_missing_object(self, db_session, world, monkeypatch):
        from src.common import object_storage
        monkeypatch.setattr(object_storage, "object_info", lambda b, k: None)
        key = self._upload(db_session, world)
        with pytest.raises(ValidationError, match="not found"):
            attachment_service.register(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                storage_key=key, file_name="x.pdf",
                size_bytes=10, comment_id=world["public_comment"].id,
            )

    def test_beneficiary_cannot_attach_to_private_comment(self, db_session, world):
        key = attachment_service.request_upload_url(
            db_session, world["principals"]["beneficiary"], world["ticket"].id,
            file_name="private.pdf", content_type=None, size_bytes=10,
        )["storage_key"]

        with pytest.raises(PermissionDeniedError):
            attachment_service.register(
                db_session, world["principals"]["beneficiary"], world["ticket"].id,
                storage_key=key, file_name="private.pdf",
                size_bytes=10, comment_id=world["private_comment"].id,
            )

    def test_register_rejects_deleted_comment(self, db_session, world):
        world["public_comment"].is_deleted = True
        key = self._upload(db_session, world)

        with pytest.raises(ValidationError, match="invalid comment_id"):
            attachment_service.register(
                db_session, world["principals"]["assignee"], world["ticket"].id,
                storage_key=key, file_name="report.pdf",
                size_bytes=200, comment_id=world["public_comment"].id,
            )

    def test_register_rejects_wrong_ticket_comment(self, db_session, world):
        # Build a SECOND ticket in the same sector (s10) so the assignee
        # can see it, then try to register an attachment whose `comment_id`
        # belongs to the *world* ticket — different ticket, invalid combo.
        from sqlalchemy import select
        from src.ticketing.models import Sector

        s10 = db_session.scalar(select(Sector).where(Sector.code == "s10"))
        u = create_user(db_session, "elsewhere")
        b = create_beneficiary(db_session, u)
        other = create_ticket(db_session, b, created_by=u, current_sector=s10)
        db_session.commit()

        out = attachment_service.request_upload_url(
            db_session, world["principals"]["assignee"], other.id,
            file_name="x.pdf", content_type=None, size_bytes=10,
        )
        with pytest.raises(ValidationError, match="invalid comment_id"):
            attachment_service.register(
                db_session, world["principals"]["assignee"], other.id,
                storage_key=out["storage_key"], file_name="x.pdf",
                size_bytes=10, comment_id=world["public_comment"].id,
            )


# ── list / visibility filtering ─────────────────────────────────────────────

class TestListVisibility:
    def _seed_one_each(self, db, world):
        # Public-comment attachment + private-comment attachment.
        pub_key = attachment_service.request_upload_url(
            db, world["principals"]["assignee"], world["ticket"].id,
            file_name="public.pdf", content_type=None, size_bytes=10,
        )["storage_key"]
        attachment_service.register(
            db, world["principals"]["assignee"], world["ticket"].id,
            storage_key=pub_key, file_name="public.pdf",
            size_bytes=10, comment_id=world["public_comment"].id,
        )
        priv_key = attachment_service.request_upload_url(
            db, world["principals"]["assignee"], world["ticket"].id,
            file_name="private.pdf", content_type=None, size_bytes=10,
        )["storage_key"]
        attachment_service.register(
            db, world["principals"]["assignee"], world["ticket"].id,
            storage_key=priv_key, file_name="private.pdf",
            size_bytes=10, comment_id=world["private_comment"].id,
        )
        db.commit()

    def test_assignee_sees_both(self, db_session, world):
        self._seed_one_each(db_session, world)
        atts = attachment_service.list_(
            db_session, world["principals"]["assignee"], world["ticket"].id,
        )
        names = {a.file_name for a in atts}
        assert "public.pdf" in names
        assert "private.pdf" in names

    def test_beneficiary_sees_only_public(self, db_session, world):
        self._seed_one_each(db_session, world)
        atts = attachment_service.list_(
            db_session, world["principals"]["beneficiary"], world["ticket"].id,
        )
        names = {a.file_name for a in atts}
        assert names == {"public.pdf"}
