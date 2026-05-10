"""Ticketing package init.

Wires the ticket resolver into `src.audit` so `get_for_ticket` can run
sector/visibility checks against a real ticket. The audit module
intentionally has no static dependency on ticketing — registering it here
keeps that boundary clean.

We use a deferred lambda to avoid an eager import of `ticket_service`
(and the SQLAlchemy ORM mappings it pulls in) at audit-module load time.
"""

from src.audit.service import set_ticket_resolver as _set_ticket_resolver


def _ticket_resolver(db, principal, ticket_id):
    # Lazy import — `ticket_service` itself depends on `audit.service`,
    # so importing it eagerly would create a cycle at package init.
    from src.ticketing.service import ticket_service
    return ticket_service.get(db, principal, ticket_id)


_set_ticket_resolver(_ticket_resolver)
