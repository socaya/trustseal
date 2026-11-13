# TrustSeal Backend — Controlled OCSP Evidence for TSA Certificates

**Date:** 13 November 2026  
**Repository:** socaya/trustseal  
**Branch:** main

## Scope and assurance

This phase adds **signed OCSP response evidence for an already retained RFC 3161 Time-Stamp Authority (TSA) signer certificate**. It extends the existing CRL evidence module without overwriting earlier evidence or changing an already signed PDF.

The current verifier intentionally supports only **directly issuer-signed** OCSP responses. Delegated OCSP responders, responder certificate policies, OCSP network discovery, automatic live fetching, nonce-backed online queries, multi-level chain aggregation, and PAdES-LT/LTA are **not implemented**. An issuer-signed response verified with the configured root may be retained as a historical observation, but not described as a qualified trust service or sufficient evidence of nonrevocation at a prior signing time.

## Verification policy

1. Start with an existing organization-specific `EvidenceRetention` and verified, cryptographically pinned `EvidenceTimestamp`. An independent administrator must be configured as operator.
2. Read one operator-approved, local DER OCSP response (up to 128 KiB) and an approved issuer PEM. Application users cannot submit arbitrary responder URLs, file paths, certificate chains or trust roots.
3. Verify the retained timestamp token and its SHA-256, generation time, and exact TSA certificate fingerprint against the configured root and signer.
4. Load the OCSP response with the X.509 cryptography library, require an OCSP `SUCCESSFUL` response and validate the pinned trust-root, issuer CA constraints and TSA signer certificate signature.
5. Reconstruct the expected OCSP `CertID` for the exact TSA leaf (SHA-256 issuer hashes plus serial number), require a directly issuer-signed response, reject an unsupported delegated responder identity, and cryptographically verify the response signature.
6. Check the TSA leaf, issuer and root certificate validity at observation time. Enforce `thisUpdate <= checked_at < nextUpdate`, require a valid `producedAt`, reject stale and future-dated responses, and inspect the responder's explicit `good`, `revoked` or `unknown` status.
7. **Only `good` observations are captured.** A `revoked` or `unknown` result is rejected, not silently converted to `good`.
8. Save the exact DER response, TSA leaf and issuer certificate bytes, SHA-256 fingerprints, status and times to an append-only PostgreSQL record and transactionally enqueue `evidence.ocsp.captured`.
9. On later verification or export, revalidate all stored ASN.1 bytes, their signatures, original timestamps, record digests, tenant binding and applicable trust root. Historical verification evaluates the original observation time; it must not pretend an expired response remains current.

## Commands

```bash
flask ocsp capture 123
flask ocsp verify 456
```

Here `123` is the retained RFC 3161 timestamp ID and `456` is the saved OCSP observation ID.

## Authenticated APIs

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/evidence-preservation/timestamps/{id}/ocsp` | List OCSP observation metadata for the caller's organization |
| GET | `/api/evidence-preservation/ocsp/{id}/export` | Export verified OCSP DER and issuer/subject certificate evidence |

Both endpoints require an active authenticated tenant administrator and never disclose records from another tenant. There is no public OCSP upload or arbitrary URL fetch API.

## Configuration

```dotenv
OCSP_EVIDENCE_ENABLED=false
OCSP_EVIDENCE_DER=/etc/trustseal/revocation/approved-tsa-ocsp.der
OCSP_ISSUER_CERT_PEM=/etc/trustseal/trust/approved-tsa-issuer.pem
RFC3161_TSA_CERT_PEM=/etc/trustseal/trust/approved-tsa-leaf.pem
RFC3161_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-root.pem
EVIDENCE_CHECKPOINT_OPERATOR_ID=
```

This workflow is **disabled by default**. The OCSP evidence DER and issuer certificate must be obtained and reviewed by an administrator or a separate approved fetch process. The backend neither invokes a remote OCSP responder nor assumes that an arbitrary issuer URL is safe. Public OCSP fetch and responder discovery require an explicit network egress policy and anti-SSRF controls.

## Persistence and tests

Migration `s3b751f6c4e2` (following `r2a640e5b3d1`) creates append-only `ocsp_evidence`, with tenant, token and operator references, certificate and response DER, immutable hashes, production and validity timestamps, status and the observation timestamp. Duplicate signed responses for the same timestamp are restricted by a unique constraint.

`tests/test_ocsp_evidence.py` creates real issuer-signed OCSP responses and tests status interpretation, certificate and issuer mismatches, expiry, forgery and tampered historical observations. The existing CI suite also checks Alembic migration replay and exact outbox handler allowlisting.

## Remaining production scope

A complete long-term validation subsystem additionally requires verified delegated responder handling and OCSP signing EKU, historical trust-policy determination, chain status across every PDF/TSA certificate, certificate rotation/revocation of roots and intermediates, independent archival timestamps, OCSP nonce strategy for real-time requests, issuer-controlled responder discovery, and secure network egress. PAdES-LT/LTA requires embedding validated certificate/status material into appropriately signed incremental PDF updates. This module retains **detached evidence**, not a PAdES-LTA archive timestamp.

The original 2025 migration chain remains unproven on a representative restored production database; CI's disposable baseline does not substitute for an actual migration rehearsal.
