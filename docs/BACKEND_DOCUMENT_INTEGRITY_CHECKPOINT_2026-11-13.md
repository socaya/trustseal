# TrustSeal backend checkpoint: draft integrity and document history

Date: 2026-11-13
Branch: main
Status: **Committed, not runtime-verified**

## Implemented

1. Added `DocumentSnapshot` as an immutable, append-only record of a draft text revision, containing document ID, revision number, UTF-8 content, SHA-256 digest, author and creation time.
2. Added migration `c6e8a2f74109` after the JWT migration `b3f1d4c7e901`, plus database enforcement migration `d0a7bc120e34`. PostgreSQL trigger prevents UPDATE and DELETE on document snapshots.
3. Canonical hashing uses sorted-key compact UTF-8 JSON, binding digest to schema version, document ID, revision and text. It is deterministic for identical input.
4. New authenticated endpoints:
   - `POST /api/documents/<id>/snapshots`: owner-only, draft-only, maximum 1 MiB UTF-8 content, idempotent per revision; database row lock and unique revision prevent duplicate writes.
   - `GET /api/documents/<id>/snapshots`: metadata listing for authorized document readers.
   - `GET /api/documents/<id>/snapshots/<snapshot_id>`: authorized snapshot read.
   - `GET /api/documents/<id>/snapshots/<snapshot_id>/integrity`: recomputed SHA-256 consistency check.
5. Writes snapshot creation activity within the same database transaction.
6. Legacy `/api/document-versions` changed to authorized, read-only metadata and rejects path/creator/version rewrites.
7. Legacy `/api/document-activity` changed to document-scoped read-only history; direct client mutation rejected.
8. Added `tests/test_document_snapshots.py` for deterministic hashing, tampering/revision differences and input validation.

## Important assurance boundaries

Draft-text SHA-256 checks are **not electronic signatures**, identity attestation, qualified timestamps, evidence packages, immutable object files or a court-ready validation system. Database-only hash and contents can be altered together by sufficiently privileged operators; independent anchoring and immutable external evidence are necessary for stronger assurance.

Legacy uploaded files remain outside the secure ingestion pipeline. No file bytes are converted, validated or stored by these endpoints. A document is **not issued, signed, stamped, verified or finalised** by taking a text snapshot.

## Compatibility and release gates

- **Database upgrade required:** run `flask db upgrade` on a backed-up staging database after replay-checking historical migrations; never apply the migrations to production without a successful migration dry run and restore drill.
- The PostgreSQL trigger is intentionally one-way for normal operations; downgrading removes the trigger. Authorised incident recovery must follow a separate audited process.
- Existing `Document.version` is a mutable integer used by legacy routes. Before production, enforce optimistic revision checks in *all* document writers, harmonize template/draft routes and enforce transactionally consistent snapshots.
- Integration tests are still needed for owner/shared/unauthorized access, duplicate snapshot requests, concurrent writers, trigger denial of UPDATE/DELETE, rollback on activity insert failure, legacy API blocking and DB migration replay.
- Existing unregistered legacy document APIs were **not** exposed: they require authorization and schema review before registration.
- No runtime tests have been executed in this environment; a passing commit is not a passing test.

## Next backend implementation slices

1. Private quarantine/object storage with object-manifest hashing and strict upload validation.
2. Tenant-scoped policy enforcement for every registered and unregistered document subresource, including view routes.
3. Atomic outbox/audit primitives with replay and dead-letter handling.
4. Envelope/participant workflow with challenge, consent, immutable digest binding, signer evidence and idempotent finalization.
5. Stamp approval/custody controls and independent verifier.
