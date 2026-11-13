# TrustSeal — Signer-Controlled Cryptographic Endorsement Module

**Date:** 2026-11-13  
**Repository:** socaya/trustseal  
**Branch:** main  
**Implementation:** Source committed. Database and end-to-end execution NOT verified.

## 1. Objective and assurance boundary

TrustSeal's earlier `review_receipts` are **platform-signed** attestations of review decisions. This module adds **signer-origin** cryptographic proof: each participant registers an Ed25519 public key by proving control of its private half and signs an authenticated, fresh challenge bound to one prepared PDF revision and previously recorded review-consent digest.

A signer-held detached cryptographic endorsement **is a real digital signature over a canonical evidence message**, but **it is not a CMS/PAdES signature embedded into a PDF**. It is not automatically a government-certified signature, verified identity credential, qualified electronic signature, trusted timestamp, or evidence that the registered key belongs to an identity independently vetted by TrustSeal. Never label such a document as personally PAdES-signed.

**No private keys are accepted by these APIs, transmitted to TrustSeal, or stored in its database.** A signer should control keys through a device keystore/HSM or other protected signing client.

## 2. Data model and migrations

`app/models/signer_cryptographic.py` introduces:

- `SignerPublicKey` — same-tenant owner, normalized Ed25519 public key, SHA-256 fingerprint, issuance/revocation timestamps.
- `SignerKeyChallenge` — nonce hash, key binding, ten-minute expiry, single-use consumption, and account/tenant binding.
- `SignerEndorsementChallenge` — frozen canonical PDF/consent signing message, signer key, participant, expiry and single-use nonce.
- `SignerEndorsement` — append-only evidence consisting of the exact signed canonical payload, signature, signer key, challenge, participant and recorded timestamp.

Migrations `i3c751b6e4a2` (after `h2b640a1d8f3`) and `j4e862c7f5b3` create the schema, uniqueness constraints, revocation and one-time challenge guards, append-only endorsement trigger, and a DB constraint trigger checking endorsement/participant/challenge/decision/envelope compatibility. The database does not itself perform Ed25519 verification; the service performs cryptographic verification before committing and on subsequent access.

## 3. API contract

