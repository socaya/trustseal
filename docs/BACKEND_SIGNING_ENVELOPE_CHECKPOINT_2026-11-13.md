# TrustSeal Backend — Signing Envelope Preparation Checkpoint

Date: 2026-11-13  
Repository: `socaya/trustseal`  
Branch: `main`  
Status: committed, **not runtime-tested**

## Scope delivered

This checkpoint introduces a **preparatory** signing envelope model rather than falsely enabling a legacy electronic-signature CRUD route. The new envelope stores the tenant, document ID, a scanned private PDF manifest ID, the corresponding SHA-256 digest, the creator, lifecycle state, and timestamps. The participant table contains tenant-validated registered internal users, their role (`signer`) and contiguous unique signing order.

The lifecycle is `draft → prepared → cancelled`, with cancellation also permitted directly from draft. There is no `signed`, `completed`, or `verified` state in this preparation-only model. Changes to participant assignments through its API are permitted only while draft; the prepared envelope is locked. Each create, prepare, and cancel action is captured through the existing transactional security event/outbox infrastructure, with specific allowlisted internal consistency consumers.

The new `/api/envelopes` routes are owner-scoped and protected by JWT as well as the central API guard:

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/envelopes` | Create envelope from an owned document and its scanned private PDF manifest |
| GET | `/api/envelopes` | List caller's own envelopes |
| GET | `/api/envelopes/<id>` | Retrieve owner's envelope and ordered participants |
| POST | `/api/envelopes/<id>/participants` | Add a distinct active same-tenant recipient and signing position while draft |
| POST | `/api/envelopes/<id>/prepare` | Validate complete signing order, document state, manifest ID and on-disk digest; lock as prepared |
| POST | `/api/envelopes/<id>/cancel` | Cancel the envelope; cannot be re-prepared |

Database migration `b7c104ef2a91` follows `a6b7d820e3f1`, adding the new tables, referential constraints, state check and per-envelope unique recipient/order constraints. The models are registered in `app/models/__init__.py` and the blueprint is registered in the Flask application factory.

## Assurance boundaries and blockers

**Prepared means configured, not signed.** No user can sign via these new routes. Identity reauthentication, recipient invitation/challenge, explicit versioned consent, certificate handling, PDF embedding/finalization, qualified timestamping, immutable evidence package generation, independent verifier, and external/remote recipient flows remain outstanding. Existing unsafe generic signature CRUD writes remain blocked.

Envelope source digests are checked against the stored PDF file, but a PostgreSQL superuser or filesystem administrator can still tamper with both data and the private storage. Cryptographic external anchoring and WORM retention remain necessary for stronger evidence assurance.

The current schema uses application-level locking and validates active same-tenant participants when added. Before shipping, add database-level guards against direct edits of prepared recipient assignments, check participant activity again at dispatch/sign time, and implement a controlled amendment/versioning policy.

## Validation status and next steps

The GitHub changes are published, but the tool environment has not executed tests, PostgreSQL migrations, or ClamAV. Add integration tests for unauthorized access, mismatched tenant, revoked account, duplicate participant, out-of-order positions, stale prepared envelope, concurrent edits, missing or tampered PDF bytes, cancellation and transaction rollback. Test the entire Alembic revision history from a fresh database and an upgraded production-like staging backup.

Next, implement authenticated signer's acceptance/decline workflow with evidence records and anti-replay semantics. Do not enable legal signing before the full trust/evidence pipeline is independently verified.
