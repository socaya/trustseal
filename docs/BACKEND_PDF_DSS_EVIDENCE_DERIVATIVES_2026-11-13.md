# TrustSeal — Incremental PDF DSS Evidence Derivatives

**Implementation:** 13 November 2026  
**Repository:** `socaya/trustseal` · branch `main`  
**Profile:** `dss_evidence_only_not_pades_lt`

## Purpose and assurance

The new DSS derivative workflow constructs a **separate PDF copy** containing a Document Security Store (DSS) with a VRI entry linked to the platform's original PDF CMS signature. It embeds previously validated X.509 certificates, OCSP responses and CRLs from an immutable evidence dossier. pyHanko writes this as an **incremental PDF revision**, preserving the already signed source bytes as an exact prefix rather than modifying or replacing the original stored PDF.

This is **not a PAdES-LT or PAdES-LTA certification or claim**. The current validation dossier is explicitly partial and primarily evaluates the Time-Stamp Authority's certificate and evidence. The platform certificate hierarchy may differ from the TSA chain. The derivative includes the actual platform PDF signer certificate but **does not yet have comprehensive historical revocation evidence for that platform signing chain, complete PKIX trust policy or embedded document archive timestamp**.

No user-facing account may request an unchecked DSS update, untrusted URL fetch, private signing key or arbitrary PDF alteration.

## Creation and verification

Operator command:

```bash
flask pdf-dss issue <validation_dossier_id>
flask pdf-dss verify <derivative_id>
```

Enabled only with:

```dotenv
PDF_DSS_DERIVATIVE_ENABLED=false
EVIDENCE_CHECKPOINT_OPERATOR_ID=
PRIVATE_DOCUMENT_ROOT=/absolute/private/trustseal/storage
DOCUMENT_CLAMSCAN_BINARY=/usr/bin/clamscan
PDF_TRUST_ROOT_PEM=/absolute/approved/platform-root.pem
```

When explicitly enabled, a separate active administrator must operate the command. Issuance locks and revalidates the immutable dossier, the original retained PDF's SHA-256, the exact platform CMS signer certificate and signed evidence digest, the RFC 3161 timestamp and each referenced signed status observation. The dossier must contain a previously authenticated certificate path and at least one CRL or OCSP response. All material has byte-size limits and is checked against its recorded SHA-256 before use.

The engine embeds the exact platform signing certificate and the dossier's certificate and revocation material using pyHanko's `DocumentSecurityStore.add_dss`. It confirms the output is a bounded incremental revision containing the **unaltered source PDF prefix**, unchanged signature CMS bytes, a readable DSS and the expected certificates. The original signature must validate with the pinned trust root **after** DSS insertion. Failure aborts issuance.

The derivative is scanned and stored under a separate unpredictable key in private immutable PDF storage. An append-only SQL manifest retains its organization, original retention ID/SHA-256, dossier ID/SHA-256, output key/SHA-256/size, separate operator and explicit non-LT profile. Database mutation triggers reject ordinary UPDATE/DELETE. Retrying issuance with the same dossier returns the previous derivative rather than silently overwriting it. A transactional outbox event `evidence.dss.issued` verifies the completed derivative.

### API

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/api/evidence-preservation/retentions/{id}/dss` | Tenant-admin list of issued DSS derivative metadata, with `complete_pades_lt: false` |
| GET | `/api/evidence-preservation/dss/{id}/download` | Tenant-admin download after re-verifying the source, dossier and resulting PDF |

Neither endpoint allows cross-tenant enumeration. Responses are private and non-cacheable.

## Persistence and tests

Migration `v6e084c9f7b5` follows `u5d973b8e6a4`. It creates `pdf_dss_derivatives` with a unique dossier identifier, tenant/retention references, separate operator, original source and dossier fingerprints, immutable output identifier and digest, explicit profile and an append-only trigger. The CI-only historical baseline excludes this new table before migration replay.

The regression suite includes **real CMS-signed PDF tests** in `tests/integration/test_pdf_dss_derivative.py`: it creates a test platform certificate and a valid signed PDF, assembles synthetic ASN.1 CRL material for testing the DSS format only, appends a real DSS via pyHanko, verifies the untouched original and derivative CMS signatures, and detects changed derivative bytes or mismatched evidence references. The synthetic CRL in that specific test is **not trusted revocation evidence**; the controlled issuance workflow separately revalidates all dossier sources.

## Limitations and production gates

1. Obtain complete historical issuer-chain and OCSP/CRL status for the **PDF platform signer**, not just the separate TSA certificate, and validate full-chain status at the relevant signing time.
2. Support complete RFC 5280 certificate-policy processing, historical trust lists, responder revocation and trusted time evidence.
3. Validate DSS/VRI interpretation with multiple independent PAdES implementations and document readers.
4. Add an independently timestamped PDF archive signature after the DSS with an approved TSA, protected key custody, renewal and a robust PAdES-LTA policy. Detached RFC 3161 tokens are **not** PDF archive timestamps.
5. Run untrusted PDF/ASN.1 parsers in a resource-limited isolated worker with malware scanning, monitoring and incident response.
6. Verify historical database upgrades using a genuine restored dataset; the existing CI disposable baseline only covers new migrations.

Do not advertise this output as a qualified electronic signature, a personal signer's PDF signature or standards-certified PAdES-LT/LTA.
