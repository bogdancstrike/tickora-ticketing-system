# Tickora — Architecture

_Last refreshed: 2026-05-12._

**Platform:** Ticketing, distribution, audit, RBAC, custom dashboards, real-
time notifications.
**Stack:** Python 3.12 · Flask · QF Framework (`qf-1.0.2-py3-none-any.whl`)
· SQLAlchemy 2.x · PostgreSQL 15 · Keycloak 24 · Redis · Kafka · MinIO ·
Jaeger · React 19 + Ant Design 6 · Vite · TanStack Query · Zustand · ECharts.
**Topology:** Modulith — one deployable; six explicit domain modules
(`core`, `common`, `iam`, `audit`, `tasking`, `ticketing`) plus a thin HTTP
layer.
**Target load:** 200–300 concurrent active users, ~50 RPS sustained, p95 <
700 ms on hot endpoints, p95 < 1.5 s on dashboards.

---

## 1. Goals and constraints

The architecture is driven by the BRD's non-negotiables:

- **RBAC server-side, always.** Visibility and mutation are decided in the
  backend; the frontend only renders affordances.
- **Audit everything that matters.** Status changes, sector changes,
  assignments, comment writes, attachment access, access-denied, admin
  overrides, config changes.
- **Private comments must never leak to beneficiaries.** Filtered server-
  side, defence-in-depth at SQL, service, and serializer layers.
- **Concurrency-safe assignment.** `assign_to_me` must be atomic — two
  members clicking simultaneously must not double-assign.
- **Stateless API.** Horizontal scaling behind a load balancer; sessions
  live in JWT + Postgres + Redis.
- **Containerizable, observable, scalable.** Health/readiness probes,
  Prometheus metrics, OpenTelemetry traces, JSON structured logs with
  `correlation_id`.

What we explicitly do **not** build into MVP-1: native mobile, AI auto-
classification, ERP/CRM integration, separate data warehouse, SLA tracking
(was scoped out at 2026-05-10 in commits `8e06b9d`/`29a1a0d`). Module
boundaries are designed so these can be bolted on without surgery.

---

## 2. High-level topology

```
                         ┌───────────────────────────────┐
                         │   Browser (React + AntD SPA)  │
                         │   PKCE → Keycloak             │
                         └───────────────┬───────────────┘
                                         │ HTTPS
                                         ▼
                         ┌───────────────────────────────┐
                         │  NGINX / Ingress (TLS, gzip,  │
                         │  rate-limit, X-Forwarded-For) │
                         └───────────────┬───────────────┘
                                         │
                       ┌─────────────────┼─────────────────┐
                       ▼                 ▼                 ▼
                ┌────────────┐    ┌────────────┐    ┌────────────┐
                │ Flask + QF │    │ Flask + QF │    │ Flask + QF │
                │  replica 1 │    │  replica 2 │ …  │  replica N │
                └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
                      │                 │                 │
        ┌─────────────┼─────────────────┼─────────────────┼──────────────┐
        ▼             ▼                 ▼                 ▼              ▼
  ┌──────────┐  ┌────────────┐  ┌────────────────┐  ┌──────────┐  ┌──────────┐
  │ Postgres │  │   Redis    │  │   MinIO / S3   │  │ Keycloak │  │  Kafka   │
  │  (HA,    │  │ (cache +   │  │  (attachments) │  │  (SSO)   │  │ (tasking │
  │  PgBouncer)│ │  locks +   │  │                │  │          │  │  topics) │
  │          │  │  ratelimit)│  │                │  │          │  │          │
  └──────────┘  └────────────┘  └────────────────┘  └──────────┘  └──────────┘
                                                                       │
                                                              ┌────────┴────────┐
                                                              ▼                 ▼
                                                     ┌────────────────┐ ┌──────────────┐
                                                     │ tickora-worker │ │  (retired)   │
                                                     │ (notifications,│ │ sla-checker  │
                                                     │  exports, etc.)│ │  removed     │
                                                     └────────────────┘ └──────────────┘
```

API replicas are stateless — no in-memory caches with cross-request
semantics; all shared state lives in Postgres or Redis. Same image runs as
`api` and `worker` with different `WORKER_NAME` / `ROLE` env vars (one
binary, two deployments).

The SLA-checker deployment was decommissioned along with the SLA subsystem.
If SLA reappears, it should plug into the existing tasking lifecycle rather
than a separate cron process.

---

## 3. Why QF + Flask + gevent

QF Framework (`qf-1.0.2-py3-none-any.whl`) gives us, for free:

- **Endpoint registry** declared in `maps/endpoint.json` (87 entries today)
  — controllers stay pure functions with the signature
  `handler(app, operation, request, **kwargs) → (body, status_code)`.
- **Gevent monkey-patched Flask** — cooperative concurrency, hundreds of
  in-flight requests per replica without thread overhead.
- **Tracing context** (`framework.tracing.get_tracer`) and **structured
  logger** (`framework.commons.logger`) wired to OpenTelemetry/Jaeger.
- **Kafka consumer/producer scaffolding** for async tasks.

