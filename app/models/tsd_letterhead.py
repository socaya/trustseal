"""Tenant-owned official Letterheads applied to finalize TS Documents."""
from __future__ import annotations

import base64
import html
from datetime import datetime

from app.extensions import db


def _brand_emblem_uri(kind: str, primary: str, secondary: str, letters: str = "M") -> str:
    """Build a crisp executive vector corporate emblem as a data URI for inbuilt templates."""
    p = html.escape(primary)
    s = html.escape(secondary)
    ltr = html.escape(letters[:3].upper())
    if kind == "shield":
        body = (
            f'<path d="M40 6 L70 18 V44 C70 60 56 71 40 76 C24 71 10 60 10 44 V18 Z" fill="{p}"/>'
            f'<path d="M40 12 L64 22 V43 C64 56 53 65 40 69 C27 65 16 56 16 43 V22 Z" fill="none" stroke="{s}" stroke-width="2.2"/>'
            f'<text x="40" y="49" text-anchor="middle" font-family="Georgia,serif" font-size="22" font-weight="700" fill="#ffffff">{ltr}</text>'
        )
    elif kind == "hexagon":
        body = (
            f'<polygon points="40,5 71,22 71,58 40,75 9,58 9,22" fill="{p}"/>'
            f'<polygon points="40,13 64,26 64,54 40,67 16,54 16,26" fill="none" stroke="{s}" stroke-width="2.2"/>'
            f'<text x="40" y="48" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="20" font-weight="700" fill="#ffffff">{ltr}</text>'
        )
    elif kind == "crest":
        body = (
            f'<circle cx="40" cy="40" r="34" fill="{p}"/>'
            f'<circle cx="40" cy="40" r="28" fill="none" stroke="{s}" stroke-width="2.2"/>'
            f'<circle cx="40" cy="40" r="23" fill="none" stroke="{s}" stroke-width="0.9" stroke-dasharray="3 2"/>'
            f'<text x="40" y="47" text-anchor="middle" font-family="Georgia,serif" font-size="20" font-weight="700" fill="#ffffff">{ltr}</text>'
        )
    elif kind == "diamond":
        body = (
            f'<polygon points="40,4 76,40 40,76 4,40" fill="{p}"/>'
            f'<polygon points="40,12 68,40 40,68 12,40" fill="none" stroke="{s}" stroke-width="2"/>'
            f'<text x="40" y="47" text-anchor="middle" font-family="Georgia,serif" font-size="20" font-weight="700" fill="#ffffff">{ltr}</text>'
        )
    elif kind == "pillar":
        body = (
            f'<rect x="6" y="6" width="68" height="68" fill="{p}"/>'
            f'<rect x="13" y="13" width="54" height="54" fill="none" stroke="{s}" stroke-width="2"/>'
            f'<rect x="22" y="24" width="36" height="4" fill="{s}"/>'
            f'<rect x="25" y="31" width="5" height="22" fill="#ffffff"/>'
            f'<rect x="37.5" y="31" width="5" height="22" fill="#ffffff"/>'
            f'<rect x="50" y="31" width="5" height="22" fill="#ffffff"/>'
            f'<rect x="20" y="55" width="40" height="4" fill="{s}"/>'
        )
    elif kind == "medical":
        body = (
            f'<rect x="6" y="6" width="68" height="68" fill="{p}"/>'
            f'<rect x="33" y="18" width="14" height="44" fill="#ffffff"/>'
            f'<rect x="18" y="33" width="44" height="14" fill="#ffffff"/>'
            f'<rect x="36" y="36" width="8" height="8" fill="{s}"/>'
        )
    elif kind == "wave":
        body = (
            f'<rect x="6" y="6" width="68" height="68" fill="{p}"/>'
            f'<path d="M12 46 Q26 30 40 46 T68 46" fill="none" stroke="#ffffff" stroke-width="4.5" stroke-linecap="round"/>'
            f'<path d="M12 58 Q26 42 40 58 T68 58" fill="none" stroke="{s}" stroke-width="3.5" stroke-linecap="round"/>'
            f'<text x="40" y="30" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="700" fill="#ffffff">{ltr}</text>'
        )
    else:
        body = (
            f'<rect x="6" y="6" width="68" height="68" fill="{p}"/>'
            f'<rect x="6" y="62" width="68" height="12" fill="{s}"/>'
            f'<text x="40" y="46" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="24" font-weight="800" fill="#ffffff">{ltr}</text>'
        )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" width="80" height="80">{body}</svg>'
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


LETTERHEAD_FONT_STACKS: dict[str, str] = {
    "sans": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif",
    "serif": "Georgia, 'Times New Roman', Times, serif",
    "legal": "'Times New Roman', Times, Georgia, serif",
    "modern": "'Helvetica Neue', Helvetica, Arial, sans-serif",
    "garamond": "'EB Garamond', Garamond, 'Palatino Linotype', Georgia, serif",
    "mono": "'JetBrains Mono', 'SFMono-Regular', Menlo, Consolas, monospace",
}

LETTERHEAD_PAPER_SIZES: dict[str, dict] = {
    "a4":        {"label": "A4 (210 × 297 mm)",        "w_mm": 210.0,  "h_mm": 297.0,  "css": "A4"},
    "letter":    {"label": "US Letter (8.5 × 11 in)",  "w_mm": 215.9,  "h_mm": 279.4,  "css": "Letter"},
    "legal":     {"label": "US Legal (8.5 × 14 in)",   "w_mm": 215.9,  "h_mm": 355.6,  "css": "Legal"},
    "a5":        {"label": "A5 (148 × 210 mm)",        "w_mm": 148.0,  "h_mm": 210.0,  "css": "A5"},
    "executive": {"label": "Executive (7.25 × 10.5 in)", "w_mm": 184.15, "h_mm": 266.7, "css": "184.15mm 266.7mm"},
    "b5":        {"label": "B5 (176 × 250 mm)",        "w_mm": 176.0,  "h_mm": 250.0,  "css": "176mm 250mm"},
}

