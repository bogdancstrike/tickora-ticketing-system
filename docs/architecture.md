# Tickora Architecture

_Last refreshed: 2026-05-12. Current branch snapshot._

Tickora is a Python/React modulith for operational ticketing. The backend is
one deployable application with explicit module boundaries. The frontend is a
React SPA that authenticates through Keycloak and calls the API with bearer
tokens.

This document describes what is implemented now. It avoids aspirational claims:
there is no active SLA subsystem, no `/metrics` route, no audit partitioning,
and Kafka task publication is not yet transaction-safe.

## 1. System Topology

```text
Browser
  React 19 + Ant Design 6 + Keycloak JS
      |
      | Bearer JWT, JSON API, SSE stream ticket exchange
      v
Flask/QF API, Python 3.12, gevent
      |
      +-- PostgreSQL 15: tickets, users, audit, tasks, dashboards, notifications
      +-- Keycloak 26: OIDC, realm roles, groups, admin REST
      +-- Redis 7: caches, presence, rate limits, SSE tickets, SSE pub/sub
      +-- Kafka 7.6: task envelopes when inline task mode is disabled
      +-- MinIO/S3: attachment object storage
      +-- Jaeger/OpenTelemetry deps: tracing dependencies and local collector
```

Local `docker-compose.yml` starts Postgres, Keycloak with its own Postgres,
Redis, Redis Insight, Kafka, Kafka UI, MinIO, and Jaeger.

The application image can run as:

- API: `python main.py`
- worker: `ROLE=worker python worker.py`

The `Makefile` still contains `ROLE=sla_checker python sla_checker.py`, but
`sla_checker.py` no longer exists. SLA schema was removed by
`20260510_remove_sla_concept.py`.

## 2. Runtime Stack

Backend:

- Python 3.12
- Flask 3, Flask-RESTX, gevent, psycogreen
- QF Framework local wheel `dist/qf-1.0.2-py3-none-any.whl`
- SQLAlchemy 2, Alembic, psycopg2
- Redis client, Kafka client, boto3
- python-jose, python-keycloak
- Pydantic 2
- OpenTelemetry packages and `prometheus-client` dependency

Frontend:

- React 19.2, React DOM 19.2
- TypeScript 5.9, Vite 8
- Ant Design 6.3, `@ant-design/icons`
- Axios, TanStack Query 5, Zustand
- React Router 7
- Keycloak JS 26
- ECharts, D3, `react-grid-layout`
- i18next, React i18next

## 3. Module Boundaries

```text
src/
  core/       infrastructure primitives
  common/     reusable infrastructure helpers
  iam/        identity, Keycloak, Principal, RBAC
  audit/      audit events and audit query surface
  tasking/    task lifecycle, producer, consumer, registry
  ticketing/  business domain models and services
  api/        HTTP composition layer
```

The intended dependency direction:

- `core` should not import application modules.
- `common` builds on `core`.
- `iam` builds on `core` and `common`.
- `audit` builds on `core`, `common`, and `iam`.
- `tasking` should stay infrastructure-first and load handlers by registry.
- `ticketing` is the business domain and can depend on the lower modules.
- `api` is the composition root and can call all service modules.

The codebase is still a modulith, not a set of independently deployable
microservices. Some modules include `MICROSERVICE.md` extraction notes, but the
current runtime is one API process plus an optional worker process.

## 4. Core And Common

`src/config.py` centralizes environment-driven settings:

- database, Redis, Kafka, Keycloak, MinIO/S3;
- CORS via `ALLOWED_ORIGINS`;
- trusted proxy handling via `TRUSTED_PROXIES`;
- task mode via `INLINE_TASKS_IN_DEV`;
- rate limits;
- attachment limits and signed URL TTL;
- `SUPER_ADMIN_SUBJECTS`;
- task handler module list.

