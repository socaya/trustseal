"""TRUSTSEAL Brand Identity Studio Engine.

Provides:
- 24 bespoke precision geometric vector brand marks (pure SVG, zero external CDN icons)
- 12 curated executive color palettes with exact HEX, RGB, CMYK & WCAG contrast specs
- 10 curated typography pairings (modern sans, editorial serif, geometric display)
- Smashing-Logo-style multi-concept generator producing 12 distinct brand identities
- 4 production vector logo lockups (primary full-color, dark monochrome, reversed light, square icon)
- Comprehensive Brand Guidelines generator (clear space, minimum sizes, color specs, voice, misuse rules)
"""
from __future__ import annotations

import hashlib
import html
import re
from typing import Any

# ---------------------------------------------------------------------------
# 1. Bespoke Geometric Vector Marks (48x48 viewBox, {primary} & {secondary})
# ---------------------------------------------------------------------------

BRAND_ICONS: list[dict[str, str]] = [
    {
        "id": "shield_check",
        "name": "Verified Shield",
        "category": "Trust & Security",
        "paths": (
            '<path d="M24 4L40 10V23C40 33.2 33.1 41.3 24 44C14.9 41.3 8 33.2 8 23V10L24 4Z" fill="{primary}"/>'
            '<path d="M24 8.5L36 13V22.8C36 30.8 30.7 37.3 24 39.6V8.5Z" fill="{secondary}" fill-opacity="0.22"/>'
            '<path d="M17.2 24.2L22 29L31.4 18.8" fill="none" stroke="{contrast}" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>'
        ),
    },
    {
        "id": "prism_hex",
        "name": "Prism Hexagon",
        "category": "Technology",
        "paths": (
            '<polygon points="24,4 41,14 41,34 24,44 7,34 7,14" fill="{primary}"/>'
            '<polygon points="24,4 41,14 24,24 7,14" fill="{secondary}"/>'
            '<polygon points="24,24 41,14 41,34 24,44" fill="{primary}" fill-opacity="0.72"/>'
            '<circle cx="24" cy="24" r="4.5" fill="{contrast}"/>'
        ),
    },
    {
        "id": "apex_peak",
        "name": "Apex Summit",
        "category": "Finance & Advisory",
        "paths": (
            '<polygon points="24,6 43,40 32.5,40 24,24 15.5,40 5,40" fill="{primary}"/>'
            '<polygon points="24,18 32,33 16,33" fill="{secondary}"/>'
        ),
    },
    {
        "id": "infinity_arc",
        "name": "Infinity Ribbon",
        "category": "Technology",
        "paths": (
            '<path d="M10 24C10 16.5 16 12 22 17.5L26 21.5C32 27 38 22.5 38 15" fill="none" stroke="{primary}" stroke-width="5.2" stroke-linecap="round"/>'
            '<path d="M38 24C38 31.5 32 36 26 30.5L22 26.5C16 21 10 25.5 10 33" fill="none" stroke="{secondary}" stroke-width="5.2" stroke-linecap="round"/>'
        ),
    },
    {
        "id": "compass_star",
        "name": "North Star Compass",
        "category": "Strategy & Consulting",
        "paths": (
            '<circle cx="24" cy="24" r="19" fill="none" stroke="{primary}" stroke-width="3"/>'
            '<polygon points="24,7 28.5,19.5 41,24 28.5,28.5 24,41 19.5,28.5 7,24 19.5,19.5" fill="{primary}"/>'
            '<polygon points="24,12 27,21 36,24 27,27 24,36 21,27 12,24 21,21" fill="{secondary}"/>'
            '<circle cx="24" cy="24" r="3.2" fill="{contrast}"/>'
        ),
    },
    {
        "id": "crown_crest",
        "name": "Executive Crest",
        "category": "Luxury & Legal",
        "paths": (
            '<path d="M7 34L10 15L18.5 23L24 11L29.5 23L38 15L41 34H7Z" fill="{primary}"/>'
            '<rect x="8" y="36.5" width="32" height="4.5" rx="1.5" fill="{secondary}"/>'
            '<circle cx="24" cy="9" r="2.6" fill="{secondary}"/>'
        ),
    },
    {
        "id": "orbit_ring",
        "name": "Orbital Core",
        "category": "Technology",
        "paths": (
            '<ellipse cx="24" cy="24" rx="19" ry="8.5" transform="rotate(-28 24 24)" fill="none" stroke="{primary}" stroke-width="3.6"/>'
            '<ellipse cx="24" cy="24" rx="19" ry="8.5" transform="rotate(28 24 24)" fill="none" stroke="{secondary}" stroke-width="3.6"/>'
            '<circle cx="24" cy="24" r="6" fill="{primary}"/>'
        ),
    },
    {
        "id": "pillar_monolith",
        "name": "Architectural Pillars",
        "category": "Real Estate & Finance",
        "paths": (
            '<rect x="7" y="18" width="8" height="24" fill="{primary}"/>'
            '<rect x="20" y="8" width="8" height="34" fill="{secondary}"/>'
            '<rect x="33" y="14" width="8" height="28" fill="{primary}"/>'
            '<rect x="5" y="42" width="38" height="3" fill="{primary}"/>'
        ),
    },
    {
        "id": "wave_flow",
        "name": "Horizon Wave",
        "category": "Logistics & Mobility",
        "paths": (
            '<path d="M5 20C11 10 19 10 24 19C29 28 37 28 43 18" fill="none" stroke="{primary}" stroke-width="5.2" stroke-linecap="round"/>'
            '<path d="M5 31C11 21 19 21 24 30C29 39 37 39 43 29" fill="none" stroke="{secondary}" stroke-width="5.2" stroke-linecap="round"/>'
        ),
    },
    {
        "id": "leaf_sprout",
        "name": "Botanical Leaf",
        "category": "Sustainability & Health",
        "paths": (
            '<path d="M10 38C10 18 22 8 40 8C40 26 30 38 10 38Z" fill="{secondary}"/>'
            '<path d="M10 38C18 28 28 20 38 11" fill="none" stroke="{primary}" stroke-width="3.4" stroke-linecap="round"/>'
            '<path d="M18 30C15 24 16 17 20 12" fill="none" stroke="{contrast}" stroke-width="2.4" stroke-linecap="round"/>'
        ),
    },
    {
        "id": "diamond_facet",
        "name": "Faceted Diamond",
        "category": "Luxury & Retail",
        "paths": (
            '<polygon points="14,8 34,8 43,19 24,42 5,19" fill="{primary}"/>'
            '<polygon points="14,8 34,8 29,19 19,19" fill="{secondary}"/>'
            '<polygon points="19,19 29,19 24,42" fill="{contrast}" fill-opacity="0.22"/>'
        ),
    },
    {
        "id": "bridge_arch",
        "name": "Span Bridge",
        "category": "Infrastructure & Engineering",
        "paths": (
            '<path d="M6 36V22C6 13.5 14 8 24 8C34 8 42 13.5 42 22V36H35V23C35 17.5 30 14 24 14C18 14 13 17.5 13 23V36H6Z" fill="{primary}"/>'
            '<rect x="6" y="38" width="36" height="4" fill="{secondary}"/>'
        ),
    },
    {
        "id": "circuit_node",
        "name": "Neural Matrix",
        "category": "Technology",
        "paths": (
            '<rect x="13" y="13" width="22" height="22" rx="4" fill="{primary}"/>'
            '<circle cx="24" cy="24" r="5" fill="{secondary}"/>'
            '<path d="M24 5V13M24 35V43M5 24H13M35 24H43" stroke="{primary}" stroke-width="3.2" stroke-linecap="round"/>'
            '<circle cx="24" cy="5" r="2.6" fill="{secondary}"/>'
            '<circle cx="43" cy="24" r="2.6" fill="{secondary}"/>'
        ),
    },
    {
        "id": "flame_spark",
        "name": "Ignite Spark",
        "category": "Energy & Ventures",
        "paths": (
            '<path d="M25 5C33 13 38 20 38 29C38 37 31.8 43 24 43C16.2 43 10 37 10 29C10 22 14.5 16 19 12C18 18 21 21 23 22C21 15 22 10 25 5Z" fill="{primary}"/>'
            '<path d="M24 24C28 27 30 30.5 30 34C30 37.5 27.3 40 24 40C20.7 40 18 37.5 18 34C18 30.5 20 27 24 24Z" fill="{secondary}"/>'
        ),
    },
    {
        "id": "globe_meridian",
        "name": "Global Meridian",
        "category": "Global Trade",
        "paths": (
            '<circle cx="24" cy="24" r="18" fill="none" stroke="{primary}" stroke-width="3.4"/>'
            '<ellipse cx="24" cy="24" rx="8.5" ry="18" fill="none" stroke="{secondary}" stroke-width="2.8"/>'
            '<line x1="6" y1="24" x2="42" y2="24" stroke="{primary}" stroke-width="2.8"/>'
            '<line x1="9" y1="15" x2="39" y2="15" stroke="{primary}" stroke-width="2"/>'
            '<line x1="9" y1="33" x2="39" y2="33" stroke="{primary}" stroke-width="2"/>'
        ),
    },
    {
        "id": "key_vault",
        "name": "Vault Keystone",
        "category": "Trust & Security",
        "paths": (
            '<rect x="7" y="7" width="34" height="34" rx="7" fill="{primary}"/>'
            '<circle cx="24" cy="20" r="6" fill="{secondary}"/>'
            '<path d="M21 24H27L29 35H19L21 24Z" fill="{contrast}"/>'
        ),
    },
    {
        "id": "scales_justice",
        "name": "Lex Balance",
        "category": "Legal & Governance",
        "paths": (
            '<line x1="24" y1="7" x2="24" y2="39" stroke="{primary}" stroke-width="3.4" stroke-linecap="round"/>'
            '<line x1="10" y1="14" x2="38" y2="14" stroke="{primary}" stroke-width="3.4" stroke-linecap="round"/>'
            '<path d="M10 14L5.5 26H14.5L10 14Z" fill="{secondary}"/>'
            '<path d="M38 14L33.5 26H42.5L38 14Z" fill="{secondary}"/>'
            '<rect x="15" y="38" width="18" height="4" rx="1.5" fill="{primary}"/>'
        ),
    },
    {
        "id": "cube_iso",
        "name": "Isometric Cube",
        "category": "Engineering & SaaS",
        "paths": (
            '<polygon points="24,5 41,14.5 24,24 7,14.5" fill="{secondary}"/>'
            '<polygon points="7,14.5 24,24 24,43 7,33.5" fill="{primary}"/>'
            '<polygon points="41,14.5 24,24 24,43 41,33.5" fill="{primary}" fill-opacity="0.72"/>'
        ),
    },
    {
        "id": "bolt_pulse",
        "name": "Kinetic Pulse",
        "category": "Energy & FinTech",
        "paths": (
            '<polygon points="27,4 10,27 22,27 19,44 38,20 26,20" fill="{primary}"/>'
            '<polygon points="27,4 22,19 31,19" fill="{secondary}"/>'
        ),
    },
    {
        "id": "sunburst_horizon",
        "name": "Dawn Horizon",
        "category": "Hospitality & Media",
        "paths": (
            '<path d="M8 31A16 16 0 0 1 40 31Z" fill="{secondary}"/>'
            '<rect x="5" y="34" width="38" height="4.5" rx="2" fill="{primary}"/>'
            '<rect x="11" y="41" width="26" height="3" rx="1.5" fill="{primary}" fill-opacity="0.7"/>'
        ),
    },
    {
        "id": "helix_dna",
        "name": "Vitality Pulse",
        "category": "Healthcare & Biotech",
        "paths": (
            '<rect x="19" y="6" width="10" height="36" rx="2.5" fill="{primary}"/>'
            '<rect x="6" y="19" width="36" height="10" rx="2.5" fill="{primary}"/>'
            '<rect x="19" y="19" width="10" height="10" rx="2" fill="{secondary}"/>'
        ),
    },
    {
        "id": "feather_quill",
        "name": "Editorial Quill",
        "category": "Publishing & Legal",
        "paths": (
            '<path d="M39 7C25 9 14 19 10 38L14 41C16 33 21 29 29 27C35 23 39 16 39 7Z" fill="{primary}"/>'
            '<path d="M10 38L34 13" stroke="{secondary}" stroke-width="2.8" stroke-linecap="round"/>'
        ),
    },
    {
        "id": "anchor_marine",
        "name": "Maritime Crest",
        "category": "Logistics & Trade",
        "paths": (
            '<circle cx="24" cy="11" r="4.5" fill="none" stroke="{secondary}" stroke-width="3.2"/>'
            '<line x1="24" y1="15.5" x2="24" y2="39" stroke="{primary}" stroke-width="3.6" stroke-linecap="round"/>'
            '<line x1="15" y1="21" x2="33" y2="21" stroke="{primary}" stroke-width="3.2" stroke-linecap="round"/>'
            '<path d="M10 30C10 37 16.5 41 24 41C31.5 41 38 37 38 30" fill="none" stroke="{primary}" stroke-width="3.6" stroke-linecap="round"/>'
        ),
    },
    {
        "id": "monogram_frame",
        "name": "Architectural Frame",
        "category": "Corporate & Consulting",
        "paths": (
            '<rect x="6" y="6" width="36" height="36" fill="none" stroke="{primary}" stroke-width="4"/>'
            '<rect x="13" y="13" width="22" height="22" fill="{primary}"/>'
            '<rect x="26" y="6" width="16" height="8" fill="{secondary}"/>'
        ),
    },
]

