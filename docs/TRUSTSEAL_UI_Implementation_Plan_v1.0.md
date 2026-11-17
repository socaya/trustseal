# TRUSTSEAL — UI Implementation Plan

**Version:** 1.0
**Date:** 2026-11-17
**Owner:** Vitalworks Limited
**Status:** Implementation baseline. Grounded in the backend capability set shipped through Phases A–AL (89 features) and the UI design-system migration shipped through UI Phases 1–14.

This plan maps every backend capability that TRUSTSEAL already ships to a concrete page or sub-page in the authenticated operator UI, the public surfaces and the signer journey. It is the companion to `docs/TRUSTSEAL_UI_UX_Requirements_Design_System_v1.0.md` — that document defines *how* things look; this one defines *what* ships and *in what order*.

---

## 1. Executive direction

### 1.1 Scope

The backend exposes 89 shipped features across identity, document preparation, signing envelopes, organizational stamps, platform sealing, verification, evidence retention, audit chain, administration, observability and governance. The UI must expose each of these features through a coherent navigation, backed by permission guards, with honest assurance language and without decorative chrome.

### 1.2 Non-negotiables (repeated from the UX spec)

1. **One shell per audience** — authenticated app, public, signer, auth card. No per-module reinvention.
2. **Permission-aware navigation** — nav items hidden when the backing endpoint is not registered or the caller is unauthorized; server enforcement remains the source of truth.
3. **Honest assurance** — a platform-sealed PDF, a drawn signature appearance, a visible stamp impression and a cryptographic signer endorsement are never presented as interchangeable guarantees.
4. **No AI card-wall layouts** — prefer headings, inline strips and tight tables over stacks of bordered panels.
5. **Correlation on every response** — `X-Request-Id` and `X-Trace-Id` surface on every error page so support can line up incidents with server-side logs.

### 1.3 Delivery principle

Each UI phase ships a thin vertical slice: real route, real template, real smoke test against the live Flask dev server, documented in a commit on `main`. Nothing is marked "done" without live-server verification.

---

## 2. Information architecture

### 2.1 Top-level audiences

| Audience        | Shell                          | Entry URL(s)                             |
| --------------- | ------------------------------ | ---------------------------------------- |
| Prospect        | `layouts/public.html`          | `/`, `/welcome`, `/trust`, `/pricing`    |
| Signer / reviewer | `layouts/signer.html`        | `/sign/<token>`, `/sign/<token>/download`, `/sign/<token>/decision`, `/sign/<token>/status`, `/sign/<token>/attachments` |
| Anonymous verifier | `layouts/public.html`        | `/verify`                                |
| Authenticated operator | `layouts/app.html`        | `/`, `/app/...`, `/documents`, `/envelopes/...`, `/stamps/...`, `/evidence/...`, `/admin/...`, `/billing/...` |
| Pre-auth        | `layouts/auth.html`            | `/auth/login`, `/auth/register`, `/auth/reset-password`, `/auth/mfa/...` |

### 2.2 Operator sidebar map

The sidebar in the authenticated shell (`templates/partials_ds/sidebar.html`) groups items into three sections. Any row whose Flask endpoint is not registered in this build is hidden automatically (TS-UI-008).

```
WORKSPACE
  Overview                    system.main_views.home
  My tasks                    system.main_views.home  (currently aliased)
  Documents                   document_views.list_documents
  Signature requests          signature_request_views.list
  Stamps                      stamp_custody_views.list
  Verification                verify_views.verify_form     ← renders app shell when authed
  Evidence & audit            evidence_views.list_retentions
  Notifications               operator_notifications_views.list_notifications

MANAGEMENT
  Templates                   templates_api.list_templates
  Contacts & parties          document_party_views.list
  Teams & delegation          teams_api.list

ADMINISTRATION
  Users & invitations         users_views.list
  Roles & permissions         roles_views.list
  Organization settings       settings_views.index
  Integrations & API          webhook_api.list_endpoints
  Subscriptions & billing     subscription_views.index
  Audit & security            audit_logs_api.list_audit_logs
```

### 2.3 Topbar

| Slot                 | Behaviour                                                                  |
| -------------------- | -------------------------------------------------------------------------- |
| Brand lockup         | `trustseal-horizontal.png` at 44px in a 64px bar                            |
| Workspace chip       | Shows `current_user.organization.name` with a divider                       |
| Global search        | Placeholder search input (planned scope-aware wiring in a later phase)     |
| `+ New` primary CTA  | Deep-links to `document_views.create_document`                              |
| Notifications        | Bell icon with red dot when `unread_notifications`                         |
| Help                 | Placeholder                                                                 |
| Account menu         | Dropdown — user email + tenant, Your profile, Notifications, Design system, Trust & security, Sign out |

---

## 3. Shipped backend capability register

The following table groups every shipped backend capability into the UI module that owns it. Phase IDs match `README.md`.

