# Common Criteria EAL4 Gap Analysis

_Last refreshed: 2026-05-12. Informal internal analysis only._

This document analyzes Tickora against a Common Criteria EAL4-style assurance
expectation. It is not a Common Criteria certificate, not a Protection Profile,
not a Security Target accepted by an evaluation lab, and not evidence that the
application satisfies EAL4.

The current verdict is direct: Tickora is not EAL4-ready. It has useful
security architecture pieces, but it lacks the formal evidence set, evaluator
artifacts, configuration management rigor, lifecycle controls, and vulnerability
closure expected for EAL4.

## 1. Scope And TOE Boundary

For a Common Criteria analysis, the TOE (Target of Evaluation) must be precise.
A reasonable Tickora TOE candidate would be:

- Flask/QF backend API in `src/`;
- database schema/migrations that define TOE-managed security state;
- React frontend only insofar as it invokes security functions and displays
  TOE decisions;
- worker process and task lifecycle where tasks affect TOE security behavior;
- configuration that controls authentication, authorization, audit, and storage.

Likely TOE environment components:

- Keycloak realm and Keycloak runtime;
- PostgreSQL server;
- Redis server;
- Kafka broker;
- MinIO/S3 service;
- ingress/TLS termination;
- operating system/container platform;
- SMTP provider if email delivery becomes real.

The boundary is important because many security properties depend on external
systems. If Keycloak is outside the TOE, the TOE must define assumptions and
environment objectives for correct token issuance, group/role administration,
clock sync, client configuration, and availability.

## 2. Assets

Primary assets:

- ticket content, category, priority, status, metadata, comments, and links;
- private comments and private attachments;
- attachment objects in MinIO/S3;
- audit events and access-denied records;
- user identity, role, group, sector, and beneficiary attributes;
- notification contents and unread state;
- admin configuration: sectors, metadata keys, widget definitions, settings;
- task payloads and task errors.

Security-sensitive derived assets:

- RBAC decisions;
- workflow state and assignment state;
- `SUPER_ADMIN_SUBJECTS`;
- presigned attachment URLs;
- SSE stream tickets;
- correlation ids and request metadata;
- Keycloak service-account credentials;
- database migration history.

## 3. Subjects And Objects

Subjects:

- unauthenticated health probe caller;
- authenticated internal user;
- authenticated external user;
- sector member;
- sector chief;
- distributor;
- avizator;
- auditor;
- admin;
- root `/tickora` admin;
- super-admin subject;
- worker process;
- Keycloak service account.

Objects:

- tickets;
- comments;
- attachments;
- metadata key/value rows;
- audit events;
- notification rows;
- dashboard and widget rows;
- widget definitions;
- snippets and snippet audiences;
- endorsement rows;
- tasks;
- users, sectors, memberships, groups, and roles.

## 4. Security Problem Definition

### Assumptions

| ID | Assumption |
|---|---|
| A.IDP | Keycloak correctly authenticates users and issues tokens with accurate subject, role, group, expiry, issuer, and audience claims. |
| A.ADMIN | Keycloak and Tickora administrators are trained, non-hostile, and use separate privileged accounts. |
| A.NETWORK | PostgreSQL, Redis, Kafka, MinIO, and Keycloak admin endpoints are not exposed to untrusted networks. |
| A.TIME | TOE and environment clocks are synchronized closely enough for token expiry, audit time, and presigned URL expiry. |
| A.SECRETS | Client secrets, database credentials, S3 credentials, and signing keys are protected by the deployment environment. |
| A.BACKUP | Backups preserve confidentiality and integrity and can be restored by authorized operators. |
| A.INGRESS | TLS termination, trusted proxy headers, and CORS policy are configured correctly in production. |

### Threats

| ID | Threat |
|---|---|
| T.UNAUTH | An unauthenticated attacker attempts to invoke protected API functions. |
| T.IDOR | A user guesses object ids to read or mutate tickets, comments, attachments, dashboards, or audit rows they do not own. |
| T.PRIVESC | A lower-privileged user gains higher privileges through admin APIs, role mutation, group mutation, or workflow bugs. |
| T.AUDIT_LEAK | A user obtains sensitive internal activity through audit history. |
| T.PRIVATE_LEAK | Private comments, private attachment existence, or private workflow activity leaks to beneficiaries or external requesters. |
| T.WORKFLOW_BYPASS | A user bypasses required workflow edges, reason requirements, endorsement checks, or assignment ownership. |
| T.ATTACHMENT | A user uploads malicious, oversized, mislabeled, or unauthorized attachment content. |
| T.REPLAY | A token, SSE ticket, presigned URL, or task envelope is reused outside its intended scope. |
| T.TASK_RACE | A task observes or emits uncommitted/rolled-back state. |
| T.AUDIT_TAMPER | A user modifies, deletes, or suppresses audit evidence. |
| T.DOS | A user overloads write endpoints, SSE streams, attachment URLs, or expensive aggregate queries. |
| T.CONFIG | A misconfiguration weakens CORS, proxy trust, super-admin scope, or external service exposure. |

