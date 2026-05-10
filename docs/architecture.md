# Tickora — Architecture

**Platform:** Ticketing, tasking, distribution, audit, RBAC, dashboarding
**Stack:** Python 3.12 · Flask · QF Framework (`qf-1.0.2-py3-none-any.whl`) · SQLAlchemy 2.x · PostgreSQL 15 · Keycloak · React 19 + Ant Design 6 · Vite · TanStack Query · Zustand
**Topology:** Monolith (modulith) with three explicit domain modules — **iam**, **tasking**, **ticketing** — plus shared infra and a thin HTTP layer.
**Target load:** 200–300 concurrent active users, ~50 RPS sustained, p95 < 700 ms on hot endpoints, p95 < 1.5 s on dashboards.

---

## 1. Goals and constraints

The architecture is driven by the BRD's non-negotiables:

- **RBAC server-side, always.** Visibility and mutation are decided in the backend; the frontend only renders affordances.
- **Audit everything that matters.** Status changes, sector changes, assignments, comment writes, attachment access, access-denied, admin overrides, exports.
- **Private comments must never leak to beneficiaries.** Filtered server-side, defense-in-depth at SQL, service, and serializer layers.
- **Concurrency-safe assignment.** `Assign to me` must be atomic — two members clicking simultaneously must not double-assign.
- **Stateless API.** Horizontal scaling behind a load balancer; sessions live in JWT + Postgres + Redis.
- **Containerizable, observable, scalable.** Health/readiness probes, Prometheus metrics, OpenTelemetry traces, JSON structured logs with `correlation_id`.

What we explicitly **do not** build into MVP-1: native mobile, AI auto-classification, ERP/CRM integration, separate data warehouse. Module boundaries are designed so these can be bolted on without surgery.

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
                                                     │ tickora-worker │ │ sla-checker  │
                                                     │ (notifications,│ │ (cron, every │
                                                     │  exports, etc.)│ │  60s)        │
                                                     └────────────────┘ └──────────────┘
```

API replicas are **stateless** — no in-memory caches with cross-request semantics; all shared state lives in Postgres or Redis. Same image runs as `api`, `worker`, and `sla-checker` with different `WORKER_NAME` / `ROLE` env vars (one binary, three deployments).

---

## 3. Why QF + Flask + gevent

QF Framework (`qf-1.0.2-py3-none-any.whl`) gives us, for free:

- **Endpoint registry** declared in `maps/endpoint.json` — controllers stay pure functions with the signature `handler(app, operation, request, **kwargs) → (body, status_code)`.
- **Gevent monkey-patched Flask** — cooperative concurrency, ~hundreds of in-flight requests per replica without thread overhead.
- **Tracing context** (`framework.tracing.get_tracer`) and **structured logger** (`framework.commons.logger`) wired to OpenTelemetry/Jaeger.
- **Kafka consumer/producer scaffolding** for async tasks (we already have prior art in `rag-poc`'s `tasking/` module).

Gevent + `psycogreen.gevent.patch_psycopg()` lets a single worker handle 200–300 concurrent users on cheap CPU. We pair this with **PgBouncer** (transaction-pooling) so the 4–8 API replicas don't exhaust Postgres connections.

---

## 4. Module boundaries

The codebase is a **modulith**: one deployable, three domain modules with strict imports. The dependency graph is a DAG:

```
   ┌──────────────┐
   │   ticketing  │  ← business domain (tickets, comments, attachments, sectors)
   └───────┬──────┘
           │ uses
           ▼
   ┌──────────────┐         ┌──────────────┐
   │     iam      │ ──uses─►│   tasking    │  ← async fanout (Kafka) for notifications,
   └───────┬──────┘         └──────┬───────┘    SLA checks, exports, audit shipping
           │                       │
           └───────────┬───────────┘
                       ▼
                 ┌──────────┐
                 │   core   │  ← Config, DB engine, get_db(), logger, tracing,
                 │          │     correlation_id, exception types
                 └──────────┘