| Module                           | Backend capability                                          | Phase   |
| -------------------------------- | ----------------------------------------------------------- | ------- |
| Authentication                   | Email verification                                          | A1      |
| Authentication                   | Password reset lifecycle                                    | A2      |
| Authentication                   | Session & device management                                 | A3      |
| Authentication                   | Step-up MFA on high-risk routes                             | A4      |
| Authentication                   | SSO (OIDC)                                                  | pre-A   |
| Authentication                   | SSO (SAML) + SP-signed AuthnRequests                        | G, H3   |
| Authentication                   | Single Logout (OIDC + SAML)                                 | L3      |
| Authentication                   | SCIM 2.0 provisioning                                       | pre-A   |
| Authentication                   | SCIM service-account lifecycle                              | L1      |
| Authentication                   | MFA secret re-wrap under rotated `SECRET_KEY`               | L2      |
| Authentication                   | Identity assurance policies                                 | I1      |
| Authorization                    | Separation of duties                                        | B1      |
| Authorization                    | Teams & departmental scope                                  | B2      |
| Authorization                    | Delegation                                                  | B3      |
| Authorization                    | Row-level security (defence-in-depth)                       | G2      |
| Authorization                    | JWT revocation + refresh rotation                           | G1      |
| Documents                        | Image (PNG/JPEG) ingestion                                  | D1      |
| Documents                        | DOCX ingestion                                              | I4      |
| Documents                        | Safe preview (pypdf)                                        | D2      |
| Documents                        | Full-text search                                            | E3      |
| Documents                        | Bulk upload                                                 | D3      |
| Documents                        | Headings / tables / clauses / variables                     | J1      |
| Documents                        | Draft autosave + optimistic concurrency                     | H2      |
| Documents                        | Document labels                                             | Y1      |
| Documents                        | Document activity timeline                                  | Z2      |
| Documents                        | Document ownership transfer                                 | AJ1     |
| Documents                        | Tenant document label list                                  | AG2     |
| Documents                        | Bulk draft-document delete                                  | AE1     |
| Documents                        | Bulk document label tag / remove                            | AK1, AK2|
| Templates & clauses              | Template revision history, publication, archival           | E1      |
| Templates & clauses              | Clause libraries + approval policies                        | E2      |
| Templates & clauses              | Envelope templates (reusable routing / cadence / roster)    | S1      |
| Envelopes & signing              | Multi-field placement                                       | C1      |
| Envelopes & signing              | Required/optional fields + signer-scoped visibility         | C2      |
| Envelopes & signing              | Field ownership enforcement                                 | C2      |
| Envelopes & signing              | Routing — sequential / parallel / quorum                    | C3      |
| Envelopes & signing              | Routing — witness                                           | C3      |
| Envelopes — conditional routing  | Routing — conditional (JSON predicate DSL)                  | H1      |
| Envelopes — lifecycle            | Reminder, Resend, Withdraw                                  | C4      |
| Envelopes — lifecycle            | Explicit preview + confirmation                             | C5      |
| Envelopes — lifecycle            | Envelope reissue lineage                                    | pre-A   |
| Envelopes — lifecycle            | Envelope auto-expiry (scheduled)                            | N1      |
| Envelopes — lifecycle            | Scheduled reminder scanner                                  | N2      |
| Envelopes — labels               | Envelope labels + filter                                    | Q1      |
| Envelopes — labels               | Tenant envelope label list                                  | AF2     |
| Envelopes — bulk ops             | Bulk envelope withdrawal                                    | Q2      |
| Envelopes — bulk ops             | Bulk participant invitations                                | P3      |
| Envelopes — bulk ops             | Bulk envelope label tag / remove                            | X2, AI2 |
| Envelopes — bulk ops             | Bulk envelope archival                                      | Y2      |
| Envelopes — bulk ops             | Bulk envelope ownership transfer                            | AJ2     |
| Envelopes — bulk ops             | Bulk reminder cadence update                                | AL1     |
| Envelopes — cadence              | Per-envelope reminder cadence overrides                     | R1      |
| Envelopes — archival             | Envelope archival                                           | R2      |
| Envelopes — participants         | Draft participant removal                                   | AA1     |
| Envelopes — participants         | Participant reorder (draft)                                 | AF1     |
| Envelopes — invitations          | Envelope invitation listing (metadata-only)                 | AB1     |
| Envelopes — invitations          | Operator invitation revocation                              | AC2     |
| Envelopes — reminders            | Envelope reminder-all                                       | AC1     |
| Envelopes — transfer             | Envelope ownership transfer + bulk                          | AI1, AJ2|
| Envelopes — activity             | Envelope activity timeline                                  | Z1      |
| Envelopes — attachments          | Signer supporting attachments (upload + evidence bind)      | U1, U2  |
| Envelopes — attachments          | Operator attachment review (list + download)                | V1      |
| Envelopes — attachments          | Attachment lookup by SHA-256                                | AD1     |
| Envelopes — receipts             | Review-receipt (Ed25519) listing                            | AE2     |
| Stamps                           | Stamp designs                                               | pre-A   |
| Stamps                           | Stamp custody & authorization                               | pre-A   |
| Stamps                           | Visible stamp PDF + stamped-PDF trail                       | pre-A   |
| Stamps                           | Stamp attestation records                                   | pre-A   |
| PDF sealing & finalization       | PDF signing via AWS KMS (pyHanko)                           | G4      |
| PDF sealing & finalization       | FinalizedPdf records                                        | pre-A   |
| PDF sealing & finalization       | Platform signer certificate chain                           | pre-A   |
| PDF sealing & finalization       | PAdES-DSS / LT derivatives                                  | pre-A   |
| PDF sealing & finalization       | RFC 3161 TSA integration + TSA chain CRL inventory          | pre-A   |
| PDF sealing & finalization       | Delegated OCSP responder verification                       | M2      |
| Verification                     | Public verifier (anon shell)                                | G13     |
| Verification                     | Verification inside app shell for authed operators          | UI-14.6 |
| Verification                     | Signer status poll (non-consuming)                          | AD2     |
| Evidence & audit                 | Evidence retention + holds + checkpoints                    | pre-A   |
| Evidence & audit                 | Validation dossier                                          | pre-A   |
| Evidence & audit                 | Audit chain + signed anchors                                | G7      |
| Evidence & audit                 | Audit chain anchor listing                                  | AL2     |
| Evidence & audit                 | Audit chain inclusion proof                                 | AH1     |
| Evidence & audit                 | Signed audit-chain slice export                             | M3      |
| Evidence & audit                 | SecurityEvent CSV export                                    | T1      |
| Integrations                     | Webhook endpoints + signed deliveries                       | pre-A   |
| Integrations                     | Webhook delivery ping + replay                              | M1      |
| Integrations                     | Webhook event-type wildcards                                | T2      |
| Integrations                     | Webhook delivery cancellation                               | AB2     |
| Integrations                     | OpenAPI route                                               | pre-A   |
| Operations                       | Durable rate limiter                                        | G8      |
| Operations                       | OpenTelemetry tracing + Prometheus                          | G11     |
| Operations                       | Idempotent transaction outbox + workers                     | pre-A   |
| Operations                       | Outbox dead-letter inspection + replay                      | P1      |
| Operations                       | Admin dashboard aggregator                                  | P2      |
| Operations                       | Liveness + readiness probes                                 | N3      |
| Operations                       | Pluggable private storage                                   | O       |
| Operations                       | Prometheus operator-notification counter                    | AH2     |
| Operations                       | Request/trace correlation headers                           | S2      |
| Operations                       | Enterprise SLOs + error budgets                             | J5      |
| Operations                       | SBOM + SAST / dependency / secrets scanning                 | J3, J4  |
| Governance                       | GDPR Art. 20 signed tenant export                           | K1      |
| Governance                       | GDPR Art. 17 tenant data erasure                            | K2      |
| Governance                       | Break-glass operator access (time-bound)                    | K3      |
| Subscriptions & billing          | Subscription records + billing hooks                        | I5      |
| Subscriptions & billing          | Usage ledger + plan entitlements                            | pre-A   |
| Subscriptions & billing          | Usage ledger CSV export                                     | V2      |
| Notifications                    | Operator notifications (DB-backed)                          | W1      |
| Notifications                    | Auto-publish on envelope auto-expiry                        | W2      |
| Notifications                    | Notifications on webhook dead-letter + seal                 | X1      |
| Notifications                    | Notification feed kind filter                               | AA2     |

