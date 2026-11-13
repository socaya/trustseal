# Public PDF Verification — Backend Checkpoint

Date: 2026-11-13
Branch: main

## Contract and assurance

This implementation verifies a **caller-supplied** already-sealed PDF. It does not expose or search TrustSeal organizations, envelope records, participants, evidence packages or private document storage. It does not download PDFs on a caller's behalf.

`POST /api/public-verification/pdf` accepts multipart form fields:

- `pdf`: one caller-supplied PDF, maximum 16 MiB.
- `evidence_sha256`: exactly 64 lowercase hexadecimal characters matching the canonical exported review/endorsement evidence bundle.

The endpoint checks the PDF structure, its single `TrustSealPlatformSeal` CMS signature, signed review-evidence digest, cryptographic integrity, explicitly configured trusted CA, and **exact expected certificate fingerprint**. Successful result is **a platform seal validation**, not a personal signer CMS/PAdES signature, independently verified identity, legal-validity determination, revocation check or trusted timestamp.

The verifier returns `status: valid | invalid | invalid_request | unavailable`, minimal cryptographic booleans, an SHA-256 of the submitted PDF, and on successful parsing the configured signer certificate fingerprint and evidence SHA-256. Responses never return names, tenant identifiers, signer identities or server-side object references. The API has no database query, user session requirement, or private object access. Internal exception strings are suppressed.

## Safe deployment defaults

```dotenv
PUBLIC_PDF_VERIFICATION_ENABLED=false
# SHA-256 fingerprint of approved platform signing certificate, in lowercase hex.
PUBLIC_PDF_VERIFICATION_CERT_SHA256=
PDF_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-root-ca.pem
```

**Do not enable the public endpoint** without an ingress gateway with strict per-IP/per-account rate limits, total request-body limits, content-type restrictions, abuse monitoring, timeout limits, a worker sandbox for untrusted PDF parsing, and controlled public-facing deployment. In-process rate counters are inadequate for multi-worker production services. For now, the feature remains disabled by default until those controls are provided outside this module.

The certificate fingerprint must be distributed through a trusted channel and updated under a reviewed rotation procedure. A verifier configured with only a CA trust root can accept another certificate under the same authority; the pinned certificate SHA-256 closes that issuer-substitution gap. Multiple historical platform certificates and revocation policy are **not** yet supported by this public endpoint.

A correct response means only that the submitted bytes have an intact cryptographic platform certificate seal issued under this verifier's configured trust policy. TrustSeal has not established personal signers' identity via this endpoint. A forged/altered or unknown PDF must not return a valid result.

## Implemented code

- `app/blueprints/documents/api/public_pdf_verify_api.py` — upload-only independent verifier with no private database/storage access.
- `app/services/platform_pdf_seal.py` — exact embedded CMS signer-certificate SHA-256 validation.
- `app/blueprints/documents/api/sealed_pdf_api.py` — existing authenticated endpoints now verify the manifest's original certificate fingerprint.
- `config.py` — disabled-by-default verification and pinned certificate controls.
- `tests/test_public_pdf_verification.py` — disabled configuration, missing fingerprint, invalid file and digest, size cap, no tenant metadata and privacy checks.
- `tests/integration/test_platform_pdf_roundtrip.py` — real-PDF valid/invalid certificate fingerprint assertions.

## Release gates

Required before production:

1. Review the current GitHub Actions run and ensure full suite passes.
2. Exercise a real platform-signed PDF and an altered PDF through the full multipart API, not only service-level integration tests.
3. Implement or configure ingress traffic limits, upload scanning policy, worker isolation and resource/time budgets.
4. Validate certificate rollover, revocation/expiry policy, PKI trust and historical signature verification semantics.
5. Confirm externally shared evidence has matching canonical digest and independently verifiable signer-held signatures.
6. Add a real upgrade rehearsal from a representative historical database. CI currently uses a guarded disposable model baseline because the original 2025 first revision cannot bootstrap a blank database.

No production verification deployment or untrusted-document sandbox was performed in this checkpoint.
