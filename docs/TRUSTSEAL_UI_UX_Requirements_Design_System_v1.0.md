# TRUSTSEAL — Comprehensive UI/UX Requirements and Design System

**Version:** 1.0  
**Date:** 15 November 2026  
**Product:** TRUSTSEAL — Verified Integrity  
**Owner:** Vitalworks Limited  
**Document type:** UI/UX Product Requirements, Design System, Information Architecture and Implementation Specification  
**Status:** Implementation baseline; proposed requirements must be validated against permissions, API contracts and operational policy before launch.

---

## 1. Executive direction

TRUSTSEAL shall offer a disciplined enterprise user experience for creating, managing, signing, stamping, sealing, distributing and independently verifying sensitive digital documents. It shall look and behave like one coherent product. Its presentation must be calm, compact, professional and trustworthy, reflecting the quality of the VitalReturns application while preserving TRUSTSEAL's independent brand and specialized assurance workflows.

The governing principle is **clarity of evidence over decoration**. Users need to know what a document is, who is responsible for the next action, what has and has not been cryptographically verified, when an action occurred, and what evidence can be obtained. Interface design must reinforce this understanding instead of obscuring it behind visual effects, generic charts, excessive cards or ambiguous status labels.

This document specifies a comprehensive target UI. It is **not** a claim that every proposed screen or interaction has already been implemented. The findings below are based on the repository files inspected on 15 November 2026. They must be followed by a route, API and permission audit before development changes are merged.

### 1.1 Non-negotiable visual requirements

1. Use a flat professional design, predominantly white surfaces and light neutral backgrounds; no gradients, glassmorphism, decorative glows, oversized shadows or floating promotional shapes.
2. No AI-like pill/chip backgrounds behind headings, arbitrary colorful cards, giant rounded widgets or decorative badges. Status indicators are permitted only when they convey genuine workflow or verification state; favor text and subtle icons.
3. Preserve supplied TRUSTSEAL logo geometry and wordmark; do not redraw or alter proportions or typography based on convenience.
4. Brand navy and green shall be applied consistently, with green primarily reserved for verified/success semantics. Do not color an entire page green to signify trust.
5. No full-page horizontal scrolling. Dense tables can scroll within their own constrained region where necessary, with frozen identifying columns where feasible.
6. The product shall behave consistently on desktop, tablet and mobile, without hiding essential verification, signing or evidence actions.
7. All business-critical actions must have clear identity, authorization, confirmation, result and audit feedback.
8. A certificate seal, human signature, visual signature mark, organizational stamp and document verification verdict must never be presented as interchangeable assurances.

## 2. Source review and traceability

### 2.1 Inspected repositories

- TRUSTSEAL: <https://github.com/socaya/trustseal>
- VitalReturns: <https://github.com/vitalworks-limited/vitalreturns>

The following code paths informed this specification:

| Reference | What was confirmed | UI implication |
|---|---|---|
| TRUSTSEAL `app/templates/base.html` | Bootstrap 5, AdminLTE, DataTables, shared navbar and sidebar, externally hosted CSS/JS | Replace inconsistent styling with a deliberate TRUSTSEAL shell; make dependencies reproducible and review external-asset exposure. |
| TRUSTSEAL `app/templates/partials/sidebar.html` | Main sidebar includes dashboard, documents, stamps, signatures, subscriptions and users; several links currently target the home route | Create an accurate, permission-aware navigation map and eliminate placeholder destinations. |
| TRUSTSEAL `app/static/css/trustseal.css` | Existing primary `#0F3B82`, green `#0E664D`, a 240px dark sidebar, Bootstrap-derived shapes | Consolidate into a token system and remove competing colors, radii and module-specific overrides. |
| TRUSTSEAL `app/templates/dashboard.html` | Four large module cards, with decorative icons and repeated card CTAs | Replace promotional tiles with concise operational summaries and actionable work queues. |
| TRUSTSEAL `app/templates/trust/verify.html` | Public PDF verification, SHA-256 evidence digest, verdicts and certificate information | Preserve accurate verification language, privacy characteristics and inspectable evidence in the redesigned public UI. |
| TRUSTSEAL `app/templates/envelopes/sign/review.html` | PDF preview, consent, signer decision and optional visual signature capture | Design a precise signing/review journey that distinguishes signer intent from cryptographic guarantees. |
| TRUSTSEAL `docs/REMAINING_GAPS_2026-11-15.md` | Browser-based axe-core/Playwright accessibility verification remains a gap; other operational and governance items are noted | Require end-to-end accessibility regression and distinguish UI completion from operational sign-off. |
| VitalReturns `plans/docs/v2.0.0/VitalReturns_UI_UX_Components_Requirements_v2.0.md` | One shell, context preservation, compact data density, 56px topbar, contextual panels, accessibility | Adopt structural and behavioral discipline, but not tax-specific terms or colors. |
| VitalReturns `plans/v2.2-ui-standardization.md` | Shared KPI, status, banner and filter components and semantic tokens; explicit removal of repeated ad-hoc styles | Establish one component owner, shared design tokens and a migration ledger. |
| VitalReturns `source/styles/tokens.css` and `source/app/globals.css` | Neutral surfaces, typography, spacing, restrained elevation and semantic state tokens | Use the token approach as a model while defining TRUSTSEAL's own palette. |

