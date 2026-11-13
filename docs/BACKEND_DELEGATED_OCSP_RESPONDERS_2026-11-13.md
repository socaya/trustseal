# TrustSeal — Delegated OCSP Signer Validation and Retained Certificates

**Date:** 13 November 2026  
**Branch:** `main`  
**Scope:** cryptographically validate an OCSP responder delegated by the TSA certificate issuer and preserve the exact signing certificate for later verification.

## Security and trust boundary

The previous OCSP verifier supported only a signed response produced directly by the certificate issuer. This change extends the same offline, operator-managed OCSP evidence workflow to a **single delegated responder directly certified by the issuer**.

TrustSeal does not trust arbitrary certificates found in a response. The responder identity is resolved using the OCSP signed `responderID` (name or public-key hash), checked for uniqueness, and tied to an exact certificate. For a delegated response, the signing certificate must be embedded in the response, directly issued by the same CA that issued the TSA signer, verified against that CA's public key, permitted by X.509 Extended Key Usage `id-kp-OCSPSigning`, permitted by digital-signature Key Usage, and explicitly designated as a non-CA. The responder certificate must be valid at the evidence observation time. The response signature must validate using **that exact responder public key**; the authority and cryptographic OCSP `CertID` checks on the target TSA certificate remain unchanged.

A directly CA-signed response remains supported. A delegated responder is not permitted to issue certificates or to substitute a self-asserted signing identity. A response with a missing, mismatched, duplicated or unauthorized signer fails verification.

## Persistence and provenance

Alembic revision `t4c862a7d5f3` follows `s3b751f6c4e2`. It introduces two nullable fields on the existing append-only `ocsp_evidence` table:

- `responder_certificate_sha256`: DER SHA-256 fingerprint of the exact trusted signer
- `responder_der_b64`: exact responder certificate bytes, retained separately from signed OCSP response bytes

New captures write both fields; they are part of the immutable signed-evidence record. Historical rows remain intact. Historical direct-issuer observations without these two fields remain valid for compatibility. Historical delegated observations without retained responder certificate data **must fail closed** rather than being silently accepted. The signed response is still verified using its embedded certificate as applicable.

The issuer PEM, TSA leaf certificate and root trust anchor remain operator-approved configuration inputs. Capture continues to read a single preapproved local DER response without arbitrary network fetches. The original timestamp must also pass verification.

## Usage

```bash
flask ocsp capture <timestamp_id>
flask ocsp verify <ocsp_evidence_id>
```

Authenticated tenant administrators can export the validated evidence at `GET /api/evidence-preservation/ocsp/{id}/export`. The export now includes the exact responder certificate DER and SHA-256, in addition to the subject, issuer and OCSP response evidence. Access remains tenant-isolated and export revalidates the signed RFC 3161 timestamp.

## Tests

`tests/test_ocsp_delegated_responder.py` creates actual X.509 roots, leaves and delegated responder certificates and signs genuine OCSP responses. It tests valid delegated authorization, absent `OCSPSigning` EKU, expired certificates, CA misuse, absent embedded certificates, tampering, pinned responder fingerprints, and rejection of unverifiable historical delegated evidence. Existing direct-issuer response tests remain in place.

Check the latest GitHub Actions result; tests and migration replay must pass before production rollout.

## Remaining high-assurance work

This **does not** implement a full independently audited PKIX trust engine, certificate-path building across arbitrarily many intermediates, certificate status for every certificate in the chain, explicit OCSP responder certificate revocation or `id-pkix-ocsp-nocheck` trust policy, current trust-list management, network-fetched OCSP evidence, or PAdES-LT/LTA PDF archive signatures. A delegated responder certificate may itself be revoked, and a cryptographically valid response alone does not establish its complete validation status. Production legal-trust claims require independently verified status evidence for the entire chain and the relevant historical validation time.

TrustSeal's historical migration-bootstrap gap also remains outstanding; disposable CI schema replay is not proof of an upgrade of a historical production-like database.
