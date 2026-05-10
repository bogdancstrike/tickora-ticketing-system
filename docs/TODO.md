# Tickora — Implementation Progress

Live tracker of what's done and what's next. Phases follow `docs/implementation_plan.md`.

Legend: `[x]` done · `[~]` partial · `[ ]` pending

---

## Phase 0 — Bootstrap ✅

- [x] Repo skeleton (src/, frontend/, tests/, scripts/, maps/, migrations/, docs/, dist/)
- [x] `requirements.txt`, `Dockerfile`, `Makefile`, `.env.example`, `.gitignore`, README, CLAUDE.md
- [x] QF wheel copied to `dist/`
- [x] `src/core/` — config, db, logging, correlation, errors, tracing, pagination, redis_client
- [x] `main.py` — gevent monkey-patch, FrameworkApp boot, error/correlation hooks
- [x] `src/api/health.py` (`/health`, `/liveness`, `/readiness`) and `maps/endpoint.json`
- [x] `docker-compose.yml` — postgres, keycloak (+ keycloak-db), redis, kafka (KRaft), minio, jaeger
- [x] Frontend skeleton: package.json, vite/tsconfig, index.html, main.tsx with `<ReactKeycloakProvider>`,
      TickoraApp shell (sider+header+routes), theme/session stores, axios client, RequireRole wrapper
- [x] `frontend/.env` + `frontend/.env.example` — VITE_* env vars for port, API base URL, Keycloak config
- [x] `frontend/vite.config.ts` — reads port and proxy target from `.env` via `loadEnv`
- [x] Makefile updated to use `.venv` Python for all backend targets (`install`, `backend`, `migrate`, `test`, etc.)
- [ ] CI: GitHub Actions for lint, unit, integration, frontend build, pip-audit, npm audit

---

## Phase 1 — IAM ✅ (live integration test deferred)

- [x] `src/iam/principal.py` — `Principal`, `SectorMembership`, role constants
- [x] `src/iam/token_verifier.py` — JWKS fetch+cache, JWT verify, Redis cache
- [x] `src/iam/service.py` — user upsert, principal hydration, `/tickora/sectors/<sN>/...` group parser
- [~] Hierarchical group semantics: `/tickora` → full platform access; parent sector group
      (for example `/tickora/sectors/s10` or shorthand `sector10`) → effective chief+member
      sector access. Backend parser work is in progress; profile/API polish still needs verification.
- [x] `src/iam/decorators.py` — `@require_authenticated`, `@require_role`, `@require_any`
      (decorators return `(dict, status)` tuples — flask_restx overrides Flask errorhandler)
- [x] `src/iam/rbac.py` — pure predicates: view/modify/assign/close/reopen/comments/admin/dashboard
- [x] `src/iam/keycloak_admin.py` — admin REST wrapper (users, groups, roles)
- [x] `src/iam/models.py` — `User` ORM + Alembic migration `0001_users`
- [x] `scripts/keycloak_bootstrap.py` — idempotent realm/clients/roles/groups setup (bugfix: graceful 404 on `get_group_by_path`)
- [x] `src/api/me.py` registered as `GET /api/me`
- [x] **Tests:** RBAC matrix line-by-line + Principal helpers (35 unit tests)
- [x] **Live stack verified:** all services healthy, `/api/me` and `/api/tickets` return 401 without JWT, Keycloak realm `tickora` bootstrapped
- [ ] Integration: `/api/me` with locally-signed JWT against testcontainers
- [ ] Live: log in via SPA → land on dashboard → token refresh works

---

## Phase 2 — Ticketing data model + create/list/get ✅ (UI deferred)

- [x] ORM (BRD §16): `Sector`, `SectorMembership`, `Beneficiary`, `Ticket`,
      `TicketComment`, `TicketAttachment`, `TicketStatusHistory`,
      `TicketSectorHistory`, `TicketAssignmentHistory`, `AuditEvent`,
      `Notification`, `SlaPolicy`, `TicketLink`
- [x] Alembic migration `0002_ticketing` with all indexes from BRD §17,
      partial indexes (`active_by_sector`, `unassigned`, `beneficiary_active`),
      `tsvector` + trigger + GIN
- [x] `ticket_code` Postgres sequence (`ticket_code_<year>` + nextval)
- [x] `ticketing/service/beneficiary_service.py` — internal upsert, external create
- [x] `ticketing/service/ticket_service.py` — create/list/get with visibility
      predicate baked into SQL; cursor pagination; sector-code hydration
