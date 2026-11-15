# TrustSeal Gap Remediation and Professional Implementation Plan

**Date:** 2026-11-14
**Author:** Engineering review (post origin/main sync at commit `54e8e0a`)
**Status:** Actionable remediation plan — complements, does not replace, `docs/IMPLEMENTATION_PLAN.md`.

## 1. Baseline and assessment

The last 180-file merge landed a substantial cryptographic and evidence stack (PAdES DSS, RFC 3161 TSA validation, OCSP, CRL, delegated responders, validation dossiers, platform signer chain, outbox lease fencing, private storage scaffolding, evidence preservation, graphical stamps, review receipts, 54 total migrations, 133 tests). The repository now holds roughly the right ingredients for a trust service. The remaining gaps are integration, surface, isolation, and operability — not primitives.

**What is actually built**
- Cryptographic primitives: TSA chain validation, OCSP (including delegated responders), CRL inventory, PAdES DSS, PDF platform signer chain, long-term validation material capture.
- Domain: signing envelopes, signer intent/challenge, signer crypto endorsement, review receipts, stamp custody, stamp designs, stamped PDF derivatives, validation dossiers, evidence preservation (holds, checkpoints, timestamps).
- Policy guard: `app/policies/api_access.py` deny-by-default for trust-critical legacy mutations.
- Persistence: 54 Alembic revisions, legacy-schema CI baseline script, new tables fully migrated.
- Ops stubs: CLIs for outbox drain, OCSP, CRLs, timestamp, preservation, PDF seal/DSS/stamping.
- Tests: 133 files across unit and `tests/integration/*`, backend CI workflow.

**What is not built (summary)**
- No user-facing surface for 80% of the new backend capability.
- No background worker runtime; outbox depends on operator CLI invocation.
- No cloud object storage adapter; private storage is local filesystem only.
- No KMS/HSM; signing keys are PKCS#12 files referenced by env.
- Per-resource RBAC is not enforced uniformly; central policy is a deny-mutations guard, not scoped authorization.
- No structured logging, metrics, tracing, or correlation IDs.
- Public verification is cert-fingerprint only; no `/verify/<ref>` page or dossier UI.
- End-to-end signing workflow is tested only in fragments; no full envelope → finalize → verify integration run.
- No multi-tenant leakage tests, no browser/e2e tests.

## 2. Gap inventory (prioritized)