BRAND_ICONS_BY_ID = {i["id"]: i for i in BRAND_ICONS}

# ---------------------------------------------------------------------------
# 2. Curated Executive Color Palettes
# ---------------------------------------------------------------------------

BRAND_PALETTES: list[dict[str, str]] = [
    {"id": "trustseal_navy", "name": "TrustSeal Navy & Emerald", "primary": "#002769", "secondary": "#02982e", "accent": "#1d4ed8", "dark": "#0f172a", "light": "#f4f7fc"},
    {"id": "sovereign_gold", "name": "Sovereign Midnight & Gold", "primary": "#0b1930", "secondary": "#c59b27", "accent": "#1e3a5f", "dark": "#070f1d", "light": "#f8f6f0"},
    {"id": "swiss_crimson", "name": "Swiss Crimson & Slate", "primary": "#991b1b", "secondary": "#0f172a", "accent": "#dc2626", "dark": "#111827", "light": "#faf7f7"},
    {"id": "nordic_forest", "name": "Nordic Forest & Sage", "primary": "#064e3b", "secondary": "#10b981", "accent": "#047857", "dark": "#052e16", "light": "#f2faf6"},
    {"id": "fintech_indigo", "name": "FinTech Indigo & Cyan", "primary": "#1e1b4b", "secondary": "#0284c7", "accent": "#4338ca", "dark": "#0f172a", "light": "#f3f6fd"},
    {"id": "obsidian_champagne", "name": "Obsidian & Champagne", "primary": "#18181b", "secondary": "#b48a4e", "accent": "#3f3f46", "dark": "#09090b", "light": "#f9f8f6"},
    {"id": "medtech_teal", "name": "MedTech Deep Teal", "primary": "#115e59", "secondary": "#0ea5e9", "accent": "#0f766e", "dark": "#042f2e", "light": "#f0fdfa"},
    {"id": "energy_amber", "name": "Industrial Navy & Amber", "primary": "#172554", "secondary": "#d97706", "accent": "#1d4ed8", "dark": "#0c142c", "light": "#fdfaf3"},
    {"id": "burgundy_heritage", "name": "Heritage Burgundy & Bronze", "primary": "#5b1525", "secondary": "#b07d48", "accent": "#881337", "dark": "#260910", "light": "#fbf7f8"},
    {"id": "cobalt_electric", "name": "Cobalt Velocity", "primary": "#0038a8", "secondary": "#059669", "accent": "#2563eb", "dark": "#0a1633", "light": "#f2f6ff"},
    {"id": "terracotta_studio", "name": "Architectural Terracotta", "primary": "#9a3412", "secondary": "#1e293b", "accent": "#c2410c", "dark": "#1c1917", "light": "#faf6f3"},
    {"id": "graphite_minimal", "name": "Graphite Architectural", "primary": "#1e293b", "secondary": "#0284c7", "accent": "#334155", "dark": "#0f172a", "light": "#f8fafc"},
]

