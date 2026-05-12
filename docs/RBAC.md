# Tickora RBAC

_Last refreshed: 2026-05-12._

This document is the **authoritative reference** for Tickora's authorization
model. It covers the identity provider topology, realm roles, organizational
groups, the predicate matrix, and the per-feature enforcement summary.

Backend RBAC is the source of truth. The frontend may hide buttons for
ergonomics, but every endpoint re-checks permissions server-side and returns
`403 Forbidden` (or `404 Not Found` where existence must not leak).

---

## 1. Identity provider topology

Application identity lives in the custom Keycloak realm `tickora`. **Do not
create Tickora business clients, roles, groups, or users in the `master`
realm.** The `master` realm is reserved for Keycloak administration; the
bootstrap script (`scripts/keycloak_bootstrap.py`) actively cleans Tickora
artifacts out of `master` if they were accidentally created there.

### Clients

| Client | Type | Purpose |
|---|---|---|
| `tickora-spa` | Public · PKCE | Browser login, access-token acquisition, refresh. Token claims include `groups` (full path) via the `tickora-groups` mapper. |
| `tickora-api` | Confidential · service account | Backend API audience and admin-side surface (user lookup, group/role administration, password resets). Calls Keycloak Admin REST with realm-management roles: `query-users`, `query-groups`, `view-users`, `view-realm`, `manage-users`. |

The SPA token also carries the `tickora-api-audience` mapper so a single
access token is accepted by both the API and Keycloak.

### Realm roles

Realm roles gate **feature modules** — what areas of the UI/API a user can
even attempt to use. They are **not** used to model organizational structure;
that is done via groups (§1.1).

| Role | Purpose |
|---|---|
| `tickora_admin` | Platform administrator. Can view/administer every entity, override every workflow predicate. Implied by membership in the `/tickora` root group. |
| `tickora_auditor` | Read-only oversight. Sees the full audit ledger, every ticket (including private comments and attachments), and every dashboard, but should not mutate operational data. |
| `tickora_distributor` | Initial triage and routing. Sees pending and sector-assigned tickets, reviews tickets via `POST /api/tickets/<id>/review`, sets triage metadata, assigns to sectors/users, cancels pending tickets, changes priority, and writes private triage comments. |
| `tickora_avizator` | Endorsement reviewer (Romanian: _avizator_). Can claim and decide ticket endorsements requested by assigned operators. Sees the endorsement inbox at `/avizator`. |
| `tickora_internal_user` | Internal beneficiary/requester. Default for any user with a sector membership or generic staff access. Can create tickets, view their own, post public comments, close their own done tickets. |
| `tickora_external_user` | External beneficiary/requester. Public ticket surface only — private comments, private attachments, and the audit tab are hidden. |
| `tickora_service_account` | Reserved for automation/system integrations. Never assigned to human seed users. |

The bootstrap script removes two historical roles if found:
`tickora_sector_member` and `tickora_sector_chief` are **deprecated** — sector
membership and sector leadership are now encoded entirely via Keycloak groups
(§1.1), never via realm roles.

### 1.1 Organizational groups

Sector access is encoded in Keycloak's group tree. The structure is
**dynamic** — the bootstrap script seeds a configurable list of sectors and
Tickora reads the live tree at runtime, so adding a sector (`/tickora/sectors/s42`)
in Keycloak requires no code change.

| Group pattern | Meaning |
|---|---|
| `/tickora` | Super-admin root. Full platform access across every sector. Treated as implicit `tickora_admin` and as visibility into every sector. |
| `/tickora/beneficiaries/internal` | Internal beneficiary cohort — typically combined with `tickora_internal_user`. |
| `/tickora/beneficiaries/external` | External beneficiary cohort — typically combined with `tickora_external_user`. |
| `/tickora/sectors/<code>` | **Effective chief + member** for the named sector. Equivalent to belonging to both child groups. Most internal staff use a single sector parent group. |
| `/tickora/sectors/<code>/member` | Operational member of `<code>`. Can claim tickets in the sector, mark them done, post comments once assigned. |
| `/tickora/sectors/<code>/chief` | Sector chief for `<code>`. Adds: see other sector members' work, reassign within the sector, change priority on sector tickets, manage sector users via the admin UI, view sector audit. |

`Principal.all_sectors` resolves to the union of every sector implied by the
groups above (both `member` and `chief` rolled up). `Principal.chief_sectors`
is the strict subset where the user is a chief.

