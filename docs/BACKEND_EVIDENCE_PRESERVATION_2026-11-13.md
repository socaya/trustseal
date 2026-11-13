# TrustSeal Backend — Evidence Preservation, Legal Holds and Integrity Checkpoints

**Date:** 13 November 2026  
**Branch:** `main`  
**Assurance:** signed platform integrity observations, **not** an accredited trusted timestamp or independent audit anchor.

## Overview

TrustSeal now offers a protected evidence-preservation control plane for cryptographically finalized PDFs and their separately signed stamped derivatives. The implementation stores retention commitments, independently releasable legal holds, and signed repeatable observations of retained PDF integrity. These are separate from the original PDF's CMS signature, TrustSeal's signer-held detached endorsements and stamp issuance proofs.

**There is no destructive retention-expiry purge endpoint.** An expired retention commitment, even without an active legal hold, does not authorize object deletion automatically. This is deliberately fail-closed until legal policy, storage isolation, external retention controls and deletion approval procedures are completed.

## Data model and persistence

`app/models/evidence_preservation.py` introduces:

1. `EvidenceRetention`: one immutable tenant-associated retention entry per finalized/stamped artifact; frozen output SHA-256, duration, author and creation timestamp. The current API accepts 365–36,500 days (one to 100 years). These periods are **configurable choices, not statements of jurisdictional compliance**.
2. `EvidenceLegalHold`: attributable legal hold with reason and protected start time. Releases are allowed only once, by an independent administrator who was not the hold requester, and must record a meaningful release reason.
3. `EvidenceCheckpoint`: immutable canonical observation, certificate-sealed PDF artifact reference/hash, protected operator identity, signed Ed25519 payload and time observed.

Alembic revisions `o9d317b2e0a8` and `p0e428c3f1b9` follow `n8c206a1d9f7`. PostgreSQL prevents ordinary UPDATE/DELETE of retention/checkpoint rows, prevents deleting legal holds, and restricts hold updates to one independently authorized, documented release. A privileged database or storage administrator is not prevented from tampering by these triggers; external immutable custody and audit anchoring are needed for adversarial protection.

No unprivileged access to these records is granted.

## Authentication and API