Gevent + `psycogreen.gevent.patch_psycopg()` lets a single worker handle
200–300 concurrent users on cheap CPU. We pair this with **PgBouncer**
(transaction-pooling) so the 4–8 API replicas don't exhaust Postgres
connections.

---

## 4. Module boundaries

The codebase is a **modulith**: one deployable; six domain modules with
strict import rules. The dependency graph is a DAG:

```
core   ─┬─ common   ─┬─ iam ─┬─ audit ─┐
        │            │       │         │
        │            │       └────────►├─ ticketing
        │            └─────────────────┤
        └─────────────────────────────►├─ tasking ──► (handlers via Config)
                                       │
                                  api/ (composition root)
```

**Import rules (enforced by lint/import-linter):**

- `core` imports from nothing internal.
- `common` may import from `core` only.
- `iam` may import from `core`, `common`.
- `audit` may import from `core`, `common`, `iam`.
- `tasking` may import from `core` only (handlers register via
  `Config.TASK_HANDLER_MODULES`, not static imports).
- `ticketing` may import from any of the above.
- `api/` may import from any module — it's the composition root for HTTP.
- Modules **never** import from `api/`.

Each leaf module ships with a `MICROSERVICE.md`
(`src/<module>/MICROSERVICE.md`) describing what to copy to extract it as
a standalone service. At the time of writing, `common/`, `audit/`, and
`tasking/` are self-contained; only `ticketing/` is genuinely modulith-only
because it *is* the business domain.

### 4.1 `core/` — bare infrastructure

The smallest-possible base layer: the things the framework boot depends on
directly.

- `config.py` — single `Config` class, every env var in one place
  (Postgres URL, Redis URL, Keycloak, Kafka, MinIO, rate limits, super-
  admin subjects, trusted proxies, INLINE_TASKS_IN_DEV, task handler
  modules).
- `db.py` — SQLAlchemy engine, session factory, `get_db()` context
  manager (commits on success, rolls back on raise), `enqueue_after_commit`
  (run a callable once the current transaction commits), declarative `Base`.
- `tracing.py` — re-exports QF tracer.
- `errors.py` — `BusinessRuleError`, `PermissionDeniedError`,
  `NotFoundError`, `ConcurrencyConflictError`, `ValidationError`. Mapped to
  HTTP codes by the API layer.
- `correlation.py` — middleware that pulls/generates `X-Correlation-Id`
  and stuffs it into a contextvar so every log line, audit row, and trace
  span shares the same id.
- `redis_client.py` — lazy Redis client, returns `None` when Redis is
  unreachable; every caller treats that as "feature unavailable, fall back
  to live computation".

> **Back-compat:** `src/core/cache`, `pagination`, `object_storage`,
> `rate_limiter`, `request_metadata`, `session_tracker`, `spans` still
> exist as one-line shims that re-export from `src/common`. Existing
> imports keep working; new code imports from `src.common.*` directly.

### 4.2 `common/` — cross-module utilities

Reusable building blocks any module can pick up. None of these participate
in the framework boot sequence — they layer on top of `core`.

- `pagination.py` — cursor pagination helpers.
- `cache.py` — JSON memoisation (`cached_call`) wrapping expensive read-
  only aggregates. Redis-backed; fails open.
- `rate_limiter.py` — Redis sliding-window limiter (`check`). Fails open.
- `request_metadata.py` — trusted-proxy-aware `client_ip()` and audit
  metadata helper. Reads `TRUSTED_PROXIES` from config.
- `session_tracker.py` — Redis presence keys (`mark_active`,
  `active_user_count`). 5-minute TTL; powers the admin Active Sessions KPI.
  **Never** used for authorization.
- `object_storage.py` — boto3-backed S3/MinIO helpers
  (`presigned_put_url`, `object_exists`, `ensure_bucket`).
- `spans.py` — thin `with span(...)` wrapper around the QF tracer.

### 4.3 `iam/` — identity, RBAC, Keycloak

The IAM module is **the only place** that talks to Keycloak. Everything
else gets a `Principal` object.

- **Token verification** (`token_verifier.py`) — Validates JWT signature
  against Keycloak JWKS (cached in Redis), checks `iss`, `aud`, `exp`,
  `nbf`.
- **Principal hydration** (`service.py`) — Maps a verified token to a
  `Principal` (sub, username, email, global roles, sector memberships,
  beneficiary type). Caches the result keyed by `jti`. First-time-seen
  Keycloak subjects upsert a row in `users`.
- **`Principal`** (`principal.py`) — Immutable dataclass with
  `global_roles`, `sector_memberships`, `has_root_group`. Helper properties
  `is_admin`, `is_auditor`, `is_distributor`, `is_avizator`, `is_internal`,
  `is_external`; helper methods `has_role`, `has_any`, `is_chief_of`,
  `is_member_of`, plus aggregate sets `all_sectors`, `chief_sectors`,
  `member_sectors`.
- **RBAC primitives** (`rbac.py`) — Pure functions. 29 predicates as of
  2026-05-12 (`can_view_ticket`, `can_modify_ticket`,
  `can_see_private_comments`, `can_post_*_comment`, `can_drive_status`,
  `can_assign_*`, `can_decide_endorsement`, `can_view_global_audit`, …).
  See `docs/RBAC.md` for the full matrix.
