"""Built-in TSD template library.

The real templates feature (DOC-099 — DOC-111) will store tenant-owned
templates in a database table with authoring, approval, versioning,
retirement and placeholder substitution. This module ships the v1
reduction: a curated set of hard-coded templates that give new users
something real to open instead of a blank page.

Each template is a self-contained HTML body that the editor's
contenteditable surface renders verbatim. Placeholders use the
``{{variable}}`` convention so the Insert ▸ Field tool and later
template-substitution engine can share the same marker.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TsdTemplate:
    slug: str
    name: str
    description: str
    category: str   # Agreement / Correspondence / Governance / Report / Policy
    title: str      # pre-filled document title
    tags: str       # comma-separated default tags
    body_html: str  # HTML body for the editor


_ATAG = (
    '<span style="background:#eef3fa;color:#0f3b82;border:1px solid #cfdcef;'
    'padding:1px 6px;border-radius:3px;font-family:monospace;font-size:10pt;">'
)


def _field(name: str) -> str:
    """Render a ``{{name}}`` field chip in the template body."""
    return f"{_ATAG}{{{{{name}}}}}</span>"


_TEMPLATES: list[TsdTemplate] = [
    TsdTemplate(
        slug="services-agreement",
        name="Services Agreement",
        description="Master services agreement with scope, compensation, term and signature block.",
        category="Agreement",
        title="Services Agreement",
        tags="legal, services, contract",
        body_html=f"""
<h1>SERVICES AGREEMENT</h1>
<p>This Services Agreement (the "Agreement") is entered into as of {_field('effective_date')}
   between {_field('provider_name')} (the "Provider") and
   {_field('client_name')} (the "Client").</p>

<h2>1. Scope of Services</h2>
<p>The Provider shall perform the services described in {_field('statement_of_work')}
   (the "Services"). The parties may add, remove, or modify Services only by
   mutual written agreement.</p>

<h2>2. Compensation</h2>
<p>The Client shall pay the Provider {_field('fee_amount')} on the terms set forth in
   {_field('payment_schedule')}. Invoices are due net thirty (30) days from issue.</p>

<h2>3. Term and Termination</h2>
<p>This Agreement begins on the Effective Date and continues until
   {_field('end_date')} unless terminated earlier under this Section 3.
   Either party may terminate for material breach on thirty (30) days' written
   notice if the breach remains uncured after that period.</p>

<h2>4. Confidentiality</h2>
<p>Each party shall protect the other's Confidential Information with no less
   than reasonable care and shall not disclose it except to perform this
   Agreement. This obligation survives termination for three (3) years.</p>

<h2>5. Governing Law</h2>
<p>This Agreement is governed by the laws of {_field('jurisdiction')}, without
   regard to conflict-of-law principles.</p>

<h2>6. Signatures</h2>
<div style="margin-top: 32pt; display: flex; gap: 40pt;">
  <div>
    <div style="border-bottom: 1px solid #121a26; width: 240pt; height: 36pt;"></div>
    <div style="font-size: 9pt; color: #5a6676;">{_field('provider_name')} — Provider</div>
  </div>
  <div>
    <div style="border-bottom: 1px solid #121a26; width: 240pt; height: 36pt;"></div>
    <div style="font-size: 9pt; color: #5a6676;">{_field('client_name')} — Client</div>
  </div>
</div>
""".strip(),
    ),

    TsdTemplate(
        slug="nda",
        name="Mutual NDA",
        description="Standard two-way non-disclosure agreement.",
        category="Agreement",
        title="Mutual Non-Disclosure Agreement",
        tags="legal, nda, confidentiality",
        body_html=f"""
<h1>MUTUAL NON-DISCLOSURE AGREEMENT</h1>
<p>This Mutual Non-Disclosure Agreement (this "NDA") is entered into as of
   {_field('effective_date')} between {_field('party_a')} ("Party A") and
   {_field('party_b')} ("Party B"). Each of Party A and Party B may be a
   Disclosing Party or Receiving Party under this NDA.</p>

<h2>1. Confidential Information</h2>
<p>"Confidential Information" means any non-public business, technical,
   financial, or operational information disclosed by one party to the other,
   whether orally, in writing, or by any other medium, and whether or not
   marked confidential.</p>

