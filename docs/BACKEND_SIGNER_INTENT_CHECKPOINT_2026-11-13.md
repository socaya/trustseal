# TrustSeal backend checkpoint — Authenticated signer review intent

Date: 2026-11-13  
Branch: `main`  
Status: **Committed to GitHub, not executed or production validated**

## Scope and assurance boundary

This tranche adds a carefully scoped participant review-decision workflow to the prepared-envelope backend. The available decisions are **acknowledged** and **declined**. They are deliberately NOT electronic signatures and do not produce a signed PDF, PKI signature, witness attestation, qualified timestamp or signature certificate. In particular, do not display a review acknowledgement as "signed" or "completed" in any client.

The earlier unsafe legacy generic signing CRUD endpoints remain blocked.

## Data model and migrations

`SignerChallenge` stores the envelope, assigned participant and authenticated internal user, SHA-256 of a cryptographically random one-time secret, PDF digest, issue and expiry timestamps and one-time consumption timestamp. The plaintext nonce is returned once to the authenticated client and is not persisted.

`SignerDecision` stores the bound participant, consumed challenge, review action, PDF SHA-256, immutable consent statement version, canonical consent digest, and recorded timestamp. A unique participant constraint prevents multiple decisions for the same envelope assignment. The decision row is append-only in PostgreSQL.

New Alembic revisions, in order:

- `d8e520c743ab` after `c8d192f4a610`: challenge and decision tables, constraints and append-only decision trigger.
- `e1a904f7b2c6`: challenge rows may only transition once from unconsumed to consumed; immutable identity and expiry fields cannot be rewritten.
- `f2a91d6e4b80`: check a decision is supported by a consumed challenge for that exact assigned participant, authenticated user, prepared envelope and PDF digest.

All these revisions require staging migration replay and real PostgreSQL integration testing before deployment.

## API surface

These are registered under the JWT-secured `/api/signer-intent` prefix:

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/envelopes/<id>` | Display assigned recipient's envelope, digest, consent text and own recorded decision |
| GET | `/envelopes/<id>/document` | Stream authorized scanned PDF after digest verification |
| POST | `/envelopes/<id>/challenge` | Reauthenticate participant with password, rate-limit attempts and issue 10-minute challenge |
| POST | `/envelopes/<id>/decision` | Explicitly acknowledge or decline the identified document, consuming one challenge |

Challenge requests accept `{"password":"<current account password>"}`. They are limited to three attempts per assigned participant in a rolling ten-minute window, counting failed password attempts as spent/consumed challenge records. This guards the narrow route only; system-wide account lockout, IP throttling, MFA, and distributed abuse protection are still missing.

Decision requests accept `challenge_id`, `challenge` (plaintext nonce received once), `decision` (`acknowledged` or `declined`), `document_sha256`, `consent_version` (`review-intent-v1`) and explicit `affirmed: true` confirming the displayed review statement. No client-provided actor ID, participant ID, source document ID or database revision is accepted for these operations.

All actions check the active JWT principal, active account, current organization, assigned recipient, prepared envelope state, and exact PDF digest. Decisions also enforce sequential signing-order acknowledgements: previous recipients must have acknowledged, and a decline blocks later review decisions. Enrollment creation/preparation and review decisions are serialized under envelope row locks.

The consent statement and its version are maintained in a versioned registry so historical review digests remain verifiable when future wording changes. New consent versions must be added to the registry, never retroactively replace old text.

## Transactional records

The decision and consumption timestamp are persisted in the same SQL transaction, together with the `SecurityEvent` and `OutboxEvent` records. The outbox now allowlists `envelope.review.acknowledged` and `envelope.review.declined` for internal consistency verification. There is **no external webhook, document issuance or delivery** from these handlers.

## Known limitations and release gates

1. No actual signing method (certificate-backed, digital pen, biometric, electronic signature placement, PDF PAdES, or PDF finalization) is enabled.
2. Password reauthentication is not MFA or identity proofing. More robust recipient authentication and account-abuse defenses are needed.
3. The stored PostgreSQL timestamp is not a certified trusted timestamp. The consent digest is not independently signed or externally anchored, so privileged database operators could still alter related data.
4. Independent append-only evidence export, audit hash chaining, key management, anti-replay integration, backups and retention remain outstanding.
5. External email recipient invitations, legal representatives, delegated signatures, signature consent templates by jurisdiction, and eID are not yet supported.
6. All tests are authored but not executed here. The code environment lacks Flask and the repository's runtime dependencies; there is no demonstrated successful integration or DB migration.
7. Test with PostgreSQL: concurrent decisions, duplicate nonce, expiry, cross-user/tenant access, disabled account, wrong password/429, invalid digest, cancellation races, stale PDFs, prior participant decline, rollback and database append-only triggers.
8. Existing private storage still requires true ClamAV, structural PDF validation, protected filesystem/backup configuration and reverse-proxy tests.
9. Review authorization is intentionally limited to **registered internal recipients in the same organization**. A prepared document can be downloaded by assigned recipients; do not expose these endpoints via a shared public URL.
10. Passwords must be handled through TLS and never logged. Review challenges and tokens must not be stored in browser history or analytics.

## Next engineering stage

Add a dedicated signing-authorization layer and signature execution state machine, integrate explicit signer identity proof/evidence retention and atomic signed-PDF finalization, and implement independent verification. Before enabling true signing, resolve migration and integration test gates.

**No production service was migrated and no claim of 100% backend completion is made.**