The JWT-protected `/api/signer-crypto` blueprint is explicitly registered in the application factory.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/keys` | List only the active caller's owned public key fingerprints and revocation status |
| POST | `/keys/challenge` | Start proof-of-possession enrollment using `{"public_key_pem":"..."}` |
| POST | `/keys/confirm` | Complete enrollment using `{"challenge_id":123,"nonce":"...","signature_b64":"..."}` |
| POST | `/keys/<key_id>/revoke` | Permanently revoke caller's public key for new endorsements |
| POST | `/envelopes/<id>/challenge` | Issue a document/consent-bound challenge using `{"key_id":123}` |
| POST | `/envelopes/<id>/endorse` | Consume challenge using `{"challenge_id":123,"signature_b64":"..."}` |
| GET | `/envelopes/<id>/endorsement` | Authorized envelope author/recipient exports signature, public key, signed payload, validity and revocation indication |

The client signs the **`sign_this` JSON object** returned by the challenge endpoint using canonical UTF-8 JSON: sorted keys, compact separators, `ensure_ascii=False`, and no NaN. The signature is the raw 64-byte Ed25519 signature encoded in standard Base64. A local reference helper is included as `examples/signer_local_sign.py`.

### Enrollment sequence

1. A JWT-authenticated, active, tenant-associated user generates or obtains a protected Ed25519 signing key under their exclusive control.
2. They submit its **public** PEM to the enrollment challenge endpoint. TrustSeal normalizes it, derives its SHA-256 fingerprint and returns a fresh nonce plus canonical `sign_this` data.
3. The user signs the `sign_this` JSON with their private key on their device and returns the nonce, challenge ID and detached signature.
4. TrustSeal verifies the signature against the exact stored public key, checks nonce binding, expiry, same account and tenant, and persists an active public key record. An unverified or previously enrolled key is rejected.
5. A key can be revoked for future operations. Historical endorsements retain the prior key's public material and signature for retrospective verification, with revocation status displayed rather than silently erased.

### Document endorsement sequence

1. The envelope must be in `prepared` state, the authenticated user must be an assigned participant in the same organization, and that participant must have already recorded an `acknowledged` review with matching consent SHA-256.
2. Each earlier participant must have **already produced a cryptographically valid signer-held endorsement** for the same envelope. TrustSeal enforces sequential order.
3. The selected key must be active and belong to the authenticated participant. The source PDF is rehashed from private storage before issuing a challenge.
4. The challenge carries `envelope_id`, tenant ID, signer identity, participant, sequence, immutable document blob and SHA-256, review decision and consent digest, key fingerprint and a fresh random nonce.
5. The signer independently signs that canonical challenge JSON and submits its Base64 Ed25519 signature. The backend rechecks the exact document, review consent, active credential, single-use nonce and prior signing order before committing.
6. TrustSeal atomically inserts append-only endorsement evidence and a transactional security/outbox event. Replays and duplicate participant endorsements are rejected.

### Integration with platform PDF sealing

`flask pdf-seal finalize <envelope_id>` now requires, for **every** assigned reviewer:

- an acknowledged review decision bound to the immutable PDF;
- an independently verifiable TrustSeal Ed25519 review receipt; and
- a genuine signature from that participant's registered signer-held public key over the frozen document/consent context.

The canonical evidence package now contains both the platform receipt and the signer-origin public key and detached signature. Its SHA-256 digest is bound inside the platform-sealed PDF's signed `/Reason` string and immutable manifest. The authorized `/api/platform-sealed-pdfs/envelopes/<id>/evidence` endpoint rechecks and exports those records.

This remains an **individual detached endorsement + platform PDF certificate seal** combination, not individual signer PAdES PDF signatures.

## 4. Operational and security considerations

- Key ownership does not equal independently proofed identity. Real-world identity verification, trusted signer credential enrollment, formal PKI, lifecycle policy, and trusted timestamps remain separate.
- Enrollment and endorsement nonce lifetime is ten minutes; each participant has a bounded challenge issuance rate. More comprehensive account/IP rate limits, MFA and risk controls are still required.
- A revoked key cannot issue new endorsements. Signed historical evidence remains inspectable and must be evaluated against key status at signing time for formal trust decisions.
- Source PDFs can still contain unsafe features; do not enable rendering/signing without validated PDF parsing and isolated conversion.
- The local example signing client is a testing/integration helper, not an approved HSM or secure-element implementation.
- The append-only DB guards cannot prevent PostgreSQL superusers or filesystem administrators from altering evidence. Implement independent anchoring, trusted timestamping, WORM retention and secure backups.
- Private-key possession is verified at enrollment, but the database does not retain a separate signed enrollment proof for third-party export. Add signed enrollment provenance and independent identity binding for higher assurance.
- The platform-seal engine stays disabled by default (`PDF_FINALIZATION_ENABLED=false`) pending real end-to-end certificate, PDF, malware-scan, migration and operational tests.

## 5. Tests and release gates

New tests:

- `tests/test_signer_crypto.py` — real Ed25519 proof-of-possession, canonical signing, wrong key, wrong document/consent, nonce replay-context, malformed key and declined review.
- `tests/test_signer_crypto_routes.py` — required JWT API route surface, no private-key ingestion path.
- `tests/test_event_delivery.py` — explicit allowlist of signer/key event handlers.

The platform-seal integration code now checks all signer-held endorsements before sealing, and the evidence export reconstructs them after sealing.

**These tests have not executed against the connected GitHub repository.** The available container does not resolve `github.com` and lacks the Flask/pyHanko application runtime. No migrations were applied and no production keys or PDFs were issued.

Run in a fully provisioned, disposable staging environment:

```bash
python -m pip install -r requirements.txt -r requirements-signing.txt -r requirements-test.txt
python -m compileall -q app tests examples
python -m pytest -q tests/test_signer_crypto.py tests/test_signer_crypto_routes.py tests/test_event_delivery.py
flask db upgrade
python -m pytest -q
```

Additionally require actual PostgreSQL concurrency tests for two simultaneous endorsements, invalid nonce, revoked keys, tenant crossover, altered review digest, canceled envelope, multiple signing orders, duplicate public keys, deleted/changed PDF object, crash/rollback, migrations, and DB triggers.

## 6. Outstanding product features

Completing **personal CMS/PAdES signatures** requires a separate signing service that incrementally signs a PDF with each signer's protected certificate-backed key, validates every signed byte range and signer certificate chain, and preserves prior signatures. A signer-controlled cryptographic endorsement cannot simply be embedded as a signature appearance or falsely converted into a personal PDF signature.

Other outstanding TrustSeal backend modules include governed electronic-stamp custody, external recipient onboarding, tenant-scoped public verification, retention/legal hold, independent audit checkpoints, payment and notification integrations, complete authorization review, CI/reproducible lockfile, and all operational readiness gates.