---

## 4. Module-by-module page inventory

The tables below are **the implementation target**. `Status` uses:

- 🟢 **Shipped** — page exists on the modern design-system shell and is smoke-tested.
- 🟡 **Shim** — route exists and renders via the `base.html` compatibility shim; re-template still owed.
- ⚪ **Planned** — route doesn't exist yet; template owed.

### 4.1 Workspace

| URL                              | Page                               | Status | Notes                                                                              |
| -------------------------------- | ---------------------------------- | ------ | ---------------------------------------------------------------------------------- |
| `/`                              | Operator overview (dashboard)      | 🟢     | Compact metric strip + Recent documents + optional Recent activity.               |
| `/welcome`                       | Public landing                     | 🟢     | Also served at `/` for anonymous users.                                            |
| `/app/notifications`             | Notifications feed                 | 🟢     | Unread / All / kind filter; mark-read, mark-all-read.                              |
| `/app/notifications` (quick-action) | Notification detail                | ⚪     | Navigate to subject link; no dedicated page yet.                                   |
| `/app/tasks`                     | My tasks                           | ⚪     | Aggregate view of signing, approvals and admin follow-ups.                        |
| `/app/profile`                   | Your profile                       | 🟢     | Edit first_name / last_name / phone; identity fields are read-only.                |
| `/app/global-search`             | Search results                     | ⚪     | Document / envelope / party / reference — cross-module scoped search.              |

### 4.2 Documents

| URL                                           | Page                                | Status | Notes                                                                 |
| --------------------------------------------- | ----------------------------------- | ------ | --------------------------------------------------------------------- |
| `/documents`                                  | Library list                        | 🟢     | Server-paginated, label-filterable, status badges, mobile cards.      |
| `/documents/create`                           | Upload / create inline              | 🟢     | Upload or inline-create; `role="tab"` switcher without jQuery.         |
| `/documents/<id>`                             | Document details                    | 🟢     | Info / File / Versions / Parties / Signatures / Shares / Activity.    |
| `/documents/<id>/edit`                        | Edit document details               | 🟢     | Title + description only; finalised documents refuse edits.           |
| `/documents/<id>/activity`                    | Activity timeline                   | 🟢 (API) | API ships; needs dedicated tab-level HTML view.                      |
| `/documents/<id>/labels`                      | Labels panel (inline)               | 🟢 (API) | HTML CRUD planned inside the detail page.                            |
| `/documents/by-label/<label>`                 | Documents by label                  | 🟢 (API) | HTML list view planned; sidebar autocomplete uses tenant label list.  |
| `/documents/bulk/label` & `…/label/remove`    | Bulk tag / untag                    | 🟢 (API) | Toolbar on library planned.                                           |
| `/documents/bulk/delete`                      | Bulk soft-delete                    | 🟢 (API) | Bulk action menu planned.                                             |
| `/documents/<id>/transfer`                    | Transfer ownership                  | 🟢 (API) | Modal from details page planned.                                      |
| `/documents/<id>/versions/*`                  | Versions sub-area                   | 🟡     | Placeholder renders via shim.                                         |
| `/documents/<id>/parties/*`                   | Parties sub-area                    | 🟡     | Placeholder renders via shim.                                         |
| `/documents/<id>/shares/*`                    | Shares sub-area                     | 🟡     | Placeholder renders via shim.                                         |
| `/documents/<id>/signatures/*`                | Signatures sub-area                 | 🟡     | Placeholder renders via shim.                                         |
| `/documents/<id>/activities/*`                | Activity entries CRUD               | 🟡     | Placeholder renders via shim.                                         |