- **Decorators** (`decorators.py`) — `@require_authenticated`,
  `@require_role(*roles)`, `@require_any(roles)`. The extractor also
  redeems short-lived `sse_ticket` query parameters from Redis for
  EventSource compatibility.
- **Keycloak admin** (`keycloak_admin.py`) — Thin wrapper around the
  Keycloak Admin REST API. Used by the admin endpoints to manage users,
  groups, and roles. Authenticates via `tickora-api` client-credentials
  grant with minimal realm-management roles: `query-users`,
  `query-groups`, `view-users`, `view-realm`, `manage-users`.

### 4.4 `audit/` — immutable ledger

Single entry point for writing audit events plus the typed event constants
that go in them.

- `service.py` — `record(...)`, `list_(...)`, `get_for_ticket(...)`,
  `get_for_user(...)`. Every write shares the caller's DB session so audit
  and the originating change commit together. The list endpoint supports
  filters by action, actor username, entity type/id, ticket id,
  correlation id, date range.
- `events.py` — typed event constants (`TICKET_CREATED`,
  `COMMENT_CREATED`, `ACCESS_DENIED`, `CONFIG_CHANGED`, …).

The audit table is partitioned by month (`PARTITION BY RANGE
(created_at)`); new partitions are auto-created. Old partitions can be
detached and archived to S3 by retention policy. Indexes:
`(action, created_at)`, `actor_user_id`, `correlation_id`,
`idx_audit_events_actor_recent`.

### 4.5 `tasking/` — async lifecycle

Kafka producer/consumer plus durable task state via the `tasks` table.

- **`producer.py`** — `publish(task_name, payload)` writes a `pending`
  lifecycle row, then sends an envelope (incl. `task_id`) to Kafka.
  `INLINE_TASKS_IN_DEV=true` runs the handler in-process after the current
  transaction commits (via `enqueue_after_commit`).
- **`consumer.py`** — gevent-friendly consumer loop. Flips the matching
  row through `pending → running → completed/failed`. Calls
  `lifecycle.recover_orphans()` once at startup.
- **`lifecycle.py`** — `create`, `mark_running`, `mark_completed`,
  `mark_failed`, `heartbeat`, `recover_orphans`; plus read helpers
  (`list_tasks`, `get_task`) for the admin tasks page.
- **`registry.py`** — `register_task(name)` decorator. Handlers register
  at module import. The registry has **zero** domain imports — the
  registration direction is one-way.
- **`models.py`** — `Task` ORM: status, payload, correlation_id,
  attempts, timestamps, heartbeat, last_error.

Two Kafka topics:

- **`tickora_fast_tasks`** — short, parallelisable: notifications, audit
  shipping, dashboard cache invalidation, attachment AV scan dispatch.
- **`tickora_slow_tasks`** — exports, bulk imports.

Operator surface: `GET /api/tasks` (admin) lists recent rows;
`GET /api/tasks/<id>` fetches one.

### 4.6 `ticketing/` — business core

The largest module. Subpackages:

- **`models.py`** — 27 SQLAlchemy ORM classes:
  `Sector`, `SectorMembership`, `Category`, `Subcategory`,
  `SubcategoryFieldDefinition`, `Beneficiary`, `Ticket`, `TicketComment`,
  `TicketAttachment`, `TicketStatusHistory`, `TicketSectorHistory`,
  `TicketAssignmentHistory`, `Notification`, `TicketLink`,
  `TicketMetadata`, `TicketSectorAssignment`, `TicketAssignee`,
  `MetadataKeyDefinition`, `TicketEndorsement`, `TicketWatcher`,
  `CustomDashboard`, `DashboardWidget`, `UserDashboardSettings`,
  `WidgetDefinition`, `Snippet`, `SnippetAudience`, `SystemSetting`.
- **`state_machine.py`** — declarative transition table. Statuses:
  `pending`, `assigned_to_sector`, `in_progress`, `done`, `cancelled`.
  Action × `from_status` → `to_status`. Adding a transition is a one-line
  change.
- **`service/ticket_service.py`** — create, list, get, update. Builds
  queries that encode RBAC visibility via `_visibility_filter`; no caller
  can ask for tickets they cannot see.
- **`service/workflow_service.py`** — atomic state transitions
  (`assign_to_sector`, `assign_to_me`, `assign_to_user`, `reassign`,
  `unassign`, `mark_done`, `close`, `reopen`, `cancel`, `change_status`,
  `change_priority`, `add_assignee`, `remove_assignee`, `add_sector`,
  `remove_sector`). Each transition validates state + RBAC, writes a
  history row, emits an audit event, publishes notification tasks.
- **`service/comment_service.py`** — public/private split, mention
  parsing (`@username`), 15-minute edit window, soft-delete.
- **`service/attachment_service.py`** — pre-signed S3/MinIO URLs for
  upload (5-min TTL) and download (60-s TTL). AV scan stub.
