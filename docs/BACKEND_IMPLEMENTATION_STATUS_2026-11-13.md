# TrustSeal backend implementation status — 2026-11-13

## Scope and provenance
This checkpoint is based on direct inspection of the GitHub `main` tree, implementation plan, Flask factory, authentication routes, document endpoints, models and migrations. It is **not** a declaration of production readiness or 100% implementation. No full test environment was available: direct Git clone failed due to DNS/network access, and the GitHub connector does not execute the application.

## Changes committed to main in this session
- Added durable `RevokedToken` model and Alembic migration `b3f1d4c7e901`, based on the existing `1856829bd7b1` migration head.
- Registered Flask-JWT-Extended's database-backed blocklist loader in the app factory. Missing/disabled users and revoked JTIs are refused.
- Updated login to reject inactive users, require JSON-compatible credentials and avoid logging passwords; registration now validates required fields and password length.
- Made logout persist revoked access **or** refresh tokens; refresh is validated against the same blocklist.
- Replaced non-functional placeholder document CRUD methods with a scoped draft-only API; only owners can modify and soft-delete drafts.
- Document list/read checks ownership or explicit active view sharing rather than relying on organisation membership alone. Serialization removes internal storage paths, sensitive sharing tokens and nested user information.

## Critical gaps still open (not safe for production)
1. **Authorization:** audit *every* existing route, including roles, settings, invitations, document child resources, downloads, stamps, signatures and subscription mutations. Several legacy routes have no authenticated authorization and must be fail-closed. A shared policy service, organisation membership isolation and privilege tests are missing.
2. **JWT/session lifecycle:** implement refresh-token rotation/family invalidation, password-change revocation, privileged MFA, rate limits and suspicious-login monitoring. Current token revocation requires applying the migration. Persistent revocation records need retention/pruning and operational monitoring.
3. **Document trust:** private object storage, verified ingestion, malware scanning, canonical SHA-256 manifests, immutable version snapshots, authorization for every document child resource, evidence retention and safe PDF conversion are not implemented.
4. **Signing:** envelope/participant state machines, recipient authentication, explicit versioned consent, idempotent completion, certificate-backed methods where supported, timestamping, verified PDF finalization and evidence packages remain unimplemented.
5. **Stamps:** managed assets/revisions, custodian policy, delegated authority, dual control, immutable impressions and approval records are missing.
6. **Verification:** public high-entropy verification reference, digest validation, expiry/revocation/replacement states, disclosure policy and audit controls are missing.
7. **Operational integrity:** transactional audit outbox, background workers, delivery retries, dead-letter recovery, backups/restore drills, observability, idempotency, controlled release and alerts remain missing.
8. **Database migrations:** historic migration replay and schema compatibility are unverified. The new migration must be validated from a clean database and a representative upgraded database.
9. **Testing:** no automated integration/security tests have been executed in this environment. Schema, RBAC/IDOR, multi-tenant, auth revocation, signing, payment, webhooks, concurrency, evidence and restore tests are required.

## Immediate release gates
- Install pinned dependencies in a clean environment and run syntax checks.
- Run `flask db upgrade` against a disposable PostgreSQL instance and verify a second upgrade from representative existing schema.
- Add integration tests for register/login/refresh/logout (including cross-worker persistence), inactive accounts, document tenant isolation, owned/sharing reads, invalid payloads and draft lifecycle.
- Audit all registered routes for anonymous writes and cross-tenant access and block insecure endpoints.
- Implement domain state machines and immutable trust evidence *before* treating any graphical signature or stamp as verifiable.

## Safety note
The additions remain **partial** and need independent review before deployment. No production database was migrated; no production environment was modified. As legacy routes remain vulnerable, do not expose this backend publicly until the release gates are satisfied.
