# TrustSeal Backend — Visible Stamp Impression and CMS-Sealed PDF Derivatives

**Date:** 2026-11-13
**Branch:** `main`
**Scope:** controlled text-based visible organizational stamp on a new PDF derivative.

## 1. Security model and why a derivative is necessary

TrustSeal previously completed a governed stamp registration/use approval and an independently signed Ed25519 stamp attestation. That evidence does not automatically place a visual stamp on the PDF.

Editing an existing CMS-signed PDF to insert an image or stamp would change its signed byte ranges and risk invalidating the existing signature. This implementation therefore **never alters the original platform-sealed PDF**. It reopens the **same frozen unsigned source revision** named in the original finalization manifest, renders a tightly bounded approved stamp plate, and applies a **fresh platform certificate-backed CMS signature to the new derivative**. The original signed PDF is retained intact. The new PDF carries an explicit hash-based provenance reference back to the original signed artifact, unsigned source, reviewed evidence and stamped application approval.

The new derivative is a **platform-sealed, visually stamped PDF**. Its embedded certificate signature belongs to the TrustSeal platform seal authority, not an individually issued qualified organization seal. It is not automatically evidence of public authority or statutory stamp eligibility.

## 2. Enabled workflow

1. Obtain an approved, active `ManagedStamp` and `StampApplication` against a previously finalized PDF.
2. Issue its independent Ed25519 `StampAttestation`, after validating the original platform certificate and review evidence. The issuer operator must be independent of the requester, approvers and custodian.
3. Configure a protected certificate-backed platform PDF signing service and scanned private storage, and explicitly enable **both** `PDF_FINALIZATION_ENABLED` and `STAMP_PDF_RENDER_ENABLED`.
4. An authorized operator calls:

   ```bash
   flask stamped-pdf issue 123 --page 1 --x 350 --y 60
   ```

   `123` is the **stamp attestation ID**, not an arbitrary document ID. Coordinates are PDF points from the bottom-left of a conventional unrotated page. Both the original source and stamp approval must be intact. Only one derivative can be issued per attestation. Repeating the command returns the existing artifact instead of issuing a different version.

5. The renderer `app/services/stamp_pdf_impression.py` creates a flat rectangular black-on-white impression with the approved stamp name, code and immutable attestation ID. The design has fixed dimensions (204 × 78 pt), 18 pt minimum margins, controlled fonts and strict page positioning. It rejects encrypted files, rotated pages, interactive forms, annotations, invalid PDF structure and unrenderable or truncated names. All source bytes are obtained from scanned private storage.
6. A canonical provenance payload is constructed with the original signed PDF SHA-256, unsigned source SHA-256, review-evidence SHA-256, signed stamp attestation SHA-256, exact stamp code, attestation ID and page/x/y placement. This canonical JSON is hashed with SHA-256.
7. The platform PDF signer applies CMS/PAdES-compatible signing **after** rendering, embedding the provenance digest in the signed `/Reason` value prefixed with `TrustSeal stamp evidence sha256:`. The resulting PDF is independently revalidated against a configured trust root and exact platform certificate fingerprint.
8. The finished PDF is scanned again, stored under a new opaque private key, and the immutable `StampedPdf` manifest and `stamp.pdf.issued` security/outbox event are committed together. The original signed PDF and original unsigned source remain unchanged.
9. Authorized tenant users may independently verify and download the resulting artifact. Verification rechecks the **original** CMS signature, original private-object digest, immutable approved stamp attestation signature, canonical provenance, rendered output digest and its new CMS signature.

## 3. APIs and commands

| Method | Endpoint | Meaning |
| --- | --- | --- |
| GET | `/api/stamped-pdfs/{id}/verify` | Verify full source, stamp authority and signed derivative lineage |
| GET | `/api/stamped-pdfs/{id}/download` | Deliver the authorized PDF only after full lineage and CMS verification |

