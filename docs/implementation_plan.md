# Tickora — Implementation Plan

This plan turns `docs/architecture.md` into a sequenced delivery program. It is organized in **phases**, each delivering a runnable increment. Every phase ends with green tests, a working dev stack, and a demo-able slice. Phase 1 establishes the skeleton; phases 2–5 fill in the BRD's MVP-1; phases 6–8 cover MVP-2/3.

**Conventions used throughout:**

- "Backend done" means: ORM + service + API endpoint + unit test + integration test against a real Postgres in `testcontainers`.
- "Frontend done" means: API hook + component + page + dark/light themes verified + axe-clean (no critical a11y violations).
- "Audit-clean" means: every state-changing path writes the appropriate `audit_events` row, verified by an integration test.
- "RBAC-clean" means: each endpoint has at least one positive and one negative authorization test (e.g. member-from-other-sector → 403).

---

## Phase 0 — Bootstrap (1–2 days)

Stand up the empty project so everything compiles, runs, and ships.

### 0.1 Repo skeleton

- [ ] Create the layout from `architecture.md` §16. Empty `__init__.py` in every package.
- [ ] Drop `dist/qf-1.0.2-py3-none-any.whl` into the repo (copy from `rag-poc/dist/`).
- [ ] `requirements.txt` — start from `rag-poc/requirements.txt`, strip RAG-specific deps (`elasticsearch`, `fastembed`, `rank-bm25`, `openai`, `pypdf`, `python-docx`, `beautifulsoup4`, `lxml`), keep `flask`, `flask-restx`, `gevent`, `psycogreen`, `sqlalchemy`, `psycopg2-binary`, `alembic`, `redis`, `kafka-python`, `python-dotenv`, `requests`, `colorama`, `pytest`, `pytest-cov`, `responses`, `faker`. Add `python-jose[cryptography]`, `pydantic>=2`, `boto3`, `prometheus-client`, `opentelemetry-api/sdk/instrumentation-flask`, `python-keycloak`, `testcontainers[postgres,redis,kafka]`, `httpx`.
- [ ] `Dockerfile` adapted from `rag-poc` (multi-stage builder + slim runtime, non-root `appuser`).
- [ ] `Makefile` with `install`, `backend`, `worker`, `infra`, `up`, `down`, `frontend`, `frontend-install`, `test`, `test-unit`, `test-integration`, `migrate`, `seed`, `lint`.
- [ ] `.env.example` with all `Config` keys, no secrets.
- [ ] `.gitignore`, `CLAUDE.md` (commands + arch summary), `README.md` (quickstart).

### 0.2 `core/` and entrypoint

- [ ] `src/config.py` — `Config` class, all env vars (DB URL, Keycloak realm/client/secret, Redis URL, Kafka bootstrap, MinIO endpoint, JWT issuer, allowed origins, log level, port).
- [ ] `src/core/db.py` — engine with pool size 5/overflow 5, `Base = declarative_base()`, `get_db()` context manager that commits/rolls back/closes.
- [ ] `src/core/logging.py` — JSON logger with contextvars (`correlation_id`, `user_id`, `ticket_id`).
- [ ] `src/core/correlation.py` — Flask before/after request hooks setting/clearing the contextvar; reads or generates `X-Correlation-Id`.
- [ ] `src/core/errors.py` — exception types + Flask error handler that maps to JSON.
- [ ] `src/core/tracing.py` — re-export from `framework.tracing`.
- [ ] `main.py` — gevent monkey-patch first, `psycogreen.gevent.patch_psycopg()`, load `.env`, register error handlers, build `FrameworkApp`, install correlation middleware, run.
- [ ] `maps/endpoint.json` — start with `health` and `liveness` (copy pattern from `rag-poc`).
- [ ] `src/api/health.py` — `health_check`, `liveness`, `readiness` (DB ping + Redis ping + Keycloak JWKS reachability).

### 0.3 Infra dev stack

