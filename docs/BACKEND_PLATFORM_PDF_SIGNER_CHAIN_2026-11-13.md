# TrustSeal — PDF Platform Signer Certificate-Chain Evidence

**Date:** 13 November 2026  
**Repository:** `socaya/trustseal` · branch `main`

## Purpose and assurance boundary

This phase extends the existing partial long-term validation dossier to examine the **PDF platform seal's actual signing certificate and its own certification authority hierarchy**, independently of the RFC 3161 TSA certificate path. Those paths may have different roots, intermediates, certificate policies and revocation sources; TrustSeal must never presume that validation evidence for the TSA also establishes status of the PDF signer.

TrustSeal already verifies the platform CMS signature, its certificate using a configured pinned root, and the exact document SHA-256. The new verifier adds a bounded, explicit PDF signer path at the retained RFC 3161 token's generation time and optional signed CRL evidence for the platform signer and each intermediate CA. This is an evidence inventory and **not complete historical PKIX or PAdES-LT certification**.

A timestamp over the finalized PDF provides proof that the bytes existed by the time stamped in the TSA token, subject to the TSA's trust and verification. It is **not** itself a PDF signature signing-time attestation and does not establish earlier signer key status. Historical trust-list and certificate-policy evaluations are still missing.

## Configuration

```dotenv
PDF_TRUST_ROOT_PEM=/etc/trustseal/pdf-ca/root.pem
VALIDATION_PDF_SEAL_CERT_PEM=/etc/trustseal/pdf-ca/platform-seal.pem
VALIDATION_PDF_INTERMEDIATES_JSON=["/etc/trustseal/pdf-ca/issuer-nearest-seal.pem"]

# Leaf first: CRL of the PDF platform signer's issuer, then of each
# intermediate's issuer. Null means no CRL available for that position.
VALIDATION_PDF_CHAIN_CRL_PATHS_JSON=["/etc/trustseal/pdf-ca/crl/issuer.crl","/etc/trustseal/pdf-ca/crl/root.crl"]
```

All referenced certificates and CRLs must be operator-approved local files, not URLs or untrusted user upload paths. Pinned paths are checked for absolute location and symbolic-link rejection. No automatic CRL network fetch is introduced. If `VALIDATION_PDF_SEAL_CERT_PEM` is not supplied, existing dossiers and DSS workflows remain unchanged.

## Validation requirements

1. Verify original PDF source integrity and platform CMS seal using the existing signed-PDF verifier.
2. Retrieve the **actual PDF signer certificate fingerprint from the immutable artifact record**, independently of TSA signer identification.
3. Check the explicitly configured platform certificate path at the TSA token's generation time. Support up to four intermediates; check certificate signatures, issuer names, common CA usage and path-length constraints, key identifiers and validity intervals.
4. Apply the PDF signing certificate purpose, rejecting an inappropriate TSA-only leaf. Unlike a TSA certificate, a platform PDF signing certificate does not require `id-kp-timeStamping`.
5. Compare the approved platform leaf's DER SHA-256 to the signed PDF artifact's retained signer certificate SHA-256. Reject substitution and expired or unauthorized chains.
6. Where configured, verify issuer-signed DER CRLs for every non-root platform certificate using the existing strict historical CRL inventory. Reject revoked serial numbers, incorrect CRL issuers, invalid signatures, expired windows, incompatible CRL scopes, delta and indirect CRLs that require additional processing.
7. Store the certificate-chain DER and hashes plus any verified signed CRLs within the immutable dossier manifest, which is SHA-256-bound and protected against database UPDATE/DELETE.
8. Reverify retained manifest bytes and certificate authorities for historical dossier verification. A changed current operator CRL file cannot silently rewrite the stored observation. Changing the approved certificate chain causes verification to fail until a separately governed trust-rotation policy is established.
9. When a verified dossier includes platform chain data, collect that material for the existing PDF DSS derivative. The derivative continues to be a separate PDF incrementally updated after the platform CMS signature, and must retain the unchanged original signature.

## Reporting and compatibility

The manifest's `platform_signer_chain` object contains `schema: trustseal.platform-pdf-chain-evidence.v1` and the bounded certificate-chain manifest, plus an optional `crl_inventory`. Missing platform CRLs are explicitly reported as `platform_signer_historical_revocation_evidence`; partial intermediate coverage is reported as `platform_signer_intermediate_revocation_coverage`. The top-level dossier **always remains `complete: false`**. Full certificate-policy checks, historical trust-list status, signer and delegated-responder revocation, and PAdES-LT compliance cannot be inferred from the absence of a serial number in a CRL.

Older dossier manifests without `platform_signer_chain` remain verifiable without rewriting or adding requirements retroactively.

## Tests and release gates

`tests/test_platform_signer_chain.py` generates an RSA platform signer, intermediate CA, root CA and signed CRLs. It checks correct signatures and identity, historical expiry, mismatched fingerprint, misuse of a TSA-only certificate, revoked signer and mutation of retained CRL evidence. `tests/test_validation_dossier.py` exercises immutable dossier binding and historical replay. The existing PDF DSS tests continue to verify PDF signature preservation after incremental updates.

**Still required for PAdES-LT/LTA:** full RFC 5280 path processing including certificate policies and critical extensions, historical trusted lists, complete OCSP/CRL and delegated responder-status coverage, independently reviewed certificate renewal and trust rotation, cross-validator PDF interoperability, proper document/archive timestamps, HSM/KMS custody, and a restored real-schema PostgreSQL migration rehearsal.

Do not label the output as a qualified signature or a standards-certified PAdES-LT/PAdES-LTA document.
