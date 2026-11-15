# Disaster Recovery Runbook

**Owner:** Platform operations.
**Review cadence:** quarterly, after every significant schema change,
and after every production incident touching storage or audit.
**Targets (recorded promises):**

- **RPO:** ≤ 15 minutes. Every trust-critical transaction is bound to a
  WAL record that ships to the backup bucket within one minute of
  commit; the recovery point is the last WAL record applied to the
  standby.
- **RTO:** ≤ 2 hours for a full tenant-scoped PostgreSQL rebuild from
  the most recent base backup and WAL chain.
- **Restore drill cadence:** quarterly (Q1 Mar, Q2 Jun, Q3 Sep, Q4
  Dec). Failing drills are a Sev-2 incident.

---

## Scope

This runbook covers:

1. Loss of the primary PostgreSQL instance or its underlying storage.
2. Corruption or malicious deletion of trust-critical rows.
3. Compromise of a tenant's object-store prefix.

It does **not** cover recovering a specific document. For per-document
recovery, see `docs/runbooks/evidence-recovery.md` (TODO).

## Backup components

| Artifact                      | Producer                               | Destination                              | Retention         |
|-------------------------------|----------------------------------------|------------------------------------------|-------------------|
| PostgreSQL base backup        | `scripts/backup.sh daily`              | `s3://trustseal-backups/base/`           | 90 days           |
| PostgreSQL WAL segments       | `archive_command` on primary           | `s3://trustseal-backups/wal/`            | 90 days           |
| Backup manifests              | `scripts/backup.sh`                    | `s3://trustseal-backups/manifests/`      | 7 years           |
| Immutable final PDFs          | S3 object-lock (COMPLIANCE mode)       | `s3://trustseal-objects/final/`          | per retention row |
| Evidence dossiers             | S3 object-lock (COMPLIANCE mode)       | `s3://trustseal-objects/dossier/`        | per retention row |
| Idempotency records           | Database (not backed up separately)    | n/a                                      | 24 h, autopruned  |

Backups are encrypted with KMS at rest and transit; access is limited
to the `trustseal-backup` IAM role.

## Automated drill

`scripts/restore_drill.sh` runs quarterly on a dedicated restore host.
The drill script:

1. Locates the most recent manifest in the backup bucket.
2. Downloads the referenced base backup, verifies its SHA-256 against
   the manifest.
3. Starts a disposable PostgreSQL instance on a non-default port.
4. Runs a reconciliation query that counts rows in each trust-critical
   table.

A failure at any step raises a Sev-2 incident and is tracked to
remediation.

## Operator procedure for full recovery

The procedure assumes a complete loss of the primary database.

### 1. Freeze writers

```sh
kubectl -n trustseal scale deployment web --replicas=0
kubectl -n trustseal scale deployment worker --replicas=0
```

Flipping replicas to zero stops new writes from reaching a database
that may not exist. Record the incident timestamp in the incident
tracker.

### 2. Provision a replacement Postgres

Use the team's standard provisioning path (RDS restore-from-snapshot
*or* a fresh container). Target version must match production
(`postgres:16`).

### 3. Download and verify the base backup

```sh
export TRUSTSEAL_BACKUP_BUCKET=s3://trustseal-backups
./scripts/restore_drill.sh
```

The drill script also serves as the production-restore driver — it
can target the replacement instance by overriding
`TRUSTSEAL_RESTORE_PGPORT`. Verify the SHA-256 match against the
manifest before continuing.

### 4. Replay WAL to the target recovery point

The default is "latest". For a point-in-time recovery, add a
`recovery_target_time` entry to `postgresql.conf` before the restore
starts. Test this path in the drill before relying on it.

### 5. Re-point application config

1. Rotate `DATABASE_URL` to the new host in the orchestrator's secret
   store.
2. Rotate `JWT_SECRET_KEY` so any in-flight refresh tokens issued
   before the incident are invalidated.
3. Rotate every webhook secret through
   `POST /api/webhooks/<id>/rotate`. A documented post-incident script
   does this in batch.

### 6. Reconcile audit trail

Run the full reconciliation checklist in
`docs/runbooks/evidence-reconciliation.md` (TODO) **before** scaling
web/worker back up. Specifically:

- Compare object-store manifests to `finalized_pdfs.output_sha256`.
- Compare webhook delivery `event_id`s to outbox `OutboxEvent.id`s.
- Confirm every `validation_dossier` has a matching evidence
  timestamp and OCSP record.

### 7. Resume traffic

```sh
kubectl -n trustseal scale deployment web --replicas=3
kubectl -n trustseal scale deployment worker --replicas=2
```

Monitor `/api/metrics` and the request-id correlation logs for
elevated error rates for the first 30 minutes.

### 8. Post-recovery audit

Within 48 hours, produce:

- A tamper-evidence report using
  `flask outbox verify-chain` (planned) comparing every chained
  audit-event hash before and after the incident.
- A summary of the WAL gap (if any) and the business transactions
  affected.
- A list of webhook deliveries that may have been double-fanned-out
  during the gap.

## Known gaps (as of 2026-11-15)

- `recovery_target_time` is not exercised in the current drill script.
  Add a drill variant that recovers to T-1 hour before quarter close.
- Idempotency records are per-tenant and not replicated across region
  failover. Document the acceptable re-trigger of retried mutations.
- Tenant-scoped point-in-time extraction is manual; a per-tenant
  logical dump is planned.