`src/core/db.py` owns SQLAlchemy engine/session setup and the `get_db()`
context manager. It also exposes `enqueue_after_commit()`. Be careful with the
name: queued callbacks run after the current `session.commit()` call, but a
callback exception can still affect the HTTP response after the database commit
has happened.

`src/common` contains:

- `cache.py`: Redis-backed JSON memoization, fail-open.
- `rate_limiter.py`: Redis sliding-window limiter, fail-open.
- `object_storage.py`: boto3 S3/MinIO client and presigned URL helpers.
- `request_metadata.py`: trusted-proxy-aware client IP extraction.
- `session_tracker.py`: Redis presence keys, not an auth signal.
- `correlation.py`: correlation ID/CORS middleware.
- `pagination.py`, `spans.py`, and compatibility shims.

## 5. IAM And RBAC

IAM is responsible for turning a Keycloak token into a local `Principal`.

Implemented pieces:

- JWT signature, issuer, audience, expiry verification.
- JWKS and principal caching.
- Keycloak Admin REST wrapper for users, groups, roles, and password reset.
- Local `users` upsert on first-seen subject.
- Realm-role mapping from `realm_access.roles`.
- Keycloak group parsing for root, beneficiary, and sector groups.
- Pure RBAC predicates in `src/iam/rbac.py`.
- `@require_authenticated` decorator used by all `/api/*` handlers.

Important current behavior:

- `/tickora` root group implies admin/root behavior.
- Some admin endpoints require root group, while others check only
  `principal.is_admin`.
- Bare `/tickora/sectors/<code>` parses as chief access.
- Local `users.is_active=false` is not enforced during authentication.
- The SSE ticket query parameter fallback is accepted by the generic bearer
  extractor, not only by the stream endpoint.

See [RBAC.md](RBAC.md) for the current predicate matrix and known defects.

## 6. Audit

`src/audit` provides:

- `AuditEvent` ORM model;
- event constants;
- `record()`, global list, ticket audit, and user audit helpers.

Audit rows include actor, action, entity, ticket id, old/new values, metadata,
request IP, user agent, and correlation id.

Current reality:

- The global audit endpoints are admin/auditor gated.
- Ticket audit currently authorizes through ticket visibility and is too broad.
- The audit table is not partitioned despite older design text. It is a normal
  table with indexes.
- Audit writes usually share the caller's DB transaction.

## 7. Tasking

`src/tasking` provides:

- `Task` ORM model and lifecycle helpers;
- task registry decorator;
- producer;
- consumer/worker;
- admin read endpoints for tasks.

There are two execution modes:

| Mode | Behavior |
|---|---|
| `INLINE_TASKS_IN_DEV=true` | The handler is queued with `enqueue_after_commit()` and runs in-process after the caller commits. This is the safer mode for transaction visibility. |
| `INLINE_TASKS_IN_DEV=false` | `publish()` creates a lifecycle row in its own transaction and sends the Kafka message immediately. This can happen before the caller's transaction commits. |

The Kafka mode needs an outbox or caller-transaction-aware task creation. Until
then, worker tasks may observe missing rows, run after rollbacks, or emit
notifications for state that did not commit.

Registered ticketing notification handlers include:

- `notify_distributors`
- `notify_sector`
- `notify_assignee`
- `notify_ticket_event`
- `notify_comment`
- `notify_mentions`
- `notify_unassigned`
- `notify_beneficiary`
- `send_email_notification` (stub)

## 8. Ticketing Domain

`src/ticketing` is the business core. It contains 27 ORM classes, serializers,
state machine constants, notification handlers, templates, and service modules.

Service modules:

- `ticket_service.py`: create, list, detail, patch/update, SQL visibility.
- `workflow_service.py`: assignment, status changes, priority, assignees,
  sectors, history, audit, notification publishing.
