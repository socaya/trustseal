# TrustSeal — Explicit Historical TSA Certificate Chain Validation

**Implementation:** 13 November 2026  
**Repository:** `socaya/trustseal` · `main`

## Purpose and assurance boundary

The certificate-validation dossier now supports a **bounded, operator-configured TSA signing certificate path** from the signer leaf through zero to four intermediate CAs to an explicitly pinned root. At the retained RFC 3161 token's generation time, the engine checks:

- Exact name linkage and cryptographic signature of each certificate, including the root self-signature.
- Approved SHA-256/384/512 signature hash algorithms and no duplicate/cyclic certificate identities.
- Root CA and intermediate CA `basicConstraints` and `keyCertSign` authorization, including `pathLenConstraint`.
- Key identity binding for any present X.509 Authority Key Identifier / Subject Key Identifier.
- Validity of every certificate at the timestamp's historical generation time.
- TSA leaf `id-kp-timeStamping` Extended Key Usage, digital-signature and content-commitment usage and prohibition on acting as a CA.
- SHA-256 fingerprint of the TSA leaf must match the signer certificate retained with the timestamp response.

The implementation is deliberately an **explicit pinned-path validator**, not a general-purpose RFC 5280 path builder. It does **not** validate all critical extension semantics, name constraints, policy mappings, every algorithm security policy, or independent historical trust-list status. It cannot establish the revocation status of each certificate in the path from the current TSA-focused observations. Consequently, **it never declares full-chain PKIX or PAdES-LT/LTA validation complete**.

## Trust configuration and issuer order

```dotenv
RFC3161_TSA_CERT_PEM=/etc/trustseal/trust/approved-tsa-leaf.pem
RFC3161_TRUST_ROOT_PEM=/etc/trustseal/trust/approved-root.pem
VALIDATION_TSA_INTERMEDIATES_JSON=["/etc/trustseal/trust/intermediate-nearest-tsa.pem","/etc/trustseal/trust/intermediate-nearest-root.pem"]

VALIDATION_DOSSIER_ENABLED=false
```

Intermediates must be listed **from the leaf's issuer toward the trusted root**. Paths must be operator-approved, absolute and non-symlink regular PEM files. The system rejects invalid JSON, more than four intermediate CAs, missing files, duplicate certificates, incorrect certificate purpose, invalid signatures, path-length violations, expired or premature certificates and a TSA certificate fingerprint mismatch.

In addition to the validated chain hashes, a new dossier retains the bounded DER bytes of each certificate in leaf-to-root order in its immutable SHA-256 manifest. This allows later inspection and identifies substitutions or modifications. On dossier verification, TrustSeal **revalidates the recorded chain against the currently configured approved certificate paths** and fails closed if the configured issuer, root or leaf changes without an approved historical trust-rotation policy.

The root and leaf paths are optional for standalone chain inventory; existing timestamp and dossier validation still uses the normal configured trust rules. If an explicit chain is not configured when issuing a new dossier, the manifest adds `bounded_explicit_tsa_certificate_path` to its missing-requirements list. An old dossier issued before this feature stays verifiable under its original manifest schema, without rewriting previous evidence or imposing new fields retrospectively.

## Dossier interface and output

Operator command and endpoints remain unchanged:

```bash
flask validation-dossier issue <timestamp_id>
flask validation-dossier verify <dossier_id>
```

`GET /api/evidence-preservation/dossiers/{id}/export` provides authenticated tenant-scoped export after verification.

A new dossier may contain a `certificate_chain` structure with the explicit path schema, leaf and root SHA-256, ordered certificate digests, bounded DER certificate bytes, historical validation time and the assertions `complete_pkix_validation: false`, `revocation_verified_for_entire_chain: false`. The parent manifest continues to state `complete: false` and identifies missing full certificate-path policy, chain-wide revocation, historical trust lists and PAdES-LT/LTA DSS/archive timestamp material.

## Regression and deployment tests

`tests/test_explicit_certificate_chain.py` generates actual RSA PKI hierarchies and tests correct historical time, intermediate path length, expired intermediate certificates, a TSA signer without required EKU, forged signer signatures, unexpected root/order and missing configuration. `tests/test_validation_dossier.py` additionally verifies exact leaf fingerprint binding, immutable report replay and compatibility with older pre-chain dossier manifests. CI replays new migrations and runs the complete backend test suite.

**Production release blockers:** real full-policy PKIX path validation including all relevant extensions and trust lists, independent revocation evidence for every non-root CA and OCSP responder, historical validation policy at signing time, secure automatic renewal and independent archive timestamps, HSM/KMS custody, reliable historical database restore-and-upgrade rehearsal, and PAdES-LT/LTA embedded PDF DSS/VRI evidence.

These are required before TrustSeal may represent a document as having qualified or comprehensive long-term cryptographic validation.