```

**Rules enforced by lint/import-linter:**

- `ticketing` may import from `iam`, `tasking`, `core`.
- `iam` may import from `core`, `tasking` (only for emitting events).
- `tasking` may import from `core` only.
- `api/` may import from any module — it's the composition root for HTTP.
- Modules **never** import from `api/`.

This keeps the door open for extracting `tasking` into a service later without untangling spaghetti.

### 4.1 `iam/` — Identity, RBAC, Keycloak interface

The IAM module is **the only place** that talks to Keycloak. Everything else gets a `Principal` object.

Responsibilities:

- **Token verification.** Validates JWT signature against Keycloak's JWKS (cached, rotated), checks `iss`, `aud`, `exp`, `nbf`. Uses `python-jose` or `authlib`.
- **Principal hydration.** Maps a verified token to a `Principal` (sub, username, email, global roles, sector memberships, beneficiary ref). Caches the result in Redis for 60 s keyed by `jti`.
- **User provisioning.** First time a Keycloak subject hits the API, IAM upserts a row in `users` with `keycloak_subject` as the natural key. Group membership (`/tickora/sectors/sN/members|chiefs`) is mirrored into `sector_memberships`.
- **RBAC primitives.** Pure functions: `can_view_ticket(principal, ticket) -> bool`, `can_modify_ticket(principal, ticket) -> bool`, `can_see_private_comments(principal, ticket) -> bool`, `can_assign_to_user(principal, ticket, target_user) -> bool`. These are the only place RBAC rules live.
- **Decorators.** `@require_role("tickora_admin")`, `@require_authenticated`, `@require_principal` for use by controllers in `api/`.
- **Keycloak admin interface (extension surface).** A thin wrapper around Keycloak Admin REST for operations Tickora needs to drive itself: list users, sync groups, force a user re-login, fetch realm roles. Used by the admin UI (`/api/admin/users`, `/api/admin/keycloak-mappings`). Calls flow through a service account (client-credentials grant) — never with a user token.
- **Audit hooks.** Emits `ACCESS_DENIED` audit events for every 403, with the rule that fired.

Public surface (everything else imports from here):

```python
from iam import Principal, get_principal, require_role, require_authenticated
from iam.rbac import can_view_ticket, can_modify_ticket, can_see_private_comments
from iam.service import get_or_create_user_from_token, sync_keycloak_groups
from iam.keycloak_admin import KeycloakAdminClient
```

### 4.2 `ticketing/` — Tickets, comments, attachments, sectors

The business core. Subpackages:

- `models.py` — SQLAlchemy ORM mirroring section 16 of the BRD: `Ticket`, `TicketComment`, `TicketAttachment`, `TicketStatusHistory`, `TicketSectorHistory`, `TicketAssignmentHistory`, `Sector`, `SectorMembership`, `Beneficiary`, `SlaPolicy`, `TicketLink`, `Notification`, `AuditEvent`.
- `service/ticket_service.py` — create, list, get, update. Builds queries that already encode RBAC visibility; no caller can ask for tickets they can't see.
- `service/workflow_service.py` — state machine. Transitions: `assign_to_sector`, `assign_to_me`, `reassign`, `mark_done`, `close`, `reopen`, `cancel`, `mark_duplicate`, `change_priority`. Each transition validates current state + RBAC + writes a status-history row + emits an audit event + publishes notification tasks.
- `service/comment_service.py` — public/private split, server-side filtering, mention parsing.
- `service/attachment_service.py` — pre-signed S3/MinIO URLs for upload, AV scan hook (sync stub for MVP-1, async via Kafka in MVP-2), download token verification.
- `service/sector_service.py` — sector CRUD, membership management, mirrors changes back to Keycloak groups when admin edits memberships.
- `service/sla_service.py` — computes `sla_due_at` on creation/transition, evaluates breach status. SLA cron job lives in the worker.
- `service/dashboard_service.py` — pre-aggregated queries; some hot ones backed by materialized views refreshed every 5 min.
- `service/audit_service.py` — single `record(action, entity, old, new, metadata)` entry point. Insert-only.
- `state_machine.py` — declarative table of allowed transitions per role-context, used by `workflow_service`.
- `events.py` — typed event constants (`TICKET_CREATED`, `TICKET_ASSIGNED_TO_SECTOR`, …).

The state machine is data, not code: `STATE_TRANSITIONS = {(from_status, action): (to_status, required_role_check)}`. Adding a new transition is a one-line change.

### 4.3 `tasking/` — Async fanout

Mirrors the prior art in `rag-poc/src/tasking/`. Two Kafka topics:

- **`tickora_fast_tasks`** — short, parallelizable: notifications, audit shipping, dashboard cache invalidation, attachment AV scan dispatch.
- **`tickora_slow_tasks`** — exports, bulk imports, materialized-view refresh.

Components:

- `producer.py` — `publish_task({task_type, payload})`. Falls back to in-process daemon thread if Kafka is unreachable so the API stays up during partial outages.
- `consumer.py` — gevent-friendly consumer loop, semaphore-gated for slow tasks.
- `registry.py` — `task_type → handler` map. Handlers live in their owning module (`ticketing/notifications.py`, `ticketing/exports.py`, etc.) and register themselves at import. The registry has **zero domain imports** — the registration direction is one-way.
- `recovery.py` — on startup, scans for tasks left dangling (status `processing` in DB) and republishes them. Same pattern as `rag-poc`'s `_recover_dangling_tasks`.

The worker process imports `ticketing` to load handlers, then runs `consumer.run()`. The API process imports the producer only.

### 4.4 `core/` — Bare infrastructure

The smallest-possible base layer: things the framework boot depends on
directly. Reusable utilities (caching, pagination, etc.) live in
`src/common/` instead — see §4.5.

- `config.py` — single `Config` class, all env vars in one place.
- `db.py` — SQLAlchemy engine, session factory, `get_db()` context manager, declarative `Base`.
- `tracing.py` — re-exports QF tracer.
- `errors.py` — `BusinessRuleError`, `PermissionDeniedError`, `NotFoundError`, `ConcurrencyConflictError`. Mapped to HTTP codes by the API layer.
- `correlation.py` — middleware that pulls/generates `X-Correlation-Id`, stuffs it into a contextvar.
- `redis_client.py` — lazy Redis client, returns `None` when Redis is unreachable.

> **Back-compat:** `src/core/cache`, `pagination`, `object_storage`,
> `rate_limiter`, `request_metadata`, `session_tracker`, `spans` still
> exist as one-line shims that re-export from `src/common`. Existing
> imports keep working; new code imports from `src.common.*` directly.

### 4.5 `common/` — Cross-module utilities

Reusable building blocks any module can pick up. None of these participate
in the framework boot sequence — they layer on top of `core`.

- `pagination.py` — cursor pagination helpers (we don't use offset on big tables).
- `cache.py` — JSON memoization (`cached_call`) wrapping expensive read-only aggregates.
- `rate_limiter.py` — Redis sliding-window limiter (`check`). Fail-open.
- `request_metadata.py` — trusted-proxy-aware `client_ip()` and audit metadata helper.
- `session_tracker.py` — Redis presence keys (`mark_active` / `active_user_count`). 5-minute TTL; powers the admin Active Sessions KPI.
- `object_storage.py` — boto3-backed S3/MinIO helpers (`presigned_put_url`, `object_exists`, `ensure_bucket`).
- `spans.py` — thin `with span(...)` wrapper around the QF tracer.

### 4.6 `audit/` — Immutable ledger

Single entry point for writing audit events plus the typed event constants
that go in them. Used by `ticketing`, `iam`, and `tasking` whenever a
domain action needs an attributable trail.

- `service.py` — `record(...)`, `list_(...)`, `get_for_ticket(...)`, `get_for_user(...)`. Every write shares the caller's DB session so audit and the originating change commit together.
- `events.py` — `TICKET_CREATED`, `COMMENT_CREATED`, `ACCESS_DENIED`, … (one name → one immutable string).

> Back-compat: `src/ticketing/service/audit_service.py` and
> `src/ticketing/events.py` re-export from here.

### 4.7 `tasking/` — Async lifecycle

Was Kafka producer/consumer plumbing only; now also owns durable task
state via the `tasks` table.

- `models.py` — `Task` ORM with status (`pending`/`running`/`completed`/`failed`), payload, correlation_id, attempts, timestamps, heartbeat.
- `lifecycle.py` — `create()` (writes a `pending` row), `mark_running()`/`mark_completed()`/`mark_failed()`/`heartbeat()`, `recover_orphans()` (run on worker startup), and read helpers (`list_tasks`, `get_task`).
- `producer.py` — `publish(task_name, payload)` writes a lifecycle row, then sends the envelope (incl. `task_id`) to Kafka. DEV inline mode follows the same path.
- `consumer.py` — flips the matching row through the lifecycle around the handler call. Calls `lifecycle.recover_orphans()` once at consumer startup.
- `registry.py` — `register_task(name)` decorator; handlers register at module import.

Operator surface: `GET /api/tasks` (admin) lists recent rows;
`GET /api/tasks/<id>` fetches one. See `src/api/tasks.py`.

### 4.5 `api/` — HTTP surface

Thin controllers, one file per domain:

```
src/api/
├── __init__.py
├── tickets.py      # /api/tickets and /api/tickets/<id>/*
├── comments.py     # /api/tickets/<id>/comments, /api/comments/<id>
├── attachments.py  # /api/tickets/<id>/attachments, /api/attachments/<id>/*
├── beneficiaries.py
├── sectors.py
├── dashboard.py
├── audit.py
├── admin.py
├── notifications.py
└── health.py       # /health, /liveness, /readiness, /metrics
```

Every handler:

1. Pulls `Principal` (via decorator).
2. Parses + validates input (Pydantic v2 model — fast, gives us OpenAPI gratis).
3. Calls a single service method.
4. Maps domain errors → HTTP via `errors.py`.
5. Returns `(body, status_code)`.

Endpoints are declared in `maps/endpoint.json` exactly as in `rag-poc`. QF wires them up.

---

## 5. Request lifecycle (golden path)

`POST /api/tickets` from an internal beneficiary:

1. **NGINX** terminates TLS, adds `X-Forwarded-For`, applies global rate limit (per IP: 50/s burst, 10/s sustained).
2. **Flask app** (gevent worker) receives the request. `correlation.py` middleware sets `correlation_id` from header or generates a new UUID.
3. **`@require_authenticated`** decorator extracts Bearer token, calls `iam.verify_token()`. Cache hit on Redis → fast path; miss → JWKS verify + cache.
4. **`get_or_create_user_from_token()`** upserts the user row if first-seen. Sector groups synced from token claims.
5. **Pydantic** validates the body. Reject early with 422 if malformed.
6. **`ticket_service.create()`** opens a Postgres transaction, inserts the ticket, generates `ticket_code` (advisory-lock-protected sequence: `TK-YYYY-NNNNNN`), records `TICKET_CREATED` audit event, commits.
7. **`tasking.publish_task({"task_type": "notify_distributors", "ticket_id": ...})`** — fire-and-forget.
8. **Response** serialized through a permission-aware serializer — even on creation we filter the response by what the caller can see.
9. **Logger** emits a JSON line with `duration_ms`, `status_code`, `user_id`, `ticket_id`, `correlation_id`. Prometheus middleware bumps `http_requests_total`, `tickets_created_total`, `http_request_duration_seconds`.

---

## 6. The atomic `Assign to me` (BRD §10.5, §26.4)

Two members clicking the same ticket at the same instant must result in exactly one winner. We use a **conditional UPDATE** as the source of truth — no advisory locks, no `SELECT FOR UPDATE`:

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
  AND  status              IN ('pending', 'assigned_to_sector', 'reopened')
  AND  is_deleted          = false
RETURNING *;
```

