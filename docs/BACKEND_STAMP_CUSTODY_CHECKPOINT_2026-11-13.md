# TrustSeal — Governed Organizational Stamp Custody

Date: 2026-11-13  
Repository: `socaya/trustseal`  
Branch: `main`  
Status: code committed; consult GitHub Actions for current validation result.

## Scope and assurance

This implementation replaces unsecured legacy stamp CRUD with governed, tenant-scoped **organizational stamp authorization** and independently issued, detached cryptographic attestations. It is NOT a visual stamp impression added to a PDF, not a PDF PAdES signature by the organization, not a statutory seal, and not proof that the organization is legally empowered to issue a regulated stamp. It must never be represented as a completed visually stamped document.

The record binds the authorized stamp authority, its approved custodian, an explicitly approved use of the stamp, the specific already-finalized TrustSeal platform-sealed PDF and its immutable SHA-256 digest, the original review-evidence digest and the issuing operator.

## Workflow

1. **Request a stamp**: An active tenant member submits a normalized code, name and a same-organization active custodian. The stamp starts `pending` and cannot be used.
2. **Independent administrator approval**: An active administrator in the same tenant approves the registration. The approver must not be the creator or custodian. Approval is attributed and recorded in the transactional audit/outbox.
3. **Request one document use**: Only the active stamp's named custodian can submit an application referring to an already-finalized private PDF belonging to the same organization. Before recording the request, TrustSeal rechecks file SHA-256, embedded CMS signature, signed review evidence, signer certificate fingerprint and CA trust.
4. **Independent administrator decision**: An active same-tenant administrator other than the requesting custodian approves or rejects the request. The document signature and immutable digest binding are verified again before approval. Decisions cannot be edited, reversed or repeated.
5. **Independent issuance operator**: An operator-controlled CLI command, disabled by default, uses the organization’s approved stamp application, valid private PDF, protected Ed25519 issuer key and a separately authorized operator. The issuing operator must be an active administrator distinct from the stamp creator, custodian, registration approver, application requester and application approver. It signs the canonical evidence record, checks it against a separately configured pinned public key and atomically stores the immutable attestation and audit event.
6. **Verification/export**: Eligible tenant administrators, the custodian and requester can verify or export the detached evidence. The verifier reconstructs the original stamp/PDF/approval data and rejects mismatches. A later revoked stamp is displayed as inactive but the historically issued receipt is retained.

## API endpoints

The new authenticated `/api/stamp-custody` routes are:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/stamp-custody` | Request a governed stamp |
| GET | `/api/stamp-custody` | List authorized tenant stamp records |
| POST | `/api/stamp-custody/{id}/approve` | Independent administrator approves stamp |
| POST | `/api/stamp-custody/{id}/revoke` | Administrator revokes future use |
| POST | `/api/stamp-custody/{id}/applications` | Custodian requests approval to attest a finalized PDF |
| GET | `/api/stamp-custody/applications/{id}` | Authorized request status |
| POST | `/api/stamp-custody/applications/{id}/decision` | Independent administrator approves/rejects |
| GET | `/api/stamp-attestations/{id}` | Verify stored cryptographic attestation and source evidence |
| GET | `/api/stamp-attestations/{id}/export` | Export signed detached evidence |

Generic legacy stamp routes, including mistaken `/api/api/stamps` and `/api/api/templates`, are retired by the central API policy. New authorization paths remain separately scoped. Neither the new nor legacy API accepts raw private stamp signing keys.

## CLI and configuration

`flask stamp-custody issue <application_id>` and `flask stamp-custody verify <attestation_id>`.

```dotenv
STAMP_ATTESTATION_ENABLED=false
STAMP_ATTESTATION_PRIVATE_KEY=/etc/trustseal/keys/stamp-private.pem
STAMP_ATTESTATION_PUBLIC_KEY=/etc/trustseal/keys/stamp-public.pem
STAMP_ATTESTATION_TRUSTED_KEYS_JSON=
STAMP_ATTESTATION_OPERATOR_ID=
```

Private-key paths must be absolute, non-symlink, access-restricted PEM files. Keep keys out of repositories, web assets and container image layers. The file-backed key adapter and configured user-ID operator assertion are only suitable for isolated staging; production requires HSM/KMS custody, operator MFA, independently audited authorization and revocation.

Configuration includes historical verifier public keys by pinned SHA-256 fingerprint for controlled rotation, but this code does **not** implement a formal key-compromise investigation/revocation or statutory trust policy.

## Persistence and audit

Migration `l6a084e9b7d5` follows `k5f973d8a6c4` and creates `managed_stamps`, `stamp_applications` and `stamp_attestations` with uniqueness, tenant FKs, lifecycle constraints and ordinary SQL tamper guards. It explicitly prevents mutable signed receipts and reopening concluded applications, and constrains stamp state transitions. This is append-only ordinary database protection, not WORM or independently anchored evidence.

The transactional security/outbox channel handles:

`stamp.registration.requested`, `stamp.registration.approved`, `stamp.registration.revoked`, `stamp.use.requested`, `stamp.use.approved`, `stamp.use.rejected` and `stamp.attestation.issued`.

## Tests and assurance gaps

- `tests/test_stamp_attestation.py` exercises Ed25519 issuance/verification, altered PDF hash, incorrect key and invalid status.
- `tests/integration/test_stamp_custody_api.py` covers real PostgreSQL-backed tenant isolation, independent stamp authorization, controlled application approval and revocation; private PDF integrity inspection is mocked only within this authorization test.
- The CI legacy-schema baseline excludes new stamp tables, then replays the new Alembic migration. This is **not** a full upgrade rehearsal from the broken historical 2025 migration chain.

Critical unfinished work before a production-ready electronic stamp module:

1. Generate and render a professional, final PDF stamp *visual impression* under a governed layout and asset custody policy; this detached attestation does not modify PDF content.
2. Bind the visual appearance and precise placement coordinates to the cryptographically signed artifact; verify the final PDF’s CMS bytes after any overlay.
3. Introduce KMS/HSM custody, authorized real-world organizational identity and regulated-stamp eligibility verification, MFA, multiple approvers and key-compromise response.
4. Implement an independently hosted public verifier with appropriate revocation/retention rules and protection from issuer impersonation.
5. Run full operational tests for expired/revoked certificates, unauthorized users, concurrent requests, duplicate application races, database/worker crashes, backup and restore and physical file access control.
6. Repair historical migration-bootstrap incompatibility, test against a restored legacy database and enforce deployment release gates.

The stamp workflow has been implemented as guarded evidence attestation. It is NOT 100% complete as a visually stamped-PDF feature, nor is TrustSeal overall production-ready.
