# BABOK TO-BE — Gap Analysis vs. the Tickora rewrite

**Requirements source:** `Analiza_TO-BE_BABOK_v4.0_Helpdesk.docx` (client
elicitation sessions of 8 May / 11 May 2026, 40 requirements CB-01..CB-40).

**Important framing:** the AS-IS columns of the BABOK document describe a
*previous, basic ticketing app* that this repository is the rewrite of.
**Those AS-IS columns are not relevant here** — the only thing that
matters from the BABOK doc is the beneficiary's expressed requirements.
This report restates each requirement and compares it to what this repo
(Tickora modulith — FastAPI-style QF handlers, Postgres, Keycloak,
SQLAlchemy 2.x, React 19) implements *today*.

Repository state used for the comparison: branch `master` at commit
`fd33c94`, today 2026-05-12.

For every requirement below: **what the client wants** → **what this repo
has** → **what's left to do**.

---

## 0. Executive summary

| Bucket | Count | Meaning |
| --- | --- | --- |
| Covered — no work needed | **17** | The rewrite already satisfies the client requirement. |
| Partial — code exists, one sub-need missing | **9** | Foundations in place; finish the last mile. |
| Missing — not implemented yet | **9** | New design + build required. |
| Decision needed (client) | **3** | Wording contradicts another CB or our architecture; needs sign-off before we build. |
| Won't do / outside scope | **2** | Explicitly declined by client (CB-13) or our stack disagrees (CB-07 alt DB). |

The remaining build work clusters into five themes:

1. **Sequential multi-sector resolution (CB-17 / CB-37)** — the single
   biggest architectural addition.
2. **Audio + native browser notifications (CB-03)** — SSE backbone is
   live; audio cue and `Notification API` integration are not.
3. **System-resources dashboard (CB-04)** — no host metrics surface yet.
4. **Two-instance, classification-segregated deployment (CB-08)** — code
   is fully env-driven; the ops overlay isn't documented.
5. **Legacy data import (CB-26)** — no ETL exists; blocked on a sample
   export from the beneficiary.

The rest is small backend hardening (CB-35 password reset, CB-39
`last_activity_at`), Keycloak realm settings (CB-18/32 session cap), and
frontend polish (CB-20 internal/external badge, CB-28 client-portal
procedures page).

---

## 1. Per-requirement analysis

Source file references use absolute repo paths and `file:line`.

### CB-01 — Dynamic per-category metadata fields when creating a ticket
**Need:** category drives extra fields on the ticket form; fields are
configurable, can be required/optional, multiple input types.
**This repo:** `Subcategory` owns `SubcategoryFieldDefinition`
(`src/ticketing/models.py:103`) with `key`, `label`, `value_type`,
`options` (JSONB for dropdowns), `is_required`, `display_order`. Values
are validated and persisted into `TicketMetadata`
(`src/ticketing/service/ticket_service.py:198`). Admin CRUDs them via
`/api/admin/subcategory-fields`; frontend reads them via
`/api/reference/subcategories/<id>/fields`.
**Verdict: COVERED.** No work.

### CB-02 — Re-take a ticket from another worker in the same sector
**Need:** colleague A can pick up a ticket currently held by colleague B.
**This repo:** distributor/chief/admin can re-assign via
`workflow_service.assign_to_user` (`workflow_service.py:446`). Peer
member-to-member takeover currently requires the holder to release
(`unassign`) or a chief to force it.
**Verdict: PARTIAL.** If the client wants direct peer steal (no chief
intervention), widen `rbac.can_assign_to_user` to "any member of the
current sector". One-line RBAC change; decision in §3 CL-A.

### CB-03 — Audio and visual real-time notifications
**Need:** sonic alert + browser/desktop notification when a relevant
ticket event happens.
**This repo:** SSE transport is live — `src/api/notifications.py:74..130`
(short-lived ticket exchange + `text/event-stream`),
`frontend/src/components/common/NotificationDropdown.tsx:77..97` consuming
it, fan-out via `publish("notify_ticket_event", …)` and
`src/ticketing/notifications.py`. **Missing:** `Notification.requestPermission()`,
desktop notification on incoming SSE message, audio cue (Web Audio API or
static `.mp3`), per-user mute toggle in profile.
**Verdict: PARTIAL.** Frontend-only work, ~½ day.