| # | Gap | Severity | Area | Owner surface |
|---|---|---|---|---|
| G1 | No end-to-end envelope orchestration (envelope → intent → crypto → receipt → PDF seal → DSS → dossier) | P0 | Domain integration | `app/services/envelopes/`, `app/services/trust/` |
| G2 | Per-resource RBAC not enforced; `api_access.py` is an interim denylist | P0 | Security | `app/policies/`, every blueprint |
| G3 | No multi-tenant isolation tests (horizontal IDOR unverified) | P0 | Testing | `tests/security/` |
| G4 | Private object storage is local filesystem only; no S3/MinIO adapter | P0 | Storage | `app/services/documents/private_storage.py` |
| G5 | Signing keys loaded from PKCS#12 on disk; no KMS/HSM; no key rotation | P0 | Secrets | `app/services/platform_pdf_seal.py`, `platform_signer_chain.py` |
| G6 | Outbox has no daemon/supervisor; events depend on manual CLI drain | P0 | Reliability | `app/cli/outbox.py`, deployment |
| G7 | No `/verify/<ref>` public page; verification is POST-only API | P0 | UX | `app/blueprints/trust/`, templates |
| G8 | No signer landing/sign flow (`/sign/<token>`); API only | P0 | UX | `app/blueprints/envelopes/views/` |
| G9 | No evidence dossier viewer / validation UI / audit console | P1 | UX | `app/blueprints/trust/views/` |
| G10 | No PDF viewer, signing canvas, QR renderer, or field-placement UI | P1 | UX | `app/static/`, build toolchain |
| G11 | No structured logging, metrics, tracing, correlation IDs | P1 | Observability | `app/__init__.py`, new `app/observability.py` |
| G12 | `backend-ci.yml` has no security scan, dependency audit, migration smoke test; PDF finalization disabled in CI | P1 | CI | `.github/workflows/` |
| G13 | Public PDF verification validates only cert fingerprint, not chain/timestamp/revocation binding | P1 | Trust | `app/blueprints/documents/api/public_pdf_verify_api.py` |
| G14 | No idempotency key middleware for trust-critical mutations | P1 | API | `app/services/idempotency.py` (new) |
| G15 | Legacy + new migration schema split is fragile (26 tables excluded from legacy baseline) | P1 | Migrations | `scripts/ci_legacy_schema_baseline.py` |
| G16 | No OpenAPI schema / contract tests / RFC 7807 errors / cursor pagination | P2 | API | `app/schemas/`, `openapi.yaml` |
| G17 | No webhook adapter (signed, replay-protected, with delivery history) | P2 | Integrations | `app/services/webhooks/` |
| G18 | No MFA / passkey / refresh-token family rotation | P2 | Identity | `app/blueprints/auth/` |
| G19 | No SSO (OIDC/SAML) / SCIM | P3 | Enterprise | new blueprints |
| G20 | No disaster recovery / backup / restore drill | P2 | Ops | runbooks + scripts |
| G21 | No performance / load testing; no accessibility checks | P2 | QA | `tests/performance/`, `tests/accessibility/` |
| G22 | No PII/content redaction in logs; retention for revoked tokens and audit not implemented | P2 | Privacy | audit pipeline |

## 3. Remediation workstreams

The gaps split into eight workstreams. Each has a concrete deliverable, touched paths, exit gate, and a size estimate (S ≤1 week, M 1–3 weeks, L 3–6 weeks for a single engineer).

### Workstream A — Trust workflow orchestration (G1, G13, G14)

**Deliverable:** A single `EnvelopeOrchestrator` service that runs a signing transaction end to end and emits one durable evidence bundle per envelope.

Add:
- `app/services/envelopes/orchestrator.py` — composes `signer_intent`, `signer_crypto`, `signing_receipts`, `platform_pdf_seal`, `pdf_dss`, `rfc3161_timestamp`, `ocsp_evidence`, `chain_crl_inventory`, `validation_dossier`, `evidence_preservation`. One state machine; one DB transaction boundary per step; all provider calls outside the DB transaction.
- `app/services/idempotency.py` + `IdempotencyRecord` model and migration — scoped by `(tenant_id, endpoint, key)`, returns the stored response for repeated keys, rejects body conflicts on reused keys.
- `app/services/trust/verification.py` + public `/verify/<ref>` service that checks: structural PDF, embedded signature byte-range, platform cert chain against pinned trust root, DSS/VRI presence, TSA signature and chain, OCSP/CRL freshness, digest match against canonical version.
- Replace `public_pdf_verify_api` fingerprint-only logic with a call into `trust.verification`; return the full RFC 7807 verdict (`valid`, `mismatch`, `revoked`, `replaced`, `expired`, `unknown`, `unverifiable`) and the actual assurance tier.

Exit: one integration test `tests/integration/test_envelope_full_cycle.py` drives envelope creation → participant invite → challenge → decision → crypto endorsement → finalize → DSS → dossier → public verification pass and tamper-reject.

Size: **L**.

### Workstream B — Tenant isolation and authorization (G2, G3)

**Deliverable:** Deny-by-default per-resource authorization and a dedicated security test suite proving cross-tenant access is impossible.