<h2>2. Obligations</h2>
<p>The Receiving Party shall (a) use Confidential Information solely to
   evaluate {_field('purpose')}, (b) protect it with the same degree of care
   it uses for its own confidential information (and in no event less than
   reasonable care), and (c) disclose it only to employees and advisors with a
   need to know who are bound by equivalent confidentiality obligations.</p>

<h2>3. Exclusions</h2>
<p>Confidential Information does not include information that (a) is or
   becomes publicly available without breach of this NDA, (b) was lawfully
   known to the Receiving Party before disclosure, (c) is independently
   developed without reference to the Disclosing Party's information, or
   (d) is received from a third party without restriction and without breach.</p>

<h2>4. Term</h2>
<p>This NDA begins on the Effective Date and continues for {_field('term_years')}
   years. The confidentiality obligations survive termination with respect to
   trade secrets for so long as they remain trade secrets.</p>

<h2>5. No License</h2>
<p>No license or other rights to any intellectual property are granted or
   implied by this NDA.</p>

<p style="margin-top: 32pt; color: #5a6676;">Signed by authorized representatives of
   both parties.</p>
""".strip(),
    ),

    TsdTemplate(
        slug="letter",
        name="Business Letter",
        description="Formal letter with sender address, date, recipient, subject and closing.",
        category="Correspondence",
        title="Official Correspondence",
        tags="correspondence, letter",
        body_html=f"""
<p>{_field('sender_name')}<br>
   {_field('sender_title')}<br>
   {_field('sender_organization')}<br>
   {_field('sender_address')}</p>

<p style="margin-top: 18pt;">{_field('date')}</p>

<p style="margin-top: 18pt;">{_field('recipient_name')}<br>
   {_field('recipient_title')}<br>
   {_field('recipient_organization')}<br>
   {_field('recipient_address')}</p>

<p style="margin-top: 18pt;"><strong>Re:</strong> {_field('subject')}</p>

<p style="margin-top: 18pt;">Dear {_field('recipient_salutation')},</p>

<p>Thank you for your {_field('reference')}. We have reviewed the matter and
   wish to share the following position.</p>

<p>{_field('body_paragraph_1')}</p>

<p>{_field('body_paragraph_2')}</p>

<p>Please do not hesitate to contact this office if you require any further
   clarification.</p>

<p style="margin-top: 24pt;">Yours sincerely,</p>

<p style="margin-top: 42pt;">{_field('sender_name')}<br>
   <span style="color:#5a6676; font-size:11px;">{_field('sender_title')}</span></p>
""".strip(),
    ),

    TsdTemplate(
        slug="memo",
        name="Internal Memo",
        description="Simple internal memo with To / From / Date / Subject header.",
        category="Correspondence",
        title="Internal Memorandum",
        tags="memo, internal",
        body_html=f"""
<h1>MEMORANDUM</h1>
<table style="border-collapse: collapse; margin: 16pt 0 24pt;">
  <tr><td style="padding: 4pt 16pt 4pt 0; color:#5a6676;"><strong>TO:</strong></td>
      <td style="padding: 4pt 0;">{_field('recipients')}</td></tr>
  <tr><td style="padding: 4pt 16pt 4pt 0; color:#5a6676;"><strong>FROM:</strong></td>
      <td style="padding: 4pt 0;">{_field('author_name')}, {_field('author_title')}</td></tr>
  <tr><td style="padding: 4pt 16pt 4pt 0; color:#5a6676;"><strong>DATE:</strong></td>
      <td style="padding: 4pt 0;">{_field('date')}</td></tr>
  <tr><td style="padding: 4pt 16pt 4pt 0; color:#5a6676;"><strong>SUBJECT:</strong></td>
      <td style="padding: 4pt 0;"><strong>{_field('subject')}</strong></td></tr>
</table>

<hr style="border: 0; border-top: 1px solid #c7ced6; margin: 12pt 0 18pt;">

<h2>Background</h2>
<p>{_field('background')}</p>

<h2>Discussion</h2>
<p>{_field('discussion_paragraph_1')}</p>
<p>{_field('discussion_paragraph_2')}</p>

<h2>Recommendation</h2>
<p>{_field('recommendation')}</p>

