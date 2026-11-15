# TrustSeal threat model

**Revision:** 2026-11-15, post Milestone 3.
**Scope:** Milestones 1–3 surface — orchestration, repositories,
idempotency, webhooks, KMS, object-store, metrics, MFA, SSO, SCIM,
refresh-token families, password lifecycle, verification/evidence UI.

The model uses STRIDE (Spoofing, Tampering, Repudiation, Information
disclosure, Denial of service, Elevation of privilege). Each entry
has a stable rule-id so counter-measures and tests can reference it.

---

## 1. Trust boundaries

| # | Boundary                                   | Crossing                                                |
|---|--------------------------------------------|---------------------------------------------------------|
| B1 | Public Internet ↔ Flask app               | HTTPS + JWT or anonymous verification form              |
| B2 | Flask app ↔ PostgreSQL                    | Postgres connection, RLS not enabled (app-layer policy) |
| B3 | Flask app ↔ Object store (S3 or local)    | Pluggable `ObjectStore` interface                       |
| B4 | Flask app ↔ KMS                           | `Signer` interface; private key never in Python memory  |
| B5 | Flask app ↔ Outbox worker                 | Shared Postgres row + lease fencing                     |
| B6 | Flask app ↔ Webhook receiver              | Outbound HMAC-signed JSON                               |
| B7 | SCIM 2.0 client ↔ Flask app               | Bearer token tied to tenant service account             |
| B8 | OIDC IdP ↔ Flask app                      | OAuth2 code flow + id_token signature verification       |

## 2. STRIDE catalogue

### Spoofing

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| S1  | Stolen access token used after password change            | `change-password` revokes every refresh family; access JWT jti added to `RevokedToken`.             | `tests/test_password_change.py`                | low      |
| S2  | Replayed refresh token after rotation                     | Family rotation; replaying an old jti revokes the family (`reuse_detected`) and emits security event.| `tests/test_refresh_rotation.py`                | low      |
| S3  | TOTP code captured and replayed                           | `last_counter` monotonic bookkeeping refuses any counter ≤ last successful.                           | `tests/test_mfa.py::test_replay_of_same_totp_rejected` | low |
| S4  | OIDC id_token issued by unauthorised IdP                  | Discovery issuer matched to registered row; id_token signed with JWKS fetched per-login.              | `tests/test_oidc_sso.py::TestCallback`         | low      |
| S5  | Impersonation via untrusted email domain                  | `trusted_email_domains` gate; `email_verified=false` rejected.                                        | `tests/test_oidc_sso.py`                       | low      |
| S6  | SCIM bearer token leaked in logs                          | Only token hash stored; access log filters authorization header; secret disclosed once on mint.      | manual audit; `tests/test_scim.py`             | medium   |
| S7  | Webhook sender impersonation                              | HMAC-SHA256 with timestamp window `REPLAY_WINDOW_SECONDS=300`; constant-time compare.                | `tests/test_webhooks.py::TestSignatureProtocol`| low      |

