from types import SimpleNamespace
from unittest.mock import MagicMock

from src.audit import events
from src.iam.principal import Principal
from src.ticketing.service import ticket_service


def _principal() -> Principal:
    return Principal(
        user_id="u-admin",
        keycloak_subject="kc-admin",
        username="admin",
        email="admin@example.test",
        user_type="internal",
        global_roles=frozenset({"tickora_admin"}),
    )


def test_delete_records_ticket_deleted_audit_event(monkeypatch):
    ticket = SimpleNamespace(id="ticket-1", is_deleted=False)
    db = MagicMock()
    recorded = {}

    monkeypatch.setattr(ticket_service, "get", lambda _db, _principal, _ticket_id: ticket)
    monkeypatch.setattr(ticket_service.rbac, "can_delete_ticket", lambda _principal, _ticket: True)

    def fake_record(db_arg, **kwargs):
        recorded.update(kwargs)
        recorded["db"] = db_arg

    monkeypatch.setattr(ticket_service.audit_service, "record", fake_record)

    ticket_service.delete(db, _principal(), ticket.id)

    assert ticket.is_deleted is True
    db.flush.assert_called_once()
    assert recorded["db"] is db
    assert recorded["action"] == events.TICKET_DELETED
    assert recorded["entity_type"] == "ticket"
    assert recorded["entity_id"] == ticket.id
    assert recorded["ticket_id"] == ticket.id
    assert recorded["old_value"] == {"is_deleted": False}
    assert recorded["new_value"] == {"is_deleted": True}
