# TrustSeal Backend — RFC 3161 Trusted Timestamp Evidence

**Date:** 13 November 2026  
**Repository:** `socaya/trustseal`  
**Branch:** `main`

## Purpose and supported assurance

This phase introduces **real detached RFC 3161 TimeStampResp evidence** against the SHA-256 of an already finalized or visually stamped PDF. It does not alter the original PDF, does not embed a document timestamp signature into PDF bytes, and does not implement PAdES-LT or PAdES-LTA.

A configured timestamp authority (TSA) signs an ASN.1 `TSTInfo` message imprint. TrustSeal validates the returned signed CMS response, TSA certificate chain and configured TSA signer certificate identity. It retains the exact DER response for later verification.

A valid response attests that a specific TSA signer key issued a token containing the requested hash and generation time. Whether that TSA is accredited, trusted for a specific jurisdiction, and entitled to provide qualified timestamps must be established separately by contract, policy, certificate status and applicable law. No qualified or legally binding assurance is implied by implementing RFC 3161 syntax.

## Architecture and workflow

1. An active, tenant-scoped `EvidenceRetention` row must already bind an immutable finalized PDF or approved stamped derivative.
2. An operator-only command checks active independently authorized administrator identity and verifies retained PDF bytes, CMS signature, exact signer certificate fingerprint, the signed review/stamp evidence digest and, for stamped PDFs, the original PDF/approval/graphic-design provenance.
3. The integration builds a fresh ASN.1 RFC 3161 `TimeStampReq` with SHA-256 message imprint, cryptographically random 128-bit nonce and `cert_req=true`.
4. It sends a bounded HTTPS POST to a fixed operator-configured TSA URL, with a short timeout, expected content type, no redirects and a maximum 64 KiB response.
5. It rejects failed TSA status, malformed ASN.1, missing or multiple signers, incorrect message imprint, wrong nonce, unsupported signer certificate identity or signer certificate differing from the **exact pinned TSA PEM leaf**.
6. It independently runs `openssl ts -verify` with the original SHA-256 and explicitly configured root and leaf certificates. OpenSSL must validate the timestamp CMS signature and timestamping certificate purpose. A TSA response that fails verification is discarded.
7. At issuance only, the TSA generation time must be within ten minutes of the system clock; retained historical tokens are not subjected to this issuance-window check.
8. The exact verified DER token is stored as Base64 with SHA-256 token hash, TSA leaf certificate SHA-256 fingerprint, UTC generation time, retained artifact SHA-256, tenant identity and issuing operator.
9. The immutable record and `evidence.timestamp.issued` security event/outbox message commit atomically. A PostgreSQL append-only trigger prevents ordinary edits or deletes.
10. The verifier rechecks the retained token, its signer identity, certificate and imprint; the operator CLI also checks the **current retained PDF** against the recorded SHA-256. The export endpoint returns the actual `.tsr` DER bytes only when their stored trust evidence validates.

## Operator commands

```bash
flask timestamp issue 123
flask timestamp verify 456
```

Here `123` is a tenant retention record ID; `456` is a timestamp record ID. No untrusted end user may choose the TSA URL or signing policy through HTTP. Issuance is disabled by default.

## Tenant-scoped APIs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/evidence-preservation/retentions/{id}/timestamps` | List signed token metadata, without dumping full tokens |
| GET | `/api/evidence-preservation/timestamps/{id}/export` | Export verified RFC 3161 DER response as `.tsr` |

Both require active tenant administrator privileges. Cross-tenant identifiers cannot be used to enumerate other tenants' timestamps.

## Configuration

```dotenv
RFC3161_ENABLED=false
RFC3161_TSA_URL=https://approved-tsa.example.invalid/timestamp
RFC3161_TSA_CERT_PEM=/etc/trustseal/trust/approved-tsa-leaf.pem
RFC3161_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-tsa-root.pem
RFC3161_OPENSSL_BINARY=openssl

# Existing independent checkpoint operator authorization applies:
EVIDENCE_CHECKPOINT_OPERATOR_ID=
```

The TSA leaf and root paths must be absolute, regular, non-symlink files. The TSA endpoint must be HTTPS on port 443 with no HTTP redirects. Keep trust roots and pinned leaf certificates under an operator-reviewed certificate-rotation policy. Response storage is capped at 64 KiB. The integration must run with outbound network policy restricting access to approved TSA endpoints. A deployment-configured proxy or DNS could still alter where a configured hostname resolves; infrastructure must enforce its own egress policy.

The current implementation records timestamps against already-signed artifact hashes. **It does not capture or preserve OCSP/CRL revocation statements**. OpenSSL's certificate-path verification is not by itself historical revocation evidence. A TSA certificate renewal/expiry or current trust-root change can invalidate historical rechecks unless historical approved roots and validation data are retained under an explicit trust policy.

## Database and migrations

Revision `q1f539d4a2c0` follows `p0e428c3f1b9`. It creates append-only `evidence_timestamps` with a unique `(retention_id, token_sha256)` constraint, tenant and retention FKs, exact artifact hash, TSA leaf fingerprint, immutable DER token, issuance time and operator ID. The disposable CI baseline excludes this new table before replaying trust-service migrations.

The migration does not repair the earlier 2025 bootstrap incompatibility. An actual restore-and-upgrade rehearsal from a historical production-like database remains mandatory.

## Test coverage

- `tests/test_rfc3161_timestamp.py` checks disabled-by-default behaviour, unsafe URLs, malformed or oversized tokens, missing trust anchors, SHA-256 imprint creation and request nonce handling.
- `tests/integration/test_rfc3161_openssl.py` creates a **real disposable TSA** certificate and RFC 3161 timestamp with OpenSSL, validates an actual signed response, and rejects wrong imprints, nonce, pinned TSA certificates and trust root.
- Existing preservation and signing suites cover the retained PDF hash verification, staff authorization and database integrity.
- The timestamp audit event has an explicit allowlisted handler that revalidates cryptographic evidence.

See actual GitHub Actions results for the current commit before reporting the suite as passed.

## Remaining work and production release gates

1. Implement and preserve OCSP/CRL statements and a signed historical chain-validation profile, including certificate expiry, TSA certificate policy and revocation handling. Do not treat a chain valid today as sufficient historical proof.
2. Embed timestamp/document-validation evidence into an incrementally updated PDF when PAdES-LT/LTA is required; this module intentionally exports **detached** RFC 3161 evidence.
3. Add approved TSA onboarding, egress allowlists, certificate expiry alerting, provider outage handling, optional multi-TSA policy, retries, idempotence and provider SLA checks.
4. Use HSM/KMS-controlled keys for platform signatures and checkpoint evidence; use independent archival storage and externally anchored/WORM proofs.
5. Introduce periodic renewal before algorithm or key expiration, archival policy, trusted retention classifications and jurisdiction-appropriate legal review.
6. Sandbox PDF and ASN.1 parsing, enforce resource quotas at the worker boundary and test large hostile documents and compromised-provider scenarios.
7. Rehearse historical database upgrades and tenant-separated backup/restore.

This is a **detached RFC 3161 timestamp workflow**, not a fully compliant qualified trust service or long-term archival signature stack.