FONT_PAIRINGS: list[dict[str, str]] = [
    {"id": "inter_clean", "name": "Inter Executive Sans", "heading": "Inter, -apple-system, BlinkMacSystemFont, sans-serif", "body": "Inter, -apple-system, sans-serif", "label": "Modern Corporate"},
    {"id": "georgia_editorial", "name": "Georgia Heritage Serif", "heading": "Georgia, 'Times New Roman', serif", "body": "Inter, -apple-system, sans-serif", "label": "Legal & Advisory"},
    {"id": "helvetica_swiss", "name": "Helvetica Swiss Grid", "heading": "'Helvetica Neue', Helvetica, Arial, sans-serif", "body": "'Helvetica Neue', Arial, sans-serif", "label": "Swiss Architectural"},
    {"id": "futura_geo", "name": "Avenir Geometric", "heading": "Avenir Next, Avenir, 'Segoe UI', sans-serif", "body": "Inter, sans-serif", "label": "Tech & SaaS"},
    {"id": "palatino_lux", "name": "Palatino Luxury Serif", "heading": "'Palatino Linotype', Palatino, Georgia, serif", "body": "'Helvetica Neue', sans-serif", "label": "Luxury & Finance"},
    {"id": "trebuchet_bold", "name": "Trebuchet Industrial", "heading": "'Trebuchet MS', 'Segoe UI', sans-serif", "body": "Inter, sans-serif", "label": "Engineering & Energy"},
]