- **`service/admin_service.py`** — `list_users`, `get_user`, `update_user`,
  `reset_password`, sector / membership / category / subcategory /
  metadata-key / system-setting CRUD, group-hierarchy view. Helpers
  `require_admin` and `require_admin_or_chief` gate each call.
- **`service/review_service.py`** — distributor triage. Atomic update
  applies category/subcategory/priority/assignment in one transaction.
- **`service/monitor_service.py`** — dashboards. Redis-cached aggregates
  with role-aware cache keys.
- **`service/dashboard_service.py`** — custom dashboards & widgets, the
  catalogue, the auto-configure recipe selector.
- **`service/snippet_service.py`** — procedures with audience scoping
  (sector / role / beneficiary_type).
- **`service/watcher_service.py`** — ticket subscriptions.
- **`service/links_service.py`** — ticket-to-ticket links.
- **`service/endorsement_service.py`** — supplementary endorsements
  (`avizare suplimentară`).
- **`service/metadata_service.py`** — typed key/value metadata bound to a
  ticket.
- **`notifications.py`** — task handlers (registered with `tasking`):
  `notify_distributors`, `notify_sector`, `notify_assignee`,
  `notify_ticket_event`, `notify_comment`, `notify_mentions`,
  `notify_unassigned`, `notify_beneficiary`, `send_email_notification`.
- **`serializers.py`** — permission-aware out-models.

### 4.7 `api/` — HTTP surface

Thin controllers, one file per domain. 19 files; 87 endpoints.

```
src/api/
├── admin.py           # /api/admin/*  (users, sectors, memberships,
│                      #                categories, metadata, system-settings,
│                      #                widget-definitions, group-hierarchy)
├── attachments.py     # /api/tickets/<id>/attachments, /api/attachments/<id>
├── audit.py           # /api/audit, /api/tickets/<id>/audit, /api/users/<id>/audit
├── comments.py        # /api/tickets/<id>/comments, /api/comments/<id>
├── dashboard.py       # /api/dashboards[/widgets/auto-configure]
├── endorsements.py    # /api/tickets/<id>/endorsements, /api/endorsements/*
├── health.py          # /health, /liveness, /readiness
├── links.py           # /api/tickets/<id>/links, /api/links/<id>
├── me.py              # /api/me
├── metadata.py        # /api/tickets/<id>/metadata
├── monitor.py         # /api/monitor/*  (overview, global, sectors, users, timeseries)
├── notifications.py   # /api/notifications/*  (incl. SSE stream)
├── reference.py       # /api/reference/*  (ticket-options, assignable-users, fields)
├── review.py          # /api/tickets/<id>/review
├── snippets.py        # /api/snippets[/<id>]
├── tasks.py           # /api/tasks[/<id>]
├── tickets.py         # /api/tickets[/<id>]
├── watchers.py        # /api/tickets/<id>/watchers[/<user_id>]
└── workflow.py        # /api/tickets/<id>/{assign-*,sectors,assignees,mark-done,...}
```

Every handler:

1. Pulls `Principal` (via `@require_authenticated`).
2. Parses + validates input (Pydantic v2 model — fast, OpenAPI-friendly).
3. Calls a single service method.
4. Maps domain errors → HTTP via `errors.py`.
5. Returns `(body, status_code)`.

Endpoints are declared in `maps/endpoint.json`. QF wires them up at boot.

---

## 5. Request lifecycle (golden path)

`POST /api/tickets` from an internal beneficiary:

1. **NGINX** terminates TLS, adds `X-Forwarded-For`, applies global rate
   limit (per IP: 50/s burst, 10/s sustained).
2. **Flask app** (gevent worker) receives the request. `correlation.py`
   middleware sets `correlation_id` from header or generates a new UUID.
3. **`@require_authenticated`** decorator extracts Bearer token, calls
   `iam.verify_token()`. Cache hit on Redis → fast path; miss → JWKS
   verify + cache.
4. **`get_or_create_user_from_token()`** upserts the user row if first-
   seen. Sector groups synced from token claims.
5. **Pydantic** validates the body. Reject early with 422 if malformed.
6. **`ticket_service.create()`** opens a Postgres transaction, inserts the
   ticket, generates `ticket_code` (sequence-protected format
   `TK-YYYY-NNNNNN`), records `TICKET_CREATED` audit event, commits.
7. **`tasking.publish("notify_distributors", {"ticket_id": …})`** —
   enqueued via `enqueue_after_commit`, so it only fires once the ticket is
   committed.
8. **Notification worker** writes one row per distributor/admin recipient,
   then publishes to `notifications:{user_id}` on Redis (also via
   `enqueue_after_commit` so the SSE event never precedes the DB row).
9. **Browser subscribers** receive the event on their SSE stream;
   distributors and admins with the sound toggle enabled hear `/alert.mp3`.
10. **Response** serialised through a permission-aware serializer — even on
    creation we filter the response by what the caller can see.
11. **Logger** emits a JSON line with `duration_ms`, `status_code`,
    `user_id`, `ticket_id`, `correlation_id`. Prometheus middleware bumps
    `http_requests_total`, `tickets_created_total`,
    `http_request_duration_seconds`.