- [x] `ticketing/service/audit_service.py` — single-entry-point ledger
- [x] Pydantic schemas (`schemas.py`) + permission-aware serializers (`serializers.py`)
- [x] API: `POST /api/tickets`, `GET /api/tickets`, `GET /api/tickets/{id}`
- [x] Frontend: tickets list, ticket details, create form without distributor-owned triage metadata
- [ ] Integration tests (testcontainers Postgres)

---

## Phase 3 — Workflow ✅

- [x] `state_machine.py` — declarative `TRANSITIONS` table, `target_status()`, `is_valid()`
- [x] `workflow_service.py`:
      assign_sector / assign_to_me (atomic UPDATE) / assign_to_user / reassign /
      mark_done / close / reopen / cancel / change_priority — each writes
      history + audit in the same transaction
- [x] All BRD §18.2 endpoints registered in `maps/endpoint.json`
- [x] **Tests:** state-machine table coverage (26 tests)
- [x] Integration: concurrent `assign_to_me` (50 greenlets, exactly one wins)
- [x] Acceptance: BRD §24 scenarios via pytest-bdd
- [x] Frontend: action buttons + RBAC-driven visibility

---

## Phase 4 — Comments + attachments + audit explorer ✅

- [x] Comment service + endpoints (visibility-filtered)
- [x] MinIO client + presigned PUT/GET URLs
- [x] Attachment service + endpoints (upload-url, register, list, download, delete)
- [x] Audit endpoints (`/api/audit`, `/api/tickets/{id}/audit`, `/api/users/{id}/audit`)
- [x] Frontend: `CommentBox`, `AttachmentUploader`, ticket audit tab, `AuditExplorer`
- [x] Distributor review flow: `POST /api/tickets/{id}/review` sets sector, assignee, priority, category, type, and private review commentary
- [x] Dynamic form options: database-backed sectors, assignable users, priorities, categories, and types
- [x] Enhanced audit UI with object diff view and request details

## Phase 5 — Notifications + dashboards ✅

- [x] Tasking infrastructure (Kafka producer/consumer + registry)
- [x] Notification handlers (in-app, email stub, SSE)
- [x] Participant-aware task notifications: requester/beneficiary + all assigned users are notified
      for visible task events; private comment notifications stay staff/assignee-only and do not
      notify beneficiaries/requesters.
- [x] Comment edit/delete notification publishing added, preserving public/private visibility rules.
- [x] SSE `/api/notifications/stream` for real-time delivery
- [x] SLA service + background checker process
- [x] Dashboard service; headline KPIs now use live aggregate queries instead of stale materialized
      view reads.
- [x] Dashboard `closed_today` counts closed tickets with `closed_at` and falls back to `updated_at`
      for legacy/manual rows where status is `closed` but `closed_at` is missing.
- [x] Dashboard query invalidation from ticket workflow/review actions so UI counters refresh after changes.
- [~] Materialized views (`mv_dashboard_global_kpis`, `mv_dashboard_sector_kpis`) still exist in
      migrations, but runtime dashboard KPI reads no longer depend on them.
- [x] Frontend dashboards with **Apache ECharts**
- [x] Header notification dropdown with unread badge
- [x] Integration coverage added for live dashboard KPIs and notification recipient visibility
      (`test_dashboard_service.py`, `test_notifications.py`); local execution currently blocked
      when `testcontainers` is not installed.

## Phase 6 — Admin module

- [x] Admin backend endpoints for overview dashboards, users, sectors, memberships,
      group hierarchy, metadata-key nomenclature, and SLA policies; membership
      and realm-role changes audit-log and best-effort sync to Keycloak.
- [x] Admin page replaces placeholder with operational dashboards, users/roles
      management, sector CRUD, group hierarchy view, membership ledger,
      metadata-key configuration, and System hardening view.
- [x] Admin access is restricted to exact `/tickora` root-group members; backend principal
      hydration falls back to Keycloak group lookup when token group claims are missing.
- [~] Role-specific queue UIs: distributor `Review Tickets` implemented (with premature closure); remaining role queues pending
- [x] Review queue is its own dedicated page (`/review/:ticketId`), not a drawer
- [x] Review queue list is split into not-yet-reviewed pending tickets and already-reviewed
      tickets routed to sectors.
- [x] Reviewer restriction: distributors route to a sector; only chief/admin pick the operator
- [x] Inline status changer (TicketsPage table + ticket detail) with double confirmation
- [x] Unified `Assign` dropdown + self-only `Unassign me`; targeted user removal uses
      `remove_assignee` rather than the broad queue-level unassign action.