### 4.3 Signature requests (envelopes)

The envelope surface is the spine of the product. The canonical URL root is `/envelopes`.

| URL                                                     | Page                              | Status | Notes                                                                 |
| ------------------------------------------------------- | --------------------------------- | ------ | --------------------------------------------------------------------- |
| `/envelopes`                                            | Envelopes list                    | ⚪     | Server-paginated; `?label=` filter; `?include_archived=1` flag.       |
| `/envelopes/new`                                        | Prepare envelope                  | ⚪     | Pick document + blob, routing mode, participants, cadence, expiry.    |
| `/envelopes/<id>`                                       | Envelope detail                   | ⚪     | Sections: Participants, Fields, Invitations, Receipts, Attachments, Activity, Labels, Reminder cadence, Archive controls. |
| `/envelopes/<id>/participants`                          | Participants panel                | 🟢 (API) | List + add + remove + reorder + bulk invite via inspector panel.     |
| `/envelopes/<id>/fields`                                | Field placement                   | 🟢 (API) | Signature / initials / date / text / checkbox editor (planned UI).    |
| `/envelopes/<id>/participants/<pid>/rules`              | Conditional routing editor        | 🟢 (API) | JSON predicate builder.                                              |
| `/envelopes/<id>/invitations`                           | Invitations                       | 🟢 (API) | Metadata only — never surfaces raw tokens.                            |
| `/envelopes/<id>/invitations/<inv>/revoke`              | Revoke invitation                 | 🟢 (API) | Inline action in invitations table.                                   |
| `/envelopes/<id>/attachments`                           | Signer attachments                | 🟢 (API) | List + download; staged (unbound) rows hidden from operators.        |
| `/envelopes/<id>/receipts`                              | Review receipts                   | 🟢 (API) | Signed Ed25519 attestations returned verbatim.                       |
| `/envelopes/<id>/activity`                              | Activity timeline                 | 🟢 (API) | Chained-hash SecurityEvent slice.                                     |
| `/envelopes/<id>/reminders`                             | Reminder cadence                  | 🟢 (API) | Per-envelope cooloff + max count override.                           |
| `/envelopes/<id>/reminders/send-all`                    | Reminder all                      | 🟢 (API) | Toolbar action, per-row result list.                                  |
| `/envelopes/<id>/withdraw`                              | Withdraw envelope                 | 🟢 (API) | Modal with reason.                                                    |
| `/envelopes/<id>/archive`, `/unarchive`                 | Archive controls                  | 🟢 (API) | Visible in terminal-state envelopes.                                  |
| `/envelopes/<id>/transfer`                              | Transfer ownership                | 🟢 (API) | New-owner modal; notifies target in-app.                             |
| `/envelopes/bulk/withdraw`                              | Bulk withdraw                     | 🟢 (API) | Bulk action menu.                                                     |
| `/envelopes/bulk/archive`                               | Bulk archive                      | 🟢 (API) | Bulk action menu.                                                     |
| `/envelopes/bulk/label`, `/bulk/label/remove`           | Bulk label                         | 🟢 (API) | Bulk action menu.                                                     |
| `/envelopes/bulk/transfer`                              | Bulk transfer                     | 🟢 (API) | Bulk action menu; new-owner modal.                                    |
| `/envelopes/bulk/reminders`                             | Bulk cadence update               | 🟢 (API) | Bulk action menu.                                                     |
| `/envelopes/labels`                                     | Tenant envelope label list        | 🟢 (API) | Powers the autocomplete; tag chips on list + detail.                  |

