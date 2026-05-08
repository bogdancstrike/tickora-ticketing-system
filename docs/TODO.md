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
- [x] Notification handlers (in-app, email stub, SSE) with idempotency
- [x] SSE `/api/notifications/stream` for real-time delivery
- [x] SLA service + background checker process
- [x] Dashboard service + materialized views (`mv_dashboard_global_kpis`, `mv_dashboard_sector_kpis`)
- [x] Frontend dashboards with **Apache ECharts**
- [x] Header notification dropdown with unread badge

## Phase 6 — Admin module

- [ ] All sectors/ Sector / User / Nomenclature CRUD endpoints; Keycloak group sync
- [~] Role-specific queue UIs: distributor `Review Tickets` implemented (with premature closure); remaining role queues pending
- [x] Review queue is its own dedicated page (`/review/:ticketId`), not a drawer
- [x] Reviewer restriction: distributors route to a sector; only chief/admin pick the operator
- [x] Inline status changer (TicketsPage table + ticket detail) with double confirmation
- [x] Unified `Assign` dropdown + Unassign (workflow_service.unassign + change_status endpoint)
- [x] Configurable metadata key catalogue (`metadata_key_definitions`) with per-key option lists
- [x] Add metadata UI in review (selectable values when key has options, free text otherwise)
- [x] Audit explorer: per-column filters/sort, quick search, "See graph" with D3 evolution chart
- [x] Profile page: chief sees a force-graph of their sector members
- [x] Reusable common components: StatusTag, PriorityTag, AuditTimeline, format helpers, StatusChanger

## Phase 7 — Modern features (MVP-3)

- [ ] FTS surface, auto-suggest sector, duplicate detection, parent/child links,
      watchers, mentions, templates, beneficiary feedback, auto-escalation

## Phase 8 — Hardening

- [ ] Load (k6), soak, security review, backups+PITR, runbooks, prod observability,
      audit_events partitioning + retention
- [x] First-pass security review (`docs/SECURITY_REVIEW.md`) — RBAC strengths,
      defence-in-depth gaps, performance hotspots, hardening backlog
- [x] Super-admin gate driven by `Config.SUPER_ADMIN_SUBJECTS` (env var) instead
      of a hardcoded UUID inside `iam/rbac.is_super_admin`
- [x] `assignable_users` endpoint refuses non-admins without an explicit sector
      and rejects sectors the caller doesn't belong to

---

## Test status

| Suite | Count | Status |
|---|--:|---|
| `tests/unit/test_rbac.py`           | 32 | ✅ |
| `tests/unit/test_principal.py`      |  3 | ✅ |
| `tests/unit/test_pagination.py`     |  4 | ✅ |
| `tests/unit/test_state_machine.py`  | 26 | ✅ |
| `tests/unit/test_auth_cache.py`     |  2 | ✅ |
| `tests/integration/test_phase4_services.py` |  3 | ✅ |
| `tests/integration/test_workflow_acceptance.py` |  3 | ✅ |
| `tests/integration/test_workflow_concurrency.py` |  1 | ✅ |
| **Total**                           | **74** | **✅** |

---

## Open questions (architecture §18)

1. External beneficiary auth path — Keycloak realm or magic-link?
2. Closed-ticket retention window?
3. Email provider — SMTP relay or transactional service?
4. i18n from day one or RO-only MVP-1?
