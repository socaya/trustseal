# TrustSeal Backend Checkpoint — Detached Cryptographic Review Attestations

Date: 2026-11-13
Branch: `main`
Status: code committed, tests and migrations **not executed**

## Assurance distinction

This checkpoint does **not** produce a cryptographically signed PDF, PAdES signature, qualified electronic signature, personally held signer key, certificate-based attestation by the human recipient, or a legally certified trust service. The new cryptographic artifact is a *platform-issued, detached Ed25519 receipt* asserting that TrustSeal recorded an authenticated participant's earlier review acknowledgement or decline.

The distinction must remain visible in API/UI: `platform_attestation_of_review_only`, `not_a_pdf_signature=true`.

## Implemented

- `app/services/signing_receipts.py` defines canonical UTF-8 JSON serialization, versioned receipt schema `trustseal.review-receipt.v1`, Ed25519 signing and verification, SHA-256 fingerprint-derived key IDs, and a payload tying together the exact envelope, organization, PDF manifest, PDF SHA-256, participant, review decision, consent version/digest and timestamp.
- `app/models/review_receipt.py` stores immutable receipt records; `migrations/versions/g1a42e05fd90_review_receipts.py` follows `f2a91d6e4b80`, creates FK/unique constraints and uses an append-only PostgreSQL trigger.
- `flask receipts issue <decision_id>` is an **operator-only CLI operation**. It validates existing consent evidence, loads an OS-protected Ed25519 key, verifies that its public key matches the pinned trusted key, signs the evidence record, verifies the generated signature, and commits it along with an outbox/audit event. Repeating issuance returns the existing receipt instead of creating another.
- `GET /api/review-receipts/<id>` checks a JWT-authenticated same-tenant envelope owner or assigned participant, verifies the detached signature with an explicitly configured trusted key, and compares the full signed payload against reconstructed database evidence. This is a signed-record integrity check, not final document verification.
- `GET /api/review-receipts/<id>/export` provides the complete detached receipt (payload, algorithm, key ID and signature) to authorized parties who can independently verify its Ed25519 signature with a public key they obtained and pinned through a separately trusted channel.
- `REVIEW_RECEIPT_TRUSTED_KEYS_JSON` optionally registers historical trusted public key paths by fingerprint for controlled key rotation. Unknown/unpinned keys are rejected rather than accepting a key supplied in a receipt.
- `tests/test_review_receipts.py` includes positive signing/verifying, payload tampering, wrong key, algorithm/schema tampering, canonicalization, unknown key and key rotation fingerprint tests. These tests have not been executed.

## Configuration and operation

A separate crypto dependency is declared in `requirements-crypto.txt`; the repository still lacks a complete application lockfile. Integrators must resolve and pin all dependencies in a reviewed deployment environment.

For a **staging-only** protected-file key adapter:

```dotenv
REVIEW_RECEIPT_PRIVATE_KEY=/etc/trustseal/keys/review-ed25519-private.pem
REVIEW_RECEIPT_PUBLIC_KEY=/etc/trustseal/keys/review-ed25519-public.pem
# Optional: JSON mapping trusted historical key ID -> absolute PEM path.
REVIEW_RECEIPT_TRUSTED_KEYS_JSON=
```

The private key path must be absolute, an ordinary non-symlink file with no group/world access (0600 recommended), and never kept in source control, Flask static assets or container image layers. Private-key material should be held by a dedicated signing service using a KMS/HSM for production. The current CLI file-backed adapter is not a production-grade key custodian.

The exported receipt's public-key fingerprint must be distributed and pinned independently of the untrusted receipt itself. In a compromised application, a response that simply says `valid=true` is insufficient proof.

## Required verification before deployment

1. Replay the entire Alembic migration chain in PostgreSQL, including triggers, unique constraints, and clean upgrade from a restored instance.
2. Run cryptographic unit tests and integration tests covering concurrency, duplicate issue, absent/revoked key, bad file permissions, expired/revoked account, cross-tenant access, detached export, tamper detection, rollback and key rotation.
3. Confirm the outbox `review.receipt.issued` handler remains allowlisted and never creates arbitrary external side effects.
4. Build an independent verifier that validates the exported receipt against an externally distributed trusted-key registry, an immutable source-PDF copy and retained key status/revocation policy.
5. Implement key lifecycle: managed generation, rotation, secure custody, backup/restore, compromise response, key revocation policy, dual-control operations, and protected audit logs.
6. Add a complete dependency manifest/lockfile, test automation and deployment configuration; none are provided by this checkpoint.

## What comes next for real PDF signing

A separate standards-aware PDF finalization service must use a defined signed-PDF profile (such as PAdES where appropriate), protect per-signer or organization signing keys under explicit authority, bind a frozen immutable PDF revision, preserve the exact signed byte ranges, embed and validate a CMS/PKCS#7 signature and trusted certificate chain, capture evidence and timestamping from authorized services, and atomically commit exactly one finalized artifact. These are **unimplemented**.

Do not remove the central block on legacy generic signature writes or label a review receipt as a signed PDF.

**No production keys were created, migrations executed, files signed or backend completion claim made in this session.**