<h2>Next steps</h2>
<ul>
  <li>{_field('next_step_1')}</li>
  <li>{_field('next_step_2')}</li>
  <li>{_field('next_step_3')}</li>
</ul>
""".strip(),
    ),

    TsdTemplate(
        slug="board-resolution",
        name="Board Resolution",
        description="Corporate board resolution with recitals, resolutions and authorization.",
        category="Governance",
        title="Resolution of the Board of Directors",
        tags="governance, resolution, board",
        body_html=f"""
<h1>RESOLUTION OF THE BOARD OF DIRECTORS</h1>
<p style="text-align: center; color: #5a6676;"><strong>OF {_field('company_name')}</strong></p>
<p style="text-align: center; color: #5a6676;">Resolution No. {_field('resolution_number')} —
   Adopted on {_field('date')}</p>

<h2>Recitals</h2>
<p><strong>WHEREAS,</strong> the Board of Directors (the "Board") met on the date above and
   considered the matter of {_field('subject')}; and</p>

<p><strong>WHEREAS,</strong> after due deliberation the Board determined that it is in the
   best interests of the Company and its stakeholders to proceed as set forth
   below;</p>

<h2>Resolutions</h2>
<p><strong>NOW, THEREFORE, BE IT RESOLVED,</strong> that the Company shall
   {_field('resolution_1')};</p>

<p><strong>RESOLVED FURTHER,</strong> that {_field('resolution_2')};</p>

<p><strong>RESOLVED FURTHER,</strong> that any officer of the Company is hereby authorized
   and directed to take all actions and execute all documents necessary or
   appropriate to effectuate the foregoing resolutions.</p>

<h2>Certification</h2>
<p>I, the undersigned, {_field('secretary_name')}, Secretary of {_field('company_name')},
   certify that the foregoing resolutions were duly adopted by the Board on
   the date set forth above and have not been rescinded or modified.</p>

<div style="margin-top: 42pt;">
  <div style="border-bottom: 1px solid #121a26; width: 300pt; height: 36pt;"></div>
  <div style="font-size: 9pt; color: #5a6676;">{_field('secretary_name')} — Company Secretary</div>
</div>
""".strip(),
    ),

    TsdTemplate(
        slug="meeting-minutes",
        name="Meeting Minutes",
        description="Structured minutes with attendees, agenda, decisions and action items.",
        category="Governance",
        title="Meeting Minutes",
        tags="governance, minutes, meeting",
        body_html=f"""
<h1>MEETING MINUTES</h1>
<table style="border-collapse: collapse; margin: 12pt 0 18pt;">
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Meeting:</strong></td>
      <td style="padding:3pt 0;">{_field('meeting_name')}</td></tr>
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Date:</strong></td>
      <td style="padding:3pt 0;">{_field('date')}</td></tr>
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Time:</strong></td>
      <td style="padding:3pt 0;">{_field('start_time')} — {_field('end_time')}</td></tr>
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Location:</strong></td>
      <td style="padding:3pt 0;">{_field('location')}</td></tr>
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Chair:</strong></td>
      <td style="padding:3pt 0;">{_field('chair_name')}</td></tr>
  <tr><td style="padding:3pt 14pt 3pt 0; color:#5a6676;"><strong>Minute-taker:</strong></td>
      <td style="padding:3pt 0;">{_field('minute_taker_name')}</td></tr>
</table>

<h2>Attendees</h2>
<p>{_field('attendees')}</p>

<h2>Apologies</h2>
<p>{_field('apologies')}</p>

<h2>Agenda</h2>
<ol>
  <li>{_field('agenda_item_1')}</li>
  <li>{_field('agenda_item_2')}</li>
  <li>{_field('agenda_item_3')}</li>
</ol>

<h2>Discussion and Decisions</h2>
<p><strong>Item 1 — {_field('agenda_item_1')}:</strong> {_field('discussion_1')}</p>
<p><strong>Decision:</strong> {_field('decision_1')}</p>

<p><strong>Item 2 — {_field('agenda_item_2')}:</strong> {_field('discussion_2')}</p>
<p><strong>Decision:</strong> {_field('decision_2')}</p>