### 4.4 Envelope templates (reusable prepare config)

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/envelope-templates`                         | List                              | 🟢 (API) |
| `/envelope-templates/new`                     | Create                            | 🟢 (API) |
| `/envelope-templates/<id>`                    | Detail + participants             | 🟢 (API) |
| `/envelope-templates/<id>/edit`               | Edit                              | 🟢 (API) |
| `/envelope-templates/<id>/instantiate`        | Instantiate as new envelope       | 🟢 (API) |

### 4.5 Digital stamps & seals

| URL                                           | Page                              | Status | Notes                                                                 |
| --------------------------------------------- | --------------------------------- | ------ | --------------------------------------------------------------------- |
| `/stamps`                                     | Custody dashboard (grants + status) | 🟡   | Custody list + state filter.                                           |
| `/stamps/designs`                             | Stamp design library              | 🟡     | Design editor + preview at realistic scale.                           |
| `/stamps/designs/<id>`                        | Design detail + version history   | ⚪     |                                                                       |
| `/stamps/designs/<id>/approve`                | Approval flow                     | ⚪     | Approver-only; audit record.                                           |
| `/stamps/custody`                             | Managed stamps + custodians       | 🟡     | Who can use which stamp, effective dates, revocations.                |
| `/stamps/custody/<id>`                        | Managed stamp detail              | ⚪     |                                                                       |
| `/stamps/applications`                        | Stamp applications history        | 🟡     |                                                                       |
| `/stamps/applications/<id>`                   | Application detail                | ⚪     | Document / version / position / attestation link.                     |
| `/stamps/attestations`                        | Stamp attestations                | ⚪     | Immutable record of each applied stamp.                               |
| `/stamps/usages`                              | Stamp usage ledger                | 🟡     |                                                                       |

### 4.6 PDF sealing & finalization

| URL                                           | Page                              | Status | Notes                                                                 |
| --------------------------------------------- | --------------------------------- | ------ | --------------------------------------------------------------------- |
| `/finalized-pdfs`                             | Finalized PDFs list               | ⚪     |                                                                       |
| `/finalized-pdfs/<id>`                        | Finalized PDF detail              | ⚪     | Source blob, output sha256, certificate sha256, profile.             |
| `/platform-signer/chain`                      | Platform signer certificate chain | ⚪     |                                                                       |
| `/platform-signer/tsa-chain-crls`             | TSA chain + CRL inventory         | ⚪     |                                                                       |
| `/platform-signer/dss-derivatives`            | PAdES-DSS derivatives             | ⚪     |                                                                       |
| `/platform-signer/delegated-ocsp`             | Delegated OCSP responders         | ⚪     |                                                                       |

### 4.7 Verification & evidence

| URL                                                       | Page                                | Status | Notes                                                                 |
| --------------------------------------------------------- | ----------------------------------- | ------ | --------------------------------------------------------------------- |
| `/verify` (anonymous)                                     | Public verifier                     | 🟢     | `layouts/public.html`.                                               |
| `/verify` (authenticated)                                 | Verifier inside workspace shell     | 🟢     | `layouts/app.html` with active sidebar row.                          |
| `/evidence/retentions`                                    | Evidence retentions list            | 🟢     | Preserved, Retention due, Indefinite tones.                           |
| `/evidence/retentions/<id>`                               | Retention detail                    | 🟢     | Canonical digest, legal holds, checkpoints, timestamps, OCSP, CRL, dossiers, DSS. |
| `/evidence/validation-dossiers/<id>`                      | Validation dossier detail           | ⚪     | Deep-link when a dossier is picked from retention detail.             |
| `/evidence/audit-chain/anchors`                           | Signed anchor list                  | 🟢 (API) | Admin-only; forward paging.                                          |
| `/evidence/audit-chain/proof?event_id=…`                  | Inclusion proof                     | 🟢 (API) | Admin tool; HTML view planned.                                        |
| `/evidence/audit-chain/export`                            | Signed slice export                 | 🟢 (API) |                                                                       |
| `/evidence/security-events/export.csv`                    | SecurityEvent CSV export            | 🟢 (API) |                                                                       |

### 4.8 Contacts, parties, organizations & clients

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/parties`                                    | Parties / contacts list           | 🟡     |
| `/parties/<id>`                               | Party detail                      | ⚪     |
| `/organizations`                              | Organizations list                | 🟡     |
| `/organizations/<id>`                         | Organization detail               | ⚪     |
| `/organizations/<id>/clients`                 | Clients under organization        | 🟡     |

### 4.9 Teams & delegation

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/teams`                                      | Teams list                        | 🟡     |
| `/teams/<id>`                                 | Team detail + memberships         | ⚪     |
| `/delegations`                                | Outgoing / incoming delegations   | 🟢 (API) |
| `/delegations/grant`                          | Grant delegation                  | 🟢 (API) |
| `/delegations/<id>/revoke`                    | Revoke delegation                 | 🟢 (API) |

### 4.10 Administration — users & access

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/users`                                | Users list                        | 🟡     |
| `/admin/users/<id>`                           | User detail                       | ⚪     |
| `/admin/users/<id>/edit`                      | Edit user                         | ⚪     |
| `/admin/users/<id>/change-password`           | Reset user password (admin)       | ⚪     |
| `/admin/invitations`                          | Pending user invitations          | 🟡     |
| `/admin/invitations/new`                      | Invite a user                     | ⚪     |
| `/admin/roles`                                | Roles list                        | 🟡     |
| `/admin/roles/<id>`                           | Role detail                       | ⚪     |
| `/admin/permissions`                          | Permissions                       | 🟡     |
| `/admin/user-roles`                           | User-role assignments             | 🟡     |
| `/admin/sod-policies`                         | Separation-of-duties rules        | ⚪     |
| `/admin/identity-assurance`                   | Assurance policy (TOTP / webauthn / IdP) | ⚪  |

