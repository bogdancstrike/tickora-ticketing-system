"""Audit module — immutable ledger for actor / action / entity records.

Exposes:
  * `service.record(...)` — single entry point for writing audit rows.
  * `service.list_global / list_for_ticket / list_for_user / list_for_sector`
    — RBAC-aware reads.
  * `events.*` — typed event constants (`TICKET_CREATED`, `ACCESS_DENIED`, …).

Use this module directly in new code. For back-compat, the old paths
(`src.ticketing.service.audit_service`, `src.ticketing.events`) re-export
from here.
"""

from src.audit import events, service  # noqa: F401