### CB-04 — System resources dashboard (CPU / RAM / HDD)
**Need:** admin can see host metrics in the app.
**This repo:** `/api/monitor/*` is ticket KPIs only; no `psutil` usage,
no host telemetry.
**Verdict: MISSING.** Add `/api/admin/system-stats` guarded by
`rbac.can_administer`, sampling host stats with `psutil`, plus an admin
widget. Recommend `psutil` over Prometheus/Grafana stack so the
"single Tickora deploy" promise of CB-08 still holds.

### CB-05 — Stats visible to sector chief
**Need:** sector chief sees stats for their sector.
**This repo:** `rbac.can_view_sector_dashboard` (`rbac.py:250`) grants
the chief access to their sector's monitor; `monitor_sector` endpoint is
live (`endpoint.json:579`). Admin keeps the global view via
`can_view_global_dashboard`.
**Verdict: COVERED**, conditional on §3 CL-C: confirm chiefs see only
*their* sector(s) — that's the current behaviour. If the client wants
chiefs to see other sectors too, widen `rbac.can_view_sector_dashboard`.

### CB-06 — Max 1000 users
**Need:** support up to ~1000 internal + external users.
**This repo:** no hard cap; list endpoints use cursor pagination with
`clamp_limit(default=50, max_=200)` (`ticket_service.py:372`). Postgres +
the current indexes handle 1000 users trivially.
**Verdict: COVERED.**

### CB-07 — Preferred DB: MySQL or MSSQL
**Need:** target deployment uses MySQL or MSSQL.
**This repo:** Postgres-only — we rely on `INET`, `JSONB`, `UUID`,
partial indexes, `CREATE SEQUENCE IF NOT EXISTS` for ticket codes
(`ticket_service.py:40`).
**Verdict: WON'T DO without explicit confirmation.** Surface the
mismatch to the client; switching dialect is a multi-week migration, not
a config swap. Recommend keeping Postgres.

### CB-08 — Two production instances with different classification levels
**Need:** same app, two isolated deployments (e.g. SECRET / UNCLASSIFIED),
no data crossover.
**This repo:** the app is 12-factor — `src/config.py` is fully env-driven,
Keycloak realm/clients are configurable, docker-compose uses named
volumes and isolated networks.
**Verdict: PARTIAL.** What's missing is operational, not code:
- per-classification `docker-compose.<level>.yml` overlay,
- two Keycloak realms (or two Keycloak instances),
- Nginx/HAProxy vhost split + TLS per instance,
- DR/backup playbook per instance.
Spec deliverable for ops; no model changes.

### CB-09 — Beneficiary sees own ticket status, summary stats, search by code or content
**Need:** external user dashboard with status, simple stats, search.
**This repo:** `list_` (`ticket_service.py:362`) supports `search` against
`title`, `txt`, `ticket_code` (lines 430..438). External users see only
their own tickets via the visibility filter
(`ticket_service.py:85..91`, matched by `requester_email`).
**Verdict: COVERED.**

### CB-10 — Categories and subcategories managed by admin
**Need:** admin CRUDs the classification nomenclature.
**This repo:** `/api/admin/categories`, `/api/admin/subcategories`,
`/api/admin/subcategory-fields` (`endpoint.json:370..422`), all
admin-gated.
**Verdict: COVERED.**

### CB-11 — Shift (TURĂ) role picks up new tickets and routes them
**Need:** a role responsible for triaging incoming tickets.
**This repo:** `ROLE_DISTRIBUTOR` (`principal.py:11`) is this role:
- sees pending + assigned_to_sector tickets (`ticket_service.py:111`),
- can route via `rbac.can_assign_sector`,
- multiple users may hold the role simultaneously (rotate via Keycloak
  realm-role grant).
**Verdict: COVERED.** If the client wants automated time-based shift
schedules, that's a separate feature (not in CB rows; flag if needed).

### CB-12 — Shift role sees already-routed tickets, not only new ones
**Need:** the shift role has visibility on tickets after they're routed.
**This repo:** distributor's visibility predicate
(`ticket_service.py:111`) explicitly includes `assigned_to_sector`;
global view available via `/api/monitor/global`.
**Verdict: COVERED.**