INDUSTRIES = [
    "Technology & SaaS",
    "Finance, Banking & SACCO",
    "Legal, Audit & Governance",
    "Engineering & Construction",
    "Healthcare & Life Sciences",
    "Logistics, Fleet & Trade",
    "Consulting & Advisory",
    "Energy & Sustainability",
    "Real Estate & Architecture",
    "Hospitality & Retail",
]

MOCKUP_CATALOG: list[dict[str, str]] = [
    {"id": "business_card", "name": "Executive Business Cards", "category": "Stationery"},
    {"id": "pen", "name": "Engraved Corporate Pen", "category": "Desk & Gifts"},
    {"id": "tshirt", "name": "Branded Polo / T-Shirt", "category": "Apparel"},
    {"id": "cap", "name": "Embroidered Corporate Cap", "category": "Apparel"},
    {"id": "car", "name": "Company Fleet Vehicle Wrap", "category": "Fleet & Mobility"},
    {"id": "billboard", "name": "Highway Outdoor Billboard", "category": "Out-of-Home"},
    {"id": "mug", "name": "Ceramic Executive Mug", "category": "Desk & Gifts"},
    {"id": "tote", "name": "Conference Canvas Tote", "category": "Events"},
    {"id": "office_wall", "name": "3D Reception Wall Signage", "category": "Architecture"},
    {"id": "social_kit", "name": "Mobile App Icon & Social Header", "category": "Digital"},
]