<h2>Action Items</h2>
<table style="border-collapse: collapse; width: 100%; margin: 6pt 0;">
  <tr style="background:#f1f2f5;">
    <th style="border: 1px solid #c7ced6; padding: 5pt 8pt; text-align: left;">#</th>
    <th style="border: 1px solid #c7ced6; padding: 5pt 8pt; text-align: left;">Action</th>
    <th style="border: 1px solid #c7ced6; padding: 5pt 8pt; text-align: left;">Owner</th>
    <th style="border: 1px solid #c7ced6; padding: 5pt 8pt; text-align: left;">Due</th>
  </tr>
  <tr>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">1</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_1')}</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_1_owner')}</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_1_due')}</td>
  </tr>
  <tr>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">2</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_2')}</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_2_owner')}</td>
    <td style="border: 1px solid #c7ced6; padding: 5pt 8pt;">{_field('action_2_due')}</td>
  </tr>
</table>

<h2>Next meeting</h2>
<p>{_field('next_meeting')}</p>
""".strip(),
    ),

    TsdTemplate(
        slug="policy",
        name="Policy Document",
        description="Organizational policy with purpose, scope, definitions and compliance.",
        category="Policy",
        title="Policy Document",
        tags="policy, governance",
        body_html=f"""
<h1>{_field('policy_name')}</h1>
<p style="color:#5a6676;">
   <strong>Policy No:</strong> {_field('policy_number')} ·
   <strong>Owner:</strong> {_field('owner_department')} ·
   <strong>Effective:</strong> {_field('effective_date')} ·
   <strong>Next review:</strong> {_field('review_date')}
</p>

<h2>1. Purpose</h2>
<p>This policy establishes {_field('purpose')}.</p>

<h2>2. Scope</h2>
<p>This policy applies to {_field('scope')}.</p>

<h2>3. Definitions</h2>
<ul>
  <li><strong>{_field('term_1')}</strong> — {_field('definition_1')}</li>
  <li><strong>{_field('term_2')}</strong> — {_field('definition_2')}</li>
</ul>

<h2>4. Policy Statements</h2>
<p>{_field('statement_1')}</p>
<p>{_field('statement_2')}</p>

<h2>5. Roles and Responsibilities</h2>
<p><strong>Policy Owner:</strong> {_field('owner_department')} is responsible for
   maintenance and interpretation of this policy.</p>
<p><strong>All Personnel:</strong> shall comply with this policy and promptly
   report deviations.</p>

<h2>6. Compliance and Enforcement</h2>
<p>Deviations from this policy may result in disciplinary action, up to and
   including termination of employment or engagement, and civil or criminal
   consequences where applicable.</p>

<h2>7. Related Documents</h2>
<p>{_field('related_documents')}</p>

<h2>8. Revision History</h2>
<table style="border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 11pt;">
  <tr style="background:#f1f2f5;">
    <th style="border:1px solid #c7ced6; padding:5pt 8pt; text-align:left;">Version</th>
    <th style="border:1px solid #c7ced6; padding:5pt 8pt; text-align:left;">Date</th>
    <th style="border:1px solid #c7ced6; padding:5pt 8pt; text-align:left;">Author</th>
    <th style="border:1px solid #c7ced6; padding:5pt 8pt; text-align:left;">Change</th>
  </tr>
  <tr>
    <td style="border:1px solid #c7ced6; padding:5pt 8pt;">1.0</td>
    <td style="border:1px solid #c7ced6; padding:5pt 8pt;">{_field('effective_date')}</td>
    <td style="border:1px solid #c7ced6; padding:5pt 8pt;">{_field('author_name')}</td>
    <td style="border:1px solid #c7ced6; padding:5pt 8pt;">Initial issue</td>
  </tr>
</table>
""".strip(),
    ),

    TsdTemplate(
        slug="blank",
        name="Blank document",
        description="Empty document — the clean slate.",
        category="Other",
        title="Untitled document",
        tags="",
        body_html="<p></p>",
    ),
]


def list_templates() -> list[dict]:
    """Return all templates as dicts (without body) for library listing."""
    return [
        {
            "slug": t.slug, "name": t.name, "description": t.description,
            "category": t.category, "title": t.title, "tags": t.tags,
        }
        for t in _TEMPLATES
    ]


def get_template(slug: str) -> TsdTemplate | None:
    for t in _TEMPLATES:
        if t.slug == slug:
            return t
    return None