These endpoints require an active JWT-authenticated user from the same organization, with access limited to the stamp custodian, application requester or an authorized administrator. Neither public access nor generic PDF editing/upload endpoints are introduced.

Operator commands:

```bash
flask stamped-pdf issue 123 --page 1 --x 350 --y 60
flask stamped-pdf verify 456
```

Issuance and verification commands are not public HTTP mutations. The CLI uses the previously configured independent stamp operator's identity, private certificate signer and trust root.

## 4. Persistence and dependencies

Migration `m7b195f0c8e6`, following `l6a084e9b7d5`, adds `stamped_pdfs`. It records tenant, unique stamp attestation, original signed PDF reference/hash, unsigned source hash, stamp attestation hash, canonical provenance digest, private output key/hash/size, certificate fingerprint, placement coordinates, issuing operator and timestamp. A PostgreSQL trigger blocks ordinary edits/deletion.

`requirements-signing.txt` now explicitly includes `pypdf` for controlled page merging and `reportlab` for vector stamp impression drawing. `scripts/ci_legacy_schema_baseline.py` excludes this new table for isolated Alembic migration validation.

Configuration:

```dotenv
STAMP_PDF_RENDER_ENABLED=false
PDF_FINALIZATION_ENABLED=false
PRIVATE_DOCUMENT_ROOT=/var/lib/trustseal/private-objects
DOCUMENT_CLAMSCAN_BINARY=/usr/bin/clamscan
PDF_PLATFORM_PKCS12=/etc/trustseal/keys/platform-seal.p12
PDF_PLATFORM_PKCS12_PASSWORD=<supplied only by secret manager>
PDF_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-root-ca.pem
STAMP_ATTESTATION_OPERATOR_ID=<independently authorized administrator>
STAMP_ATTESTATION_PUBLIC_KEY=/etc/trustseal/keys/stamp-public.pem
```

The feature defaults to disabled. The current key adapter is an operator-only controlled-file integration, not production HSM custody.

## 5. Verification and test expectations

- `tests/test_stamp_pdf_impression.py`: actual source PDF rendering, complete visible stamp identity, invalid placement/oversized labels, non-PDF rejection, and original byte immutability.
- `tests/test_stamped_pdf_provenance.py`: deterministic evidence hashing and changes caused by placement, document or approval tampering.
- `tests/integration/test_platform_pdf_roundtrip.py`: real test CA, new signed derivative, original CMS signature preserved, expected stamp evidence reason, and refusal to modify/re-sign the already-signed original.
- `tests/integration/test_stamped_pdf_workflow.py`: PostgreSQL-backed end-to-end issuance using disposable keys, private object storage, a test-only scanner, authorized download, cross-tenant denial and duplicate issuance rejection.
- `tests/test_event_delivery.py`: explicit `stamp.pdf.issued` outbox allowlist.

No production key, stamp or signed PDF is issued by CI. Check the latest GitHub Actions run before claiming the tests are green.

## 6. Remaining production requirements

1. Branded stamp artwork support (approved vector/logo assets, sizes, organization identity, regulatory formats), preview, template versioning and asset custody. The current renderer is a **controlled text-based standard plate**, not a full arbitrary image/logo stamp designer.
2. Consent and signature flows for personal signer certificates remain separate. The new platform seal must not be marketed as a qualified organizational electronic seal without independently verified certification and policy.
3. Independent PDF and stamp evidence public verification (without relying on tenant database access), trusted timestamping (RFC 3161), revocation checking, certificate rotation and retention/legal-hold policy.
4. Sandboxed PDF parsing/flattening, resource budgets, hostile PDF testing, ingress abuse prevention, real antivirus scanning and HSM/KMS-backed key custody.
5. A real upgrade rehearsal from historical production-like PostgreSQL schema and backups, since the older 2025 migration chain cannot bootstrap an empty database directly.
6. Concurrent transaction tests, disk-full recovery, orphan reconciliation and immutable storage/WORM evidence anchoring.

**Do not claim 100% system completion or legal trust-service certification from this module.**
