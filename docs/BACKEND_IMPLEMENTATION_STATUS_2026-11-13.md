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


## 2026-11-13 continuation: legacy API hardening checkpoint

Additional changes committed to `main`:

- `app/policies/api_access.py`: central authentication and administrative access policy; deny generic signing, stamping and payment mutations that would otherwise create false trusted records. Trust-critical writes now return HTTP 409 until governed domain services replace the legacy operations. Sensitive legacy collection reads require platform-admin privileges temporarily, **not** a final tenant policy.
- `app/__init__.py`: activate the new policy and return JSON for API 401/403 responses.
- `app/blueprints/documents/api/document_share_api.py`: prevent arbitrary model-field updates, token disclosure and cross-organisation recipient assignment; only document owners can manage explicit seven-day shares to active members of the same organisation.
- `app/blueprints/organizations/routes/organization_api.py`: scope organisation reads to membership, prevent caller-controlled verification flags, deactivate rather than cascade-delete an organisation.
- `app/blueprints/organizations/routes/clients_api.py`: scope directory operations to the current organisation, prevent caller-controlled organisation IDs, soft-deactivate clients.
- `app/blueprints/system/routes/settings_api.py`: fix endpoints that referenced nonexistent `SystemSettings.key/value` fields, expose/update only non-secret allowlisted settings under platform-admin access.
- `app/blueprints/users/routes/user_api.py`: validate administrative account creation/update, prevent mass assignment, avoid hard-delete of attribution history.
- `tests/test_api_security_policy.py`: regression cases covering public auth, protected endpoints, platform-administration access and blocked trust-critical writes.

### Explicit limitations of this checkpoint

- No runtime or integration test was executed; `git ls-remote` from the test container failed due to DNS resolution of `github.com`. GitHub connector writes were successful, but **commit success is not test success**.
- The interim platform-admin role test relies on pre-existing globally named roles. It is not a replacement for tenant membership, delegated authority, permission scope, stronger account bootstrap or separation of duties.
- Backend HTML view handlers, document child APIs, subscriptions, signature profiles, template/editor routes and other legacy endpoints still require individual authorization audits. The central policy only protects the cases documented above.
- Existing clients may need adaptation: non-admin global listings are restricted, arbitrary document-share fields are rejected, trust-critical CRUD writes are blocked, and organisation deletion becomes deactivation.
- Full signing, stamping, payment and verification functionality is **not implemented** by this hardening. These must be added as proper domain workflows, not unblocked by removing the interim guard.
- No production migrations were run. The persistent JWT revocation migration remains an operational prerequisite for authenticated requests.
