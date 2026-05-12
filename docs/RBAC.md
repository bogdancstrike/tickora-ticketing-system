# Tickora RBAC

_Last refreshed: 2026-05-12. Current branch snapshot._

This document describes the authorization model implemented in the current
codebase. It is not just the intended product model. Where the implementation
has drifted or contains a bug, the drift is called out explicitly.

Backend RBAC is authoritative. Frontend route guards, hidden buttons, and page
visibility are only convenience. Every security-sensitive decision must be made
by the API/service layer.

## 1. Identity Topology

Tickora identity lives in the Keycloak realm `tickora`.

| Client | Type | Purpose |
|---|---|---|
| `tickora-spa` | Public, PKCE | Browser login and access-token acquisition. |
| `tickora-api` | Confidential service account | Backend audience and Keycloak Admin REST access for users, groups, roles, and password reset. |

The backend accepts Keycloak access tokens, verifies signature/issuer/audience,
then hydrates a local `Principal`.

### Principal Inputs

| Source | Used for |
|---|---|
| JWT `sub` | Stable Keycloak subject. Also used for `SUPER_ADMIN_SUBJECTS`. |
| JWT username/email | Local user upsert, display, requester matching. |
| `realm_access.roles` | Global application roles. |
| `groups` claim | Root group, sector groups, beneficiary groups. |
| Keycloak Admin REST | Fallback group lookup when token groups are incomplete. |
| Local `users` table | Internal user id and profile data. |

Important implementation notes:

- A first-seen Keycloak subject is provisioned into the local `users` table.
- `Config.PRINCIPAL_CACHE_TTL` exists, but principal cache TTL follows the
  remaining token lifetime rather than that setting.
- Local `users.is_active = false` is not currently enforced during principal
  hydration. If Keycloak still issues a valid token, the user can authenticate.
- Admin user disable/enable attempts may update Keycloak, but some Keycloak
  failures are swallowed. Treat local deactivation alone as insufficient.

## 2. Global Roles

| Role | Current behavior |
|---|---|
| `tickora_admin` | Platform-level role. Grants broad visibility and many write predicates. Hard delete still requires `is_super_admin`. Some admin endpoints require `/tickora` root group, not only this role. |
| `tickora_auditor` | Global read-only oversight. Can view all tickets and global audit. Should not mutate operational data. |
| `tickora_distributor` | Intake/review role. Sees `pending` and `assigned_to_sector` tickets globally. Can route/assign and change priority through service predicates. |
| `tickora_avizator` | Endorsement reviewer. Can see the endorsement inbox and decide/claim allowed endorsement requests. |
| `tickora_internal_user` | Default internal requester/staff marker. Used for UI and dashboard/widget eligibility. Does not by itself grant sector access. |
| `tickora_external_user` | External requester marker. External ticket visibility is primarily email-matched. |
| `tickora_service_account` | Reserved for automation; not intended for human seed users. |

Deprecated historical roles `tickora_sector_member` and
`tickora_sector_chief` should not be used. Sector structure is encoded by
Keycloak groups.

## 3. Keycloak Groups

| Group path | Current parser behavior |
|---|---|
| `/tickora` | Root platform group. Sets `has_root_group` and effectively implies admin behavior. |
| `/tickora/beneficiaries/internal` | Beneficiary cohort marker. User type is still primarily role-derived. |
| `/tickora/beneficiaries/external` | External beneficiary cohort marker. User type is still primarily role-derived. |
| `/tickora/sectors/<code>` | Parsed as chief access for `<code>`. It is not currently stored as both member and chief. |
| `/tickora/sectors/<code>/member` or `/members` | Parsed as member access for `<code>`. |
| `/tickora/sectors/<code>/chief` or `/chiefs` | Parsed as chief access for `<code>`. |

`Principal.all_sectors` includes both member and chief sectors. Most visibility
checks use `all_sectors`, so a chief still sees the sector even if the bare
group is not duplicated as a member group.

`GET /api/me` performs extra profile expansion for display. In particular, a
root `/tickora` user may be shown a full sector tree by querying Keycloak. That
display expansion is not the same thing as the `Principal` object used inside
RBAC predicates.

