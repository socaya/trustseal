# TrustSeal backend checkpoint — Audit events and transactional outbox
Date: 2026-11-13
Branch: main
Status: committed; NOT runtime-tested

## Implemented

The new `SecurityEvent` and `OutboxEvent` persistence models and Alembic revision `f9b135a0c642` extend revision `e4d92f6a301b`. Audit events are append-only for ordinary SQL UPDATE/DELETE (PostgreSQL trigger). Outbox rows carry event classification, tenant reference, aggregate reference, opaque idempotency key, minimal identifier-only payload, attempts, retry scheduling, lease and error state. No raw document bytes, passwords, contact details, signing materials or object keys are placed in the outbox.

`app/services/event_delivery.py` exposes `enqueue()`, `claim_next()`, `finish()` and `deliver_one()`. `enqueue()` does not commit, enabling business rows, security events and dispatch records to commit atomically. `claim_next()` uses PostgreSQL `FOR UPDATE SKIP LOCKED` to avoid two workers claiming the same queued message simultaneously. It leases rows for 120 seconds; processing rows become eligible again after lease expiry. `finish()` checks the lease timestamp to reject stale worker acknowledgments. Failed handlers retry with bounded exponential delay and reach a dead-letter state after eight attempts.

The document API now creates security/outbox records for:
- draft creation;
- draft update;
- draft soft deletion;
- immutable text snapshot creation;
- private file ingestion.

The CLI registers:
- `flask outbox status` — print counts by processing status;
- `flask outbox drain --limit 25` — bounded attempt processing;
- `flask outbox retry-dead <id> --confirm` — manually requeue one dead event with a registered handler.

The only registered consumers are **internal consistency checks** for the five document event types. They check the relevant document and, for snapshot/file events, the existence of the associated manifest. This is intentionally **not** a notification/webhook delivery system. No untrusted event_type or payload can select arbitrary Python code.

`tests/test_event_delivery.py` adds initial unit cases for transaction ownership, invalid idempotency keys and consumer allowlisting. Tests are written but have not been run in this session.

## Critical gaps and correctness caveats

1. **Not a complete tamper-evident audit ledger.** Append-only triggers do not prevent superusers or privileged storage operators from changing evidence. Cryptographic hash chaining, independent checkpoints, retention, audit export verification, schema-controlled actor context and operational restoration remain to be implemented.
2. **At-least-once dispatch.** Downstream handlers must be idempotent because a worker may crash after an external side effect but before committing completion. The current handlers do not perform external effects.
3. **Finite leases.** Jobs lasting more than the configured 120-second lease may be claimed again; the stale finish check helps prevent incorrect acknowledgments but cannot cancel a previously started external side effect. Add heartbeat/renewal and consumer-specific timeouts for long-running work.
4. **No continuous supervisor.** `flask outbox drain` is a bounded worker invocation, not a deployed background service. A supervised scheduler/worker process, alerts and monitoring are required.
5. **No HTTP-facing operator API.** Dead-letter retry is accessible through server CLI only; operator authentication, approvals and retry audit need integration.
6. **Legacy route audit incomplete.** Not every authenticated/HTML/legacy API mutation is wired to the new audit service. In particular, payment, stamp, signature, invitation and settings operations are not covered.
7. **No request idempotency gateway.** Unique outbox keys protect event duplicates but do not make every incoming HTTP request idempotent. Draft edits still lack a fully enforced optimistic concurrency contract across all clients.
8. **Outbox payload is limited to identifiers.** Consumers may query the current aggregate state, not a frozen historical snapshot. Immutable event payload snapshots and schema versioning must be introduced when external business effects are added.
9. **Migration pending.** Apply against an isolated PostgreSQL instance, replay from the historic revision chain and rehearse restore before deployment.
10. **Integration tests pending.** Concurrent claims, retries, worker crashes, expired lease reclamation, stale-worker finish, dead-letter recovery, unique-key collisions and transaction rollback must be tested on PostgreSQL.

## Suggested verification commands (do not run against production first)

```bash
python -m pytest -q tests/test_event_delivery.py
flask db upgrade
flask outbox status
flask outbox drain --limit 25
```

The app must have the required dependencies, database, migrations, and environment configuration ready. The above are instructions, not evidence that these checks were run.

## Next engineering slices

- Implement independent audit checkpoints and verification with secure tenant and actor attribution.
- Implement a supervised worker with health probes, poison-message recovery and end-to-end idempotent external delivery.
- Strengthen all draft edits with deterministic optimistic concurrency and transaction boundaries.
- Implement immutable envelope/participant signing workflow with consent and binding to scanned PDF digest.
- Implement governed stamp workflows and publicly verifiable evidence only after the prerequisite audit and storage test gates pass.