If `RETURNING` is empty, the service raises `ConcurrencyConflictError` → 409 with the current state, so the UI can refresh. The Prometheus counter `ticket_assignment_conflicts_total` increments. Audit event is written **only on the winning row**.

This pattern (one atomic UPDATE per state transition) is reused for every workflow action.

---

## 7. RBAC — visibility vs. mutation

The BRD's principle "to see a ticket is not to have the right to modify it" is enforced by **two separate predicates** at the SQL level:

**Visibility (used by every list/get query):**

```sql
-- pseudocode, materialized by SQLAlchemy filter expressions
ticket.created_by_user_id = :uid
OR ticket.beneficiary_id IN (SELECT b.id FROM beneficiaries b WHERE b.user_id = :uid)
OR (ticket.current_sector_id IN (:my_sectors_member))      -- sector member
OR (ticket.current_sector_id IN (:my_sectors_chief))       -- sector chief
OR :is_distributor AND ticket.status IN ('pending', 'assigned_to_sector')
OR :is_admin
OR :is_auditor
```

**Mutation (checked in service before every transition):**

`iam.can_modify_ticket(principal, ticket)` returns true iff:

- principal is admin, **or**
- principal is sector chief of `ticket.current_sector_id`, **or**
- principal is the current `assignee_user_id`, **or**
- specific transitions allow specific roles (e.g. `close` allowed for the beneficiary regardless of assignee).