## 4. Super Admin

`is_super_admin(p)` returns true only when:

- `p.is_admin` is true; and
- `p.keycloak_subject` is listed in `Config.SUPER_ADMIN_SUBJECTS`.

The default config contains a seed subject UUID. Hard delete is the main
operation behind this gate. This should move to a Keycloak group or deployment
secret before production.

## 5. Ticket Visibility

`can_view_ticket(p, t)` grants visibility when any condition is true:

| Condition | Result |
|---|---|
| `p.is_admin` | Can view. |
| `p.is_auditor` | Can view. |
| External requester email matches `t.requester_email` and ticket beneficiary type is external | Can view. |
| `t.created_by_user_id == p.user_id` | Can view. |
| `t.beneficiary_user_id == p.user_id` | Can view. |
| Ticket sector intersects `p.all_sectors` | Can view. |
| `p.is_distributor` and status is `pending` or `assigned_to_sector` | Can view. |

Assignment alone is not a visibility grant. The assignment services should
therefore avoid assigning users who do not have sector/requester visibility.

Ticket list endpoints use a SQL visibility filter instead of post-filtering
after loading rows. Direct ticket reads return `404` on visibility miss.

## 6. Ticket Mutation Predicates

| Predicate | Current allowed callers |
|---|---|
| `can_modify_ticket` | admin, chief of current sector, or active assignee. |
| `can_update_ticket` | admin, distributor, or chief of current sector. Used by ticket patch/update. |
| `can_assign_sector` | admin, distributor, or chief of current sector. |
| `can_assign_to_me` | admin or caller whose sectors intersect the ticket sectors. |
| `can_assign_to_user` | admin, distributor, or chief of current sector. |
| `can_change_priority` | admin, distributor, or chief of current sector. |
| `can_delete_ticket` | super-admin only. |

Service-level add/remove assignee logic adds extra constraints around target
sector membership and self-removal.

## 7. Workflow Actions

Statuses currently in code:

- `pending`
- `assigned_to_sector`
- `in_progress`
- `done`
- `cancelled`

There is no separate `closed` database status. The close endpoint lands on
`done`.

| Endpoint/action | Current gate | Notes |
|---|---|---|
| `assign-sector` | `can_assign_sector` | Sets/changes current sector. |
| `assign-to-me` | `can_assign_to_me` | Bug: current SQL accepts all statuses, including `done` and `cancelled`. |
| `assign-to-user` / `reassign` | `can_assign_to_user` | Target validation must ensure user can actually see/work the sector. |
| `add-assignee` | `can_assign_to_user` plus target sector rules | Multi-assignee support. |
| `remove-assignee` | admin, chief, or removing self | Depends on service branch. |
| `unassign` | active assignee or admin/chief | Returns ticket to sector assignment. |
| `mark-done` | active assignee | Blocks pending endorsements. |
| `close` | active assignee | Sets status to `done`; beneficiaries do not currently close tickets through this predicate. |
| `reopen` | active assignee plus reason path | Sets status to `in_progress`. |
| `cancel` | active assignee plus reason path | Sets status to `cancelled`. |
| `change-status` | active assignee for drive-style changes | Bug: target status graph is too permissive. |

Important drift: older docs described beneficiary close/reopen or distributor
cancel behavior. The current predicates are assignee-owned. The review endpoint
can attempt private-comment or cancel branches, but those branches can fail
because the downstream comment/workflow services require active assignment.

## 8. Comments

| Predicate | Current allowed callers |
|---|---|
| `can_see_private_comments` | admin, auditor, distributor, and sector members/chiefs for the ticket sector. |
| `can_post_public_comment` | active assignee, creator, beneficiary user, or email-matched external requester. |
| `can_post_private_comment` | active assignee only. |

Comments have a server-side edit window (`COMMENT_EDIT_WINDOW`, default 15
minutes). Edit/delete is author-scoped inside that window except where admin
paths explicitly override.

Private comment risk: notification recipient selection should be filtered
through `can_see_private_comments()`. Current watcher fanout can leak that a
private comment occurred.

