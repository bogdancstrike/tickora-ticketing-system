# Tickora

Ticketing, tasking, distribution, audit, RBAC, and dashboarding platform.

**Stack:** Python 3.12 · Flask · QF Framework · SQLAlchemy 2 · PostgreSQL 15 · Keycloak · React 19 + Ant Design 6.

See `docs/architecture.md` for the system design and `docs/implementation_plan.md` for the phased plan. Live progress lives in `docs/TODO.md`.

---

## Quickstart

```bash
# Bring up the dev infra (Postgres, Keycloak, Redis, Kafka, MinIO, Jaeger)
make up

# Install Python deps + the local QF wheel
make install

# Provision the Keycloak realm (one-time, after `make up`)
make keycloak-bootstrap

# Apply DB migrations
make migrate

# Run the API on :5100
make backend

# Run the frontend on :5173
make frontend-install
make frontend
```

## Layout

```
src/
├── core/            # config, db, logging, errors, correlation, tracing, pagination
├── iam/             # token verifier, principal, RBAC, decorators, Keycloak admin
├── ticketing/       # models + service (tickets, comments, attachments, audit, workflow)
├── tasking/         # Kafka producer/consumer/registry (Phase 5)
└── api/             # thin HTTP controllers (one file per domain)
```

## Tests

```bash
make test-unit          # fast, deps-light unit tests (RBAC matrix, state machine, ...)
make test-integration   # testcontainers Postgres
```