- [x] Configurable metadata key catalogue (`metadata_key_definitions`) with per-key option lists
- [x] Add metadata UI in review (selectable values when key has options, free text otherwise)
- [x] Audit explorer: per-column filters/sort, quick search, "See timeline" with D3 evolution chart
- [~] Multi-assignment API + model support: `ticket_sectors` / `ticket_assignees`, serializer arrays
      (`sector_codes`, `assignee_user_ids`), endpoint map entries, service helpers, and frontend client
      methods are present; remaining UI polish and regression testing are still in progress.
- [x] Profile page: chief sees a force-graph of their sector members
- [x] Profile page: "Teams I lead" redesign with maximize/minimize fullscreen view is in progress.
- [x] Profile page access tree for hierarchical RBAC is planned/in progress so users can see the
      sectors and members implied by their group tree.
- [x] Reusable common components: StatusTag, PriorityTag, AuditTimeline, format helpers, StatusChanger

## Phase 7 — Modern features (MVP-3)

- [~] FTS surface, auto-suggest sector, duplicate detection, parent/child links,
      watchers, mentions, attachements (via Minio, keep in mind the RBAC and who can see what), templates, beneficiary feedback, auto-escalation

## Phase 8 — Hardening

- [ ] Load (k6), soak, security review, backups+PITR, runbooks, prod observability,
      audit_events partitioning + retention
- [x] First-pass security review (`docs/SECURITY_REVIEW.md`) — RBAC strengths,
      defence-in-depth gaps, performance hotspots, hardening backlog
- [x] **Refresh of security review (2026-05-09)** — adds the dashboards/widgets
      RBAC analysis (Section D), documents the self-assignment policy for
      comments/status, and lists the perf changes below.
- [x] `assignable_users` endpoint refuses non-admins without an explicit sector
      and rejects sectors the caller doesn't belong to
- [x] Phase 8 hardening index migration (`0007_phase8_hardening_indexes`) adds
      hot-path indexes for admin queues, SLA breach views, audit recency,
      notifications, active memberships, metadata keys, and trigram lookup.
- [x] **Phase 9 perf indexes** (`9a1f3e0c2d10_phase9_perf_indexes`) — partial
      indexes on `(status|priority|creator|sector, created_at desc)` for the
      million-row TicketsPage path, plus joins for `ticket_sectors` and
      `ticket_assignees`.
- [x] **`/api/monitor/overview` 60-s Redis cache** keyed by visibility class
      (admin/auditor share, sector users keyed by sectors, others by user_id);
      eliminates repeat-load cost on 1M+ ticket datasets.
- [x] **`/api/tickets` reltuples fast-path** — admin/auditor with no narrowing
      filter uses `pg_class.reltuples` instead of `COUNT(*)` over a 1M-row
      visibility subquery.
- [x] **Self-assignment gate** — `can_post_public_comment`,
      `can_post_private_comment`, `can_drive_status`, `can_mark_done` now
      require the active-assignee link (admin override + beneficiary side
      preserved). Bystander chiefs/members must self-assign first.
- [x] **Active-session presence** (`src/core/session_tracker`) — admin
      overview exposes an `active_sessions` KPI driven by Redis presence
      keys with a 5-minute TTL.

## Phase 9 - Testing
- [~] Unit tests for all services — RBAC + state machine + pagination + auth
      cache covered; ticket/workflow/comment/attachment/sla/dashboard/audit
      service unit suites pending.
- [~] Integration tests for all services — phase 4 services, workflow
      acceptance, workflow concurrency, RBAC, admin, dashboard, notifications,
      bottleneck analysis, stale tickets, system settings, monitor refinements
      covered. Comment/attachment/SLA service-level integration still pending.
- [x] Admin service integration coverage for admin-only access, membership grant
      and hierarchy visibility, and SLA policy validation/creation.
- [ ] Acceptance tests for all services (only workflow today)
- [ ] End2End tests (Playwright UI smoke) for the golden-path flows
- [ ] Performance tests (k6) for `/api/tickets`, `/api/monitor/*`,
      `/api/admin/overview` against the 30M seed.
- [ ] Load tests (sustained 50 RPS, 200 concurrent)
- [ ] Security tests using the seeded role users (admin / auditor / distributor /
      chief.s10 / member.s10 / member.s2 / beneficiary / external.user) — assert
      403/404 across the full role × endpoint matrix.
- [ ] Chaos tests (Postgres restart, Redis blackout, Keycloak unreachable).