Add:
- `app/policies/authorization.py` with domain predicates `can_read(actor, resource)`, `can_write(actor, resource, op)`, `can_sign(actor, envelope, participant)`, `can_admin(actor, tenant)`.
- Tenant-safe repository layer under `app/repositories/` that always joins on `tenant_id` and refuses unscoped queries; every blueprint queries through it.
- `@require_policy(predicate)` decorator replacing the interim guard for mutations and lifting the deny-mutation flag per resource as policies are wired in.
- `tests/security/test_tenant_isolation.py` — matrix test covering: documents, versions, blobs, envelopes, participants, signers, stamp assets, custody records, dossiers, preservation retentions, OCSP/CRL evidence, review receipts, DSS derivatives, stamp impressions. Every table listed must have two adjacent fixture tenants with resources; every GET/POST/PATCH/DELETE must return 404 to the other tenant.
- `tests/security/test_rbac_matrix.py` — roles × actions × resources.

Exit: 404 (not 403) on every cross-tenant read; policy decorator attached to every route; CI blocks a PR that adds a route without `@require_policy`.

Size: **L**.

### Workstream C — Storage and secrets (G4, G5)

**Deliverable:** Pluggable object storage with an S3/MinIO adapter and KMS-backed signing keys.

Add:
- `app/services/integrations/storage/base.py`, `s3.py`, `local.py` with a common `ObjectStore` interface (`put`, `get`, `exists`, `presign_get`, `delete`, `list_versions`, `head`).
- Refactor `app/services/documents/private_storage.py` to depend on `ObjectStore`; select implementation via `OBJECT_STORAGE_BACKEND` env.
- S3 server-side encryption with KMS key, object-lock (compliance mode) for final and evidence objects, immutable versioning, inventory-based reconciliation.
- `app/services/integrations/kms/base.py`, `aws_kms.py`, `local_pkcs12.py`. Replace `_load_signer()` in `platform_pdf_seal.py` and `platform_signer_chain.py` with `KmsSigner(key_arn)` producing CMS signatures without exposing the private key to the process.
- Key rotation policy doc under `docs/decisions/0001-key-rotation.md`; rotation CLI `app/cli/keys.py` that enrolls a new signer certificate without invalidating historical dossiers.

Exit: integration test spins up MinIO + localstack KMS, signs a PDF end to end without the private key ever touching Python memory. Configurable to run against real AWS in CI nightly.

Size: **L**.

### Workstream D — Background workers and observability (G6, G11, G22)

**Deliverable:** A supervised background worker runtime and production-grade observability.

Add:
- Worker: `app/workers/outbox_worker.py` running `drain()` in a loop with lease fencing (already in migration `a6b7d820e3f1`), structured logs, exponential backoff, dead-letter table (`event_delivery` already has state; add `event_dead_letter` migration), metrics counter per outcome.
- Container: `Dockerfile.worker`, `compose.yml` adds web, worker, postgres, redis, minio, localstack.
- Supervisor: a `trustseal-worker` systemd unit template under `deploy/systemd/`; Kubernetes deployment manifest under `deploy/k8s/`.
- Observability: `app/observability.py` wires `structlog` with content-redaction processors (document bytes, tokens, signatures, PII never logged), `prometheus_flask_exporter` on `/metrics`, OpenTelemetry tracer with Flask + SQLAlchemy + requests instrumentation, `X-Request-ID` middleware that propagates to outbox events and worker spans.
- Audit retention and token-revocation retention CLIs: `app/cli/retention.py prune-revoked-tokens`, `prune-audit --older-than`.

Exit: a document signed on the web pod produces a span that traces into the worker pod's DSS/dossier job; metrics show p95 per endpoint; no document content or tokens appear in any log line (enforced by a redaction unit test).

Size: **M**.

### Workstream E — Public-facing UI (G7, G8, G9, G10)

**Deliverable:** Four user surfaces the backend already supports but the UI does not expose.

E1. **Signer landing** — `app/blueprints/envelopes/views/sign_views.py` + templates under `app/templates/envelopes/sign/` implementing `/sign/<invitation_token>` with:
   - Token resolution through hashed lookup + anti-enumeration delay.
   - Participant authentication challenge (email OTP or passkey).
   - Document viewer (PDF.js, served from vendored assets, no CDN) with field overlay.
   - Consent capture with versioned wording, timestamp, user-agent, IP hash.
   - Signing canvas (SignaturePad, vendored) for drawn appearance.
   - Decline path with reason capture.
   - All field completion and decision calls route through `signer_intent_api` + `signer_crypto_api`.

