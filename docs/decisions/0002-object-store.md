# ADR 0002 — Object storage abstraction and S3-compatible backend

**Date:** 2026-11-14
**Status:** Accepted.

## Context

`app/services/documents/private_storage.py` writes document originals, sealed PDFs, DSS derivatives, and evidence dossiers to the local filesystem. The current design is unsafe in production: it cannot be served from multiple pods, loses durability on pod eviction, and precludes any object-lock or compliance retention on final artifacts.

## Decision

1. Introduce `app/services/integrations/storage/base.py` with a narrow `ObjectStore` interface:
   ```
   put(key, body, *, content_type, metadata) -> ObjectPut
   get(key) -> bytes
   stream(key) -> Iterator[bytes]
   head(key) -> ObjectMeta
   exists(key) -> bool
   presign_get(key, ttl) -> str  # authenticated short-lived URL
   delete(key) -> None           # legal-hold aware; refuses locked objects
   list_versions(key) -> list[ObjectVersion]
   ```
2. Implementations:
   - `LocalObjectStore` — current `Path()` behaviour, dev and CI only.
   - `S3ObjectStore` — boto3, SSE-KMS mandatory, versioning mandatory, object lock in COMPLIANCE mode for keys under `final/`, `dossier/`, `dss/`. Production.
   - `MinioObjectStore` — alias of `S3ObjectStore` with endpoint override for local compose.
3. Backend selection via `OBJECT_STORAGE_BACKEND={local,s3,minio}`. Production refuses `local`.
4. Keys are opaque: `<tenant_id>/<kind>/<yyyy>/<mm>/<ulid>` (no user-supplied path components, no PII in keys).
5. `check_object_digest()` in `private_storage.py` becomes `digest()` on the interface. Local path leakage removed from serializers (already partial).
6. Downloads go through authorized Flask streaming or presigned URLs with ≤5 minute TTL and `Content-Disposition` set server-side. Static directories never serve uploads (already partially enforced in `app/__init__.py` before-request hook).
7. Backup is handled by S3 inventory + replication to a second region bucket, not by the application.

## Consequences

- `private_storage.py` becomes a thin wrapper around the interface.
- One new config block in `config.py` (`OBJECT_STORAGE_*`).
- `compose.yml` adds a MinIO service for local dev parity.
- Integration tests run the full signing suite against both `LocalObjectStore` and `MinioObjectStore` in CI.

## Alternatives rejected

- Database LOB storage: limits throughput, breaks object lock.
- NFS shared disk: no immutability guarantee, operationally fragile.
