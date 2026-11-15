# Remaining Gaps — 2026-11-15

All code-addressable gaps from the 2026-11-14 remediation plan are
closed. What remains is **process**, **governance**, and **third-party
engagements** that cannot be implemented inside this repository. Each
item below carries an owner, required artefact, and the first evidence
that will close it.

## G3 — Cross-region idempotency replay

**Status:** single-region ON CONFLICT upsert is production grade. Cross-
region active-active replay is a *deployment topology* decision, not a
code change — a second region requires either (a) global Postgres (Aurora
Global, Spanner, CockroachDB) or (b) a Redis-backed idempotency cache
with eventual convergence. Both change the operating model.

**Owner:** Platform infrastructure.

**Closes when:** a Target Operating Model is signed off that names the
chosen replica topology; the service layer already accepts a pluggable
idempotency backend (`app.services.idempotency.IdempotencyRepository`).

## G5 — Automated accessibility (axe-core + Playwright)

**Status:** `tests/test_accessibility.py` covers the static HTML
templates with pytest-selenium-free assertions; it catches missing
labels, aria-roles, and heading order. A full browser-level axe-core
sweep requires a Playwright suite running against the real UI.

**Owner:** Frontend quality.

**Closes when:** a Playwright axe-core run exists against:

* Public verify (`/verify`, `/verify/pdf`).
* Sign landing + review (`/sign/<token>`).
* Evidence retention browser (`/evidence/retentions`).
* Stamp custody dashboard.

## G6 — External penetration test

**Status:** threat-model v2 is current (`docs/threat-model.md`).
What remains is an engagement with an external firm.

**Owner:** Security.

**Closes when:** a signed pen-test report lands in
`docs/security/pentest-reports/` and all high / critical findings are
tracked to closure in GitHub issues.

## SSO SAML (deferred)

**Status:** OIDC SSO is fully implemented (`tests/test_oidc_sso.py`).
SAML is a separate protocol with its own test matrix and IdP
onboarding runbook.

**Owner:** Identity.

**Closes when:** a design doc selects an IdP library
(`python-saml` vs `authlib-saml`), the service-provider metadata
endpoint is implemented, and three IdPs (Azure AD, Okta, Google
Workspace) have signed-off integration tests.

## Enterprise SLOs & error budgets

**Status:** `docs/perf/` carries a load-test checkpoint. Prometheus
metrics are emitted. What remains is codifying SLO targets, error
budgets, and the burn-rate alert policy.

**Owner:** SRE.

**Closes when:** `docs/runbooks/SLOs.md` defines:

* Availability SLO per API family (public verify, sign, admin).
* Latency SLO (p95, p99) per endpoint class.
* Error-budget burn-rate alerting (fast + slow) wired through
  AlertManager.

## Threat-model residuals already closed

For reference, the remediation plan's G1, G2, G4, G7–G13 are closed:

* G1 — JWT revocation + refresh rotation (`app/services/token_security.py`).
* G2 — PostgreSQL RLS defence-in-depth (migration `h8e206f1c0a7`).
* G4 — PDF signing via AWS KMS (`app/services/pdf_sealing.py`,
  `tests/test_kms_sealing.py`).
* G7 — Durable audit chain + signed anchors
  (`app/services/audit_chain.py`, `AuditChainAnchor`).
* G8 — Durable rate limiter (`app/services/rate_limiting.py`,
  `RateLimitBucket`).
* G9 — SBOM + provenance tooling is a policy decision; not wired here.
* G10 — PDF.js + drawn-signature capture on `/sign`
  (`app/static/vendor/pdfjs/`, `app/static/vendor/signature_pad/`,
  `SignerAppearance`).
* G11 — OpenTelemetry tracing + Prometheus (`app/tracing.py`).
* G12 — Validation-dossier retention + export
  (`app/services/validation_dossier.py`).
* G13 — Public verification wired to validation dossier
  (`app/blueprints/trust/views/verify_views.py`).