E2. **Public verification** — `app/blueprints/trust/views/verify_views.py` + `/verify/<reference>` page showing: issuer, issue time, document title (per disclosure policy), status badge (text + icon, not color-only), evidence download link for authenticated viewers, uploaded-file hash comparison form, QR code renderer for reciprocal verification URL.

E3. **Evidence dossier viewer** — `/documents/<id>/evidence` authenticated view rendering the dossier as a navigable tree: canonical digest, TSA chain, OCSP responses (with freshness), CRL entries, DSS/VRI contents, chain certificates (with issuer/subject/validity), preservation holds, checkpoints, replay of every audit event with chained hash integrity check.

E4. **Stamp custody and operator consoles** — `/estamp/custody` showing asset revisions, custodian assignments, approval queue, impression history; `/system/evidence` showing holds, dossiers awaiting countersign, outbox dead-letter queue, failed worker jobs.

Frontend baseline:
- Add `package.json` + Vite + esbuild for a thin JS bundle (no SPA framework); vendor PDF.js, SignaturePad, qrcode.js locally.
- Preserve the flat enterprise aesthetic from the UX spec (no gradients, zero radius, `#164C83` primary, text-with-icon status).
- Playwright test suite `tests/e2e/` covering: sign flow happy path, decline, expired token rejection, verification valid/mismatch/revoked, evidence viewer renders dossier, operator console lists dead letters.

Exit: a user can sign, a counterparty can verify by reference and by upload, a compliance officer can inspect the dossier, an operator can clear the dead-letter queue — all without touching the API directly.

Size: **L** (E1 alone is M).

### Workstream F — CI, migrations, and schema (G12, G15)

**Deliverable:** CI that blocks regressions and a reconciled migration chain.

Add to `.github/workflows/`:
- `backend-ci.yml`: enable `PDF_FINALIZATION_ENABLED: true` in a dedicated job with MinIO + localstack KMS services. Split unit, integration, security, migration jobs.
- `security.yml`: `pip-audit`, `bandit`, `safety`, `trivy` for container images, `gitleaks` for secrets.
- `migrations.yml`: fresh PostgreSQL → `flask db upgrade` → `flask db downgrade base` → `flask db upgrade`; also upgrade from the last tagged release's schema dump captured under `tests/fixtures/schemas/`.
- `openapi.yml`: validate `openapi.yaml` and run Dredd contract tests against the running app.

Migrations:
- Collapse the legacy/new split: add `scripts/freeze_legacy_baseline.py` that generates a new consolidated baseline migration from the current head, mark pre-legacy migrations as superseded, remove the 26-table exclusion in `ci_legacy_schema_baseline.py`.
- Add `tests/integration/test_migration_replay.py` covering clean install, upgrade from baseline, idempotent reruns, and NOT NULL/FK constraint survival.

Exit: a red CI run on any of: missing policy decorator, new route without schema, failed migration downgrade, dependency vuln above threshold, uncovered security test.

Size: **M**.

### Workstream G — API contract and integrations (G14, G16, G17)

**Deliverable:** Stable versioned API with typed schemas and signed webhooks.

Add:
- `app/schemas/` Marshmallow schemas per endpoint, generated from OpenAPI via `apispec`.
- `/api/v1` prefix, RFC 7807 error handler already partially in `app/errors/handlers.py` — extend to every blueprint.
- Cursor pagination helper `app/services/pagination.py`.
- Idempotency key middleware reading `Idempotency-Key` header, scoped by tenant + route.
- `app/services/webhooks/` dispatcher: HMAC-SHA256 signed payloads, `webhook_endpoint`, `webhook_delivery` tables, replay-protection via `timestamp + nonce`, dead-letter integration with the outbox worker, delivery-history read API.
- `app/blueprints/integrations/service_account_api.py` — tenant-scoped service accounts with granular scopes and rotation.