- `comment_service.py`: public/private comments, mentions, edit/delete.
- `attachment_service.py`: presigned URL, register, list, download, delete.
- `review_service.py`: distributor/admin review entry point.
- `admin_service.py`: users, sectors, categories, metadata keys, settings.
- `monitor_service.py`: aggregate dashboards and role-aware cache keys.
- `dashboard_service.py`: custom dashboard and widget catalog logic.
- `notification_service.py`: notification rows and read state.
- `endorsement_service.py`: supplementary endorsement workflow.
- `snippet_service.py`: procedures with audience scoping.
- `watcher_service.py`: explicit ticket watchers.
- `links_service.py`: ticket-to-ticket links.
- `metadata_service.py`: typed ticket metadata.
- `reference_service.py`: form/reference dropdown data.

## 9. ORM Model Inventory

Current ORM classes:

- IAM: `User`.
- Audit: `AuditEvent`.
- Tasking: `Task`.
- Ticketing: `Sector`, `SectorMembership`, `Category`, `Subcategory`,
  `SubcategoryFieldDefinition`, `Beneficiary`, `Ticket`, `TicketComment`,
  `TicketAttachment`, `TicketStatusHistory`, `TicketSectorHistory`,
  `TicketAssignmentHistory`, `Notification`, `TicketLink`, `TicketMetadata`,
  `TicketSectorAssignment`, `TicketAssignee`, `MetadataKeyDefinition`,
  `TicketEndorsement`, `TicketWatcher`, `CustomDashboard`, `DashboardWidget`,
  `UserDashboardSettings`, `WidgetDefinition`, `Snippet`, `SnippetAudience`,
  `SystemSetting`.

Current schema corrections compared with older design docs:

- SLA tables/columns were removed.
- `dashboard_shares` was dropped.
- `custom_dashboards.is_public` still exists; the migration with "drop" in its
  name is a no-op.
- `audit_events` is not partitioned.
- `tickets.search_vector` exists again for potential future use, but active
  search currently uses `ILIKE` patterns in service code rather than a full
  trigger/indexed search pipeline.
- Notification rows do not have a uniqueness/idempotency constraint.

## 10. API Surface

`maps/endpoint.json` registers 111 method operations across 87 unique URLs.
Public URLs are only:

- `GET /health`
- `GET /liveness`
- `GET /readiness`

Authenticated API domains:

- `/api/me`
- `/api/tickets`
- `/api/tickets/<id>` workflow subroutes
- comments, attachments, metadata, watchers, links
- endorsements
- audit
- review
- reference
- admin
- monitor
- dashboards
- notifications and SSE
- snippets
- tasks

Controller files:

```text
src/api/admin.py
src/api/attachments.py
src/api/audit.py
src/api/comments.py
src/api/dashboard.py
src/api/endorsements.py
src/api/health.py
src/api/links.py
src/api/me.py
src/api/metadata.py
src/api/monitor.py
src/api/notifications.py
src/api/reference.py
src/api/review.py
src/api/snippets.py
src/api/tasks.py
src/api/tickets.py
src/api/watchers.py
src/api/workflow.py
```

Handlers are thin:

1. authenticate and build `Principal`;
2. parse request data;
3. call a service method;
4. serialize the result;
5. map domain errors to HTTP responses.

## 11. Ticket Request Lifecycle

Ticket creation, simplified:

1. Browser authenticates through Keycloak and sends bearer JWT.
2. `@require_authenticated` verifies the token and hydrates `Principal`.
3. Rate limiter checks `RATE_LIMIT_TICKET_CREATE_PER_MIN`.
4. Pydantic schema validates request body.
5. `ticket_service.create()` inserts ticket and related rows.
6. Audit row is recorded in the same DB session.
7. Notification task is published.
8. Serializer returns a permission-aware DTO.

Current caveat: in inline task mode, notification work is delayed until after
commit. In Kafka mode, task publish can occur before the ticket transaction
commits. That needs an outbox before production.

## 12. Workflow Architecture

Statuses:

- `pending`
- `assigned_to_sector`
- `in_progress`
- `done`
- `cancelled`

