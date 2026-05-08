# Tickora RBAC

This document describes the application roles, seeded development users, and the main permissions enforced by the backend.

## Keycloak Realm

Application identity lives in the custom Keycloak realm `tickora`.

Do not create Tickora business clients, roles, groups, or users in the `master` realm. The `master` realm is only for Keycloak administration.

Clients:

| Client | Type | Purpose |
|---|---|---|
| `tickora-spa` | Public PKCE | Browser login and access-token acquisition |
| `tickora-api` | Confidential | Backend API audience and service-account surface |

Tickora uses realm roles for feature permissions and a tree-shaped group model
for organizational access. A parent group grants the effective organizational
access of its children, so a user can be configured with one broad group instead
of a long membership list.

The organization tree is dynamic. Tickora expects the shape
`/tickora/sectors/<sector>/{chiefs,members}`, but the `<sector>` nodes are read
from Keycloak at runtime. Adding `/tickora/sectors/s42` in Keycloak should not
require a code change.

| Group pattern | Meaning |
|---|---|
| `/tickora` | Full Tickora platform access. Super-admin root with all sector visibility and admin-level backend access. |
| `/tickora/sectors/<sector>` | Full sector access for that sector. Equivalent to both chief and member in the sector. |
| `/tickora/sectors/<sector>/members` | Operational member of the sector. |
| `/tickora/sectors/<sector>/chiefs` | Sector chief for the sector. |
| `sector10` or `/tickora/sector10` | Accepted shorthand for sector `s10`; equivalent to `/tickora/sectors/s10`. |

Sector membership and sector chief status must come from groups, not realm
roles. Realm roles decide which feature modules a user can see or use, such as
Audit or Review Tickets.

## Roles

| Role | Purpose | Main permissions |
|---|---|---|
| `tickora_admin` | Platform administrator feature permission | Can view and administer all tickets, comments, private notes, attachments, audit, users, sectors, and configuration. Can execute all workflow actions. Also implied by `/tickora`. |
| `tickora_auditor` | Audit/read-only oversight | Can view global audit and dashboards. Can view tickets for audit purposes, including private comments, but should not mutate operational data. |
| `tickora_distributor` | Initial triage and distribution | Can see pending and sector-assigned tickets, review tickets, set triage metadata, assign tickets to sectors/users, cancel pending tickets, change priority, and write private triage comments. |
| `tickora_internal_user` | Internal beneficiary/requester | Can create tickets, view own tickets, post public comments, close done tickets, and reopen own done/closed tickets. |
| `tickora_external_user` | External beneficiary/requester | Can create/view own external tickets and interact only through public ticket surfaces. Private comments are hidden. |
| `tickora_service_account` | Automation/service role | Reserved for worker/system integrations. Not assigned to human seed users. |

## Seed Users

Run:

```bash
make keycloak-bootstrap
make migrate
make seed
```

All seeded users use the development password:

```text
Tickora123!
```

| Username | Type | Roles | Sector groups | Typical use |
|---|---|---|---|---|
| `admin` | Internal | implied by `/tickora` | `/tickora` | Full platform administration and global testing |
| `bogdan` | Internal | implied by `/tickora` | `/tickora` | Super-admin seed user with full platform access |
| `auditor` | Internal | `tickora_auditor`, `tickora_internal_user` | none | Read-only audit and oversight testing |
| `distributor` | Internal | `tickora_distributor`, `tickora_internal_user` | none | Review pending tickets, set metadata, write private notes, and assign work to sectors/users |
| `chief.s10` | Internal | implied by sector parent group | `/tickora/sectors/s10` | Coordinate sector `s10` work and reassign sector tickets |
| `member.s10` | Internal | `tickora_internal_user` | `/tickora/sectors/s10/members` | Process `s10` tickets and mark assigned tickets done |
| `member.s2` | Internal | `tickora_internal_user` | `/tickora/sectors/s2/members` | Process `s2` network tickets |
| `beneficiary` | Internal | `tickora_internal_user` | none | Create internal tickets, view own tickets, close/reopen own work |
| `external.user` | External | `tickora_external_user` | none | Validate external beneficiary visibility restrictions |

## Seeded Sectors

| Code | Name |
|---|---|
| `s1` | Service Desk |
| `s2` | Network Operations |
| `s3` | Infrastructure |
| `s4` | Applications |
| `s5` | Security |
| `s10` | Field Operations |

## Seeded Tickets

| Code | Status | Sector | Assignee | Visibility scenario |
|---|---|---|---|---|
| `TK-SEED-000001` | `pending` | none | none | Distributor/admin can triage; beneficiary can see own ticket |
| `TK-SEED-000002` | `in_progress` | `s10` | `member.s10` | `s10` member/chief workflow, comments, private notes |
| `TK-SEED-000003` | `assigned_to_sector` | `s2` | `member.s2` | Cross-sector visibility and critical priority testing |

## Backend Enforcement Summary

Backend RBAC is the source of truth. The frontend can hide buttons, but endpoints still enforce permissions.

| Capability | Allowed principals |
|---|---|
| View all tickets | Admin, auditor |
| View own ticket | Creator or beneficiary user |
| View sector ticket | Member or chief of current sector |
| View pending triage queue | Distributor |
| Assign sector | Admin, distributor, current sector chief |
| Assign to self | Admin or user in current sector when ticket is unassigned and assignable |
| Assign/reassign user | Admin, distributor, or current sector chief |
| Review ticket metadata | Admin or distributor |
| Mark done | Admin, current sector chief, or current assignee |
| Close/reopen | Admin, ticket creator, or beneficiary user |
| Cancel pending ticket | Admin, distributor, or current sector chief |
| Change priority | Admin, distributor, or current sector chief |
| See private comments/attachments | Admin, auditor, distributor, or current sector members/chiefs |
| Post private comment | Admin, distributor, or current sector members/chiefs |
| Global audit | Admin or auditor |
| Ticket audit | Ticket viewers; sector chiefs additionally have sector audit authority |

## Profile Visibility

`GET /api/me` returns the authenticated user's effective roles and sector
memberships after group-tree expansion. For `/tickora` users, the API expands
sector visibility from the current Keycloak `/tickora/sectors` children and only
falls back to database sectors if Keycloak is temporarily unavailable. The
Profile page should render that as an access tree:

- root node: the current user
- `/tickora` users: full platform access
- sector parent users: sector node with both chief and member capabilities
- chief users: sector members visible under the sector
- member users: their own sector access and task participation

This makes the hierarchy visible to the user instead of requiring them to infer
permissions from raw Keycloak group names.

## Notes

- Private comments and private attachments must never be exposed to beneficiaries.
- Unauthorized ticket reads return `404` where existence should not be leaked.
- Access-denied workflow attempts write `ACCESS_DENIED` audit events where the service can identify the entity.