LETTERHEAD_PRESETS: list[dict] = [
    {
        "slug": "classic_executive",
        "label": "Meridian Executive Navy & Gold",
        "category": "Executive",
        "doc_type": "Official Corporate Letterhead",
        "description": "Boardroom A4 stationery in deep navy & metallic gold with branded crest, dual-tone corner accents, and formal ref bar.",
        "layout": {
            "header_align": "left", "accent_color": "#0f213d", "brand_secondary": "#c59b27", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 6, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 22,
            "bg_pattern": "geometric_corners", "bg_pattern_opacity": 85, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("shield", "#0f213d", "#c59b27", "MH"),
            "logo_height_px": 54, "org_name": "MERIDIAN HOLDINGS LIMITED",
            "tagline": "Office of the Chief Executive", "address": "14th Floor, Delta Towers, Westlands, Nairobi",
            "phone": "+254 20 555 0140", "email": "board@meridianholdings.co", "website": "www.meridianholdings.co",
            "reg_no": "REG. NO. PVT-884210", "directors": "A. Kamau (Chairman), E. Ochieng (Group CEO), M. Patel (CFO)",
            "footer_text": "Confidential · Regulated Entity · All Rights Reserved",
        },
    },
    {
        "slug": "modern_split",
        "label": "Northstar Royal Blue & Sky",
        "category": "Executive",
        "doc_type": "Corporate Split Letterhead",
        "description": "Crisp split header in royal blue & electric sky with geometric emblem and bold architectural side ribbon.",
        "layout": {
            "header_align": "split", "accent_color": "#1e4b9e", "brand_secondary": "#0ea5e9", "secondary_color": "#334155",
            "font_style": "modern", "top_bar_px": 5, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 22,
            "bg_pattern": "side_accent_ribbon", "bg_pattern_opacity": 90, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("hexagon", "#1e4b9e", "#0ea5e9", "NS"),
            "logo_height_px": 50, "org_name": "NORTHSTAR INFRASTRUCTURE PLC",
            "tagline": "Engineering · Energy · Advisory", "address": "Level 9, One Financial Place",
            "phone": "+44 20 7946 0821", "email": "secretariat@northstar-plc.com", "website": "www.northstar-plc.com",
            "reg_no": "CO. NO. 09482711", "footer_text": "Registered in England & Wales · ISO 27001 Certified",
        },
    },
    {
        "slug": "legal_counsel",
        "label": "Kensington Law Chambers",
        "category": "Legal & Governance",
        "doc_type": "Chambers Legal Letterhead",
        "description": "Authoritative charcoal & bronze chambers stationery with classical pillar emblem, double rule, and ivory stock.",
        "layout": {
            "header_align": "split", "accent_color": "#1f2937", "brand_secondary": "#b45309", "secondary_color": "#374151",
            "font_style": "legal", "top_bar_px": 0, "divider_style": "double", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 24,
            "bg_pattern": "corner_brackets", "bg_pattern_opacity": 75, "paper_bg": "#fcfbf7",
            "logo_data_uri": _brand_emblem_uri("pillar", "#1f2937", "#d97706", "KP"),
            "logo_height_px": 50, "org_name": "KENSINGTON & PARTNERS LLP",
            "tagline": "Advocates · Commissioners for Oaths · Notaries Public", "address": "Suite 600, Chancery Chambers",
            "phone": "+254 20 555 0199", "email": "chambers@kensingtonlaw.co", "reg_no": "LLP/2019/0412",
            "directors": "Senior Partners: R. Kensington, SC · D. Mwangi · S. Al-Mansoor",
            "footer_text": "Privileged & Confidential · Attorney-Client Communication",
        },
    },
    {
        "slug": "centered_official",
        "label": "Sovereign Crest & Royal Gold",
        "category": "Legal & Governance",
        "doc_type": "Official Institutional Stationery",
        "description": "Centered ceremonial crest in royal navy & antique gold with double divider and guilloché security frame.",
        "layout": {
            "header_align": "center", "accent_color": "#14326b", "brand_secondary": "#c59b27", "secondary_color": "#334155",
            "font_style": "serif", "top_bar_px": 0, "divider_style": "double", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 25,
            "bg_pattern": "certificate_frame", "bg_pattern_opacity": 65, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("crest", "#14326b", "#c59b27", "ICG"),
            "logo_height_px": 60, "org_name": "INSTITUTE OF CORPORATE GOVERNANCE",
            "tagline": "Chartered Secretariat & Regulatory Standards", "address": "100 Civic Plaza · P.O. Box 40210",
            "phone": "+254 20 555 0100", "email": "registrar@icg-standards.org", "website": "www.icg-standards.org",
            "footer_text": "Official Institutional Instrument · Verify Authenticity via TrustSeal",
        },
    },
    {
        "slug": "audit_advisory",
        "label": "Veritas Emerald & Gold Audit",
        "category": "Finance & Audit",
        "doc_type": "Audit & Assurance Letterhead",
        "description": "Rich forest emerald & warm gold advisory stationery with angled left brand panel and diamond crest.",
        "layout": {
            "header_align": "left", "accent_color": "#14532d", "brand_secondary": "#ca8a04", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 4, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 24,
            "bg_pattern": "angled_side_panel", "bg_pattern_opacity": 88, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("diamond", "#14532d", "#ca8a04", "VA"),
            "logo_height_px": 50, "org_name": "VERITAS ASSURANCE & TAX",
            "tagline": "Certified Public Accountants · Statutory Auditors", "address": "8th Floor, Commerce House",
            "phone": "+254 20 555 0175", "email": "assurance@veritas-cpa.com", "tax_id": "PRACTICE NO. ICPA-4419",
            "footer_text": "Member Firm · Regulated Public Practice",
        },
    },
    {
        "slug": "aurelia_private_bank",
        "label": "Aurelia Private Banking",
        "category": "Finance & Audit",
        "doc_type": "Private Wealth Stationery",
        "description": "Warm ivory & burnished bronze-gold centered serif stationery with subtle diamond lattice security backdrop.",
        "layout": {
            "header_align": "center", "accent_color": "#78350f", "brand_secondary": "#d97706", "secondary_color": "#44403c",
            "font_style": "serif", "top_bar_px": 5, "divider_style": "double", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 24,
            "bg_pattern": "diamond_lattice", "bg_pattern_opacity": 14, "paper_bg": "#fcfbf7",
            "show_bottom_bar": True, "logo_data_uri": _brand_emblem_uri("crest", "#78350f", "#f59e0b", "AP"),
            "logo_height_px": 54, "org_name": "AURELIA PRIVATE BANK",
            "tagline": "Wealth Advisory · Fiduciary Services · Zurich & Nairobi",
            "address": "Bahnhofstrasse 42 · Private Banking Desk", "email": "advisory@aureliabank.ch",
            "footer_text": "Licensed Financial Institution · Strict Fiduciary Confidentiality",
        },
    },
    {
        "slug": "apex_obsidian_banner",
        "label": "Apex Obsidian & Crimson Banner",
        "category": "Executive",
        "doc_type": "Modern Banner Letterhead",
        "description": "Bold full-bleed obsidian dark header banner with crimson accent bar on US Letter stock.",
        "layout": {
            "header_align": "banner", "header_bg": "solid", "accent_color": "#111827", "brand_secondary": "#dc2626", "secondary_color": "#374151",
            "font_style": "modern", "top_bar_px": 0, "divider_style": "none", "show_divider": False,
            "show_ref_bar": True, "ref_bar_style": "compact", "paper_size": "letter", "orientation": "portrait", "margin_mm": 22,
            "bg_pattern": "bottom_dual_wave", "bg_pattern_opacity": 80, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("monogram", "#dc2626", "#ffffff", "AG"),
            "logo_height_px": 48, "org_name": "APEX GLOBAL SYSTEMS INC.",
            "tagline": "Enterprise Architecture & Executive Operations",
            "address": "500 Market Street, Suite 2100, San Francisco, CA", "email": "executive@apexglobalsystems.com",
            "footer_text": "Confidential Corporate Correspondence · All Rights Reserved",
        },
    },
    {
        "slug": "pacific_teal_wave",
        "label": "Pacific Teal & Turquoise Wave",
        "category": "Executive",
        "doc_type": "Modern Wave Stationery",
        "description": "Deep ocean teal & bright turquoise stationery with sculpted top wave arch and maritime emblem.",
        "layout": {
            "header_align": "split", "accent_color": "#0e5a6d", "brand_secondary": "#14b8a6", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 0, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 22,
            "bg_pattern": "top_wave_arch", "bg_pattern_opacity": 82, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("wave", "#0e5a6d", "#2dd4bf", "PM"),
            "logo_height_px": 50, "org_name": "PACIFIC MARITIME & LOGISTICS",
            "tagline": "Global Freight · Port Operations · Trade Finance",
            "address": "Harbour View Plaza, Mombasa", "phone": "+254 41 555 0188",
            "email": "operations@pacificmaritime.co", "footer_text": "ISO 9001:2015 Certified Maritime Carrier",
        },
    },
    {
        "slug": "us_legal_burgundy",
        "label": "Sterling Burgundy & Gold Legal",
        "category": "Legal & Governance",
        "doc_type": "US Legal Formal Filing",
        "description": "Full US Legal (8.5 × 14 in) format in deep burgundy & gold with shield emblem and double divider.",
        "layout": {
            "header_align": "split", "accent_color": "#6b1d2f", "brand_secondary": "#c59b27", "secondary_color": "#334155",
            "font_style": "legal", "top_bar_px": 5, "divider_style": "double", "show_divider": True,
            "show_ref_bar": True, "paper_size": "legal", "orientation": "portrait", "margin_mm": 24,
            "bg_pattern": "corner_brackets", "bg_pattern_opacity": 78, "paper_bg": "#fcfbf7",
            "logo_data_uri": _brand_emblem_uri("shield", "#6b1d2f", "#c59b27", "SR"),
            "logo_height_px": 50, "org_name": "STERLING REGULATORY COUNSEL",
            "tagline": "Corporate Compliance & Litigation Practice",
            "address": "1200 Avenue of the Americas, New York, NY 10036", "phone": "+1 (212) 555-0194",
            "email": "filings@sterlingcounsel.us", "footer_text": "Attorney Work Product · Confidential Legal Filing",
        },
    },
    {
        "slug": "helios_crimson_health",
        "label": "Helios Crimson Medical Board",
        "category": "HR & Employment",
        "doc_type": "Clinical & Institutional Stationery",
        "description": "Crisp institutional crimson & coral medical board letterhead with dual footer waves and cross emblem.",
        "layout": {
            "header_align": "left", "accent_color": "#9b1c2c", "brand_secondary": "#f43f5e", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 5, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 22,
            "bg_pattern": "bottom_dual_wave", "bg_pattern_opacity": 85, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("medical", "#9b1c2c", "#fda4af", "HH"),
            "logo_height_px": 48, "org_name": "HELIOS HEALTHCARE GROUP",
            "tagline": "Clinical Governance & Specialist Medical Board",
            "address": "Medical Park Avenue, Upper Hill", "email": "board@helioshealth.org",
            "footer_text": "Confidential Medical & Institutional Record",
        },
    },
    {
        "slug": "vanguard_indigo_tech",
        "label": "Vanguard Indigo & Violet Tech",
        "category": "Executive",
        "doc_type": "Tech Enterprise Stationery",
        "description": "Deep indigo full-width brand banner with electric violet accent and crisp hexagon emblem.",
        "layout": {
            "header_align": "banner", "header_bg": "solid", "accent_color": "#312e81", "brand_secondary": "#818cf8", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 0, "divider_style": "none", "show_divider": False,
            "show_ref_bar": True, "ref_bar_style": "compact", "paper_size": "a4", "orientation": "portrait",
            "margin_mm": 21, "bg_pattern": "geometric_corners", "bg_pattern_opacity": 80, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("hexagon", "#4f46e5", "#c7d2fe", "VC"),
            "logo_height_px": 48, "org_name": "VANGUARD CLOUD SYSTEMS",
            "tagline": "Security Infrastructure · Enterprise AI", "website": "www.vanguardcloud.io",
            "email": "legal@vanguardcloud.io", "footer_text": "SOC 2 Type II · ISO 27001 Certified",
        },
    },
    {
        "slug": "sahara_terracotta",
        "label": "Sahara Terracotta & Amber",
        "category": "Finance & Audit",
        "doc_type": "Management Consulting Stationery",
        "description": "Warm terracotta & amber editorial stationery with bold angled left brand panel and monogram mark.",
        "layout": {
            "header_align": "split", "accent_color": "#9a3412", "brand_secondary": "#f59e0b", "secondary_color": "#44403c",
            "font_style": "modern", "top_bar_px": 4, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 24,
            "bg_pattern": "angled_side_panel", "bg_pattern_opacity": 90, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("monogram", "#9a3412", "#f59e0b", "SS"),
            "logo_height_px": 48, "org_name": "SAHARA STRATEGY PARTNERS",
            "tagline": "Capital Markets · Economic Advisory", "address": "18th Floor, Prism Tower",
            "email": "partners@saharastrategy.com", "footer_text": "Strictly Private & Confidential",
        },
    },
    {
        "slug": "nordic_slate_minimal",
        "label": "Nordic Slate & Ice Blue",
        "category": "HR & Employment",
        "doc_type": "Clean Editorial Letterhead",
        "description": "Ultra-clean soft pearl paper with slate & steel-blue hairline accent and 3-column contact footer.",
        "layout": {
            "header_align": "left", "accent_color": "#1e293b", "brand_secondary": "#38bdf8", "secondary_color": "#475569",
            "font_style": "sans", "top_bar_px": 4, "divider_style": "thin", "show_divider": True,
            "show_ref_bar": False, "footer_layout": "columns", "paper_size": "a4", "orientation": "portrait",
            "margin_mm": 24, "bg_pattern": "swiss_dots", "bg_pattern_opacity": 18, "paper_bg": "#f9fafc",
            "logo_data_uri": _brand_emblem_uri("monogram", "#1e293b", "#38bdf8", "NC"),
            "logo_height_px": 44, "org_name": "NORDIC CAPITAL GROUP",
            "tagline": "People · Governance · Sustainability", "address": "24 Harbour Quay",
            "email": "office@nordiccapital.eu", "footer_text": "Nordic Capital Group AB",
        },
    },
    {
        "slug": "commonwealth_diplomatic",
        "label": "Commonwealth Diplomatic Seal",
        "category": "Legal & Governance",
        "doc_type": "Ceremonial Diplomatic Stationery",
        "description": "Deep diplomatic navy & bronze-gold centered crest with ceremonial guilloché border on ivory stock.",
        "layout": {
            "header_align": "center", "accent_color": "#1e3a5f", "brand_secondary": "#b45309", "secondary_color": "#334155",
            "font_style": "serif", "top_bar_px": 0, "divider_style": "double", "show_divider": True,
            "show_ref_bar": True, "paper_size": "a4", "orientation": "portrait", "margin_mm": 25,
            "bg_pattern": "certificate_frame", "bg_pattern_opacity": 72, "paper_bg": "#fcfbf7",
            "logo_data_uri": _brand_emblem_uri("crest", "#1e3a5f", "#d97706", "RG"),
            "logo_height_px": 60, "org_name": "OFFICE OF THE REGISTRAR GENERAL",
            "tagline": "Official Registry & Statutory Certifications",
            "address": "Chancery Square · P.O. Box 30031", "footer_text": "Official State & Statutory Instrument",
        },
    },
    {
        "slug": "landscape_certificate",
        "label": "Landscape Corporate Charter",
        "category": "Executive",
        "doc_type": "A4 Landscape Certificate / Resolution",
        "description": "A4 Landscape ceremonial layout in navy & gold with radial crest sunburst and double formal border.",
        "layout": {
            "header_align": "center", "accent_color": "#0f213d", "brand_secondary": "#c59b27", "secondary_color": "#475569",
            "font_style": "serif", "top_bar_px": 6, "divider_style": "double", "show_divider": True,
            "show_ref_bar": False, "paper_size": "a4", "orientation": "landscape", "margin_mm": 22,
            "bg_pattern": "sunburst_crest", "bg_pattern_opacity": 14, "page_border": "double", "paper_bg": "#fcfbf7",
            "logo_data_uri": _brand_emblem_uri("crest", "#0f213d", "#c59b27", "ST"),
            "logo_height_px": 58, "org_name": "SOVEREIGN TRUST CORPORATION",
            "tagline": "Certificate of Corporate Authority & Good Standing",
            "address": "Registered Head Office · International Financial Centre",
            "footer_text": "Issued Under Official Seal · Cryptographically Verifiable via TrustSeal",
        },
    },
    {
        "slug": "a5_executive_memo",
        "label": "A5 Executive Dispatch Memo",
        "category": "HR & Employment",
        "doc_type": "A5 Compact Memo Stationery",
        "description": "Compact A5 stationery in cobalt & amber with built-in TO/FROM/DATE/REF memo grid and corner accents.",
        "layout": {
            "header_align": "split", "accent_color": "#1e4b9e", "brand_secondary": "#f59e0b", "secondary_color": "#334155",
            "font_style": "sans", "top_bar_px": 5, "divider_style": "solid", "show_divider": True,
            "show_ref_bar": True, "ref_bar_style": "memo", "paper_size": "a5", "orientation": "portrait",
            "margin_mm": 16, "bg_pattern": "geometric_corners", "bg_pattern_opacity": 85, "paper_bg": "#ffffff",
            "logo_data_uri": _brand_emblem_uri("monogram", "#1e4b9e", "#f59e0b", "ME"),
            "logo_height_px": 40, "org_name": "MERIDIAN EXECUTIVE OFFICE",
            "tagline": "Internal Dispatch & Directive", "email": "dispatch@meridianholdings.co",
            "footer_text": "Internal Distribution Only",
        },
    },
]