### 1.2 Profile expansion

`GET /api/me` returns the user's effective roles and sector memberships
**after group-tree expansion**. For `/tickora` users the API expands sector
visibility from the live Keycloak `/tickora/sectors` children and only falls
back to the database when Keycloak is briefly unreachable. The Profile page
renders this as an access tree so the user can see *why* they have the
permissions they do, instead of having to infer from raw group paths.

---

## 2. Roles cheat-sheet

| Role / group | Can read | Can write | Restricted from |
|---|---|---|---|
| `/tickora` (super-admin) | Everything | Everything (incl. hard delete if subject is in `SUPER_ADMIN_SUBJECTS`) | — |
| `tickora_admin` | Everything | Everything except hard delete | Hard delete unless super-admin |
| `tickora_auditor` | Everything (incl. private comments/attachments) | Nothing operational | All ticket workflow actions |
| `tickora_distributor` | All pending + sector-assigned tickets globally | Triage review, sector/user assignment, priority change, cancel; private comments during triage | Operator-side status pushes unless self-assigned |
| `tickora_avizator` | Endorsement inbox + tickets that have a request assigned to them | Endorsement decision (approve/reject/claim) | Anything outside endorsement scope unless also internal user |
| Sector chief `/tickora/sectors/s10/chief` | Tickets in `s10`, sector audit, sector members | Reassign within `s10`, change priority, remove sector, set/delete metadata; can manage `s10` users in admin UI | Other sectors |
| Sector member `/tickora/sectors/s10/member` | Tickets in `s10` | Self-assign; post comments / drive status once assigned | Other sectors; status pushes / comments unless actively assigned |
| `tickora_internal_user` | Own tickets, own watchlist, mentions | Create tickets, comment on own tickets (public), close own done tickets, reopen own | Anything cross-user |
| `tickora_external_user` | Own tickets via email-matched identity | Create tickets (external surface) | Private comments, private attachments, audit tab |

---

## 3. Predicate matrix

Every check goes through pure predicate functions in `src/iam/rbac.py`. Each
function takes a `Principal` plus the entity (ticket/comment/endorsement) and
returns `bool`. No DB calls, no HTTP — they are trivially unit-testable.

### 3.1 Ticket visibility

`can_view_ticket(p, t)`

| Condition | Grants visibility |
|---|---|
| `p.is_admin` or `p.is_auditor` | Yes |
| Email-matched external requester (`p.email == t.requester_email`, `t.beneficiary_type == 'external'`) | Yes |
| `t.created_by_user_id == p.user_id` | Yes |
| `t.beneficiary_user_id == p.user_id` | Yes |
| Sector intersection (`t.sector_codes ∩ p.all_sectors`) | Yes |
| `p.is_distributor` **and** `t.status ∈ {pending, assigned_to_sector}` | Yes |
| Otherwise | No |

A failed visibility check from a list endpoint silently filters the ticket
out. A failed visibility check on a `GET /api/tickets/<id>` returns `404` to
avoid leaking existence.

### 3.2 Ticket mutation

`can_modify_ticket(p, t)`: admin **or** chief of current sector **or** active
assignee.

`can_update_ticket(p, t)`: admin **or** distributor **or** chief of current
sector (used during triage edits like priority/category).

### 3.3 Workflow transitions

| Action | Predicate | Allowed |
|---|---|---|
| `assign_sector` | `can_assign_sector` | admin, distributor, chief of current sector |
| `assign_to_me` | `can_assign_to_me` | admin, anyone whose sectors intersect the ticket's |
| `assign_to_user` / `reassign` | `can_assign_to_user` | admin, distributor, chief of current sector |
| `add_assignee` | service-level check | `can_assign_to_user` + target user in current sector (unless admin) |
| `remove_assignee` | service-level check | admin, chief of current sector, or removing self |
| `unassign` | (workflow_service) | active assignee or admin/chief |
| `mark_done` / `close` / `cancel` / `reopen` | `can_drive_status` | active assignee only (admin via assign-then-act) |
| `change_priority` | `can_change_priority` | admin, distributor, chief of current sector |
| `change_status` | composite | depends on target status — close/reopen for beneficiary, otherwise driver predicate |
| `delete_ticket` (soft) | `can_delete_ticket` | super-admin only (`is_super_admin`) |