### CB-13 — No formal escalation levels
**Need:** explicitly *no* L1/L2/L3 escalation tier.
**This repo:** none built. The endorsement flow (avizare suplimentară) is
a different concept (a request for a second opinion, not escalation).
**Verdict: COVERED by absence.**

### CB-14 — Anyone internal can route a ticket to anyone in the org
**Need:** loosen routing permission from "distributor/chief/admin" to
"any internal user".
**This repo:** routing gated by `can_assign_sector` /
`can_assign_to_user` — currently admin + distributor + chief-of-current-sector.
**Verdict: NEEDS DECISION** (§3 CL-A). If approved, a small RBAC change
in `rbac.py`. Conflicts with audit-trail expectations and with CB-16
(see CL-B).

### CB-15 — Ticket can be reopened; returns to the user who closed it
**Need:** reopen flow, ticket goes back to the original closer.
**This repo:** `workflow_service.reopen` (`workflow_service.py:789..843`):
- requires a reason,
- moves `done|cancelled → in_progress`,
- re-attaches the **last active assignee** (`last_active_assignee_user_id`,
  `models.py:195`),
- increments `reopened_count`, sets `reopened_at`,
- records `TICKET_REOPENED` audit event and a public comment with the
  reason (`comment_type="reopen_reason"`).
**Verdict: COVERED**, conditional on §3 CL-E (who can initiate the
reopen — today only the assignee; the client may want the external
requester to be able to as well).

### CB-16 — Every worker in a sector sees every ticket in that sector
**Need:** sector-scoped read for all members.
**This repo:** `_visibility_filter` clauses at
`ticket_service.py:93..109` grant visibility on tickets whose
`current_sector_id` matches **any** sector the user is a member of, plus
the secondary `TicketSectorAssignment` join.
**Verdict: COVERED** if "in the sector" means "current sector". The
BABOK wording is ambiguous (could also mean cross-sector for all
workers). Surface as §3 CL-B.

### CB-17 / CB-37 — Sequential multi-sector resolution
**Need:** a ticket that requires multiple sectors is handled by them
**in sequence**; each sector marks its step done; **only the last sector
in the chain may close the ticket**.
**This repo:** today's model has `Ticket.current_sector_id` plus a
many-to-many `TicketSectorAssignment` (`models.py:378..392`) where the
extra sectors are *parallel observers*, with no ordering and no per-sector
status.
**Verdict: MISSING.** Largest item. Proposed shape:

| Need | Land at |
| --- | --- |
| Ordered chain of sectors | New table `TicketSectorStep(ticket_id, sequence_no, sector_id, status, started_at, completed_at, notes, by_user_id)`. |
| Only the active step can mark itself done | New action `complete_step` in `workflow_service`. |
| Only the **last** step may move ticket to `done` | New predicate `rbac.can_close_chain(p, t)` checking `step.sequence_no == max(sequence_no)`. Tighten `can_close`. |
| Comments visible across the whole chain | Already true (TicketComment is per-ticket). |
| Chain editable by distributor/admin pre-completion | New `update_chain` endpoint. |
| Audit | New events `TICKET_STEP_STARTED`, `TICKET_STEP_COMPLETED`. |
| Notifications | Reuse `publish("notify_sector", …)` on each handoff. |

Effort: 1–2 sprints (model + migration + state-machine extension + UI
for chain editor and per-step "complete" button + monitor breakdown by
step). **Blocked on §3 CL-G** (who builds the chain, can it be edited
mid-flight, refusal-to-handle semantics).