## Phase 10 - Internalization and Wrapping Up

- [x] add useful indices on often used columns from tables and generate seed.sql in scripts/ to create (with indices) tables and populate the DB
- [ ] add useful React Joyride info points that explain all functionalities of the module
- [ ] i18n (en + ro)
- [ ] write very comprehensive technical documentation in docs/technical_documentation.md with examples, mermaid charts, etc.
- [ ] write very comprehensive user documentation in docs/user_documentation.md with examples, use-cases, etc.

## Dead code / unused packages — survey (2026-05-09)

Frontend (verified by grepping `import` lines under `frontend/src/`):

- [ ] `recharts` — declared in `package.json` but never imported. Charts use
      `echarts-for-react`. Safe to drop after a fresh `npm install` + build.
- [ ] `@ant-design/plots` — declared but never imported. Same as above.

Backend (verified by grepping `import` under `src/`):

- [ ] `colorama` and `httpx` in `requirements.txt` — neither is imported in
      `src/`. Confirm scripts/tests don't pull them transitively before
      removal.

ORM / DB:

- [ ] `DashboardShare` model + table — orphan. Either implement sharing
      end-to-end (`dashboard_service`, an HTTP endpoint, RBAC gate) or drop
      the model + add a downgrade migration. See `SECURITY_REVIEW.md` §D.
- [ ] Materialized views `mv_dashboard_global_kpis` /
      `mv_dashboard_sector_kpis` — defined in `0003_dashboard_mvs` but no
      runtime code reads them now that monitor uses live aggregates. Drop
      in a follow-up migration.

## Open refactor backlog (2026-05-09)

The following are surfaced as user requests but not yet executed in this
branch — they are large, cross-cutting refactors and should be sequenced
carefully:

- [ ] Extract `src/audit/` as its own backend module (audit service, events,
      and api/audit endpoints currently live under `src/ticketing/`).
- [ ] Extract `src/common/` for utilities shared between modules
      (currently in `src/core/`).
- [ ] Refactor `src/tasking/` to own task lifecycle + status persistence so
      every async job has a queryable DB row. Currently `tasking/` only owns
      Kafka producer/consumer plumbing.
- [ ] Sweep dead code and unused dependencies on both backend and frontend
      (e.g. orphaned `DashboardShare` model, unused materialized views).
- [ ] Decide on `dashboard_shares` and `is_public` flag — implement sharing
      end-to-end or drop the unused surface (see `SECURITY_REVIEW.md` Section D).

---

## Test status

| Suite | Count | Status |
|---|--:|---|
| `tests/unit/test_rbac.py`           | 32 | ✅ |
| `tests/unit/test_principal.py`      |  3 | ✅ |
| `tests/unit/test_pagination.py`     |  4 | ✅ |
| `tests/unit/test_state_machine.py`  | 26 | ✅ |
| `tests/unit/test_auth_cache.py`     |  2 | ✅ |
| `tests/unit/test_me_api.py`         |  — | tracked separately |
| `tests/integration/test_phase4_services.py`        |  3 | ✅ |
| `tests/integration/test_workflow_acceptance.py`    |  3 | ✅ |
| `tests/integration/test_workflow_concurrency.py`   |  1 | ✅ |
| `tests/integration/test_rbac_new.py`               | 11 | ✅ |
| `tests/integration/test_admin_service.py`          |  5 | ✅ |
| `tests/integration/test_dashboard_service.py`      |  2 | 🟡 requires `testcontainers` locally |
| `tests/integration/test_notifications.py`          |  3 | 🟡 requires `testcontainers` locally |
| `tests/integration/test_dashboard_service_auto_config.py` | — | 🟡 requires testcontainers |
| `tests/integration/test_monitor_service_refinements.py`   | — | 🟡 requires testcontainers |
| `tests/integration/test_bottleneck_analysis.py`           | — | 🟡 requires testcontainers |
| `tests/integration/test_stale_tickets.py`                 | — | 🟡 requires testcontainers |
| `tests/integration/test_system_settings.py`               | — | 🟡 requires testcontainers |
| **Tracked total**                                          | **95+** | **🟡 broader local integration suite needs Docker/testcontainers** |

⚠️ The RBAC tightening (2026-05-09) for self-assignment may regress
acceptance tests where a chief drives status without first self-assigning.
Re-run `tests/integration/test_workflow_acceptance.py` and
`tests/integration/test_rbac_new.py` after the migration; update fixtures
if any test relied on chief-as-default-actor.