### Tampering

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| T1  | Finalized PDF bytes altered post-issuance                 | Immutable row + object_key; SHA-256 recorded; S3 object-lock in COMPLIANCE mode for `final/`.       | `tests/integration/test_platform_pdf_roundtrip.py` | low |
| T2  | Evidence dossier mutated                                  | `trustseal_reject_snapshot_mutation()` PostgreSQL trigger on append-only tables.                     | migrations/versions/*                          | low      |
| T3  | Audit-event chain broken                                  | Chained-hash checkpoint integrity probe surfaces breaks in the evidence viewer.                       | `tests/test_evidence_views.py::test_integrity_chain_break_surfaced` | medium |
| T4  | Idempotency reuse to overwrite stored response            | `(tenant_id, endpoint, key)` unique; body-hash check returns 409 on mismatch.                        | `tests/test_idempotency.py`                    | low      |
| T5  | Outbox payload modified before dispatch                   | Lease fencing on claim + idempotency key; payload hashed as part of webhook signature.                | `tests/test_outbox_worker.py`                  | low      |

### Repudiation

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| R1  | Signer denies acknowledging the document                  | `SignerDecision` + detached endorsement + review receipt chain; all three must verify in orchestrator.| `tests/test_envelope_orchestrator.py`          | low      |
| R2  | Operator denies sealing a PDF                              | `FinalizedPdf.issued_by_id` + outbox event `platform.pdf.sealed.authorized_operator`.                | orchestrator tests                             | low      |
| R3  | Tenant denies rotating a webhook secret                   | `WebhookEndpoint.updated_at` + mandatory `rotate` audit entry (idempotent key).                       | `tests/test_webhooks.py`                       | medium   |

### Information disclosure

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| I1  | Cross-tenant access via guessed id                        | `TenantScopedRepository` + `@require_policy`; 404 anti-enumeration contract (ADR 0003).              | `tests/security/test_tenant_isolation.py`      | low      |
| I2  | Error responses leak traceback / SQL                      | RFC 7807 problem+json handler strips Werkzeug defaults and unhandled exception messages.             | `tests/test_problem_details.py::test_unhandled_exception_hides_internals` | low |
| I3  | Structured logs contain tokens / PII                      | `_redact_processor` strips known-sensitive keys and summarises byte bodies.                           | `tests/test_observability.py::TestRedaction`   | low      |
| I4  | `/metrics` discloses per-tenant counts to anonymous users | Admin-only JWT gate + role check.                                                                    | `tests/test_metrics.py::TestEndpointAccess`    | low      |
| I5  | Timing side-channel on SCIM bearer                        | Token digest lookup is constant-time via SQL equality on index; `hmac.compare_digest` helper exposed.| `tests/test_scim.py::TestAuthentication`       | medium   |

### Denial of service

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| D1  | Anonymous public verify spam                              | In-process rate limiter (10 req / 60 s / client); edge rate limit documented.                        | `tests/test_verify_view.py::TestRateLimiting`  | medium   |
| D2  | Oversized PDF upload                                      | `MAX_PDF_BYTES=16 MiB` guard; connection terminated on overflow read.                                 | `tests/test_platform_pdf_seal.py`              | low      |
| D3  | Outbox worker thrash on failing handler                   | Exponential backoff on empty queue; lease fencing prevents duplicate concurrent work.                 | `tests/test_outbox_worker.py`                  | low      |
| D4  | Hostile webhook receiver stalls dispatcher                | `REQUEST_TIMEOUT_SECONDS=10`; max `MAX_RETRIES=6`; `dead` state after exhaustion.                     | `tests/test_webhooks.py::TestDispatch`         | low      |
| D5  | Idempotency table unbounded                               | `prune_expired` CLI; 24 h default TTL.                                                                | `tests/test_idempotency.py::TestPruning`       | low      |

### Elevation of privilege

| id  | risk                                                      | mitigation                                                                                           | tests / artifacts                              | residual |
|-----|-----------------------------------------------------------|------------------------------------------------------------------------------------------------------|------------------------------------------------|----------|
| E1  | Operator seals an envelope they prepared                  | `_authorize_operator` refuses when operator id == envelope creator id or operator is a participant.   | `tests/test_envelope_orchestrator.py`          | low      |
| E2  | Admin password change hijacks another account             | `change-password` is self-service (no target id in URL); `active_token_user()` resolves the caller only.| `tests/test_password_change.py::test_endpoint_changes_only_the_callers_password` | low |
| E3  | SCIM client attempts to assign roles outside its tenant   | Users table has no role mutation path through SCIM; roles managed separately.                        | SCIM API reads/writes ``active``/name/email only | low   |
| E4  | OIDC user escalation into another tenant                  | Email → existing user lookup; user already bound to a different tenant → `OidcCallbackError`.         | `tests/test_oidc_sso.py`                       | low      |
| E5  | Metrics gate bypass via Flask-Login session               | Metrics route requires JWT (`current_actor`), not a web session.                                      | `tests/test_metrics.py`                        | low      |

## 3. Explicit residual gaps

The following gaps are acknowledged and tracked. They are **not**
blockers for the current functionality but must close before TrustSeal
claims any qualified assurance tier.

- **G1** — Edge rate limiting is in-process only. A regional edge
  (Cloudfront + AWS WAF or equivalent) is required before public
  verification handles production traffic.
- **G2** — PostgreSQL row-level security is not enabled. The
  application-layer `TenantScopedRepository` is authoritative; RLS is
  a planned defence-in-depth layer.
- **G3** — Idempotency records are per-tenant and not cross-region;
  failover produces a window in which a retried mutation would run
  twice. DR runbook §"Known gaps" reiterates this.
- **G4** — pyHanko integration still uses PKCS#12 directly. The
  `AwsKmsSigner` is wired for detached JSON signatures but the PDF
  seal path is a separate migration ticket (ADR 0001 §6).
- **G5** — The accessibility probe is narrow by design. Axe-core
  Playwright coverage is planned.
- **G6** — Independent penetration test and evidence-validation
  third-party review are both pending before any assurance claim.

## 4. Review log

| date       | reviewer | summary                                               |
|------------|----------|-------------------------------------------------------|
| 2026-11-15 | eng     | Initial threat model aligning with Milestones 1–3.    |
