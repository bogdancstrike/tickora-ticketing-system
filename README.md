# Tickora

Tickora is a full-stack operational ticketing system for controlled intake,
sector routing, assignee-owned workflow, comments, attachments, audit, realtime
notifications, custom dashboards, and Keycloak-backed RBAC.

The current application is an active-development modulith. It has useful
production-oriented structure, but it is not production-hardened yet. Read
[docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) before treating it as a
security boundary.

## Current Stack

Backend:

- Python 3.12, Flask 3, Flask-RESTX, gevent, QF Framework
- SQLAlchemy 2, Alembic, PostgreSQL 15
- Keycloak 26 for OIDC, JWTs, realm roles, and group hierarchy
- Redis 7 for cache, rate-limit windows, presence keys, SSE tickets, and SSE pub/sub
- Kafka 7.6 for task delivery when inline task mode is disabled
- MinIO/S3 for attachment object storage
- OpenTelemetry/Jaeger dependencies and correlation IDs

Frontend:

- React 19, TypeScript 5.9, Vite 8
- Ant Design 6 and `@ant-design/icons`
- TanStack Query, Axios, Zustand
- ECharts, D3, `react-grid-layout`
- Keycloak JS, i18next, React Router 7

## What Is Implemented

- Ticket creation, list, detail, update, metadata, watchers, links, and audit history.
- Workflow actions for sector assignment, user assignment, self-assignment,
  status changes, priority changes, reopen, cancel, done, and unassign flows.
- Distributor review queue and review endpoint.
- Public and private comments with edit/delete windows.
- Attachment upload registration and signed download redirects through MinIO/S3.
- Endorsement requests ("avizare") with claim, approve, reject, and inbox flows.
- Notifications table plus Redis/SSE delivery, unread counts, mark-read, and stream tickets.
- Admin endpoints for users, sectors, group hierarchy, metadata keys,
  widget definitions, dashboard settings, task inspection, and overview data.
- Custom dashboards with owner-only dashboards and widget catalog role filtering.
- Monitor endpoints for overview, sector, personal, beneficiary, workflow,
  workload, and bottleneck views.
- Snippets/procedures with audience scoping.
- Three unauthenticated health probes and 108 authenticated API method
  registrations in `maps/endpoint.json`.

What is not currently implemented:

- SLA tracking. The migration `20260510_remove_sla_concept.py` removes the
  SLA tables/columns. The `Makefile` still contains a stale `sla-checker`
  target pointing at a removed `sla_checker.py`; do not use it.
- A Prometheus `/metrics` endpoint. Dependencies exist, but the exposed route
  and counters are not wired.
- Real antivirus scanning for attachments. The current scanner marks objects
  clean immediately.
- Real SMTP delivery. Email notification code is a stub.
- Common Criteria certification. `docs/CC.md` is an EAL4-style gap analysis,
  not a certificate or evaluated Security Target.

## Architecture

```text
React SPA
  -> Keycloak PKCE login
  -> Axios bearer token calls
  -> Flask/QF API
       -> IAM: JWT verification, Principal hydration, Keycloak admin calls
       -> RBAC: pure predicate checks plus service-level SQL filters
       -> Ticketing: workflow, comments, attachments, watchers, links, endorsements
       -> Audit: append-only audit rows in the caller's transaction
       -> Tasking: inline dev callbacks or Kafka-backed worker tasks
       -> PostgreSQL: canonical relational state
       -> Redis: cache, rate limiting, presence, SSE ticket exchange, pub/sub
       -> MinIO/S3: attachment bytes
```

Controllers in `src/api/` are intentionally thin. Most behavior lives in
service modules under `src/ticketing/service`, `src/iam`, `src/audit`, and
`src/tasking`. Frontend route guards and hidden buttons are ergonomics only;
the backend is the authorization source of truth.

See [docs/architecture.md](docs/architecture.md) for the detailed module and
data-flow description.

## Quickstart

```bash
# Bring up local infrastructure: Postgres, Keycloak, Redis, Kafka, MinIO, Jaeger.
make up

# Install Python dependencies and the local QF wheel.
make install

# Provision the Tickora Keycloak realm, clients, roles, and group tree.
make keycloak-bootstrap

# Apply Alembic migrations.
make migrate

# Seed local users, sectors, memberships, tickets, comments, metadata, widgets.
make seed

# Run the API on :5100.
make backend

# Run the frontend on :5173.
make frontend-install
make frontend
```

Useful local URLs:

- Frontend: `http://localhost:5173`
- API health: `http://localhost:5100/health`
- API liveness: `http://localhost:5100/liveness`
- API readiness: `http://localhost:5100/readiness`
- Keycloak: `http://localhost:8080`
- Redis Insight: `http://localhost:5540`
- Kafka UI: `http://localhost:8082`
- MinIO console: `http://localhost:9001`
- Jaeger: `http://localhost:16686`