def render_letterhead_parts(layout: dict | None) -> tuple[str, str]:
    """Build clean, print-ready HTML snippets for ``(header_html, footer_html)``."""
    cfg = layout or {}
    esc = html.escape
    accent = esc(str(cfg.get("accent_color") or "#0f213d"))
    secondary = esc(str(cfg.get("secondary_color") or "#42526e"))
    brand_secondary = esc(str(cfg.get("brand_secondary") or "#c59b27"))
    font_key = str(cfg.get("font_style") or "sans").lower()
    font_stack = LETTERHEAD_FONT_STACKS.get(font_key, LETTERHEAD_FONT_STACKS["sans"])

    align = str(cfg.get("header_align") or "left").lower()
    if align not in ("left", "center", "split", "right", "banner"):
        align = "left"

    top_bar_px = max(0, min(12, int(cfg.get("top_bar_px") or 0)))
    divider_style = str(cfg.get("divider_style") or "solid").lower()
    show_divider = cfg.get("show_divider", True) and divider_style != "none"
    show_ref_bar = bool(cfg.get("show_ref_bar", False))
    ref_bar_style = str(cfg.get("ref_bar_style") or "classic").lower()
    show_trust_badge = cfg.get("show_trust_badge", True)
    show_footer_rule = cfg.get("show_footer_rule", True)
    show_bottom_bar = bool(cfg.get("show_bottom_bar", False))
    show_page_numbers = bool(cfg.get("show_page_numbers", False))
    footer_layout = str(cfg.get("footer_layout") or "split").lower()
    header_bg = str(cfg.get("header_bg") or "none").lower()

    hide_org_name = bool(cfg.get("hide_org_name", False))
    org_font_pt = max(11, min(22, int(cfg.get("org_font_pt") or 15)))
    org_uppercase = bool(cfg.get("org_uppercase", False))

    logo_uri = str(cfg.get("logo_data_uri") or "").strip()
    logo_h = max(20, min(160, int(cfg.get("logo_height_px") or 50)))
    logo_w = max(24, min(360, int(cfg.get("logo_width_px") or 220)))
    logo_ox = max(-650, min(650, int(cfg.get("logo_offset_x") or 0)))
    logo_oy = max(-300, min(900, int(cfg.get("logo_offset_y") or 0)))
    el_pos = cfg.get("el_pos") if isinstance(cfg.get("el_pos"), dict) else {}
    el_align = cfg.get("el_align") if isinstance(cfg.get("el_align"), dict) else {}

    def _el_css(key: str) -> str:
        bits = []
        p = el_pos.get(key)
        if isinstance(p, dict):
            px = max(-650, min(650, int(p.get("x") or 0)))
            py = max(-300, min(900, int(p.get("y") or 0)))
            if px or py:
                bits.append(f"position:relative;transform:translate({px}px,{py}px);")
        al = str(el_align.get(key) or "").lower()
        if al in ("left", "center", "right", "justify"):
            bits.append(f"text-align:{al};")
        return "".join(bits)
    logo_frame = str(cfg.get("logo_frame") or "none").lower()
    logo_mat = str(cfg.get("logo_mat") or "none").lower()
    logo_filter = str(cfg.get("logo_filter") or "none").lower()
    logo_op = max(20, min(100, int(cfg.get("logo_opacity") if cfg.get("logo_opacity") is not None else 100))) / 100.0

    org_name = "" if hide_org_name else esc(str(cfg.get("org_name") or "").strip())
    tagline = esc(str(cfg.get("tagline") or "").strip())
    department = esc(str(cfg.get("department") or "").strip())
    address = esc(str(cfg.get("address") or "").strip())
    postal = esc(str(cfg.get("postal_address") or "").strip())
    phone = esc(str(cfg.get("phone") or "").strip())
    phone2 = esc(str(cfg.get("secondary_phone") or "").strip())
    email = esc(str(cfg.get("email") or "").strip())
    website = esc(str(cfg.get("website") or "").strip())
    reg_no = esc(str(cfg.get("reg_no") or "").strip())
    tax_id = esc(str(cfg.get("tax_id") or "").strip())
    license_no = esc(str(cfg.get("license_no") or "").strip())
    directors = esc(str(cfg.get("directors") or "").strip())
    bank_details = esc(str(cfg.get("bank_details") or "").strip())
    footer_text = esc(str(cfg.get("footer_text") or "").strip())
    watermark_text = esc(str(cfg.get("watermark_text") or "").strip())
    wm_opacity = max(3, min(25, int(cfg.get("watermark_opacity") or 6))) / 100.0
    wm_angle = max(-45, min(0, int(cfg.get("watermark_angle") if cfg.get("watermark_angle") is not None else -28)))

    addr_line = " &nbsp;·&nbsp; ".join(p for p in (address, postal) if p)
    contact_line = " &nbsp;·&nbsp; ".join(p for p in (phone, phone2, email, website) if p)
    reg_line = " &nbsp;·&nbsp; ".join(p for p in (reg_no, tax_id, license_no) if p)

    logo_html = ""
    if logo_uri.startswith("data:image/") or logo_uri.startswith("/static/"):
        mat_css = (
            "background:#ffffff;padding:6px;" if logo_mat == "white"
            else (f"background:{accent};padding:7px;" if logo_mat == "brand" else "")
        )
        frame_css = (
            f"border-radius:50%;overflow:hidden;border:1.5px solid {brand_secondary};display:inline-flex;align-items:center;justify-content:center;"
            if logo_frame == "circle"
            else (f"border:1.5px solid {accent};padding:5px;" if logo_frame == "square" else "")
        )
        filter_css = (
            "filter:grayscale(100%);" if logo_filter == "grayscale"
            else ("filter:contrast(1.35) saturate(1.1);" if logo_filter == "contrast"
            else ("filter:brightness(0) invert(1);" if logo_filter == "invert" else ""))
        )
        logo_fit = str(cfg.get("logo_fit") or "contain").lower()
        size_css = (
            f"width:{logo_w}px;height:{logo_h}px;object-fit:fill;"
            if logo_fit == "fill"
            else f"height:{logo_h}px;max-width:{logo_w}px;width:auto;object-fit:contain;"
        )
        wrap_css = f"transform:translate({logo_ox}px,{logo_oy}px);opacity:{logo_op:.2f};flex:0 0 auto;{frame_css}{mat_css}"
        logo_html = (
            f'<div style="{wrap_css}">'
            f'<img src="{esc(logo_uri)}" alt="Logo" '
            f'style="{size_css}display:block;{filter_css}">'
            f'</div>'
        )

    header_bleed = str(cfg.get("header_bleed") or ("bleed" if align == "banner" else "margin")).lower()
    header_min_h = max(0, min(260, int(cfg.get("header_min_height") or 0)))
    header_pad_y = max(0, min(56, int(cfg.get("header_pad_y") if cfg.get("header_pad_y") is not None else 14)))
    header_pad_x = max(0, min(72, int(cfg.get("header_pad_x") if cfg.get("header_pad_x") is not None else 24)))
    footer_bleed = str(cfg.get("footer_bleed") or "margin").lower()
    footer_bg = str(cfg.get("footer_bg") or "none").lower()
    footer_min_h = max(0, min(180, int(cfg.get("footer_min_height") or 0)))
    footer_pad_y = max(4, min(44, int(cfg.get("footer_pad_y") if cfg.get("footer_pad_y") is not None else 10)))

    is_banner = (align == "banner" or header_bg in ("solid", "gradient", "angled"))
    ink_primary = "#ffffff" if is_banner else accent
    ink_sec = "rgba(255,255,255,0.86)" if is_banner else secondary
    ink_muted = "rgba(255,255,255,0.72)" if is_banner else "#64748b"

    bg_css = ""
    if header_bg == "solid" or (align == "banner" and header_bg == "none"):
        bg_css = f"background:{accent};border-bottom:3px solid {brand_secondary};"
    elif header_bg == "gradient":
        bg_css = f"background:linear-gradient(125deg,{accent} 0%,{accent} 62%,{brand_secondary} 135%);border-bottom:3px solid {brand_secondary};"
    elif header_bg == "angled":
        bg_css = f"background:linear-gradient(112deg,{accent} 0%,{accent} 68%,{brand_secondary} 68.2%,{brand_secondary} 100%);"
    elif header_bg == "neutral":
        bg_css = "background:#f6f8fb;"
    elif header_bg == "tint":
        bg_css = f"background:linear-gradient(90deg,{accent}14,{brand_secondary}14);"
    elif header_bg == "framed":
        bg_css = f"background:#f8fafc;border-left:4px solid {accent};"
    elif header_bg == "underline_band":
        bg_css = f"background:#f8fafc;border-top:4px solid {accent};border-bottom:2px solid {brand_secondary};"

    h_min_css = f"min-height:{header_min_h}px;box-sizing:border-box;" if header_min_h > 0 else ""
    if header_bleed == "bleed":
        margin_mm_hdr = max(10, min(40, int(cfg.get("margin_mm") or 22)))
        bg_css += f"margin-left:-{margin_mm_hdr}mm;margin-right:-{margin_mm_hdr}mm;padding:{max(12, header_pad_y)}px {max(12, header_pad_x)}px;{h_min_css}"
    else:
        px_pad = max(10, min(32, header_pad_x)) if header_bg != "none" else 0
        bg_css += f"padding:{header_pad_y if header_bg != 'none' else 0}px {px_pad}px {max(8, header_pad_y)}px;{h_min_css}"

    show_tagline = cfg.get("show_tagline", True)
    show_contact = cfg.get("show_contact", True)
    show_footer = cfg.get("show_footer", True)
    tagline_font_pt = max(6.5, min(14.0, float(cfg.get("tagline_font_pt") or 8.5)))
    contact_font_pt = max(6.5, min(12.0, float(cfg.get("contact_font_pt") or 8.2)))
    contact_layout = str(cfg.get("contact_layout") or "inline").lower()
    footer_font_pt = max(6.5, min(11.0, float(cfg.get("footer_font_pt") or 8.0)))
    ref_font_pt = max(7.0, min(12.0, float(cfg.get("ref_font_pt") or 8.5)))
    divider_px = max(1, min(8, int(cfg.get("divider_px") or 2)))
    bottom_bar_px = max(2, min(14, int(cfg.get("bottom_bar_px") or 5)))
    ref_l1 = str(cfg.get("ref_label_1") if cfg.get("ref_label_1") is not None else "Our Ref").strip()
    ref_l2 = str(cfg.get("ref_label_2") if cfg.get("ref_label_2") is not None else "Your Ref").strip()
    ref_l3 = str(cfg.get("ref_label_3") if cfg.get("ref_label_3") is not None else "Date").strip()

    divider_html = ""
    if show_divider and not is_banner:
        if divider_style == "dual":
            divider_html = f'<div style="height:{divider_px}px;background:linear-gradient(90deg,{accent} 72%,{brand_secondary} 72%);margin-top:2pt;"></div>'
        elif divider_style == "double":
            divider_html = f'<div style="border-bottom:{max(3, divider_px + 1)}px double {accent};margin-top:2pt;"></div>'
        elif divider_style == "thin":
            divider_html = f'<div style="border-bottom:{divider_px}px solid rgba(15,23,42,0.16);margin-top:2pt;"></div>'
        elif divider_style == "dotted":
            divider_html = f'<div style="border-bottom:{divider_px}px dotted {accent};margin-top:2pt;"></div>'
        else:
            divider_html = f'<div style="height:{divider_px}px;background:{accent};margin-top:2pt;"></div>'

    top_bar_html = (
        f'<div style="height:{top_bar_px}px;background:linear-gradient(90deg,{accent} 72%,{brand_secondary} 72%);margin-bottom:12pt;"></div>'
        if (top_bar_px > 0 and not is_banner) else ""
    )

    org_transform = "text-transform:uppercase;" if org_uppercase else ""
    org_pos_css = _el_css("org_title")
    tag_pos_css = _el_css("tagline")
    ct_pos_css = _el_css("contact")
    title_block = (
        f'<div style="min-width:0;">'
        + (f'<div style="font-size:{org_font_pt}pt;font-weight:700;color:{ink_primary};letter-spacing:0.015em;line-height:1.15;{org_transform}{org_pos_css}">{org_name}</div>' if org_name else "")
        + (f'<div style="{tag_pos_css}">'
           + (f'<div style="font-size:{tagline_font_pt}pt;font-weight:600;color:{brand_secondary if is_banner else ink_sec};margin-top:2pt;letter-spacing:0.05em;text-transform:uppercase;">{tagline}</div>' if tagline else "")
           + (f'<div style="font-size:{tagline_font_pt}pt;color:{ink_sec};margin-top:1.5pt;">{department}</div>' if department else "")
           + '</div>' if (show_tagline and (tagline or department)) else "")
        + "</div>"
    )

    contact_block = ""
    if show_contact and (addr_line or contact_line or reg_line):
        reg_pt = max(6.5, contact_font_pt - 0.6)
        if contact_layout == "stacked":
            lines_html = "".join(
                f"<div>{p}</div>"
                for p in (address, postal, phone, phone2, email, website)
                if p
            )
            contact_block = (
                f'<div style="font-size:{contact_font_pt}pt;color:{ink_sec};line-height:1.45;margin-top:3pt;{ct_pos_css}">'
                + lines_html
                + (f'<div style="color:{ink_muted};font-size:{reg_pt:.1f}pt;">{reg_line}</div>' if reg_line else "")
                + "</div>"
            )
        else:
            contact_block = (
                f'<div style="font-size:{contact_font_pt}pt;color:{ink_sec};line-height:1.45;margin-top:3pt;{ct_pos_css}">'
                + (f'<div>{addr_line}</div>' if addr_line else "")
                + (f'<div>{contact_line}</div>' if contact_line else "")
                + (f'<div style="color:{ink_muted};font-size:{reg_pt:.1f}pt;">{reg_line}</div>' if reg_line else "")
                + "</div>"
            )

    if align == "center":
        inner_header = (
            f'<div style="text-align:center;padding-bottom:10pt;{bg_css}">'
            + (f'<div style="display:flex;justify-content:center;margin-bottom:7pt;">{logo_html}</div>' if logo_html else "")
            + title_block
            + contact_block
            + "</div>"
        )
    elif align in ("split", "banner"):
        inner_header = (
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:16pt;padding-bottom:10pt;{bg_css}">'
            f'<div style="display:flex;align-items:center;gap:11pt;min-width:0;">{logo_html}{title_block}</div>'
            + (f'<div style="text-align:right;">{contact_block}</div>' if contact_block else "")
            + "</div>"
        )
    elif align == "right":
        inner_header = (
            f'<div style="display:flex;align-items:center;justify-content:space-between;gap:14pt;padding-bottom:10pt;{bg_css}">'
            f'<div style="flex:1;min-width:0;">{title_block}{contact_block}</div>'
            + logo_html
            + "</div>"
        )
    else:
        inner_header = (
            f'<div style="display:flex;align-items:center;gap:12pt;padding-bottom:10pt;{bg_css}">'
            + logo_html
            + f'<div style="flex:1;min-width:0;">{title_block}{contact_block}</div></div>'
        )

    ref_bar_html = ""
    if show_ref_bar:
        if ref_bar_style == "compact":
            bits = [f'<span><strong>{esc(lb)}:</strong> ________________</span>' for lb in (ref_l1 or "Ref", ref_l3 or "Date") if lb]
            ref_bar_html = (
                f'<div class="tsd-letterhead-ref" style="display:flex;justify-content:space-between;gap:12pt;'
                f'margin-top:8pt;font-size:{ref_font_pt}pt;color:{secondary};">'
                + "".join(bits)
                + "</div>"
            )
        elif ref_bar_style == "boxed":
            bits = [f'<span><strong>{esc(lb)}:</strong> ____________</span>' for lb in (ref_l1, ref_l2, ref_l3) if lb]
            ref_bar_html = (
                f'<div class="tsd-letterhead-ref" style="display:flex;justify-content:space-between;gap:12pt;'
                f'margin-top:8pt;padding:6pt 10pt;background:#f6f8fb;border-left:3px solid {brand_secondary};font-size:{ref_font_pt}pt;color:{secondary};">'
                + ("".join(bits) or '<span><strong>Ref:</strong> ____________</span><span><strong>Date:</strong> ____________</span>')
                + "</div>"
            )
        elif ref_bar_style == "memo":
            ref_bar_html = (
                f'<div class="tsd-letterhead-ref" style="display:grid;grid-template-columns:1fr 1fr;gap:4pt 14pt;'
                f'margin-top:9pt;padding:7pt 10pt;background:#f6f8fb;border-left:3px solid {brand_secondary};font-size:{ref_font_pt}pt;color:{secondary};">'
                f'<div><strong>TO:</strong> _______________________</div>'
                f'<div><strong>DATE:</strong> _____________________</div>'
                f'<div><strong>FROM:</strong> _____________________</div>'
                f'<div><strong>REF:</strong> ______________________</div>'
                f'</div>'
            )
        else:
            bits = [f'<span><strong>{esc(lb)}:</strong> ________________</span>' for lb in (ref_l1, ref_l2, ref_l3) if lb]
            ref_bar_html = (
                f'<div class="tsd-letterhead-ref" style="display:flex;justify-content:space-between;gap:12pt;'
                f'margin-top:8pt;font-size:{ref_font_pt}pt;color:{secondary};">'
                + ("".join(bits) or '<span><strong>Ref:</strong> ________________</span><span><strong>Date:</strong> ________________</span>')
                + "</div>"
            )

    wm_html = ""
    if watermark_text:
        wm_html = (
            f'<div class="tsd-letterhead-wm" aria-hidden="true" style="position:relative;height:0;overflow:visible;pointer-events:none;">'
            f'<div style="position:absolute;left:50%;top:160pt;transform:translate(-50%,0) rotate({wm_angle}deg);'
            f'font-size:38pt;font-weight:700;letter-spacing:0.12em;color:{accent};opacity:{wm_opacity:.2f};white-space:nowrap;user-select:none;">'
            f'{watermark_text}</div></div>'
        )

    paper_size = str(cfg.get("paper_size") or "a4").lower()
    if paper_size not in LETTERHEAD_PAPER_SIZES:
        paper_size = "a4"
    orientation = str(cfg.get("orientation") or "portrait").lower()
    if orientation not in ("portrait", "landscape"):
        orientation = "portrait"
    margin_mm = max(10, min(40, int(cfg.get("margin_mm") or 22)))

    bg_img_uri = str(cfg.get("bg_image_data_uri") or "").strip()
    bg_img_op = max(2, min(40, int(cfg.get("bg_image_opacity") or 8))) / 100.0
    bg_img_scale = max(20, min(85, int(cfg.get("bg_image_scale") or 42)))
    bg_img_html = ""
    if bg_img_uri.startswith("data:image/"):
        bg_img_html = (
            f'<div class="tsd-letterhead-bgimg" aria-hidden="true" style="position:relative;height:0;overflow:visible;pointer-events:none;">'
            f'<img src="{esc(bg_img_uri)}" alt="" style="position:absolute;left:50%;top:120pt;transform:translate(-50%,0);'
            f'width:{bg_img_scale}%;max-height:340pt;object-fit:contain;opacity:{bg_img_op:.2f};user-select:none;">'
            f'</div>'
        )

    bg_pattern = esc(str(cfg.get("bg_pattern") or "none").lower())

    header_html = (
        f'<div class="tsd-letterhead-header" contenteditable="false" '
        f'data-paper-size="{paper_size}" data-orientation="{orientation}" '
        f'data-margin-mm="{margin_mm}" data-watermark="{watermark_text}" '
        f'data-bg-pattern="{bg_pattern}" '
        f'style="font-family:{font_stack};margin-bottom:14pt;">'
        + top_bar_html
        + inner_header
        + divider_html
        + ref_bar_html
        + bg_img_html
        + wm_html
        + "</div>"
    )

    footer_rows = []
    if show_footer:
        if directors:
            footer_rows.append(f'<div style="font-size:{max(6.5, footer_font_pt - 0.5):.1f}pt;color:#64748b;margin-bottom:3pt;"><strong>Directors / Officers:</strong> {directors}</div>')
        if bank_details:
            footer_rows.append(f'<div style="font-size:{max(6.5, footer_font_pt - 0.5):.1f}pt;color:#64748b;margin-bottom:3pt;"><strong>Banking:</strong> {bank_details}</div>')

        bottom_left = footer_text or reg_line or org_name
        right_parts = []
        if show_page_numbers:
            right_parts.append("Page 1 of 1")
        if show_trust_badge:
            right_parts.append("Verified · TrustSeal Document")
        bottom_right = (
            f'<span style="color:#94a3b8;white-space:nowrap;">{" &nbsp;·&nbsp; ".join(right_parts)}</span>'
            if right_parts else ""
        )

        if footer_layout == "centered":
            footer_rows.append(
                f'<div style="text-align:center;">'
                f'<div>{bottom_left}</div>'
                + (f'<div style="margin-top:2pt;">{bottom_right}</div>' if bottom_right else "")
                + "</div>"
            )
        elif footer_layout == "columns":
            footer_rows.append(
                f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8pt;font-size:{max(6.5, footer_font_pt - 0.4):.1f}pt;">'
                f'<div>{addr_line or bottom_left}</div>'
                f'<div style="text-align:center;">{contact_line or reg_line}</div>'
                f'<div style="text-align:right;">{bottom_right or reg_line}</div>'
                f'</div>'
            )
        else:
            footer_rows.append(
                f'<div style="display:flex;justify-content:space-between;align-items:center;gap:10pt;">'
                f'<span>{bottom_left}</span>{bottom_right}</div>'
            )

    is_dark_ftr = footer_bg in ("solid", "gradient")
    ftr_ink = "rgba(255,255,255,0.9)" if is_dark_ftr else secondary
    ftr_bg_css = (
        f"background:{accent};" if footer_bg == "solid"
        else (f"background:linear-gradient(125deg,{accent} 0%,{accent} 68%,{brand_secondary} 135%);" if footer_bg == "gradient"
        else ("background:#f6f8fb;" if footer_bg == "neutral"
        else (f"background:linear-gradient(90deg,{accent}12,{brand_secondary}12);" if footer_bg == "tint" else "")))
    )
    ftr_min_css = f"min-height:{footer_min_h}px;box-sizing:border-box;" if footer_min_h > 0 else ""
    ftr_bleed_css = (
        f"margin-left:-{margin_mm}mm;margin-right:-{margin_mm}mm;padding:{footer_pad_y}px {margin_mm}mm;"
        if footer_bleed == "bleed"
        else f"padding:{footer_pad_y}px {'12px' if footer_bg != 'none' else '0'};"
    )
    ftr_rule = "border-top:1px solid rgba(15,23,42,0.14);" if (show_footer_rule and not is_dark_ftr) else ""
    bottom_bar_html = (
        f'<div style="height:{bottom_bar_px}px;background:linear-gradient(90deg,{accent} 72%,{brand_secondary} 72%);margin-top:8pt;"></div>'
        if (show_bottom_bar and footer_bleed != "bleed") else ""
    )

    footer_html = (
        f'<div class="tsd-letterhead-footer" contenteditable="false" '
        f'style="font-family:{font_stack};margin-top:24pt;'
        f'{ftr_rule}{ftr_bg_css}{ftr_bleed_css}{ftr_min_css}font-size:{footer_font_pt}pt;color:{ftr_ink};line-height:1.4;">'
        + "".join(footer_rows)
        + bottom_bar_html
        + "</div>"
    ) if (footer_rows or show_footer_rule or show_bottom_bar) else ""
    return header_html, footer_html


class TSDLetterhead(db.Model):
    __tablename__ = "tsd_letterheads"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer, db.ForeignKey("organizations.id"),
        nullable=False, index=True,
    )
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"),
        nullable=False,
    )
    name = db.Column(db.String(140), nullable=False)
    description = db.Column(db.String(300), nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(20), nullable=False, default="active")
    layout = db.Column(db.JSON, nullable=False)
    header_html = db.Column(db.Text, nullable=False, default="")
    footer_html = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at = db.Column(db.DateTime, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "created_by_id": self.created_by_id,
            "name": self.name,
            "description": self.description or "",
            "is_default": bool(self.is_default),
            "status": self.status or "active",
            "layout": self.layout or {},
            "header_html": self.header_html or "",
            "footer_html": self.footer_html or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