**Self-assignment policy.** Operator-side actions — driving status,
writing comments — require the caller to be the **active assignee**. A chief
who needs to push a ticket through state must first claim it via
`assign_to_me`. This makes every write attributable to a real owner. Admin
override is preserved.

### 3.4 Comments

| Predicate | Allowed |
|---|---|
| `can_see_private_comments` | admin, auditor, distributor, members/chiefs of current sector |
| `can_post_public_comment` | active assignee, creator, beneficiary user, email-matched external requester |
| `can_post_private_comment` | active assignee only (admin override via prior self-assign) |

Bystander chiefs and distributors **read** but do not **write** on tickets
they are not actively working. The 15-minute edit window is enforced server-
side in `comment_service`.

### 3.5 Attachments

| Predicate | Allowed |
|---|---|
| `can_upload_attachment` | Same as `can_view_ticket` |
| `can_download_attachment(t, "public")` | Same as `can_view_ticket` |
| `can_download_attachment(t, "private")` | Same as `can_see_private_comments` |

Bytes never transit the API: upload uses pre-signed PUT URLs to MinIO,
download returns a 302 to a 60-second signed GET URL. Backend authorizes
before issuing either URL.

### 3.6 Audit / dashboards

| Predicate | Allowed |
|---|---|
| `can_view_global_audit` | admin, auditor |
| `can_view_sector_audit(sector)` | admin, auditor, chief of `sector` |
| `can_view_audit_tab(t)` | admin, auditor, distributor, sector members/chiefs of current sector |
| `can_view_global_dashboard` | admin, auditor |
| `can_view_sector_dashboard(sector)` | admin, auditor, chief of `sector`, member of `sector` |

The personal monitor (`GET /api/monitor/users/<id>`) is gated by a
`_can_view_user_dashboard` helper at the service layer — self, admin, or
auditor.

### 3.7 Endorsements (avizare suplimentară)

| Predicate | Allowed |
|---|---|
| `can_request_endorsement(t)` | active assignee of `t` |
| `can_decide_endorsement(e)` | admin, any avizator on a pool request, or the targeted avizator on a direct request |

The endorsement inbox at `/avizator` lists open requests filtered by the
caller's role: pool requests are visible to every avizator, direct requests
only to the named avizator.

### 3.8 Widget catalogue

The widget catalogue (`widget_definitions`) has a `required_roles` JSONB
column. The list endpoint `GET /api/admin/widget-definitions` filters the
returned catalogue by the caller's roles:

- **Admin** / **auditor**: see every active widget (they manage the catalogue
  and audit configurations).
- **Anyone else**: see widgets where `required_roles` is empty (universally
  available) **or** they hold at least one matching role.

`upsert_widget` re-checks the same gate at write time
(`_check_widget_required_roles`). `auto_configure_dashboard` pre-loads the
catalogue and skips any widget the caller is not authorized for, so a
beneficiary's auto-configured dashboard never silently includes admin widgets.

The current beneficiary-visible catalogue is:

`ticket_list`, `profile_card`, `recent_comments`, `shortcuts`, `clock`,
`welcome_banner`, `notification_feed`, `my_watchlist`, `my_mentions`,
`my_requests`, `requester_status`.

Sector members/chiefs additionally see operational widgets (`sector_stats`,
`user_workload`, `stale_tickets`, `workload_balancer`, `bottleneck_analysis`,
`my_assigned`, `assignment_age`, `throughput_trend`, `priority_mix`,
`oldest_active`, `monitor_kpi`, `linked_tickets`). Distributors add
`audit_stream`, `not_reviewed`, `reviewed_today`, `global_kpi`,
`backlog_by_sector`. Admins add `task_health`, `recent_failures`,
`active_sessions`, `system_health`.

### 3.9 Snippets (procedures)

Snippets are admin-authored procedures with audience scoping. The visibility
rule:

- Empty audiences → public (every signed-in user).
- Otherwise → visible if at least one audience row matches the caller's
  sectors, realm roles, or beneficiary type.
- Admin / `/tickora` users always see every snippet.

Writes (`POST/PATCH/DELETE /api/snippets[/<id>]`) are admin-only
(`_require_admin`). Reads return `404` (not `403`) on visibility mismatch to
avoid leaking existence.

### 3.10 Dashboards (custom)

Dashboards are owner-only:

- `GET / PATCH / DELETE /api/dashboards/<id>`: `owner_user_id == p.user_id`,
  else `404`.
- Widget add/update/delete and `auto-configure`: same ownership gate.