### 4.11 Administration — identity providers & SSO

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/idp/oidc`                             | OIDC providers list               | ⚪     |
| `/admin/idp/oidc/<id>`                        | OIDC provider detail              | ⚪     |
| `/admin/idp/saml`                             | SAML providers                    | ⚪     |
| `/admin/idp/saml/<id>`                        | SAML provider detail              | ⚪     |
| `/admin/idp/saml/metadata`                    | SP metadata XML                   | 🟢 (route) |
| `/admin/idp/saml/sp-signing`                  | SP signing key rotation           | ⚪     |
| `/admin/idp/single-logout`                    | SLO wiring                        | 🟢 (API) |
| `/admin/scim/service-accounts`                | SCIM service accounts             | ⚪     |
| `/admin/scim/service-accounts/<id>/rotate`    | Rotate SCIM key                   | 🟢 (API) |
| `/admin/break-glass`                          | Break-glass grants                | 🟢 (API) |

### 4.12 Administration — MFA & secrets

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/mfa/credentials`                      | MFA credentials                   | ⚪     |
| `/admin/mfa/recovery-codes`                   | MFA recovery codes                | ⚪     |
| `/admin/mfa/rewrap`                           | Secret re-wrap operation          | ⚪     |

### 4.13 Administration — integrations & API

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/webhooks`                             | Webhook endpoints list            | 🟡     |
| `/admin/webhooks/new`                         | Create webhook                    | ⚪     |
| `/admin/webhooks/<id>`                        | Webhook detail                    | ⚪     |
| `/admin/webhooks/<id>/deliveries`             | Delivery history                  | ⚪     |
| `/admin/webhooks/deliveries/<id>/replay`      | Replay delivery                   | 🟢 (API) |
| `/admin/webhooks/deliveries/<id>/cancel`      | Cancel delivery                   | 🟢 (API) |
| `/admin/openapi`                              | OpenAPI reference                 | 🟢 (route) |

### 4.14 Administration — outbox & reliability

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/outbox`                               | Outbox event summary              | ⚪     |
| `/admin/outbox/dead`                          | Dead-letter inspection            | 🟢 (API) |
| `/admin/outbox/dead/<id>/replay`              | Replay dead event                 | 🟢 (API) |
| `/admin/idempotency`                          | Idempotency records               | ⚪     |

### 4.15 Administration — observability

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/dashboard`                            | Admin dashboard aggregator        | 🟢 (API) |
| `/admin/slo`                                  | SLO observations                  | 🟢 (API) |
| `/admin/health`, `/admin/ready`               | Health + readiness probes         | 🟢 (route) |
| `/metrics`                                    | Prometheus scrape target          | 🟢 (route) |
| `/admin/security-events`                      | SecurityEvent explorer            | ⚪     |

### 4.16 Administration — storage

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/admin/storage/backend`                      | Active private-storage backend    | ⚪     |
| `/admin/storage/retention-policies`           | Retention policies                | ⚪     |

### 4.17 Subscriptions, billing & usage

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/billing`                                    | Current plan + renewal            | 🟡     |
| `/billing/subscriptions`                      | Subscriptions                     | 🟡     |
| `/billing/plans`                              | Plan catalogue                    | 🟡     |
| `/billing/payments`                           | Payment history                   | 🟡     |
| `/billing/usage`                              | Usage ledger (per meter, period)  | 🟢 (API) |
| `/billing/usage/export.csv`                   | Usage CSV export                  | 🟢 (API) |
| `/billing/entitlements`                       | Plan entitlements enforcement     | ⚪     |

### 4.18 Governance & compliance

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/governance/data-export`                     | GDPR Art. 20 signed tenant export | 🟢 (API) |
| `/governance/data-erasure`                    | GDPR Art. 17 tenant data erasure  | 🟢 (API) |
| `/governance/break-glass`                     | Break-glass operator grants       | 🟢 (API) |
| `/governance/legal-holds`                     | Evidence legal holds              | 🟢 (API) |

### 4.19 Settings

| URL                                           | Page                              | Status |
| --------------------------------------------- | --------------------------------- | ------ |
| `/settings`                                   | Organization settings             | 🟡     |
| `/settings/notifications`                     | Notification defaults             | ⚪     |
| `/settings/reminders`                         | Default reminder cadence          | ⚪     |
| `/settings/branding`                          | Signer-landing branding (future)  | ⚪     |
| `/settings/retention`                         | Retention policy defaults         | ⚪     |

### 4.20 Public / marketing

| URL                     | Page                           | Status |
| ----------------------- | ------------------------------ | ------ |
| `/` (anonymous), `/welcome` | Public landing              | 🟢     |
| `/trust`                | Trust & security notes         | 🟢     |
| `/pricing`              | Pricing (contact-based)        | 🟢     |
| `/verify` (anonymous)   | Public verifier                | 🟢     |

### 4.21 Signer journey

| URL                                     | Page                                | Status |
| --------------------------------------- | ----------------------------------- | ------ |
| `/sign/<token>`                         | Review envelope                     | 🟢     |
| `/sign/<token>/download`                | Download PDF                        | 🟢 (route) |
| `/sign/<token>/attachments` (POST)      | Upload supporting attachment        | 🟢 (route) |
| `/sign/<token>/decision` (POST)         | Acknowledge / decline               | 🟢 (route) |
| `/sign/<token>/status`                  | Non-consuming status poll           | 🟢 (route) |
| recorded / unavailable / rate-limited   | End-state pages                     | 🟢     |

### 4.22 Pre-auth & profile