These are source-code findings; live browser rendering, all routes, authenticated accounts and every screen were **not** independently exercised as part of this review. The reference website may change independently of its repository.

### 2.2 Present design weaknesses to resolve

TRUSTSEAL currently mixes AdminLTE's dashboard conventions with Bootstrap forms, handcrafted inline styles and a limited product stylesheet. Several public signing and verification screens define colors, spacing and borders directly in templates. The shell contains generic username/logout controls and module navigation that does not yet represent the product's full functional structure. This creates visual inconsistency and risks user journeys that appear complete while routing to a generic landing screen.

The target shall correct these issues through one design system and a route-backed, permission-aware information architecture. Do not mistake a successful CSS refresh for a complete UI implementation: the work must include navigation, end states, error paths, accessibility, document identity, permissions and evidence transparency.

## 3. Brand identity and usage

### 3.1 Approved imagery and lockups

The supplied artwork establishes three product elements: a navy shield outline, a check mark in green or monochrome navy, and the TRUSTSEAL wordmark. The tagline is **VERIFIED INTEGRITY**. Approved placement families are: horizontal lockup with tagline, horizontal compact lockup without tagline, vertical stacked lockup, shield-only icon, monochrome black, monochrome white on navy and navy-only mark.

**Primary UI lockup:** horizontal shield and TRUSTSEAL wordmark without tagline when navigation width is constrained. **Public marketing, verification and document cover use:** horizontal lockup with tagline when readable. **Favicon and small sidebar rail:** shield icon only. **Dark surfaces:** supplied white mono version. **Print/grayscale:** supplied black mono version.

Never stretch artwork, change the green check to another decorative color, add shadows, wrap the logo inside arbitrary circular chips, independently re-typeset the wordmark or crop the shield. Keep clear space around the mark of at least half the visible shield width where possible. Do not rely on a low-resolution raster as the canonical asset: obtain approved source SVG/vector assets and maintain a versioned brand manifest. The supplied PNGs are **reference assets**, not proof of exact original vector geometry or official hexadecimal swatches.

### 3.2 Brand palette

The current TRUSTSEAL stylesheet defines `#0F3B82` and `#0E664D`. Use these as the provisional UI token baseline because they are repository-confirmed. The images also depict deep navy and green, but exact sampled artwork colors require source-asset approval before declaring a master brand palette.

| Token | Provisional value | Intended use |
|---|---|---|
| `--ts-brand-primary` | `#0F3B82` | Primary actions, selected links, essential product chrome |
| `--ts-brand-primary-hover` | `#0C2E66` | Hover/pressed brand action |
| `--ts-brand-primary-soft` | `#EEF3FA` | Very limited selected-row and focus context, not decorative pills |
| `--ts-brand-green` | `#0E664D` | Brand check, verified/success emphasis |
| `--ts-green-soft` | `#EAF5F0` | Modest success details only |
| `--ts-canvas` | `#F6F8FB` | Main application canvas |
| `--ts-surface` | `#FFFFFF` | Forms, tables, panels |
| `--ts-text` | `#172536` | Default text |
| `--ts-text-muted` | `#526174` | Metadata and help text |
| `--ts-border` | `#E1E6ED` | Simple section boundaries |
| `--ts-border-strong` | `#BCC6D2` | Interactive controls where boundaries are needed |
| `--ts-danger` | `#9E2F36` | Rejection, invalid, material risks |
| `--ts-warning` | `#835A0C` | Warning, pending attention |
| `--ts-focus` | `#3778D4` | Keyboard focus outline |

These proposed colors are a starting point, not a replacement for brand sign-off. The warning and danger colors are **semantic utility colors**, not new primary brand colors. Each text/background pair must pass contrast tests before release.

### 3.3 Typography

Use the VitalReturns design-system approach to typography rather than copying legacy template-local font rules. **Inter** is confirmed as the self-hosted UI font in the inspected VitalReturns token file; TRUSTSEAL may use licensed/self-hosted Inter with `Arial, sans-serif` fallback. If Vitalworks has an approved TRUSTSEAL typography master, it takes precedence over this recommendation. Never substitute a generic stylized font for the supplied logo wordmark.

| Role | Desktop size | Weight | Guidance |
|---|---:|---:|---|
| App page title | 24px | 600 | One H1 per page, no giant greeting banners |
| Primary section heading | 18px | 600 | Unambiguous hierarchy |
| Subsection heading | 16px | 600 | Panels and forms |
| Main body / table | 14px | 400–500 | Dense but readable |
| Input labels | 13–14px | 500–600 | Always visible, not placeholder-only |
| Secondary metadata | 12–13px | 400 | Use good contrast |
| Numeric counters | 22–28px | 600 | Only when numbers aid operational decisions |
| Verification hashes | 12–13px | 400 monospace | Break long strings and provide copy action |

Never use all caps for long headings. Short uppercase navigation section labels are acceptable. Long identifiers should be selectable and copyable, with tooltips or explicit copy feedback.

### 3.4 Geometry and spacing

Use spacing increments of 4px with 8px as the normal rhythm: `4, 8, 12, 16, 20, 24, 32, 40`. Desktop content padding is 24px, tablet 20px and mobile 16px. Buttons and text inputs use 36–40px heights in desktop density and at least 44px touch targets where practical on mobile. Default table rows are 40–44px; allow a comfortable density preference for users who need it.