Assignment concepts:

- `current_sector_id` on `tickets`;
- `TicketSectorAssignment` for multi-sector association;
- `TicketAssignee` for multi-assignee association;
- active assignee fields on `tickets`;
- status, sector, and assignment history tables.

The intended pattern is atomic conditional update for state transitions.
Some flows use this well. Current workflow defects:

- the declared transition table accepts every status as a source for every
  action;
- `assign_to_me` currently accepts all statuses in the conditional SQL;
- generic `change_status` is too permissive;
- priority-change audit can lose the previous value.

These are correctness and security problems because workflow state is part of
authorization and audit truth.

## 13. Attachments Architecture

Attachment flow:

1. Caller asks API for a signed upload URL.
2. API checks ticket visibility, validates requested filename/size metadata,
   and returns a presigned PUT URL.
3. Browser uploads bytes directly to MinIO/S3.
4. Browser calls register endpoint.
5. API checks object existence and creates `TicketAttachment`.
6. Downloads authorize through API and redirect to a presigned GET URL.

Current limits:

- `ATTACHMENT_MAX_SIZE_BYTES` defaults to 25 MB.
- `ATTACHMENT_PRESIGNED_TTL` defaults to 60 seconds.

Current gaps:

- actual object size is not verified;
- checksum is not verified;
- content type/magic bytes are not enforced;
- AV scan is a stub;
- comment-level authorization during registration is incomplete.

## 14. Notifications Architecture

Notification data is stored in Postgres and delivered live through Redis pub/sub
and SSE.

SSE flow:

1. SPA posts to `/api/notifications/stream-ticket` with bearer JWT.
2. API stores a one-time Redis key `sse_ticket:<uuid>` with the raw JWT and a
   30-second TTL.
3. SPA opens EventSource to `/api/notifications/stream?sse_ticket=<uuid>`.
4. API redeems the ticket and subscribes to `notifications:{user_id}`.
5. Task handlers write notification rows and publish Redis messages after their
   own transaction commits.

Security caveat: the generic auth extractor accepts `sse_ticket` on every
authenticated endpoint, not only the stream endpoint.

Delivery caveat: notification row creation is not idempotent at the database
level.

## 15. Dashboards And Monitor

There are two related surfaces:

- monitor endpoints: role-aware aggregate data;
- custom dashboards: user-owned dashboards composed of widget rows.

Monitor data uses Redis memoization for expensive aggregate reads. Keys include
the caller's visibility class so an admin/global result is not served to a
sector user.

Custom dashboards:

- owner-scoped list/get/create/update/delete;
- widget catalog role filtering through `WidgetDefinition.required_roles`;
- widget config validation for scope, sector, and ticket references;
- auto-configure recipes by role.

Current gaps:

- widget deletion misses the parent owner check;
- `custom_dashboards.is_public` remains in the schema but sharing is not
  implemented;
- unknown widget types can be persisted;
- `UserDashboardSettings` is only partially reflected through API/frontend.

## 16. Frontend Architecture

The SPA uses:

- `frontend/src/auth`: Keycloak provider and auth bootstrap;
- `frontend/src/api`: Axios client and domain-specific API wrappers;
- `frontend/src/pages`: tickets, create, detail, review, avizator, procedures,
  profile, monitor, dashboard, audit, admin;
- `frontend/src/components`: shared UI components;
- `frontend/src/stores`: Zustand state for UI/session details;
- `frontend/src/i18n`: English/Romanian localization.

Main routes include:

- `/tickets`
- `/tickets/:ticketId`
- `/create`
- `/review`
- `/review/:ticketId`
- `/avizator`
- `/procedures`
- `/profile`
- `/monitor`
- `/dashboard`
- `/audit`
- `/admin`

Frontend caveats:

- Route guards are not security. They must match backend capabilities but cannot
  replace backend checks.
- The metadata delete client path currently does not match the backend endpoint
  contract.