### Organizational Security Policies

| ID | Policy |
|---|---|
| OSP.RBAC | All protected business functions must enforce backend authorization. Frontend controls are not sufficient. |
| OSP.AUDIT | Security-relevant actions and denials must be attributable to an actor, request, and time. |
| OSP.PRIVATE | Private comments and private attachments must be restricted to authorized staff roles. |
| OSP.WORKFLOW | Ticket workflow state changes must be attributable and follow approved transitions. |
| OSP.ADMIN | Privileged role/group administration must be restricted to designated root admins. |

## 5. Security Objectives

### Objectives For The TOE

| ID | Objective |
|---|---|
| O.AUTH | Verify bearer tokens and reject unauthenticated protected API calls. |
| O.USER_ATTR | Maintain and use subject attributes including roles, groups, sectors, user type, and local user id. |
| O.ACCESS | Enforce ticket, comment, attachment, audit, admin, dashboard, endorsement, and notification access control. |
| O.WORKFLOW | Enforce workflow state transition rules and assignment ownership. |
| O.AUDIT_GEN | Generate audit records for security-relevant actions and denials. |
| O.AUDIT_PROTECT | Prevent unauthorized audit read, modification, and deletion. |
| O.ATTACHMENT | Authorize, constrain, verify, and scan attachment content before release. |
| O.TASK | Ensure asynchronous tasks reflect committed TOE state only. |
| O.CONFIG | Expose secure configuration defaults and fail closed for security-sensitive settings. |
| O.ERROR | Avoid leaking sensitive existence or state through error responses. |

### Objectives For The Environment

| ID | Objective |
|---|---|
| OE.IDP | Keycloak protects credentials, authenticates users, signs tokens, and maintains accurate groups/roles. |
| OE.TRANSPORT | Ingress terminates TLS and enforces secure HTTP headers. |
| OE.NETWORK | Databases, brokers, object storage, and admin APIs are network-restricted. |
| OE.SECRETS | Deployment platform protects secrets and rotates them when needed. |
| OE.TIME | Environment provides reliable clock synchronization. |
| OE.BACKUP | Environment provides confidential, integrity-protected backups. |
| OE.MONITOR | Operators monitor logs, audit rows, task failures, and dependency health. |

## 6. Candidate SFR Mapping

This is an informal mapping to Common Criteria-style Security Functional
Requirements. It is not a formal Security Target.

| Family | Candidate requirement | Current status |
|---|---|---|
| FAU_GEN | Generate audit records for startup/security events/user actions. | Partial. Many writes and denials are audited; stream issuance, all admin role changes, and some edge cases need review. |
| FAU_SAR | Audit review by authorized roles. | Partial. Global audit is admin/auditor; ticket audit is too broad. |
| FAU_STG | Protect audit storage from unauthorized modification/deletion. | Partial. DB controls assumed; application has no append-only enforcement, retention, or partition policy. |
| FIA_UID | Identify users before protected actions. | Mostly met for `/api/*`; health probes public by design. |
| FIA_UAU | Authenticate users before protected actions. | Mostly delegated to Keycloak and JWT verification. |
| FIA_ATD | Maintain user security attributes. | Partial. Principal attributes exist; inactive local users not enforced. |
| FIA_USB | Bind subject attributes to sessions/requests. | Partial. Principal hydration binds token claims; cache invalidation/TTL behavior needs formalization. |
| FDP_ACC | Define access control policy over objects. | Partial. Policies exist in code/docs but need formal object/operation tables. |
| FDP_ACF | Enforce access control rules. | Partial. Strong in many areas; known defects in admin roles, ticket audit, workflow, attachments, dashboards. |
| FMT_MSA | Manage security attributes. | Not ready. Role/group/sector management authority is inconsistent and vulnerable. |
| FMT_SMF | Provide security management functions. | Partial. Admin APIs exist but need privilege separation and evidence. |
| FMT_SMR | Maintain security roles. | Partial. Roles exist through Keycloak; local/root/super-admin semantics need formalization. |
| FPT_STM | Reliable timestamps. | Delegated to environment/database; no formal TOE clock objective beyond assumption. |
| FPT_TDC | Consistent interpretation of external security data. | Partial. Keycloak claim/group parsing needs strict documented semantics and tests. |
| FTA_SSL | Session locking/termination. | Mostly outside TOE for browser/Keycloak sessions; SSE lifetime needs explicit bounds. |
| FTP_TRP | Trusted path/channel. | Delegated to TLS ingress and Keycloak; TOE assumes secure transport. |

## 7. EAL4 Assurance Mapping

EAL4 is commonly summarized as "methodically designed, tested, and reviewed."
The current repository does not yet have the evidence set expected by that
level.

