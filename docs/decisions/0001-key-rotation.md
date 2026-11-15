# ADR 0001 — Platform signing key custody and rotation

**Date:** 2026-11-14
**Status:** Accepted (interim), supersedes implicit PKCS#12 handling in `app/services/platform_pdf_seal.py`.

## Context

The platform seals PDFs with a private key currently loaded from a PKCS#12 bundle referenced by the `PDF_PLATFORM_PKCS12` environment variable. The private key is read into process memory on every signing operation. There is no rotation procedure, no audit trail for key material access, no separation between development and production keys, and no path to a hardware-backed signer.

Historical dossiers must remain verifiable after a rotation. Changing the active signing cert cannot invalidate previously issued seals.

## Decision

1. Signing is performed through a `Signer` interface (`app/services/integrations/kms/base.py`) that exposes `sign(data: bytes, digest_alg: str) -> bytes` and `public_certificate_chain() -> list[x509.Certificate]`. Implementations:
   - `LocalPkcs12Signer` — current PKCS#12 path, dev and CI only.
   - `AwsKmsSigner` — AWS KMS asymmetric sign (RSA_PSS_SHA_256 or ECDSA_P256), targeted for production.
   - `Pkcs11Signer` — HSM path, deferred.
2. Signer selection is config-driven (`PLATFORM_SIGNER_BACKEND={local_pkcs12,aws_kms}`). Production startup refuses `local_pkcs12`.
3. Each active signer certificate has an immutable `platform_signer_certificate` row (id, pem, not_before, not_after, kms_key_arn, retired_at, created_at). The `active` certificate is the one with `retired_at IS NULL` and the latest `not_before`.
4. Every sealed PDF records `platform_signer_certificate_id`. Verification loads the certificate by id, not by current active value, so historical dossiers stay valid after rotation.
5. Rotation runs through `flask keys rotate --new-cert <path>`:
   - Enrolls the new cert, verifies chain against the pinned trust root.
   - Marks previous cert `retired_at = now()` after a configurable overlap.
   - Publishes an event to the outbox so DSS material for existing dossiers is refreshed if the new intermediate CRL supersedes the old.
6. No signing key material is ever logged. `AwsKmsSigner` never sees the raw private key. `LocalPkcs12Signer` loads the key with `BestAvailableEncryption` and zeroes buffers on release.

## Consequences

- One new table and migration (`platform_signer_certificate`), one FK from `pdf_finalizations.platform_signer_certificate_id`.
- `app/services/platform_pdf_seal.py` must be refactored to call `Signer.sign()` instead of loading PKCS#12 inline.
- CI nightly job runs the full signing suite against localstack KMS to prove the interface parity.

## Alternatives rejected

- Keeping PKCS#12 only: no path to production assurance.
- HSM-first (`Pkcs11Signer`): operationally heavier than KMS, deferred until a tenant requires it.
