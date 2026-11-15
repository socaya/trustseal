# ADR 0003 — Tenant isolation via tenant-scoped repositories and policy predicates

**Date:** 2026-11-14
**Status:** Accepted.

## Context

`app/policies/api_access.py` is a deny-by-default *mutation* guard. It does not enforce per-resource reads, does not prevent IDOR, and relies on each blueprint to filter by `organization_id` after the fact. Horizontal privilege escalation (user in tenant A reading tenant B's envelope by guessing the id) is not tested.

The target is: every tenant-scoped resource read or write passes through a narrow boundary that refuses to run an unscoped query, and every route carries an explicit policy predicate. Cross-tenant access returns 404 (anti-enumeration), not 403.

## Decision

1. `app/repositories/base.py` defines `TenantScopedRepository[T]`:
   - `__init__(session, tenant_id: int)` — binds the tenant at construction.
   - `get(resource_id) -> T | None` — always joins on `tenant_id`.
   - `list(**filters) -> list[T]` — always joins on `tenant_id`.
   - `.query` is not exposed; raw `Model.query` usage inside a repository is a code smell flagged by a lint rule.
2. Per-resource repositories (`DocumentRepository`, `EnvelopeRepository`, `StampAssetRepository`, `ValidationDossierRepository`, …) inherit from `TenantScopedRepository` and expose only resource-appropriate finders.
3. `app/policies/authorization.py` defines pure predicate functions:
   - `can_read(actor, resource) -> bool`
   - `can_write(actor, resource, op: str) -> bool`
   - `can_sign(actor, envelope, participant) -> bool`
   - `can_admin(actor, tenant) -> bool`
   Each predicate is pure; it never queries the DB — callers pass the resource already loaded through the tenant-scoped repository.
4. `@require_policy(predicate_name, resource_loader)` decorator:
   - Runs after JWT verification.
   - Calls the loader (`loader(request) -> Resource | None`), which must use a tenant-scoped repository.
   - Returns 404 when the loader returns `None` (uniformly for "does not exist" and "exists in another tenant").
   - Returns 403 only when the resource exists in the caller's tenant but the predicate denies.
5. The existing `enforce_legacy_api_security()` remains as the outermost guard. New routes carry `@require_policy`; migrated routes graduate off the interim guard and are removed from the trust-critical denylist in a controlled sequence.
6. PostgreSQL row-level security (RLS) is a *defence-in-depth* follow-up, not a replacement for the application policy.

## Consequences

- One cross-cutting refactor touching every blueprint; done incrementally per resource.
- `tests/security/test_tenant_isolation.py` is the gate: every tenant-scoped table and every method appears in the matrix; CI fails if new routes bypass the decorator.
- 404-for-cross-tenant is user-visible; counterparties get a consistent anti-enumeration response.

## Alternatives rejected

- RLS-only: moves policy to the DB and hides it from reviewers; harder to test.
- Session-level `SET tenant_id`: fragile with connection pooling and background workers.
