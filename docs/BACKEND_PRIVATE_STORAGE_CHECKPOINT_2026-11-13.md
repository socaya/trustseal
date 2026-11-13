# TrustSeal secure document ingestion — backend checkpoint

Date: 2026-11-13
Repository: `socaya/trustseal`
Branch: `main`
Status: **Code committed; deployment and integration testing outstanding**

## 1. Scope implemented

The new backend implements a separate, private, fail-closed PDF ingestion path. The previous public/static upload design is not reused.

- A database-backed `DocumentBlob` manifest tracks document ID, independently sequenced file revision, opaque storage object key, original display name, byte count, MIME, SHA-256 digest, scanner identifier, uploader, and UTC creation time (database currently stores naive UTC).
- PostgreSQL migration `e4d92f6a301b` follows `d0a7bc120e34` and creates a unique (document, revision) constraint and append-only UPDATE/DELETE trigger.
- The service `app/services/documents/private_storage.py` streams into a restricted private quarantine file, enforces 16 MiB maximum file bytes, checks PDF header/end markers, invokes an explicitly configured ClamAV `clamscan` executable with timeout, and **rejects** submissions when the scanner is unavailable, times out, returns infection or errors. A clean scan precedes promotion.
- The promoted file has a cryptographically random name, restrictive filesystem permissions, and lives under `PRIVATE_DOCUMENT_ROOT` outside Flask static paths. It is never served by an unrestricted `/static` route.
- POST is limited to the document owner and an editable draft. Document-level row locking and a unique revision constraint prevent duplicate revision numbers; the file manifest and the activity record commit together. Failed database commits attempt to clean up promoted objects.
- Listing requires existing document visibility; downloads additionally require ownership **or** an explicit active `can_download` share. On every download the object is rehashed and must match its persisted SHA-256; a mismatch returns service-unavailable rather than suspect bytes.
- Removed legacy document-path download behavior (returns HTTP 410 pending migration), blocked legacy static upload/QR paths in Flask, and removed internal path/secret fields from several legacy serializers.

## 2. Newly added document endpoints

- `POST /api/documents/<id>/files` — `multipart/form-data`, one `file` field, PDF only; returns private manifest metadata, HTTP 201.
- `GET /api/documents/<id>/files` — authorized file revision metadata, maximum 100 entries.
- `GET /api/documents/<id>/files/<file_id>/download` — authorized attachment transfer after SHA-256 verification, `Cache-Control: no-store, private`.

No endpoint accepts a caller-provided filesystem path, object key, scanner result, digest, uploader ID, document status or revision.

## 3. Configuration

The existing `config.py` now reads:

```dotenv
PRIVATE_DOCUMENT_ROOT=/var/lib/trustseal/private-objects
DOCUMENT_CLAMSCAN_BINARY=/usr/bin/clamscan
DOCUMENT_SCAN_TIMEOUT=30
```

Prerequisites:

1. Run the Flask service as an unprivileged dedicated service account.
2. Provision the private directory with owner/group appropriate to that account and permissions **0700**. Do not use a web-served, shared, symlinked or world-readable location.
3. Install and continually update ClamAV signatures. Keep the executable path fixed and owned by the OS/package manager, not by the web user.
4. Set up encrypted backups of BOTH PostgreSQL and the private object directory. Database-only restores will not restore document bytes.
5. Ensure public reverse proxies/CDNs explicitly deny `/static/uploads/` and `/static/qrcodes/`. The Flask block alone cannot protect assets served directly by nginx, Apache, a CDN or object-store public ACLs.
6. Replay the complete migration chain against a disposable PostgreSQL database, then validate upgrade against a representative restored existing database. Apply to production only after a documented backup and rollback/recovery drill.

## 4. Security/assurance boundaries

**Only PDF is supported by this slice.** DOCX, JPEG, PNG, archive, HTML, and office format conversion are not implemented. The PDF header/trailer gate is only format sniffing; it is not exhaustive PDF structural validation or sanitization. ClamAV checks are necessary here but are not a guarantee that an uploaded file is harmless. No file preview, script removal, PDF/A conversion, embedded-content policy or sandboxed rendering is provided.

The file store is a local private filesystem, **not WORM/cloud Object Lock**. The append-only database trigger prevents normal updates and deletes, but administrators with sufficiently privileged database or filesystem access can still tamper with both manifest and stored bytes. Stronger guarantees require independent external audit checkpoints, signed manifest anchoring, tenant policies, immutable object storage, and restore verification.

An uploaded PDF is **not signed, stamped, legally sealed, certified, timestamped, or publicly verifiable** just because the file passed the scanner or has a SHA-256 digest.

## 5. Tests and operational gates

Added `tests/test_private_document_storage.py` covering staging and promotion, digest, missing scanner, invalid filename/PDF, file size, directory traversal, public storage root, and integrity mismatch. Scanner success is mocked in unit tests. These tests have **not been executed** here: the available runtime has no Flask installation, and previous GitHub clone network access was unavailable.

Before enabling the feature, add and run:

- Flask integration tests of ownership, cross-tenant read/write isolation, can_view versus can_download, expiry, multi-file requests, oversized multipart bodies and corrupted object recovery.
- Real ClamAV clean, infected, unavailable, timeout and permission-error tests in an isolated environment with current signature database.
- PostgreSQL migration tests, unique-revision concurrency tests, trigger tamper tests, orphan-cleanup reconciliation, disk-full failures, simulated crash tests and backups/restores.
- PDF validation with a hardened parser and sandboxed converter/preview service before any rendering or signing workflow.
- Threat review of reverse proxy paths, filesystem permissions, symlink/mount attacks, malware scanning policy and private object backup.
- Upgrade preexisting static uploads via a separate auditable quarantine/re-scan/import process; do not blindly move them or treat historic unscreened files as clean.

## 6. Remaining backend implementation order

1. Private object and manifest lifecycle: orphan reconciliation, retention/holds, encrypted backups and validated restores; S3/object-lock adapter as needed.
2. Safe preview and conversion pipeline, quarantine processing jobs, structural PDF checks, DOCX/images behind isolated converter.
3. Transactional audit ledger and durable outbox workers, idempotency, dead-letter recovery and health checks.
4. Envelope creation, participant authorization, explicit consent, PDF finalization, immutable evidence and verifier.
5. Governed electronic stamp authorization and impression verification.
6. Billing/payment-provider workflows and comprehensive tenant-scoped API policy across remaining legacy routes.

**No production system was migrated or tested in this conversation.**


## 7. Follow-up hardening in the same checkpoint

- Admin bootstrap no longer falls back to `admin123` or prints any initial password. Creating the first admin now requires `ADMIN_PASSWORD` with at least 16 characters set through the environment. Existing admin accounts are left unchanged.
- The production factory rejects missing `SECRET_KEY`/`JWT_SECRET_KEY`, Flask debugging, or the repository's example local PostgreSQL credentials.
- The legacy document model serializers no longer include internal `file_path`, raw signature data, signature IP addresses or share tokens; nested collections use limited metadata. Direct legacy share, version and signature serialization similarly omits sensitive fields.
- Fixed the private object-key format validator to accept only `64 hex characters + .pdf` and prevent path-based access.
- Confirmed the manifest model, private storage service, database migration and endpoint code are present on GitHub after the commits.

**Runtime status remains unchanged:** Python dependencies (including Flask) are unavailable in the execution container; PostgreSQL and ClamAV integrations have not been tested. The new service must not be presented as operationally validated.
