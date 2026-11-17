# TrustSeal Documents — Ribbon and Rulers UI Design Specification

**Product:** TrustSeal Documents · Vitalworks Limited  
**Design status:** UI reference and interactive browser prototype  
**Design direction:** Ultra-compact corporate document editor; flat styling; thin, precise rulers; keyboard-accessible security controls; no gradients, exaggerated rounding, decorative chips or unnecessary outlines.

## 1. Layout hierarchy

The main editor uses six predictable regions in this order:

1. **Application bar (47 px):** TrustSeal Documents logo/identity, document title, save state, version history, comments and primary Share action.
2. **Ribbon tabs (38 px):** File, Home, Insert, Layout, References, Review and View, with a restrained brand-color underline under the active tab.
3. **Context ribbon (111 px):** Clearly grouped commands with quiet dividing rules and group labels at the bottom. Horizontal overflow is permitted on narrow screens; the document canvas must not acquire unwanted horizontal scroll from ribbon content.
4. **Measurement controls (34 px):** Toggle rulers, toggle margin guides, select centimeters/inches, change zoom and inspect page format.
5. **Document canvas:** Centered A4 page in a neutral light-gray workspace, horizontal ruler immediately above the page and vertical ruler along its left edge.
6. **Status bar (27 px):** Page number, page dimensions, word count and view mode.

## 2. Ribbon specification

### Ribbon tabs

| Tab | Required groups | Primary actions |
| --- | --- | --- |
| File | Document, History | New, Open, Save, Save As, Import, Export, Print, Version History, Properties |
| Home | Clipboard, Font, Paragraph, Styles, Editing | Paste, Copy, Cut, Undo, Redo, font family and size, bold, italic, underline, colors, alignment, lists, indentation, headings, find and replace |
| Insert | Content, Pages, Structure, Trust | Tables, images, links, shapes, header, footer, page break, page number, signature field, stamp field |
| Layout | Page Setup, Paragraph, Arrange | A4/Letter/Legal, orientation, margins, columns, page/section breaks, paragraph indents and spacing |
| References | Contents, Notes, Citations | Table of contents, footnotes, endnotes, citations, cross-references, captions |
| Review | Comments, Changes, Approvals | Comment, resolve, track changes, accept/reject edits, compare, request review, submit for approval |
| View | Views, Show, Zoom | Print layout, page/outline modes, rulers, margin guides, navigation pane, zoom to page/width |

Keep **Sign**, **Seal**, **Verify**, **Approve** and **Archive** as contextual, permission-controlled actions. They must call the existing TrustSeal trust and workflow services rather than independently mutating document signatures or records.

### Visual standards

- **Tab typography:** Arial or the approved TrustSeal brand font, approximately 12–13 px; active tab weight 700.
- **Ribbon command labels:** 10–11 px; icons 16–20 px; compact group spacing.
- **Command icons:** one consistent outline icon family; do not mix filled and outline families.
- **Ribbon surface:** white, with one subtle bottom border. Groups separated by a faint vertical divider only where useful.
- **Primary brand accent:** restrained professional blue (`#215B82` in the standalone mockup); final colors must adopt the approved TrustSeal brand tokens.
- **Hover/selected state:** pale neutral or lightly tinted surface; clear focus outline for keyboard access.
- **Responsive behavior:** do not squash commands; allow horizontal ribbon scrolling, collapse low-frequency commands into a More menu, or show an alternate compact toolbar.
- **Action availability:** permission/state rules must determine active, disabled and absent commands. Signed or immutable document versions must not expose editing commands as if they could change the signed bytes.

## 3. Horizontal ruler design

- Place a **18–19 px tall** ruler directly above the A4 page, width exactly matching the page canvas.
- Support **centimeters and inches** with real unit conversions.
- For an A4 portrait page, show 21 cm across the full width; the horizontal ruler must represent the whole page, not merely the text area.
- Show **major numeric labels** at 1 cm intervals, intermediate ticks at 0.5 cm and small ticks at 0.25 cm. Inch mode may show major inch labels and fractional subdivisions.
- Draw the current **left and right margin regions** with a restrained gray background.
- Display accessible, keyboard-operable **left margin, right margin, first-line indent, hanging indent and tab-stop markers** when editing permits them.
- Display a vertical alignment guide through the page only while a marker is being adjusted.
- Snap positions to configurable increments, with a numeric popover for exact entry and undo/redo support.

## 4. Vertical ruler design

- Place a **18–19 px wide** ruler against the left edge of the document page, matching the full page height.
- An A4 page displays 29.7 cm vertically, with major and minor ticks using the same measurement scale as the horizontal ruler.
- Distinguish the **top and bottom margins** with a restrained gray background.
- Display margin indicators and optional guides; drag-based adjustments should obey section/page layout constraints.
- When a document contains multiple pages, show a correctly aligned vertical measurement reference for the active page instead of presenting one continuous ruler as if it covered every page.

## 5. Page, margins and ruler alignment

Default page profile:

| Property | Initial value |
| --- | --- |
| Page | A4 portrait |
| Physical dimensions | 210 × 297 mm |
| Page width at 96 CSS px/in | Approximately 794 px |
| Page height at 96 CSS px/in | Approximately 1123 px |
| Left/right margin | 20 mm default; configurable |
| Top/bottom margin | 25 mm default; configurable |
| Measurement units | Centimeters initially; inches optional |
| Background | White page on a light neutral workspace |
| Shadow | Very subtle page shadow, no decorative card styling |

