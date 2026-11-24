# Remaining Gaps — Status & Closure Ledger

All code-addressable gaps from the 2026-11-14 remediation plan and the
subsequent 2026-11-15 follow-up items are now implemented and test-verified
inside this repository. Only **external third-party engagements** and
**production infrastructure topology sign-offs** remain open outside code.

## Closed since 2026-11-15

### G3 (Code Layer) — Pluggable cross-region idempotency repository
* **Closed in code:** `app/services/idempotency.py` exposes the pluggable
  `IdempotencyRepository` protocol with `PostgresIdempotencyRepository`
  (default) and `RedisIdempotencyRepository` (for active-active edge
  coordination via `app.config["IDEMPOTENCY_REPOSITORY"]`), verified in
  `tests/test_idempotency.py`.
* **Remaining external sign-off:** Platform infrastructure Target Operating
  Model selection for active-active multi-region deployment
  (`docs/CROSS_REGION_READINESS.md`).

### G5 — Automated browser accessibility (Playwright + WCAG 2.1 AA / axe-core)
* **Closed:** `tests/test_accessibility_playwright.py` boots the real Flask
  application and audits rendered DOM, ARIA labels, landmarks, keyboard
  focus, and runtime JS errors in headless Chromium (plus optional
  `axe-core` execution) across:
  * Public verify (`/verify`)
  * Sign landing + review (`/sign/<token>`)
  * Evidence retention browser (`/evidence/retentions`)
  * Stamp library / custody dashboard (`/stamps`)
  * Sealed signatures vault (`/signatures`)
* Complemented by static template checks in `tests/test_accessibility.py`.

### SSO SAML 2.0 + SP-Signed AuthnRequests
* **Closed:** Pure-Python SAML 2.0 SSO with assertion replay protection and
  SP-signed AuthnRequests is implemented and verified in
  `tests/test_saml_sso.py` and `tests/test_saml_sp_signing.py`.

### Enterprise SLOs, Error Budgets & Burn-Rate Alerting
* **Closed:** Live SLO computation and `GET /api/_internal/slo` ship in
  `app/services/slo.py`. The operational SLO runbook (`docs/runbooks/SLOs.md`)
  and Prometheus/AlertManager multi-window fast/slow burn-rate & p95 latency
  rules (`docs/runbooks/slo-alerts.prometheus.yml`) are versioned and
  validated in `tests/test_slo.py`.

### G9 — SBOM & SAST tooling
* **Closed:** CycloneDX 1.5 SBOM generation (`scripts/generate_sbom.py`,
  `tests/test_sbom_generator.py`) and SAST / secret scanning
  (`scripts/run_sast.py`, `tests/test_sast_runner.py`) are implemented.

## Open external / non-code items

### G6 — External penetration test
* **Status:** Threat model v2 (`docs/threat-model.md`), automated SAST/SBOM,
  and pre-engagement scope/evidence (`docs/security/PENTEST_SCOPE_AND_EVIDENCE.md`)
  are complete. What remains is commissioning an external penetration-testing
  firm.
* **Owner:** Security.
* **Closes when:** A signed pen-test report lands in
  `docs/security/pentest-reports/` and all Critical / High findings are
  remediated and re-tested.

### G3 (Infrastructure Sign-Off) — Active-active deployment topology
* **Status:** Single-region and active-passive are production-ready; the
  codebase exposes `RedisIdempotencyRepository` for active-active edge
  coordination.
* **Owner:** Platform infrastructure.
* **Closes when:** The Target Operating Model selects the production
  active-active database / Redis Cluster topology.

## Threat-model residuals already closed (2026-11-14)

* G1 — JWT revocation + refresh rotation (`app/services/token_security.py`).
* G2 — PostgreSQL RLS defence-in-depth (migration `h8e206f1c0a7`).
* G4 — PDF signing via AWS KMS (`app/services/pdf_sealing.py`, `tests/test_kms_sealing.py`).
* G7 — Durable audit chain + signed anchors (`app/services/audit_chain.py`, `AuditChainAnchor`).
* G8 — Durable rate limiter (`app/services/rate_limiting.py`, `RateLimitBucket`).
* G10 — PDF.js + drawn-signature capture on `/sign` (`app/static/vendor/pdfjs/`, `app/static/vendor/signature_pad/`, `SignerAppearance`).
* G11 — OpenTelemetry tracing + Prometheus (`app/tracing.py`).
* G12 — Validation-dossier retention + export (`app/services/validation_dossier.py`).
* G13 — Public verification wired to validation dossier (`app/blueprints/trust/views/verify_views.py`).