# ---------------------------------------------------------------------------
# 3. Color Conversion Helpers (HEX -> RGB, CMYK)
# ---------------------------------------------------------------------------

def sanitize_hex(color: str, fallback: str = "#002769") -> str:
    c = (color or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", c):
        return c.lower()
    if re.fullmatch(r"#[0-9a-fA-F]{3}", c):
        return ("#" + "".join(ch * 2 for ch in c[1:])).lower()
    return fallback


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = sanitize_hex(hex_color).lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_cmyk(hex_color: str) -> tuple[int, int, int, int]:
    r, g, b = (v / 255.0 for v in hex_to_rgb(hex_color))
    k = 1.0 - max(r, g, b)
    if k >= 0.999:
        return 0, 0, 0, 100
    c = (1.0 - r - k) / (1.0 - k)
    m = (1.0 - g - k) / (1.0 - k)
    y = (1.0 - b - k) / (1.0 - k)
    return round(c * 100), round(m * 100), round(y * 100), round(k * 100)


def color_spec(name: str, role: str, hex_color: str) -> dict[str, Any]:
    h = sanitize_hex(hex_color)
    r, g, b = hex_to_rgb(h)
    c, m, y, k = hex_to_cmyk(h)
    return {
        "name": name,
        "role": role,
        "hex": h.upper(),
        "rgb": f"rgb({r}, {g}, {b})",
        "cmyk": f"C{c} M{m} Y{y} K{k}",
    }


def _initials(brand_name: str) -> str:
    words = [w for w in re.split(r"[\s\-_&]+", (brand_name or "TS").strip()) if w]
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper()
    return "TS"


# ---------------------------------------------------------------------------
# 4. Precision Vector SVG Logo Renderer (4 Production Variants)
# ---------------------------------------------------------------------------

def render_logo_svg(
    *,
    brand_name: str,
    tagline: str = "",
    icon_id: str = "shield_check",
    layout: str = "horizontal",
    primary_color: str = "#002769",
    secondary_color: str = "#02982e",
    dark_color: str = "#0f172a",
    font_heading: str = "Inter, -apple-system, sans-serif",
    letter_spacing: float = 1.5,
    mode: str = "primary",
) -> str:
    """Render a crisp, standalone scalable SVG logo.

    ``mode``: ``primary`` | ``mono_dark`` | ``mono_light`` | ``icon_only``
    """
    name = html.escape((brand_name or "TRUSTSEAL").strip())
    tag = html.escape((tagline or "").strip())
    p = sanitize_hex(primary_color, "#002769")
    s = sanitize_hex(secondary_color, "#02982e")
    d = sanitize_hex(dark_color, "#0f172a")
    ff = html.escape(font_heading or "Inter, sans-serif", quote=False).replace('"', "'")

    if mode == "mono_dark":
        icon_p, icon_s, icon_c, txt_main, txt_sub = d, d, "#ffffff", d, d
    elif mode == "mono_light":
        icon_p, icon_s, icon_c, txt_main, txt_sub = "#ffffff", "#ffffff", p, "#ffffff", "rgba(255,255,255,0.82)"
    else:
        icon_p, icon_s, icon_c, txt_main, txt_sub = p, s, "#ffffff", p, "#475569"

    icon = BRAND_ICONS_BY_ID.get(icon_id, BRAND_ICONS[0])
    mark_inner = icon["paths"].format(primary=icon_p, secondary=icon_s, contrast=icon_c)

    if mode == "icon_only":
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" role="img" aria-label="{name} Mark">'
            f'<g transform="translate(12,12) scale(1.5)">{mark_inner}</g>'
            f'</svg>'
        )

    ls = f"{float(letter_spacing):.1f}"
    name_len = max(len(brand_name or "TRUSTSEAL"), 4)
    if name_len <= 12:
        title_fs = 34
    elif name_len <= 17:
        title_fs = 26
    elif name_len <= 22:
        title_fs = 21
    else:
        title_fs = 17

    if layout == "stacked":
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 220" role="img" aria-label="{name}">'
            f'<g transform="translate(168,22) scale(1.75)">{mark_inner}</g>'
            f'<text x="210" y="152" text-anchor="middle" font-family="{ff}" font-size="{title_fs}" font-weight="800" letter-spacing="{ls}" fill="{txt_main}">{name.upper()}</text>'
            + (f'<text x="210" y="182" text-anchor="middle" font-family="{ff}" font-size="13" font-weight="600" letter-spacing="2.4" fill="{txt_sub}">{tag.upper()}</text>' if tag else "")
            + '</svg>'
        )

    if layout == "emblem":
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 320" role="img" aria-label="{name}">'
            f'<circle cx="160" cy="160" r="144" fill="none" stroke="{icon_p}" stroke-width="5"/>'
            f'<circle cx="160" cy="160" r="133" fill="none" stroke="{icon_s}" stroke-width="1.8" stroke-dasharray="4 4"/>'
            f'<g transform="translate(118,52) scale(1.75)">{mark_inner}</g>'
            f'<text x="160" y="182" text-anchor="middle" font-family="{ff}" font-size="{min(title_fs, 26)}" font-weight="800" letter-spacing="{ls}" fill="{txt_main}">{name.upper()}</text>'
            + (f'<text x="160" y="210" text-anchor="middle" font-family="{ff}" font-size="11.5" font-weight="600" letter-spacing="2.2" fill="{txt_sub}">{tag.upper()}</text>' if tag else "")
            + f'<line x1="108" y1="232" x2="212" y2="232" stroke="{icon_s}" stroke-width="2.5"/>'
            + '</svg>'
        )

    if layout == "monogram":
        init = html.escape(_initials(brand_name))
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 460 130" role="img" aria-label="{name}">'
            f'<rect x="18" y="18" width="94" height="94" rx="12" fill="{icon_p}"/>'
            f'<rect x="18" y="102" width="94" height="10" rx="2" fill="{icon_s}"/>'
            f'<text x="65" y="76" text-anchor="middle" font-family="{ff}" font-size="40" font-weight="800" letter-spacing="2" fill="{icon_c}">{init}</text>'
            f'<text x="134" y="{66 if tag else 76}" font-family="{ff}" font-size="{title_fs}" font-weight="800" letter-spacing="{ls}" fill="{txt_main}">{name.upper()}</text>'
            + (f'<text x="135" y="92" font-family="{ff}" font-size="12.5" font-weight="600" letter-spacing="2.2" fill="{txt_sub}">{tag.upper()}</text>' if tag else "")
            + '</svg>'
        )

    if layout == "wordmark":
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 480 124" role="img" aria-label="{name}">'
            f'<text x="240" y="{64 if tag else 74}" text-anchor="middle" font-family="{ff}" font-size="{title_fs + 6}" font-weight="800" letter-spacing="{float(letter_spacing) + 1.5:.1f}" fill="{txt_main}">{name.upper()}</text>'
            f'<rect x="176" y="{76 if tag else 88}" width="128" height="3.5" fill="{icon_s}"/>'
            + (f'<text x="240" y="102" text-anchor="middle" font-family="{ff}" font-size="12.5" font-weight="600" letter-spacing="2.8" fill="{txt_sub}">{tag.upper()}</text>' if tag else "")
            + '</svg>'
        )

    # Default: horizontal corporate lockup
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 120" role="img" aria-label="{name}">'
        f'<g transform="translate(18,16) scale(1.85)">{mark_inner}</g>'
        f'<text x="122" y="{62 if tag else 72}" font-family="{ff}" font-size="{title_fs}" font-weight="800" letter-spacing="{ls}" fill="{txt_main}">{name.upper()}</text>'
        + (f'<text x="123" y="88" font-family="{ff}" font-size="12.5" font-weight="600" letter-spacing="2.3" fill="{txt_sub}">{tag.upper()}</text>' if tag else "")
        + '</svg>'
    )