### CB-18 / CB-32 — Max 2 concurrent sessions per user, 12-hour each
**Need:** enforce at most 2 active sessions per user (so a worker can be
logged in on two devices for shift handover), 12h session length.
**This repo:** no app-level session cap. `session_tracker` is presence
tracking only (Redis TTL, `src/common/session_tracker.py`).
**Verdict: MISSING — but the right home is Keycloak**, not Tickora:
- set realm SSO session max = 12h,
- set client "max session count per user" = 2 (or implement via event
  listener if the version doesn't support it natively).
Zero backend code change unless the client wants an in-app "kick oldest
session" UX (in which case we'd need our own session table).

### CB-19 — Username-only login (no email)
**Need:** sign in with username only.
**This repo:** Keycloak realm is configured for username login;
`User.email` is nullable (`iam/models.py:23`).
**Verdict: COVERED.**

### CB-20 — Visual separation between internal and external tickets
**Need:** distinct colour/badge for `internal` vs `external` tickets in
lists.
**This repo:** `beneficiary_type` is always set
(`models.py:176`); the review page tags it
(`frontend/src/pages/ReviewTicketPage.tsx:299`) but the main tickets list
(`TicketsPage.tsx`) and ticket cards don't show the badge consistently.
**Verdict: PARTIAL.** Half-day frontend task: add a coloured badge on
the list page and ticket cards.

### CB-21 — Admin sees all tickets
**Need:** unrestricted read for admin.
**This repo:** `_visibility_filter` returns `None` for admin / auditor
(`ticket_service.py:72`).
**Verdict: COVERED.**

### CB-22 — Re-request endorsement after rejection
**Need:** if endorsement is rejected, the assignee can add notes and
re-request on the same ticket.
**This repo:** `TicketEndorsement` (`models.py:428..455`). A rejection
sets `status='rejected'` and `decided_at`; nothing stops the assignee
creating another endorsement on the same ticket with a new
`request_reason` — every iteration is preserved as its own row. The
endorsement service permits this
(`src/ticketing/service/endorsement_service.py`).
**Verdict: COVERED.** If the client wants an explicit "this re-request
replaces endorsement X" link between iterations, add a
`previous_endorsement_id` FK — trivial.

### CB-23 — Workers can search tickets they previously had access to
**Need:** a worker who moved out of sector A still finds tickets they
worked on while in A.
**This repo:** `_visibility_filter` evaluates **current** state; moving
out of a sector hides past tickets.
**Verdict: MISSING.** Needs (a) `SectorMembershipHistory` table — see
also CB-25, and (b) an extra OR-clause in `_visibility_filter` joining
on the historical window. Modest piece; sequence after CB-25 since they
share the new history table.

### CB-24 — Management can search any ticket in the system
**Need:** unrestricted search for management roles.
**This repo:** admin and auditor already see everything. If
"management" includes sector chiefs and they should search globally
(not just their sector + sub-sectors), a small `rbac.py` widen is
needed.
**Verdict: COVERED for admin/auditor; NEEDS DECISION for chiefs** (§3
CL-C).

### CB-25 — User sector-change history; stats by period per sector
**Need:** when user X moves from sector A to B, X's prior contributions
remain attributed to A; statistics reflect the per-period membership.
**This repo:** `SectorMembership` (`models.py:42`) is a single current
row per (user, sector, role); no history.
**Verdict: MISSING.** Add `SectorMembershipHistory(user_id, sector_id,
role, granted_at, revoked_at)`, dual-write on grant/revoke, then
rewrite the affected monitor queries to join on
`granted_at <= ticket.assigned_at <= revoked_at`. Touches ~3 queries in
`monitor_service.py`.

### CB-26 — Import metadata from the existing helpdesk
**Need:** load historical tickets from the legacy system; searchable
afterwards.
**This repo:** no ETL exists.
**Verdict: MISSING — blocked on spec.** Cannot estimate without (a) the
source system identity, (b) an export sample, (c) field mapping, (d)
row count. Once delivered: build `scripts/etl/` with
parser → mapper → loader → report, add `is_imported` boolean and
`legacy_id` on `Ticket` for traceability.

### CB-27 — Procedures created by admin only
**Need:** snippet / procedure CRUD restricted to admin.
**This repo:** `snippet_service` (`snippet_service.py:28`) calls
`_require_admin` on create/update/delete. Reads are audience-filtered.
**Verdict: COVERED.**

### CB-28 — Procedures visible to external clients (priority-criteria guide)
**Need:** at least some procedures must be visible to external users in
the client portal.
**This repo:** `SnippetAudience` (`models.py:580..596`) supports
`audience_kind='beneficiary_type'` with value `'external'`. Add such an
audience row to a snippet and it becomes visible to externals —
`_is_visible` already handles it (`snippet_service.py:67..69`).
**Verdict: PARTIAL (frontend only).** Backend is done; add a
client-portal route in React that lists procedures
(`snippet_service.list_` runs for any authenticated user). Half-day
task.

### CB-29 — Admin can change priority on an existing ticket
**Need:** change the urgency/severity of an open ticket.
**This repo:** `POST /api/tickets/<id>/change-priority`
(`endpoint.json:259..262`) → `workflow_service.change_priority`
(`workflow_service.py:868`). RBAC permits admin, distributor, chief of
current sector (`rbac.py:159..164`).
**Verdict: COVERED.** Naming note: BABOK calls it *severity*, we call it
*priority* (`low|medium|high|critical`) — same concept, alias in UI if
the client prefers their term.

### CB-30 — Admin can resolve tickets, create groups/subgroups, deactivate users
**Need:** standard admin powers.
**This repo:** admin can drive any ticket via RBAC; sectors managed via
`/api/admin/sectors`; users deactivated via `is_active` on
`/api/admin/users` (`admin_service.py:181..183`).
**Verdict: COVERED.**

### CB-31 — Every action is audited
**Need:** comprehensive audit trail.
**This repo:** `audit_service.record` is invoked from every workflow
function, endorsement transition, admin op, attachment lifecycle,
snippet CRUD, membership change. Catalogue in `src/audit/events.py`.
**Verdict: COVERED.**

### CB-32 — Sessions limited to 2 per user, 12h each
Duplicate of CB-18; same answer (Keycloak realm settings).

### CB-33 — Password rules (30-day expiry, complexity, minimum length)
**Need:** strict password policy.
**This repo:** owned by Keycloak realm password policy (Tickora never
sees plaintext). Confirm the realm bootstrap script
(`scripts/keycloak/`) enforces 30-day expiry, complexity, min length.
**Verdict: COVERED (delegated)** — verify realm config matches.

### CB-34 — Account hierarchy as a tree
**Need:** organisation hierarchy visible as a tree.
**This repo:** Keycloak groups + sector codes form the hierarchy.
`/api/admin/group-hierarchy` (`endpoint.json:773..778`) exposes it; the
`has_root_group` principal flag marks the root.
**Verdict: COVERED.**

### CB-35 — Sector chief can reset a subordinate's password, with reason, audited
**Need:** chief-initiated password reset, mandatory reason, temporary
random password, audited.
**This repo:** `admin_service.reset_password` (`admin_service.py:206`)
is callable by admin **or** chief-of-target's-sector
(`require_admin_or_chief`, line 226). Calls Keycloak with
`temporary=True` so the user must change it on next login. **Gaps:**

1. **No `reason` field captured.** Audit row writes only
   `{"operation": "admin_reset_password"}` (line 222). Add `reason` to
   the POST body, validate non-empty, persist in `audit.metadata.reason`.
2. **Caller supplies the new password.** Replace with
   `secrets.token_urlsafe(16)` server-side and return the generated
   value in the response (one-time display) so chiefs can't pick weak
   passwords.

**Verdict: PARTIAL.** ~1 hour of work, security-positive.

### CB-36 — Admin creates accounts
**Need:** admin-only user creation.
**This repo:** `POST /api/admin/users` → `admin_service.create_user`,
provisions via Keycloak admin client then mirrors the row in `users`.
**Verdict: COVERED.**

### CB-37 — Sequential resolution: each sector in turn, last closes
Duplicate of CB-17. See above.

### CB-38 — Ticket closed only by the user who took it
**Need:** prevent strangers from closing someone else's work.
**This repo:** `rbac.can_close` requires `_is_assigned_to`
(`rbac.py:136`). After CB-17 lands, this predicate must additionally
require `step.sequence_no == max` so only the **last sector's** assignee
can close.
**Verdict: COVERED today; tighten when CB-17 lands.**

### CB-39 — Status / activity timestamp updates on every interaction
**Need:** "last activity" timestamp moves forward whenever someone
comments, assigns, or changes status.
**This repo:** `Ticket.updated_at` (`models.py:220`) is bumped via
SQLAlchemy `onupdate` only when *Ticket* row columns change — not when a
comment is added. Comments have their own `created_at`.
**Verdict: PARTIAL.** Cleanest fix: add `Ticket.last_activity_at`,
bump it from every comment / endorsement / status / assignment write,
expose in the serializer, and let the list endpoint sort by it.
~2 hours: migration + 4 call-sites.

### CB-40 — Comments can be published to the external user (toggle)
**Need:** staff decides whether each comment is visible to the external
requester.
**This repo:** `TicketComment.visibility ∈ {public, private}`
(`models.py:237`). Public is shown to all parties (including the
requester); private is gated by `can_see_private_comments`
(`rbac.py:182`). UI toggle is present in `TicketsPage.tsx`.
**Verdict: COVERED.**

---

## 2. Non-functional requirements (BABOK §5)

| ID | Topic | Client need | This repo | Verdict |
| --- | --- | --- | --- | --- |
| CNF-N01 | Scale to 1000 users | yes | no cap; cursor pagination + indexes | COVERED |
| CNF-N02 | 2 isolated prod instances | yes | env-driven config, one compose today | PARTIAL (ops) |
| CNF-N03 | 2 sessions / user | yes | unconstrained | MISSING (Keycloak config) |
| CNF-N04 | Reset password: random + reason | yes | caller-chosen, no reason | PARTIAL (CB-35) |
| CNF-N05 | Real-time push ≤2 s | yes | SSE works | COVERED |
| CNF-N06 | System-resource dashboard | yes | absent | MISSING (CB-04) |
| CNF-N07 | Audit captures reset reason | yes | absent | MISSING (folds into CB-35) |
| CNF-N08 | User sector-change history | yes | absent | MISSING (CB-25) |
| CNF-N09 | Legacy data import | yes | absent | MISSING (CB-26) |
| CNF-N10 | Internal/external visual cue | yes | inconsistent | PARTIAL (CB-20) |

---

## 3. Decisions needed from the beneficiary

These must be resolved before we ship the affected items. They are
**not** ambiguities of this codebase — they are unresolved scope items
in the BABOK doc itself.

- **CL-A — routing RBAC (CB-14):** any internal user routes, or stay
  with admin/distributor/chief? Affects audit-trail integrity.
- **CL-B — sector visibility (CB-16):** "every ticket in the sector" =
  current-sector only (today's behaviour) or cross-sector for all
  internal? If cross-sector, CB-14 becomes mandatory.
- **CL-C — chief read scope (CB-05 / CB-24):** chiefs see their sector
  only (today) or everything? Auditor exists for the latter.
- **CL-D — legacy import (CB-26):** the beneficiary must deliver a
  sample export, the source system identity, the field list, and the
  row count. Without these we can scaffold but not estimate.
- **CL-E — reopen initiator (CB-15):** assignee-only (today) or also
  external requester? If yes, widen `rbac.can_reopen`.
- **CL-F — "video" notifications (CB-03):** confirm this means browser
  `Notification API` + visual badge, not video call.
- **CL-G — sequential chain (CB-17):** who builds the chain (intake at
  creation? distributor at triage?); can it be edited mid-flight; what
  happens if a sector refuses a step?

---

## 4. Roadmap

### Sprint 1 — quick wins and safety
- CB-35 password-reset hardening: random temp password + reason +
  enriched audit (~1 day).
- CB-18 / CB-32 Keycloak realm: max 2 sessions / user, 12 h SSO max,
  documented in `scripts/keycloak/` (½ day).
- CB-20 internal/external badge across `TicketsPage` and ticket cards
  (½ day).
- CB-28 React client-portal route for procedures filtered by
  `beneficiary_type=external` audience (½ day).
- CB-39 `Ticket.last_activity_at` column, bump from every write,
  expose in serializer (½ day).
- CB-03 audio cue + `Notification.requestPermission` in
  `NotificationDropdown`, profile mute toggle (½ day).

### Sprint 2 — sequential resolution (CB-17 / CB-37)
- New `TicketSectorStep` model + migration.
- `workflow_service.complete_step`, `advance_chain`, `update_chain`.
- New predicate `rbac.can_close_chain`; tighten `rbac.can_close`.
- New audit events + per-step notifications.
- React: chain editor (admin / distributor) and per-step "complete"
  control.
- Monitor: time-per-step KPIs and "stuck-step" surfacing.

### Sprint 3 — history & search
- CB-25 `SectorMembershipHistory` model; refactor monitor queries to
  join on the membership window.
- CB-23 historical-access OR clause in `_visibility_filter` reusing the
  new history table.
- CB-24 widen chief search if §3 CL-C says so.

### Sprint 4 — ops & integrations
- CB-04 `/api/admin/system-stats` via `psutil` + admin widget.
- CB-08 per-classification `docker-compose` overlay, second Keycloak
  realm, Nginx vhost split, runbooks.
- CB-26 ETL once the beneficiary delivers a sample export.

---

## 5. Things the rewrite already gives the beneficiary

Useful to surface back so they don't request what's already done:

- **Dynamic per-category metadata fields (CB-01)** — backend + UI.
- **Full audit (CB-31)** — every workflow, endorsement, attachment,
  snippet, membership, and config change is recorded (`src/audit/events.py`).
- **Endorsement workflow (CB-22)** — first-class model with pool /
  direct assignment, decision history, and a `done`-blocking guard if
  any endorsement is pending (`workflow_service.py:118..129`).
- **SSE notifications (CB-03 backbone)** — production-ready transport;
  only the audio + native browser notification call are missing.
- **Beneficiary self-service search (CB-09)** — search by code, title
  and body for the requester's own tickets.
- **Snippets with audience scoping (CB-27 / CB-28)** — admin-only writes;
  per-sector / per-role / per-beneficiary-type read filtering.
- **Watchers and ticket links (Phase 7)** — not in BABOK, already
  shipped; surface as upsell.
- **Customisable dashboards** (`CustomDashboard` / `DashboardWidget`) —
  not in BABOK, already shipped.

---

## 6. Final classification table

| BABOK CB | Status in this repo | Action |
| --- | --- | --- |
| CB-01 | COVERED | — |
| CB-02 | PARTIAL | Decide CL-A; if loosened, widen `rbac.can_assign_to_user`. |
| CB-03 | PARTIAL | Frontend: audio + `Notification API` + mute toggle. |
| CB-04 | MISSING | Build `/api/admin/system-stats` + widget. |
| CB-05 | COVERED | Confirm CL-C scope. |
| CB-06 | COVERED | — |
| CB-07 | WON'T DO | Confirm Postgres is acceptable. |
| CB-08 | PARTIAL | Ops overlay + second Keycloak realm + Nginx split. |
| CB-09 | COVERED | — |
| CB-10 | COVERED | — |
| CB-11 | COVERED | — |
| CB-12 | COVERED | — |
| CB-13 | COVERED (absent by design) | — |
| CB-14 | DECISION | CL-A; small RBAC edit if approved. |
| CB-15 | COVERED | Confirm CL-E. |
| CB-16 | COVERED for current-sector | Confirm CL-B for cross-sector. |
| CB-17 | MISSING | `TicketSectorStep` + chain workflow. |
| CB-18 | MISSING | Keycloak realm setting. |
| CB-19 | COVERED | — |
| CB-20 | PARTIAL | Add badge on list pages. |
| CB-21 | COVERED | — |
| CB-22 | COVERED | Optional: add `previous_endorsement_id` FK. |
| CB-23 | MISSING | Historical-access OR-clause + CB-25 table. |
| CB-24 | COVERED for admin/auditor | Decide CL-C for chiefs. |
| CB-25 | MISSING | `SectorMembershipHistory`. |
| CB-26 | MISSING | ETL — blocked on sample. |
| CB-27 | COVERED | — |
| CB-28 | PARTIAL | Frontend route in client portal. |
| CB-29 | COVERED | Optional: rename UI label to "severity" if requested. |
| CB-30 | COVERED | — |
| CB-31 | COVERED | — |
| CB-32 | MISSING | Keycloak realm setting (duplicate of CB-18). |
| CB-33 | COVERED (delegated to Keycloak) | Verify realm bootstrap. |
| CB-34 | COVERED | — |
| CB-35 | PARTIAL | Add reason + generate random temp password. |
| CB-36 | COVERED | — |
| CB-37 | MISSING | Same as CB-17. |
| CB-38 | COVERED today | Tighten when CB-17 lands. |
| CB-39 | PARTIAL | Add `last_activity_at` column. |
| CB-40 | COVERED | — |

---

*Comparison performed against repo state at commit `fd33c94` on 2026-05-12.*