**Self-assignment policy (since 2026-05-09).** Comment writes
(`can_post_public_comment`, `can_post_private_comment`) and operator-side
status pushes (`can_drive_status`, `can_mark_done`) are restricted to the
**active assignee** plus admin override (and beneficiary-side close/reopen).
Bystander chiefs and sector members can read but cannot write — to
participate they must `assign_to_me` first. This makes every comment and
status change attributable to a real owner. See `docs/RBAC.md` for the full
matrix.

The state machine in `ticketing.workflow_service` calls `can_modify_ticket` plus a transition-specific predicate before each action. Failing either raises `PermissionDeniedError` → 403 + `ACCESS_DENIED` audit row.

Comment visibility filters at the SQL layer too:

```sql
-- private comments only for: distributor, sector member of current sector,
-- sector chief, admin, auditor (if policy allows)
visibility = 'public'
OR (visibility = 'private' AND :can_see_private)
```

Three checks total: query filter, service guard, serializer scrubber. If one ever fails, the others catch it.

---

## 8. Data model notes

The DDL in BRD §16 is adopted verbatim with a few additions:

- **`tickets.search_vector tsvector`** populated by trigger on insert/update; concatenates `ticket_code`, `title`, `txt`, `resolution`, requester name, organization. GIN index for full-text search.
- **`audit_events`** is **partitioned by month** (`PARTITION BY RANGE (created_at)`). New partitions auto-created by a daily cron. Old partitions detached + archived to S3 by retention policy.
- **`tickets.lock_version INTEGER`** for optimistic concurrency on non-workflow edits (title/description by admin), via SQLAlchemy's `version_id_col`.
- **`notifications`** gains `delivered_channels JSONB` (`{"in_app": true, "email": false}`) so retries are idempotent.
- **`ticket_code`** generated via Postgres sequence + format function; collision-free without app-level coordination.

