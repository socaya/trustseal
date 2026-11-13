# TrustSeal backend checkpoint: concurrency and outbox recovery
Date: 2026-11-13
Branch: main
Status: committed; **NOT executed against a live PostgreSQL database**

## Changes in this checkpoint

### Draft mutation concurrency
- `PUT /api/documents/<document_id>/` now requires a JSON integer `expected_version` and rejects a missing precondition (HTTP 428), stale revision (HTTP 409), unrecognized fields (HTTP 400), and modifications of non-draft records (HTTP 409).
- Draft updates acquire a PostgreSQL row lock before comparing revision and writing changes, then increment revision and enqueue the corresponding event in the same transaction.
- `DELETE /api/documents/<document_id>/` requires a numeric `If-Match` revision header, acquires the document row lock, and soft-deletes only a matching draft.
- Client applications must read the document's `version` and submit that revision with every write. This is an intentional API contract change to prevent lost updates; update frontend clients after the backend receives integration verification.

### Outbox crash recovery
- Due messages are claimed with `FOR UPDATE SKIP LOCKED`, including previously processing messages with expired leases.
- Claims that exhausted the eight-attempt budget are moved to dead-letter state without executing the handler again.
- A worker whose lease has expired cannot commit a success/failure acknowledgment for that lease. The database row is checked under lock.
- Added `renew_lease(event_id, lease_until)` for controlled extensions by future long-running workers.
- Existing unregistered event types still fail closed, and only internal document consistency handlers remain available.
- Added regression tests for stale claims and unregistered handlers (written but unexecuted).

## Important remaining constraints

- No exactly-once semantics: external side effects must have their own idempotency guarantees. Leases and row locks only coordinate DB claiming/acknowledgment.
- Lease identity now uses a unique per-claim UUID persisted as `outbox_events.lease_token` (migration `a6b7d820e3f1`). Stale completion and renewal requests require the matching token. External side effects still require provider-level idempotency.
- Lease renewal is not automatically scheduled; long-running handlers must explicitly renew or use supervised bounded execution.
- No live worker supervisor, queue heartbeat dashboard, alert thresholds or full concurrency and crash tests have been deployed.
- No integrated optimistic concurrency check exists yet for every legacy draft/template and HTML mutation; the contract in this checkpoint applies to `/api/documents/<id>/` only.
- Current audit events are append-only SQL records, **not** independently anchored tamper-evident evidence.
- Concurrency changes require end-to-end tests with two independently connected PostgreSQL sessions, including duplicate attempts, absent preconditions, stale version, conflicting document updates, worker crash/lease expiry and recovery from backup.

## Suggested local staging checks

```bash
python -m pytest -q tests/test_event_delivery.py tests/test_document_snapshots.py
flask db upgrade
flask outbox status
flask outbox drain --limit 25
```

These commands have **not** been executed as part of this change; no automated test pass, migration pass or production safety claim is made.

## Next implementation target

1. PostgreSQL tests, migration replay, and route-level authorization regression tests.
2. Audited dead-letter operator action, worker supervision and lease renewal for long-running operations.
3. Independent audit integrity checkpoints and canonical event schemas.
4. Complete signature envelope/participant state machine and consent workflow bound to immutable PDF revision and digest.

## Additional commit: per-claim UUID fencing

Added `lease_token` to the `OutboxEvent` model with migration `a6b7d820e3f1`, following `f9b135a0c642`. Each new claim receives an independently generated UUID. `finish()` and `renew_lease()` query by both event ID and lease UUID. Manual requeue clears the previous token. This reduces the risk of old workers accidentally acknowledging reclaimed events, but does not make third-party effects exactly-once.

The migration and recovery regressions have **not** been executed. Apply the new revision in staging and verify concurrent claims, crash/reclaim and rollback before production.
