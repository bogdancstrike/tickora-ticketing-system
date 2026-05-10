"""Back-compat shim — audit moved to `src.audit.service`.

This re-export keeps existing
`from src.ticketing.service import audit_service` and
`from src.ticketing.service.audit_service import record` imports working
after the 2026-05-10 module split. New code should import from
`src.audit.service` (or `from src.audit import service as audit_service`).
"""

from src.audit.service import (  # noqa: F401
    get_for_ticket,
    get_for_user,
    list_,
    record,
)