| URL                                   | Page                              | Status |
| ------------------------------------- | --------------------------------- | ------ |
| `/auth/login`                         | Sign in                           | 🟢     |
| `/auth/register`                      | Create account                    | 🟢     |
| `/auth/reset-password`                | Password reset request            | 🟢     |
| `/auth/change-password`               | Change password                   | ⚪     |
| `/auth/mfa/enrol`                     | MFA enrolment                     | ⚪     |
| `/auth/mfa/verify`                    | MFA challenge                     | ⚪     |
| `/auth/verify-email/<token>`          | Email-verification confirmation   | ⚪     |
| `/auth/sso/oidc`, `/auth/sso/saml`    | SSO entry points                  | ⚪     |
| `/app/profile`                        | Operator profile                  | 🟢     |

### 4.23 Design-system reference

| URL                                   | Page                              | Status |
| ------------------------------------- | --------------------------------- | ------ |
| `/design/gallery`                     | Admin-only component gallery      | 🟢     |

### 4.24 Error pages

| URL        | Page                               | Status |
| ---------- | ---------------------------------- | ------ |
| `/*` → 404 | Page not found                     | 🟢     |
| `/*` → 403 | Access not permitted               | 🟢     |
| `/*` → 429 | Too many requests                  | 🟢     |
| `/*` → 500 | Internal server error (+ X-Request-Id) | 🟢 |

---

## 5. Execution phases (ordered)

Each phase is a vertical slice: template + any supporting endpoint wiring + live smoke test + commit.

### Phase A — ✅ Core design system (shipped)

- Brand assets + manifest (UI-F1)
- Design tokens + reset (UI-F2)
- Shell CSS (UI-F3)
- Component CSS (UI-F4)
- Public shell CSS (UI-F5)
- Layout templates — app / public / signer / auth (UI-F6)
- Reusable partials (UI-F7)
- Component gallery (UI-F8)

### Phase B — ✅ Core workspace entry points (shipped)

- Public landing + /welcome (UI-P2.1 / UI-P12)
- Operator overview (UI-P2.2 / UI-P14.1)
- Public verifier (UI-P2.3)
- Login (UI-P2.4)

### Phase C — ✅ Signer journey + auth completeness (shipped)

- Signer review (UI-P3.1)
- Signer end-state pages (UI-P3.2)
- Register (UI-P3.3)
- Reset password (UI-P3.4)

### Phase D — ✅ Notifications, evidence, errors, documents, details (shipped)

- Operator notifications (UI-P4.1)
- Evidence retentions list (UI-P4.2) + detail (UI-P6.1)
- Error pages (UI-P4.3)
- Documents list / create / edit (UI-P5.1–3)
- Document details (UI-P7.1)

### Phase E — ✅ Shell cleanup, branding, access flows (shipped)

- Retire base.html + module_base.html (UI-P8)
- Trust page + account dropdown (UI-P9)
- Pricing + profile + link cleanup (UI-P10)
- Dev harness (UI-P11)
- Type scale + topbar size + register fix (UI-P13)
- Dashboard overhaul + nav polish (UI-P14)
- /verify authenticated shell (UI-P14.6)

### Phase F — Envelope surface (next)

Order of work:

1. `/envelopes` — server-paginated list on `data_table` with label filter + archived flag.
2. `/envelopes/new` — Prepare wizard: document picker → routing → participants → cadence → preview → send.
3. `/envelopes/<id>` — Detail page. Sections: Overview, Participants, Fields, Invitations, Receipts, Attachments, Activity, Labels, Reminder cadence, Lifecycle (withdraw / archive / transfer).
4. Bulk-action toolbar on the list (withdraw / archive / label / transfer / cadence).
5. Reminder cadence modal + reminder-all toolbar button.
6. Invitation revocation inline action.
7. Attachment review in details.
8. Receipts section on details.
9. Activity timeline tab on details.

### Phase G — Envelope templates

- `/envelope-templates` list + create + edit.
- Participants editor.
- Instantiate action (from the envelope-templates list and inline on `/envelopes/new`).

### Phase H — Stamps

- `/stamps` custody dashboard.
- `/stamps/designs` library + detail + approval flow.
- `/stamps/applications` + attestations.
- Operator-only "Apply stamp" CTA on the envelope detail page.

### Phase I — Finalized PDFs + platform signer chain

- `/finalized-pdfs` + detail.
- `/platform-signer/*` admin pages (chain, TSA CRL inventory, DSS, delegated OCSP).

### Phase J — Administration surfaces

- Users + invitations (list + detail + invite flow).
- Roles + permissions + user-role assignments.
- SoD policies + identity-assurance policy.
- Organization + clients + parties.
- Teams + memberships.

### Phase K — Identity providers + SSO + SCIM + MFA + break-glass

- OIDC + SAML provider lists + detail pages + SP signing rotation.
- SP metadata and SLO wiring page.
- SCIM service-account management + rotate.
- MFA credentials + recovery codes + re-wrap page.
- Break-glass grants page.

### Phase L — Integrations & reliability

- Webhook endpoints list + create + detail + deliveries + replay + cancel.
- OpenAPI reference (iframe or redoc view).
- Outbox summary + dead-letter inspection.
- Idempotency-record browser.

### Phase M — Observability & governance

- Admin dashboard aggregator HTML.
- SLO observations.
- Health + readiness probe status page (optional).
- SecurityEvent explorer (CSV export already shipped).
- Governance: data-export, erasure, break-glass, legal holds.

### Phase N — Subscriptions, billing, usage, settings

- Billing dashboard: current plan + renewal + invoice history.
- Plans catalogue + entitlements.
- Usage ledger + CSV export page.
- Organization settings sub-pages.

