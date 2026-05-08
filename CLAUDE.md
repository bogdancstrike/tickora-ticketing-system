# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Commands

```bash
make install            # pip install requirements + local QF wheel
make backend            # python main.py  (port 5100)
make worker             # python worker.py  (Phase 5+)
make sla-checker        # python sla_checker.py  (Phase 5+)

make up / down / logs   # docker compose dev stack
make infra              # postgres + redis + keycloak only

make migrate            # alembic upgrade head
make migrate-revision m="description"
make seed
make keycloak-bootstrap

make frontend-install / frontend / frontend-build

make test               # all tests
make test-unit
make test-integration
make lint               # py_compile syntax check
```

## Architecture (modulith)

```
src/
├── core/        # cross-cutting: Config, db (engine/Base/get_db), JSON logger,
│                #  correlation_id contextvars, errors, pagination, tracing,
│                #  redis_client
├── iam/         # principal, token_verifier (JWKS+Redis cache), service
│                #  (user upsert, principal hydration), decorators
│                #  (@require_authenticated, @require_role), rbac (pure
│                #  predicates, single source of truth), keycloak_admin
├── ticketing/   # models (BRD §16 ORM), state_machine (transition table),
│                #  events (audit constants), service/{ticket,beneficiary,
│                #  workflow,audit}_service, schemas (Pydantic in),
│                #  serializers (permission-aware out)
├── tasking/     # producer/consumer/registry (Phase 5)
└── api/         # thin handlers, QF signature
                 #  handler(app, operation, request, **kwargs) → (body, status)
```

All endpoints declared in `maps/endpoint.json`. URL prefix `/tickora/`.

## Key patterns

- **`get_db()` context manager** — auto-commit on success, rollback on raise.
- **Atomic UPDATE for workflow transitions** — `workflow_service.assign_to_me`
  guards concurrency by encoding the precondition in the WHERE clause and
  raising `ConcurrencyConflictError` on `rowcount == 0`.
- **RBAC predicates are pure** — `iam.rbac.*` take Principal + entity, return bool.
  Never reach into the DB. Tested line-by-line against the BRD §9.4 matrix.
- **Permission-aware serializers** — `ticketing/serializers.py` strips fields per
  Principal, so a controller that forgets a check still doesn't leak.
- **Audit always in the same transaction** — `audit_service.record(db, ...)` uses
  the caller's session. If the txn rolls back, the audit row goes with it.
- **Lazy package `__init__.py`** — submodules import their own deps. Pulling
  `from src.iam import Principal` won't drag jose/keycloak into a unit test.

## DB

- SQLAlchemy 2.x typed mappings (`Mapped[...]`, `mapped_column`).
- Alembic in `migrations/`. Schema mirrors BRD §16 exactly, indexes per §17.
- Postgres-only features used: `INET`, `JSONB`, `UUID`, partial indexes,
  `tsvector` + GIN, `CREATE SEQUENCE IF NOT EXISTS` for ticket-code generation.

## Tests

- Unit (`tests/unit/`): no DB, no network. Run on every save (`pytest -q`).
- Integration (`tests/integration/`): testcontainers Postgres, Phase 2+.
- Acceptance (`tests/integration/acceptance/`): pytest-bdd for BRD §24 scenarios.

## Frontend

React 19 + AntD 6 + Vite + TanStack Query + Zustand + keycloak-js (PKCE).
`src/main.tsx` wraps the app in `<ReactKeycloakProvider>`. The axios client
in `src/api/client.ts` uses a token provider hook so refreshes propagate.
Theme via `themeStore`, session/role state via `sessionStore`, gating via
`<RequireRole>`.