Most surfaces should have 0–4px corner radius. Avoid pill shapes as the default. Borders should be reserved for meaningful containment, section boundaries and controls. Prefer headings and whitespace over stacks of bordered cards. Use little or no shadow; an overlay may use a restrained shadow only to make its layering clear.

## 4. Overall application architecture

### 4.1 Universal authenticated shell

The application shall share one shell comprising a 56px topbar, collapsible left navigation, fluid work region and optional contextual inspector. The topbar shows the approved logo, workspace/organization switcher where authorized, global search, create menu, notifications, help and account menu. The sidebar contains product navigation and may collapse to a compact icon rail. The content area has a page title, short description if necessary, contextual primary action and breadcrumb when navigation depth warrants it.

Recommended desktop initial sidebar width is **256px** with resizable width between 232px and 320px, persisted per user. Unlike VitalReturns' documented 320px default, TRUSTSEAL can adopt a narrower starting width because its menu labels are shorter. Below tablet breakpoints, show the navigation as an accessible drawer. Do not create separate shells for each business module.

```text
+---------------------------------------------------------------------------------------+
| TRUSTSEAL [workspace]           Search                         +New  Alerts  Account |
+-----------------------+---------------------------------------------------------------+
| WORKSPACE             | Documents / Contracts                [Upload document]          |
| Overview              | Manage documents, requests and evidence                         |
| Documents             |---------------------------------------------------------------|
| Signature Requests    | Filters: Status [All]  Owner [All]  Search [___________]       |
| Stamps                |---------------------------------------------------------------|
| Verification          | Document         Owner        Status       Updated        ...   |
| Evidence & Audit      | Master NDA       Legal        In review    12 Nov         ...   |
|                       | Supplier terms   Procurement  Signed       11 Nov         ...   |
| ADMINISTRATION        | ...                                                           |
| Organizations         |---------------------------------------------------------------|
| Users & Access        | [Selected item details appear in right inspector when opened]   |
| Templates             |                                                               |
| Integrations          |                                                               |
| Billing               |                                                               |
| Audit & Security      |                                                               |
+-----------------------+---------------------------------------------------------------+
```

This schematic defines information hierarchy, not a requirement for boxes around every region.

### 4.2 Product navigation

Navigation shall be based on actual authorized tasks, not backend blueprint names. The recommended top-level grouping is:

- **Workspace:** Overview, My Tasks, Documents, Signature Requests, Stamps, Verification, Evidence & Audit.
- **Management:** Document Templates, Contacts & Parties, Organizations/Clients (role-dependent), Team & Delegation.
- **Administration:** Users, Invitations, Roles & Permissions, Organizational Settings, Signature Profiles, Stamp Designs & Custody, Integrations & API, Subscriptions & Billing, System Audit & Security.
- **Public interfaces:** Verify a Document, Invited Signer/Reviewer, Trust & Security Information. These routes use their own lightweight public shell rather than exposing internal menus.

Do not display both “eSignatures” and “Signature Requests” as independent duplicated functions unless they represent documented distinct business objects. Prefer **Signature Requests** for orchestration and **Signature Profiles** for reusable identity/appearance settings. Similarly distinguish **Stamps**, **Stamp Designs** and **Custody** only when permissions and operations truly differ. Public verification should never require a workspace login unless a protected feature explicitly requires authentication.

### 4.3 Permission-aware navigation

Menus, toolbars, inline row actions and empty-state CTAs must reflect effective tenant, role, organization and object-level permissions. Hiding a control is not authorization; server policies remain the source of truth. Direct URLs to unauthorized resources must return appropriate responses without leaking existence, participants or document titles. Permission changes must take effect without stale UI exposure.

## 5. Shared component specification

Every module must consume the same shared components. When an existing component covers the requirement, a page must not define its own variant using inline styles. Required primitives include AppShell, Topbar, Sidebar, PageHeader, Breadcrumbs, SearchInput, CommandSearch, ActionToolbar, Button, IconButton, TextField, Textarea, Select, Combobox, Checkbox, RadioGroup, DatePicker, FileUploader, FilePreview, DocumentViewer, DataTable, FilterBar, Tabs, Accordion, EmptyState, ErrorSummary, Toast, InlineMessage, ConfirmationDialog, Modal, SidePanel, Stepper, Timeline, StatusText, CopyValue, EvidenceDetail, IdentitySummary and AuditEvent.

### 5.1 Buttons and menus

A screen has one unmistakable primary action. Secondary operations use outlined or text buttons. Destructive operations are visually distinct and require explicit confirmation where irreversible. The overflow menu shall group low-frequency actions without burying essential next steps. Disabled actions must explain the prerequisite in plain language; avoid tooltips as the only source of required explanation. Use consistent names such as “Send for signature”, “Verify document”, “Download evidence package”, “Revoke invitation”, and “Archive document”.

### 5.2 Tables and search

Operational lists shall provide server-side pagination, meaningful sorting, query filters, saved views where justified, bulk selection when safe, column visibility and export subject to permission. Every row should have a stable key and clear status, owner, date and next-action context. Row selection opens an inspector without discarding filters or scroll position. Use a full page only for tasks that require sustained work or editing. A long table must never force the whole page to scroll horizontally.