Widget `config` is validated at write time
(`dashboard_service._validate_widget_config`): unknown `scope`, foreign
`sector_code`, and invisible `ticketId` references are rejected up front.
Data fetch endpoints behind each widget re-check the same predicates as
direct API calls — defence in depth.

---

## 4. Endpoint gates (audit table)

Every backend endpoint passes through `@require_authenticated` (which builds
the `Principal` from the bearer JWT). The table below documents the
**additional** gate enforced by the service layer.

### Tickets

| Endpoint | Method | Service gate |
|---|---|---|
| `/api/tickets` | GET | `ticket_service._visibility_filter` per role |
| `/api/tickets` | POST | All authenticated users (creates a ticket they own) |
| `/api/tickets/<id>` | GET | `can_view_ticket` → 404 on miss |
| `/api/tickets/<id>` | PATCH | `can_modify_ticket` |
| `/api/tickets/<id>` | DELETE | `can_delete_ticket` (super-admin) |
| `/api/tickets/<id>/assign-sector` | POST | `can_assign_sector` |
| `/api/tickets/<id>/assign-to-me` | POST | `can_assign_to_me` |
| `/api/tickets/<id>/assign-to-user` | POST | `can_assign_to_user` |
| `/api/tickets/<id>/reassign` | POST | `can_assign_to_user` |
| `/api/tickets/<id>/unassign` | POST | active assignee, chief, or admin |
| `/api/tickets/<id>/change-status` | POST | `can_drive_status` (action-specific) |
| `/api/tickets/<id>/sectors/add` | POST | `can_assign_sector` |
| `/api/tickets/<id>/sectors/remove` | POST | `can_remove_sector` |
| `/api/tickets/<id>/assignees/add` | POST | `can_assign_to_user` + sector membership |
| `/api/tickets/<id>/assignees/remove` | POST | admin, chief, or removing self |
| `/api/tickets/<id>/mark-done` | POST | `can_mark_done` (active assignee) |
| `/api/tickets/<id>/close` | POST | `can_close` (active assignee or beneficiary) |
| `/api/tickets/<id>/reopen` | POST | `can_reopen` |
| `/api/tickets/<id>/cancel` | POST | `can_cancel` |
| `/api/tickets/<id>/change-priority` | POST | `can_change_priority` |
| `/api/tickets/<id>/review` | POST | `is_admin or is_distributor` |

### Comments / attachments / metadata / watchers / links

| Endpoint | Method | Service gate |
|---|---|---|
| `/api/tickets/<id>/comments` | GET | `can_see_private_comments` filters private rows |
| `/api/tickets/<id>/comments` | POST | `can_post_public_comment` or `can_post_private_comment` per visibility |
| `/api/comments/<id>` | PATCH/DELETE | author-only + 15-minute edit window |
| `/api/tickets/<id>/attachments/upload-url` | POST | `can_upload_attachment` |
| `/api/tickets/<id>/attachments` | POST/GET | `can_view_ticket` + comment access (if private) |
| `/api/attachments/<id>` | DELETE | uploader or admin |
| `/api/attachments/<id>/download` | GET | `can_download_attachment` (per visibility) |
| `/api/tickets/<id>/metadata` | GET | `can_view_ticket` (via service) |
| `/api/tickets/<id>/metadata` | POST/DELETE | `can_modify_ticket` |
| `/api/tickets/<id>/watchers` | GET | `can_view_ticket` |
| `/api/tickets/<id>/watchers` | POST | self-subscribe, admin to subscribe others |
| `/api/tickets/<id>/watchers/<user_id>` | DELETE | self-remove, admin to remove others |
| `/api/tickets/<id>/links` | GET | `can_modify_ticket` on source |
| `/api/tickets/<id>/links` | POST | source modifiable + target visible |
| `/api/links/<id>` | DELETE | source-ticket modifiable |

### Endorsements / audit / reference

| Endpoint | Method | Service gate |
|---|---|---|
| `/api/tickets/<id>/endorsements` | POST | `can_request_endorsement` |
| `/api/tickets/<id>/endorsements` | GET | `can_view_ticket` |
| `/api/endorsements/<id>/decide` (+ approve/reject) | POST | `can_decide_endorsement` |
| `/api/endorsements/<id>/claim` | POST | avizator on a pool request |
| `/api/endorsements` | GET | filters by avizator + targeting |
| `/api/audit` | GET | `can_view_global_audit` |
| `/api/tickets/<id>/audit` | GET | viewer of the ticket; chief on sector |
| `/api/users/<id>/audit` | GET | `can_view_global_audit` |
| `/api/reference/ticket-options` | GET | authenticated |
| `/api/reference/assignable-users` | GET | admin/distributor/chief/member (sector_code required for non-admin) |