Indexes from BRD §17 are adopted unchanged — they're already well-shaped for the access patterns. We add:

```sql
CREATE INDEX idx_tickets_search_vector
ON tickets USING gin(search_vector);

CREATE INDEX idx_audit_events_correlation
ON audit_events(correlation_id);
```

### 8.1 Connection pooling

- Per replica: SQLAlchemy pool size 5, max_overflow 5.
- All replicas behind **PgBouncer** (transaction pooling) → effective Postgres-side limit 50–100 connections regardless of replica count.

---

## 9. Caching strategy

Redis is used for:

- **JWT verification cache** — keyed by `jti`, TTL = remaining token lifetime. Avoids re-hitting JWKS.
- **Principal cache** — keyed by `keycloak_subject`, TTL 60 s. Invalidated on role/membership change by IAM.
- **Hot dashboard fragments** — KPI cards keyed by `(role, sector_id, day)`, TTL 60 s.
- **Rate limiting** — per-user sliding window for write endpoints (e.g. comments: 30/min, attachments: 10/min).
- **Distributed locks** — only for cross-replica admin operations (e.g. running a one-shot data migration). **Not** for ticket assignment — that uses the atomic UPDATE.

We do **not** cache ticket data itself — staleness here is a correctness problem.

---

## 10. Notifications