Exit: an external integration can subscribe to envelope events, verify signatures with the published secret, replay deliveries from the history endpoint, and the OpenAPI spec round-trips through Dredd.

Size: **M**.

### Workstream H — Identity hardening and enterprise (G18, G19, G20, G21)

**Deliverable:** Baseline identity hardening and enterprise readiness.

Add:
- TOTP MFA (`pyotp`) + passkey/WebAuthn (`webauthn` lib) for platform-admin and stamp-custodian roles. UI in `app/templates/auth/mfa/`.
- Refresh token family rotation with reuse detection; persistent revocation already in place.
- Password-change and role-change revocation of all sessions.
- OIDC SSO adapter (`authlib`) + optional SAML (`python3-saml`). SCIM 2.0 user/group provisioning API.
- Disaster recovery: `scripts/backup.sh` (pgBackRest or `pg_basebackup` + WAL archiving + S3 inventory), `docs/runbooks/restore.md`, a quarterly restore drill script, `scripts/dr_rehearsal.sh`.
- Performance: `tests/performance/locustfile.py` with scenarios for 200 concurrent signers, bulk verification, dossier read.
- Accessibility: `axe-core` integration in Playwright tests against sign and verification pages at 320 CSS px.

Size: **L** (SSO alone is M; DR drill recurring).

## 4. Milestone plan

Three two-month milestones deliver production readiness for the prototype's actual contract (platform-sealed PDFs with evidence dossiers).

### Milestone 1 — "Correctness floor" (weeks 1–8)
Blocks that make the current backend safe to expose at all.
- Workstream A (orchestrator + idempotency + real public verification).
- Workstream B (tenant isolation + RBAC + security tests).
- Workstream F migration reconciliation + CI security gates.
- Workstream D worker runtime (basic daemon + structured logging; metrics/tracing pushed to M2).

**Exit gate:** no route without a policy decorator, no cross-tenant leak, one end-to-end signing integration test passes, outbox drains in a container without operator intervention, CI blocks dependency vulns and migration regressions.

### Milestone 2 — "User surface and ops" (weeks 9–16)
Everything the backend can already do becomes reachable without curl.
- Workstream E all four UIs (sign, verify, evidence, operator console) with Playwright coverage.
- Workstream D finish observability (Prometheus + OTel + redaction).
- Workstream C storage adapter (S3/MinIO) in production path; KMS adapter in a dedicated job in CI.
- Workstream G OpenAPI + RFC 7807 everywhere + webhook dispatcher.

**Exit gate:** a counterparty can sign and a third party can verify entirely through the browser; dossier is downloadable and independently verifiable with `examples/verify_checkpoint_offline.py`; traces span web → worker; webhook delivery history is queryable.

### Milestone 3 — "Enterprise readiness" (weeks 17–24)
Features required to sell to regulated tenants.
- Workstream C KMS/HSM in production (AWS KMS or CloudHSM), object-lock with compliance retention.
- Workstream H MFA, SSO, SCIM, DR drill, performance baseline, accessibility compliance.
- Final threat model refresh; independent penetration test; evidence-validation third-party review.

**Exit gate:** externally penetration-tested, DR restore demonstrated with reconciled audit, SSO and MFA in production, accessibility audit clean on signing and verification flows, performance SLOs met at 200 concurrent signers.

## 5. Ordering invariants

Regardless of parallelism, the following dependencies must hold:

1. Tenant isolation (B) lands before any new UI surface (E) is exposed.
2. Storage adapter (C) and KMS (C) land before production deploy; local filesystem + PKCS#12 is dev-only.
3. Orchestrator + idempotency (A) land before webhook dispatch (G17); otherwise retries produce duplicates.
4. Observability (D11) lands before scale (H21); you cannot tune what you cannot see.
5. Migration reconciliation (F15) lands before SSO/SCIM schema additions (H19); do not pile features on an unstable baseline.