### Admin / config

| Endpoint | Method | Service gate |
|---|---|---|
| `/api/admin/overview` | GET | `require_admin` |
| `/api/admin/users` | GET | admin or sector chief (chiefs see only users in their sectors) |
| `/api/admin/users/<id>` | GET/PATCH | `require_admin_or_chief` |
| `/api/admin/users/<id>/reset-password` | POST | `require_admin_or_chief`; backend generates the password, returned once to the caller |
| `/api/admin/sectors` (+ membership / group-hierarchy / metadata-keys / system-settings / ticket-metadatas / categories / subcategories / subcategory-fields) | all | `require_admin` |
| `/api/admin/widget-definitions` | GET | filtered by caller's roles (no admin gate by design) |
| `/api/admin/widget-definitions/upsert` | POST | `is_admin` |
| `/api/admin/widget-definitions/sync` | POST | `is_admin` |

### Notifications / tasks / monitor / dashboards / snippets

| Endpoint | Method | Service gate |
|---|---|---|
| `/api/notifications` | GET | scoped to `principal.user_id` |
| `/api/notifications/mark-read`, `<id>/mark-read` | POST | scoped to `principal.user_id` |
| `/api/notifications/stream-ticket` | POST | trades JWT for a 30-second one-time SSE ticket in Redis |
| `/api/notifications/stream` | GET | Redis pubsub channel scoped to `notifications:{user_id}` |
| `/api/tasks`, `/api/tasks/<id>` | GET | admin only |
| `/api/monitor/overview` | GET | data scoped by role (admin/auditor → global; sector users → sector; others → personal) |
| `/api/monitor/global` | GET | `can_view_global_dashboard` |
| `/api/monitor/sectors` | GET | filtered by membership |
| `/api/monitor/sectors/<code>` | GET | `can_view_sector_dashboard` |
| `/api/monitor/users/<id>` | GET | self, admin, or auditor |
| `/api/monitor/timeseries` | GET | data scoped by visibility filter |
| `/api/dashboards` | GET/POST | owner scope |
| `/api/dashboards/<id>` (+ widgets, auto-configure) | all | owner scope |
| `/api/snippets` | GET | audience filter |
| `/api/snippets[/<id>]` | POST/PATCH/DELETE | admin only |

### Public

`/health`, `/liveness`, `/readiness` — no authentication. Used by k8s probes
and the docker-compose health checks.

---

## 5. Defence in depth

Three checks protect every read:

1. **SQL.** `ticket_service._visibility_filter` baked into the `SELECT`. A
   buggy controller cannot leak via the list endpoint.
2. **Service.** RBAC predicate before returning the entity.
3. **Serializer.** `serialize_ticket` strips internal fields when
   `can_see_internal` is false (sectors, request IP, source channel, internal
   user IDs).

For writes:

1. **Decorator.** `@require_authenticated` populates the `Principal`.
2. **Service predicate.** Action-specific check + state-machine transition.
3. **Atomic UPDATE.** Workflow transitions use `UPDATE … WHERE …` clauses
   that encode the precondition; concurrent attempts get
   `ConcurrencyConflictError` (409).
4. **Audit.** `audit_service.record(db, …)` writes in the same transaction
   so audit and state changes commit or roll back together. Access-denied
   attempts emit `ACCESS_DENIED` events with the failing rule name.

---

## 6. Seed users

Run the bootstrap stack:

```bash
make keycloak-bootstrap   # realm, clients, roles, group tree
make migrate              # database schema
make seed                 # users, sectors, sample tickets, dashboards, snippets
```

All seeded users share the development password `Tickora123!`.

