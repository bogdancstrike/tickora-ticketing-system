# Tickora

Tickora is an operations ticketing platform for teams that need controlled
triage, sector-based ownership, auditable workflow, and real-time visibility.
It is built as a full-stack product, not a demo: Keycloak-backed RBAC,
PostgreSQL-first data modeling, event-driven notifications, SLA tracking,
attachments, audit trails, and an Ant Design operational UI.

**Stack:** Python 3.12 · Flask · QF Framework · SQLAlchemy 2 · PostgreSQL 15 ·
Keycloak · Redis · Kafka · MinIO · Jaeger · React 19 · Ant Design 6 · ECharts.

## What It Does

- Routes tickets through distributor review, sector assignment, operator work,
  beneficiary close/reopen, cancellation, and audit-backed status changes.
- Models hierarchical RBAC with Keycloak groups:
  `/tickora` grants full platform access, while `/tickora/sectors/<code>` grants
  effective chief+member access for one sector.
- Supports public/private comments, file attachments, metadata, priority changes,
  and ticket audit history.
- Sends in-app/SSE notifications to users implied on a ticket while preserving
  private-comment visibility boundaries.
- Provides dashboards for global, distributor, sector, personal, beneficiary,
  SLA, and time-series views.
- Exposes a React UI for ticket queues, review, dashboards, profile access,
  notifications, audit exploration, and operational workflow actions.

## Architecture

```text
React SPA
  └─ Axios + Keycloak token
      └─ Flask/QF API
          ├─ IAM/RBAC: JWT verification, principal hydration, Keycloak groups
          ├─ Ticketing services: workflow, comments, attachments, audit, SLA
          ├─ PostgreSQL: tickets, history, audit, notifications, metadata
          ├─ Redis: JWT cache + notification stream support
          ├─ Kafka: async task and notification handlers
          └─ MinIO: object storage for attachments
```

The backend keeps controllers thin and puts business rules in service modules.
RBAC is enforced server-side; frontend visibility is only an ergonomic layer.

## Quickstart

```bash
# Bring up Postgres, Keycloak, Redis, Kafka, MinIO, and Jaeger
make up

# Install Python dependencies and the local QF wheel
make install

# Provision the Tickora Keycloak realm, clients, roles, and group tree
make keycloak-bootstrap

# Apply database migrations
make migrate

# Seed local users, sectors, memberships, tickets, comments, and metadata
make seed

# Run the API on :5100
make backend

# Run the frontend on :5173
make frontend-install
make frontend
```

Open:

- Frontend: `http://localhost:5173`
- API health: `http://localhost:5100/health`
- Keycloak: `http://localhost:8080`
- Jaeger: `http://localhost:16686`
- MinIO console: `http://localhost:9001`

## Development Users

All seeded users use:

```text
Tickora123!
```

| User | Access model | Use case |
|---|---|---|
| `admin` | `/tickora` | Full platform administrator |
| `bogdan` | `/tickora` | Full platform/super-admin seed user |
| `auditor` | `tickora_auditor` | Read-only global audit/dashboard visibility |
| `distributor` | `tickora_distributor` | Review queue and triage routing |
| `chief.s10` | `/tickora/sectors/s10` | Chief+member access for sector `s10` |
| `member.s10` | `/tickora/sectors/s10/members` | Operator access in sector `s10` |
| `member.s2` | `/tickora/sectors/s2/members` | Operator access in sector `s2` |
| `beneficiary` | `tickora_internal_user` | Internal requester flow |
| `external.user` | `tickora_external_user` | External requester visibility checks |

See [docs/RBAC.md](docs/RBAC.md) for the full authorization model.

## Repository Layout

```text
src/
├── api/             # Thin HTTP controllers, one file per domain
├── core/            # Config, db, logging, errors, tracing, pagination, Redis
├── iam/             # Token verifier, Principal, RBAC, decorators, Keycloak admin
├── tasking/         # Kafka producer/consumer/registry
└── ticketing/       # ORM models and ticketing domain services

frontend/
├── src/api/         # Axios client and typed API functions
├── src/auth/        # Keycloak integration
├── src/components/  # Reusable UI primitives
├── src/pages/       # Tickets, review, dashboards, audit, profile
└── src/stores/      # Session and theme stores

docs/
├── architecture.md
├── implementation_plan.md
├── RBAC.md
├── SECURITY_REVIEW.md
└── TODO.md
```

## Tests

```bash
make test-unit          # RBAC matrix, principal helpers, pagination, state machine
make test-integration   # testcontainers-backed PostgreSQL integration tests
npm --prefix frontend run build
```

Integration tests require Docker and `testcontainers[postgres]`.

## Useful Commands

```bash
make up                 # Start local infrastructure
make down               # Stop local infrastructure
make migrate            # Apply Alembic migrations
make seed               # Seed Keycloak + database data
make worker             # Run Kafka task consumer
make sla-checker        # Run SLA background checker
make frontend           # Start Vite dev server
```

## Project Status

Tickora is in active development. Core ticketing, workflow, comments,
attachments, audit, notifications, dashboards, metadata, and review flows are
implemented. Current work is focused on hierarchical RBAC/profile visibility,
multi-assignment UI polish, admin CRUD, and production hardening.

Live status: [docs/TODO.md](docs/TODO.md)  
Architecture: [docs/architecture.md](docs/architecture.md)  
Security review: [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md)