## 6. Acceptance scenarios (gate for calling it "done")

The ten scenarios in `IMPLEMENTATION_PLAN.md §16.2` remain the master gate. The following are the concrete tests that must pass for *this* remediation cycle:

1. `tests/integration/test_envelope_full_cycle.py` — prepare, invite, authenticate, challenge, decide, endorse, finalize, DSS, dossier, verify.
2. `tests/security/test_tenant_isolation.py` — every table, every method, two tenants, all cross-access returns 404.
3. `tests/integration/test_idempotency.py` — ten concurrent completions produce one final artifact and one completion event; conflicting body on reused key returns 409.
4. `tests/integration/test_public_verification.py` — valid, tamper-mismatch, expired, revoked, replaced, unknown each return the correct verdict and assurance tier.
5. `tests/integration/test_storage_s3.py` — same test suite against local and S3 backends.
6. `tests/integration/test_kms_signing.py` — platform PDF seal works without the private key existing as bytes in the Python process.
7. `tests/integration/test_outbox_worker.py` — worker survives DB restart, duplicate deliveries have one effective outcome, dead-letter is draining.
8. `tests/e2e/test_sign_flow.py` + `test_verify_flow.py` — Playwright happy paths and principal failure paths.
9. `tests/integration/test_migration_replay.py` — clean install, upgrade from previous tag, downgrade, idempotent rerun.
10. `tests/performance/locustfile.py` — 200 concurrent signers at p95 within SLO.

## 7. What will remain out of scope

The following stay deferred until the three milestones close:

- Standards-conformant signer-side PAdES (as opposed to platform-sealed PDFs). Users still receive a platform seal with evidence of their consent; qualified signer certificates are Phase 8 work.
- Contract lifecycle management (obligations, renewals, amendments) — exists in the SRS but is adjacent to trust correctness.
- Jurisdiction-specific legal assurance claims.
- Localization and residency controls beyond UTC storage.

These remain documented in `IMPLEMENTATION_PLAN.md` phases 6–8 and are not blocked by this plan; they can proceed in parallel after Milestone 1 lands.

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| KMS integration delays Milestone 3 | M | H | Build `KmsSigner` interface and keep `LocalPkcs12Signer` as fallback; ship Milestone 2 without KMS in prod if needed. |
| Tenant isolation refactor breaks existing APIs | H | H | Repository layer is additive; migrate blueprint by blueprint behind a feature flag per resource. |
| Playwright tests become flaky | M | M | Run against a seeded database per test, use trace-on-failure, pin browser versions. |
| Migration consolidation loses historic context | L | H | Keep the full chain; introduce a baseline marker, do not delete revisions. |
| Vendored PDF.js / SignaturePad bloat | M | L | Use fingerprinted assets with CSP, measure bundle weight in CI. |

## 9. Immediate next actions (first week)

1. Create ADRs under `docs/decisions/`: `0001-key-rotation.md`, `0002-object-store.md`, `0003-tenant-isolation-strategy.md`, `0004-idempotency.md`.
2. Scaffold `app/repositories/` and `app/policies/authorization.py`.
3. Add `tests/security/test_tenant_isolation.py` with fixtures for two adjacent tenants and failing tests for every existing API — red CI is the baseline to drive the fix.
4. Scaffold `app/services/envelopes/orchestrator.py` with the state machine signature; wire the first slice (envelope → finalize) and leave the rest as explicit TODOs.
5. Add `Dockerfile.worker` and a `compose.yml` entry; run the outbox worker locally for a week.
6. Open a milestone board tracking the workstreams above against the three milestones.

---
**End of plan.** This document supersedes none of the prior checkpoint docs under `docs/BACKEND_*_2026-11-13.md`; it consolidates them into an executable sequence.