- [ ] `docker-compose.yml` — postgres:15, redis:7, kafka+zookeeper, minio, keycloak:26, jaeger. Healthchecks on all. Mirror `rag-poc/docker-compose.yml` style.
- [ ] `make up` brings the stack live. `make backend` runs `python main.py` on port 5100. `curl localhost:5100/tickora/health` returns OK.

### 0.4 Frontend skeleton

- [ ] `cd frontend && npm init` based on `rag-poc/frontend/package.json` — same React 19, AntD 6, TanStack Query, axios, zustand, dayjs, vite.
- [ ] Add `keycloak-js` and `@react-keycloak/web`.
- [ ] `vite.config.ts` with proxy `/tickora → http://localhost:5100`.
- [ ] Copy theme tokens, `themeStore`, `sessionStore`, `index.css` from `rag-poc/frontend/src/`.
- [ ] `src/TickoraApp.tsx` — minimal AntD `Layout` with sider + header, "Hello Tickora" content. Theme toggle works.
- [ ] `npm run dev` boots on 5173.

### 0.5 CI

- [ ] GitHub Actions: `lint` (`make lint`), `test-unit`, `test-integration`, `frontend build`, `pip-audit`, `npm audit`. Fail on critical.

**Gate:** the empty app starts, healthcheck passes, the empty SPA loads, CI is green.

---

## Phase 1 — IAM module (3–5 days)

Authentication and authorization arrive before any ticketing code. Every later endpoint is gated by IAM.

### 1.1 Keycloak realm bootstrap

- [ ] `scripts/keycloak_bootstrap.py` — uses `python-keycloak` to provision realm `tickora`, client `tickora-api` (confidential, service account on), client `tickora-spa` (public, PKCE), realm roles from BRD §9.1, top-level groups `/tickora/sectors/<sN>/{members,chiefs}` for `s1..s10`. Idempotent.
- [ ] Document the bootstrap flow in `docs/keycloak_setup.md`.

### 1.2 Token verification

- [ ] `iam/token_verifier.py` — fetch JWKS, cache in-memory + Redis, verify signature/iss/aud/exp/nbf, return claims. Rotation-aware (refresh JWKS on `kid` miss).
- [ ] Unit tests with locally-signed JWTs (jose).

### 1.3 Principal + decorators

- [ ] `iam/principal.py` — `Principal` dataclass: `user_id`, `keycloak_subject`, `username`, `email`, `global_roles: set[str]`, `sector_memberships: list[(sector_code, role)]`, `is_admin`, `is_auditor`, `is_distributor`, `beneficiary_user`.
- [ ] `iam/decorators.py` — `@require_authenticated` (401 if no/invalid token), `@require_role(*roles)` (403 if missing), `@require_principal` (alias). Adds `principal=...` to handler kwargs.
- [ ] Wire into a smoke endpoint: `GET /api/me` returns the current principal as JSON.

### 1.4 User provisioning

- [ ] `iam/models.py` — `User` ORM (BRD §16.1).
- [ ] `iam/service.py` — `get_or_create_user_from_token(claims) -> User` upserts on `keycloak_subject`. Mirrors token's email/given_name/family_name.
- [ ] First Alembic migration: `users` table.
- [ ] On every authenticated request, hydrate `User` and attach to `Principal`. Cache the row in Redis 60 s.

### 1.5 RBAC primitives

- [ ] `iam/rbac.py` — pure predicate functions: `can_view_ticket`, `can_modify_ticket`, `can_see_private_comments`, `can_assign_to_user`, `can_close`, `can_reopen`, `can_administer`. Each takes `(principal, ticket_or_comment, [target])` and returns bool.
- [ ] **Required:** unit tests covering BRD §9.4 matrix line-by-line. Each row of the matrix is a parametrized test case.

### 1.6 Keycloak Admin extension surface

