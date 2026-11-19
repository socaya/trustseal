"""Built-in TSD stamp templates.

A starter gallery of common stamp designs — pre-baked layout JSON +
rendered SVG — that users can instantiate as their own stamps and
then tweak in the Studio. Templates are tenant-free: every tenant
sees the same catalogue, and the ``POST /api/tsd-stamps/from-template``
endpoint copies the layout + SVG into a new ``TSDStamp`` row.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StampTemplate:
    slug: str
    name: str                 # suggested stamp name (editable before save)
    category: str             # Governance / Operations / Correspondence / Legal
    kind: str                 # seal | company_dated | date | rubber
    description: str
    layout: dict
    svg: str


# -- SVG helpers (kept inline so the file stays self-contained) ---------


def _seal_svg(*, top: str, bottom: str, center_lines: list[str], color: str,
              border: str) -> str:
    def arc(id_: str, text: str, r: int, side: str) -> str:
        if side == "top":
            d = f"M {-r} 0 A {r} {r} 0 0 1 {r} 0"
            tr = ""
        else:
            d = f"M {r} 0 A {r} {r} 0 0 1 {-r} 0"
            tr = 'transform="translate(0,20)"'
        return (
            f'<defs><path id="{id_}" d="{d}" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="18" font-weight="700" '
            f'letter-spacing="2" fill="{color}" {tr}>'
            f'<textPath href="#{id_}" startOffset="50%" text-anchor="middle">'
            f'{text.upper()}</textPath></text>'
        )

    if border == "double":
        outer = (
            f'<circle r="140" fill="none" stroke="{color}" stroke-width="3"/>'
            f'<circle r="128" fill="none" stroke="{color}" stroke-width="1"/>'
        )
    elif border == "dashed":
        outer = (
            f'<circle r="140" fill="none" stroke="{color}" '
            f'stroke-width="3" stroke-dasharray="6,4"/>'
        )
    else:
        outer = f'<circle r="140" fill="none" stroke="{color}" stroke-width="3"/>'

    cy0 = 6 if len(center_lines) == 1 else (-4 if len(center_lines) == 2 else -18)
    center = ""
    for i, line in enumerate(center_lines[:4]):
        y = cy0 + i * 24
        size = 14 if len(line) > 12 else 20
        center += (
            f'<text y="{y}" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{size}" font-weight="700" fill="{color}">'
            f'{line.replace("<", "&lt;")}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" '
        'width="160" height="160" data-stamp-root="1">'
        f'{outer}'
        f'{arc("tpl-top", top, 115, "top")}'
        f'{arc("tpl-bot", bottom, 115, "bottom")}'
        f'{center}'
        '</svg>'
    )


def _company_dated_svg(*, company: str, tagline: str, verb: str, color: str) -> str:
    def arc(id_: str, text: str, r: int, side: str) -> str:
        if side == "top":
            d = f"M {-r} 0 A {r} {r} 0 0 1 {r} 0"; tr = ""
        else:
            d = f"M {r} 0 A {r} {r} 0 0 1 {-r} 0"; tr = 'transform="translate(0,20)"'
        return (
            f'<defs><path id="{id_}" d="{d}" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="18" font-weight="700" '
            f'letter-spacing="2" fill="{color}" {tr}>'
            f'<textPath href="#{id_}" startOffset="50%" text-anchor="middle">'
            f'{text.upper()}</textPath></text>'
        )

    outer = (
        f'<circle r="140" fill="none" stroke="{color}" stroke-width="3"/>'
        f'<circle r="128" fill="none" stroke="{color}" stroke-width="1"/>'
    )
    verb_el = (
        f'<text y="-12" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="10" fill="{color}" letter-spacing="3">{verb.upper()}</text>'
    ) if verb else '<line x1="-70" y1="-14" x2="70" y2="-14" stroke="' + color + '" stroke-width="1"/>'
    date_el = (
        '<text y="18" text-anchor="middle" font-family="Courier New, monospace" '
        f'font-size="20" font-weight="700" fill="{color}">[DD MMM YYYY]</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" '
        'width="160" height="160" data-stamp-root="1">'
        f'{outer}'
        f'{arc("tpl-top", company, 115, "top")}'
        f'{arc("tpl-bot", tagline, 115, "bottom")}'
        f'{verb_el}{date_el}'
        '</svg>'
    )


def _date_svg(*, label: str, color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 170" '
        'width="200" height="106" data-stamp-root="1">'
        f'<rect x="4" y="4" width="312" height="162" fill="none" stroke="{color}" stroke-width="3" rx="4"/>'
        f'<rect x="12" y="14" width="296" height="40" fill="{color}"/>'
        f'<text x="160" y="42" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
        f'font-size="26" fill="#fff" letter-spacing="3">{label}</text>'
        f'<text x="160" y="100" text-anchor="middle" font-family="Courier New, monospace" '
        f'font-size="28" font-weight="700" fill="{color}">[DD MMM YYYY]</text>'
        f'<line x1="40" y1="130" x2="280" y2="130" stroke="{color}" stroke-width="1"/>'
        f'<text x="160" y="150" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="10" fill="{color}" letter-spacing="2">BY ____________________________</text>'
        '</svg>'
    )


def _rubber_svg(*, text: str, color: str, shape: str = "rect") -> str:
    if shape == "oval":
        outer = f'<ellipse cx="160" cy="70" rx="150" ry="55" fill="none" stroke="{color}" stroke-width="4"/>'
    elif shape == "rounded":
        outer = f'<rect x="10" y="15" width="300" height="110" rx="18" fill="none" stroke="{color}" stroke-width="4"/>'
    else:
        outer = f'<rect x="10" y="15" width="300" height="110" fill="none" stroke="{color}" stroke-width="4"/>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" '
        'width="200" height="88" data-stamp-root="1">'
        f'{outer}'
        f'<text x="160" y="85" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
        f'font-size="42" font-weight="900" fill="{color}" letter-spacing="4">{text}</text>'
        '</svg>'
    )


# -- Templates ----------------------------------------------------------


_TEMPLATES: list[StampTemplate] = [
    # Governance
    StampTemplate(
        slug="corporate-seal",
        name="Corporate Seal",
        category="Governance",
        kind="seal",
        description="Classic double-ring corporate seal with organization name on top arc, "
                    "registration or tagline below. Royal blue.",
        layout={
            "top": "COMPANY NAME LIMITED", "bottom": "INCORPORATED 2026",
            "center": ["★★★", "OFFICIAL", "SEAL"],
            "color": "#0f3b82", "border_style": "double",
            "size_value": "42", "logo_x": 0, "logo_y": 0,
            "logo_size": 95, "logo_opacity": 0.08, "logo_watermark": True,
        },
        svg=_seal_svg(
            top="COMPANY NAME LIMITED", bottom="INCORPORATED 2026",
            center_lines=["★★★", "OFFICIAL", "SEAL"],
            color="#0f3b82", border="double",
        ),
    ),
    StampTemplate(
        slug="notary-seal",
        name="Notary Public Seal",
        category="Governance",
        kind="seal",
        description="55 mm notary seal — single ring, state-style arc text, notary number "
                    "and jurisdiction in the center.",
        layout={
            "top": "NOTARY PUBLIC", "bottom": "JURISDICTION · COUNTRY",
            "center": ["[NAME]", "COMMISSION", "# 000000"],
            "color": "#9e2f36", "border_style": "single",
            "size_value": "55", "logo_x": 0, "logo_y": 0,
            "logo_size": 95, "logo_opacity": 0.08, "logo_watermark": True,
        },
        svg=_seal_svg(
            top="NOTARY PUBLIC", bottom="JURISDICTION · COUNTRY",
            center_lines=["[NAME]", "COMMISSION", "# 000000"],
            color="#9e2f36", border="single",
        ),
    ),
    StampTemplate(
        slug="university-seal",
        name="University Seal",
        category="Education",
        kind="seal",
        description="Classic university seal — 55 mm, double ring, monogram placeholder "
                    "in the centre with the motto arc. Deep purple.",
        layout={
            "top": "UNIVERSITY NAME", "bottom": "SAPIENTIA · VERITAS · MDCCCLXX",
            "center": ["★★★", "ALMA", "MATER"],
            "color": "#5b3a97", "border_style": "double",
            "size_value": "55", "dividers": "star",
            "center_style": "monogram", "monogram": "U",
        },
        svg=_seal_svg(
            top="UNIVERSITY NAME", bottom="SAPIENTIA · VERITAS · MDCCCLXX",
            center_lines=["★★★", "ALMA", "MATER"],
            color="#5b3a97", border="double",
        ),
    ),
    StampTemplate(
        slug="government-seal",
        name="Government Authority Seal",
        category="Government",
        kind="seal",
        description="Triple-ring government seal — 50 mm, dark green ink, "
                    "authority name on top, country on bottom, star dividers.",
        layout={
            "top": "GOVERNMENT AUTHORITY", "bottom": "REPUBLIC OF ____",
            "center": ["[OFFICIAL]", "SEAL"],
            "color": "#0e664d", "border_style": "triple",
            "size_value": "50", "dividers": "star",
        },
        svg=_seal_svg(
            top="GOVERNMENT AUTHORITY", bottom="REPUBLIC OF ____",
            center_lines=["[OFFICIAL]", "SEAL"],
            color="#0e664d", border="double",
        ),
    ),
    StampTemplate(
        slug="chamber-of-commerce-seal",
        name="Chamber of Commerce Seal",
        category="Governance",
        kind="seal",
        description="Business association seal — 50 mm, rope border, amber ink. "
                    "Chamber name on top, 'MEMBER' + year below.",
        layout={
            "top": "CHAMBER OF COMMERCE", "bottom": "ESTABLISHED YYYY",
            "center": ["MEMBER", "IN GOOD", "STANDING"],
            "color": "#b4821f", "border_style": "rope",
            "size_value": "50", "dividers": "diamond",
        },
        svg=_seal_svg(
            top="CHAMBER OF COMMERCE", bottom="ESTABLISHED YYYY",
            center_lines=["MEMBER", "IN GOOD", "STANDING"],
            color="#b4821f", border="single",
        ),
    ),
    StampTemplate(
        slug="nonprofit-seal",
        name="Nonprofit Seal",
        category="Governance",
        kind="seal",
        description="Nonprofit/foundation seal — scalloped border, 42 mm, red ink. "
                    "Organization name on top, mission tag below.",
        layout={
            "top": "FOUNDATION NAME", "bottom": "SINCE YYYY · 501(c)(3)",
            "center": ["★", "CHARITABLE", "MISSION"],
            "color": "#9e2f36", "border_style": "scalloped",
            "size_value": "42", "dividers": "sparkle",
        },
        svg=_seal_svg(
            top="FOUNDATION NAME", bottom="SINCE YYYY · 501(c)(3)",
            center_lines=["★", "CHARITABLE", "MISSION"],
            color="#9e2f36", border="single",
        ),
    ),
    StampTemplate(
        slug="medical-seal",
        name="Medical Practice Seal",
        category="Healthcare",
        kind="seal",
        description="Clinic / hospital seal — 45 mm, teal, double ring with inner "
                    "decorative circle. Practice name on top, specialty below.",
        layout={
            "top": "MEDICAL PRACTICE", "bottom": "LICENSED PRACTITIONER",
            "center": ["⚕", "DR.", "[NAME]"],
            "color": "#1c6978", "border_style": "double",
            "size_value": "45", "dividers": "dot",
            "inner_border": True,
        },
        svg=_seal_svg(
            top="MEDICAL PRACTICE", bottom="LICENSED PRACTITIONER",
            center_lines=["⚕", "DR.", "[NAME]"],
            color="#1c6978", border="double",
        ),
    ),
    StampTemplate(
        slug="company-dated",
        name="Company Dated Seal",
        category="Governance",
        kind="company_dated",
        description="Everyday dated organization seal — company on top arc, registration "
                    "on bottom arc, today's date in the center. Double ring, brand blue.",
        layout={
            "company": "COMPANY NAME LIMITED", "tagline": "REG. NO. 12345 · CITY",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "", "color": "#0f3b82", "border_style": "double",
            "size_value": "42", "logo_x": 0, "logo_y": 0,
            "logo_size": 95, "logo_opacity": 0.08, "logo_watermark": True,
        },
        svg=_company_dated_svg(
            company="COMPANY NAME LIMITED", tagline="REG. NO. 12345 · CITY",
            verb="", color="#0f3b82",
        ),
    ),
    StampTemplate(
        slug="company-dated-approved",
        name="APPROVED ON (Company dated)",
        category="Governance",
        kind="company_dated",
        description="Dated organization seal with APPROVED ON verb. Dark green, triple ring.",
        layout={
            "company": "COMPANY NAME LIMITED", "tagline": "APPROVALS COMMITTEE",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "APPROVED ON", "color": "#0e664d", "border_style": "triple",
            "size_value": "45",
        },
        svg=_company_dated_svg(
            company="COMPANY NAME LIMITED", tagline="APPROVALS COMMITTEE",
            verb="APPROVED ON", color="#0e664d",
        ),
    ),
    StampTemplate(
        slug="company-dated-certified",
        name="CERTIFIED ON (Company dated)",
        category="Legal",
        kind="company_dated",
        description="Certification variant with rope border. Red, 50mm — formal attestation.",
        layout={
            "company": "COMPANY NAME LIMITED", "tagline": "REG. NO. 12345",
            "date_format": "YYYY-MM-DD", "fixed_date": "",
            "verb": "CERTIFIED ON", "color": "#9e2f36", "border_style": "rope",
            "size_value": "50",
        },
        svg=_company_dated_svg(
            company="COMPANY NAME LIMITED", tagline="REG. NO. 12345",
            verb="CERTIFIED ON", color="#9e2f36",
        ),
    ),
    StampTemplate(
        slug="company-dated-received",
        name="RECEIVED ON (Company dated)",
        category="Operations",
        kind="company_dated",
        description="Received-at variant for inbound mail/registry stamps. Amber, dashed ring.",
        layout={
            "company": "COMPANY NAME LIMITED", "tagline": "MAILROOM · REGISTRY",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "RECEIVED", "color": "#b4821f", "border_style": "dashed",
            "size_value": "42",
        },
        svg=_company_dated_svg(
            company="COMPANY NAME LIMITED", tagline="MAILROOM · REGISTRY",
            verb="RECEIVED", color="#b4821f",
        ),
    ),
    StampTemplate(
        slug="company-dated-issued",
        name="ISSUED (Company dated)",
        category="Governance",
        kind="company_dated",
        description="Issuance seal for licences, permits, certificates. Purple, 55mm.",
        layout={
            "company": "LICENSING AUTHORITY", "tagline": "GOVERNMENT OFFICE",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "ISSUED", "color": "#5b3a97", "border_style": "double",
            "size_value": "55",
        },
        svg=_company_dated_svg(
            company="LICENSING AUTHORITY", tagline="GOVERNMENT OFFICE",
            verb="ISSUED", color="#5b3a97",
        ),
    ),
    StampTemplate(
        slug="company-dated-notary",
        name="SEALED ON (Notary · dated)",
        category="Legal",
        kind="company_dated",
        description="Notary variant with SEALED ON verb. 55mm, double ring, deep red.",
        layout={
            "company": "NOTARY PUBLIC", "tagline": "JURISDICTION · COUNTRY",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "SEALED ON", "color": "#9e2f36", "border_style": "double",
            "size_value": "55",
        },
        svg=_company_dated_svg(
            company="NOTARY PUBLIC", tagline="JURISDICTION · COUNTRY",
            verb="SEALED ON", color="#9e2f36",
        ),
    ),
    StampTemplate(
        slug="company-dated-academic",
        name="REGISTRAR (Academic · dated)",
        category="Education",
        kind="company_dated",
        description="Academic registrar dated seal — university, department, date. Navy.",
        layout={
            "company": "UNIVERSITY NAME", "tagline": "OFFICE OF THE REGISTRAR",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "REGISTERED", "color": "#0f3b82", "border_style": "triple",
            "size_value": "50",
        },
        svg=_company_dated_svg(
            company="UNIVERSITY NAME", tagline="OFFICE OF THE REGISTRAR",
            verb="REGISTERED", color="#0f3b82",
        ),
    ),
    # ------------------------------------------------------------------
    # Rectangular company stamps — real-world business stamps with company
    # name + address + reg / tel, not round corporate seals.
    # ------------------------------------------------------------------
    StampTemplate(
        slug="rect-company-address",
        name="Company address stamp",
        category="Governance",
        kind="rubber",
        description="Rectangular business stamp — company name header + address + "
                    "registration number. 80×35 mm, rounded corners, navy ink.",
        layout={
            "text": "COMPANY NAME LIMITED",
            "subtitle": "REG. NO. 12345 · NAIROBI, KENYA",
            "color": "#0f3b82", "shape": "rounded",
            "size_value": "80x35", "border_thickness": 3,
            "letter_spacing": 2, "decoration": "double-rule",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="10" fill="none" stroke="#0f3b82" stroke-width="3"/>'
            '<line x1="30" y1="34" x2="290" y2="34" stroke="#0f3b82" stroke-width="2"/>'
            '<line x1="30" y1="112" x2="290" y2="112" stroke="#0f3b82" stroke-width="2"/>'
            '<text x="160" y="60" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="20" font-weight="900" fill="#0f3b82" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<text x="160" y="90" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="12" font-weight="700" fill="#0f3b82" letter-spacing="1">REG. NO. 12345 · NAIROBI</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-contact",
        name="Company contact stamp",
        category="Correspondence",
        kind="rubber",
        description="Rectangular stamp with company name + website / tel / email. "
                    "Forest green, bracketed decoration.",
        layout={
            "text": "COMPANY NAME LIMITED",
            "subtitle": "www.company.com · +254 700 000 000",
            "color": "#0e664d", "shape": "rounded",
            "size_value": "80x35", "border_thickness": 3,
            "letter_spacing": 1, "decoration": "none",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="10" fill="none" stroke="#0e664d" stroke-width="3"/>'
            '<text x="160" y="58" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#0e664d" letter-spacing="2">COMPANY NAME</text>'
            '<line x1="40" y1="72" x2="280" y2="72" stroke="#0e664d" stroke-width="1"/>'
            '<text x="160" y="93" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="11" font-weight="600" fill="#0e664d">www.company.com</text>'
            '<text x="160" y="110" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="11" font-weight="600" fill="#0e664d">+254 700 000 000</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-approved",
        name="APPROVED BY (Rectangular · company)",
        category="Governance",
        kind="rubber",
        description="Rectangular approval stamp — company name at top, APPROVED BY line + "
                    "signature area. Red ink, 80×35 mm.",
        layout={
            "text": "COMPANY NAME",
            "subtitle": "APPROVED BY _______",
            "color": "#9e2f36", "shape": "rounded",
            "size_value": "80x35", "border_thickness": 3,
            "letter_spacing": 2,
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="6" fill="none" stroke="#9e2f36" stroke-width="3"/>'
            '<rect x="10" y="15" width="300" height="34" fill="#9e2f36"/>'
            '<text x="160" y="40" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="18" font-weight="900" fill="#ffffff" letter-spacing="2">COMPANY NAME</text>'
            '<text x="160" y="75" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="20" font-weight="900" fill="#9e2f36" letter-spacing="3">APPROVED</text>'
            '<line x1="40" y1="100" x2="280" y2="100" stroke="#9e2f36" stroke-width="1"/>'
            '<text x="160" y="115" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="10" fill="#9e2f36" letter-spacing="1">BY ______________________</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-received",
        name="Company RECEIVED stamp",
        category="Operations",
        kind="rubber",
        description="Rectangular inbound-mail stamp — company name + RECEIVED banner + "
                    "date line. 80×35 mm, amber ink.",
        layout={
            "text": "COMPANY NAME LIMITED",
            "subtitle": "RECEIVED  DATE: ____",
            "color": "#b4821f", "shape": "rounded",
            "size_value": "80x35", "border_thickness": 3,
            "letter_spacing": 2,
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="6" fill="none" stroke="#b4821f" stroke-width="3"/>'
            '<text x="160" y="40" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="16" font-weight="900" fill="#b4821f" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<line x1="24" y1="52" x2="296" y2="52" stroke="#b4821f" stroke-width="1"/>'
            '<text x="160" y="80" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#b4821f" letter-spacing="4">RECEIVED</text>'
            '<text x="160" y="110" text-anchor="middle" font-family="Courier New, monospace" '
            'font-size="13" font-weight="700" fill="#b4821f">DATE: __________</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-invoice-paid",
        name="INVOICE PAID (Rectangular · company)",
        category="Finance",
        kind="rubber",
        description="Finance team stamp — company name + PAID banner + reference line. "
                    "Forest green ink, 80×35 mm rounded.",
        layout={
            "text": "COMPANY NAME LIMITED",
            "subtitle": "INVOICE PAID · REF ____",
            "color": "#0e664d", "shape": "rounded",
            "size_value": "80x35", "border_thickness": 3,
            "letter_spacing": 2,
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="10" fill="none" stroke="#0e664d" stroke-width="3"/>'
            '<text x="160" y="40" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="14" font-weight="900" fill="#0e664d" letter-spacing="1">COMPANY NAME LIMITED</text>'
            '<text x="160" y="78" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="28" font-weight="900" fill="#0e664d" letter-spacing="5">PAID</text>'
            '<text x="160" y="110" text-anchor="middle" font-family="Courier New, monospace" '
            'font-size="11" font-weight="700" fill="#0e664d">INVOICE REF: ______</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-shield",
        name="Company shield stamp",
        category="Legal",
        kind="rubber",
        description="Shield-shaped company verification stamp — company name + CERTIFIED "
                    "TRUE COPY. Royal blue, 80×35 mm.",
        layout={
            "text": "COMPANY NAME LIMITED",
            "subtitle": "CERTIFIED TRUE COPY",
            "color": "#0f3b82", "shape": "shield",
            "size_value": "80x35", "border_thickness": 3,
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<path d="M 20 15 L 300 15 L 310 70 L 300 125 L 20 125 L 10 70 Z" fill="none" stroke="#0f3b82" stroke-width="3"/>'
            '<text x="160" y="52" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="17" font-weight="900" fill="#0f3b82" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<line x1="40" y1="64" x2="280" y2="64" stroke="#0f3b82" stroke-width="1"/>'
            '<text x="160" y="90" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="18" font-weight="900" fill="#0f3b82" letter-spacing="3">CERTIFIED</text>'
            '<text x="160" y="112" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="12" font-weight="700" fill="#0f3b82" letter-spacing="2">TRUE COPY</text>'
            '</svg>'
        ),
    ),
    # ------------------------------------------------------------------
    # Rectangular Company stamps — proper multi-line business stamps
    # with header + address + registration + contact + date reference.
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Signature stamps — signatory with name, title, line + optional date.
    # ------------------------------------------------------------------
    StampTemplate(
        slug="signature-basic",
        name="Basic signature stamp",
        category="Governance",
        kind="signature",
        description="Signatory name + title + horizontal signature line. "
                    "80×40 mm, navy ink, solid border.",
        layout={
            "name": "JANE DOE", "title": "Managing Director",
            "line_label": "Signature", "show_line": True, "show_date": False,
            "width_mm": 80, "height_mm": 40,
            "border_style": "solid", "border_thickness": 1,
            "color": "#0f3b82",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 380" '
            'width="302" height="151" data-stamp-root="1">'
            '<rect x="0.5" y="0.5" width="759" height="379" fill="none" stroke="#0f3b82" stroke-width="1"/>'
            '<text x="60" y="231" font-family="Arial, sans-serif" font-size="9" fill="#0f3b82" letter-spacing="1">Signature</text>'
            '<line x1="60" y1="235" x2="700" y2="235" stroke="#0f3b82" stroke-width="1.5"/>'
            '<text x="380" y="253" text-anchor="middle" font-family="Georgia, serif" font-size="14" font-weight="700" fill="#0f3b82" letter-spacing="1">JANE DOE</text>'
            '<text x="380" y="266" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#0f3b82" letter-spacing="1">Managing Director</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="signature-dated",
        name="Dated signature stamp",
        category="Legal",
        kind="signature",
        description="Signatory + title + line + auto-dated for legal signoff. "
                    "100×50 mm, red ink, rounded border.",
        layout={
            "name": "JOHN SMITH", "title": "Notary Public",
            "line_label": "Signature", "show_line": True,
            "show_date": True, "date_format": "DD MMM YYYY",
            "width_mm": 100, "height_mm": 50,
            "border_style": "rounded", "border_thickness": 2,
            "corner_radius": 6,
            "color": "#9e2f36",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 380" '
            'width="302" height="151" data-stamp-root="1">'
            '<rect x="1" y="1" width="758" height="378" rx="18" fill="none" stroke="#9e2f36" stroke-width="2"/>'
            '<text x="60" y="231" font-family="Arial, sans-serif" font-size="9" fill="#9e2f36" letter-spacing="1">Signature</text>'
            '<line x1="60" y1="235" x2="700" y2="235" stroke="#9e2f36" stroke-width="1.5"/>'
            '<text x="380" y="253" text-anchor="middle" font-family="Georgia, serif" font-size="14" font-weight="700" fill="#9e2f36" letter-spacing="1">JOHN SMITH</text>'
            '<text x="380" y="266" text-anchor="middle" font-family="Arial, sans-serif" font-size="10" fill="#9e2f36" letter-spacing="1">Notary Public</text>'
            '<text x="740" y="365" text-anchor="end" font-family="Courier New, monospace" font-size="10" font-weight="700" fill="#9e2f36" letter-spacing="1" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-full",
        name="Full Company Stamp",
        category="Governance",
        kind="company_rect",
        description="Complete rectangular company stamp — header band, address, "
                    "registration, tax PIN, contact, auto-date. 90×50 mm, royal blue.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "PRIVATE LIMITED COMPANY",
            "address1": "123 Business Avenue",
            "address2": "Nairobi, Kenya",
            "reg_label": "REG. NO.",
            "reg_value": "C.12345",
            "tax_label": "TAX PIN",
            "tax_value": "P00000000A",
            "phone":   "+254 700 000 000",
            "email":   "info@company.com",
            "website": "www.company.com",
            "reference_label": "DATE",
            "reference_value": "",
            "date_format": "DD MMM YYYY",
            "width_mm": 90, "height_mm": 50,
            "border_style": "rounded", "border_thickness": 3,
            "corner_radius": 6,
            "header_bar": True, "divider_rule": True, "alignment": "center",
            "show_subtitle": True, "show_address": True,
            "show_reg": True, "show_tax": True,
            "show_contact": True, "show_reference": True,
            "color": "#0f3b82",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="340" height="188" data-stamp-root="1">'
            '<rect x="1.5" y="1.5" width="757" height="417" rx="18" fill="none" stroke="#0f3b82" stroke-width="3"/>'
            '<rect x="3" y="3" width="754" height="50" fill="#0f3b82"/>'
            '<text x="380" y="39" text-anchor="middle" font-family="Arial Black, sans-serif" font-size="22" fill="#ffffff" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<text x="380" y="80" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#0f3b82" letter-spacing="1">PRIVATE LIMITED COMPANY</text>'
            '<line x1="40" y1="94" x2="720" y2="94" stroke="#0f3b82" stroke-width="1"/>'
            '<text x="380" y="130" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f3b82">123 Business Avenue</text>'
            '<text x="380" y="150" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f3b82">Nairobi, Kenya</text>'
            '<text x="380" y="180" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f3b82">REG. NO. C.12345</text>'
            '<text x="380" y="200" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f3b82">TAX PIN P00000000A</text>'
            '<text x="380" y="230" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#0f3b82">+254 700 000 000 · info@company.com</text>'
            '<text x="24" y="356" font-family="Courier New, monospace" font-size="14" font-weight="700" fill="#0f3b82" letter-spacing="1">DATE</text>'
            '<text x="736" y="356" text-anchor="end" font-family="Courier New, monospace" font-size="14" font-weight="700" fill="#0f3b82" letter-spacing="1" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-minimal",
        name="Minimal Company Stamp",
        category="Governance",
        kind="company_rect",
        description="Minimal rectangular stamp — company name, address, reg number. "
                    "70×40 mm, forest green, no colored header band.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "address1": "P.O. Box 00000 - 00100",
            "address2": "Nairobi, Kenya",
            "reg_label": "REG.", "reg_value": "123456",
            "phone": "", "email": "", "website": "",
            "reference_label": "", "reference_value": "",
            "width_mm": 70, "height_mm": 40,
            "border_style": "solid", "border_thickness": 2,
            "corner_radius": 0,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_subtitle": False, "show_contact": False,
            "show_reference": False,
            "color": "#0e664d",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="265" height="151" data-stamp-root="1">'
            '<rect x="1" y="1" width="758" height="418" fill="none" stroke="#0e664d" stroke-width="2"/>'
            '<text x="380" y="80" text-anchor="middle" font-family="Arial Black, sans-serif" font-size="26" font-weight="900" fill="#0e664d" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<line x1="80" y1="100" x2="680" y2="100" stroke="#0e664d" stroke-width="1"/>'
            '<text x="380" y="160" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#0e664d">P.O. Box 00000 - 00100</text>'
            '<text x="380" y="190" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" fill="#0e664d">Nairobi, Kenya</text>'
            '<text x="380" y="240" text-anchor="middle" font-family="Arial, sans-serif" font-size="16" font-weight="700" fill="#0e664d">REG. 123456</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-tax",
        name="Tax Company Stamp",
        category="Finance",
        kind="company_rect",
        description="Company stamp with VAT/Tax focus — Reg number + Tax PIN + registered "
                    "office. Red, 80×40 mm, double border.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "VAT REGISTERED",
            "address1": "Registered Office: 123 Business Ave",
            "address2": "Nairobi, Kenya",
            "reg_label": "REG. NO.", "reg_value": "C.12345",
            "tax_label": "VAT", "tax_value": "0123456X",
            "phone": "", "email": "", "website": "",
            "reference_label": "DATE", "reference_value": "",
            "width_mm": 80, "height_mm": 40,
            "border_style": "double", "border_thickness": 2,
            "corner_radius": 2,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_contact": False, "show_tax": True,
            "color": "#9e2f36",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="303" height="151" data-stamp-root="1">'
            '<rect x="1" y="1" width="758" height="418" fill="none" stroke="#9e2f36" stroke-width="2"/>'
            '<rect x="12" y="12" width="736" height="396" fill="none" stroke="#9e2f36" stroke-width="1"/>'
            '<text x="380" y="70" text-anchor="middle" font-family="Arial Black, sans-serif" font-size="22" font-weight="900" fill="#9e2f36" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<text x="380" y="100" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#9e2f36" letter-spacing="1">VAT REGISTERED</text>'
            '<line x1="80" y1="116" x2="680" y2="116" stroke="#9e2f36" stroke-width="1"/>'
            '<text x="380" y="148" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#9e2f36">Registered Office: 123 Business Ave</text>'
            '<text x="380" y="168" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" fill="#9e2f36">Nairobi, Kenya</text>'
            '<text x="380" y="210" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" font-weight="700" fill="#9e2f36">REG. NO. C.12345  ·  VAT 0123456X</text>'
            '<text x="40" y="356" font-family="Courier New, monospace" font-size="14" font-weight="700" fill="#9e2f36" letter-spacing="1">DATE</text>'
            '<text x="720" y="356" text-anchor="end" font-family="Courier New, monospace" font-size="14" font-weight="700" fill="#9e2f36" letter-spacing="1" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="rect-company-contact-rect",
        name="Contact Company Stamp",
        category="Correspondence",
        kind="company_rect",
        description="Rectangular stamp emphasising contact details — phone / email / web. "
                    "80×50 mm, navy header bar.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "GET IN TOUCH",
            "address1": "123 Business Avenue, Nairobi, Kenya",
            "address2": "",
            "phone": "+254 700 000 000",
            "email": "hello@company.com",
            "website": "www.company.com",
            "reference_label": "", "reference_value": "",
            "width_mm": 80, "height_mm": 50,
            "border_style": "rounded", "border_thickness": 3,
            "corner_radius": 8,
            "header_bar": True, "divider_rule": False, "alignment": "center",
            "show_reg": False, "show_tax": False,
            "show_reference": False,
            "color": "#0f3b82",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 420" width="303" height="189" data-stamp-root="1">'
            '<rect x="1.5" y="1.5" width="757" height="417" rx="24" fill="none" stroke="#0f3b82" stroke-width="3"/>'
            '<rect x="3" y="3" width="754" height="60" fill="#0f3b82"/>'
            '<text x="380" y="45" text-anchor="middle" font-family="Arial Black, sans-serif" font-size="22" fill="#ffffff" letter-spacing="2">COMPANY NAME LIMITED</text>'
            '<text x="380" y="100" text-anchor="middle" font-family="Arial, sans-serif" font-size="12" font-weight="700" fill="#0f3b82" letter-spacing="1">GET IN TOUCH</text>'
            '<text x="380" y="155" text-anchor="middle" font-family="Arial, sans-serif" font-size="14" fill="#0f3b82">123 Business Avenue, Nairobi, Kenya</text>'
            '<text x="380" y="210" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#0f3b82">+254 700 000 000  ·  hello@company.com</text>'
            '<text x="380" y="240" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#0f3b82">www.company.com</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="company-dated-logistics",
        name="DISPATCHED (Logistics · dated)",
        category="Logistics",
        kind="company_dated",
        description="Warehouse/logistics dispatch seal with date. Forest green, 45mm.",
        layout={
            "company": "WAREHOUSE OPS", "tagline": "DISPATCH DEPT",
            "date_format": "DD MMM YYYY", "fixed_date": "",
            "verb": "DISPATCHED", "color": "#0e664d", "border_style": "single",
            "size_value": "45",
        },
        svg=_company_dated_svg(
            company="WAREHOUSE OPS", tagline="DISPATCH DEPT",
            verb="DISPATCHED", color="#0e664d",
        ),
    ),

    # Operations
    StampTemplate(
        slug="originals-only",
        name="ORIGINALS ONLY",
        category="Legal",
        kind="rubber",
        description="Compact ORIGINAL rubber stamp with heavy underline. Navy, 50×20 mm.",
        layout={
            "text": "ORIGINAL", "color": "#0f3b82", "shape": "rect",
            "size_value": "50x20", "decoration": "underline",
        },
        svg=_rubber_svg(text="ORIGINAL", color="#0f3b82"),
    ),
    StampTemplate(
        slug="posted",
        name="POSTED (Mail Room)",
        category="Operations",
        kind="date",
        description="Mailroom POSTED stamp with date. Dark blue ink.",
        layout={"label": "POSTED", "date": "", "byline": "MAIL ROOM",
                "color": "#0f3b82", "size_value": "59x23"},
        svg=_date_svg(label="POSTED", color="#0f3b82"),
    ),
    StampTemplate(
        slug="urgent",
        name="URGENT rubber",
        category="Correspondence",
        kind="rubber",
        description="Urgent attention stamp — red, double rule, bold.",
        layout={
            "text": "URGENT", "color": "#9e2f36", "shape": "rect",
            "size_value": "70x25", "decoration": "double-rule",
        },
        svg=_rubber_svg(text="URGENT", color="#9e2f36"),
    ),
    StampTemplate(
        slug="rejected",
        name="REJECTED stamp",
        category="Operations",
        kind="date",
        description="Rejection stamp with date + reason line. Red ink.",
        layout={"label": "REJECTED", "date": "", "byline": "REASON: ____",
                "color": "#9e2f36", "size_value": "70x25"},
        svg=_date_svg(label="REJECTED", color="#9e2f36"),
    ),
    StampTemplate(
        slug="received-stamp",
        name="RECEIVED stamp",
        category="Operations",
        kind="date",
        description="Mail-room RECEIVED stamp with today's date. Red ink. Ribbon label "
                    "on top, date below, signature line.",
        layout={
            "label": "RECEIVED", "date": "", "byline": "",
            "color": "#9e2f36", "size_value": "59x23",
        },
        svg=_date_svg(label="RECEIVED", color="#9e2f36"),
    ),
    StampTemplate(
        slug="approved-stamp",
        name="APPROVED stamp",
        category="Operations",
        kind="date",
        description="APPROVED stamp with date. Dark green ink. Use for signed-off documents.",
        layout={
            "label": "APPROVED", "date": "", "byline": "",
            "color": "#0e664d", "size_value": "59x23",
        },
        svg=_date_svg(label="APPROVED", color="#0e664d"),
    ),
    StampTemplate(
        slug="paid-stamp",
        name="PAID stamp",
        category="Operations",
        kind="date",
        description="PAID stamp for finance operations — dark green, dated.",
        layout={
            "label": "PAID", "date": "", "byline": "",
            "color": "#0e664d", "size_value": "59x23",
        },
        svg=_date_svg(label="PAID", color="#0e664d"),
    ),

    # Correspondence
    StampTemplate(
        slug="draft-watermark",
        name="DRAFT watermark",
        category="Correspondence",
        kind="rubber",
        description="Large DRAFT rubber stamp — amber ink, rectangular. Insert onto any "
                    "document that's not final.",
        layout={
            "text": "DRAFT", "color": "#835a0c", "shape": "rect",
            "size_value": "80x35",
        },
        svg=_rubber_svg(text="DRAFT", color="#835a0c"),
    ),
    StampTemplate(
        slug="confidential-stamp",
        name="CONFIDENTIAL stamp",
        category="Correspondence",
        kind="rubber",
        description="Red CONFIDENTIAL rubber stamp — mark sensitive correspondence.",
        layout={
            "text": "CONFIDENTIAL", "color": "#9e2f36", "shape": "rect",
            "size_value": "80x35",
        },
        svg=_rubber_svg(text="CONFIDENTIAL", color="#9e2f36"),
    ),
    StampTemplate(
        slug="copy-stamp",
        name="COPY stamp",
        category="Correspondence",
        kind="rubber",
        description="Simple COPY stamp with oval border. Blue ink.",
        layout={
            "text": "COPY", "color": "#0f3b82", "shape": "oval",
            "size_value": "70x25",
        },
        svg=_rubber_svg(text="COPY", color="#0f3b82", shape="oval"),
    ),

    # Legal
    StampTemplate(
        slug="certified-true-copy",
        name="CERTIFIED TRUE COPY",
        category="Legal",
        kind="rubber",
        description="Larger legal verification rubber stamp — blue, rounded corners.",
        layout={
            "text": "CERTIFIED\nTRUE COPY", "color": "#0f3b82", "shape": "rounded",
            "size_value": "80x35",
        },
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" '
            'width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="18" fill="none" stroke="#0f3b82" stroke-width="4"/>'
            '<text x="160" y="60" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="26" font-weight="900" fill="#0f3b82" letter-spacing="2">CERTIFIED</text>'
            '<text x="160" y="100" text-anchor="middle" font-family="Arial, sans-serif" '
            'font-size="18" font-weight="700" fill="#0f3b82" letter-spacing="2">TRUE COPY</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="notarized",
        name="NOTARIZED rubber stamp",
        category="Legal",
        kind="rubber",
        description="Compact NOTARIZED mark for witnessed documents. Red, double-rule.",
        layout={"text": "NOTARIZED", "color": "#9e2f36", "shape": "rounded",
                "size_value": "70x25", "decoration": "double-rule"},
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="12" fill="none" stroke="#9e2f36" stroke-width="4"/>'
            '<line x1="30" y1="34" x2="290" y2="34" stroke="#9e2f36" stroke-width="2"/>'
            '<line x1="30" y1="112" x2="290" y2="112" stroke="#9e2f36" stroke-width="2"/>'
            '<text x="160" y="85" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="38" font-weight="900" fill="#9e2f36" letter-spacing="4">NOTARIZED</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="court-filed",
        name="COURT FILED stamp",
        category="Legal",
        kind="date",
        description="Court clerk FILED stamp with today's date. Dark blue.",
        layout={"label": "FILED", "date": "", "byline": "COURT CLERK",
                "color": "#0f3b82", "size_value": "59x23", "box_style": "shadow"},
        svg=_date_svg(label="FILED", color="#0f3b82"),
    ),

    # Healthcare
    StampTemplate(
        slug="medical-reviewed",
        name="MEDICAL REVIEWED",
        category="Healthcare",
        kind="date",
        description="Clinician review stamp for patient records. Green, outlined box.",
        layout={"label": "REVIEWED", "date": "", "byline": "MD / RN",
                "color": "#0e664d", "size_value": "59x23"},
        svg=_date_svg(label="REVIEWED", color="#0e664d"),
    ),
    StampTemplate(
        slug="prescription-filled",
        name="RX FILLED stamp",
        category="Healthcare",
        kind="date",
        description="Pharmacy fulfillment stamp with dispense date. Dark purple.",
        layout={"label": "RX FILLED", "date": "", "byline": "PHARMACIST",
                "color": "#5b3a97", "size_value": "59x23"},
        svg=_date_svg(label="RX FILLED", color="#5b3a97"),
    ),
    StampTemplate(
        slug="ehr-locked",
        name="EHR LOCKED (chart complete)",
        category="Healthcare",
        kind="rubber",
        description="EHR chart-lock stamp signalling encounter complete. Teal, rounded.",
        layout={"text": "CHART LOCKED", "color": "#1c6978", "shape": "rounded",
                "size_value": "70x25"},
        svg=_rubber_svg(text="CHART LOCKED", color="#1c6978"),
    ),

    # Finance
    StampTemplate(
        slug="void",
        name="VOID stamp",
        category="Finance",
        kind="rubber",
        description="Large VOID stamp for cancelled cheques and invoices. Red, oval.",
        layout={"text": "VOID", "color": "#9e2f36", "shape": "oval",
                "size_value": "80x35"},
        svg=_rubber_svg(text="VOID", color="#9e2f36", shape="oval"),
    ),
    StampTemplate(
        slug="invoice-paid",
        name="INVOICE PAID with date",
        category="Finance",
        kind="date",
        description="Accounts-receivable PAID stamp with today's date. Green ribbon.",
        layout={"label": "PAID", "date": "", "byline": "A/P DEPT",
                "color": "#0e664d", "size_value": "59x23", "ribbon_style": "striped"},
        svg=_date_svg(label="PAID", color="#0e664d"),
    ),
    StampTemplate(
        slug="audit-reviewed",
        name="AUDIT REVIEWED",
        category="Finance",
        kind="date",
        description="Internal audit review stamp with signature line. Dark blue.",
        layout={"label": "AUDITED", "date": "", "byline": "AUDITOR",
                "color": "#0f3b82", "size_value": "70x25"},
        svg=_date_svg(label="AUDITED", color="#0f3b82"),
    ),

    # Logistics
    StampTemplate(
        slug="shipped",
        name="SHIPPED stamp",
        category="Logistics",
        kind="date",
        description="Warehouse SHIPPED stamp with dispatch date. Dark green.",
        layout={"label": "SHIPPED", "date": "", "byline": "TRACKING #",
                "color": "#0e664d", "size_value": "59x23"},
        svg=_date_svg(label="SHIPPED", color="#0e664d"),
    ),
    StampTemplate(
        slug="inspected",
        name="QC INSPECTED",
        category="Logistics",
        kind="date",
        description="Quality control inspection stamp with inspector line. Amber.",
        layout={"label": "INSPECTED", "date": "", "byline": "INSPECTOR",
                "color": "#b4821f", "size_value": "70x25"},
        svg=_date_svg(label="INSPECTED", color="#b4821f"),
    ),
    StampTemplate(
        slug="customs-cleared",
        name="CUSTOMS CLEARED",
        category="Logistics",
        kind="rubber",
        description="Customs clearance rubber stamp. Blue, shield shape.",
        layout={"text": "CUSTOMS\nCLEARED", "color": "#0f3b82", "shape": "shield",
                "size_value": "70x25"},
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<path d="M 20 15 L 300 15 L 310 70 L 300 125 L 20 125 L 10 70 Z" fill="none" stroke="#0f3b82" stroke-width="4"/>'
            '<text x="160" y="60" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#0f3b82" letter-spacing="2">CUSTOMS</text>'
            '<text x="160" y="100" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#0f3b82" letter-spacing="2">CLEARED</text>'
            '</svg>'
        ),
    ),

    # Education
    StampTemplate(
        slug="graded",
        name="GRADED stamp",
        category="Education",
        kind="date",
        description="Teacher grading stamp with date. Red ink.",
        layout={"label": "GRADED", "date": "", "byline": "GRADE: ___",
                "color": "#9e2f36", "size_value": "59x23"},
        svg=_date_svg(label="GRADED", color="#9e2f36"),
    ),
    StampTemplate(
        slug="transcript-official",
        name="OFFICIAL TRANSCRIPT",
        category="Education",
        kind="rubber",
        description="Registrar's OFFICIAL TRANSCRIPT stamp. Deep purple, bracketed.",
        layout={"text": "OFFICIAL\nTRANSCRIPT", "color": "#5b3a97",
                "shape": "rounded", "size_value": "80x35",
                "decoration": "bracketed"},
        svg=(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 140" width="200" height="88" data-stamp-root="1">'
            '<rect x="10" y="15" width="300" height="110" rx="12" fill="none" stroke="#5b3a97" stroke-width="4"/>'
            '<text x="160" y="60" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#5b3a97" letter-spacing="2">OFFICIAL</text>'
            '<text x="160" y="100" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            'font-size="22" font-weight="900" fill="#5b3a97" letter-spacing="2">TRANSCRIPT</text>'
            '</svg>'
        ),
    ),
    StampTemplate(
        slug="diploma-seal",
        name="Diploma / Degree seal",
        category="Education",
        kind="seal",
        description="Round university seal with monogram center — 55 mm, double ring.",
        layout={
            "top": "UNIVERSITY SEAL", "bottom": "FOUNDED YYYY",
            "center": ["[MONOGRAM]"],
            "color": "#5b3a97", "border_style": "double",
            "size_value": "55",
        },
        svg=_seal_svg(
            top="UNIVERSITY SEAL", bottom="FOUNDED YYYY",
            center_lines=["★★★", "ALMA", "MATER"],
            color="#5b3a97", border="double",
        ),
    ),

    # Government
    StampTemplate(
        slug="government-received",
        name="GOV RECEIVED (with time)",
        category="Government",
        kind="date",
        description="Government office received stamp with date + time byline. Red.",
        layout={"label": "RECEIVED", "date": "", "byline": "TIME ______",
                "color": "#9e2f36", "size_value": "70x25"},
        svg=_date_svg(label="RECEIVED", color="#9e2f36"),
    ),
    StampTemplate(
        slug="approved-seal",
        name="APPROVED round seal",
        category="Government",
        kind="seal",
        description="Round APPROVED government seal with triple ring and star dividers.",
        layout={
            "top": "APPROVED", "bottom": "AUTHORITY",
            "center": ["★★★", "APPROVED", "[OFFICE]"],
            "color": "#0e664d", "border_style": "triple",
            "size_value": "50", "dividers": "star",
        },
        svg=_seal_svg(
            top="APPROVED", bottom="AUTHORITY",
            center_lines=["★★★", "APPROVED", "[OFFICE]"],
            color="#0e664d", border="double",
        ),
    ),
]


def list_templates() -> list[dict]:
    return [
        {
            "slug": t.slug, "name": t.name, "category": t.category,
            "kind": t.kind, "description": t.description, "svg": t.svg,
        }
        for t in _TEMPLATES
    ]


def get_template(slug: str) -> StampTemplate | None:
    for t in _TEMPLATES:
        if t.slug == slug:
            return t
    return None