## 9. Attachments

| Operation | Current gate |
|---|---|
| Upload URL | `can_view_ticket` via `can_upload_attachment`. |
| Register metadata | Ticket visibility and object existence checks; comment ownership/visibility checks are incomplete. |
| List | Ticket visibility, with private visibility derived from parent comment. |
| Download public attachment | `can_view_ticket`. |
| Download private attachment | `can_see_private_comments`. |
| Delete | Uploader or admin. |

Signed URL TTL defaults to 60 seconds for both upload and download.

Security gaps:

- Object size is not verified against the actual uploaded object.
- Checksum is not verified.
- MIME/magic bytes are not enforced.
- AV scanning is a stub.
- Attachment registration can target comments the caller should not mutate if
  the comment id is known.

## 10. Audit

| Endpoint | Current gate |
|---|---|
| `GET /api/audit` | admin or auditor. |
| `GET /api/users/<id>/audit` | admin or auditor. |
| `GET /api/tickets/<id>/audit` | Current implementation allows ordinary ticket viewers through ticket visibility. This is too broad. |

`can_view_audit_tab(t)` exists and allows admin, auditor, distributor, and
sector members/chiefs. The per-ticket audit endpoint should enforce it, or a
stricter predicate, before returning audit rows.

## 11. Endorsements

| Operation | Current gate |
|---|---|
| Request endorsement | Active assignee of the ticket. |
| List inbox | Admin sees all; avizators see pool requests, direct-to-me requests, and decisions they made. |
| Claim | Avizator on a pool request. Current implementation is read-then-write, not an atomic conditional update. |
| Decide | Admin, pool avizator, or targeted avizator. |

Gaps:

- Direct request target validation checks active user existence but not the
  `tickora_avizator` role.
- Claim should be a conditional `UPDATE ... WHERE assigned_to_user_id IS NULL`.

## 12. Admin And Configuration

| Area | Current gate |
|---|---|
| Admin overview | `require_admin()`; this requires `/tickora` root group. |
| User list | Admin or sector chief. Chiefs are scoped to users in managed sectors. |
| User get/update/reset-password | Admin or sector chief scoped to managed users. |
| Sectors, memberships, metadata keys, categories, subcategories, system settings | `require_admin()` root group. |
| Widget definitions list | Authenticated and role-filtered by `required_roles`. |
| Widget definition upsert/sync | `principal.is_admin`. |
| Tasks | Admin only. |

Critical gap: chief-scoped user update must not be allowed to mutate realm
roles. Treat role assignment as a separate root-admin operation.

## 13. Dashboards And Widgets

Custom dashboards are intended to be owner-only:

- list/create returns dashboards owned by `principal.user_id`;
- get/update/delete checks owner and returns `404` on mismatch;
- widget upsert validates the parent dashboard owner;
- auto-configure validates the parent dashboard owner;
- widget catalog is role-filtered.

Known bug: widget delete only validates that the widget belongs to the supplied
dashboard id. It does not verify that the dashboard belongs to the caller.

Schema reality:

- `custom_dashboards.is_public` still exists in the model. The migration named
  `drop_is_public_dashboards` is a no-op.
- `dashboard_shares` was dropped.
- `user_dashboard_settings` exists, but parts of the API/frontend contract are
  not fully wired.
- Unknown widget types can be persisted because the widget type is not a
  database-enforced foreign key to `widget_definitions`.

## 14. Snippets

Snippets are admin-authored procedures with audience scoping.

Read visibility:

- empty audience means visible to every signed-in user;
- otherwise at least one audience row must match caller sector, role, or
  beneficiary type;
- admin/root users see all snippets;
- invisible snippets return `404` on direct read.

Writes are admin-only.

## 15. Notifications

| Endpoint | Current gate |
|---|---|
| `GET /api/notifications` | Current user's notifications only. |
| Mark read | Current user's notification rows only. |
| `POST /api/notifications/stream-ticket` | Authenticated; stores a one-time 30-second Redis ticket containing the raw JWT. |
| `GET /api/notifications/stream` | Redeems SSE ticket and subscribes to `notifications:{user_id}`. |