**Implementation invariant:** Ruler tick positions, page coordinates, layout dimensions, margin guides and draggable controls must all use the **same normalized document coordinate system**. Scaling/zoom must transform them together; do not compute ruler pixels separately from page-layout pixels.

## 6. Interaction behavior

- Ribbon tabs change the command groups without moving or resizing the document canvas unnecessarily.
- The active tab and toggle state persist during a local editing session.
- Rulers can be shown or hidden separately from margin guides.
- Unit changes update tick labels, tooltips and numeric inputs without physically changing document layout.
- Zoom scales the page, rulers, guides and overlays together; the source document's physical page dimensions remain unchanged.
- Margin and indentation changes modify the **editable document model** and enter the undo history; they must not directly modify an existing signed PDF.
- Measurement popovers accept exact values and enforce valid page geometry.
- Tooltips show the action name and keyboard shortcut where available.
- Save state must distinguish saving, saved, offline and failed; avoid fake 'saved' confirmations in production.
- Accessibility: buttons, menu semantics and ruler markers must be keyboard accessible with visible focus, meaningful labels and screen-reader feedback.

## 7. Security and document states

| Document state | Ribbon behavior | Ruler behavior |
| --- | --- | --- |
| Editable draft | Full authorized editing controls | Display and edit permitted margins, tabs and indents |
| In review | Editing according to workflow policy | Display; edit only where allowed |
| Awaiting signature | Editing typically locked to the frozen version | Display only |
| Signed or sealed | Verification, share, download, evidence and supersession controls | Display only; never rewrite signed page geometry |
| Archived or held | Read and authorized records controls | Display only |

A document may be transformed into an **explicit new derivative or version** only through a governed workflow; the original evidence must remain immutable.

## 8. Prototype limitations

The accompanying HTML prototype demonstrates responsive ribbons, selectable tabs, font/paragraph controls, measurement units, margin guides, a ruler-aligned A4 page and basic draft text editing. It is **not** the TrustSeal production editor. Several commands intentionally show explanatory placeholders. It does not include a real collaborative document engine, secure autosave, access control, signature issuance, pagination engine or production-grade draggable ruler markers.

### Artifact

- `TrustSeal_Documents_Ribbon_Rulers_Prototype.html` — open locally in a modern browser; no external assets or services required.


## Compact enterprise revision — refined prototype

The refined standalone HTML prototype uses a 38 px application bar, 30 px ribbon tabs, 70 px tool ribbon, 27 px measurement controls, 18–19 px ruler dimensions and a 24 px status bar. It retains the original tab sequence and adds a contextual **Security** tab and Security control in the application bar. The horizontal and vertical ruler ticks are hairline-weight, numbered sparingly, and retain correct A4 proportion, margin regions and centimeter/inch selection. Commands are tightened, not removed. On narrow screens, scroll within the ribbon rather than causing page horizontal overflow.

### Security interface — mandatory backend design requirements

| ID | Security capability | Implementation and verification requirement |
|---|---|---|
| SEC-01 | Classification | Public, Internal, Confidential, Restricted; persist on version and document; authenticated policy transitions |
| SEC-02 | Protected editing | Freeze immutable/signed versions server-side; read-only UI is supplementary and cannot be trusted by itself |
| SEC-03 | User permissions | Tenant-isolated RBAC and ABAC per document, version, workspace and action |
| SEC-04 | Secure sharing | Expiring grants, optional OTP/MFA, recipient-bound access, revocation and audited sharing |
| SEC-05 | Export restrictions | Enforce export, download, print, watermark, bulk export and classification policies on backend |
| SEC-06 | Integrity | SHA-256 source/version fingerprints, integrity rechecks at ingestion and export, immutable finalized evidence |
| SEC-07 | Encryption | TLS in transit, authenticated encryption at rest, per-tenant key isolation or key hierarchy, rotation |
| SEC-08 | Key custody | HSM/KMS for high-assurance signing and encryption keys, separate operators, recovery policy |
| SEC-09 | Audit | Append-only events with actor/time/version/action/context, tamper detection and retention controls |
| SEC-10 | Malware controls | File type validation, antivirus scanning, isolated conversions and sanitized previews |
| SEC-11 | Privacy mode | Optional local display concealment (not encryption); never claim screenshot blocking in ordinary browsers |
| SEC-12 | Document sensitivity | Apply confidentiality labels, DLP rules and redaction with enforcement across search and notifications |
| SEC-13 | Authentication | MFA and step-up authentication for high-impact actions; service account scopes for APIs |
| SEC-14 | Data lifecycle | Legal hold, retention lock, version supersession, secure disposal and preserved evidence packages |
| SEC-15 | Verification | Cryptographic verification and timestamp/certificate evidence status; distinguish partial assurance from PAdES-LT/LTA |

### Prototype limitations

The Security panel's classification, protect-edit and privacy toggle controls operate **only within the open HTML preview**. They do not save to a server, encrypt documents, enforce tenant permissions, stop screenshots, create audit events or provide cryptographic integrity. Real TrustSeal services must implement every protected operation in the backend and enforce policy on every API. Do not use UI toggles as security boundaries.
