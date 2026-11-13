# TrustSeal Complete Implementation Plan

## 1. Purpose and authority

This plan converts the TrustSeal documentation into an executable engineering programme for the existing repository. It covers the complete desired platform, not merely the current prototype.

The governing sources are:

1. `TrustSeal_Master_SRS_Architecture_UX_v2.0_REGENERATED.md` as the traceable requirements baseline.
2. `TrustSeal_Complete_System_Documentation_v3.0.md` as the supporting product, workflow, security, operations, and implementation narrative.

The Master SRS contains 182 individually testable requirements: 140 functional requirements and 42 non-functional requirements. The DOCX and PDF files are publication variants of the Markdown sources and do not define a separate implementation baseline.

The documentation describes proposed behaviour, not proof that the current application implements it, is production-ready, or has received legal approval.

## 2. Current-state assessment

The repository is a Flask/Jinja/SQLAlchemy modular-monolith prototype with PostgreSQL/Alembic migrations and scaffolding for users, organisations, documents, signatures, stamps, subscriptions, and administration.

Material gaps include:

- no dependency/project manifest, automated test suite, CI pipeline, container/deployment definition, OpenAPI contract, or operational runbooks;
- a staged `.env` and staged/generated IDE, bytecode, archive, and operating-system artifacts that must not be published;
- development secrets and insecure fallback credentials in `config.py` and `app/decorators/system.py`;
- API requests bypassing the web authentication hook while multiple API routes lack their own mandatory authentication and tenant checks;
- incomplete document endpoints, unsafe serializers, exposed bearer/share tokens, signature data, IP information, and internal file paths;
- public/static path-based uploads without private object storage, malware scanning, content inspection, immutable object manifests, or safe conversion;
- mutable document records without a canonical digest-bound revision and execution snapshot model;
- signature and stamp CRUD records without recipient-bound invitations, consent, state machines, custody, dual control, idempotent finalisation, or evidence generation;
- no public verification service, tamper-evident audit chain, transaction outbox, worker queue, dead-letter recovery, health checks, metrics, tracing, backup validation, or disaster-recovery drill;
- a migration history that must be reconciled and replayed before it can be trusted as a production baseline.

Treat all existing feature routes as candidates for reuse only after their authorization, domain rules, serialization, tests, and migrations satisfy the relevant requirements.

## 3. Implementation principles

1. Retain Python, Flask, PostgreSQL, SQLAlchemy, Alembic, Jinja, and progressive JavaScript unless Phase 0 discovers a blocking constraint.
2. Keep a modular monolith with strict domain/service boundaries and asynchronous workers. Do not introduce microservices until measured scale or team ownership justifies them.
3. Implement vertical, production-verifiable slices: UI, API, policy, state transition, persistence, audit, asynchronous effects, failure recovery, and tests ship together.
4. Enforce deny-by-default tenant and object authorization on every read, write, download, export, and background task.
5. Treat originals, issued execution inputs, final records, and evidence packages as immutable objects with recorded SHA-256 manifests.
6. Separate authentication, authorization, consent, graphical appearance, identity assurance, cryptographic signing, stamp custody, and legal meaning.
7. Make all trust-critical mutations idempotent and attributable, including invitations, consent, signatures, stamp approvals, finalisation, payments, and webhooks.
8. Use expand/backfill/switch/contract database changes. Never invent missing historic evidence or approval data during migration.
9. Map every requirement to an owner, design component, migration, automated test, release, acceptance result, and any approved exception.
10. Do not claim legal validity, regulatory compliance, certificate-backed assurance, official seal authority, immutability, recovery targets, or service levels without the corresponding reviewed evidence.

## 4. Phase 0: governance, repository safety, and reproducible baseline

### 4.1 Decisions and sign-offs

Create versioned architecture decision records under `docs/decisions/` and assign owners and dates for:

- legal owner, brand rights, launch jurisdictions, customer segment, and supported assurance tiers;
- canonical state machines for documents, drafts, envelopes, participants, stamp requests, verification records, contracts, subscriptions, and jobs;
- multi-organisation membership, team/folder scope, role precedence, explicit denial, delegation, and separation-of-duties rules;
- graphical signature methods, recipient challenges, consent text/versioning, and partner-versus-native certificate signing;
- official stamp/seal terminology, custodian policy, and when four-eyes approval is mandatory;
- retention classes, legal holds, deletion adjudication, public verification disclosure, residency, and cross-border processing;
- object storage, malware scanning, document converter, queue, cache, email/SMS, KMS/HSM, timestamp/certificate, payment, and observability providers;
- pricing, currencies, metering, taxes, invoices, grace/suspension, and historical evidence access;
- measurable availability, latency, throughput, maximum file size, RPO, RTO, support, and incident objectives;
- the audit immutability/checkpoint mechanism and long-term evidence verification design.

Resolve the documentation conflicts by adopting separate canonical state machines:

- `Document`: `DRAFT`, `PREPARED`, `IN_PROCESS`, `FINAL`, `ARCHIVED`, `DISPOSED`;
- `Envelope`: `CREATED`, `SENT`, `ACTIVE`, `COMPLETED`, `DECLINED`, `EXPIRED`, `WITHDRAWN`, `FAILED`;
- `Participant`: `INVITED`, `OPENED`, `AUTHENTICATED`, `COMPLETED`, `DECLINED`;
- review/approval stages as workflow tasks rather than ambiguous document states;
- verification credential status independently as `VALID`, `EXPIRED`, `REVOKED`, `REPLACED`, `UNKNOWN`, or `UNVERIFIABLE`.

Confirm these values in an ADR before migrations are authored.

### 4.2 Repository hygiene

Before the first remote push:

- create `.gitignore` for `.env`, `.venv/`, `.idea/`, `__pycache__/`, `*.pyc`, `.DS_Store`, generated uploads/previews/QR codes, logs, coverage, build output, and local archives;
- unstage and remove generated/local artifacts from Git tracking without deleting the user's local working copies;
- replace `.env` with a safe `.env.example` containing names and placeholders only;
- inspect the existing `.env` and configuration values, rotate every credential that is real or reused, and document rotation completion without recording the secrets;
- eliminate hard-coded secret fallbacks and make production startup fail when required secrets are absent or known-development values are used;
- add a project manifest such as `pyproject.toml` plus a deterministic lock strategy, supported Python/PostgreSQL versions, lint/type/test configuration, and developer commands;
- add `README.md`, `CONTRIBUTING.md`, and `SECURITY.md` with local setup, security reporting, migrations, testing, and release expectations.

Do not push the current staged tree as-is. It contains credential-like material and generated artifacts.

### 4.3 Traceability and inventory

Add:

- `docs/requirements-traceability.csv` with all 182 IDs and columns for priority, module, owner, decision, implementation, migration, test, release, status, evidence, and exception;
- `docs/decisions/` for ADRs;
- `docs/threat-model.md`, `docs/data-inventory.md`, and `docs/assurance-matrix.md`;
- a route/model/template/migration inventory that marks each current artifact as retain, refactor, replace, or retire.

### 4.4 Baseline engineering platform

Add a testable local environment with PostgreSQL, private S3-compatible object storage, queue/cache, malware scanner, and isolated converter. Add development, test, staging, and production configuration classes. Add CI for formatting, linting, type checks, unit/integration/security tests, dependency and secret scanning, migration replay, and artifact creation.

Likely paths:

- `.github/workflows/ci.yml`, `.github/dependabot.yml`;
- `pyproject.toml`, lock file, `.env.example`, `.gitignore`;
- `compose.yml`, `Dockerfile`, worker image/command, health checks;
- `app/config/` or a refactored `config.py`;
- `tests/conftest.py` and test directory skeletons;
- `scripts/` for safe local setup, migration checks, and test execution.

Phase 0 exit gate: the repository is safe to publish, reproducible from a clean checkout, the migration chain is understood, all P0 requirements have owners and proposed tests, and unresolved launch blockers are explicit.

## 5. Target application structure

Preserve blueprints as transport adapters and move business rules into services and policies.

```text
app/
  blueprints/          HTML and versioned API transport
  models/              persistence models grouped by domain
  policies/            tenant, object, operation and contextual authorization
  schemas/             allowlisted request/response validation
  services/
    identity/
    documents/
    envelopes/
    stamps/
    trust/
    contracts/
    billing/
    notifications/
    audit/
    integrations/
  repositories/        tenant-safe query boundaries where useful
  tasks/               idempotent background jobs
  templates/           accessible server-rendered UI
  static/              first-party CSS and progressive JavaScript only
tests/
  unit/
  integration/
  security/
  e2e/
  accessibility/
  performance/
```