Emitted as Kafka tasks. Channels:

- **In-app** — insert into `notifications` table. UI polls or subscribes via SSE.
- **SSE** — `/api/notifications/stream` keeps a long-lived gevent connection per browser. The stream is hydrated from a per-user Redis pubsub channel published by the worker.
- **Email** — SMTP via worker. Bounce/failure tracked in `delivered_channels`.
- **Webhook (admin-configured)** — out of MVP-1 scope.

Notifications are **idempotent**: each is keyed `(ticket_id, event_type, recipient_user_id, dedup_window=5min)` to prevent storms when many state transitions land at once.

---

## 11. Attachments

- **Storage:** MinIO (S3-compatible) bucket `tickora-attachments`, server-side encryption on.
- **Upload flow:** client requests pre-signed PUT URL from `/api/tickets/{id}/attachments/upload-url` → uploads directly to MinIO → calls `/api/tickets/{id}/attachments` to register metadata. Backend never proxies the bytes.
- **Download flow:** client calls `/api/attachments/{id}/download` → backend authorizes → returns 302 to a short-lived (60 s) signed URL.
- **Limits:** 25 MB per file MVP-1, 100 MB MVP-2. MIME allowlist enforced server-side from extension + magic bytes.
- **AV scan:** MVP-1 stub returns clean. MVP-2 dispatches a `tasking` job to ClamAV; attachment stays `pending_scan` until cleared.
- **Audit:** every upload/download/delete writes an audit event with the caller's IP and user agent.

---

## 12. Frontend

The SPA mirrors `rag-poc/frontend/`'s look and feel:

- **Layout:** AntD `Layout` with collapsible left `Sider`, top `Header` with theme toggle + user menu, content area with route-driven pages.
- **Theme:** AntD `ConfigProvider` switching between light/dark via `useThemeStore` (Zustand). Same dark-mode token tweaks as `rag-poc` (`#0d1117` background family, accent blue).
- **Auth:** `keycloak-js` (PKCE). `KeycloakProvider` holds the singleton; an axios interceptor injects `Authorization: Bearer` and refreshes 30 s before expiry. Routes are gated by a `<RequireRole>` wrapper.
- **Data layer:** TanStack Query for server state, Zustand for UI/session state (theme, sidebar, filters). Same pattern as `rag-poc`.
- **Routing:** `react-router-dom` v7. Top-level routes per role (`/tickets`, `/queue`, `/sector/:id`, `/admin/...`).
- **Components mirroring rag-poc:** `PageHeader`, `RelevanceBar`-style indicators, table page patterns (`DataTable`-like). Plus the BRD's recommended set: `TicketTable`, `TicketDetailsPage`, `StatusTimeline`, `CommentBox`, `AttachmentUploader`, `AssignToMeButton`, `ReassignModal`, `AuditDrawer`, `SlaIndicator`, `DashboardKpiCard`, etc.
- **Real-time:** SSE subscription in a `useNotificationsStream` hook that invalidates relevant TanStack Query caches on event arrival (e.g. `ticket:updated:<id>` → `queryClient.invalidateQueries(['ticket', id])`).
- **Build:** Vite + TypeScript strict mode; `tsc -b && vite build` for production. Same `package.json` shape as `rag-poc` (React 19, AntD 6, `@ant-design/icons`, `@ant-design/plots`, `@tanstack/react-query`, `axios`, `dayjs`, `zustand`).

---

## 13. Security

Layered:

