# ADR 0004 — Idempotency keys for trust-critical mutations

**Date:** 2026-11-14
**Status:** Accepted.

## Context

Trust-critical mutations (envelope finalization, signer decision, PDF seal, DSS derivation, dossier assembly, webhook dispatch) must produce exactly one durable outcome under client retries, worker retries, and double-click conditions. The platform already uses outbox lease fencing (`migration a6b7d820e3f1`) but lacks a request-level idempotency contract.

## Decision

1. `IdempotencyRecord` model (new migration):
   - `id`, `tenant_id` (indexed), `endpoint` (method + path template), `key` (client-supplied, ≤128 chars), `request_hash` (SHA-256 of canonical body), `response_status`, `response_body` (JSONB, ≤64KB), `response_headers` (JSONB), `locked_at`, `completed_at`, `expires_at`.
   - Unique index on `(tenant_id, endpoint, key)`.
2. Middleware: `app/services/idempotency.py::idempotent(endpoint_name)` decorator.
   - Required for every POST/PUT/PATCH on `/api/envelopes/*/finalize`, `/api/envelopes/*/decision`, `/api/sealed-pdfs`, `/api/evidence/*/checkpoints`, and future trust mutations.
   - Reads `Idempotency-Key` header (required; 400 otherwise).
   - Computes request hash; if row exists and status is `completed`, returns stored response verbatim.
   - If row exists and status is `locked`, returns 409 with `Retry-After`.
   - If body hash differs from stored row, returns 409 `idempotency_key_body_conflict`.
   - Otherwise acquires a row with `locked_at = now()` using `INSERT ... ON CONFLICT DO NOTHING`; stores the response on success, releases on failure.
3. Retention: records older than 24 hours are prunable by `flask retention prune-idempotency`.
4. The outbox worker uses a *separate* worker-side idempotency key (`event_id`) and does not share this table; the request-level key protects clients, the event id protects workers.

## Consequences

- One new table, one migration, one decorator, one CLI retention job.
- All POST clients must send `Idempotency-Key`; this is a breaking change for callers of the current prototype routes and must be announced in the API changelog before Milestone 2.
- Load tests gain a scenario that hammers the same key 100 times and asserts a single state transition.

## Alternatives rejected

- Dedup by business key (e.g., envelope_id): too narrow; cannot cover endpoints like webhook dispatch.
- In-memory cache: loses safety on pod restart.
