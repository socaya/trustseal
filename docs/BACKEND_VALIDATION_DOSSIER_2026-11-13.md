# TrustSeal Backend — Immutable Certificate Validation Dossiers

**Date:** 13 November 2026  
**Branch:** `main`  
**Assurance:** deliberately **partial**, not a completed PKIX or PAdES-LT/LTA validation determination.

## Purpose

A validation dossier is a reproducible, immutable evidence manifest linking the exact finalized PDF SHA-256, its retained RFC 3161 timestamp, and selected signed OCSP or CRL observations pertaining to the TSA signer. TrustSeal verifies the underlying private PDF bytes, its platform CMS certificate signature, timestamp token, configured TSA signer and trust root, and the cryptographic status evidence before recording the dossier.

**The dossier NEVER reports `complete: true`.** The implemented OCSP/CRL observations cover a bounded subset of the TSA signer chain and cannot substantiate full historical certificate-chain validation, regulated trust status or PAdES-LT/LTA archival assurances. No raw certificate or status evidence is invented to fill missing requirements.

## Operational workflow

An independently authorized tenant administrator operates the command after retention, timestamp and any approved OCSP/CRL observations exist:

```bash
flask validation-dossier issue <timestamp_id>
flask validation-dossier verify <dossier_id>
```

Feature gate:

```dotenv
VALIDATION_DOSSIER_ENABLED=false
EVIDENCE_CHECKPOINT_OPERATOR_ID=<independent tenant administrator>
```

No new private keys are introduced. The existing TSA and PDF trust configuration must be present and verifiable. Only retained, immutable status observations with positive cryptographic verification may enter a new dossier. A revoked, unknown, stale-at-observation or mismatched status cannot be represented as a positive observation.

Every manifest includes a version, tenant and retention identity, artifact type/ID/SHA-256, timestamp ID/token SHA-256/TSA signer certificate SHA-256 and generation time, referenced OCSP and CRL evidence IDs/hashes/observation times, and a machine-readable list of **missing requirements**. Its SHA-256 is retained alongside the canonical JSON and the issuing operator ID. The manifest is expressly described as `partial_tsa_status_evidence_not_full_chain_or_pades_lt`.

The dossier captures an evidentiary **snapshot**, not an automatically evolving or overwritten report. Adding additional OCSP/CRL observations requires issuance of a new dossier if those observations should be included. Previous records remain immutable and referenced historical evidence can be independently revalidated.

## HTTP interfaces

JWT-authenticated tenant administrators:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/evidence-preservation/retentions/{id}/dossiers` | List immutable dossier IDs, digests and incomplete assurance |
| GET | `/api/evidence-preservation/dossiers/{id}/export` | Revalidate the original PDF, timestamp and exact referenced status evidence before returning the manifest |

Cross-tenant IDs are not disclosed. Export does not merely trust the stored JSON: it reconstructs the manifest from the signed source evidence and checks its canonical SHA-256, source/tenant references and status. It returns a **manifest inventory**, not a bundle of raw OCSP/CRL bytes or an external certified validation report. Raw cryptographic objects remain available through the previously authorized timestamp, OCSP and CRL evidence export endpoints.

## Persistence and audit

Alembic revision `u5d973b8e6a4` follows `t4c862a7d5f3` and creates `validation_dossiers` with unique retention/timestamp/digest, FK constraints, metadata, operator identity and PostgreSQL append-only mutation guard. The transactional outbox event `evidence.dossier.issued` is explicitly allowlisted, and its handler rechecks original certificate and retained evidence integrity.

## Tests and limitations

- `tests/test_validation_dossier.py` verifies reproducible canonical hashing, tamper rejection, tenant mismatch, repeated observations, revoked evidence and explicit incomplete assurance.
- `tests/integration/test_validation_dossier_api.py` exercises PostgreSQL persistence and immutability, independent operator issuance, JWT tenant isolation, verified export and refusal to claim full-chain assurance.
- Previous TSA, CRL, OCSP and delegated-responder tests still verify actual cryptographic responses and issuer constraints.

**Not implemented:** full certificate path building and revocation verification for every intermediate and trusted root, responder revocation/no-check policies, historical trusted list and time-specific policy, evidence capture for every signer certificate, independently authenticated archival anchoring, PAdES-LT DSS/VRI embedding or PAdES-LTA document archive timestamps, HSM/KMS custody, and genuine restored legacy-database migration rehearsal.

The validation dossier is a **truthful evidence inventory**, not a production certification that an electronic signature remains legally qualified.