- **Transport.** TLS terminated at NGINX. HSTS, secure-only cookies (we don't use cookies for auth, but for CSRF tokens on form-encoded admin endpoints we do).
- **AuthN.** Keycloak OIDC + PKCE. Tokens short-lived (5 min access, 30 min refresh). JWKS rotation handled by `iam`.
- **AuthZ.** Server-side RBAC at every endpoint. Visibility predicate baked into every list query.
- **Input.** Pydantic v2 schemas; reject extra fields by default. IP fields validated as `INET`. Free-text bounded.
- **Output.** Permission-aware serializers strip private fields per principal.
- **Rate limiting.** NGINX + Redis sliding window per user/IP.
- **CSRF.** Not applicable to JSON+Bearer endpoints. Applicable to file uploads via signed pre-URLs (the URL itself is the credential, scoped tightly).
- **IDOR.** Every `/api/.../{id}` endpoint pulls the entity then checks visibility before returning. Tested.
- **Secrets.** No secrets in env files in repo; `.env.example` only. Production uses Kubernetes secrets or Vault.
- **Audit on denial.** Every 403 records `ACCESS_DENIED` with rule name, route, target entity. The auditor role can query these.
- **PII masking in logs.** Email and phone hashed in log lines; visible only in DB.
- **SAST/DAST.** `bandit`, `pip-audit`, `npm audit` in CI. Optional ZAP baseline scan in staging.

---

## 14. Observability

Identical pattern to `rag-poc`:

- **Logs.** JSON to stdout, scraped by container logs → Loki/ES.
- **Metrics.** `prometheus_client` exposed at `/metrics`. Counters per BRD §21.2.
- **Traces.** OpenTelemetry → Jaeger (dev) / OTLP collector (prod). Every request spans the controller, every service method spans its work, every SQL query spans its execution.
- **Health endpoints.** `/health` (full deps), `/liveness` (process up), `/readiness` (deps reachable enough to serve).

---

## 15. Performance budget

| Operation                   | p50      | p95      | p99      |
|-----------------------------|---------:|---------:|---------:|
| `GET /api/tickets` (paged)  | 80 ms    | 400 ms   | 800 ms   |
| `GET /api/tickets/{id}`     | 60 ms    | 300 ms   | 600 ms   |
| `POST /api/.../assign-to-me`| 40 ms    | 200 ms   | 400 ms   |
| `POST /api/.../comments`    | 50 ms    | 250 ms   | 500 ms   |
| `GET /api/dashboard/global` | 200 ms   | 1.2 s    | 2 s      |
| Ticket creation             | 70 ms    | 350 ms   | 700 ms   |

Capacity model for **300 concurrent users at ~0.5 RPS each = 150 RPS sustained**:

- 4 API replicas × 1 gevent worker × 100 in-flight greenlets = 400 concurrency headroom.
- Postgres p95 query < 50 ms on properly-indexed access paths → ample.
- PgBouncer keeps Postgres connection count flat regardless of replicas.

---

## 16. Project layout

Mirrors `rag-poc`:

```
tickora/
├── main.py                  # entry; gevent monkey-patch first; FrameworkApp boot
├── worker.py                # entry for tasking consumer
├── sla_checker.py           # entry for SLA cron
├── Makefile
├── Dockerfile
├── docker-compose.yml       # postgres, keycloak, redis, minio, kafka, jaeger
├── requirements.txt         # flask, qf wheel, sqlalchemy, alembic, psycogreen, …
├── .env.example
├── CLAUDE.md
├── README.md
│
├── dist/qf-1.0.2-py3-none-any.whl
│
├── docs/
│   ├── architecture.md
│   ├── implementation_plan.md
│   ├── rbac_matrix.md
│   ├── state_machine.md
│   └── api_reference.md
│
├── maps/
│   └── endpoint.json        # QF endpoint registration
│
├── scripts/
│   ├── seed_dev.py          # sectors, users, sample tickets
│   ├── keycloak_bootstrap.py
│   └── benchmark.py
│
├── migrations/              # alembic
│   └── versions/
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   │
│   ├── core/
│   │   ├── db.py
│   │   ├── logging.py
│   │   ├── tracing.py
│   │   ├── errors.py
│   │   ├── pagination.py
│   │   └── correlation.py
│   │
│   ├── iam/
│   │   ├── principal.py
│   │   ├── token_verifier.py
│   │   ├── decorators.py
│   │   ├── rbac.py
│   │   ├── service.py
│   │   └── keycloak_admin.py
│   │
│   ├── ticketing/
│   │   ├── models.py
│   │   ├── state_machine.py
│   │   ├── events.py
│   │   ├── service/
│   │   │   ├── ticket_service.py
│   │   │   ├── workflow_service.py
│   │   │   ├── comment_service.py
│   │   │   ├── attachment_service.py
│   │   │   ├── sector_service.py
│   │   │   ├── beneficiary_service.py
│   │   │   ├── sla_service.py
│   │   │   ├── dashboard_service.py
│   │   │   └── audit_service.py
│   │   ├── notifications.py     # task handlers (registered with tasking)
│   │   ├── exports.py           # task handlers
│   │   └── serializers.py       # permission-aware Pydantic out-models
│   │
│   ├── tasking/
│   │   ├── producer.py
│   │   ├── consumer.py
│   │   ├── registry.py
│   │   ├── recovery.py
│   │   └── handlers.py
│   │
│   └── api/
│       ├── tickets.py
│       ├── comments.py
│       ├── attachments.py
│       ├── beneficiaries.py
│       ├── sectors.py
│       ├── dashboard.py
│       ├── audit.py
│       ├── admin.py
│       ├── notifications.py
│       └── health.py
│
├── frontend/
│   ├── package.json         # React 19 + AntD 6 + TanStack + axios + zustand + dayjs
│   ├── vite.config.ts
│   ├── index.html
│   ├── tsconfig*.json
│   └── src/
│       ├── main.tsx
│       ├── TickoraApp.tsx
│       ├── index.css
│       ├── api/                     # one file per backend domain
│       ├── auth/                    # keycloak-js wrapper, RequireRole, hooks
│       ├── components/
│       │   ├── common/              # PageHeader, KpiCard, EmptyState, ...
│       │   ├── layout/              # AppShell, Sider, Header
│       │   ├── tickets/
│       │   ├── comments/
│       │   ├── attachments/
│       │   ├── sectors/
│       │   ├── admin/
│       │   ├── dashboard/
│       │   └── audit/
│       ├── hooks/                   # useTickets, useTicket, useComments, ...
│       ├── stores/                  # themeStore, sessionStore, filtersStore
│       ├── pages/                   # one per route
│       └── types/
│
└── tests/
    ├── unit/
    ├── integration/                 # real Postgres via testcontainers
    └── e2e/                         # API-level + Playwright UI smoke
```

---

## 17. Deployment

- **Image:** single Python image (`Dockerfile`) plus single Node build → static assets served by NGINX.
- **K8s:** three Deployments off the same image with different commands — `api` (4 replicas), `worker` (2), `sla-checker` (1, with leader election via Redis lock so only one instance runs the cron).
- **Probes:** `livenessProbe → /liveness`, `readinessProbe → /readiness`.
- **HPA:** API scales on CPU (target 60%) and on `http_requests_total` rate. Worker on Kafka consumer lag.
- **Migrations:** Alembic, run as a one-shot `Job` before rolling the API. Migrations are backwards-compatible (expand-then-contract).
- **Backups:** Postgres `pg_dump` daily + WAL archive for PITR. MinIO bucket replicated.

---

## 18. Open questions

These don't block MVP-1 but should be answered before production hardening:

1. Are external beneficiaries authenticated through Keycloak (separate realm/client) or via a magic-link / token-on-email flow? Affects the `/portal` routes.
2. Retention windows — how long do closed tickets stay queryable vs. archived? Drives partition policy.
3. Email provider — internal SMTP relay or transactional service (SES/SendGrid)? Affects worker config.
4. Multi-language UI — Romanian only for MVP-1, or i18n from day one?
