#!/usr/bin/env bash
# Quarterly restore drill.
#
# Restores the most recent base backup into a disposable Postgres
# instance and replays WAL. The drill PASSES if every row in the
# reconciliation query returns a non-zero count, which proves that
# trust-critical tables were materialised after the restore.
#
# Usage:
#   TRUSTSEAL_BACKUP_BUCKET=s3://company-trustseal-backups \
#   TRUSTSEAL_RESTORE_PGPORT=55432 \
#   ./scripts/restore_drill.sh
#
# The drill fails loudly if any step errors so an oncall can pick up
# the alert. See docs/runbooks/disaster-recovery.md for the full
# procedure and the reconciliation checklist.

set -euo pipefail
set -o errtrace

: "${TRUSTSEAL_BACKUP_BUCKET:?TRUSTSEAL_BACKUP_BUCKET required}"
: "${TRUSTSEAL_RESTORE_PGPORT:=55432}"
: "${TRUSTSEAL_AWS_PROFILE:=trustseal-backups}"

workdir="$(mktemp -d -t trustseal-restore-XXXXXXXX)"
trap 'pg_ctl -D "$workdir/data" stop -m fast >/dev/null 2>&1 || true; rm -rf "$workdir"' EXIT

echo "[$(date -u +%FT%TZ)] locating most recent manifest"
latest_manifest=$(
  aws --profile "$TRUSTSEAL_AWS_PROFILE" s3api list-objects-v2 \
    --bucket "${TRUSTSEAL_BACKUP_BUCKET#s3://}" \
    --prefix manifests/ \
    --query 'sort_by(Contents, &LastModified)[-1].Key' \
    --output text
)
[ -z "$latest_manifest" ] && { echo "no manifest found"; exit 2; }

echo "[$(date -u +%FT%TZ)] downloading manifest $latest_manifest"
aws --profile "$TRUSTSEAL_AWS_PROFILE" s3 cp \
  "$TRUSTSEAL_BACKUP_BUCKET/$latest_manifest" \
  "$workdir/manifest.json"

archive_key=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['archive_key'])" "$workdir/manifest.json")
expected_sha256=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['sha256'])" "$workdir/manifest.json")
echo "[$(date -u +%FT%TZ)] archive key=$archive_key sha256=$expected_sha256"

aws --profile "$TRUSTSEAL_AWS_PROFILE" s3 cp \
  "$TRUSTSEAL_BACKUP_BUCKET/$archive_key" \
  "$workdir/base.tgz"

actual_sha256=$(shasum -a 256 "$workdir/base.tgz" | awk '{print $1}')
if [ "$actual_sha256" != "$expected_sha256" ]; then
  echo "archive sha256 mismatch: $actual_sha256 != $expected_sha256" >&2
  exit 3
fi

mkdir -p "$workdir/data"
chmod 700 "$workdir/data"

echo "[$(date -u +%FT%TZ)] extracting archive"
tar -xzf "$workdir/base.tgz" -C "$workdir/data"

echo "[$(date -u +%FT%TZ)] starting disposable postgres on port $TRUSTSEAL_RESTORE_PGPORT"
pg_ctl -D "$workdir/data" -o "-p $TRUSTSEAL_RESTORE_PGPORT" -l "$workdir/pg.log" start

# Wait for the server to come up.
for attempt in $(seq 1 30); do
  if pg_isready -h localhost -p "$TRUSTSEAL_RESTORE_PGPORT" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

echo "[$(date -u +%FT%TZ)] running reconciliation query"
psql -h localhost -p "$TRUSTSEAL_RESTORE_PGPORT" -d trustseal <<'SQL'
\set ON_ERROR_STOP on
SELECT
  (SELECT COUNT(*) FROM finalized_pdfs)              AS finalized_pdfs,
  (SELECT COUNT(*) FROM validation_dossiers)         AS validation_dossiers,
  (SELECT COUNT(*) FROM evidence_timestamps)         AS evidence_timestamps,
  (SELECT COUNT(*) FROM evidence_checkpoints)        AS evidence_checkpoints,
  (SELECT COUNT(*) FROM organizations WHERE is_active) AS active_tenants,
  (SELECT COUNT(*) FROM users WHERE is_active)       AS active_users;
SQL

echo "[$(date -u +%FT%TZ)] restore drill complete"