- [ ] `iam/keycloak_admin.py` — wrapper around `python-keycloak`'s admin client (service-account auth). Methods: `list_users`, `get_user`, `set_user_enabled`, `list_groups`, `add_user_to_group`, `remove_user_from_group`, `list_realm_roles`, `assign_realm_role`.
- [ ] Group sync: when admin edits `sector_memberships` in Tickora UI, IAM mirrors the change to Keycloak groups.

### 1.7 Frontend auth

- [ ] `frontend/src/auth/keycloak.ts` — singleton `Keycloak` instance with PKCE. Refresh 30 s before expiry.
- [ ] `KeycloakProvider` wraps `<TickoraApp>`. Until `initialized && authenticated`, render a splash.
- [ ] axios interceptor injects `Authorization: Bearer ${kc.token}`.
- [ ] `<RequireRole roles={[...]}>` route wrapper.
- [ ] Header shows username + logout button (`kc.logout()`).

**Gate:** logging in via Keycloak lands on the SPA, `GET /api/me` returns the right principal with the right roles. RBAC unit tests cover the BRD §9.4 matrix at 100%.

---

## Phase 2 — Ticketing data model + create/list/get (5–7 days)

The minimum viable ticketing slice: a beneficiary creates a ticket; a member sees it.

### 2.1 ORM models

- [ ] `ticketing/models.py` — every table from BRD §16. SQLAlchemy 2.x `Mapped[...]` style. Enums for `status`, `priority`, `beneficiary_type`, `comment_visibility`, `membership_role`. Composite indexes from §17.
- [ ] Alembic migration generating all tables + indexes. Hand-edit to add `tsvector` column, GIN index, trigger function `tickets_search_vector_update()`.
- [ ] Partition `audit_events` monthly: declarative table + initial partition + script to roll new partitions (called by `sla_checker` daily).

### 2.2 Beneficiary handling

- [ ] `ticketing/service/beneficiary_service.py` — `get_or_create_for_principal(principal)` (internal), `create_external(payload)` (external). External creation captures source IP, user-agent, `correlation_id`.

### 2.3 Ticket creation

- [ ] `ticketing/service/ticket_service.py` — `create(principal, payload)`. Pydantic validates payload (different schemas per `beneficiary_type`). Generates `ticket_code` via Postgres function `next_ticket_code()` (sequence + format).
- [ ] Sector suggestion (MVP-1 manual via `suggested_sector_code`); auto-suggest deferred to Phase 7.
- [ ] Audit `TICKET_CREATED`. Publish `notify_distributors` task (handler stub for now).

### 2.4 Ticket list and detail