---

## 6. The atomic `assign_to_me` pattern

Two members clicking the same ticket at the same instant must result in
exactly one winner. We use a **conditional UPDATE** as the source of truth
— no advisory locks, no `SELECT FOR UPDATE`:

```sql
UPDATE tickets
SET    assignee_user_id              = :uid,
       last_active_assignee_user_id  = :uid,
       status                        = 'in_progress',
       assigned_at                   = now(),
       first_response_at             = COALESCE(first_response_at, now()),
       updated_at                    = now()
WHERE  id                  = :ticket_id
  AND  current_sector_id   = :user_sector_id
  AND  assignee_user_id    IS NULL
  AND  status              IN ('pending', 'assigned_to_sector')
  AND  is_deleted          = false
RETURNING *;
```

If `RETURNING` is empty, the service raises `ConcurrencyConflictError` →
409 with the current state so the UI can refresh. The Prometheus counter
`ticket_assignment_conflicts_total` increments. Audit event is written
**only on the winning row**.

This pattern (one atomic UPDATE per state transition) is reused for every
workflow action, plus the supplementary endorsements claim (`POST
/api/endorsements/<id>/claim`).

---

## 7. RBAC — visibility vs. mutation

The BRD's principle "to see a ticket is not to have the right to modify
it" is enforced by **two separate predicates** at the SQL level:

**Visibility (used by every list/get query):**

```sql
-- pseudocode, materialised by SQLAlchemy filter expressions
ticket.created_by_user_id = :uid
OR ticket.beneficiary_id IN (SELECT b.id FROM beneficiaries b WHERE b.user_id = :uid)
OR (ticket.current_sector_id IN (:my_sectors))
OR :is_distributor AND ticket.status IN ('pending', 'assigned_to_sector')
OR :is_admin
OR :is_auditor
OR :is_external_requester_by_email
```

**Mutation (checked in service before every transition):**
`iam.rbac.can_modify_ticket(p, t)` returns true iff `p.is_admin`, or
`p.is_chief_of(t.current_sector_code)`, or `p` is the current active
assignee.

**Self-assignment policy.** Comment writes (`can_post_public_comment`,
`can_post_private_comment`) and operator-side status pushes
(`can_drive_status`, `can_mark_done`) require **active assignment** (or
admin override / triage role / beneficiary side). Bystander chiefs and
sector members cannot comment or change status without first
`assign_to_me`. See `docs/RBAC.md` for the full matrix.

Comment visibility filters at the SQL layer too:

```sql
visibility = 'public'
OR (visibility = 'private' AND :can_see_private)
```

Three checks total: query filter, service guard, serializer scrubber. If
one ever fails, the others catch it.

---

## 8. Data model notes

Tickora has 27 ORM classes; the BRD §16 DDL is adopted with the following
additions and corrections:

- **`ticket_endorsements`** — supplementary endorsement workflow. An
  assigned operator can request approval from an avizator before pushing
  the ticket forward. Pool requests fan out to every avizator; direct
  requests target one. `claim` is atomic via `UPDATE … WHERE
  assigned_to_user_id IS NULL`.
- **`ticket_watchers`** — explicit subscribers, independent of
  assignment. Watchers receive notifications and can see the ticket in
  their `my_watchlist` widget.
- **`ticket_links`** — parent/child/blocked-by relationships between
  tickets. Surfaced as the `linked_tickets` widget.
- **`ticket_metadata`** + **`metadata_key_definitions`** — typed key/value
  pairs bound to a ticket. Keys are admin-defined (with data types and
  enum options) so the schema stays stable while the metadata fan-out can
  grow.
- **`categories`** + **`subcategories`** + **`subcategory_field_definitions`**
  — hierarchical ticket classification with per-subcategory custom fields.
- **`custom_dashboards`** + **`dashboard_widgets`** + **`widget_definitions`**
  + **`user_dashboard_settings`** — per-user customisable dashboards.
- **`snippets`** + **`snippet_audiences`** — admin-authored procedures
  with audience scoping (sector / role / beneficiary_type).
- **`tasks`** — task lifecycle table for the `tasking` module.
- **`system_settings`** — generic key/value config (e.g.
  `autopilot_max_ticket_watchers`).
- **`audit_events`** is partitioned by month
  (`PARTITION BY RANGE (created_at)`). New partitions are auto-created;
  old partitions can be detached and archived to S3 by retention policy.
- **`tickets.lock_version INTEGER`** for optimistic concurrency on non-
  workflow edits, via SQLAlchemy's `version_id_col`.
- **`notifications.delivered_channels JSONB`** (`{"in_app": true,
  "email": false}`) so retries are idempotent.
- **`ticket_code`** generated via Postgres sequence + format function;
  collision-free without app-level coordination.

**Schema removals** (since the original design):

- `mv_dashboard_*` materialized views — dropped in
  `c4d8a72e1f5b_drop_orphan_tables`. Monitor service uses Redis-cached
  live aggregates exclusively.
- `dashboard_shares` — dropped in `c4d8a72e1f5b_drop_orphan_tables`. The
  feature was unimplemented.
