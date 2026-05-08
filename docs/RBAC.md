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

Sector groups:

| Group pattern | Meaning |
|---|---|
| `/tickora/sectors/<sector>/members` | User is an operational member of the sector |
| `/tickora/sectors/<sector>/chiefs` | User is a sector chief for the sector |

## Roles

| Role | Purpose | Main permissions |
|---|---|---|
| `tickora_admin` | Platform administrator | Can view and administer all tickets, comments, private notes, attachments, audit, users, sectors, and configuration. Can execute all workflow actions. |
| `tickora_auditor` | Audit/read-only oversight | Can view global audit and dashboards. Can view tickets for audit purposes, including private comments, but should not mutate operational data. |
| `tickora_distributor` | Initial triage and distribution | Can see pending and sector-assigned tickets, review tickets, set triage metadata, assign tickets to sectors/users, cancel pending tickets, change priority, and write private triage comments. |
| `tickora_internal_user` | Internal beneficiary/requester | Can create tickets, view own tickets, post public comments, close done tickets, and reopen own done/closed tickets. |
| `tickora_external_user` | External beneficiary/requester | Can create/view own external tickets and interact only through public ticket surfaces. Private comments are hidden. |
| `tickora_sector_member` | Sector operator | Can view sector tickets, assign eligible tickets to self, comment, upload attachments, and mark assigned work done. |
| `tickora_sector_chief` | Sector coordinator | Can view sector tickets, assign/reassign users in their sector, change priority, cancel pending sector tickets, mark done, and view sector audit. |
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
| `admin` | Internal | `tickora_admin`, `tickora_internal_user` | none | Full platform administration and global testing |
| `auditor` | Internal | `tickora_auditor`, `tickora_internal_user` | none | Read-only audit and oversight testing |
| `distributor` | Internal | `tickora_distributor`, `tickora_internal_user` | none | Review pending tickets, set metadata, write private notes, and assign work to sectors/users |
| `chief.s10` | Internal | `tickora_sector_chief`, `tickora_sector_member`, `tickora_internal_user` | `/tickora/sectors/s10/chiefs` | Coordinate sector `s10` work and reassign sector tickets |
| `member.s10` | Internal | `tickora_sector_member`, `tickora_internal_user` | `/tickora/sectors/s10/members` | Process `s10` tickets and mark assigned tickets done |
| `member.s2` | Internal | `tickora_sector_member`, `tickora_internal_user` | `/tickora/sectors/s2/members` | Process `s2` network tickets |
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

## Notes

- Private comments and private attachments must never be exposed to beneficiaries.
- Unauthorized ticket reads return `404` where existence should not be leaked.
- Access-denied workflow attempts write `ACCESS_DENIED` audit events where the service can identify the entity.
