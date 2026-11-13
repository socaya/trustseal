# TrustSeal — Signed Certificate Revocation Evidence (CRL)

**Date:** 13 November 2026  
**Branch:** `main`  
**Status:** Implemented as an optional, operator-controlled **historical CRL evidence snapshot**, not a complete PAdES-LT/LTA implementation.

## Purpose and exact assurance

TrustSeal now preserves signed certificate revocation list (CRL) evidence for the leaf certificate that issued a retained RFC 3161 timestamp. This complements existing PDF signature verification, retained detached timestamp tokens, and immutable integrity checkpoints. It does not modify an already-signed PDF.

An accepted snapshot is evidence that an explicitly trusted certificate issuer signed a CRL that **did not list the configured TSA signer as revoked at the time of observation**. It is not proof of timeless certificate validity, not an online OCSP response, not automatically proof of non-revocation at the earlier PDF-signing time, and not a jurisdictionally qualified validation report.

## Controlled workflow

1. A tenant has an immutable `EvidenceRetention`, an already-verified detached `EvidenceTimestamp`, and an approved operator distinct from the retention creator.
2. Operators configure an approved DER CRL file and an approved PEM issuer certificate. The TSA signer and pinned trust root come from the already configured RFC 3161 trust settings. There is **no arbitrary URL fetching or user-uploaded CRL endpoint**.
3. The `revocation capture` command rereads and cryptographically validates the exact RFC 3161 token, its retained SHA-256, generation time and pinned signer certificate.
4. The CRL service decodes the original DER, verifies certificate names/issuer binding and the certificate-to-root trust signature path (one intermediate at most), checks issuer CA and CRL-signing key usage, validates its signed bytes using RSA/ECDSA/EdDSA as appropriate, enforces certificate validity intervals and the CRL's `thisUpdate` / `nextUpdate` window, and checks the CRL authority-key identifier when present.
5. If the TSA leaf serial is listed as revoked, TrustSeal **rejects capture** rather than saving a misleading positive status. The service can report a revoked status in isolated cryptographic tests.
6. Successful capture stores the *exact* CRL DER, TSA signer and issuer certificate DER, SHA-256 hashes, observation time, CRL validity window and an explicitly bounded status. The immutable database entry and transactional `evidence.crl.captured` event commit together.
7. Authorized tenant administrators can list CRL metadata or export the complete historical evidence. Export requires re-verifying the signed CRL against the currently configured root and its retained certificate binding.

## Operator commands

```bash
flask revocation capture 123
flask revocation verify 456
```

Here `123` is the immutable RFC 3161 timestamp record ID and `456` is a CRL evidence record ID.

### Configuration

```dotenv
CRL_EVIDENCE_ENABLED=false
CRL_EVIDENCE_DER=/etc/trustseal/revocation/approved-issuer.crl
CRL_ISSUER_CERT_PEM=/etc/trustseal/trust/approved-issuer.pem

# Existing pinned TSA trust configuration also applies
RFC3161_TSA_CERT_PEM=/etc/trustseal/trust/approved-tsa-leaf.pem
RFC3161_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-tsa-root.pem
EVIDENCE_CHECKPOINT_OPERATOR_ID=
```

The CRL is obtained through an operator-reviewed external process, then provided to TrustSeal from a controlled absolute-path local file. Operational teams must authenticate the origin of these files, renew CRLs before they expire, restrict file access, review keys and configure alerts for unavailable/expired evidence. A CRL is not retrieved over HTTP by application users.

## Authenticated API

| Method | Endpoint | Meaning |
| --- | --- | --- |
| GET | `/api/evidence-preservation/timestamps/{id}/revocations` | List revocation observation metadata for the caller's own tenant |
| GET | `/api/evidence-preservation/revocations/{id}/export` | Export validated CRL, TSA signer and issuer certificates as Base64 DER with accompanying provenance |

Cross-tenant records return not found, even when the requesting user is an administrator in another organization. Export requires the configured trusted root and validation of the historical certificate and CRL evidence. No private signing keys are accepted or exported.

## Data model and integrity

Alembic revision `r2a640e5b3d1`, following `q1f539d4a2c0`, creates `certificate_revocation_evidence` with timestamp/organization/operator FKs, certificate and CRL DER, hashes, signed validity window, verification status and observation time. A PostgreSQL append-only trigger rejects ordinary UPDATE/DELETE. Duplicate exact CRL captures for a timestamp are constrained by `(timestamp_id, crl_sha256)`.

This is database-enforced application integrity, not independent WORM retention. Privileged database operators require external oversight.

## Tests

- `tests/test_certificate_revocation.py` builds real RSA certificates and signed X.509 CRLs, validating non-revoked and revoked signers, expiry, issuer mismatch, invalid signatures, corrupt encoding and stored-evidence tampering.
- `tests/integration/test_crl_evidence_api.py` tests PostgreSQL-backed tenant-scoped CRL listing and protection against foreign-tenant evidence export.
- Existing `tests/integration/test_rfc3161_openssl.py` verifies actual RFC 3161 timestamp tokens against an approved signer and trust root.
- `tests/test_event_delivery.py` checks the explicit outbox handler allowlist.

See the latest GitHub Actions result before reporting the suite green.

## Limitations and next release gates

**Not yet implemented:** OCSP response acquisition/validation, issuer CRLs for every certificate in all PDF and TSA chains, algorithm/chain policy at a historical validation time, RFC 3161 document timestamp signatures embedded into signed PDFs, PAdES-LT/LTA archival data, key rotation and independent trust-list management.

The CRL observation is checked at its recorded observation time. A clean CRL at that time is **not sufficient** to prove certificate status at an earlier signing or timestamp generation time. Long-term validation needs verified historical revocation data, a relevant validation time, complete chains, trust policies, revocation reasons, and sometimes independent timestamps over the assembled evidence. CRL entry absence must never be advertised as unrestricted proof of trust.

Production readiness also requires: sandboxed ASN.1 parsing, issuer onboarding/approval, independent network egress controls for any future fetcher, a true historical migration rehearsal, external immutable archives and deployment certificate/key custody controls.