- Vite dev API base/proxy configuration should be checked whenever the API base
  path changes.

## 17. Observability

Implemented or partially implemented:

- health endpoints: `/health`, `/liveness`, `/readiness`;
- correlation ID middleware;
- structured logging through the QF/framework logging layer;
- request metadata capture in audit rows;
- OpenTelemetry dependencies;
- Jaeger local service in docker compose.

Not implemented despite older docs:

- no confirmed `/metrics` endpoint;
- no complete Prometheus counter/histogram surface;
- no audit table partition rotation;
- no production log masking review;
- no dependency-audit CI gate.

## 18. Security Architecture

Security controls that exist:

- OIDC/PKCE through Keycloak;
- bearer JWT verification in backend;
- server-side RBAC predicates;
- SQL visibility filter for ticket lists;
- permission-aware serializers;
- audit rows for many writes and access denials;
- signed URLs for attachment transfer;
- trusted-proxy-aware request IP handling;
- CORS allowlist config;
- Redis rate limiting for ticket create and review.

Security controls that need work:

- admin role mutation separation;
- ticket audit authorization;
- inactive user enforcement;
- workflow transition invariants;
- attachment content verification and scanning;
- SSE ticket scope;
- rate limiting coverage;
- task outbox/transaction safety;
- endpoint matrix tests.

The detailed finding list is in [SECURITY_REVIEW.md](SECURITY_REVIEW.md).

## 19. Performance Architecture

Current performance choices:

- Gevent workers for cooperative concurrency.
- SQLAlchemy connection pooling.
- Bounded ticket page sizes.
- SQL visibility filtering.
- Redis caching for monitor aggregates.
- Phase 9 indexes for active ticket filters and audit recency.
- Direct browser-to-MinIO attachment transfer.

Likely pressure points:

- broad `assignable_users` joins;
- global audit scans as table grows;
- distributor queues over all pending/assigned tickets;
- long comment threads;
- long-lived SSE connections;
- Kafka retry noise from transaction visibility races.

Before production-like load:

- run `EXPLAIN ANALYZE` on ticket list variants by role;
- load test SSE concurrency through the actual ingress;
- test MinIO presigned upload abuse cases;
- seed audit at expected retention volume;
- verify worker behavior under rollback/retry cases.

## 20. Development Workflow

Common commands:

```bash
make up
make install
make keycloak-bootstrap
make migrate
make seed
make backend
make worker
make frontend-install
make frontend
make frontend-build
make lint
make test-unit
make test-integration
```

Do not use `make sla-checker` in the current branch.

## 21. Production Hardening Checklist

1. Fix critical/high findings in `SECURITY_REVIEW.md`.
2. Remove or fix stale Makefile targets.
3. Add outbox semantics for task publication.
4. Add attachment object verification and scanning.
5. Add audit retention and partitioning strategy.
6. Add dependency scanning and SAST/secret scanning in CI.
7. Add endpoint role matrix integration tests.
8. Decide whether local `users.is_active` or Keycloak enabled state is the
   source of truth and enforce it consistently.
9. Define production ingress, CORS, trusted proxy, TLS, and HSTS settings.
10. Implement real metrics if Prometheus is required.
11. Review all task payloads and audit payloads for secrets/PII.
12. Document backup/restore for Postgres, Keycloak database, and MinIO bucket.

## 22. Open Architecture Questions

- Should sector chiefs manage user roles at all, or only profile/sector
  membership inside their sectors?
- Should external requester identity be pinned to a local user id after first
  contact instead of matching email forever?
- Should ticket audit be staff-only or include beneficiaries with redaction?
- Should all workflow changes go through named action endpoints instead of a
  generic status endpoint?
- Should dashboard widget types be constrained by a database foreign key?
- Should notifications be generated from an outbox instead of direct task calls?
- Should attachment registration require client-side checksum headers?
- What retention periods apply to tickets, audit rows, notifications, and task
  rows?