- `custom_dashboards.is_public` — dropped in
  `d5e9b1207f08_drop_is_public_dashboards.py`. Sharing isn't implemented.
- `tickets.search_vector` and its trigger — removed in
  `c769aeaad506_remove_search_vector_and_trigger.py` because the search
  surface moved to client-side filtering on the loaded page; reintroduced
  in `8b305d56a8ec_restore_search_vector_column.py` for potential future
  full-text use, but no trigger and no GIN index yet.
- SLA tables and columns — removed alongside the SLA-checker process.

Indexes from BRD §17 plus the Phase 9 perf set
(`9a1f3e0c2d10_phase9_perf_indexes`).

### 8.1 Connection pooling

- Per replica: SQLAlchemy pool size 5, max_overflow 5.
- All replicas behind **PgBouncer** (transaction pooling) → effective
  Postgres-side limit 50–100 connections regardless of replica count.

---

## 9. Caching strategy

Redis is used for:

- **JWT verification cache** — keyed by `jti`, TTL = remaining token
  lifetime. Avoids re-hitting JWKS.
- **Principal cache** — keyed by `keycloak_subject`, TTL 60 s. Invalidated
  on role/membership change by IAM.
- **Monitor cache** (`monitor_overview`, etc.) — keyed by visibility class
  (admin/auditor share one key; sector users keyed by sorted sectors;
  others keyed by user_id), TTL 60 s.
- **SSE tickets** — one-time, 30-second TTL.
- **Rate limiting** — per-user sliding window for write endpoints
  (comments: 30/min, attachments: 10/min, review: configurable).
- **Active session tracker** — `tickora:session:active:<user_id>`, TTL
  5 minutes. Presence-only.
- **SSE pubsub** — `notifications:{user_id}` channels published by the
  worker, subscribed by the API replica serving the user's stream.

We do **not** cache ticket data itself — staleness here is a correctness
problem.

Every Redis path **fails open**: if Redis is unreachable the surface
degrades (no cache, no rate limit, no presence) but the request still
succeeds.

---

## 10. Notifications & SSE

Emitted as Kafka tasks (or run inline in DEV via `INLINE_TASKS_IN_DEV`).
Handlers in `src/ticketing/notifications.py`:

| Task | Trigger | Recipients |
|---|---|---|
| `notify_distributors` | ticket created | admins + distributors (resolved from Keycloak by role) |
| `notify_sector` | ticket assigned to a sector | sector members |
| `notify_assignee` | ticket assigned to a user | the named user |
| `notify_ticket_event` | generic ticket update | participants (creator, beneficiary, assignees, watchers) |
| `notify_comment` | comment posted | participants (private comments skip the requester side) |
| `notify_mentions` | comment contained `@user` | mentioned users that can see the comment |
| `notify_unassigned` | ticket unassigned | previous assignee + sector members |
| `notify_beneficiary` | status changed | participants on the requester side |
| `send_email_notification` | any of the above with email enabled | stub — SMTP config gated |

Each handler:

1. Writes one `notifications` row per recipient.
2. Schedules `_publish_to_sse_raw(...)` via `enqueue_after_commit`. The
   Redis publish only fires once the rows are committed, so the SSE event
   never precedes the DB row.

**Browser-side:**

1. POST `/api/notifications/stream-ticket` exchanges the JWT for a 30-
   second one-time ticket stored in Redis.
2. GET `/api/notifications/stream?sse_ticket=<uuid>` opens a long-lived
   gevent EventSource connection.
3. The handler subscribes to `notifications:{user_id}` and forwards
   messages as SSE frames. Heartbeats every 30 s keep the connection
   open through corporate proxies.
4. The SPA's `NotificationDropdown` updates the badge, prepends the row,
   triggers an AntD `notification` popup. Distributors and admins with the
   sound toggle enabled hear `/alert.mp3` on `ticket_created`.

Notifications are **idempotent**: each is keyed `(ticket_id, event_type,
recipient_user_id)` so concurrent fan-outs don't double-deliver.

---

## 11. Attachments

- **Storage:** MinIO (S3-compatible) bucket `tickora-attachments`, server-
  side encryption on in prod.
- **Upload:** client requests pre-signed PUT URL from
  `/api/tickets/<id>/attachments/upload-url` → uploads directly to MinIO →
  calls `/api/tickets/<id>/attachments` to register metadata. Backend
  **never proxies the bytes**.
- **Download:** client calls `/api/attachments/<id>/download` → backend
  authorises → returns 302 to a short-lived (60 s) signed URL.
- **Visibility:** every attachment is public or private. Private
  attachments are gated by `can_see_private_comments`.
- **Limits:** 25 MB per file MVP-1, 100 MB MVP-2. MIME allowlist enforced
  server-side from extension + magic bytes.
- **AV scan:** MVP-1 stub returns clean. MVP-2 dispatches a `tasking` job
  to ClamAV; attachment stays `pending_scan` until cleared.
- **Audit:** every upload/download/delete writes an audit event with
  caller's IP and user agent.

---

## 12. Frontend