Search shall support relevant identifiers (document title, reference, envelope/request ID, party, organization), with secure scope enforcement. Empty search results must say what was searched and allow filter reset. Searching public verifier records must not allow identifier enumeration or unauthorized discovery.

### 5.3 Form behavior

All labels remain visible, field instructions appear before submission, and errors identify exactly what must be corrected. Use 1-column layouts for demanding workflows; a 2-column grid may be used for short compatible fields on desktop. Preserve entered state after non-destructive validation errors. Any auto-save must explicitly say when data is saved and what remains unsent. Uploads must validate file type, size, corruption and security rules without ambiguous failures.

### 5.4 Status system

Use a restrained text-first status system with clear terms and accessible icons. Distinguish process status from cryptographic assurance:

| Domain | Example values | Meaning |
|---|---|---|
| Document lifecycle | Draft, In review, Awaiting signatures, Completed, Archived | Business workflow status |
| Recipient decision | Pending, Viewed, Acknowledged, Declined, Expired | Recorded participant interaction |
| Cryptographic verification | Valid, Invalid, Untrusted, Indeterminate | Outcome for specific checked evidence and trust configuration |
| Stamp custody | Active, Suspended, Revoked, Expired | Operational authorization |
| Evidence availability | Preserved, Pending preservation, Retention due, Unavailable | Evidence handling state |

Never label a document “fully verified” solely because its visual checkmark is present or a platform seal exists. Show what was checked, against which evidence, at what time and under which trust assumptions. A successful business acknowledgment is not automatically an individual cryptographic signature.

### 5.5 Dialogs and side panels

Inspect metadata, participants, timelines and low-risk edits in a right panel; use a full page for extensive document editing, multi-party sequencing and PDF signing. Confirmation dialogs must name the affected object and consequence. Keyboard focus must enter and leave dialogs predictably. Background content is inert while a modal is open.

## 6. Page-by-page functional UI requirements

### 6.1 Public landing, trust information and authentication

The public landing should explain the product through its actual supported functions: document signing/review, organizational stamps, sealing and evidence-based verification. It should not claim legal accreditation, qualified-signature status or regulatory certification without evidence. Use a restrained hero, a concise product overview, transparent steps and distinct paths to “Verify a document” and “Sign in”. This is a marketing surface; avoid bringing hero patterns into the authenticated app.

Login, registration, password reset, invitations and MFA must use a consistent branded auth shell. Show password visibility control, session/device notices when applicable, recoverable validation errors, explicit organization context for multi-tenant users and accessible MFA methods. Account recovery must not disclose whether an unknown email exists.

### 6.2 Workspace overview

The overview is an operational command center, not a wall of promotional cards. It should present a short work queue (“Needs your signature”, “Awaiting others”, “Documents with review deadlines”), recent documents, pending stamp approvals and recent verification/evidence events. Only show metrics that map to a user decision. Each summary must be permission-filtered and linked to a correctly filtered list. Remove the current four equal-weight decorative dashboard cards as the principal information structure.

### 6.3 Documents library

A compact document register must support secure upload, creation from approved templates, search, filters and lifecycle actions. Recommended columns are Document, Reference, Owner, Parties, Lifecycle status, Last updated and Actions. The inspector shows exact document version, digest when applicable, permissions, participants, related requests, retention state and timeline. Distinguish editable drafts from immutable finalized versions. Preview must always indicate which version is being viewed; display a warning if subsequent edits invalidate the comparison to an earlier digest.

### 6.4 Document creation and structured editing

Use a guided workflow: document information, source/upload or template, parties, document content and sections, review, then release/signature preparation. Keep forms concise and reveal advanced options contextually. Preserve version history with explicit differences and meaningful authorship. Support autosave only if implemented with durable persistence and appropriate conflict handling; otherwise use a clear Save Draft action. Avoid implying that a draft is sealed or immutable.

### 6.5 Signature requests and envelope creation

Request creation must make the document version, intended participants, roles, sequence (parallel/sequential where supported), authentication requirements, due date, consent/intent text and notification schedule visible before sending. The final review page must display a human-readable summary and the exact version reference. “Send for signature” creates a clear event with outcome and audit reference; retry behavior must not create duplicate active requests.

A request detail page shall show participants, sequence, dispatch, viewed/acted timestamps, outstanding steps and acceptable cancellation/resend controls. Resends must not silently reset a signer decision or create unsupported proofs. Expiry, decline and replacement should have meaningful separate states.

### 6.6 Invited signer/reviewer journey

The invited experience must run without the internal application sidebar. It shows issuer identity (verified only to the extent supported), document title and version, a secure PDF viewer with zoom/page controls, clear consent text, explicit acknowledgment/decline decision and a final receipt. Optional drawn signature capture is labeled as a visual representation where that is the actual assurance tier; it must not be described as an individual cryptographic signature unless signer-held cryptographic endorsement is independently applied and validated.

On mobile, prioritize legible PDF review, page navigation, zoom, accessible signature alternatives and a sticky but unobtrusive action region. Distinguish expired, already-used, invalid and revoked invitation links without disclosing private data. Provide a download fallback when preview is unavailable, and do not allow a user to confirm a materially changed document without re-review.