SSE ticket warning: the bearer extractor accepts `sse_ticket` on all
authenticated endpoints. It should be restricted to the stream route or bound
to path/method.

## 16. Endpoint Gate Summary

The endpoint map currently registers 111 method operations across 87 unique
URLs. Public endpoints are:

- `GET /health`
- `GET /liveness`
- `GET /readiness`

Every `/api/*` handler currently imports and uses `@require_authenticated`.
Additional gates are service-level and domain-specific:

| Domain | Main service gate |
|---|---|
| Tickets | SQL visibility filter for list; `can_view_ticket` for detail; mutation predicates for writes. |
| Workflow | RBAC predicate plus status logic in `workflow_service`. |
| Review | Top-level admin/distributor, then downstream workflow/comment gates. |
| Comments | Comment visibility plus post/edit predicates. |
| Attachments | Ticket/comment visibility plus uploader/admin delete. |
| Metadata | Ticket visibility for read, `can_modify_ticket` for write/delete. |
| Watchers | Ticket visibility; self/admin watcher mutation. |
| Links | Source ticket modifiable; target ticket visible. |
| Audit | Global admin/auditor; per-ticket currently too broad. |
| Admin | Mixed root-admin, `is_admin`, and admin-or-chief gates. |
| Monitor | Role-aware/global/sector/self gates. |
| Dashboards | Owner scope, except widget-delete bug. |
| Endorsements | Active assignee for request; avizator/admin for claim/decision. |
| Notifications | Current user scope. |
| Snippets | Audience filters for reads; admin for writes. |
| Tasks | Admin only. |

## 17. Seed Users

All seeded users use `Tickora123!` in development.

| Username | Roles/groups | Typical use |
|---|---|---|
| `admin` | `/tickora`, `tickora_admin` | Root platform admin. |
| `bogdan` | `/tickora`, `tickora_admin` | Seed super-admin subject in default config. |
| `auditor` | `tickora_auditor`, `tickora_internal_user` | Global audit/read-only review. |
| `distributor` | `tickora_distributor`, `tickora_internal_user` | Intake triage and routing. |
| `avizator` | `tickora_avizator`, `tickora_internal_user` | Endorsement inbox. |
| `chief.s10` | `/tickora/sectors/s10`, `tickora_internal_user` | Sector chief for `s10`. |
| `member.s10` | `/tickora/sectors/s10/member`, `tickora_internal_user` | Sector operator. |
| `member.s2` | `/tickora/sectors/s2/member`, `tickora_internal_user` | Cross-sector test user. |
| `beneficiary` | `tickora_internal_user`, internal beneficiary group | Internal requester. |
| `external.user` | `tickora_external_user`, external beneficiary group | External requester. |

## 18. Known Authorization Defects

Fix these before treating the matrix as production-grade:

1. Sector chiefs can potentially grant privileged realm roles through the user
   update path.
2. Ticket audit is exposed to ordinary ticket viewers.
3. Local inactive users are not rejected during principal hydration.
4. `assign_to_me` and generic status changes accept too many status paths.
5. Assignment alone is not visibility; assignment services must prevent
   non-visible assignees.
6. Attachment registration does not fully authorize target comments.
7. Dashboard widget delete lacks parent owner verification.
8. Private comment notifications can leak activity to unprivileged watchers.
9. SSE tickets can authenticate one arbitrary request within their TTL.
10. Endorsement direct targets are not role-validated and claim is not atomic.
11. Admin gates are inconsistent between `/tickora` root group and
    `tickora_admin` role.

## 19. Regression Tests To Add

- Matrix tests for every persona against every workflow action.
- Ticket audit negative tests for beneficiary, external requester, watcher, and
  unrelated sector member.
- Chief user-management tests proving chiefs cannot add `tickora_admin`,
  `tickora_auditor`, `tickora_distributor`, or root-equivalent groups.
- Disabled-user authentication test.
- Attachment registration tests around private/deleted comments.
- Dashboard widget delete IDOR test.
- SSE ticket path binding test.
- Endorsement target role and concurrent claim tests.