All routes require an active JWT and an authorized administrator in the same organization.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/evidence-preservation/retentions` | Register original artifact and retention term |
| GET | `/api/evidence-preservation/retentions/{id}` | Inspect duration and active-hold count |
| POST | `/api/evidence-preservation/retentions/{id}/holds` | Place a hold with a specific legal reason |
| GET | `/api/evidence-preservation/retentions/{id}/holds` | List authored/released holds |
| POST | `/api/evidence-preservation/holds/{id}/release` | Independently release a hold with documented reason |
| GET | `/api/evidence-preservation/retentions/{id}/checkpoints` | List prior detached cryptographic observations |
| GET | `/api/evidence-preservation/checkpoints/{id}/export` | Export one verified signed checkpoint |

Retention registration takes exactly:

```json
{
  "artifact_type": "finalized_pdf",
  "artifact_id": 123,
  "retention_days": 3650
}
```

Supported types are `finalized_pdf` and `stamped_pdf`. Retention entries are immutable and cannot be shortened or overwritten. Legal holds are placed with `{"reason":"Specific reason for preservation..."}`. Release requires `{"reason":"Specific independent authorization for release..."}`. The persisted release record preserves requester, releaser and reasons. The decision is reflected in audit/outbox events. Importantly, release of a hold **does not** automatically delete files.

The API does not provide a retention bypass or raw file-deletion action.

## Signed integrity checkpoints

The operator can create or inspect a preserved PDF checkpoint using:

```bash
flask preservation checkpoint 123
flask preservation verify 456
```

The checkpoint is disabled by default. Issuance requires a separately configured active administrator in the same organization, who must differ from the creator of the retention commitment.

Before signing, TrustSeal re-hashes the actual privately stored PDF, validates its CMS/PAdES-compatible platform certificate against its pinned trust root and exact certificate fingerprint, and compares the signed evidence digest. The signed observation includes the identity and SHA-256 of the artifact, retention duration, organization, operator and UTC system-observation time. A protected Ed25519 key signs the canonical JSON. The new immutable checkpoint and transactional audit/outbox event are committed together.

`flask preservation verify` reconstructs and verifies the checkpoint payload, validates its signature with an explicitly trusted public key, and also checks the *current* stored PDF bytes. If the bytes later change, live verification fails.

**The observation time comes from TrustSeal's system clock.** It is not a trusted timestamp from an independent RFC 3161 Time-Stamp Authority, and database uniqueness/hash-based checks are not independently anchored.

### Configuration

```dotenv
EVIDENCE_CHECKPOINT_ENABLED=false
EVIDENCE_CHECKPOINT_PRIVATE_KEY=/etc/trustseal/keys/checkpoint-private.pem
EVIDENCE_CHECKPOINT_PUBLIC_KEY=/etc/trustseal/keys/checkpoint-public.pem
EVIDENCE_CHECKPOINT_TRUSTED_KEYS_JSON=
EVIDENCE_CHECKPOINT_OPERATOR_ID=
```

The private key must be an absolute-path, non-symlink PEM with no group/world permissions; never commit it. The public key's fingerprint should be distributed separately through a trusted channel. `EVIDENCE_CHECKPOINT_TRUSTED_KEYS_JSON` is an optional fingerprint-to-file registry for historical public keys after rotation.

The current file-backed adapter is a staging tool, not high-assurance production HSM custody.

## External offline verification

`examples/verify_checkpoint_offline.py` verifies an exported detached checkpoint JSON against an independently supplied PEM public key **and independently pinned Ed25519 key fingerprint**. It needs no TrustSeal API or database access.

```bash
python examples/verify_checkpoint_offline.py \
  --evidence checkpoint.json \
  --public-key /trusted/checkpoint-public.pem \
  --fingerprint ed25519-sha256:<64 lowercase hex characters>
```

A successful result proves that the specified private key signed the included canonical observation of the claimed artifact SHA-256, subject to key custody and compromise history. It **does not** by itself prove that the PDF bytes still exist, establish the true wall-clock time of the observation, validate revocation status or prove the PDF's separate CMS certificate signature. For present-time integrity, verify the PDF independently and compare its SHA-256 with the checkpoint payload.

## Tests and production gates

The code includes:

- `tests/test_evidence_preservation.py`: deterministic Ed25519 sign/verify, tampering, fail-closed deletion policy.
- `tests/test_offline_checkpoint_verifier.py`: offline signature and pinned-key mismatch rejection.
- `tests/integration/test_evidence_preservation_api.py`: PostgreSQL tenant administration, immutable retention, legal hold, independent release, operator issuance, signature verification and export.
- `tests/test_event_delivery.py`: explicit event-handler allowlisting.

PostgreSQL migration replay in CI uses a guarded disposable legacy-schema baseline. It does not repair or replay the original 2025 bootstrap chain from a restored production-like database.

**Still required before trustworthy long-term archival use:**

1. Object-store WORM/immutability, retention policy enforcement below application administrators, independent immutable evidence anchors, tamper-evident external chain.
2. An approved legal retention schedule per document classification and jurisdiction, legal hold policy, deletion approval/appeal procedures, backup/restore testing and privacy-compliant disposal workflows.
3. Trusted timestamping (RFC 3161 TSA), OCSP/CRL revocation evidence, certificate path-validation policy, PAdES-LT/LTA evidence, periodic renewal/resealing and key-compromise procedures.
4. HSM/KMS signer, strict separation of operating roles, MFA, secure time synchronization and append-only monitoring logs.
5. Scheduled re-verification with alert delivery and independently reviewed incident response; the current CLI creates checkpoints **only when invoked**.
6. PDF parser sandboxing, CPU/memory/time budgets, anti-malware controls and disaster recovery simulations.
7. Historical upgrade rehearsal on an actual restored dataset.

This checkpoint introduces operational preservation controls; it is **not a complete legally certified archiving or qualified trust service**. Consult the current GitHub Actions result for actual executed test counts.