def render_logo_variants(params: dict[str, Any]) -> dict[str, str]:
    common = dict(
        brand_name=params.get("brand_name") or "TRUSTSEAL",
        tagline=params.get("tagline") or "",
        icon_id=params.get("icon_id") or "shield_check",
        layout=params.get("logo_layout") or "horizontal",
        primary_color=params.get("primary_color") or "#002769",
        secondary_color=params.get("secondary_color") or "#02982e",
        dark_color=params.get("dark_color") or "#0f172a",
        font_heading=params.get("font_heading") or "Inter, -apple-system, sans-serif",
        letter_spacing=float(params.get("letter_spacing", 1.5)),
    )
    return {
        "primary_svg": render_logo_svg(**common, mode="primary"),
        "mono_dark_svg": render_logo_svg(**common, mode="mono_dark"),
        "mono_light_svg": render_logo_svg(**common, mode="mono_light"),
        "icon_only_svg": render_logo_svg(**common, mode="icon_only"),
    }


# ---------------------------------------------------------------------------
# 5. Smashing-Logo-Style Multi-Concept Generator (12 Distinct Concepts)
# ---------------------------------------------------------------------------

def generate_logo_concepts(
    *,
    brand_name: str,
    tagline: str = "",
    industry: str = "Technology & SaaS",
    archetype: str = "modern_corporate",
    count: int = 12,
) -> list[dict[str, Any]]:
    """Generate 12 distinct, high-craft brand concepts ready for instant customization."""
    seed = int(hashlib.sha256(f"{brand_name}|{industry}|{archetype}".encode("utf-8")).hexdigest()[:8], 16)
    layouts = ["horizontal", "stacked", "monogram", "emblem", "wordmark", "horizontal"]

    # Prioritize icons aligned with industry first, then diversify across geometric marks
    ind_low = (industry or "").lower()
    preferred: list[str] = []
    if "finance" in ind_low or "bank" in ind_low or "sacco" in ind_low:
        preferred = ["shield_check", "pillar_monolith", "apex_peak", "crown_crest", "key_vault", "monogram_frame"]
    elif "legal" in ind_low or "audit" in ind_low or "gov" in ind_low:
        preferred = ["scales_justice", "shield_check", "crown_crest", "feather_quill", "pillar_monolith", "monogram_frame"]
    elif "health" in ind_low or "life" in ind_low:
        preferred = ["helix_dna", "leaf_sprout", "shield_check", "orbit_ring", "wave_flow", "sunburst_horizon"]
    elif "energy" in ind_low or "sustain" in ind_low:
        preferred = ["leaf_sprout", "flame_spark", "bolt_pulse", "sunburst_horizon", "globe_meridian", "prism_hex"]
    elif "logistics" in ind_low or "fleet" in ind_low or "trade" in ind_low:
        preferred = ["globe_meridian", "wave_flow", "anchor_marine", "compass_star", "bridge_arch", "bolt_pulse"]
    elif "engineer" in ind_low or "construct" in ind_low or "real estate" in ind_low:
        preferred = ["bridge_arch", "pillar_monolith", "cube_iso", "apex_peak", "prism_hex", "monogram_frame"]
    else:
        preferred = ["shield_check", "prism_hex", "cube_iso", "circuit_node", "infinity_arc", "orbit_ring"]

    all_icon_ids = preferred + [i["id"] for i in BRAND_ICONS if i["id"] not in preferred]

    concepts: list[dict[str, Any]] = []
    for idx in range(min(count, 12)):
        pal = BRAND_PALETTES[(idx + (seed % 3)) % len(BRAND_PALETTES)]
        icon_id = all_icon_ids[idx % len(all_icon_ids)]
        font = FONT_PAIRINGS[(idx + (seed % 2)) % len(FONT_PAIRINGS)]
        layout = layouts[idx % len(layouts)]
        ls = 2.0 if layout in ("wordmark", "stacked") else 1.4
        params = {
            "brand_name": brand_name,
            "tagline": tagline,
            "industry": industry,
            "archetype": archetype,
            "icon_id": icon_id,
            "logo_layout": layout,
            "font_heading": font["heading"],
            "font_body": font["body"],
            "letter_spacing": ls,
            "primary_color": pal["primary"],
            "secondary_color": pal["secondary"],
            "accent_color": pal["accent"],
            "dark_color": pal["dark"],
            "light_color": pal["light"],
        }
        svgs = render_logo_variants(params)
        concepts.append({
            "concept_index": idx + 1,
            "concept_label": f"{pal['name']} · {layout.title()}",
            "palette_name": pal["name"],
            "font_name": font["name"],
            **params,
            **svgs,
        })
    return concepts


