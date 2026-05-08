from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN, SectorMembership
from src.ticketing.service import attachment_service, audit_service, comment_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def _ticket_context(db_session: Session):
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    sector = create_sector(db_session, "s10")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_user,
        current_sector=sector,
        status="in_progress",
        assignee=member_user,
    )
    beneficiary_principal = principal_for(beneficiary_user)
    member_principal = principal_for(member_user, sectors=(SectorMembership("s10", "member"),))
    return ticket, beneficiary_principal, member_principal


def test_private_comments_are_hidden_from_beneficiary(db_session: Session):
    ticket, beneficiary, member = _ticket_context(db_session)

    comment_service.create(db_session, member, ticket.id, body="public update", visibility="public")
    comment_service.create(db_session, member, ticket.id, body="private sector note", visibility="private")
    db_session.commit()

    beneficiary_comments = comment_service.list_(db_session, beneficiary, ticket.id)
    member_comments = comment_service.list_(db_session, member, ticket.id)

    assert [c.body for c in beneficiary_comments] == ["public update"]
    assert {c.body for c in member_comments} == {"public update", "private sector note"}


def test_attachment_visibility_and_audit(monkeypatch, db_session: Session):
    ticket, beneficiary, member = _ticket_context(db_session)
    monkeypatch.setattr(attachment_service.object_storage, "object_exists", lambda bucket, key: True)

    private_attachment = attachment_service.register(
        db_session,
        member,
        ticket.id,
        storage_key=f"tickets/{ticket.id}/abc/private.txt",
        file_name="private.txt",
        size_bytes=100,
        content_type="text/plain",
        visibility="private",
    )
    public_attachment = attachment_service.register(
        db_session,
        member,
        ticket.id,
        storage_key=f"tickets/{ticket.id}/abc/public.txt",
        file_name="public.txt",
        size_bytes=100,
        content_type="text/plain",
        visibility="public",
    )
    db_session.commit()

    beneficiary_attachments = attachment_service.list_(db_session, beneficiary, ticket.id)
    member_attachments = attachment_service.list_(db_session, member, ticket.id)

    assert [a.id for a in beneficiary_attachments] == [public_attachment.id]
    assert {a.id for a in member_attachments} == {private_attachment.id, public_attachment.id}


def test_global_audit_requires_admin(db_session: Session):
    ticket, beneficiary, member = _ticket_context(db_session)
    comment_service.create(db_session, member, ticket.id, body="audit me", visibility="public")
    admin_user = create_user(db_session, "admin")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})
    db_session.commit()

    events = audit_service.list_(db_session, admin, ticket_id=ticket.id)

    assert any(e.action == "COMMENT_CREATED" for e in events)