The SPA mirrors a familiar AntD operational pattern:

- **Layout:** AntD `Layout` with collapsible left `Sider`, top `Header`
  with theme toggle / sound toggle (admins+distributors only) / language
  switcher / notification bell / user menu.
- **Theme:** AntD `ConfigProvider` switching between light/dark via
  `useThemeStore` (Zustand `persist` → `tickora-theme`). Sound toggle via
  `useSoundStore` (Zustand `persist` → `tickora-sound`).
- **Auth:** `keycloak-js` (PKCE). `KeycloakProvider` holds the singleton;
  an axios interceptor injects `Authorization: Bearer` and refreshes 30 s
  before expiry. Routes are gated by a `<RequireRole>` wrapper.
- **Data layer:** TanStack Query for server state, Zustand for UI/session
  state (theme, sidebar, filters, sound, language).
- **Routing:** `react-router-dom` v7. Top-level routes:
  - `/tickets` — ticket queue (everyone)
  - `/tickets/:ticketId` — ticket detail
  - `/create` — new ticket form
  - `/review` + `/review/:ticketId` — distributor triage (admin /
    distributor only)
  - `/avizator` — endorsement inbox (admin / avizator only)
  - `/procedures` — admin-authored snippets
  - `/profile` — own profile + access tree
  - `/monitor` — KPI cards
  - `/dashboard` — custom dashboards
  - `/audit` — global audit explorer (admin / auditor only)
  - `/admin` — administration (admin or sector chief)
- **i18n:** `react-i18next` with English and Romanian locales in
  `frontend/src/i18n/locales/`. Language switcher in the sidebar.
- **Real-time:** SSE subscription in `NotificationDropdown` that
  invalidates relevant TanStack Query caches and pops AntD notifications.
- **Product tour:** `<ProductTour pageKey="...">` per page; entry from the
  page's `<TourInfoButton>`.
- **Build:** Vite + TypeScript strict mode. Pages directly import service
  layers in `frontend/src/api/`.

### 12.1 Custom dashboards

`react-grid-layout` 12-column grid. Each widget is rendered by a function
in `DashboardPage.tsx` based on its `type`. Configurable widgets open a
form modal on add; the form is type-specific (sector selector, ticket
selector, scope dropdown). The widget picker is sourced from
`GET /api/admin/widget-definitions` — already role-filtered server-side,
so a beneficiary sees fewer choices than a chief.

Auto-configure (`POST /api/dashboards/<id>/auto-configure`) runs a recipe
based on the caller's role and packs the result onto the grid.

---

## 13. Security

Layered:

- **Transport.** TLS terminated at NGINX. HSTS, secure-only cookies (we
  don't use cookies for auth).
- **AuthN.** Keycloak OIDC + PKCE. Tokens short-lived (5 min access,
  30 min refresh). JWKS rotation handled by `iam`.
- **AuthZ.** Server-side RBAC at every endpoint. Visibility predicate
  baked into every list query. See `docs/RBAC.md` and `docs/SECURITY_REVIEW.md`.
- **Input.** Pydantic v2 schemas; reject extra fields by default.
- **Output.** Permission-aware serializers strip private fields per
  principal.
- **Rate limiting.** Redis sliding window per user/IP for write endpoints.
- **CSRF.** Not applicable to JSON+Bearer endpoints. Applicable to file
  uploads via signed pre-URLs (the URL itself is the credential, scoped
  tightly to method + path + content type + expiry).
- **IDOR.** Every `/api/.../<id>` endpoint pulls the entity then checks
  visibility before returning. 404 returned where existence must not leak.
- **Secrets.** No secrets in env files in repo; `.env.example` only.
  Production uses Kubernetes secrets or Vault.
- **Audit on denial.** Every 403 records `ACCESS_DENIED` with rule name,
  route, target entity. The auditor role can query these.
- **PII masking in logs.** Email and phone hashed in log lines; visible
  only in DB.
- **SAST/DAST.** `bandit`, `pip-audit`, `npm audit` in CI (TODO Phase 0).

---

## 14. Observability

- **Logs.** JSON to stdout, scraped by container logs → Loki/ES. Every
  line carries `correlation_id`, `user_id`, `route`, `duration_ms`.
- **Metrics.** `prometheus_client` exposed at `/metrics`. Counters for
  HTTP requests, ticket events, workflow conflicts, task lifecycle.
- **Traces.** OpenTelemetry → Jaeger (dev) / OTLP collector (prod). Every
  request spans the controller, every service method spans its work,
  every SQL query spans its execution.
- **Health endpoints.** `/health` (full deps), `/liveness` (process up),
  `/readiness` (deps reachable enough to serve).

---

## 15. Performance budget

| Operation                   | p50      | p95      | p99      |
|-----------------------------|---------:|---------:|---------:|
| `GET /api/tickets` (paged)  | 80 ms    | 400 ms   | 800 ms   |
| `GET /api/tickets/<id>`     | 60 ms    | 300 ms   | 600 ms   |
| `POST /api/.../assign-to-me`| 40 ms    | 200 ms   | 400 ms   |
| `POST /api/.../comments`    | 50 ms    | 250 ms   | 500 ms   |
| `GET /api/monitor/overview` | 200 ms   | 1.2 s    | 2 s      |
| Ticket creation             | 70 ms    | 350 ms   | 700 ms   |

Capacity model for **300 concurrent users at ~0.5 RPS each = 150 RPS
sustained**:

- 4 API replicas × 1 gevent worker × 100 in-flight greenlets = 400
  concurrency headroom.
- Postgres p95 query < 50 ms on properly-indexed access paths → ample.
- PgBouncer keeps Postgres connection count flat regardless of replicas.

---

## 16. Project layout

```
tickora/
├── main.py                  # entry; gevent monkey-patch first; FrameworkApp boot
├── worker.py                # entry for tasking consumer
├── Makefile
├── Dockerfile
├── docker-compose.yml       # postgres, keycloak, redis, minio, kafka, jaeger
├── requirements.txt
├── .env.example
├── CLAUDE.md
├── README.md
│
├── dist/qf-1.0.2-py3-none-any.whl
│
├── docs/
│   ├── architecture.md
│   ├── implementation_plan.md
│   ├── brd.md
│   ├── RBAC.md
│   ├── SECURITY_REVIEW.md
│   └── TODO.md
│
├── maps/
│   └── endpoint.json        # QF endpoint registration (87 endpoints)
│
├── migrations/              # alembic (26 revisions)
│   └── versions/
│
├── scripts/
│   ├── seed_dev.py
│   ├── seed_dev_30M.py      # large-volume perf seed
│   └── keycloak_bootstrap.py
│
├── src/
│   ├── config.py
│   ├── core/
│   ├── common/
│   ├── iam/
│   ├── audit/
│   ├── tasking/
│   ├── ticketing/
│   │   ├── models.py
│   │   ├── state_machine.py
│   │   ├── notifications.py
│   │   ├── serializers.py
│   │   ├── service/
│   │   │   ├── admin_service.py
│   │   │   ├── attachment_service.py
│   │   │   ├── comment_service.py
│   │   │   ├── dashboard_service.py
│   │   │   ├── endorsement_service.py
│   │   │   ├── links_service.py
│   │   │   ├── metadata_service.py
│   │   │   ├── monitor_service.py
│   │   │   ├── review_service.py
│   │   │   ├── snippet_service.py
│   │   │   ├── ticket_service.py
│   │   │   ├── watcher_service.py
│   │   │   └── workflow_service.py
│   │   └── templates/
│   └── api/                 # 19 controllers
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── public/
│   │   ├── alert.mp3
│   │   └── logo*.png
│   └── src/
│       ├── main.tsx
│       ├── TickoraApp.tsx
│       ├── api/             # typed API clients per domain
│       ├── auth/            # keycloak wrapper + RequireRole
│       ├── components/
│       │   ├── common/      # PageHeader, NotificationDropdown, etc.
│       │   └── ...
│       ├── pages/           # 11 pages
│       ├── stores/          # theme, sound, session
│       ├── i18n/
│       │   └── locales/{en.json, ro.json}
│       └── types/
│
└── tests/
    ├── unit/                # RBAC, principal, pagination, state machine,
    │                        # widget config validation, caching, session
    │                        # tracker
    ├── integration/         # testcontainers Postgres
    │   └── acceptance/      # pytest-bdd scenarios
    └── e2e/                 # API smoke + Playwright (incremental)
```

---

## 17. Deployment

- **Image:** single Python image (`Dockerfile`) plus single Node build →
  static assets served by NGINX.
- **K8s:** two Deployments off the same image with different commands —
  `api` (4 replicas) and `worker` (2 replicas). The SLA cron is no longer
  a separate deployment.
- **Probes:** `livenessProbe → /liveness`, `readinessProbe → /readiness`.
- **HPA:** API scales on CPU (target 60%) and on `http_requests_total`
  rate. Worker on Kafka consumer lag.
- **Migrations:** Alembic, run as a one-shot `Job` before rolling the API.
  Migrations are backwards-compatible (expand-then-contract).
- **Backups:** Postgres `pg_dump` daily + WAL archive for PITR. MinIO
  bucket replicated.

---

## 18. Open questions

These don't block MVP-1 but should be answered before production
hardening:

1. Are external beneficiaries authenticated through Keycloak (separate
   realm/client) or via a magic-link / token-on-email flow? Affects the
   `/portal` routes (not yet implemented).
2. Retention windows — how long do closed/cancelled tickets stay queryable
   vs. archived? Drives audit partition policy.
3. Email provider — internal SMTP relay or transactional service
   (SES/SendGrid)? Affects worker config and bounce handling.
4. SLA reintroduction — if needed, does it plug into the existing
   `tasking` lifecycle or as a separate cron? The first design hooked it
   into a dedicated `sla-checker` deployment; that was removed when SLA
   was scoped out.
5. Dashboard sharing — beyond owner-only, what (if anything) does sharing
   look like? The `dashboard_shares` model was dropped to avoid an
   attractive nuisance; a future implementation should design RBAC end-to-
   end before reintroducing tables.