# ---------------------------------------------------------------------------
# 6. Complete Brand Guidelines Book Generator
# ---------------------------------------------------------------------------

def build_brand_guidelines(params: dict[str, Any]) -> dict[str, Any]:
    brand = (params.get("brand_name") or "TRUSTSEAL").strip()
    tagline = (params.get("tagline") or "Verified Integrity").strip()
    industry = (params.get("industry") or "Enterprise").strip()
    p = sanitize_hex(params.get("primary_color") or "#002769")
    s = sanitize_hex(params.get("secondary_color") or "#02982e")
    a = sanitize_hex(params.get("accent_color") or "#1d4ed8")
    d = sanitize_hex(params.get("dark_color") or "#0f172a")
    l = sanitize_hex(params.get("light_color") or "#f4f7fc")
    fh = params.get("font_heading") or "Inter"
    fb = params.get("font_body") or "Inter"

    return {
        "brand_name": brand,
        "tagline": tagline,
        "industry": industry,
        "version": "1.0",
        "colors": [
            color_spec("Primary Brand", "Headers, primary logos, key actions, vehicle & signage base", p),
            color_spec("Secondary / Signal", "Accents, verification indicators, embroidery highlights", s),
            color_spec("Supporting Accent", "Interactive highlights, secondary charts & digital links", a),
            color_spec("Executive Ink", "Primary typography, monochrome print & dark apparel", d),
            color_spec("Architectural Surface", "Clean canvas backgrounds, KPI strips & stationery tints", l),
        ],
        "typography": {
            "heading_font": fh,
            "body_font": fb,
            "scale": [
                {"role": "Display / Billboard", "size": "48–64px", "weight": "700–800", "tracking": "-0.03em"},
                {"role": "Section Heading", "size": "24–32px", "weight": "700", "tracking": "-0.02em"},
                {"role": "Subheading / Card", "size": "16–18px", "weight": "600", "tracking": "-0.01em"},
                {"role": "Body Copy", "size": "14–16px", "weight": "400", "tracking": "0em"},
                {"role": "Caption / Code", "size": "12–13px", "weight": "600", "tracking": "0.05em"},
            ],
        },
        "clear_space": {
            "rule": "Maintain a minimum clear space equal to 1× the height of the primary mark icon around all four edges of the logo.",
            "min_digital_px": 120,
            "min_print_mm": 24,
            "min_icon_px": 24,
        },
        "dos": [
            "Use the official full-color vector SVG on crisp white or light architectural surfaces.",
            "Use the Reversed White lockup on Deep Brand Navy, dark charcoal apparel, and night-lit signage.",
            "Use the Square Icon Mark for mobile app icons, favicons, embroidered caps, and pen clips.",
            "Preserve original proportions and official HEX/CMYK color formulas across all print vendors.",
        ],
        "donts": [
            "Do not stretch, skew, rotate, or alter the aspect ratio of the brand mark or wordmark.",
            "Do not apply drop shadows, neon glows, or unapproved gradients over the official logo.",
            "Do not place the dark primary lockup over busy photography without a solid contrast backing.",
            "Do not substitute unapproved display fonts or alter letter-spacing outside the brand book.",
        ],
    }