Provider-specific code must sit behind interfaces so object storage, scanning, email/SMS, payment, timestamp, certificate, and queue providers can be replaced and contract-tested.

## 6. Phase 1: identity, tenancy, authorization, and safe administration

### 6.1 Data model

Introduce opaque UUID/ULID public identifiers and add or normalize:

- `Tenant`, `Membership`, `Team`, `Role`, `Permission`, `RoleGrant`, `DelegationGrant`;
- `Session`, `RefreshToken` or persistent token-family/revocation records;
- verified contact, MFA credential/recovery, login/security event, invitation, and identity-assurance policy records;
- tenant policy revision and versioned organisation settings.

Every tenant-scoped table must carry `tenant_id`, appropriate composite indexes, and constraints. Historical attribution must survive membership deactivation and user deletion. Consider PostgreSQL row-level security only as defence in depth, not a replacement for application policy.

### 6.2 Policy and authentication layer

Add `app/policies/authorization.py` and domain predicates that evaluate actor, tenant, resource, operation, scope, policy revision, and context. Centralize tenant-safe repository queries and make absence/denial responses resistant to object enumeration.

Implement:

- verified email registration, one-time expiring activation and reset tokens;
- secure password hashing with a memory-hard KDF;
- privileged-role MFA using TOTP and/or passkeys;
- session/device history, revocation, rotation after password/privilege changes, and persistent JWT blocklisting if JWT remains;
- time-limited external invitations with least privilege;
- CSRF for cookie-authenticated actions, secure cookie policy, rate limiting, safe redirects, and complete security headers;
- audited role, policy, invitation, MFA, session, and break-glass actions.

Modify first:

- `app/__init__.py`, `app/extensions.py`, `config.py`;
- `app/blueprints/auth/routes/auth_api.py` and `auth_views.py`;
- `app/blueprints/users/`, `app/blueprints/organizations/`, `app/blueprints/system/`;
- `app/decorators/system.py` and every API blueprint;
- `app/models/user.py`, `organization.py`, and `system.py`.

Remove unsafe generic serializers and introduce allowlisted schemas under `app/schemas/`. Never serialize password material, tokens, signature images, raw evidence metadata, IP/device data, storage keys, or internal paths by default.

Phase 1 exit gate: every route and file endpoint has an explicit policy; anonymous, inactive, revoked, cross-tenant, IDOR, and role-escalation tests fail closed; privileged MFA and recovery are audited.

## 7. Phase 2: private document foundation

### 7.1 Storage and ingestion

Add private object storage and staged ingestion services:

- `app/services/documents/storage.py`;
- `app/services/documents/ingestion.py`;
- `app/services/documents/conversion.py`;
- `app/services/documents/preview.py`;
- provider adapters under `app/services/integrations/storage/` and `scanner/`.

The ingestion pipeline must:

1. authorize the tenant and entitlement;
2. stream to quarantine with size limits;
3. verify extension, declared MIME, magic bytes, structural validity, and filename safety;
4. calculate SHA-256 while streaming;
5. scan for malware;
6. convert DOCX/images in a non-root, resource-limited, no-egress worker;
7. produce script-free page previews and metadata;
8. atomically promote immutable objects and persist their manifests;
9. record audit and processing outcomes without logging content;
10. clean orphaned quarantine data only after reconciliation.

### 7.2 Document model

Refactor the current mutable `Document` into an identity/metadata aggregate plus immutable `DocumentVersion` records. Add `ObjectManifest`, processing job, classification, retention, legal-hold, tag, and safe extracted-text records.

Each version records tenant, version number, source object, canonical execution object, MIME, byte count, digest, creator, creation reason, schema version, and lifecycle state. An envelope always binds exactly one frozen version and digest. Corrections create a linked successor; they never alter completed bytes.

Modify:

- `app/models/documents/document.py`, `document_version.py`, related models;
- `app/blueprints/documents/api/document_api.py` and all document APIs;
- `app/blueprints/documents/views/document_views.py` and download/preview views;
- document templates and `app/static/js/document_editor.js`;
- `config.py` to remove public static upload and QR storage.

