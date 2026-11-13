# TrustSeal — Governed Graphical Stamp Designs

Date: 2026-11-13 | Repository: socaya/trustseal | Branch: main

## Purpose and assurance

This module introduces a controlled graphical design registry for already-governed organizational stamps. It supports compact approved PNG logos, two standard layout sizes, flat black or blue ink, optional simple rectangle border, immutable versioned layout records, specimen PDF previews and independent approval. It is **not** a general-purpose SVG/HTML editor, remote image fetcher, digital identity verification service or regulated e-seal authority. The logo and stamp appearance are controlled representations of an already registered organization, not independently established legal authorization.

The existing workflow is preserved: a stamp custodian requests use of a specific finalized PDF, an independent administrator approves use, and a separate cryptographic stamp receipt must be issued. Visual issuance then starts with the **frozen unsigned source**, renders a new derivative and applies a fresh platform CMS signature. It never changes the original signed document.

## Data model and approved version lifecycle

`StampDesignVersion` in `app/models/stamp_design.py` stores immutable `(stamp_id, version)`, tenant, controlled layout, normalized embedded PNG, logo SHA-256, canonical design SHA-256, creator and independent approval/rejection evidence. Alembic revision `n8c206a1d9f7` creates that registry with a database trigger that rejects deletion or arbitrary content changes, and adds optional approved design ID and immutable design digest columns to `stamped_pdfs`.

A design remains immutable once submitted. New artwork or a different approved size, ink or border creates the **next sequential version**, not an update to an existing approved design. Each decision can occur once. Rejected design versions remain retained in the audit history. A revoked stamp cannot be used to approve or issue newly designed artwork.

### Design API

JWT-authenticated, tenant-scoped:

| Method | Endpoint | Role |
| --- | --- | --- |
| POST | `/api/stamp-designs/stamps/{stamp_id}` | Active stamp custodian proposes a new version |
| GET | `/api/stamp-designs/stamps/{stamp_id}` | Authorized stamp users list version history |
| POST | `/api/stamp-designs/{design_id}/decision` | Independent tenant administrator approves or rejects |
| GET | `/api/stamp-designs/{design_id}/preview` | Authorized users download a PDF specimen of one immutable design |

Submission accepts exactly:

```json
{
  "layout": {
    "size": "standard",
    "ink": "blue",
    "border": "rectangle"
  },
  "logo_png_b64": null
}
```

`logo_png_b64` may instead contain the Base64 bytes of a PNG. The server decodes it, verifies PNG structure and limits, strips metadata by normalizing to RGBA PNG, stores the normalized bytes and retains SHA-256. Reject SVG, HTML, remote URLs, arbitrary fonts and unsupported style controls. The service limits source size to 80 KiB, source dimensions to 512×512, pixel budget to 262,144 and normalized bitmap to 144×144. A maximum of 80 KiB applies after re-encoding as well.

Allowed design options are *only*:

- `size`: `standard` 204×78 PDF points, or `wide` 240×90 points
- `ink`: `black` or `blue`, using constant flat ink values, no gradients
- `border`: `rectangle` or `none`

Preview output explicitly displays `PREVIEW - NOT ISSUED` and a version reference. It cannot be mistaken for a final signed stamp artifact based on the specimen reference. No remote asset URLs are embedded.

## Binding the graphical design into a finalized PDF

The operator can select one independently approved version at issuance time:

```bash
flask stamped-pdf issue 123 --page 1 --x 350 --y 60 --design-id 42
```

The designated stamp and version must belong to the same tenant, the design must already be approved, and its original normalized artwork, SHA-256 and canonical design hash are all rechecked. The renderer uses the previously approved fixed logo and layout, placing it on the unsigned frozen PDF. It refuses pages or labels that cannot fit without clipping. The *exact design version ID and SHA-256* are included in the signed provenance digest, and stored with the immutable output manifest. This digest is bound inside the new PDF's CMS signature, so substitution of a different layout, logo or version is detectable by the authenticated verification/download API.

For older pre-design stamped artifacts, these design fields remain null and existing legacy evidence verification remains supported. A design is optional for compatibility; when provided, it must be approved and intact. The legacy standardized text-only rendering path remains available while migration is planned.

## Audit and testing

The transactional outbox now allowlists `stamp.design.proposed`, `stamp.design.approved`, `stamp.design.rejected`, together with existing `stamp.pdf.issued`. Tests include PNG normalization, malformed input rejection, SHA-256 tamper detection, rendered preview, and an actual PostgreSQL/JWT/CMS-signed PDF integration that submits a PNG through the API, independently approves the version, previews it and issues a sealed PDF using that approved design. Consult current GitHub Actions checks before claiming passing results.

## Remaining production gates

1. Harden graphic/PDF decoding in an isolated worker with CPU/memory/time limits; the synchronous Pillow/PDF parser is not a security sandbox.
2. Perform legal organizational identity and stamp authorization verification, protected HSM/KMS signing, MFA and independent key revocation policy.
3. Add scalable user-facing graphical design preview/placement selection and accessible asset-management UI.
4. Add application-level operational rate limiting, persistent incident/security monitoring, concurrent stamp-version tests, and disaster recovery/WORM retention.
5. Audit signed PDF compatibility on different viewers, page rotations, document layers and variable page geometry. The current renderer deliberately rejects complex inputs rather than silently flattening them.
6. Repair the historical 2025 migration bootstrap/upgrade rehearsal using representative restored data; CI's disposable model baseline is not a substitute.

These modules must not be advertised as a certified qualified electronic signature or seal service based solely on passing application tests.
