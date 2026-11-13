# TrustSeal Backend — Platform Certificate PDF Seal Module

Date: 2026-11-13
Branch: main
Status: SOURCE COMMITTED; LIVE TESTING AND DEPLOYMENT NOT VERIFIED

## Assurance and intended purpose

This module adds a **certificate-backed platform seal** to a frozen private PDF after an internal TrustSeal envelope's entire sequential participant roster has recorded authenticated review acknowledgements. The issuer of the PDF's embedded CMS signature is the **platform certificate holder**. It is NOT a signature made using any participant's personal key, and it does not represent multiple individual signatures. The completed review receipts remain separate evidence of recorded review decisions.

The resulting PDF has an embedded CMS/PKCS#7 signature in the `TrustSealPlatformSeal` field using pyHanko's PAdES subfilter, SHA-256, and a configured PKCS#12 certificate. The profile label `platform_pades_b_b` identifies this specific implementation target; **formal profile conformance and legal validity have not been certified**. No RFC 3161 trusted timestamp, revocation-checking integration, validation-info embedding, PAdES-LT/LTA, government accreditation, or personal certificate-based signature is provided by this slice.

## Components delivered

### Services

`app/services/platform_pdf_seal.py` uses pyHanko to parse the source, reject already signed PDFs for this one-seal workflow, apply a CMS platform signature, and validate the signed PDF with an explicitly configured certificate trust root. If dependencies, key, trust root or trusted validation are unavailable, the operation fails instead of returning a success artifact. Private PKCS#12 must be at an absolute non-symlink path with no group/world file permissions.

### Finalized artifact storage

`app/models/pdf_finalization.py` and Alembic migration `h2b640a1d8f3` (following `g1a42e05fd90`) create a unique per-envelope `FinalizedPdf` manifest recording the frozen source blob and SHA-256, private output object key and hash, size, certificate SHA-256 fingerprint, signature field, and profile. A PostgreSQL trigger disallows ordinary UPDATE/DELETE of these records; another guard prevents cancelling envelopes after finalization.

The output uses the previously added private, scanned PDF storage service: a distinct non-public object with a random key, ClamAV scanning, SHA-256 integrity check, and denied public static access. Source and output filesystem objects must be backed up with the database. The database trigger does **not** provide WORM immutability against privileged storage/database operators.

### Operator flow and authorization

`flask pdf-seal finalize <envelope_id>` is an internal CLI command, not a public HTTP action. Before signing, it:

1. Acquires a row lock on the prepared envelope, checks it has not been finalized, and verifies every participant has an `acknowledged` decision for the exact prepared PDF digest.
2. Requires a previously issued, cryptographically verified Ed25519 review receipt for every acknowledgement, checked against the full current immutable participant/consent evidence payload and a pinned trusted key.
3. Verifies the frozen source manifest and rehashes the source PDF from private storage.
4. Loads the protected platform PKCS#12, applies the CMS PDF signature with pyHanko, and validates its embedded signature against an explicitly trusted root.
5. Re-scans and stores the output PDF privately, and atomically commits the unique finalized manifest and `platform.pdf.sealed` security/outbox event.
6. Refuses a second final artifact; a repeat operation returns the existing record.

`flask pdf-seal verify <envelope_id>` rehashes stored bytes and validates the certificate-backed PDF signature with the configured trust root. Neither CLI command is a personalized signer workflow.

### Authorized APIs

- `GET /api/platform-sealed-pdfs/envelopes/<id>/verify` — reports embedded CMS validity, byte integrity and certificate trust; requires same-organization envelope owner or assigned recipient.
- `GET /api/platform-sealed-pdfs/envelopes/<id>/download` — downloads scanned private PDF only after the stored-object digest and embedded signature both validate; same authorization requirement.

Both report `platform_certificate_seal_not_individual_signatures` semantics. The generic legacy signing CRUD routes remain blocked.

### Configuration

Install `requirements-signing.txt` into a fully resolved, pinned backend environment and configure:

```dotenv
PDF_PLATFORM_PKCS12=/etc/trustseal/keys/platform-seal.p12
PDF_PLATFORM_PKCS12_PASSWORD=<secret supplied by secure deployment secret manager>
PDF_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-root-ca.pem
PRIVATE_DOCUMENT_ROOT=/var/lib/trustseal/private-objects
DOCUMENT_CLAMSCAN_BINARY=/usr/bin/clamscan
```

Do not check in the PKCS#12 bundle, secret, or any trusted key material. Restrict private files and protect secrets in process environment and diagnostics. This implementation uses a local PKCS#12 adapter and **is not suitable for high-assurance production custody without a dedicated KMS/HSM signer, dedicated service isolation, privilege separation and controlled key ceremony**.