### 6.7 Digital stamps

The stamp library shall separate **design**, **authorization/custody**, **application** and **usage history**. A stamp-design editor should support approved dimensions, text, emblem/logo, date line, signatory line, ink colors where allowed, official preview at realistic scale, proofing and version control. The viewer must not simulate a security guarantee merely through ornamental stamp appearance. Before application, display the document/version, stamp owner, authorized custodian, intended position, visible impression preview and final action consequence.

Custody screens show who can use a stamp, delegated rights, state, effective dates, revocations and application history. Every applied stamp should link to associated evidence. Protect against unauthorized recreation, changed templates and undocumented modification of an approved stamp design.

### 6.8 Public document verification

Verification is a first-class public service with a simple, standalone page. Support methods actually backed by APIs, including the repository-confirmed PDF plus evidence SHA-256 digest flow. A future code/QR or reference lookup is permitted only after its privacy and backend contract are established. The process is: choose verification method, provide proof inputs, run validation, review verdict and inspect/download available evidence.

The results page must clearly separate **document integrity**, **certificate/path trust**, **revocation/time evidence**, **signer or seal identity**, **signer intent evidence where applicable** and **overall result**. For unavailable checks, say “Not checked” or “Indeterminate”, not “Passed”. Expose check time and relevant identifiers with secure redaction; do not divulge unrelated organization records. Explain that verification can establish properties of bytes and evidence, not the truth of the document's underlying claims.

### 6.9 Evidence, audit and preservation

The Evidence Center should show accessible validation dossiers, timestamp evidence, audit-chain references, preservation state, proof bundles and retention events subject to authorization. A record detail includes event sequence, actor/service identity as authorized, document hash, correlation identifiers, timestamp, evidence type and integrity status. Export should clearly state bundle format, included records and a verifiable checksum. Audit event data must not be editable from the UI. When older evidence has been superseded, show preserved provenance and an explicit relationship rather than silently replacing it.

### 6.10 Organizations, users, roles and invitations

Administration pages require explicit current organization context, searchable users/teams, roles, access scopes and effective permissions. Invite-user workflows should show email, target organization, proposed role, expiry and invitation status. Role changes and permission grants require confirmation and durable audit records. Never expose a misleading capability merely because its menu item is visible. Organization switches must refresh scoped datasets and clear stale cross-tenant state.

### 6.11 Templates and party management

Template lists need owner, version, approval, activation and last-updated information. Editing a template must not mutate finalized documents or historic signed versions. Document parties should be selectable by verified contact records where appropriate, while allowing manual entry when policy permits. Clearly indicate whether an identity is asserted, verified, or only invited; do not imply verification from a populated email field.

### 6.12 Billing and subscriptions

Show active plan, usage units, entitlements, renewal/expiry date, invoice/payment history and any limits that affect workflows. Present clear upgrade or support paths without disrupting core verification access. Failed payment states must explain permitted continuing actions and document retention implications; avoid unverified promises regarding service continuity.

### 6.13 Integrations, developer API and webhooks

Administrators need integration overview, API credential lifecycle, scopes, webhook endpoints, event subscriptions, delivery results, retries and safe test controls. Secrets appear only at creation or authorized rotation and must never leak into HTML, telemetry or copied support diagnostics. Show endpoint health, last delivery and failure reasons without exposing sensitive payload data. API docs should be reachable from the product, with examples that match actual published OpenAPI contracts.

### 6.14 Platform settings and security

Settings shall be divided into organization, identity/security, document policy, stamp/signature policy, notifications, integrations, evidence retention and billing. Advanced settings live behind permission controls and explanatory copy. Potentially dangerous changes require strong confirmation and impact explanation. The admin UI must never present security checks as optional cosmetic toggles when server policy requires them.

## 7. Verification and assurance language requirements

The most serious UI failure in an integrity platform is overstating assurance. The interface must use precise language consistent with what the backend proves. For example, a platform-signed PDF can demonstrate that a platform certificate sealed the document; it does not automatically prove that every displayed human signatory cryptographically signed it. A drawn signature may be evidence of appearance or intent under a documented process, not independent PKI evidence. A visual organizational stamp is not a cryptographically trusted seal by itself.

Every verification or signing result shall therefore show: the claim tested, relevant evidence, observed result, limitations, timestamp, and where to obtain the audit record. When evidence is missing, stale, untrusted or blocked by policy, explicitly state the limitation and the next appropriate action. Terms such as “verified”, “qualified”, “certified”, “legally binding”, “tamper-proof” and “non-repudiation” must only appear in claims that are supported by the configured trust/legal framework and documented verification scope.

## 8. State model and error experiences

For all major screens, design and test loading, normal, empty, filtered-empty, error, permission-denied, expired, conflicting-update, partially successful and offline/interrupted states. Loading feedback must preserve layout and avoid flicker. Never display fabricated values while data is loading. Save/sign/apply operations need idempotency or safe retry semantics, with observable job status when asynchronous processing is involved. Errors should have a stable reference or correlation ID for support without exposing internal stack traces.

Examples of required messaging:

- **Signature request sent:** explain which recipients were notified and link to the request detail.
- **Verification indeterminate:** explain exactly which trust check could not complete and distinguish from a confirmed invalid signature.
- **Upload rejected:** state safe file limits, supported formats and retry instructions.
- **Stamp application rejected:** identify the authorization or document-state prerequisite without exposing unnecessary internal policy information.
- **Invitation expired:** provide a privacy-safe route to request a new invitation from the issuer.

## 9. Accessibility, responsive behavior and localization

Conform to **WCAG 2.2 AA** as a release acceptance target. All interactive controls need programmatic names; icons cannot carry meaning alone. Use semantic headings, visible labels, keyboard-operable menus, logical focus, announcement regions for completion/errors and visible focus outlines. Verify zoom/reflow, contrast, reduced motion, keyboard-only usage, screen-reader narration and high-contrast settings. PDF previews need accessible fallbacks and clear disclosure of viewer limitations.

Responsive breakpoints are implementation recommendations: wide desktop >= 1280px, desktop >= 1024px, tablet 768–1023px and mobile below 768px. At mobile sizes, forms stack, action bars wrap or dock responsibly, and tables switch to a task-focused compact row representation where horizontal data cannot be meaningfully preserved. Full-document inspection must remain possible. Side panels become full-screen or near-full-screen sheets with explicit close/navigation controls.

Store dates as properly typed data and render according to locale and account settings, including correct timezone indicators for legal/audit timestamps. Distinguish local display from canonical UTC record. Avoid embedding English strings in CSS or icon assets. Use locale-ready message resources even if English ships first.

## 10. Performance, security and resilience

The initial product shell should render without waiting for every dashboard metric. Paginate large lists at the server; avoid shipping thousands of records into the browser. Lazy-load PDF viewer and signature-pad code only on relevant screens. Use responsive assets, avoid oversized logos, and maintain accessible behavior on slow networks. Suggested performance acceptance: aim for LCP <= 2.5s and INP <= 200ms at the 75th percentile for representative supported network/device conditions, then calibrate production SLOs from measurement.

Do not introduce an entire new frontend framework solely for visual parity with VitalReturns. TRUSTSEAL currently uses Flask/Jinja, Bootstrap, AdminLTE, JavaScript, PDF.js and a signature-pad vendor module; a phased design-system migration is viable within this stack. Framework migration requires a separate documented architecture decision, including SSR/auth, session management, API stability, testing and operations.

Security-critical views must use CSRF protection where relevant, strict output encoding, content-security policy aligned with assets, safe attachment/download handling, authorization checks and audit logs. Review third-party CDN usage from the current base template and favor pinned, self-hosted assets where feasible for reliability and supply-chain control. Never expose raw secrets, internal private file paths, complete signing tokens or unrestricted hashes in public telemetry. Document-specific security messaging must be accurate for the configured deployment.

## 11. Implementation design tokens (starter CSS)

The following is an implementation starting point. It intentionally keeps TRUSTSEAL token names separate from VitalReturns `--vr-*` names. Expand with dark-mode and semantic token families only if those modes are actually supported and tested.

```css
:root {
  --ts-brand-primary: #0f3b82;
  --ts-brand-primary-hover: #0c2e66;
  --ts-brand-primary-soft: #eef3fa;
  --ts-brand-green: #0e664d;
  --ts-green-soft: #eaf5f0;
  --ts-canvas: #f6f8fb;
  --ts-surface: #ffffff;
  --ts-text: #172536;
  --ts-text-muted: #526174;
  --ts-border: #e1e6ed;
  --ts-border-strong: #bcc6d2;
  --ts-danger: #9e2f36;
  --ts-warning: #835a0c;
  --ts-focus: #3778d4;
  --ts-font: Inter, Arial, sans-serif;
  --ts-font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --ts-space-1: 4px;
  --ts-space-2: 8px;
  --ts-space-3: 12px;
  --ts-space-4: 16px;
  --ts-space-5: 20px;
  --ts-space-6: 24px;
  --ts-topbar-h: 56px;
  --ts-sidebar-w: 256px;
  --ts-radius: 3px;
}

.ts-app { background: var(--ts-canvas); color: var(--ts-text); font-family: var(--ts-font); }
.ts-page { padding: var(--ts-space-6); min-width: 0; }
.ts-page-title { margin: 0; font-size: 24px; font-weight: 600; line-height: 1.3; }
.ts-button-primary { background: var(--ts-brand-primary); color: white; border: 1px solid var(--ts-brand-primary); border-radius: var(--ts-radius); }
.ts-button-primary:hover { background: var(--ts-brand-primary-hover); }
.ts-input { min-height: 38px; border: 1px solid var(--ts-border-strong); border-radius: var(--ts-radius); background: var(--ts-surface); }
.ts-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.ts-table th, .ts-table td { padding: 10px 12px; border-bottom: 1px solid var(--ts-border); text-align: left; }
:where(button, a, input, select, textarea, [tabindex]):focus-visible { outline: 2px solid var(--ts-focus); outline-offset: 2px; }
@media (max-width: 767px) { .ts-page { padding: 16px; } .ts-page-title { font-size: 21px; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }
```

Avoid shipping this CSS in parallel with competing inline page colors. The final architecture must move styles into tested component definitions and one authoritative token stylesheet.

## 12. Proposed project organization and code migration

Keep server routes and security policies intact while changing the presentation layer. A recommended structure is:

```text
app/
  static/
    brand/trustseal/             # approved vector/raster lockups and manifest
    css/
      tokens.css                 # canonical design tokens
      reset.css
      shell.css
      components.css
      forms.css
      tables.css
      public.css
      trustseal.css              # thin compatibility entry point during migration
    js/
      shell.js
      components/
      documents/
      verification/
      signing/
      stamps/
  templates/
    layouts/
      app.html
      public.html
      signer.html
    components/
      page_header.html
      data_table.html
      form_field.html
      status_text.html
      confirmation_dialog.html
      evidence_summary.html
    pages/
      overview/
      documents/
      signature_requests/
      stamps/
      verification/
      evidence/
      administration/
      billing/
```

This is a target organization; do not rename existing paths without a verified route/template migration plan. Preserve all route names consumed by backend tests or external integrations unless compatibility redirects/aliases are documented. Extract shared components from existing templates first, then migrate modules incrementally. Retire AdminLTE assets only after the replacement shell, menus and accessibility behavior are demonstrated and regression-tested. Do not leave two visual systems active indefinitely.

### 12.1 Phased execution

**Phase 0 — Inventory and contracts.** Build a route/template map; identify active vs dead views; compare backend endpoints and permissions; catalogue all CSS, vendor assets and form patterns; inventory brand assets; record baseline screenshots and accessibility findings.

**Phase 1 — Foundations.** Approve brand source assets and tokens, establish typography, shell, page headers, navigation, responsive behavior and common component library. Add screenshot and accessibility regression tests before migrating business screens.

**Phase 2 — Core workspace.** Migrate dashboard, documents, document details, drafts, templates and parties. Validate data tables, filters, list-to-detail navigation and permission behavior.

**Phase 3 — High-trust journeys.** Migrate signature request creation, signer review, PDF viewer, stamps and public verifier. Prioritize semantic correctness, accessibility, state machines, confirm/retry handling and evidence presentation.

**Phase 4 — Governance surfaces.** Migrate organizations, users, roles, integrations, billing, settings, logs, preservation and custody. Align all controls with real API authorization and audit contracts.

**Phase 5 — Cleanup and hardening.** Remove duplicate templates/styles, unreferenced AdminLTE artifacts, placeholder routes and dead UI flows. Complete end-to-end tests, documented sign-off, performance measurement and production rollout criteria.

## 13. Requirement register

Requirements below are normative for the target system. IDs should be entered into the project tracker and linked to code, automated tests and visual acceptance evidence.

| ID | Priority | Requirement | Verification |
|---|---|---|---|
| TS-UI-001 | MUST | One authenticated application shell for all modules | Screenshots and template audit |
| TS-UI-002 | MUST | Canonical semantic tokens, no duplicated page-specific primitive styles | Static analysis and component review |
| TS-UI-003 | MUST | Approved TRUSTSEAL artwork unchanged | Brand source comparison |
| TS-UI-004 | MUST | Flat UI, no gradients/decorative AI chips | Visual review |
| TS-UI-005 | MUST | Responsive, no page-wide horizontal overflow | Multi-viewport browser tests |
| TS-UI-006 | MUST | WCAG 2.2 AA target | axe-core, manual keyboard and screen-reader tests |
| TS-UI-007 | MUST | Permission-aware navigation and server enforcement | Auth matrix tests |
| TS-UI-008 | MUST | Every visible menu reaches a real route or is removed | Route/link crawler |
| TS-UI-009 | MUST | Search, filters and data table state retention | Integration tests |
| TS-UI-010 | MUST | Explicit document version and lifecycle | End-to-end document tests |
| TS-UI-011 | MUST | Signature participant decision and assurance distinguished | Copy review and signer tests |
| TS-UI-012 | MUST | Public verifier details each evidence check and limitation | Verdict matrix tests |
| TS-UI-013 | MUST | Stamp authorization, design and usage separated | Custody and application tests |
| TS-UI-014 | MUST | Immutable audit events visible under authorization | Evidence access tests |
| TS-UI-015 | MUST | Secure upload/preview/download behaviors | Security tests |
| TS-UI-016 | MUST | Loading, empty, error, expiry and retry states | UI state test suite |
| TS-UI-017 | MUST | No misleading assurance or legal claims | Security/legal copy audit |
| TS-UI-018 | MUST | Responsive signer PDF workflow with fallback | Mobile end-to-end tests |
| TS-UI-019 | MUST | Proper keyboard focus, announcements and feedback | Accessibility manual tests |
| TS-UI-020 | MUST | Multi-tenant context isolation | Tenant-crossing security tests |
| TS-UI-021 | SHOULD | Reusable contextual inspector on document/record lists | UX interaction tests |
| TS-UI-022 | SHOULD | Saved views for operational tables | Feature tests |
| TS-UI-023 | SHOULD | Command/global search | Keyboard and search tests |
| TS-UI-024 | SHOULD | Density preference for operational lists | Preference persistence test |
| TS-UI-025 | MUST | Removal of legacy duplicate UI after full regression | Dependency and dead-code audit |
| TS-UI-026 | MUST | All release claims trace to actual working backend features | Capability checklist |
| TS-UI-027 | MUST | Safe handling of inaccessible/expired invitation links | Signed-link abuse tests |
| TS-UI-028 | MUST | Timestamp timezone and evidence source clarity | Date/locale test matrix |
| TS-UI-029 | MUST | Stable, observable failure states with correlation IDs | Monitoring and E2E checks |
| TS-UI-030 | SHOULD | Component gallery/style documentation | Design-system review |

