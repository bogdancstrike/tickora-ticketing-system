# `audit/` as a standalone microservice

Audit ships as a self-sufficient module: copy `src/audit/`, plus the
support packages it imports, and you have a working "central audit log"
service.

## Dependency boundary

`audit/` imports only:

| Symbol                     | Source              | Required? |
|----------------------------|---------------------|-----------|
| `Base`                     | `src.core.db`       | Yes — `AuditEvent` ORM. |
| `get_correlation_id()`     | `src.core.correlation` | Yes — every audit row carries the originating correlation id. |
| `NotFoundError`, `PermissionDeniedError` | `src.core.errors` | Yes. |
| `rbac` predicates          | `src.iam.rbac`      | Yes — `can_view_global_audit`, `can_view_sector_audit`, `can_view_ticket`. |
| `Principal`                | `src.iam.principal` | Yes — typed actor. |
| `request_metadata()`       | `src.common.request_metadata` | Yes — fills `request_ip` / `user_agent` on every row. |

Specifically: **no static import from `ticketing` or `tasking`**. Per-
ticket visibility (`get_for_ticket`) used to call `ticket_service.get`
directly; that's now an injectable resolver — see "Wiring" below.

## Extraction recipe

Copy these files into the new project:

```
src/
├── config.py                     # bring or replace
├── core/                         # required
│   ├── __init__.py
│   ├── correlation.py
│   ├── db.py
│   ├── errors.py
│   ├── redis_client.py           # only if you keep the request-metadata helper
│   └── tracing.py
├── common/                       # required (request_metadata)
│   ├── __init__.py
│   └── request_metadata.py
├── iam/                          # required (Principal + rbac)
│   ├── __init__.py
│   ├── decorators.py             # if you expose HTTP endpoints
│   ├── keycloak_admin.py         # optional — only if you mirror groups
│   ├── models.py
│   ├── principal.py
│   ├── rbac.py
│   ├── service.py
│   └── token_verifier.py
└── audit/
    ├── __init__.py
    ├── events.py
    ├── models.py
    └── service.py
```

Plus the migrations that own the tables you keep:

* `0001_users.py`              — required (`actor_user_id` FK).
* `0002_ticketing.py`          — **only if** you keep the `tickets.id` FK.
  Otherwise drop the `audit_events.ticket_id` FK and bring just a
  custom audit-only migration. See "FK on tickets" below.
* `0007_phase8_hardening_indexes.py` — optional (audit recency index).

Python deps:

* `flask`, `flask-restx`         (HTTP surface)
* `sqlalchemy`, `psycopg2-binary`, `alembic`
* `python-jose[cryptography]`, `python-keycloak`   (token verification)
* `redis`                        (transitively used by IAM cache)

## Wiring

```python
# main.py — host startup
from src.audit.service import set_ticket_resolver

# Option A: full resolver (the modulith default).
def my_resolver(db, principal, ticket_id):
    from somewhere import fetch_ticket
    return fetch_ticket(db, principal, ticket_id)
set_ticket_resolver(my_resolver)

# Option B: leave it unset.
# `GET /api/tickets/<id>/audit` then refuses unless the caller is a
# global auditor. Sector auditors lose ticket-scoped reads — usually
# fine for a centralised log service.
```

API surface (in `src/api/audit.py` — copy alongside):

```
GET /api/audit                       — list (admin / auditor)
GET /api/tickets/<id>/audit          — per-ticket timeline
GET /api/users/<id>/audit            — actor-scoped
```

Endpoint registration is in `maps/endpoint.json`; copy the relevant
entries when carving the new service.

## FK on `tickets`

`audit_events.ticket_id` references `tickets.id`. Two stances:

* **Hard FK** — both tables in the same database. Modulith default.
  Audit rows can't refer to non-existent tickets.
* **Soft FK** — audit lives in its own database. Drop the constraint:

  ```python
  # in your audit-microservice migration
  op.drop_constraint("audit_events_ticket_id_fkey", "audit_events", type_="foreignkey")
  ```

  `ticket_id` becomes an opaque identifier. Audit rows survive
  upstream-ticket deletion, which is usually what you want for an
  immutable ledger anyway.

## What a microservice does NOT need from the modulith

* `src.ticketing.*`              — no static reference.
* `src.tasking.*`                — audit doesn't publish or consume tasks.
* `src.common.cache`, `rate_limiter`, `session_tracker`, `object_storage`,
  `pagination`, `spans` — none are imported by audit.
