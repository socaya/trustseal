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

The current schema uses application-level locking and validates active same-tenant participants when added. A follow-up PostgreSQL migration, `c8d192f4a610`, adds guards against changing prepared recipients, moving participants between envelopes, changing envelope source identity, hard-deleting envelopes or reversing lifecycle transitions. Recipient activity and tenant membership are rechecked at preparation. These controls still require migration replay and database tests; check participants again at eventual signing time and implement a governed amendment/versioning policy.

## Validation status and next steps

The GitHub changes are published, but the tool environment has not executed tests, PostgreSQL migrations, or ClamAV. Add integration tests for unauthorized access, mismatched tenant, revoked account, duplicate participant, out-of-order positions, stale prepared envelope, concurrent edits, missing or tampered PDF bytes, cancellation and transaction rollback. Test the entire Alembic revision history from a fresh database and an upgraded production-like staging backup.

Next, implement authenticated signer's acceptance/decline workflow with evidence records and anti-replay semantics. Do not enable legal signing before the full trust/evidence pipeline is independently verified.

## Follow-up hardening

- `c8d192f4a610` follows `b7c104ef2a91` and defines PostgreSQL lifecycle/recipient guards. The prepared and cancelled states prevent ordinary direct edits to participants.
- Preparation rechecks every recipient's active status and current organisation membership before locking the envelope.
- Added `tests/test_envelope_preparation.py` for sequential order validation and to confirm that only preparation (not signing) endpoints are registered. Tests are authored but not executed.
- The new API is registered explicitly in `app/__init__.py`. Legacy signature mutation APIs remain disabled by the central guard.

The frontend remains unchanged. Do **not** treat a prepared envelope as signed, certified, sealed or legally verified.
