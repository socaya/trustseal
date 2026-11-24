# Cross-region readiness

This document records exactly which TrustSeal invariants already
support a multi-region deployment and which ones a future
**active-active** topology would need to add. Treat it as the
hand-off between engineering and the operator who selects a
database topology.

## 1. Deployment modes

TrustSeal distinguishes three deployment modes:

| Mode | Description | Supported today? |
| --- | --- | --- |
| **Single-region** | One Flask fleet, one PostgreSQL. | Yes — default. |
| **Multi-region active-passive** | One primary region with a read replica or async-replicated hot standby in a second region. Failover promotes the standby. | Yes — see §2. |
| **Multi-region active-active** | Two regions writing concurrently, converging via a global database (Aurora Global, Spanner, Cockroach) or a conflict-resolved idempotency layer (Redis Cluster). | Not yet — see §3. |

## 2. Invariants that already support active-passive

All of these are code-enforced today. Nothing additional is
required of the operator beyond provisioning a PostgreSQL that
supports streaming replication:

1. **Idempotency.** `app/services/idempotency.py` stores durable
   records in `idempotency_records`. The table is tenant-scoped
   and the unique index on `(tenant_id, endpoint, key)` is the
   single source of truth. A replica receives inserts from the
   primary via WAL; after a failover a replayed request still
   collides on the unique index.
2. **Outbox.** `app/services/outbox.py` + `app/workers/outbox_worker.py`
   use `SELECT ... FOR UPDATE SKIP LOCKED` + a lease token column
   to claim work. Multiple workers in the same region and another
   region's hot standby after promotion are all safe — a lost
   lease simply releases the row.
3. **Audit chain.** `app/services/audit_chain.py` computes the
   next `event_hash` inside a transaction that locks the chain
   tip. After failover the standby already carries the committed
   tip because replication is synchronous to the local WAL. The
   chain anchors (`AuditChainAnchor`) provide off-database
   verifiability if replication ever diverges.
4. **Row-level security.** `app/services/tenant_rls.py` propagates
   the active tenant via a session-scoped `SET LOCAL`. Replicas
   enforce RLS identically because the policies live in the
   schema.
5. **Rate limiter.** `app/services/rate_limiting.py` uses Postgres
   `INSERT ... ON CONFLICT DO UPDATE` keyed by the fixed-window
   `(bucket_key, window_start)`. After failover the counters
   continue incrementing from their replicated values.
6. **Validation dossier.** `app/services/validation_dossier.py`
   is append-only; the `trustseal_reject_snapshot_mutation`
   trigger enforces immutability at the database layer, so any
   secondary writer (promoted replica, administrative replay) is
   gated the same way.

**Operator checklist for active-passive:**

- Use PostgreSQL ≥ 14 with synchronous_commit = `on` and
  streaming replication to the standby region.
- Point the Flask fleet at the primary via a DNS record that can
  be flipped at failover (e.g. Route 53 health-checked failover
  record, or an internal proxy).
- Promote the standby only after the primary is confirmed dead —
  two primaries would cause the audit chain to fork. The chain
  anchors give auditors an off-DB way to detect such a fork.

## 3. What active-active requires (not yet shipped)

To run two Flask fleets in different regions writing to separate
databases, three things must be added:

### 3.1 Global idempotency layer

The current `IdempotencyRecord` table is region-local. An
active-active deployment needs a global tier so a retried request
that lands in the "other" region still collides with the original.
Options:

- **Spanner / Aurora Global / CockroachDB.** Replace the single
  Postgres with a globally-consistent database. The existing
  SQL-based `IdempotencyRecord` continues to work with no
  application changes.
- **Redis Cluster at the edge.** Introduce a short-lived
  distributed lock before the regional insert. This is cheaper
  but weakens the single-source-of-truth property: a Redis
  partition briefly allows duplicate writes.

The existing `app/services/idempotency.py` isolates its backend behind the
`IdempotencyRepository` protocol and ships both `PostgresIdempotencyRepository`
(default) and `RedisIdempotencyRepository` (configurable via
`app.config["IDEMPOTENCY_REPOSITORY"]`), verified in `tests/test_idempotency.py`.

### 3.2 Audit chain consolidation

If both regions commit audit events in parallel the chain forks.
Options:

- **Single writer per tenant.** Shard tenants by region; a
  tenant's events only land in its home region.
- **Signed chain merge.** Each region signs its own chain anchor
  and a consolidation worker merges them into a global ordering.
  This matches the design of the existing
  `AuditChainAnchor` model.

Shipping either requires a product/compliance review of
jurisdictional ordering requirements.

### 3.3 Outbox-event delivery de-duplication

Each region has its own outbox table. A webhook recipient must
not observe duplicate events because tenant A's prepared event
landed in region US-EAST and the superseded replay landed in
EU-WEST after a failover. The existing per-event
`idempotency_key` protects against this at the receiving side,
**if** the receiver honours it; outbound webhook delivery must
also carry the idempotency key in a header (already shipped as
`TrustSeal-Idempotency-Key`).

## 4. Readiness summary

- **Single-region**: fully shipped, test-covered.
- **Active-passive**: fully supported; no application changes
  required.
- **Active-active**: adopters must pick a global-database or
  edge-coordination strategy (§3). The TrustSeal codebase is
  **topology-agnostic** everywhere except the three items above,
  and each of those has a clean extension point already in the
  service layer.

This file is authoritative for the cross-region gap in
`docs/REMAINING_GAPS_2026-11-15.md`; update both files together
when the active-active strategy is selected.