Use short-lived authorized delivery or application streaming for previews/downloads. Do not expose object keys or filesystem paths.

Phase 2 exit gate: supported files are private, scanned, validated, immutable, hashed, safely previewed, tenant-authorized, and recoverable; malformed/unsafe files are rejected; duplicate and partial-batch behaviours are tested.

## 8. Phase 3: audit, outbox, workers, and operational foundation

Introduce:

- append-only `AuditEvent` records with tenant, actor, delegated authority, action, resource, outcome, UTC time, request/correlation IDs, source, previous hash, and event hash;
- transactional `OutboxEvent`, idempotency record, processing job, and dead-letter records;
- worker tasks for scan/conversion, notifications, webhooks, PDF finalisation, reconciliation, retention, and evidence generation;
- correlation IDs propagated from HTTP through database events and workers;
- metrics for latency, conversion, queue lag, failures, signing, stamp approvals, verification mismatches, webhooks, storage, and billing;
- health/readiness endpoints that distinguish web, database, storage, queue, and dependency state;
- encrypted backup, object/version backup, key-reference recovery, restore, and reconciliation runbooks.

Likely paths:

- `app/models/audit.py`, `app/models/outbox.py`, `app/models/jobs.py`;
- `app/services/audit/`, `app/services/outbox.py`, `app/services/idempotency.py`;
- `app/tasks/`, worker entry point, scheduler configuration;
- `app/observability.py`, structured logging and redaction filters;
- `docs/runbooks/backup-restore.md`, `incident-response.md`, `worker-recovery.md`.

External provider calls must occur outside the originating database transaction. Retries use exponential backoff, explicit timeouts, idempotency/deduplication keys, maximum attempts, and observable dead-letter recovery.

Phase 3 exit gate: a database mutation and its asynchronous effects reconcile after worker crashes and retries; audit alteration is detectable; operators can observe and recover failures; a sampled document and its evidence dependencies survive a restore drill.

## 9. Phase 4: envelope execution, electronic consent, and evidence

### 9.1 Models and state machines

Add domain models for:

- `Envelope`, exact `DocumentVersion`, routing policy, assurance profile, expiry, immutable digest, and state;
- `Participant`, role, identity/contact binding, sequence/quorum, authentication requirement, and state;
- typed `Field` with page, normalized bounding box, assignee, validation, and required flag;
- hashed `InvitationToken`, consent record/version, authentication event, signature appearance reference, signature event, and finalisation record;
- certificate/timestamp/revocation material only for assurance profiles that actually support it.

Add services:

- `app/services/envelopes/workflow.py`;
- `app/services/envelopes/invitations.py`;
- `app/services/envelopes/signing.py`;
- `app/services/trust/finalization.py`;
- `app/services/trust/evidence.py`.

### 9.2 Workflow behaviour

Implement prepare, validate, preview, send, open, authenticate, consent, fill, sign, decline, remind, expire, cancel, withdraw, correct/reissue, and archive. Support sequential and parallel routing first; add quorum and conditional routing only after deterministic policy tests.

Every completion request must:

- re-authorize the participant and verify the token/challenge;
- validate the exact envelope/document digest and optimistic revision;
- require all assigned fields and explicit versioned consent;
- write the durable completion/finalisation record once;
- return the existing result for a repeated idempotency key;
- reject conflicting content under a reused key;
- emit audit/outbox events;
- generate a final PDF and machine-readable evidence manifest without mutating the issued input.

Replace generic CRUD behaviour in `app/blueprints/esignatures/` and `app/blueprints/documents/api/document_signature_api.py` with workflow commands and safe query endpoints. Build a reduced, accessible `/sign/<token>` experience.

Graphical drawn, typed, or uploaded appearances must be labelled accurately. Certificate-backed/PAdES support is a separate adapter and release gate, not an implication of storing an image.

Phase 4 exit gate: single, sequential, and parallel signing; decline, expiry, cancel, withdrawal/reissue; forwarded/expired token protection; ten repeated completions yielding one result; and independent digest/evidence checks all pass.

## 10. Phase 5: governed stamps, seals, and independent verification

### 10.1 Stamp governance

Refactor `app/models/estamp.py` into:

- stable `StampAsset` and immutable `StampRevision`;
- custodian/authorized-role assignments and expiring delegation grants;
- validity, intended-use, organisation, document-type, and approval policies;
- `StampRequest`, decision, escalation, and `StampImpression` records;
- attributable page/coordinates/rotation/scale, server timestamp, actor, authority chain, document version/digest, and final-object binding.

Add `app/services/stamps/policy.py`, `designer.py`, and `application.py`. Replace generic stamp CRUD routes with governed commands. Enforce self-approval prohibition when four-eyes policy applies and preserve historical impressions when an asset is suspended, retired, expired, or revoked.

### 10.2 Verification

Add `VerificationRecord` using a high-entropy opaque reference and QR URL. Add:

- `app/models/verification.py`;
- `app/services/trust/verification.py`;
- a public verification blueprint for `/verify/<reference>` and authenticated evidence access;
- uploaded-file digest comparison performed without retaining the file longer than policy permits;
- configured minimal disclosure, rate limiting, anti-enumeration, access logs, and anti-phishing copy.

The verifier must distinguish valid, digest mismatch, expired, revoked, replaced, unknown, and temporarily unverifiable states. It must report the actual assurance profile and avoid a generic boolean that overstates trust.

Phase 5 exit gate: unauthorized seal use and self-approval fail; approved impressions bind the correct revision/digest/actor/authority; altered bytes fail verification; all verifier states and disclosure policies pass; evidence access is authorized and audited.

## 11. Phase 6: templates, contracts, collaboration, and notifications

### 11.1 Authoring and templates

Add versioned templates, typed/escaped variables, controlled clauses, autosave with optimistic locking, publish/archive governance, field placement, and explicit preview before send. Existing issued envelopes remain bound to the template revision used at issuance.

### 11.2 Contracts

Add `Contract`, parties, owners, type/value metadata, linked document versions, review decisions, approval tasks, obligations, milestones, renewal/termination, amendments, and supersession lineage. Contract states and authorization remain distinct from document/envelope states.

### 11.3 Collaboration and notification

Add scoped internal/external comments, mentions, tasks, email/SMS notifications, reminders, frequency caps, delivery/open state, templates, retries, and user preferences. Internal comments must never leak to external signers.

Likely paths:

- `app/models/templates/`, `app/models/contracts/`, `app/models/notifications.py`;
- `app/services/templates/`, `contracts/`, `notifications/`;
- new blueprints and accessible UI routes for templates/contracts/tasks;
- provider adapters with contract tests.

Phase 6 exit gate: template revision retention, field-coordinate accuracy, contract approval/renewal/amendment flows, scoped comments, and retried notifications pass business UAT with audit and failure evidence.

## 12. Phase 7: subscriptions, APIs, integrations, and enterprise controls

Implement:

- data-driven Free, Pro, Business, and Enterprise plans without hard-coded prices;
- server-side entitlement service, seat/storage/document usage ledger, deduplicated metering, trials, upgrade/downgrade, grace, suspension, and cancellation;
- hosted/tokenized payment integration, invoices/receipts, reconciliation, taxes, currencies, and payment webhooks;
- continued read-only access to historical trust records after downgrade as policy permits;
- tenant-scoped service accounts, granular scopes, credential rotation/expiry, and sandbox separation;
- versioned REST API with OpenAPI 3.x, RFC 7807-style errors, cursor pagination, correlation IDs, deprecation policy, and idempotency keys;
- signed, replay-protected webhooks with retries and delivery history;
- approved OIDC/SAML SSO, JIT mapping, SCIM offboarding, reports, audit export, legal hold, operator break-glass, residency, and isolated deployment options.

Refactor `app/models/subscription.py` and `app/blueprints/subscriptions/` behind `app/services/billing/`. Add API schemas/contracts and integration adapters rather than embedding providers in domain models.

Phase 7 exit gate: entitlement bypass tests fail, usage/payment reconciliation balances, duplicate provider events do not double-charge, API contracts pass, SSO/SCIM lifecycle is tested, and historical evidence remains accessible according to policy.

## 13. Phase 8: higher assurance and regional production readiness

Only after the preceding controls are stable:

- integrate vetted timestamp, certificate, and protected key providers;
- implement standards-conformant PDF byte-range signatures and the approved PAdES profile through qualified libraries/providers;
- persist chain, timestamp, revocation, and long-term validation material;
- add localization, selectable timezones with UTC storage, jurisdiction-specific terms/consent, resident deployments, and assurance badges whose wording is counsel-approved;
- complete independent penetration, accessibility, evidence-validation, privacy, DR, performance, and legal reviews.

Phase 8 exit gate: jurisdiction and assurance claims have recorded sign-off; independent tools validate supported cryptographic evidence; revocation and historical validation behave correctly; production SLO, restore, security, privacy, and accessibility evidence is accepted.

## 14. Database migration plan

1. Inventory every table, route, relationship, seed record, migration, and stored upload.
2. Rebuild and rehearse the existing Alembic chain against a disposable database; repair multiple heads, invalid dependencies, or misleading revisions with documented corrective migrations rather than editing applied history.
3. Add new tables and nullable columns first. Preserve legacy columns while new services are introduced.
4. Backfill tenant membership, opaque IDs, document versions, and storage manifests only from defensible source data. Mark ambiguous records for remediation.
5. Never fabricate historic consent, approval, hashes, assurance, or audit events. Label legacy records with their actual provenance and capability.
6. Switch reads and writes one complete vertical slice at a time. Use temporary shadow reads/comparisons where valuable; avoid prolonged dual writes.
7. Add `NOT NULL`, uniqueness, foreign keys, check constraints, and indexes only after reconciliation.
8. Retire old serializers, CRUD endpoints, storage paths, and columns after UI/API migration and compatibility windows.
9. Keep releases backward-compatible with the previous application version where practical and define rollback limits for every migration.
10. Rehearse migration, backup, restore, application rollback, and post-restore idempotency before production.

## 15. User experience implementation

Apply the documented flat interface consistently:

- white/neutral surfaces, `#164C83` primary, `#D6DADE` borders, zero border radius, no gradients, glass, decorative shadows, pill badges, or coloured chips;
- persistent labels, visible focus, accessible error summaries, text plus icons for status, keyboard operation, appropriate touch targets, and mobile reflow at 320 CSS pixels;
- 224px collapsible desktop sidebar and full-height mobile drawer with permission-filtered navigation;
- dense full-width tables and inline filters instead of decorative dashboard cards;
- document canvas with thumbnails and one contextual panel; reduced signer flow for review, requirements, consent, complete/decline;
- text-readable verification outcomes and chronological plain-row audit timelines.

Refactor `app/templates/base.html`, `layouts/module_base.html`, partials, domain templates, `app/static/css/trustseal.css`, and progressive JavaScript. Remove or override Bootstrap/AdminLTE patterns that conflict with the UI contract. Verify Chromium, Firefox, and Safari plus keyboard, screen-reader, zoom, contrast, and narrow viewport behaviour.

## 16. Testing and verification programme

Every automated test name or metadata should reference relevant SRS IDs.

### 16.1 Test layers

- Unit: policy predicates, state transitions, tokens, hashes/manifests, coordinate transforms, consent, dates/timezones, entitlements, retry decisions.
- Integration: PostgreSQL constraints/transactions, Alembic replay, outbox, storage, scanner, converter, queue, email/SMS, KMS/timestamp/certificate, payment, and webhooks.
- Security: tenant isolation, IDOR, role escalation, session/token replay, CSRF, XSS, SSRF, path traversal, unsafe uploads, QR enumeration, sensitive serialization, forged webhooks, and rate limits.
- End-to-end: create/upload/prepare/review/approve/invite/consent/sign/stamp/finalize/verify/export/archive, including every deliberate failure path.
- Reliability: worker crash, client retry, duplicate callbacks, queue loss/backlog, provider outage, database/object restore, stale version, simultaneous finalisation, and recovery reconciliation.
- Accessibility: automated WCAG checks plus keyboard/screen-reader/high zoom/mobile manual scenarios for core flows.
- Performance: representative 10 MB previews, tenant search at 100k records, 200 concurrent pilot users, ordinary API p95, page navigation p95, queue lag, and finalisation throughput against approved targets.
- Legal evidence: independent recalculation of hashes, evidence manifest validation, consent/audit reconstruction, timestamp/certificate verification, revocation history, and deletion/offboarding preservation.

### 16.2 Mandatory acceptance scenarios

At minimum automate and record evidence for:

1. Organisation A cannot infer or access Organisation B data by ID, search, download, error response, job, export, or share.
2. Unauthorized staff cannot apply a company seal; four-eyes requester self-approval fails.
3. A forwarded or expired signing link cannot authorize the wrong recipient.
4. Modified issued/final bytes produce a digest mismatch while the original remains available.
5. Ten simultaneous/repeated completion requests create one final artefact and completion event.
6. Decline, expiry, cancel, withdrawal, correction/reissue, replacement, suspension, and revocation preserve evidence and expose the correct status.
7. Billing downgrade prevents new paid operations without deleting completed evidence.
8. Duplicate payment/webhook/notification deliveries have one effective outcome.
9. A restored environment does not resend old invitations or duplicate trust actions and can verify a sampled historical record.
10. A keyboard/screen-reader user can complete the core signing and verification flows at a 320px viewport.

### 16.3 Verification commands once the baseline exists

```sh
python -m compileall app
ruff check .
mypy app
pytest -q tests/unit
pytest -q tests/integration
pytest -q tests/security
flask db heads
flask db history
flask db check
docker compose config
docker compose build
pytest -q tests/e2e
```

CI must also run secret/dependency/container scanning, migration replay from an empty database and a representative prior release, accessibility checks, OpenAPI validation, and production artifact generation.

## 17. Release and operations gates

A phase or release advances only when:

- every in-scope requirement is linked to code, migration, tests, evidence, owner, and traceability status;
- all migrations have been reviewed and rehearsed with representative data;
- tenant isolation and authorization tests fail closed;
- success, denial, exception, concurrency, retry, and recovery paths pass;
- logs/metrics show the workflow without disclosing content, tokens, credentials, raw signature assets, or excess personal data;
- backups and restoration cover database, object manifests/versions, audit, configuration, and key references;
- the operational owner can identify, retry, reconcile, and close failed work;
- security, privacy, accessibility, performance, product, and legal reviewers approve the relevant claims;
- an expiring written risk acceptance exists for any allowed exception.

Production deployment uses controlled promotion, feature flags that do not reinterpret completed transactions, backward-compatible migrations, health-based rollout, documented rollback, and post-deployment verification.

## 18. Claims that must remain withheld

Until supported by implementation, independent validation, operations, and legal sign-off, do not claim that TrustSeal provides:

- universally legally binding or jurisdictionally valid electronic signatures;
- advanced, qualified, certificate-backed, PAdES, or independently trusted digital signatures;
- official, certified, government-authorized, or legally recognized seals;
- verified signer identity without an approved identity-assurance process;
- tamper-proof or immutable records instead of the precise implemented tamper-evidence model;
- independent verification before the public verifier and evidence validation operate end to end;
- regulatory compliance, guaranteed retention, residency, encryption, availability, RPO, RTO, or disaster recovery without accepted evidence.

Until then, describe the current application accurately as a prototype document-management system.

## 19. Recommended delivery sequence and dependency map

```text
Phase 0: decisions + safe repository + reproducible platform
    -> Phase 1: identity + tenancy + policy
        -> Phase 2: private immutable document foundation
            -> Phase 3: audit + outbox + workers + recovery
                -> Phase 4: envelope signing + consent + evidence
                    -> Phase 5: governed stamps + verification
                        -> Phase 6: templates + contracts + notifications
                            -> Phase 7: billing + APIs + enterprise
                                -> Phase 8: high assurance + regional production
```

Work may overlap only when dependencies are stable. UI prototypes, provider evaluations, and test harnesses can proceed in parallel, but no downstream feature may bypass tenant policy, immutable versions, audit/outbox, or evidence contracts.

## 20. Definition of complete implementation

TrustSeal is complete only when all approved requirements in the traceability matrix are implemented, tested, accepted, operated, and supported. A screen or CRUD route alone is not completion.

For every capability, completion means:

- the intended actor can finish the whole journey;
- unauthorized actors and cross-tenant access are blocked;
- state, document bytes, evidence, and audit remain consistent under failure and concurrency;
- completed records remain independently verifiable to the accurately stated assurance level;
- privacy, accessibility, retention, and legal decisions are enforced;
- monitoring, recovery, support, and migration procedures are proven;
- customer-facing claims match the evidence and approvals.