| Username | Type | Roles | Sector groups | Typical use |
|---|---|---|---|---|
| `admin` | Internal | implied by `/tickora` | `/tickora` | Full platform administration |
| `bogdan` | Internal | implied by `/tickora` | `/tickora` | Super-admin seed user |
| `auditor` | Internal | `tickora_auditor`, `tickora_internal_user` | none | Read-only audit / dashboards |
| `distributor` | Internal | `tickora_distributor`, `tickora_internal_user` | none | Triage / review queue |
| `avizator` | Internal | `tickora_avizator`, `tickora_internal_user` | none | Endorsement inbox |
| `chief.s10` | Internal | `tickora_internal_user` | `/tickora/sectors/s10/chief` | Sector chief — manage `s10` users, reassign, audit |
| `member.s10` | Internal | `tickora_internal_user` | `/tickora/sectors/s10/member` | Sector operator |
| `member.s2` | Internal | `tickora_internal_user` | `/tickora/sectors/s2/member` | Cross-sector visibility tests |
| `beneficiary` | Internal | `tickora_internal_user` | `/tickora/beneficiaries/internal` | Internal requester |
| `external.user` | External | `tickora_external_user` | `/tickora/beneficiaries/external` | External requester (email-matched identity) |

### Seeded sectors

| Code | Name |
|---|---|
| `s1` | Service Desk |
| `s2` | Network Operations |
| `s3` | Infrastructure |
| `s4` | Applications |
| `s5` | Security |
| `s10` | Field Operations |

Additional sectors (`s6`–`s9`) are provisioned in Keycloak by the bootstrap
script and can be activated by creating database rows; the group tree is
dynamic.

---

## 7. Ticket state machine

States: `pending`, `assigned_to_sector`, `in_progress`, `done`, `cancelled`.
There is no longer a separate `closed` state — closing simply lands on
`done`. The legacy `reopened` state was folded back into `in_progress` to
keep the transition table small.

Actions (with the predicate they ultimately call):

| Action | Predicate | Target status |
|---|---|---|
| `assign_sector` | `can_assign_sector` | `assigned_to_sector` |
| `assign_to_me` | `can_assign_to_me` | `in_progress` |
| `assign_to_user` / `reassign` | `can_assign_to_user` | `in_progress` |
| `unassign` | active assignee, chief, or admin | `assigned_to_sector` |
| `mark_done` / `close` | `can_drive_status` (active assignee) | `done` |
| `reopen` | `can_drive_status` | `in_progress` |
| `cancel` | `can_cancel` | `cancelled` |

Each transition is implemented as a single atomic `UPDATE … WHERE … RETURNING`
in `workflow_service`, so concurrent attempts collapse to exactly one
winner. The losing call sees `rowcount == 0` and raises
`ConcurrencyConflictError`.

---

## 8. Authorization-related audit events

`access_denied` is emitted whenever a service call short-circuits with
`PermissionDeniedError` and a target entity can be identified. The audit row
carries the failing rule name (e.g. `rule: can_post_private_comment`), the
ticket id, and the actor. Auditors can query these via `GET /api/audit?action=access_denied`.

Successful writes are audited too: `ticket_created`, `ticket_updated`,
`ticket_assigned_to_sector`, `ticket_assigned_to_user`, `ticket_reassigned`,
`ticket_unassigned`, `ticket_marked_done`, `ticket_closed`,
`ticket_cancelled`, `ticket_reopened`, `ticket_priority_changed`,
`ticket_reviewed`, `ticket_deleted`, `comment_created`, `comment_deleted`,
`attachment_uploaded`, `attachment_deleted`, `ticket_metadata_set`,
`ticket_metadata_deleted`, `config_changed`. Each row records actor user id +
username, request IP (via `request_metadata.client_ip` — trusted-proxy
aware), user-agent, the old/new value snapshot, and the correlation id of
the request that produced it.

---

## 9. Operational notes

- **Private comments and private attachments must never be exposed to
  beneficiaries.** Three layers of enforcement; auditors are the only
  read-only role with full visibility.
- **404 vs 403.** Unauthorized reads of a specific ticket return `404` so
  existence cannot be enumerated. Authorization failures on writes return
  `403` with the rule name in the body.
- **Sector chief admin scope.** A chief can manage users in their sectors
  via the admin UI (list/get/update/reset-password), but cannot administer
  global config (sectors, metadata keys, categories, widget catalogue, etc.).
- **External requester identity.** `can_close` / `can_reopen` match by email
  when `beneficiary_type == 'external'`. If a recipient's email rotates,
  consider pinning `beneficiary_user_id` on first contact instead.
- **`SUPER_ADMIN_SUBJECTS`** (env-driven, comma-separated Keycloak subject
  UUIDs) gates hard delete (`can_delete_ticket`). Default empty in dev;
  rotate during deploy.