| Assurance area | EAL4-style expectation | Current gap |
|---|---|---|
| ASE: Security Target | Clear TOE description, security problem, objectives, SFRs, and TOE summary specification. | This document is only an informal starting point. No evaluated ST exists. |
| ADV_ARC.1 | Security architecture description showing how TSF resists bypass/tamper. | Architecture docs exist but are not formal and currently identify bypass defects. |
| ADV_FSP.4 | Complete functional specification with full external interfaces and SFR-enforcing behavior. | Endpoint map exists, but no complete formal interface specification with pre/postconditions. |
| ADV_TDS.3 | Basic modular design with TSF internals and subsystem interactions. | Module docs exist, but not at evaluator-ready detail. |
| ADV_IMP.1 | Implementation representation available for evaluator sampling. | Source exists, but no controlled evaluation baseline/evidence package. |
| AGD_PRE.1 | Secure preparation guidance. | README/dev setup exists; production secure install guide does not. |
| AGD_OPE.1 | Operational user/admin guidance. | Admin/security operating guide is missing. |
| ALC_CMC.4 | Production support and automated configuration management. | Git exists, but formal CM plan, release baselines, and controlled build evidence are missing. |
| ALC_CMS.4 | Problem tracking and CM scope for implementation/evidence. | No formal CC evidence inventory. |
| ALC_DEL.1 | Secure delivery procedures. | No release/delivery procedure. |
| ALC_DVS.1 | Development security controls. | No documented dev environment security policy. |
| ALC_LCD.1 | Life-cycle model. | No formal lifecycle model beyond normal development. |
| ALC_TAT.1 | Well-defined development tools. | Toolchain is visible but not pinned/evidenced enough for evaluation. |
| ATE_COV.2 | Test coverage analysis against functional specification. | Tests exist but no traceability matrix. |
| ATE_DPT.1 | Testing depth at subsystem level. | Unit/integration tests exist; depth is uneven. |
| ATE_FUN.1 | Functional test documentation. | Test code exists; formal test procedures/results missing. |
| ATE_IND.2 | Independent testing sample. | No independent evaluator test package. |
| AVA_VAN.3 | Focused vulnerability analysis. | Current review finds exploitable design/code defects; not ready. |

## 8. Current Evidence Available

Useful raw material:

- `maps/endpoint.json` gives endpoint registration.
- `src/iam/rbac.py` centralizes many authorization predicates.
- `docs/RBAC.md` now documents current predicates and drift.
- `docs/SECURITY_REVIEW.md` lists current defects and test gaps.
- Alembic migrations document schema evolution.
- Unit and integration tests cover selected RBAC, state, cache, metadata,
  dashboard, request metadata, and service behavior.
- Docker Compose defines a reproducible local environment.
- Keycloak bootstrap script creates repeatable realm/client/role/group setup.

Insufficient or missing evidence:

- formal Security Target;
- SFR traceability to code/tests;
- formal interface specification for all 111 method registrations;
- production secure installation guide;
- administrator operating guide;
- role management policy;
- audit retention/protection policy;
- vulnerability analysis with closure evidence;
- independent testing evidence;
- configuration management plan;
- release baseline and delivery controls;
- dependency vulnerability records;
- penetration test results;
- crypto/key management documentation;
- backup/restore security procedure.

## 9. Major EAL4 Blockers

1. Critical role escalation risk through sector-chief user update.
2. Ticket audit leakage to ordinary ticket viewers.
3. Disabled local users can still authenticate if Keycloak issues tokens.
4. Workflow transition model is too permissive.
5. Attachment content controls are not real security controls yet.
6. Kafka task publication is not transaction-safe.
7. Dashboard widget delete IDOR.
8. SSE ticket scope is too broad.
9. Rate limiting coverage is incomplete and fails open.
10. No formal Security Target or SFR traceability.
11. No formal secure installation/operation guidance.
12. No independent vulnerability analysis or evaluator evidence package.

## 10. Remediation Roadmap

### Phase 1: Close Concrete Security Defects

- Fix admin role escalation.
- Gate ticket audit properly.
- Enforce inactive user policy.
- Restrict workflow transitions.
- Fix attachment registration and content verification.
- Fix dashboard widget ownership.
- Restrict SSE tickets.
- Add transaction-safe task outbox.

### Phase 2: Build A Testable Security Contract

- Create a role-by-endpoint matrix.
- Add regression tests for every listed defect.
- Add SFR-like operation tables for tickets, audit, admin, attachments,
  dashboards, notifications, and endorsements.
- Trace RBAC predicates to tests.

### Phase 3: Production Hardening

- Add dependency scanning and secret scanning.
- Add real metrics and alerting.
- Define audit retention and protection.
- Define backup/restore procedures.
- Lock down CORS, trusted proxies, MinIO CORS, and network exposure.
- Document secure Keycloak realm configuration.

### Phase 4: EAL4 Evidence Preparation

- Write a formal Security Target draft.
- Freeze a TOE boundary.
- Create configuration management and delivery procedures.
- Create administrator and user guidance.
- Produce functional specification and modular design docs.
- Produce test coverage/depth analysis.
- Run independent vulnerability analysis.

## 11. Verdict

Tickora could become a credible candidate for a formal assurance effort after
hardening, but the current branch is not close to EAL4 readiness. Treat this
document as a roadmap for evidence and defect closure, not as a compliance
statement.
