# TrustSeal — Historical TSA Chain Revocation Inventory

**Date:** 13 November 2026  
**Branch:** `main`  
**Scope:** issuer-signed CRL verification for non-root certificates of an explicitly configured TSA path, with preserved evidence in immutable validation dossiers.

## What is implemented

The existing `explicit_certificate_chain.py` authenticates a bounded leaf-to-root certificate path at the retained RFC 3161 timestamp's generation time. The new `chain_crl_inventory.py` extends this with independently signed CRL evidence for **each non-root certificate**, including the TSA leaf and every intermediate CA. Each supplied CRL is matched to the **immediate issuer in that approved path**, rather than assuming all CRLs are issued by the root.

For every provided non-root position, TrustSeal checks the CRL's DER structure, issuer distinguished name, issuer CA and CRL-signing Key Usage, cryptographic signature, Authority Key Identifier when available, and `thisUpdate <= timestamp generation time < nextUpdate`. A revoked serial number causes verification failure. An absent CRL is reported as **missing evidence**; it is never silently interpreted as a successful status.

The verifier deliberately rejects delta CRLs without verified base CRLs, indirect CRLs, partial-reasons CRLs, and distribution-point certificate-type mismatches. It also rejects duplicate indices, mismatched certificate fingerprints, malformed DER/Base64, CRL files larger than 512 KiB, and unapproved relative file paths or symbolic links.

### Operator configuration

The operator supplies exactly one position per non-root certificate, in leaf-to-root order. Use `null` where no CRL is available. This configuration is **optional** and does not change older dossier formats.

```dotenv
RFC3161_TSA_CERT_PEM=/etc/trustseal/trust/tsa-leaf.pem
RFC3161_TRUST_ROOT_PEM=/etc/trustseal/trust/root.pem
VALIDATION_TSA_INTERMEDIATES_JSON=["/etc/trustseal/trust/tsa-issuer.pem"]

# Position 0: CRL from TSA leaf's issuer
# Position 1: CRL from intermediate's issuer (trusted root)
VALIDATION_CHAIN_CRL_PATHS_JSON=["/etc/trustseal/revocation/tsa-issuer.crl","/etc/trustseal/revocation/root.crl"]

VALIDATION_DOSSIER_ENABLED=false
```

The configuration is supplied by a separately authorized operator. No HTTP client can submit a CRL path, arbitrary trusted CA or revocation endpoint. The application **does not fetch CRLs from external URLs**. CRL acquisition and authenticity verification must be handled through an approved external process and controlled filesystem permissions.

### Dossier lifecycle

```bash
flask validation-dossier issue <timestamp_id>
flask validation-dossier verify <dossier_id>
```

On issuance, TrustSeal validates the previously signed PDF and the retained timestamp, performs the explicit path checks and checks all configured CRLs. If a CRL reports revocation or fails verification, no new dossier is issued. If a CRL is missing, a **partial** inventory is saved.

New dossiers may now include `chain_revocation`, with:

- `schema`, `validation_time`, and `status` (`partial` or `non_root_crls_checked`)
- `non_root_certificates`, `covered_positions` and `missing_positions`
- One observation per supplied position, with subject and issuer certificate SHA-256, exact Base64-encoded DER CRL bytes, CRL SHA-256, `this_update`, `next_update` and an explicit non-revocation-on-CRL status
- `full_historical_pkix_assurance: false`

The inventory is part of the existing canonical SHA-256 dossier manifest stored in the database's append-only table. Reverification reconstructs every issuer-signed CRL observation from the **retained CRL bytes**, not the current CRL-file contents. This permits a historical dossier to remain independently checkable after CRLs are refreshed, while the separate path verification still requires the approved trust configuration.

Dossiers issued before this capability retain their original manifest structure; historical evidence is not overwritten or silently reclassified. The top-level dossier continues to report `complete: false` and unresolved comprehensive trust requirements. Even a `non_root_crls_checked` result cannot establish full RFC 5280 trust validation.

### Tests

`tests/test_explicit_certificate_chain.py` generates an actual TSA leaf, intermediate CA, root CA, and signed CRLs for both the leaf and intermediate positions. It tests complete and incomplete coverage, missing positional configuration, revoked serials, expired CRLs, forged CRL signatures, duplicate observations, malformed configuration, and altered hashes.

`tests/test_validation_dossier.py` verifies immutable inventory inclusion, historical compatibility and tamper rejection. The established integration suite covers tenant-scoped authenticated dossier export and PostgreSQL append-only safeguards.

## What remains before production trust claims

The CRL inventory is **not** a complete certificate-validation service. Remaining requirements include full RFC 5280 path processing (certificate policies, name constraints and relevant critical extensions), OCSP/CRL evidence for every relevant delegated responder, independent historical trust lists, revocation reason and delta/indirect CRL processing where applicable, authenticated receipt dates and long-term archives, algorithm/clock policies, independent legal review and PAdES-LT/LTA DSS and archive timestamp embedding.

Original 2025 schema migrations also still require rehearsal against a restored, production-representative PostgreSQL database. Passing disposable CI migration replay does not prove upgrade safety.

Neither this module nor its passing tests establish qualified electronic signature, legal stamp or regulated long-term validation certification.