## Development Users

Seed users use this password:

```text
Tickora123!
```

| User | Current access model | Primary use |
|---|---|---|
| `admin` | `/tickora`, `tickora_admin` | Platform administrator. |
| `bogdan` | `/tickora`, `tickora_admin` | Seed super-admin subject in the default config. |
| `auditor` | `tickora_auditor` | Global read-only audit and oversight. |
| `distributor` | `tickora_distributor` | Intake review and routing. |
| `chief.s10` | `/tickora/sectors/s10` | Sector chief for `s10`; the current parser treats the bare sector group as chief. |
| `member.s10` | `/tickora/sectors/s10/member` | Sector operator for `s10`. |
| `member.s2` | `/tickora/sectors/s2/member` | Sector operator for `s2`. |
| `beneficiary` | `tickora_internal_user` | Internal requester/beneficiary flow. |
| `external.user` | `tickora_external_user` | External requester flow and email-matched ticket visibility. |
| `avizator` | `tickora_avizator` | Endorsement reviewer inbox. |

Important RBAC details:

- `/tickora` implies platform admin behavior and root-group admin access.
- `tickora_admin` is a realm role; some admin endpoints additionally require
  the `/tickora` root group rather than only the role.
- Sector membership is derived from Keycloak groups, not deprecated
  `tickora_sector_member` or `tickora_sector_chief` roles.
- The current code parses `/tickora/sectors/<code>` as chief access for that
  sector. Child paths `/member`, `/members`, `/chief`, and `/chiefs` are also
  accepted.
- Local `users.is_active = false` is not enough to block login if Keycloak still
  issues tokens. Disable users in Keycloak as well.

See [docs/RBAC.md](docs/RBAC.md) for the detailed authorization matrix and
known authorization defects.

## Repository Layout

```text
src/
|-- api/             # QF/Flask handlers, one file per API domain
|-- audit/           # Audit models, constants, write/list helpers
|-- common/          # Cache, rate limiter, object storage, request metadata
|-- core/            # Config, DB session, errors, tracing, correlation
|-- iam/             # JWT verification, Principal hydration, RBAC, Keycloak admin
|-- tasking/         # Task lifecycle, producer, consumer, registry
`-- ticketing/       # ORM models, serializers, and domain services

frontend/
|-- src/api/         # Axios client and typed endpoint wrappers
|-- src/auth/        # Keycloak integration and session bootstrap
|-- src/components/  # Shared UI components
|-- src/pages/       # Tickets, review, dashboard, monitor, admin, audit, profile
|-- src/routes/      # Route guards and app route registration
`-- src/stores/      # Zustand stores

docs/
|-- architecture.md
|-- CC.md
|-- RBAC.md
|-- SECURITY_REVIEW.md
|-- TODO.md
`-- brd.md
```

## Tests And Checks

```bash
make lint
make test-unit
make test-integration
make test-e2e
npm --prefix frontend run build
```

Integration tests use `testcontainers` and require Docker. Some tests are
behind the current implementation and should be treated as additional evidence
to review, not as proof that every role/endpoint pair is covered.

## Useful Commands

```bash
make up                 # Start all local infrastructure
make infra              # Start only Postgres, Redis, Keycloak
make down               # Stop local infrastructure
make logs               # Follow docker compose logs
make install            # Create .venv and install backend deps
make migrate            # Apply Alembic migrations
make seed               # Seed development data
make backend            # Run API
make worker             # Run Kafka task consumer
make frontend-install   # npm install in frontend/
make frontend           # Run Vite dev server
make frontend-build     # Type-check and build the frontend
```

Do not run `make sla-checker` unless the stale Makefile target is fixed first.
The referenced `sla_checker.py` no longer exists.

## Security Status

Tickora has meaningful security structure: Keycloak JWT verification,
server-side RBAC predicates, SQL visibility filters for ticket lists, audit
records, MinIO signed URLs, trusted-proxy request metadata, and Redis-backed
rate limiting on selected write paths.

It also has security bugs and hardening gaps that must be fixed before a
production deployment. The most important current issues are documented in
[docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md), including sector-chief role
escalation risk, ticket audit leakage to ordinary ticket viewers, workflow
state bypasses, attachment validation gaps, dashboard widget ownership gaps,
and notification/SSE edge cases.

## Project Status

Core ticketing, workflow, comments, attachments, audit, notifications,
dashboards, snippets, endorsements, and monitor views are implemented. Current
work should prioritize authorization fixes, workflow invariants, attachment
validation, task consistency, test coverage, and production hardening.

- Architecture: [docs/architecture.md](docs/architecture.md)
- RBAC: [docs/RBAC.md](docs/RBAC.md)
- Security review: [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md)
- Common Criteria EAL4 gap analysis: [docs/CC.md](docs/CC.md)
- Backlog: [docs/TODO.md](docs/TODO.md)