## 14. Quality assurance and release gates

The UI is acceptable for release only when its required screens work end to end under relevant roles, tenants and document states. Create a screenshot baseline at 1440px, 1024px, 768px and 390px widths, then manually inspect high-risk workflows. Use Playwright with axe-core for representative journeys: login/MFA, document upload, signature request, signer review, stamp application, public PDF verification, evidence dossier and organization switching.

Record functional checks for valid, invalid, mismatched, untrusted, revoked, expired and indeterminate verification outcomes wherever corresponding backend verdicts exist. Test safe retry after network interruption and duplicate submission, revocation effects, permissions and data scope. No page should require hidden knowledge of backend identifiers to complete ordinary user tasks. Do not declare 100% UI completion based solely on static template checks.

Release gates must include: approved branding, complete navigation, functional role matrix, accessibility evidence, browser and mobile tests, clear verification language, screenshot regression, no console errors in primary journeys, performance measurements, security review and documented owner sign-off. A separate legal review is required before advertising regulatory or qualified trust statuses.

## 15. Acceptance scenarios

**Scenario A — A document owner uploads an agreement.** The user opens Documents, uploads a supported PDF, provides required metadata, sees the saved draft and its current version, invites permitted participants, reviews the request summary and sends it once. The list and document detail correctly reflect subsequent recipient actions.

**Scenario B — A recipient signs/reviews from a secure invitation.** A recipient opens a single-use link, verifies the document context, can inspect and download the correct PDF, reviews the consent language, makes an explicit decision and obtains a receipt. A drawn signature, if supplied, is not mislabeled as cryptographic proof. Reuse of an expired or consumed link is handled safely.

**Scenario C — A third party verifies a sealed PDF.** A verifier uses the public page without an internal account, supplies the PDF and required evidence digest, and receives a clearly classified result. The result shows which integrity and certificate checks succeeded or failed, identifies checks not performed, and does not reveal private tenant data.

**Scenario D — An administrator manages stamp custody.** An authorized custodian views an approved stamp design, checks its rights and validity, applies it to the correct version and sees usage evidence. A user without rights cannot perform the same action, whether through the UI or by direct API request.

**Scenario E — An auditor inspects evidence.** An authorized auditor filters events, opens a dossier, reviews identifiers and timestamp provenance and exports a controlled proof package. No UI interaction edits historical audit evidence.

## 16. Outstanding decisions and dependencies

Before implementation, confirm the official vector master and palette of the supplied logo; the approved default font; whether TRUSTSEAL public marketing is hosted in the same Flask app; the canonical route and permission registry; support for QR/reference-based verification beyond PDF/digest verification; the legal/assurance terminology approved for deployment; evidence retention/export policy; and whether advanced tenant/workspace functionality is enabled for each subscription level. These are explicit decisions, not permissions to defer the core redesign.

Also confirm the existing backend's API coverage for each proposed UI. Features beyond the current contract must be tagged **planned**, not presented as implemented. The repository's remaining-gap document states that browser-level accessibility testing still needs implementation; treat this as a mandatory UI work item rather than relying exclusively on static HTML assertions.

## 17. Definition of done

TRUSTSEAL's UI redesign is complete when users can move among all authorized functions through one coherent shell; every page uses approved brand artwork and semantic design tokens; documents, signing, stamps, verification and evidence are fully understandable without insider knowledge; all actions accurately reflect actual backend guarantees; mobile and keyboard users can complete core journeys; legacy styles and placeholder links are removed; and test evidence supports each mandatory requirement. The desired result is **a trustworthy and efficient enterprise workbench**, not simply a more attractive dashboard.

---

### Source URLs

- <https://github.com/socaya/trustseal/blob/main/app/templates/base.html>
- <https://github.com/socaya/trustseal/blob/main/app/templates/partials/sidebar.html>
- <https://github.com/socaya/trustseal/blob/main/app/static/css/trustseal.css>
- <https://github.com/socaya/trustseal/blob/main/app/templates/dashboard.html>
- <https://github.com/socaya/trustseal/blob/main/app/templates/trust/verify.html>
- <https://github.com/socaya/trustseal/blob/main/app/templates/envelopes/sign/review.html>
- <https://github.com/socaya/trustseal/blob/main/docs/REMAINING_GAPS_2026-11-15.md>
- <https://github.com/vitalworks-limited/vitalreturns/blob/main/plans/v2.2-ui-standardization.md>
- <https://github.com/vitalworks-limited/vitalreturns/blob/main/plans/docs/v2.0.0/VitalReturns_UI_UX_Components_Requirements_v2.0.md>
- <https://github.com/vitalworks-limited/vitalreturns/blob/main/source/styles/tokens.css>
- <https://github.com/vitalworks-limited/vitalreturns/blob/main/source/app/globals.css>

**Document control:** This specification is derived from the inspected repository state and user-supplied brand references as of 15 November 2026. It does not itself change repository code or imply that every defined requirement is implemented.