The platform certificate must have the correct purpose/key usage and chain to an independently approved trust anchor. Never use a test/self-signed root as production trust. Offline chain validation with `allow_fetching=False` does not provide current certificate revocation checks: configure trusted revocation and timestamp services before treating verification as production evidence.

## Test coverage and blockers

Added `tests/test_platform_pdf_seal.py` for invalid inputs and private-key file policy. THESE TESTS HAVE NOT BEEN EXECUTED. The execution environment in this conversation could not resolve github.com from its container, and pyHanko is not installed there. GitHub commits confirm source publication only.

Production readiness still requires:

- Complete application dependency and reproducible, hash-locked environment; ensure pyHanko version and its certvalidator API match the deployed dependencies.
- Migration replay (including trigger order) on a clean PostgreSQL installation and an upgraded restored staging copy.
- Real signing tests with an approved test CA, PKCS#12 test signer and known-good PDF inputs; verify CMS ByteRange, field, digest, certificate usage and chain.
- Negative tests for modified signed PDF, tampered manifest, broken chain, revoked/expired certificate, unsupported algorithms, missing permissions, wrong PKCS#12 password, missing ClamAV, disk-full and crash before DB commit.
- Tests of concurrent finalization requests, duplicate artifacts, aborted transactions, orphan reconciliation, append-only DB guards and illegal cancellation.
- Revocation checking (OCSP/CRL) with controlled URL/network policy and trusted timestamping (RFC 3161), with explicit PAdES profile validation and long-term preservation requirements.
- A sandboxed, memory/CPU/time-limited untrusted PDF parsing worker and secure operational key management.
- Application-level PDF signing by each individual participant using an authorized, participant-held key/certificate if personal signatures are required; such a feature is **not implemented by the platform-seal module**.
- Independent validation against original PDF bytes, retained evidence, trust policies, key status, and legal requirements for the jurisdiction.

## Suggested staging commands — not executed here

```bash
python -m pytest -q tests/test_platform_pdf_seal.py
flask db upgrade
flask pdf-seal finalize 123
flask pdf-seal verify 123
```

Do not run the example finalization against a real record until certificate, trust, malware scanning, migrations and test configuration have passed staging gates.

## Remaining development modules

The next major dependency for a complete TrustSeal signing feature is **individual signer authorization and certificate-backed signing** (where applicable), followed by signed-document evidence packaging, independent public verification, trusted timestamping, key custody, revocation policy, and comprehensive operational/contract tests.

No production signing occurred during this checkpoint. No claim of 100% backend completion or production readiness is made.


## Follow-up: signed review-evidence binding and separation of duties

The final manifest now also records `evidence_sha256`, the SHA-256 of a deterministic JSON bundle of the **ordered, independently verified Ed25519 review receipts**. The bundle is assembled using `app/services/platform_review_evidence.py`. The signing service embeds the digest as the PDF signature's `/Reason` field prior to CMS signing. This PDF metadata is included in the cryptographically signed PDF revision; verification checks that it matches the immutable finalization manifest. Independently proving the historical completeness of all reviewer records still requires external audit anchoring.

- `GET /api/platform-sealed-pdfs/envelopes/<id>/evidence` exports the ordered receipt bundle only to an authorized envelope author or assigned participant after re-verifying all receipts and comparing the canonical digest to the sealed artifact manifest.
- `tests/test_platform_review_evidence.py` covers canonical hashing, tampering and duplicate or nonsequential participant positions.
- `tests/integration/test_platform_pdf_roundtrip.py` uses a disposable test CA and PKCS#12 bundle to exercise actual PDF sealing, CMS validation, digest binding, tampering and re-sign rejection. It additionally needs `reportlab` from `requirements-signing-test.txt`. This test has **not been executed** in this environment.

Finalization now also requires `PDF_SEAL_OPERATOR_ID` in deployment configuration. The configured identity must be an active administrator in the envelope's organization, distinct from the document creator and **not** one of the reviewers. The user ID is stored in the immutable PDF manifest as `issued_by_id` and in the transactional security-event actor field. This is a staging-level controlled operator identity, NOT an HSM attestation, interactive MFA, OS identity verification or dual-control cryptographic key authorization. A production custody service must verify authorized operators through an independent security boundary.

The `h2b640a1d8f3` migration was updated to include the nonnullable `evidence_sha256` and `issued_by_id` columns. Since these migrations have never been run in a target environment here, replay must occur from the full original revision history. If this initial migration has already been applied anywhere else, create a separate forward-only migration instead of editing an applied revision.