### Phase O — Public polish

- Public footer rewrite for marketing links (contact, docs, status).
- Signer-landing branding integration point (once `TenantSignerBranding` ships in the backend).

### Phase P — Accessibility regression harness (axe-core + Playwright)

- End-to-end axe-core audit on public verify, sign landing + review, evidence retention list, stamp custody dashboard.
- Keyboard-only + screen-reader passes.
- Covers TS-UI-006 and TS-UI-019.

---

## 6. Cross-cutting concerns

### 6.1 Permission enforcement

- Every list / detail route applies tenant filtering first, then owner/role filtering. The sidebar hides nav items whose endpoint is not registered; the view itself still checks `current_user`, `is_admin`, `is_tenant_member` and falls through to the 403 page on failure.
- Destructive actions (withdraw, archive, transfer, bulk ops) require explicit confirmation modals (`components_ds/confirmation_dialog.html`).
- Admin-only surfaces (outbox DLQ, audit anchors, SecurityEvent export, admin dashboard) gate on `policies.api_access.is_admin`.

### 6.2 Audit propagation

- Every mutating action enqueues a SecurityEvent via `event_delivery.enqueue`; this appends to the chained-hash audit log automatically.
- The envelope detail page's Activity timeline (Phase Z1) and the admin SecurityEvent explorer read the same log.
- Correlation IDs land on every 5xx error page so operators can share them with support without screenshotting a stack trace.

### 6.3 Status semantics

Use the semantic status classes defined in `components.css`:

| Domain                     | Tones used                                                                          |
| -------------------------- | ----------------------------------------------------------------------------------- |
| Document lifecycle         | `neutral` (draft) / `info` (review) / `pending` (awaiting) / `success` (completed) / `warning` (archived) |
| Recipient decision         | `pending` / `info` (viewed) / `success` (acknowledged) / `danger` (declined) / `warning` (expired) |
| Cryptographic verification | `success` (valid) / `danger` (invalid) / `warning` (untrusted) / `indeterminate`    |
| Stamp custody              | `success` (active) / `warning` (suspended) / `danger` (revoked) / `warning` (expired)|
| Evidence availability      | `success` (preserved) / `pending` (pending) / `warning` (retention due) / `danger` (unavailable) |

### 6.4 Responsive behaviour

- The shell collapses the sidebar to a drawer below 1024px; data tables switch to the `data-label` card layout below 768px.
- The signer review page keeps the PDF.js viewer scrollable within a 70vh container regardless of viewport.
- The landing hero stacks on mobile.

### 6.5 Accessibility

- All interactive controls carry a programmatic name and a visible focus ring (`--ts-focus`).
- Semantic headings: one `<h1>` per page (the page title), section `<h2>`s, sub-section `<h3>`s.
- Forms always render visible labels; errors are announced inline with `role="alert"`.
- Status dots have their colour accompanied by the status text (never colour-alone).

### 6.6 Telemetry

- `X-Request-Id` + `X-Trace-Id` on every HTTP response.
- Prometheus metrics include a counter for operator-notification publishes (Phase AH2) and SLO observations.
- Admin dashboard aggregator (`/api/_internal/dashboard`) powers the operator-facing admin dashboard page planned in Phase M.

---

## 7. Dependency notes — what the UI does not add

- The UI never bypasses the server-side policy guard. Hiding a control is not authorization.
- The UI does not persist state the backend doesn't persist (saved views, column visibility and density preference are per-browser localStorage until the backend grows a user-preferences table).
- The UI does not add new routes beyond what the backend already exposes; any ⚪ entry in the inventory depends on wiring a view + template against an existing API or model, not on inventing new business rules.
- The UI does not change evidence semantics. A platform-sealed PDF and an individual signer PKI endorsement remain separate.

---

## 8. Definition of done (for this plan)

TRUSTSEAL's UI is complete for v1 when:

1. Every row in the tables in §4 is **🟢 Shipped** (route exists, template on design-system shell, smoke-tested).
2. Every destructive action has a confirmation dialog + an audit SecurityEvent.
3. Every list has a meaningful empty state with a next-action link.
4. Every form has visible labels, inline error summary, and preserved input on validation failure.
5. Every status badge uses a token from `components.css`; no page-local status styles.
6. Every page renders at 1440 / 1024 / 768 / 390 widths.
7. Every endpoint referenced by a nav item is registered in the build (no dead links).
8. Playwright + axe-core sweep passes the acceptance journeys in Phase P.
9. The retired `base.html` and `module_base.html` shims are removed once every template that currently extends them has been migrated directly to the design-system layouts.

---

## 9. Change control

- This plan is versioned alongside the design-system spec. A change to the backend capability register (e.g. a new Phase AM shipping a feature) **must** update §3 and the relevant module in §4, and schedule a UI slice in §5.
- Every UI phase commit cites its UI-P# identifier in the commit message.
- Status flips (⚪ → 🟡 → 🟢) are only updated after live-server verification.

---

### Document control

Derived from the shipped backend capability register in `README.md` (Phases A–AL) and the UI migration shipped through UI Phases 1–14. Cross-reference `docs/TRUSTSEAL_UI_UX_Requirements_Design_System_v1.0.md` for visual norms and `docs/REMAINING_GAPS_2026-11-15.md` for non-code-addressable items.