- [ ] `ticket_service.list(principal, filters, cursor, limit)` — builds the visibility predicate from §7, applies filters (BRD §12.3 subset for MVP-1: status, sector, assignee, priority, category, beneficiary_type, created_at range, ticket_code, text search).
- [ ] `ticket_service.get(principal, ticket_id)` — visibility check; 404 not 403 for unauthorized read (don't leak existence).
- [ ] Cursor pagination on `(created_at desc, id desc)`.

### 2.5 API endpoints

- [ ] Add to `maps/endpoint.json`:
  - `POST   /api/tickets` (`tickets.create`)
  - `GET    /api/tickets` (`tickets.list`)
  - `GET    /api/tickets/<ticket_id>` (`tickets.get`)
- [ ] `src/api/tickets.py` — thin handlers, Pydantic in/out, calls service, maps errors.
- [ ] Permission-aware out-serializer scrubs fields the principal can't see (no `requester_email` for unrelated members, etc.).

### 2.6 Tests

- [ ] Unit: ticket_code generation, payload validation, pagination cursor encoding.
- [ ] Integration (testcontainers Postgres):
  - external creates → 201 with `ticket_code`.
  - internal creates → links to user/beneficiary correctly.
  - sector member of `sN` lists tickets → only sees tickets visible per RBAC.
  - admin lists → sees all.
  - beneficiary lists → sees only their own.
  - non-member tries `GET /api/tickets/<other-sector-ticket>` → 404.
  - Audit row written for each create.

### 2.7 Frontend

- [ ] `api/tickets.ts` — `createTicket`, `listTickets`, `getTicket`. Axios + types.
- [ ] `hooks/useTickets.ts`, `hooks/useTicket.ts` (TanStack Query).
- [ ] Pages: `pages/CreateTicket.tsx` (forms diverge by beneficiary_type), `pages/TicketsList.tsx`, `pages/TicketDetails.tsx`.
- [ ] Components: `TicketTable`, `TicketStatusTag`, `PriorityTag`, `BeneficiaryTypeTag`, `PageHeader`.
- [ ] Routing: `/create`, `/tickets`, `/tickets/:id`. `<RequireRole>` wraps as needed.

**Gate:** an internal user can log in, create a ticket, see it in their list, open it. An admin sees all tickets. A foreign sector member can't see it. Audit rows exist.

---

## Phase 3 — Workflow (5–7 days)

The heart of the BRD: distribution, assignment, transitions, with concurrency safety.

### 3.1 State machine

- [ ] `ticketing/state_machine.py` — declarative table `STATE_TRANSITIONS = {(from_status, action): (to_status, predicate)}` covering BRD §11.3.
- [ ] `ticketing/events.py` — event constants used in audit + tasks.

### 3.2 Workflow service

- [ ] `ticketing/service/workflow_service.py`:
  - `assign_sector(principal, ticket_id, sector_code, reason)` — distributor or admin; updates `current_sector_id`, sets `sector_assigned_at`, transitions `pending → assigned_to_sector`, history + audit, fanout `notify_sector`.
  - `assign_to_me(principal, ticket_id)` — **atomic UPDATE** from architecture §6. On miss → 409. Audit `TICKET_ASSIGNED_TO_USER`.
  - `assign_to_user(principal, ticket_id, target_user_id)` — chief/admin only; same atomic guard; sets `assignee_user_id` to target.
  - `reassign(principal, ticket_id, target_user_id, reason)` — chief/admin; writes both unassign and assign audit rows.
  - `mark_done(principal, ticket_id, resolution)` — assignee only.
  - `close(principal, ticket_id, feedback?)` — beneficiary or admin.
  - `reopen(principal, ticket_id, reason)` — beneficiary or admin; sets `assignee_user_id = last_active_assignee_user_id`, `status = 'reopened'`, `reopened_count += 1`.
  - `cancel(principal, ticket_id, reason)`, `mark_duplicate(principal, ticket_id, target_id, reason)` — distributor/chief/admin.
  - `change_priority(principal, ticket_id, priority, reason)`, `change_status(...)` — guarded by RBAC + state machine.
- [ ] Each writes the appropriate history row (`ticket_status_history` / `ticket_sector_history` / `ticket_assignment_history`) **and** an `audit_events` row in the same transaction.
- [ ] All transitions publish a notification task (handler stubs in Phase 5).

### 3.3 API endpoints

Add the BRD §18.2 actions to `maps/endpoint.json` and `src/api/tickets.py`:

```
POST /api/tickets/{id}/assign-sector
POST /api/tickets/{id}/assign-to-me
POST /api/tickets/{id}/assign-to-user
POST /api/tickets/{id}/reassign
POST /api/tickets/{id}/mark-done
POST /api/tickets/{id}/close
POST /api/tickets/{id}/reopen
POST /api/tickets/{id}/cancel
POST /api/tickets/{id}/mark-duplicate
POST /api/tickets/{id}/change-priority
POST /api/tickets/{id}/change-status
```

### 3.4 Tests

- [ ] Unit: state machine table coverage; every defined transition has a test, every undefined transition raises.
- [ ] Integration:
  - Concurrent `assign-to-me` (gevent: spawn 50 greenlets, only one wins, others get 409).
  - Sector member can't modify a ticket assigned to a peer (403, audit `ACCESS_DENIED`).
  - Chief can reassign within their sector but not across sectors.
  - Beneficiary can `close` their own ticket but not others.
  - `reopen` lands the ticket back on `last_active_assignee_user_id`, increments count.
  - All BRD §24 acceptance criteria, encoded as Gherkin via `pytest-bdd` in `tests/integration/acceptance/`.

### 3.5 Frontend

- [ ] `api/tickets.ts` — workflow action methods.
- [ ] Components: `AssignToMeButton` (with optimistic update + 409 toast → refetch), `ReassignModal`, `CloseTicketModal`, `ReopenTicketModal`, `ChangePriorityMenu`, `ChangeStatusMenu`, `StatusTimeline`.
- [ ] Action visibility on `TicketDetails` is RBAC-driven from a `/api/tickets/{id}/permissions` endpoint that returns the allowed actions for the principal — no client-side rule duplication.

**Gate:** the BRD §24 acceptance scenarios pass end-to-end. The concurrency test goes 50/1.

---

## Phase 4 — Comments + attachments + audit explorer (4–6 days)

### 4.1 Comments

- [ ] `comment_service.py` — `list(principal, ticket_id)` filters by visibility server-side; `create(principal, ticket_id, body, visibility, parent_comment_id?)`; `edit(principal, comment_id, body)` (within edit window, audit-logged); `delete(principal, comment_id)` (logical, audit-logged).
- [ ] Mention parsing: `@username` → in-app notification to that user (Phase 5).
- [ ] System comments (`comment_type = 'system'`) auto-created on transitions for the timeline.
- [ ] Endpoints `/api/tickets/{id}/comments` (GET/POST), `/api/comments/{id}` (PATCH/DELETE).
- [ ] Tests: external beneficiary cannot see `private`; member without sector access cannot see; admin sees all; auditor sees per policy flag.

### 4.2 Attachments

- [ ] MinIO client wrapper in `core/object_storage.py` (boto3, S3 v4 sigv).
- [ ] `attachment_service.py`:
  - `request_upload_url(principal, ticket_id, filename, content_type, size)` — validates extension/MIME/size, returns presigned PUT URL + storage key.
  - `register(principal, ticket_id, storage_key, file_name, size, checksum, visibility)` — verifies the object exists in MinIO, persists metadata.
  - `list(principal, ticket_id)` — visibility-filtered.
  - `download(principal, attachment_id)` — authorize, return 302 with 60-s presigned GET URL. Audit `ATTACHMENT_DOWNLOADED`.
  - `delete(principal, attachment_id)` — logical, audit-logged.
- [ ] Endpoints from BRD §18.4. Plus `/api/tickets/{id}/attachments/upload-url`.
- [ ] AV scan stub returns clean. Field `is_scanned`, `scan_result` exposed.

### 4.3 Audit explorer

- [ ] `audit_service.py` — `list(principal, filters)`, `get_for_ticket(principal, ticket_id)`, `get_for_user(principal, user_id)`. Auditor + admin only for global, sector chiefs for their sector.
- [ ] Endpoints `GET /api/audit`, `GET /api/tickets/{id}/audit`, `GET /api/users/{id}/audit`.
- [ ] Frontend: `AuditDrawer` (per-ticket), `pages/AuditExplorer.tsx` for auditor/admin with filter form (action, actor, entity, date range, correlation_id).

### 4.4 Frontend

- [ ] `CommentBox` with public/private toggle (default `private` for internal users on internal tickets, always disabled for beneficiaries on their own tickets), `PrivateCommentBadge`, `CommentTimeline`.
- [ ] `AttachmentUploader` (chunked, AntD `Upload` + custom request hitting presigned URL), `AttachmentList`, `AttachmentDownloadButton`.
- [ ] `StatusTimeline` extended to merge comments, status/sector/assignment history, and SLA events into a single chronological view (BRD §13.2).

**Gate:** comments and attachments work end-to-end. The audit explorer answers "who did what to ticket X". Beneficiaries provably cannot see private comments (test + manual).

---

## Phase 5 — Notifications + SLA + dashboards (5–7 days)

### 5.1 Tasking infrastructure

- [ ] `tasking/producer.py`, `tasking/consumer.py`, `tasking/registry.py`, `tasking/recovery.py` — port the `rag-poc` patterns. Two topics: `tickora_fast`, `tickora_slow`.
- [ ] `worker.py` entrypoint — imports `ticketing` so handlers self-register, then runs the consumer. Single image, different command.
- [ ] On startup, `recovery.py` requeues notifications/exports stuck in `processing`.

### 5.2 Notification handlers

- [ ] `ticketing/notifications.py`:
  - `notify_distributors` — on ticket create, in-app to all `tickora_distributor` users + email digest.
  - `notify_sector` — on sector assign, in-app to all members + chiefs of `current_sector_id`.
  - `notify_assignee` — on assign-to-user.
  - `notify_beneficiary` — on done, on public comment, on reopen confirmation.
  - `notify_mention` — on `@user` in private comment (only if user has access to ticket).
  - Channel matrix per BRD §12.7. Idempotency key `(ticket_id, event, recipient, dedup_window=5min)`.
- [ ] In-app: insert into `notifications` table.
- [ ] SSE: `/api/notifications/stream` — gevent SSE keeping a Redis pubsub subscription per user.
- [ ] Email: SMTP via `aiosmtplib`-style sync wrapper (gevent-friendly). Templates in `ticketing/templates/`.

### 5.3 SLA

- [ ] `sla_service.py` — on ticket create / priority change / status change, evaluate active `sla_policies` and write `sla_due_at`, `sla_status`.
- [ ] `sla_checker.py` entrypoint — leader-elected via Redis lock. Runs every 60 s:
  - tickets with `sla_due_at` in next 30 min → `sla_status = approaching_breach` + notify.
  - past due → `sla_status = breached` + notify chief + escalate per policy.
  - increment `sla_breaches_total`.
- [ ] Endpoints to manage policies (`/api/admin/sla-policies` — admin only).

### 5.4 Dashboards

- [ ] `dashboard_service.py` — KPI queries from BRD §14.5. Wherever a query crosses 200 ms, materialize:
  - `mv_dashboard_global_kpis` refreshed every 5 min.
  - `mv_dashboard_sector_kpis` refreshed every 5 min, per sector_id.
  - Refresh job runs as a `tasking` task scheduled by `sla_checker`.
- [ ] Endpoints from BRD §18.7. RBAC scoping: members see their own, chiefs see their sectors, admins see all.

### 5.5 Frontend

- [ ] `useNotificationsStream` hook (SSE) → invalidates relevant TanStack queries on ticket events.
- [ ] In-app notification dropdown in header with unread count.
- [ ] Pages: `pages/DashboardGlobal.tsx` (admin), `pages/DashboardSector.tsx` (chief), `pages/DashboardMember.tsx` (member), `pages/DashboardBeneficiary.tsx`. KPI cards via `@ant-design/plots` and `recharts`.
- [ ] `SlaIndicator` (within SLA / approaching / breached) on ticket row + detail.

**Gate:** state changes drive notifications across all enabled channels; SLA breach is detected within 90 s of due time; dashboards render under 1.5 s p95.

---

## Phase 6 — Admin module + sectors + queues (4–5 days)

### 6.1 Sector administration

- [ ] `sector_service.py` — CRUD; activate/deactivate; list memberships. Edits to memberships sync to Keycloak groups via `iam.keycloak_admin`.
- [ ] Endpoints from BRD §18.6.

### 6.2 User administration

- [ ] `/api/admin/users` — list (paginated, search), get, patch (enable/disable, role assignment via Keycloak admin client). All audit-logged.

### 6.3 Nomenclature management

- [ ] Categories, priorities, ticket types — small ORM tables with admin CRUD endpoints. Cached in Redis 5 min. Used by ticket creation forms.
- [ ] SLA policies admin (links to Phase 5).

### 6.4 Role-specific queues

Each role's UI lands on a tailored queue (BRD §12.2). Backend filters are already there; this is mostly frontend pages + saved-filter shortcuts:

- Distributor: `Distribution Queue`, `Recently Distributed`, `Reassignment Candidates`, `Invalid/Duplicate Review`.
- Member: `Sector Queue`, `Assigned to Me`, `Waiting for User`, `Done by Me`, `Reopened to Me`.
- Chief: `Sector Overview`, `Unassigned in Sector`, `Assigned`, `Blocked`, `SLA Breaches`, `Team Workload`.
- Admin: `All Tickets`, `All SLA Breaches`, `Audit Explorer`, `System Overview`.

**Gate:** an admin can manage sectors, users, and nomenclature end-to-end via the UI; changes mirror to Keycloak; every queue shows the right rows for the right role.

---

## Phase 7 — Modern features (MVP-3, 5–8 days)

Implement the BRD §13 backlog after MVP-1/2 is solid.

- [ ] **Full-text search** on `tickets.search_vector` exposed via `q=` filter; ranked output.
- [ ] **Auto-suggest sector** — rules engine in `ticketing/auto_suggest.py` (IP CIDR rules, category rules, keyword rules), all admin-configurable.
- [ ] **Duplicate detection** — pgvector or trigram similarity on title+body within 7 days; surfaced as suggestions in the distributor UI.
- [ ] **Parent/child tickets** — uses `ticket_links` (`link_type = 'parent'/'child'`).
- [ ] **Watchers/followers** — new table `ticket_watchers`; receive notifications without being assignee.
- [ ] **Mentions** in private comments (Phase 5 hook → richer UI).
- [ ] **Templates** — admin-managed snippet library inserted into `CommentBox`.
- [ ] **Beneficiary feedback** — modal on close, fields per §13.9, persisted on `tickets.feedback JSONB`.
- [ ] **Auto-escalation** — rules-driven, runs in `sla_checker`.

---

## Phase 8 — Hardening (3–5 days)

- [ ] Load test with `k6`: 300 VUs, mixed scenarios (read-heavy + create + assign-to-me storm). Confirm performance budget.
- [ ] Soak test: 24 h at 100 VUs; check for memory leaks, connection leaks, audit table growth, partition rotation.
- [ ] Security review: `bandit`, `pip-audit`, `npm audit`, ZAP baseline, manual IDOR sweep across all `/api/.../{id}` routes.
- [ ] Backups: `pg_dump` + WAL archiving validated by a restore drill.
- [ ] Disaster recovery runbook in `docs/runbook.md`.
- [ ] Production observability: Loki + Grafana dashboards mirroring BRD §21.2 metrics.
- [ ] Documentation pass: `docs/api_reference.md` (auto-generated from Pydantic models + maps), `docs/rbac_matrix.md` (the BRD §9.4 matrix as ground truth, generated by a test that diffs it against `iam.rbac`).

---

## Cross-cutting checklists

These apply to every phase, every PR.

### Definition of Done

- [ ] Code compiles, tests pass, lint clean.
- [ ] Every state-changing endpoint writes the matching `audit_events` row.
- [ ] Every endpoint has at least one positive RBAC test and one negative RBAC test.
- [ ] No `print()`, no debug `pdb`, no commented-out code.
- [ ] No new `INFO+` log lines without `correlation_id`.
- [ ] If a Postgres query is added on a hot path, an index exists for it (or an explicit decision to seq-scan, justified in the PR).
- [ ] Pydantic input models reject extra fields.
- [ ] Frontend: dark and light themes both verified; loading/empty/error states present.

### Test strategy

- **Unit (`tests/unit/`)** — pure logic: RBAC predicates, state machine, ticket_code, pagination cursor, payload validation.
- **Integration (`tests/integration/`)** — testcontainers Postgres + Redis. One transaction-per-test using `pytest-postgresql`-style fixtures or rolling savepoints. Mock Keycloak with locally-signed JWTs.
- **Acceptance (`tests/integration/acceptance/`)** — `pytest-bdd` for the BRD §24 scenarios, kept under version control as Gherkin.
- **E2E (`tests/e2e/`)** — Playwright smoke for the golden paths (login → create → see → admin sees all). Runs against `make up` stack in CI.
- **Load (`tests/load/`)** — k6 scripts for §22.1 budgets.

### Observability requirements per phase

By the end of Phase 5, every endpoint emits:

- `http_requests_total{route,method,status}`.
- `http_request_duration_seconds{route,method}`.
- A trace span per service call.
- A JSON log line with `user_id`, `correlation_id`, `duration_ms`.

Every Kafka task emits:

- `tasks_published_total{type}`, `tasks_consumed_total{type,result}`.
- `task_duration_seconds{type}`.
- A trace span linked to the originating request via `correlation_id` baggage.

### Risk register (live)

| Risk | Mitigation | Phase |
|---|---|---|
| Private comment leak | server-side filter + serializer scrub + integration test on every list path | 4 |
| IDOR on `{id}` routes | visibility predicate baked into queries; auto-test sweep in CI | 2,3,4 |
| Concurrent `assign-to-me` | atomic UPDATE; concurrency test in CI | 3 |
| Audit table growth | monthly partitioning; archival script; retention setting | 2 (schema), 8 (retention) |
| Dashboard slowness | indexes from §17 + materialized views + Redis fragment cache | 5 |
| Keycloak group drift | bidirectional sync from admin UI; nightly reconciliation job | 6 |
| Token cache poisoning | sign cache key with JWKS `kid`; invalidate on rotation | 1 |
| Email backpressure | tasking semaphore + retries with backoff in worker | 5 |

---

## Suggested team and timeline

A 3-engineer team (1 backend lead, 1 backend, 1 frontend) plus part-time SRE and designer:

| Phase | Calendar weeks | Cumulative |
|---|---:|---:|
| 0. Bootstrap | 0.5 | 0.5 |
| 1. IAM | 1 | 1.5 |
| 2. Tickets create/list/get | 1.5 | 3 |
| 3. Workflow | 1.5 | 4.5 |
| 4. Comments + attachments + audit | 1.5 | 6 |
| 5. Notifications + SLA + dashboards | 1.5 | 7.5 |
| 6. Admin module | 1 | 8.5 |
| 7. Modern features (MVP-3) | 2 | 10.5 |
| 8. Hardening | 1 | 11.5 |

**MVP-1 (BRD §25.1)** is delivered at the end of Phase 4 (~6 weeks).
**MVP-2 (BRD §25.2)** is delivered at the end of Phase 6 (~8.5 weeks).
**MVP-3 (BRD §25.3)** is delivered at the end of Phase 8 (~11.5 weeks).

---

## First-week concrete action list

1. `mkdir tickora && cd tickora` — apply the Phase 0 layout.
2. Copy the QF wheel and `Dockerfile` from `rag-poc`. Strip RAG deps from `requirements.txt`.
3. Author `docker-compose.yml` (postgres, redis, kafka, minio, keycloak, jaeger).
4. Stand up `main.py` + `health` endpoint.
5. Bootstrap Keycloak realm via `scripts/keycloak_bootstrap.py`.
6. Build `iam/token_verifier.py` + `iam/principal.py` + `@require_authenticated`.
7. `GET /api/me` works end-to-end behind Keycloak login.
8. Frontend skeleton with `keycloak-js`, theme store, AntD shell.
9. CI green.
10. Open the Phase 1 milestone with the IAM tickets.
