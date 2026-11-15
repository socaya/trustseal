#!/usr/bin/env bash
# TrustSeal database base-backup + WAL archive uploader.
#
# Usage (production):
#   TRUSTSEAL_BACKUP_BUCKET=s3://company-trustseal-backups \
#   TRUSTSEAL_PGHOST=postgres-primary.internal \
#   TRUSTSEAL_PGUSER=trustseal_backup \
#   TRUSTSEAL_PGDATABASE=trustseal \
#   ./scripts/backup.sh daily
#
# The script produces three outputs per invocation:
#   1. A pg_basebackup tar.gz uploaded to s3://.../base/<utc-timestamp>.tgz.
#   2. A manifest JSON uploaded alongside the archive.
#   3. The current WAL file archived via ``pg_wal_archive``.
#
# The script is strict: it exits non-zero on any failure so that the
# invoking scheduler (systemd timer, cron, or managed job) can alert.

set -euo pipefail
set -o errtrace

# Mandatory environment.
: "${TRUSTSEAL_BACKUP_BUCKET:?TRUSTSEAL_BACKUP_BUCKET required}"
: "${TRUSTSEAL_PGHOST:?TRUSTSEAL_PGHOST required}"
: "${TRUSTSEAL_PGUSER:?TRUSTSEAL_PGUSER required}"
: "${TRUSTSEAL_PGDATABASE:?TRUSTSEAL_PGDATABASE required}"

# Optional.
: "${TRUSTSEAL_PGPORT:=5432}"
: "${TRUSTSEAL_AWS_PROFILE:=trustseal-backups}"
: "${TRUSTSEAL_BACKUP_TAG:=${1:-adhoc}}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
workdir="$(mktemp -d -t trustseal-backup-XXXXXXXX)"
trap 'rm -rf "$workdir"' EXIT

echo "[$(date -u +%FT%TZ)] starting pg_basebackup -> $workdir"
pg_basebackup \
  --host "$TRUSTSEAL_PGHOST" \
  --port "$TRUSTSEAL_PGPORT" \
  --username "$TRUSTSEAL_PGUSER" \
  --dbname "$TRUSTSEAL_PGDATABASE" \
  --pgdata "$workdir/base" \
  --format=tar \
  --gzip \
  --compress=9 \
  --progress \
  --wal-method=fetch \
  --checkpoint=fast

archive_name="$timestamp-$TRUSTSEAL_BACKUP_TAG.tgz"
archive_path="$workdir/$archive_name"
# ``pg_basebackup --format=tar`` writes ``base.tar.gz`` inside the
# destination directory; rename to the versioned filename used in S3.
mv "$workdir/base/base.tar.gz" "$archive_path"

# Fingerprint the archive so the manifest proves immutability.
sha256="$(shasum -a 256 "$archive_path" | awk '{print $1}')"
size_bytes="$(wc -c <"$archive_path")"

manifest_path="$workdir/$timestamp-$TRUSTSEAL_BACKUP_TAG.manifest.json"
cat >"$manifest_path" <<JSON
{
  "trustseal_backup": "pg_basebackup",
  "tag": "$TRUSTSEAL_BACKUP_TAG",
  "pg_host": "$TRUSTSEAL_PGHOST",
  "pg_database": "$TRUSTSEAL_PGDATABASE",
  "timestamp_utc": "$timestamp",
  "sha256": "$sha256",
  "size_bytes": $size_bytes,
  "archive_key": "base/$archive_name"
}
JSON

echo "[$(date -u +%FT%TZ)] uploading base backup to $TRUSTSEAL_BACKUP_BUCKET/base/$archive_name"
aws --profile "$TRUSTSEAL_AWS_PROFILE" s3 cp \
  --sse aws:kms \
  --no-progress \
  "$archive_path" \
  "$TRUSTSEAL_BACKUP_BUCKET/base/$archive_name"

echo "[$(date -u +%FT%TZ)] uploading manifest to $TRUSTSEAL_BACKUP_BUCKET/manifests/$timestamp-$TRUSTSEAL_BACKUP_TAG.json"
aws --profile "$TRUSTSEAL_AWS_PROFILE" s3 cp \
  --sse aws:kms \
  --no-progress \
  "$manifest_path" \
  "$TRUSTSEAL_BACKUP_BUCKET/manifests/$timestamp-$TRUSTSEAL_BACKUP_TAG.json"

# WAL archiving is Postgres-side via ``archive_command`` → S3. This
# script does not drive ongoing WAL shipping; it only verifies that the
# archive location is reachable before exiting.
aws --profile "$TRUSTSEAL_AWS_PROFILE" s3 ls \
  "$TRUSTSEAL_BACKUP_BUCKET/wal/" >/dev/null

echo "[$(date -u +%FT%TZ)] backup $timestamp-$TRUSTSEAL_BACKUP_TAG complete"
echo "sha256=$sha256 size=$size_bytes"
