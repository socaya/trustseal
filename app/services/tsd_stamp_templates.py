"""Built-in TSD stamp templates.

A starter gallery of common stamp designs — pre-baked layout JSON +
rendered SVG — that users can instantiate as their own stamps and
then tweak in the Studio. Templates are tenant-free: every tenant
sees the same catalogue, and the ``POST /api/tsd-stamps/from-template``
endpoint copies the layout + SVG into a new ``TSDStamp`` row.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math


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

def _uid(*parts: object) -> str:
    raw = "|".join(str(p) for p in parts).encode("utf-8", "ignore")
    return hashlib.md5(raw).hexdigest()[:7]


def _esc_xml(val: str) -> str:
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fit_size(text: str, max_px: float, base_px: float, letter_spacing: float = 1.5, char_ratio: float = 0.64) -> int:
    n = max(1, len(text))
    est = n * (base_px * char_ratio + letter_spacing)
    if est <= max_px:
        return max(8, round(base_px))
    fitted = (max_px / n - letter_spacing) / char_ratio
    return max(8, min(round(base_px), round(fitted)))


def _seal_svg(*, top: str, bottom: str, center_lines: list[str], color: str,
              border: str, logo_url: str = "", logo_size: int = 74) -> str:
    uid = _uid("seal", top, bottom, "|".join(center_lines), color, border, logo_url)

    def arc(id_: str, text: str, r: int, side: str) -> str:
        t_up = text.upper()
        arc_len = math.pi * r * 0.86
        fs = _fit_size(t_up, arc_len, 18, letter_spacing=1.8, char_ratio=0.68)
        if side == "top":
            r_eff = r - 5
            d = f"M {-r_eff} 0 A {r_eff} {r_eff} 0 0 1 {r_eff} 0"
        else:
            r_eff = r + 7
            d = f"M {-r_eff} 0 A {r_eff} {r_eff} 0 0 0 {r_eff} 0"
        return (
            f'<defs><path id="{id_}" d="{d}" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="{fs}" font-weight="700" '
            f'letter-spacing="1.8" fill="{color}">'
            f'<textPath href="#{id_}" startOffset="50%" text-anchor="middle">'
            f'{_esc_xml(t_up)}</textPath></text>'
        )

    if border == "double":
        outer = (
            f'<circle r="140" fill="none" stroke="{color}" stroke-width="3.2"/>'
            f'<circle r="129" fill="none" stroke="{color}" stroke-width="1.2"/>'
            f'<circle r="86" fill="none" stroke="{color}" stroke-width="1"/>'
        )
    elif border == "dashed":
        outer = (
            f'<circle r="140" fill="none" stroke="{color}" '
            f'stroke-width="3" stroke-dasharray="6,4"/>'
            f'<circle r="86" fill="none" stroke="{color}" stroke-width="1"/>'
        )
    else:
        outer = (
            f'<circle r="140" fill="none" stroke="{color}" stroke-width="3.2"/>'
            f'<circle r="86" fill="none" stroke="{color}" stroke-width="1"/>'
        )

    logo_el = ""
    if logo_url:
        ls = max(36, min(110, logo_size))
        ly = -ls / 2 - (16 if center_lines else 0)
        logo_el = f'<image href="{_esc_xml(logo_url)}" x="{-ls/2:.1f}" y="{ly:.1f}" width="{ls}" height="{ls}" preserveAspectRatio="xMidYMid meet"/>'

    lines = center_lines[:4]
    if logo_url and lines:
        cy0 = 34 if len(lines) == 1 else 26
        step = 18
    else:
        cy0 = 6 if len(lines) == 1 else (-6 if len(lines) == 2 else -20)
        step = 22
    center = ""
    for i, line in enumerate(lines):
        y = cy0 + i * step
        chord = 2 * math.sqrt(max(100, 80 * 80 - y * y)) * 0.90
        size = _fit_size(line, chord, 14 if logo_url else 19, letter_spacing=1.0, char_ratio=0.64)
        center += (
            f'<text y="{y}" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{size}" font-weight="700" fill="{color}">'
            f'{_esc_xml(line)}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" '
        'width="160" height="160" data-stamp-root="1">'
        f'{outer}'
        f'{arc(f"tp-{uid}-top", top, 114, "top")}'
        f'{arc(f"tp-{uid}-bot", bottom, 114, "bottom")}'
        f'{logo_el}{center}'
        '</svg>'
    )


def _company_dated_svg(*, company: str, tagline: str, verb: str, color: str,
                       logo_url: str = "") -> str:
    uid = _uid("cd", company, tagline, verb, color, logo_url)

    def arc(id_: str, text: str, r: int, side: str) -> str:
        t_up = text.upper()
        arc_len = math.pi * r * 0.86
        fs = _fit_size(t_up, arc_len, 18, letter_spacing=1.8, char_ratio=0.68)
        if side == "top":
            r_eff = r - 5
            d = f"M {-r_eff} 0 A {r_eff} {r_eff} 0 0 1 {r_eff} 0"
        else:
            r_eff = r + 7
            d = f"M {-r_eff} 0 A {r_eff} {r_eff} 0 0 0 {r_eff} 0"
        return (
            f'<defs><path id="{id_}" d="{d}" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="{fs}" font-weight="700" '
            f'letter-spacing="1.8" fill="{color}">'
            f'<textPath href="#{id_}" startOffset="50%" text-anchor="middle">'
            f'{_esc_xml(t_up)}</textPath></text>'
        )

    outer = (
        f'<circle r="140" fill="none" stroke="{color}" stroke-width="3.2"/>'
        f'<circle r="129" fill="none" stroke="{color}" stroke-width="1.2"/>'
        f'<circle r="88" fill="none" stroke="{color}" stroke-width="1"/>'
    )
    logo_el = ""
    if logo_url:
        logo_el = f'<image href="{_esc_xml(logo_url)}" x="-22" y="-66" width="44" height="44" preserveAspectRatio="xMidYMid meet"/>'
        verb_y = -6
        date_y = 22
    else:
        verb_y = -12
        date_y = 18

    verb_el = (
        f'<text y="{verb_y}" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="10" font-weight="700" fill="{color}" letter-spacing="2.5">{_esc_xml(verb.upper())}</text>'
    ) if verb else f'<line x1="-68" y1="{verb_y - 2}" x2="68" y2="{verb_y - 2}" stroke="{color}" stroke-width="1"/>'
    date_el = (
        f'<text y="{date_y}" text-anchor="middle" font-family="Courier New, monospace" '
        f'font-size="17" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-160 -160 320 320" '
        'width="160" height="160" data-stamp-root="1">'
        f'{outer}'
        f'{arc(f"tp-{uid}-top", company, 114, "top")}'
        f'{arc(f"tp-{uid}-bot", tagline, 114, "bottom")}'
        f'{logo_el}{verb_el}{date_el}'
        '</svg>'
    )


def _company_rect_svg(
    *,
    company: str,
    subtitle: str = "",
    department: str = "",
    address1: str = "",
    address2: str = "",
    reg_line: str = "",
    tax_line: str = "",
    contact: str = "",
    custom_line: str = "",
    signatory_prefix: str = "",
    signatory_title: str = "",
    show_signatory: bool = False,
    show_reference: bool = True,
    reference_label: str = "DATE",
    date_format: str = "DD MMM YYYY",
    color: str = "#0f3b82",
    border_style: str = "rounded",
    border_thickness: int = 3,
    corner_radius: int = 6,
    header_bar: bool = False,
    divider_rule: bool = True,
    width_mm: int = 75,
    height_mm: int = 38,
    logo_url: str = "",
) -> str:
    w_px = round(width_mm * 3.78)
    h_px = round(height_mm * 3.78)
    vw, vh = 760, 420
    t = border_thickness

    # Border
    rx = corner_radius * 3
    if border_style == "double":
        border_el = (
            f'<rect x="{t/2}" y="{t/2}" width="{vw - t}" height="{vh - t}" rx="{rx}" fill="none" stroke="{color}" stroke-width="{t}"/>'
            f'<rect x="{t + 6}" y="{t + 6}" width="{vw - 2*(t+6)}" height="{vh - 2*(t+6)}" rx="{max(0, rx-4)}" fill="none" stroke="{color}" stroke-width="1"/>'
        )
    elif border_style == "solid":
        border_el = f'<rect x="{t/2}" y="{t/2}" width="{vw - t}" height="{vh - t}" fill="none" stroke="{color}" stroke-width="{t}"/>'
    elif border_style == "shadowed":
        border_el = (
            f'<rect x="6" y="6" width="{vw - 6}" height="{vh - 6}" rx="{rx}" fill="#00000012"/>'
            f'<rect x="2" y="2" width="{vw - 8}" height="{vh - 8}" rx="{rx}" fill="none" stroke="{color}" stroke-width="{t}"/>'
        )
    else:  # rounded
        border_el = f'<rect x="{t/2}" y="{t/2}" width="{vw - t}" height="{vh - t}" rx="{rx}" fill="none" stroke="{color}" stroke-width="{t}"/>'

    def _esc(val: str) -> str:
        return _esc_xml(val)

    inner_els = [border_el]
    y_cursor = 24

    if logo_url and not header_bar:
        inner_els.append(f'<image href="{_esc(logo_url)}" x="290" y="16" width="180" height="46" preserveAspectRatio="xMidYMid meet"/>')
        y_cursor = 68

    if header_bar and company:
        bar_h = 56
        inner_els.append(f'<rect x="{t}" y="{t}" width="{vw - 2*t}" height="{bar_h}" rx="{max(0, rx-2)}" fill="{color}"/>')
        cfs = _fit_size(company.upper(), vw - 80, 22, letter_spacing=2.0, char_ratio=0.72)
        inner_els.append(
            f'<text x="380" y="38" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            f'font-size="{cfs}" font-weight="900" fill="#ffffff" letter-spacing="2">{_esc(company.upper())}</text>'
        )
        y_cursor = bar_h + 16
        if logo_url:
            inner_els.append(f'<image href="{_esc(logo_url)}" x="300" y="{y_cursor}" width="160" height="38" preserveAspectRatio="xMidYMid meet"/>')
            y_cursor += 44
    elif company:
        cfs = _fit_size(company.upper(), vw - 80, 24, letter_spacing=2.0, char_ratio=0.72)
        inner_els.append(
            f'<text x="380" y="{y_cursor + 24}" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            f'font-size="{cfs}" font-weight="900" fill="{color}" letter-spacing="2">{_esc(company.upper())}</text>'
        )
        y_cursor += 34

    if subtitle:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="13" font-weight="700" fill="{color}" letter-spacing="1.5">{_esc(subtitle.upper())}</text>'
        )
        y_cursor += 22

    if department:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="14" font-weight="800" fill="{color}" letter-spacing="2">★ {_esc(department.upper())} ★</text>'
        )
        y_cursor += 24

    if divider_rule:
        inner_els.append(f'<line x1="40" y1="{y_cursor + 4}" x2="720" y2="{y_cursor + 4}" stroke="{color}" stroke-width="1.2"/>')
        y_cursor += 16

    if custom_line:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="12" font-weight="600" fill="{color}" letter-spacing="1">{_esc(custom_line)}</text>'
        )
        y_cursor += 20

    if address1:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="13" fill="{color}">{_esc(address1)}</text>'
        )
        y_cursor += 20

    if address2:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="13" fill="{color}">{_esc(address2)}</text>'
        )
        y_cursor += 20

    if reg_line or tax_line:
        combined = "  ·  ".join(filter(None, [reg_line, tax_line]))
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="13" font-weight="700" fill="{color}">{_esc(combined)}</text>'
        )
        y_cursor += 22

    if contact:
        inner_els.append(
            f'<text x="380" y="{y_cursor + 14}" text-anchor="middle" font-family="Arial, sans-serif" '
            f'font-size="12" fill="{color}">{_esc(contact)}</text>'
        )
        y_cursor += 20

    if show_signatory:
        sig_y = max(y_cursor + 24, 320)
        if signatory_prefix:
            inner_els.append(
                f'<text x="380" y="{sig_y - 12}" text-anchor="middle" font-family="Arial, sans-serif" '
                f'font-size="11" font-weight="600" fill="{color}" letter-spacing="1">{_esc(signatory_prefix)}</text>'
            )
        inner_els.append(f'<line x1="120" y1="{sig_y}" x2="640" y2="{sig_y}" stroke="{color}" stroke-width="1.5"/>')
        if signatory_title:
            inner_els.append(
                f'<text x="380" y="{sig_y + 18}" text-anchor="middle" font-family="Arial, sans-serif" '
                f'font-size="12" font-weight="700" fill="{color}" letter-spacing="1">{_esc(signatory_title.upper())}</text>'
            )

    if show_reference:
        ref_y = 390
        inner_els.append(
            f'<text x="36" y="{ref_y}" font-family="Courier New, monospace" font-size="13" font-weight="700" fill="{color}" letter-spacing="1">{_esc(reference_label)}</text>'
            f'<text x="724" y="{ref_y}" text-anchor="end" font-family="Courier New, monospace" font-size="13" font-weight="700" fill="{color}" letter-spacing="1" data-stamp-date="{_esc(date_format)}">[{_esc(date_format)}]</text>'
        )

    content = "".join(inner_els)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" '
        f'width="{w_px}" height="{h_px}" data-stamp-root="1">'
        f'{content}'
        f'</svg>'
    )


def _date_svg(*, label: str, color: str) -> str:
    lfs = _fit_size(label, 276, 26, letter_spacing=2.5, char_ratio=0.72)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 170" '
        'width="200" height="106" data-stamp-root="1">'
        f'<rect x="4" y="4" width="312" height="162" fill="none" stroke="{color}" stroke-width="3" rx="4"/>'
        f'<rect x="12" y="14" width="296" height="40" fill="{color}"/>'
        f'<text x="160" y="42" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
        f'font-size="{lfs}" fill="#fff" letter-spacing="2.5">{_esc_xml(label)}</text>'
        f'<text x="160" y="100" text-anchor="middle" font-family="Courier New, monospace" '
        f'font-size="26" font-weight="700" fill="{color}" data-stamp-date="DD MMM YYYY">[DD MMM YYYY]</text>'
        f'<line x1="40" y1="130" x2="280" y2="130" stroke="{color}" stroke-width="1"/>'
        f'<text x="160" y="150" text-anchor="middle" font-family="Arial, sans-serif" '
        f'font-size="10" fill="{color}" letter-spacing="2">BY ____________________________</text>'
        '</svg>'
    )


def _rubber_svg(
    *,
    text: str = "",
    lines: list[str] | None = None,
    color: str = "#0f3b82",
    shape: str = "rect",
    width_mm: float = 70,
    height_mm: float = 28,
    double_border: bool = False,
    logo_url: str = "",
) -> str:
    aspect = max(0.4, min(4.0, width_mm / max(1.0, height_mm)))
    is_sq = shape in ("circle", "hexagon", "octagon", "star", "triangle", "pentagon", "shield")
    vh = 320 if is_sq else 200
    vw = round(vh * (1.0 if shape == "shield" else aspect))
    cx, cy = vw / 2, vh / 2
    pad_x = max(12, round(vw * 0.05))
    pad_y = max(12, round(vh * 0.06))
    rx, ry = cx - pad_x, cy - pad_y
    r_poly = min(rx, ry)

    if shape == "oval":
        outer = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="{color}" stroke-width="4"/>'
        if double_border:
            outer += f'<ellipse cx="{cx}" cy="{cy}" rx="{max(8, rx - 9)}" ry="{max(8, ry - 9)}" fill="none" stroke="{color}" stroke-width="1.6"/>'
    elif shape == "circle":
        outer = f'<circle cx="{cx}" cy="{cy}" r="{r_poly}" fill="none" stroke="{color}" stroke-width="4"/>'
        if double_border:
            outer += f'<circle cx="{cx}" cy="{cy}" r="{max(8, r_poly - 9)}" fill="none" stroke="{color}" stroke-width="1.6"/>'
    elif shape in ("hexagon", "octagon"):
        sides = 6 if shape == "hexagon" else 8
        rot = 0 if sides == 6 else 22.5
        def _poly(rad: float, sw: float) -> str:
            pts = " ".join(
                f"{cx + math.cos(math.radians(rot + i * 360 / sides)) * rad:.1f},"
                f"{cy + math.sin(math.radians(rot + i * 360 / sides)) * rad:.1f}"
                for i in range(sides)
            )
            return f'<polygon points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}"/>'
        outer = _poly(r_poly, 4) + (_poly(max(10, r_poly - 9), 1.6) if double_border else "")
    elif shape == "shield":
        sx0, sx1 = pad_x + 14, vw - pad_x - 14
        sy0, sy_mid, sy_bot = pad_y + 4, vh * 0.56, vh - pad_y - 4
        def _shield_path(inset: float, sw: float) -> str:
            x0, x1 = sx0 + inset, sx1 - inset
            y0, ym, yb = sy0 + inset, sy_mid, sy_bot - inset
            return (
                f'<path d="M {x0:.1f} {y0:.1f} L {x1:.1f} {y0:.1f} '
                f'L {x1:.1f} {ym:.1f} Q {x1:.1f} {yb - 20:.1f} {cx:.1f} {yb:.1f} '
                f'Q {x0:.1f} {yb - 20:.1f} {x0:.1f} {ym:.1f} Z" '
                f'fill="none" stroke="{color}" stroke-width="{sw}"/>'
            )
        outer = _shield_path(0, 4) + (_shield_path(9, 1.6) if double_border else "")
    elif shape == "rounded":
        cr = round(min(rx, ry) * 0.22)
        outer = f'<rect x="{pad_x}" y="{pad_y}" width="{vw - pad_x * 2}" height="{vh - pad_y * 2}" rx="{cr}" fill="none" stroke="{color}" stroke-width="4"/>'
        if double_border:
            i = 9
            outer += f'<rect x="{pad_x + i}" y="{pad_y + i}" width="{vw - (pad_x + i) * 2}" height="{vh - (pad_y + i) * 2}" rx="{max(0, cr - 4)}" fill="none" stroke="{color}" stroke-width="1.6"/>'
    else:
        outer = f'<rect x="{pad_x}" y="{pad_y}" width="{vw - pad_x * 2}" height="{vh - pad_y * 2}" fill="none" stroke="{color}" stroke-width="4"/>'
        if double_border:
            i = 9
            outer += f'<rect x="{pad_x + i}" y="{pad_y + i}" width="{vw - (pad_x + i) * 2}" height="{vh - (pad_y + i) * 2}" fill="none" stroke="{color}" stroke-width="1.6"/>'

    all_lines = [ln for ln in (lines if lines is not None else text.split("\n")) if ln]
    if not all_lines:
        all_lines = [text or "STAMP"]

    logo_el = ""
    top_pad_extra = 0
    if logo_url:
        ls = 58 if is_sq else 40
        ly = (pad_y + 24) if shape == "shield" else (pad_y + 18)
        logo_el = f'<image href="{_esc_xml(logo_url)}" x="{cx - ls/2:.1f}" y="{ly:.1f}" width="{ls}" height="{ls}" preserveAspectRatio="xMidYMid meet"/>'
        top_pad_extra = ls + 10

    if shape == "shield":
        inset_top = pad_y + 26 + top_pad_extra
        inset_bot = round(vh * 0.28)
    elif shape in ("circle", "oval", "hexagon", "octagon"):
        inset_top = round(vh * 0.22) + top_pad_extra
        inset_bot = round(vh * 0.22)
    else:
        inset_top = pad_y + (18 if double_border else 12) + top_pad_extra
        inset_bot = pad_y + (18 if double_border else 12)

    usable_h = max(40, vh - inset_top - inset_bot)
    n = len(all_lines)
    slot_h = usable_h / n
    base_size = min(round(slot_h * 0.66), 44 if n == 1 else (28 if n == 2 else (21 if n == 3 else 16)))

    def _avail_w(y_pos: float) -> float:
        inner_rx = max(30.0, rx - (18 if double_border else 10))
        inner_ry = max(30.0, ry - (18 if double_border else 10))
        if shape in ("oval", "circle"):
            norm = min(0.92, abs(y_pos - cy) / inner_ry)
            return 2.0 * inner_rx * math.sqrt(max(0.12, 1.0 - norm * norm)) * 0.88
        if shape in ("hexagon", "octagon"):
            norm = min(0.90, abs(y_pos - cy) / (r_poly * 0.86))
            return 2.0 * (r_poly - 16) * max(0.45, 1.0 - 0.35 * norm) * 0.86
        if shape == "shield":
            frac = max(0.0, (y_pos - pad_y) / max(1.0, vh - pad_y * 2))
            taper = 1.0 if frac < 0.56 else max(0.32, 1.0 - (frac - 0.56) * 1.6)
            return (vw - (pad_x + 26) * 2) * taper * 0.88
        return (vw - (pad_x + (18 if double_border else 10)) * 2) * 0.92

    text_els = []
    for idx, line in enumerate(all_lines):
        y_center = inset_top + slot_h * (idx + 0.5)
        max_w = _avail_w(y_center)
        ls_sp = 2.0 if idx == 0 else 1.0
        target_sz = base_size + (2 if idx == 0 and n > 1 else 0)
        size = _fit_size(line, max_w, target_sz, letter_spacing=ls_sp, char_ratio=0.72)
        y = round(y_center + size * 0.34)
        weight = 900 if idx == 0 else 700
        text_els.append(
            f'<text x="{cx}" y="{y}" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" letter-spacing="{ls_sp}">{_esc_xml(line)}</text>'
        )

    w_px = round(width_mm * 3.2)
    h_px = round(height_mm * 3.2)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw} {vh}" '
        f'width="{w_px}" height="{h_px}" data-stamp-root="1">'
        f'{outer}{logo_el}{"".join(text_els)}'
        '</svg>'
    )


def _shaped_seal_svg(
    *,
    top: str,
    bottom: str,
    center_lines: list[str],
    color: str,
    shape: str = "oval",
    width_mm: float = 55,
    height_mm: float = 35,
    border: str = "double",
    logo_url: str = "",
) -> str:
    uid = _uid("sh", top, bottom, "|".join(center_lines), color, shape, logo_url)
    x_scale = max(0.5, min(3.0, width_mm / max(1.0, height_mm)))
    logical_w = round(320 * x_scale)
    r = 140
    rx = round(r * x_scale)

    top_el = ""
    bot_el = ""
    logo_el = ""

    if shape == "oval":
        outer = f'<ellipse cx="0" cy="0" rx="{rx}" ry="{r}" fill="none" stroke="{color}" stroke-width="3.5"/>'
        if border == "double":
            outer += f'<ellipse cx="0" cy="0" rx="{rx - 8}" ry="{r - 8}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        inner_rx = round(84 * x_scale)
        inner_ry = 82
        outer += f'<ellipse cx="0" cy="0" rx="{inner_rx}" ry="{inner_ry}" fill="none" stroke="{color}" stroke-width="1"/>'

        # Curve top & bottom text along the true elliptical arc so text hugs the oval cleanly!
        rx_t, ry_t = round((r - 30) * x_scale), r - 32
        rx_b, ry_b = round((r - 22) * x_scale), r - 20
        arc_len = math.pi * (0.5 * (rx_t + ry_t)) * 0.80
        t_fs = _fit_size(top.upper(), arc_len, 19, letter_spacing=1.8, char_ratio=0.68)
        b_fs = _fit_size(bottom.upper(), arc_len, 16, letter_spacing=1.6, char_ratio=0.68)
        top_el = (
            f'<defs><path id="tp-{uid}-ot" d="M {-rx_t} 0 A {rx_t} {ry_t} 0 0 1 {rx_t} 0" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="{t_fs}" font-weight="700" letter-spacing="1.8" fill="{color}">'
            f'<textPath href="#tp-{uid}-ot" startOffset="50%" text-anchor="middle">{_esc_xml(top.upper())}</textPath></text>'
        )
        bot_el = (
            f'<defs><path id="tp-{uid}-ob" d="M {-rx_b} 0 A {rx_b} {ry_b} 0 0 0 {rx_b} 0" fill="none"/></defs>'
            f'<text font-family="Georgia, serif" font-size="{b_fs}" font-weight="700" letter-spacing="1.6" fill="{color}">'
            f'<textPath href="#tp-{uid}-ob" startOffset="50%" text-anchor="middle">{_esc_xml(bottom.upper())}</textPath></text>'
        )
        center_max_w = inner_rx * 1.72
    elif shape == "hexagon":
        # Flat-top hexagon (rot=0) gives clean horizontal top/bottom bands for text alignment
        pts_o = " ".join(
            f"{math.cos(math.radians(i * 60)) * r:.1f},{math.sin(math.radians(i * 60)) * r:.1f}"
            for i in range(6)
        )
        pts_i = " ".join(
            f"{math.cos(math.radians(i * 60)) * (r - 9):.1f},{math.sin(math.radians(i * 60)) * (r - 9):.1f}"
            for i in range(6)
        )
        outer = f'<polygon points="{pts_o}" fill="none" stroke="{color}" stroke-width="3.5"/>'
        if border == "double":
            outer += f'<polygon points="{pts_i}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        outer += (
            f'<line x1="-88" y1="-58" x2="88" y2="-58" stroke="{color}" stroke-width="1"/>'
            f'<line x1="-88" y1="58" x2="88" y2="58" stroke="{color}" stroke-width="1"/>'
        )
        t_fs = _fit_size(top.upper(), 148, 16, letter_spacing=1.2, char_ratio=0.68)
        b_fs = _fit_size(bottom.upper(), 148, 14, letter_spacing=1.2, char_ratio=0.68)
        top_el = (
            f'<text x="0" y="-76" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{t_fs}" font-weight="700" fill="{color}" letter-spacing="1.2">{_esc_xml(top.upper())}</text>'
        )
        bot_el = (
            f'<text x="0" y="88" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{b_fs}" font-weight="700" fill="{color}" letter-spacing="1.2">{_esc_xml(bottom.upper())}</text>'
        )
        center_max_w = 186
    else:
        cr = 20 if shape == "rounded" else 0
        outer = f'<rect x="{-rx}" y="{-r}" width="{rx * 2}" height="{r * 2}" rx="{cr}" fill="none" stroke="{color}" stroke-width="3.5"/>'
        if border == "double":
            outer += f'<rect x="{-rx + 8}" y="{-r + 8}" width="{rx * 2 - 16}" height="{r * 2 - 16}" rx="{max(0, cr - 4)}" fill="none" stroke="{color}" stroke-width="1.2"/>'
        outer += (
            f'<line x1="{-rx + 22}" y1="-68" x2="{rx - 22}" y2="-68" stroke="{color}" stroke-width="1"/>'
            f'<line x1="{-rx + 22}" y1="68" x2="{rx - 22}" y2="68" stroke="{color}" stroke-width="1"/>'
        )
        band_w = (rx - 24) * 2
        t_fs = _fit_size(top.upper(), band_w, 22, letter_spacing=1.8, char_ratio=0.68)
        b_fs = _fit_size(bottom.upper(), band_w, 17, letter_spacing=1.6, char_ratio=0.68)
        top_el = (
            f'<text x="0" y="-88" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{t_fs}" font-weight="700" fill="{color}" letter-spacing="1.8">{_esc_xml(top.upper())}</text>'
        )
        bot_el = (
            f'<text x="0" y="102" text-anchor="middle" font-family="Georgia, serif" '
            f'font-size="{b_fs}" font-weight="700" fill="{color}" letter-spacing="1.6">{_esc_xml(bottom.upper())}</text>'
        )
        center_max_w = band_w * 0.94

    if logo_url:
        ls = 52
        ly = -ls / 2 - (16 if center_lines else 0)
        logo_el = f'<image href="{_esc_xml(logo_url)}" x="{-ls/2:.1f}" y="{ly:.1f}" width="{ls}" height="{ls}" preserveAspectRatio="xMidYMid meet"/>'

    if logo_url and center_lines:
        cy0 = 26 if len(center_lines) == 1 else 20
        step = 20
    else:
        cy0 = -10 if len(center_lines) == 2 else (8 if len(center_lines) == 1 else -22)
        step = 25

    center_els_list = []
    for i, ln in enumerate(center_lines):
        cfs = _fit_size(ln, center_max_w, 18 if logo_url else 21, letter_spacing=1.0, char_ratio=0.64)
        is_date = "[" in ln and "YYYY" in ln
        d_attr = ' data-stamp-date="DD MMM YYYY"' if is_date else ''
        center_els_list.append(
            f'<text x="0" y="{cy0 + i * step}" text-anchor="middle" font-family="Courier New, monospace" '
            f'font-size="{cfs}" font-weight="700" fill="{color}"{d_attr}>{_esc_xml(ln)}</text>'
        )
    center_els = "".join(center_els_list)
    w_px = round(width_mm * 3.4)
    h_px = round(height_mm * 3.4)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-logical_w / 2} -160 {logical_w} 320" '
        f'width="{w_px}" height="{h_px}" data-stamp-root="1">'
        f'{outer}{top_el}{bot_el}{logo_el}{center_els}'
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
    # Rectangular company stamps — professional corporate company stamps
    # with company legal name, registration, tax, address, signatory and dates.
    # ------------------------------------------------------------------
    StampTemplate(
        slug="corp-rect-official-seal",
        name="Official Corporate Registry Stamp",
        category="Governance",
        kind="company_rect",
        description="Double-border corporate registry stamp — legal company name, incorporation "
                    "reference, registration number, tax PIN, registered office, and auto-date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "INCORPORATED UNDER THE COMPANIES ACT",
            "address1": "Registered Office: 123 Commercial Boulevard",
            "address2": "P.O. Box 40000 - 00100, Nairobi, Kenya",
            "reg_label": "REG. NO.", "reg_value": "C.145892",
            "tax_label": "TAX PIN", "tax_value": "P051234567A",
            "phone": "+254 700 000 000", "email": "info@company.com", "website": "www.company.com",
            "reference_label": "DATE", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 75, "height_mm": 38,
            "border_style": "double", "border_thickness": 3, "corner_radius": 4,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_address": True,
            "show_reg": True, "show_tax": True, "show_contact": True, "show_reference": True,
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            subtitle="INCORPORATED UNDER THE COMPANIES ACT",
            address1="Registered Office: 123 Commercial Boulevard",
            address2="P.O. Box 40000 - 00100, Nairobi, Kenya",
            reg_line="REG. NO. C.145892",
            tax_line="TAX PIN P051234567A",
            contact="+254 700 000 000 · info@company.com · www.company.com",
            border_style="double",
            border_thickness=3,
            corner_radius=4,
            color="#0f3b82",
            width_mm=75,
            height_mm=38,
        ),
    ),
    StampTemplate(
        slug="corp-rect-director-sign",
        name="Director / Executive Signatory Stamp",
        category="Governance",
        kind="company_rect",
        description="Executive signatory stamp — company name header, 'FOR & ON BEHALF OF', "
                    "horizontal signature line, designated title, and date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "EXECUTIVE BOARD OF DIRECTORS",
            "signatory_prefix": "FOR & ON BEHALF OF:",
            "signatory_title": "MANAGING DIRECTOR / AUTHORISED SIGNATORY",
            "show_signatory": True,
            "reg_label": "REG. NO.", "reg_value": "CPR/2021/89201",
            "reference_label": "DATE", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 80, "height_mm": 40,
            "border_style": "rounded", "border_thickness": 3, "corner_radius": 6,
            "header_bar": True, "divider_rule": False, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_address": False,
            "show_reg": True, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            subtitle="EXECUTIVE BOARD OF DIRECTORS",
            reg_line="REG. NO. CPR/2021/89201",
            signatory_prefix="FOR & ON BEHALF OF:",
            signatory_title="MANAGING DIRECTOR / AUTHORISED SIGNATORY",
            show_signatory=True,
            header_bar=True,
            divider_rule=False,
            border_style="rounded",
            border_thickness=3,
            corner_radius=6,
            color="#0f3b82",
            width_mm=80,
            height_mm=40,
        ),
    ),
    StampTemplate(
        slug="corp-rect-finance-approval",
        name="Finance & Accounts Payment Stamp",
        category="Finance",
        kind="company_rect",
        description="Accounts approval stamp — APPROVED FOR PAYMENT, voucher reference, "
                    "passed by signature line, and verification date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "department": "FINANCE & ACCOUNTS DEPARTMENT",
            "subtitle": "APPROVED FOR PAYMENT",
            "custom_line": "VOUCHER REF / EFT NO: ________________",
            "signatory_prefix": "PASSED BY / CHIEF FINANCIAL OFFICER:",
            "signatory_title": "AUTHORIZED FINANCIAL SIGNATURE",
            "show_signatory": True,
            "reference_label": "PAYMENT DATE", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 70, "height_mm": 40,
            "border_style": "rounded", "border_thickness": 3, "corner_radius": 5,
            "header_bar": True, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_department": True, "show_custom_line": True,
            "show_address": False, "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#0e664d",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            department="FINANCE & ACCOUNTS DEPARTMENT",
            subtitle="APPROVED FOR PAYMENT",
            custom_line="VOUCHER REF / EFT NO: ________________",
            signatory_prefix="PASSED BY / CHIEF FINANCIAL OFFICER:",
            signatory_title="AUTHORIZED FINANCIAL SIGNATURE",
            show_signatory=True,
            reference_label="PAYMENT DATE",
            header_bar=True,
            border_style="rounded",
            border_thickness=3,
            corner_radius=5,
            color="#0e664d",
            width_mm=70,
            height_mm=40,
        ),
    ),
    StampTemplate(
        slug="corp-rect-legal-cert",
        name="Legal & Compliance Certified Copy",
        category="Legal",
        kind="company_rect",
        description="Legal compliance stamp — CERTIFIED TRUE COPY OF ORIGINAL, Advocate / "
                    "Commissioner for Oaths signature line, and date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "department": "LEGAL & COMPLIANCE DIVISION",
            "subtitle": "CERTIFIED TRUE AND CORRECT COPY OF ORIGINAL",
            "custom_line": "SEEN & VERIFIED AGAINST ORIGINAL DOCUMENT",
            "signatory_prefix": "ADVOCATE / COMMISSIONER FOR OATHS:",
            "signatory_title": "SIGNATURE & PRACTICING CERTIFICATE NO.",
            "show_signatory": True,
            "reference_label": "ATTESTED ON", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 80, "height_mm": 45,
            "border_style": "double", "border_thickness": 3, "corner_radius": 4,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_department": True, "show_custom_line": True,
            "show_address": False, "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#9e2f36",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            department="LEGAL & COMPLIANCE DIVISION",
            subtitle="CERTIFIED TRUE AND CORRECT COPY OF ORIGINAL",
            custom_line="SEEN & VERIFIED AGAINST ORIGINAL DOCUMENT",
            signatory_prefix="ADVOCATE / COMMISSIONER FOR OATHS:",
            signatory_title="SIGNATURE & PRACTICING CERTIFICATE NO.",
            show_signatory=True,
            reference_label="ATTESTED ON",
            border_style="double",
            border_thickness=3,
            corner_radius=4,
            color="#9e2f36",
            width_mm=80,
            height_mm=45,
        ),
    ),
    StampTemplate(
        slug="corp-rect-procurement-grn",
        name="Procurement Goods Received (GRN)",
        category="Logistics",
        kind="company_rect",
        description="Warehouse procurement stamp — GOODS RECEIVED IN SATISFACTORY CONDITION, "
                    "LPO/PO reference, storekeeper signature, and delivery date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "department": "PROCUREMENT & STORES DEPARTMENT",
            "subtitle": "GOODS RECEIVED IN SATISFACTORY CONDITION",
            "custom_line": "LPO NO: ___________ · DELIVERY NOTE: ___________",
            "signatory_prefix": "STOREKEEPER / RECEIVING OFFICER:",
            "signatory_title": "AUTHORIZED SIGNATURE",
            "show_signatory": True,
            "reference_label": "RECEIVED ON", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 75, "height_mm": 40,
            "border_style": "rounded", "border_thickness": 3, "corner_radius": 6,
            "header_bar": True, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_department": True, "show_custom_line": True,
            "show_address": False, "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#b4821f",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            department="PROCUREMENT & STORES DEPARTMENT",
            subtitle="GOODS RECEIVED IN SATISFACTORY CONDITION",
            custom_line="LPO NO: ___________ · DELIVERY NOTE: ___________",
            signatory_prefix="STOREKEEPER / RECEIVING OFFICER:",
            signatory_title="AUTHORIZED SIGNATURE",
            show_signatory=True,
            reference_label="RECEIVED ON",
            header_bar=True,
            border_style="rounded",
            border_thickness=3,
            corner_radius=6,
            color="#b4821f",
            width_mm=75,
            height_mm=40,
        ),
    ),
    StampTemplate(
        slug="corp-rect-registry-inward",
        name="Central Registry Inward Stamp",
        category="Operations",
        kind="company_rect",
        description="Inward correspondence stamp — CENTRAL REGISTRY, RECEIVED & LOGGED, "
                    "file/reference number line, actioning officer, and auto-date.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "department": "CENTRAL REGISTRY & INWARD CORRESPONDENCE",
            "subtitle": "RECEIVED & LOGGED",
            "custom_line": "FILE / REF NO: ___________________________",
            "signatory_prefix": "RECEIVING OFFICER:",
            "signatory_title": "ACTION BY: DEPT / DESK",
            "show_signatory": True,
            "reference_label": "RECEIVED DATE", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 65, "height_mm": 35,
            "border_style": "solid", "border_thickness": 2, "corner_radius": 0,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_department": True, "show_custom_line": True,
            "show_address": False, "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            department="CENTRAL REGISTRY & INWARD CORRESPONDENCE",
            subtitle="RECEIVED & LOGGED",
            custom_line="FILE / REF NO: ___________________________",
            signatory_prefix="RECEIVING OFFICER:",
            signatory_title="ACTION BY: DEPT / DESK",
            show_signatory=True,
            reference_label="RECEIVED DATE",
            border_style="solid",
            border_thickness=2,
            corner_radius=0,
            color="#0f3b82",
            width_mm=65,
            height_mm=35,
        ),
    ),
    StampTemplate(
        slug="corp-rect-compact-desk",
        name="Compact Corporate Self-Inking Stamp",
        category="Corporate",
        kind="company_rect",
        description="Standard Trodat Printy 4912 size (47×18 mm) — high-density 4-line layout: "
                    "Company Legal Name, Registration, Address, and Contacts.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "C.R. NO. C.98214 · PIN P051928471K",
            "address1": "P.O. Box 10293 - 00100 Nairobi",
            "address2": "Tel: +254 711 000 000 · info@company.com",
            "width_mm": 47, "height_mm": 18,
            "border_style": "rounded", "border_thickness": 1, "corner_radius": 2,
            "header_bar": False, "divider_rule": False, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_address": True,
            "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": False,
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            subtitle="C.R. NO. C.98214 · PIN P051928471K",
            address1="P.O. Box 10293 - 00100 Nairobi",
            address2="Tel: +254 711 000 000 · info@company.com",
            show_reference=False,
            divider_rule=False,
            border_style="rounded",
            border_thickness=1,
            corner_radius=2,
            color="#0f3b82",
            width_mm=47,
            height_mm=18,
        ),
    ),
    StampTemplate(
        slug="corp-rect-address-contact",
        name="Corporate Registered Office Stamp",
        category="Correspondence",
        kind="company_rect",
        description="Official letterhead companion stamp — legal company name, registered physical "
                    "office, P.O. Box, telephone, official email, and website.",
        layout={
            "company": "COMPANY NAME LIMITED",
            "subtitle": "REGISTERED OFFICE",
            "address1": "Commerce House, 4th Floor, City Square",
            "address2": "P.O. Box 30003 - 00100 Nairobi, Kenya",
            "phone": "+254 20 329 3900", "email": "info@company.com", "website": "www.company.com",
            "width_mm": 60, "height_mm": 30,
            "border_style": "rounded", "border_thickness": 2, "corner_radius": 4,
            "header_bar": False, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_address": True,
            "show_reg": False, "show_tax": False, "show_contact": True, "show_reference": False,
            "color": "#0e664d",
        },
        svg=_company_rect_svg(
            company="COMPANY NAME LIMITED",
            subtitle="REGISTERED OFFICE",
            address1="Commerce House, 4th Floor, City Square",
            address2="P.O. Box 30003 - 00100 Nairobi, Kenya",
            contact="+254 20 329 3900 · info@company.com · www.company.com",
            show_reference=False,
            border_style="rounded",
            border_thickness=2,
            corner_radius=4,
            color="#0e664d",
            width_mm=60,
            height_mm=30,
        ),
    ),
    StampTemplate(
        slug="corp-rect-bilingual",
        name="Bilingual Corporate Company Stamp",
        category="Corporate",
        kind="company_rect",
        description="Bilingual corporate stamp — English company legal name with localized secondary "
                    "header, commercial registry, tax code, and date.",
        layout={
            "company": "GULF COMMERCIAL TRADING FZCO",
            "subtitle": "شركة الخليج للتجارة العامة ذ.م.م",
            "address1": "Dubai Silicon Oasis, DSOA HQ",
            "address2": "P.O. Box 341041, Dubai, United Arab Emirates",
            "reg_label": "C.R. NO.", "reg_value": "184920",
            "tax_label": "TRN", "tax_value": "100294819200003",
            "reference_label": "DATE / التاريخ", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 85, "height_mm": 45,
            "border_style": "double", "border_thickness": 3, "corner_radius": 4,
            "header_bar": True, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_address": True,
            "show_reg": True, "show_tax": True, "show_contact": False, "show_reference": True,
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="GULF COMMERCIAL TRADING FZCO",
            subtitle="شركة الخليج للتجارة العامة ذ.م.م",
            address1="Dubai Silicon Oasis, DSOA HQ",
            address2="P.O. Box 341041, Dubai, United Arab Emirates",
            reg_line="C.R. NO. 184920",
            tax_line="TRN 100294819200003",
            reference_label="DATE / التاريخ",
            header_bar=True,
            border_style="double",
            border_thickness=3,
            corner_radius=4,
            color="#0f3b82",
            width_mm=85,
            height_mm=45,
        ),
    ),
    StampTemplate(
        slug="corp-rect-qa-inspected",
        name="QA Inspected & Batch Release Stamp",
        category="Operations",
        kind="company_rect",
        description="Quality assurance release stamp — company name, QA division, "
                    "INSPECTED & BATCH RELEASED, lot/batch number, inspector ID, and date.",
        layout={
            "company": "PHARMACARE BIOTECH LTD",
            "department": "QUALITY ASSURANCE DIVISION",
            "subtitle": "INSPECTED & BATCH RELEASED",
            "custom_line": "BATCH / LOT NO: ___________________________",
            "signatory_prefix": "QA INSPECTOR / ANALYST:",
            "signatory_title": "CONFORMS TO ISO 9001:2015 STANDARDS",
            "show_signatory": True,
            "reference_label": "RELEASE DATE", "reference_value": "", "date_format": "DD MMM YYYY",
            "width_mm": 70, "height_mm": 35,
            "border_style": "rounded", "border_thickness": 3, "corner_radius": 5,
            "header_bar": True, "divider_rule": True, "alignment": "center",
            "show_company": True, "show_subtitle": True, "show_department": True, "show_custom_line": True,
            "show_address": False, "show_reg": False, "show_tax": False, "show_contact": False, "show_reference": True,
            "color": "#0e664d",
        },
        svg=_company_rect_svg(
            company="PHARMACARE BIOTECH LTD",
            department="QUALITY ASSURANCE DIVISION",
            subtitle="INSPECTED & BATCH RELEASED",
            custom_line="BATCH / LOT NO: ___________________________",
            signatory_prefix="QA INSPECTOR / ANALYST:",
            signatory_title="CONFORMS TO ISO 9001:2015 STANDARDS",
            show_signatory=True,
            reference_label="RELEASE DATE",
            header_bar=True,
            border_style="rounded",
            border_thickness=3,
            corner_radius=5,
            color="#0e664d",
            width_mm=70,
            height_mm=35,
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
    # General Company Stamps (Multi-shape: Oval, Rectangular, Hexagonal, Dated, & Rubber)
    StampTemplate(
        slug="general-company-oval-seal",
        name="General Company Stamp (Oval)",
        category="General Company",
        kind="seal",
        description="55×35 mm classic oval corporate company stamp with curved company name, "
                    "registration/city below, and official centre text. Royal blue.",
        layout={
            "shape": "oval",
            "top": "COMPANY NAME LIMITED",
            "bottom": "REG. NO. 12345 · CITY",
            "center": ["★★★", "OFFICIAL", "STAMP"],
            "color": "#0f3b82",
            "border_style": "double",
            "inner_border": True,
            "width_mm": 55,
            "height_mm": 35,
            "size_value": "55x35",
        },
        svg=_shaped_seal_svg(
            top="COMPANY NAME LIMITED",
            bottom="REG. NO. 12345 · CITY",
            center_lines=["★★★", "OFFICIAL", "STAMP"],
            color="#0f3b82",
            shape="oval",
            width_mm=55,
            height_mm=35,
            border="double",
        ),
    ),
    StampTemplate(
        slug="general-company-rect-seal",
        name="General Company Seal (Rectangular)",
        category="General Company",
        kind="seal",
        description="70×38 mm rectangular company seal with double border, top company title, "
                    "centre status, and bottom registration details.",
        layout={
            "shape": "rectangle",
            "top": "COMPANY NAME LIMITED",
            "bottom": "P.O. BOX 12345 · REG. NO. C.00000",
            "center": ["OFFICIAL COMPANY SEAL"],
            "color": "#0f3b82",
            "border_style": "double",
            "width_mm": 70,
            "height_mm": 38,
            "size_value": "70x38",
        },
        svg=_shaped_seal_svg(
            top="COMPANY NAME LIMITED",
            bottom="P.O. BOX 12345 · REG. NO. C.00000",
            center_lines=["OFFICIAL COMPANY SEAL"],
            color="#0f3b82",
            shape="rectangle",
            width_mm=70,
            height_mm=38,
            border="double",
        ),
    ),
    StampTemplate(
        slug="general-company-hex-seal",
        name="General Company Stamp (Hexagonal)",
        category="General Company",
        kind="seal",
        description="45×45 mm hexagonal company stamp — distinctive geometric corporate mark "
                    "for certifications, dispatch, and inspections.",
        layout={
            "shape": "hexagon",
            "top": "COMPANY NAME LTD",
            "bottom": "EST. 2026",
            "center": ["VERIFIED", "CORPORATE"],
            "color": "#0e664d",
            "border_style": "double",
            "width_mm": 45,
            "height_mm": 45,
            "size_value": "45x45",
        },
        svg=_shaped_seal_svg(
            top="COMPANY NAME LTD",
            bottom="EST. 2026",
            center_lines=["VERIFIED", "CORPORATE"],
            color="#0e664d",
            shape="hexagon",
            width_mm=45,
            height_mm=45,
            border="double",
        ),
    ),
    StampTemplate(
        slug="general-company-dated-oval",
        name="General Company Dated Stamp (Oval)",
        category="General Company",
        kind="company_dated",
        description="55×35 mm oval company stamp with dynamic date centre, company arc, "
                    "and registration tagline. Colop Oval 55 format.",
        layout={
            "shape": "oval",
            "company": "COMPANY NAME LIMITED",
            "tagline": "P.O. BOX 12345 · CITY",
            "verb": "DATED",
            "date_format": "DD MMM YYYY",
            "fixed_date": "",
            "color": "#0f3b82",
            "border_style": "double",
            "inner_border": True,
            "width_mm": 55,
            "height_mm": 35,
            "size_value": "55x35",
        },
        svg=_shaped_seal_svg(
            top="COMPANY NAME LIMITED",
            bottom="P.O. BOX 12345 · CITY",
            center_lines=["DATED", "[DD MMM YYYY]"],
            color="#0f3b82",
            shape="oval",
            width_mm=55,
            height_mm=35,
            border="double",
        ),
    ),
    StampTemplate(
        slug="general-company-dated-rect",
        name="General Company Dated Stamp (Rectangular)",
        category="General Company",
        kind="company_dated",
        description="70×35 mm rounded-rectangle dated company stamp with automatic date, "
                    "company header, and branch/registry footer.",
        layout={
            "shape": "rounded",
            "company": "COMPANY NAME LIMITED",
            "tagline": "HEAD OFFICE · REG. NO. 12345",
            "verb": "RECEIVED ON",
            "date_format": "DD MMM YYYY",
            "fixed_date": "",
            "color": "#9e2f36",
            "border_style": "double",
            "width_mm": 70,
            "height_mm": 35,
            "size_value": "70x35",
        },
        svg=_shaped_seal_svg(
            top="COMPANY NAME LIMITED",
            bottom="HEAD OFFICE · REG. NO. 12345",
            center_lines=["RECEIVED ON", "[DD MMM YYYY]"],
            color="#9e2f36",
            shape="rounded",
            width_mm=70,
            height_mm=35,
            border="double",
        ),
    ),
    StampTemplate(
        slug="general-company-rubber-rect",
        name="General Company Rubber Stamp (Rectangular)",
        category="General Company",
        kind="rubber",
        description="70×35 mm multi-line corporate rubber stamp with double border, company name, "
                    "registration/tax details, address, contact, and live date.",
        layout={
            "shape": "rounded",
            "double_border": True,
            "border_thickness": 3,
            "line1": "COMPANY NAME LIMITED",
            "line2": "P.O. BOX 12345-00100, NAIROBI",
            "line3": "REG. NO. PVT-000000 · PIN P000000000A",
            "line4": "TEL: +254 700 000 000 · info@company.com",
            "show_date": True,
            "date_format": "DD MMM YYYY",
            "color": "#0f3b82",
            "width_mm": 70,
            "height_mm": 35,
            "size_value": "70x35",
        },
        svg=_rubber_svg(
            lines=[
                "COMPANY NAME LIMITED",
                "P.O. BOX 12345-00100, NAIROBI",
                "REG. NO. PVT-000000 · PIN P000000000A",
                "[DD MMM YYYY]",
            ],
            color="#0f3b82",
            shape="rounded",
            width_mm=70,
            height_mm=35,
            double_border=True,
        ),
    ),
    StampTemplate(
        slug="general-company-rubber-oval",
        name="General Company Rubber Stamp (Oval)",
        category="General Company",
        kind="rubber",
        description="55×35 mm oval company rubber stamp with double frame and structured "
                    "corporate contact & registration lines.",
        layout={
            "shape": "oval",
            "double_border": True,
            "border_thickness": 3,
            "line1": "COMPANY NAME LTD",
            "line2": "OFFICIAL COMPANY STAMP",
            "line3": "REG. NO. 12345 · CITY",
            "line4": "info@company.com",
            "color": "#0f3b82",
            "width_mm": 55,
            "height_mm": 35,
            "size_value": "55x35",
        },
        svg=_rubber_svg(
            lines=[
                "COMPANY NAME LTD",
                "OFFICIAL COMPANY STAMP",
                "REG. NO. 12345 · CITY",
            ],
            color="#0f3b82",
            shape="oval",
            width_mm=55,
            height_mm=35,
            double_border=True,
        ),
    ),
    StampTemplate(
        slug="general-company-rubber-circle",
        name="General Company Rubber Stamp (Circular)",
        category="General Company",
        kind="rubber",
        description="42 mm circular self-inking company rubber stamp with double ring, "
                    "company details, and optional date line.",
        layout={
            "shape": "circle",
            "double_border": True,
            "border_thickness": 3,
            "line1": "COMPANY NAME LTD",
            "line2": "ACCOUNTS / ADMIN",
            "line3": "REG. NO. 12345",
            "show_date": True,
            "date_format": "DD MMM YYYY",
            "color": "#0e664d",
            "width_mm": 42,
            "height_mm": 42,
            "size_value": "42",
        },
        svg=_rubber_svg(
            lines=[
                "COMPANY NAME LTD",
                "ACCOUNTS / ADMIN",
                "[DD MMM YYYY]",
            ],
            color="#0e664d",
            shape="circle",
            width_mm=42,
            height_mm=42,
            double_border=True,
        ),
    ),
    StampTemplate(
        slug="general-company-rubber-hexagon",
        name="General Company Rubber Stamp (Hexagonal)",
        category="General Company",
        kind="rubber",
        description="45×45 mm hexagonal company rubber stamp for quality control, "
                    "warehouse, or operations sign-off.",
        layout={
            "shape": "hexagon",
            "double_border": True,
            "border_thickness": 3,
            "line1": "COMPANY NAME LTD",
            "line2": "OPERATIONS DEPT",
            "line3": "CHECKED & VERIFIED",
            "show_date": True,
            "date_format": "DD MMM YYYY",
            "color": "#5b3a97",
            "width_mm": 45,
            "height_mm": 45,
            "size_value": "45x45",
        },
        svg=_rubber_svg(
            lines=[
                "COMPANY NAME LTD",
                "OPERATIONS DEPT",
                "CHECKED & VERIFIED",
            ],
            color="#5b3a97",
            shape="hexagon",
            width_mm=45,
            height_mm=45,
            double_border=True,
        ),
    ),
    StampTemplate(
        slug="general-company-rubber-shield",
        name="General Company Rubber Stamp (Shield)",
        category="General Company",
        kind="rubber",
        description="65×38 mm shield-shaped corporate rubber stamp with double border, "
                    "company details, and automatic date.",
        layout={
            "shape": "shield",
            "double_border": True,
            "border_thickness": 3,
            "line1": "COMPANY NAME LIMITED",
            "line2": "SECURITY & COMPLIANCE",
            "line3": "VERIFIED ORIGINAL",
            "show_date": True,
            "date_format": "DD MMM YYYY",
            "color": "#121a26",
            "width_mm": 65,
            "height_mm": 38,
            "size_value": "65x38",
        },
        svg=_rubber_svg(
            lines=[
                "COMPANY NAME LIMITED",
                "SECURITY & COMPLIANCE",
                "VERIFIED ORIGINAL",
                "[DD MMM YYYY]",
            ],
            color="#121a26",
            shape="shield",
            width_mm=65,
            height_mm=38,
            double_border=True,
        ),
    ),
    # Standard Industry & Professional Stamp Types (Accounting, Banking, Notary, Legal, Medical, Engineering, Logistics)
    StampTemplate(
        slug="std-accounting-posting-voucher",
        name="Accounting / Voucher Posting Stamp",
        category="Finance",
        kind="company_rect",
        description="85×55 mm Trodat 4926 finance voucher stamp with account code, cost centre, "
                    "approval signatory line, and live posting date.",
        layout={
            "company": "POSTED & APPROVED",
            "subtitle": "ACCOUNTS / GENERAL LEDGER",
            "department": "FINANCE VOUCHER",
            "custom_line": "A/C CODE: ____________  ·  COST CTR: ________",
            "address1": "INVOICE / VOUCHER NO.: ____________________",
            "address2": "AMOUNT VERIFIED: __________________________",
            "show_company": True,
            "show_subtitle": True,
            "show_department": True,
            "show_custom_line": True,
            "show_address": True,
            "show_signatory": True,
            "signatory_prefix": "CHECKED & AUTHORISED BY:",
            "signatory_title": "FINANCE CONTROLLER / ACCOUNTANT",
            "show_reference": True,
            "reference_label": "POSTING DATE",
            "date_format": "DD MMM YYYY",
            "header_bar": True,
            "divider_rule": True,
            "border_style": "double",
            "border_thickness": 3,
            "corner_radius": 4,
            "width_mm": 85,
            "height_mm": 55,
            "size_value": "85x55",
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="POSTED & APPROVED",
            subtitle="ACCOUNTS / GENERAL LEDGER",
            department="FINANCE VOUCHER",
            custom_line="A/C CODE: ____________  ·  COST CTR: ________",
            address1="INVOICE / VOUCHER NO.: ____________________",
            address2="AMOUNT VERIFIED: __________________________",
            show_signatory=True,
            signatory_prefix="CHECKED & AUTHORISED BY:",
            signatory_title="FINANCE CONTROLLER / ACCOUNTANT",
            show_reference=True,
            reference_label="POSTING DATE",
            header_bar=True,
            divider_rule=True,
            border_style="double",
            width_mm=85,
            height_mm=55,
            color="#0f3b82",
        ),
    ),
    StampTemplate(
        slug="std-bank-deposit-only",
        name="Bank Endorsement (For Deposit Only)",
        category="Finance",
        kind="company_rect",
        description="70×35 mm standard corporate banking endorsement stamp for cheque deposits.",
        layout={
            "company": "FOR DEPOSIT ONLY",
            "subtitle": "TO THE CREDIT OF COMPANY NAME LIMITED",
            "custom_line": "BANK: COMMERCIAL BANK PLC · MAIN BRANCH",
            "reg_label": "A/C NO.",
            "reg_value": "0100-0000-0000-00",
            "tax_label": "BRANCH CODE",
            "tax_value": "001",
            "show_company": True,
            "show_subtitle": True,
            "show_custom_line": True,
            "show_reg": True,
            "show_tax": True,
            "header_bar": True,
            "divider_rule": False,
            "border_style": "solid",
            "border_thickness": 3,
            "width_mm": 70,
            "height_mm": 35,
            "size_value": "70x35",
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="FOR DEPOSIT ONLY",
            subtitle="TO THE CREDIT OF COMPANY NAME LIMITED",
            custom_line="BANK: COMMERCIAL BANK PLC · MAIN BRANCH",
            reg_line="A/C NO. 0100-0000-0000-00",
            tax_line="BRANCH CODE 001",
            header_bar=True,
            border_style="solid",
            width_mm=70,
            height_mm=35,
            color="#0f3b82",
        ),
    ),
    StampTemplate(
        slug="std-cheque-ac-payee",
        name="Cheque Crossing (A/C Payee Only)",
        category="Finance",
        kind="rubber",
        description="58×18 mm parallel-rule cheque crossing stamp — A/C PAYEE ONLY · NOT NEGOTIABLE.",
        layout={
            "shape": "none",
            "decoration": "double-rule",
            "line1": "A/C PAYEE ONLY",
            "line2": "NOT NEGOTIABLE",
            "color": "#121a26",
            "width_mm": 58,
            "height_mm": 18,
            "size_value": "58x18",
        },
        svg=_rubber_svg(
            lines=["A/C PAYEE ONLY", "NOT NEGOTIABLE"],
            color="#121a26",
            shape="rect",
            width_mm=58,
            height_mm=18,
            double_border=False,
        ),
    ),
    StampTemplate(
        slug="std-notary-jurat-block",
        name="Notary Public Jurat / Acknowledgment",
        category="Legal",
        kind="company_rect",
        description="75×38 mm rectangular notary public jurat & commission block with expiry and signature.",
        layout={
            "company": "NOTARY PUBLIC",
            "subtitle": "SWORN & SUBSCRIBED BEFORE ME",
            "custom_line": "COMMISSION NO. NP-000000 · EXPIRES: 31 DEC 2028",
            "address1": "COMMISSIONER FOR OATHS & NOTARY PUBLIC",
            "address2": "JURISDICTION / CITY, COUNTRY",
            "show_company": True,
            "show_subtitle": True,
            "show_custom_line": True,
            "show_address": True,
            "show_signatory": True,
            "signatory_prefix": "IN WITNESS WHEREOF:",
            "signatory_title": "NOTARY PUBLIC SIGNATURE",
            "show_reference": True,
            "reference_label": "DATED",
            "header_bar": False,
            "divider_rule": True,
            "border_style": "double",
            "border_thickness": 3,
            "width_mm": 75,
            "height_mm": 38,
            "size_value": "75x38",
            "color": "#121a26",
        },
        svg=_company_rect_svg(
            company="NOTARY PUBLIC",
            subtitle="SWORN & SUBSCRIBED BEFORE ME",
            custom_line="COMMISSION NO. NP-000000 · EXPIRES: 31 DEC 2028",
            address1="COMMISSIONER FOR OATHS & NOTARY PUBLIC",
            show_signatory=True,
            signatory_prefix="IN WITNESS WHEREOF:",
            signatory_title="NOTARY PUBLIC SIGNATURE",
            show_reference=True,
            reference_label="DATED",
            divider_rule=True,
            border_style="double",
            width_mm=75,
            height_mm=38,
            color="#121a26",
        ),
    ),
    StampTemplate(
        slug="std-legal-certified-true-copy",
        name="Certified True Copy Block",
        category="Legal",
        kind="company_rect",
        description="70×40 mm official document certification stamp with certifying officer signature & date.",
        layout={
            "company": "CERTIFIED TRUE COPY",
            "subtitle": "OF THE ORIGINAL DOCUMENT SIGHTED",
            "custom_line": "CERTIFYING AUTHORITY / ADVOCATE / COMPANY SECRETARY",
            "show_company": True,
            "show_subtitle": True,
            "show_custom_line": True,
            "show_signatory": True,
            "signatory_prefix": "CERTIFIED BY:",
            "signatory_title": "AUTHORISED CERTIFYING OFFICER",
            "show_reference": True,
            "reference_label": "DATE",
            "header_bar": True,
            "divider_rule": False,
            "border_style": "rounded",
            "border_thickness": 3,
            "width_mm": 70,
            "height_mm": 40,
            "size_value": "70x40",
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="CERTIFIED TRUE COPY",
            subtitle="OF THE ORIGINAL DOCUMENT SIGHTED",
            custom_line="CERTIFYING AUTHORITY / ADVOCATE / COMPANY SECRETARY",
            show_signatory=True,
            signatory_prefix="CERTIFIED BY:",
            signatory_title="AUTHORISED CERTIFYING OFFICER",
            show_reference=True,
            reference_label="DATE",
            header_bar=True,
            border_style="rounded",
            width_mm=70,
            height_mm=40,
            color="#0f3b82",
        ),
    ),
    StampTemplate(
        slug="std-legal-exhibit-mark",
        name="Court / Legal Exhibit Stamp",
        category="Legal",
        kind="rubber",
        description="60×30 mm litigation exhibit marking stamp with exhibit number, case ref, and date.",
        layout={
            "shape": "rect",
            "double_border": True,
            "border_thickness": 3,
            "line1": "EXHIBIT NO. ________",
            "line2": "CASE / FILE REF: ____________",
            "line3": "INITIALS: ______",
            "show_date": True,
            "date_format": "DD MMM YYYY",
            "color": "#9e2f36",
            "width_mm": 60,
            "height_mm": 30,
            "size_value": "60x30",
        },
        svg=_rubber_svg(
            lines=["EXHIBIT NO. ________", "CASE / FILE REF: ____________", "[DD MMM YYYY]"],
            color="#9e2f36",
            shape="rect",
            width_mm=60,
            height_mm=30,
            double_border=True,
        ),
    ),
    StampTemplate(
        slug="std-logistics-qc-checklist",
        name="Logistics / QC Inspection Checklist",
        category="Operations",
        kind="company_rect",
        description="80×45 mm warehouse & quality control checklist stamp with pass/reject boxes, waybill, and date.",
        layout={
            "company": "RECEIVED & INSPECTED",
            "department": "QUALITY CONTROL / STORES",
            "custom_line": "[  ] QTY OK    [  ] QUALITY PASS    [  ] DAMAGED",
            "address1": "WAYBILL / GRN NO.: ________________________",
            "address2": "INSPECTOR INITIALS: ____________",
            "show_company": True,
            "show_department": True,
            "show_custom_line": True,
            "show_address": True,
            "show_reference": True,
            "reference_label": "DATE",
            "header_bar": True,
            "divider_rule": True,
            "border_style": "solid",
            "border_thickness": 3,
            "width_mm": 80,
            "height_mm": 45,
            "size_value": "80x45",
            "color": "#0e664d",
        },
        svg=_company_rect_svg(
            company="RECEIVED & INSPECTED",
            department="QUALITY CONTROL / STORES",
            custom_line="[  ] QTY OK    [  ] QUALITY PASS    [  ] DAMAGED",
            address1="WAYBILL / GRN NO.: ________________________",
            address2="INSPECTOR INITIALS: ____________",
            show_reference=True,
            reference_label="DATE",
            header_bar=True,
            divider_rule=True,
            border_style="solid",
            width_mm=80,
            height_mm=45,
            color="#0e664d",
        ),
    ),
    StampTemplate(
        slug="std-medical-practitioner",
        name="Medical / Clinical Practitioner Stamp",
        category="Medical",
        kind="company_rect",
        description="60×35 mm physician / pharmacist prescription & clinical endorsement stamp with board reg no.",
        layout={
            "company": "DR. FULL NAME",
            "subtitle": "MBChB, MMed · CONSULTANT PHYSICIAN",
            "reg_label": "BOARD REG. NO.",
            "reg_value": "A-00000",
            "address1": "CLINIC / HOSPITAL NAME",
            "phone": "TEL: +254 700 000 000",
            "email": "doctor@clinic.org",
            "show_company": True,
            "show_subtitle": True,
            "show_reg": True,
            "show_address": True,
            "show_contact": True,
            "header_bar": False,
            "divider_rule": True,
            "border_style": "rounded",
            "border_thickness": 2,
            "width_mm": 60,
            "height_mm": 35,
            "size_value": "60x35",
            "color": "#0f3b82",
        },
        svg=_company_rect_svg(
            company="DR. FULL NAME",
            subtitle="MBChB, MMed · CONSULTANT PHYSICIAN",
            reg_line="BOARD REG. NO. A-00000",
            address1="CLINIC / HOSPITAL NAME",
            contact="TEL: +254 700 000 000 · doctor@clinic.org",
            divider_rule=True,
            border_style="rounded",
            width_mm=60,
            height_mm=35,
            color="#0f3b82",
        ),
    ),
    StampTemplate(
        slug="std-engineering-drawing-approval",
        name="Engineering / Drawing Approval Block",
        category="Engineering",
        kind="company_rect",
        description="85×45 mm technical drawing approval & revision stamp for engineers and architects.",
        layout={
            "company": "APPROVED FOR CONSTRUCTION",
            "subtitle": "ENGINEER / ARCHITECT REVIEW",
            "custom_line": "PROJECT NO.: ____________  ·  REV: ______",
            "reg_label": "ENG. REG.",
            "reg_value": "PE-00000",
            "show_company": True,
            "show_subtitle": True,
            "show_custom_line": True,
            "show_reg": True,
            "show_signatory": True,
            "signatory_prefix": "APPROVED BY:",
            "signatory_title": "REGISTERED PROFESSIONAL ENGINEER",
            "show_reference": True,
            "reference_label": "DATE",
            "header_bar": True,
            "divider_rule": True,
            "border_style": "double",
            "border_thickness": 3,
            "width_mm": 85,
            "height_mm": 45,
            "size_value": "85x45",
            "color": "#9e2f36",
        },
        svg=_company_rect_svg(
            company="APPROVED FOR CONSTRUCTION",
            subtitle="ENGINEER / ARCHITECT REVIEW",
            custom_line="PROJECT NO.: ____________  ·  REV: ______",
            reg_line="ENG. REG. PE-00000",
            show_signatory=True,
            signatory_prefix="APPROVED BY:",
            signatory_title="REGISTERED PROFESSIONAL ENGINEER",
            show_reference=True,
            reference_label="DATE",
            header_bar=True,
            divider_rule=True,
            border_style="double",
            width_mm=85,
            height_mm=45,
            color="#9e2f36",
        ),
    ),
    StampTemplate(
        slug="std-executive-monogram-seal",
        name="Executive Monogram / Dry Seal",
        category="Governance",
        kind="seal",
        description="42 mm ornate monogram seal — classic embossed/dry-seal corporate & executive emblem.",
        layout={
            "shape": "circle",
            "top": "COMPANY NAME LIMITED",
            "bottom": "COMMON CORPORATE SEAL",
            "center_style": "monogram",
            "monogram": "VW",
            "color": "#121a26",
            "border_style": "ornate",
            "inner_border": True,
            "dividers": "star",
            "width_mm": 42,
            "height_mm": 42,
            "size_value": "42",
        },
        svg=_seal_svg(
            top="COMPANY NAME LIMITED",
            bottom="COMMON CORPORATE SEAL",
            center_lines=["VW"],
            color="#121a26",
            border="double",
        ),
    ),
    # ------------------------------------------------------------------
    # Official Branded Stamps (with Brand Logos)
    # ------------------------------------------------------------------
    StampTemplate(
        slug="brand-official-corporate-seal",
        name="Official Corporate Seal (With Brand Shield)",
        category="Governance",
        kind="seal",
        description="45 mm official double-ring corporate seal featuring your centered brand shield logo in TrustSeal Navy.",
        layout={
            "shape": "circle",
            "top": "TRUSTSEAL CORPORATION LTD",
            "bottom": "OFFICIAL CORPORATE SEAL",
            "center": ["CERTIFIED"],
            "color": "#002769",
            "border_style": "double",
            "inner_border": True,
            "dividers": "star",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 36, "logo_x": 0, "logo_y": -10, "logo_opacity": 0.95,
            "width_mm": 45, "height_mm": 45, "size_value": "45",
        },
        svg=_seal_svg(
            top="TRUSTSEAL CORPORATION LTD",
            bottom="OFFICIAL CORPORATE SEAL",
            center_lines=["CERTIFIED"],
            color="#002769",
            border="double",
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
            logo_size=72,
        ),
    ),
    StampTemplate(
        slug="brand-verified-original-seal",
        name="Verified Original Seal (With Brand Shield)",
        category="Legal",
        kind="seal",
        description="45 mm forensic authenticity & verified original seal with centered brand shield in TrustSeal Emerald.",
        layout={
            "shape": "circle",
            "top": "TRUSTSEAL VERIFICATION",
            "bottom": "AUTHENTIC ORIGINAL",
            "center": ["VERIFIED"],
            "color": "#02982E",
            "border_style": "double",
            "inner_border": True,
            "dividers": "star",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 36, "logo_x": 0, "logo_y": -10, "logo_opacity": 0.95,
            "width_mm": 45, "height_mm": 45, "size_value": "45",
        },
        svg=_seal_svg(
            top="TRUSTSEAL VERIFICATION",
            bottom="AUTHENTIC ORIGINAL",
            center_lines=["VERIFIED"],
            color="#02982E",
            border="double",
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
            logo_size=72,
        ),
    ),
    StampTemplate(
        slug="brand-dated-registry-seal",
        name="Official Dated Registry Seal (Brand Shield)",
        category="Governance",
        kind="company_dated",
        description="45 mm round dated company registry seal with brand shield above the live document date.",
        layout={
            "shape": "circle",
            "company": "TRUSTSEAL REGISTRY OFFICE",
            "tagline": "REGISTERED & FILED",
            "verb": "RECORDED",
            "date_format": "DD MMM YYYY",
            "fixed_date": "",
            "color": "#002769",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 24, "logo_x": 0, "logo_y": -28, "logo_opacity": 0.92,
            "width_mm": 45, "height_mm": 45, "size_value": "45",
        },
        svg=_company_dated_svg(
            company="TRUSTSEAL REGISTRY OFFICE",
            tagline="REGISTERED & FILED",
            verb="RECORDED",
            color="#002769",
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
        ),
    ),
    StampTemplate(
        slug="brand-dated-received-seal",
        name="Official Document Received Dater (Brand Shield)",
        category="Operations",
        kind="company_dated",
        description="45 mm round incoming mail & contract received dater with brand shield emblem.",
        layout={
            "shape": "circle",
            "company": "TRUSTSEAL OPERATIONS",
            "tagline": "DOCUMENT CONTROL",
            "verb": "RECEIVED",
            "date_format": "DD MMM YYYY",
            "fixed_date": "",
            "color": "#1D3648",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 24, "logo_x": 0, "logo_y": -28, "logo_opacity": 0.92,
            "width_mm": 45, "height_mm": 45, "size_value": "45",
        },
        svg=_company_dated_svg(
            company="TRUSTSEAL OPERATIONS",
            tagline="DOCUMENT CONTROL",
            verb="RECEIVED",
            color="#1D3648",
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
        ),
    ),
    StampTemplate(
        slug="brand-oval-certified-copy",
        name="Certified True Copy Oval Seal (Brand Shield)",
        category="Legal",
        kind="seal",
        description="55×35 mm elliptical certified true copy seal with curved arc lettering and centered brand shield.",
        layout={
            "shape": "oval",
            "top": "TRUSTSEAL LEGAL DIVISION",
            "bottom": "CERTIFIED TRUE COPY",
            "center": ["ORIGINAL SEEN"],
            "color": "#002769",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 30, "logo_x": 0, "logo_y": -10, "logo_opacity": 0.95,
            "width_mm": 55, "height_mm": 35, "size_value": "55x35",
        },
        svg=_shaped_seal_svg(
            top="TRUSTSEAL LEGAL DIVISION",
            bottom="CERTIFIED TRUE COPY",
            center_lines=["ORIGINAL SEEN"],
            color="#002769",
            shape="oval",
            width_mm=55,
            height_mm=35,
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
        ),
    ),
    StampTemplate(
        slug="brand-hexagon-board-seal",
        name="Board Resolution Hexagonal Seal (Brand Shield)",
        category="Governance",
        kind="seal",
        description="45×45 mm flat-top hexagonal board resolution seal with centered brand emblem.",
        layout={
            "shape": "hexagon",
            "top": "BOARD OF DIRECTORS",
            "bottom": "RESOLUTION PASSED",
            "center": ["APPROVED"],
            "color": "#002769",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 30, "logo_x": 0, "logo_y": -10, "logo_opacity": 0.95,
            "width_mm": 45, "height_mm": 45, "size_value": "45x45",
        },
        svg=_shaped_seal_svg(
            top="BOARD OF DIRECTORS",
            bottom="RESOLUTION PASSED",
            center_lines=["APPROVED"],
            color="#002769",
            shape="hexagon",
            width_mm=45,
            height_mm=45,
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
        ),
    ),
    StampTemplate(
        slug="brand-notary-public-seal",
        name="Notary Public Commission Seal (Brand Shield)",
        category="Legal",
        kind="seal",
        description="45 mm crimson notary public commission seal with brand shield emblem.",
        layout={
            "shape": "circle",
            "top": "NOTARY PUBLIC & COMMISSIONER",
            "bottom": "COMMISSION EXPIRES 2029",
            "center": ["NOTARIAL SEAL"],
            "color": "#9e2f36",
            "border_style": "double",
            "inner_border": True,
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 34, "logo_x": 0, "logo_y": -10, "logo_opacity": 0.92,
            "width_mm": 45, "height_mm": 45, "size_value": "45",
        },
        svg=_seal_svg(
            top="NOTARY PUBLIC & COMMISSIONER",
            bottom="COMMISSION EXPIRES 2029",
            center_lines=["NOTARIAL SEAL"],
            color="#9e2f36",
            border="double",
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
            logo_size=68,
        ),
    ),
    StampTemplate(
        slug="brand-rect-contract-executed",
        name="Contract Executed & Sealed (With Brand Logo)",
        category="Legal",
        kind="company_rect",
        description="75×38 mm rectangular contract execution stamp with horizontal brand logo, signatory line, and live date.",
        layout={
            "company": "TRUSTSEAL LEGAL & CONTRACTS",
            "subtitle": "AGREEMENT EXECUTED & SEALED",
            "department": "EXECUTED",
            "reg_line": "REG. NO. TS-2026-001",
            "show_signatory": True,
            "signatory_prefix": "FOR AND ON BEHALF OF THE ORGANIZATION",
            "signatory_title": "AUTHORIZED SIGNATORY",
            "show_reference": True,
            "reference_label": "SIGNED DATE",
            "date_format": "DD MMM YYYY",
            "color": "#002769",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-horizontal.png",
            "logo_size": 40, "logo_x": 0, "logo_y": -32, "logo_opacity": 0.95,
            "width_mm": 75, "height_mm": 38, "size_value": "75x38",
        },
        svg=_company_rect_svg(
            company="TRUSTSEAL LEGAL & CONTRACTS",
            subtitle="AGREEMENT EXECUTED & SEALED",
            reg_line="REG. NO. TS-2026-001",
            show_signatory=True,
            signatory_prefix="FOR AND ON BEHALF OF THE ORGANIZATION",
            signatory_title="AUTHORIZED SIGNATORY",
            show_reference=True,
            reference_label="SIGNED DATE",
            color="#002769",
            border_style="double",
            logo_url="/static/brand/trustseal/trustseal-horizontal.png",
        ),
    ),
    StampTemplate(
        slug="brand-rect-accounts-approved",
        name="Accounts & Audit Approved (With Brand Logo)",
        category="Operations",
        kind="company_rect",
        description="75×38 mm finance & audit approval block with brand logo, voucher reference, and date.",
        layout={
            "company": "FINANCE & TREASURY",
            "subtitle": "APPROVED FOR PAYMENT",
            "department": "VERIFIED & AUDITED",
            "reg_line": "VOUCHER NO. ____________",
            "show_signatory": True,
            "signatory_title": "CHIEF FINANCIAL OFFICER",
            "show_reference": True,
            "reference_label": "APPROVED ON",
            "date_format": "DD MMM YYYY",
            "color": "#02982E",
            "border_style": "double",
            "logo_data_uri": "/static/brand/trustseal/trustseal-horizontal.png",
            "logo_size": 38, "logo_x": 0, "logo_y": -32, "logo_opacity": 0.95,
            "width_mm": 75, "height_mm": 38, "size_value": "75x38",
        },
        svg=_company_rect_svg(
            company="FINANCE & TREASURY",
            subtitle="APPROVED FOR PAYMENT",
            reg_line="VOUCHER NO. ____________",
            show_signatory=True,
            signatory_title="CHIEF FINANCIAL OFFICER",
            show_reference=True,
            reference_label="APPROVED ON",
            color="#02982E",
            border_style="double",
            logo_url="/static/brand/trustseal/trustseal-horizontal.png",
        ),
    ),
    StampTemplate(
        slug="brand-rect-executive-signoff",
        name="Executive Sign-Off Block (With Brand Logo)",
        category="Governance",
        kind="company_rect",
        description="75×38 mm executive office sign-off stamp with solid header bar, brand logo, and signatory line.",
        layout={
            "company": "OFFICE OF THE MANAGING DIRECTOR",
            "subtitle": "EXECUTIVE APPROVAL",
            "show_signatory": True,
            "signatory_title": "MANAGING DIRECTOR",
            "show_reference": True,
            "reference_label": "DATE",
            "date_format": "DD MMM YYYY",
            "color": "#1D3648",
            "border_style": "rounded",
            "header_bar": True,
            "logo_data_uri": "/static/brand/trustseal/trustseal-horizontal.png",
            "logo_size": 36, "logo_x": 0, "logo_y": -14, "logo_opacity": 0.95,
            "width_mm": 75, "height_mm": 38, "size_value": "75x38",
        },
        svg=_company_rect_svg(
            company="OFFICE OF THE MANAGING DIRECTOR",
            subtitle="EXECUTIVE APPROVAL",
            show_signatory=True,
            signatory_title="MANAGING DIRECTOR",
            show_reference=True,
            reference_label="DATE",
            color="#1D3648",
            border_style="rounded",
            header_bar=True,
            logo_url="/static/brand/trustseal/trustseal-horizontal.png",
        ),
    ),
    StampTemplate(
        slug="brand-shield-customs-cleared",
        name="Official Shield Clearance Stamp (Brand Shield)",
        category="Operations",
        kind="rubber",
        description="45×45 mm heraldic shield clearance stamp with brand shield emblem and perfectly fitted text.",
        layout={
            "text": "VERIFIED\nCLEARED",
            "color": "#002769",
            "shape": "shield",
            "double_border": True,
            "logo_data_uri": "/static/brand/trustseal/trustseal-shield-color.png",
            "logo_size": 26, "logo_x": 0, "logo_y": -26, "logo_opacity": 0.95,
            "width_mm": 45, "height_mm": 45, "size_value": "45x45",
        },
        svg=_rubber_svg(
            lines=["VERIFIED", "CLEARED"],
            color="#002769",
            shape="shield",
            width_mm=45,
            height_mm=45,
            double_border=True,
            logo_url="/static/brand/trustseal/trustseal-shield-color.png",
        ),
    ),
    StampTemplate(
        slug="brand-rect-quality-certified",
        name="Quality & Compliance Certified (With Brand Logo)",
        category="Operations",
        kind="company_rect",
        description="75×38 mm QA / ISO compliance stamp with brand logo, inspection status, and date.",
        layout={
            "company": "QUALITY & COMPLIANCE ASSURANCE",
            "subtitle": "INSPECTED · PASSED · CERTIFIED",
            "reg_line": "CERT REF. QA-2026",
            "show_signatory": True,
            "signatory_title": "COMPLIANCE OFFICER",
            "show_reference": True,
            "reference_label": "INSPECTED",
            "date_format": "DD MMM YYYY",
            "color": "#002769",
            "border_style": "rounded",
            "logo_data_uri": "/static/brand/trustseal/trustseal-horizontal.png",
            "logo_size": 38, "logo_x": 0, "logo_y": -32, "logo_opacity": 0.95,
            "width_mm": 75, "height_mm": 38, "size_value": "75x38",
        },
        svg=_company_rect_svg(
            company="QUALITY & COMPLIANCE ASSURANCE",
            subtitle="INSPECTED · PASSED · CERTIFIED",
            reg_line="CERT REF. QA-2026",
            show_signatory=True,
            signatory_title="COMPLIANCE OFFICER",
            show_reference=True,
            reference_label="INSPECTED",
            color="#002769",
            border_style="rounded",
            logo_url="/static/brand/trustseal/trustseal-horizontal.png",
        ),
    ),
]


def list_templates() -> list[dict]:
    return [
        {
            "slug": t.slug, "name": t.name, "category": t.category,
            "kind": t.kind, "description": t.description,
            "layout": t.layout, "svg": t.svg,
        }
        for t in _TEMPLATES
    ]


def get_template(slug: str) -> StampTemplate | None:
    for t in _TEMPLATES:
        if t.slug == slug:
            return t
    from app.services.stamp_templates_1000 import get_1000_stamp_by_slug, render_stamp_item

    raw = get_1000_stamp_by_slug().get(slug)
    if raw is not None:
        h = render_stamp_item(raw)
        return StampTemplate(
            slug=h["slug"],
            name=h["name"],
            category=h["category"],
            kind=h["kind"],
            description=h["description"],
            layout=h["layout"],
            svg=h["svg"],
        )
    return None


def search_templates(
    *,
    q: str = "",
    category: str = "",
    style: str = "",
    kind: str = "",
    page: int = 1,
    per_page: int = 24,
) -> dict:
    from app.services.stamp_templates_1000 import search_stamp_catalog

    return search_stamp_catalog(
        builtin_items=list_templates(),
        q=q,
        category=category,
        style=style,
        kind=kind,
        page=page,
        per_page=per_page,
    )


def get_stamp_catalog_summary() -> dict:
    from app.services.stamp_templates_1000 import get_1000_stamp_catalog, get_stamp_catalog_facets

    builtins = list_templates()
    facets = get_stamp_catalog_facets(builtins)
    return {
        "total": len(builtins) + len(get_1000_stamp_catalog()),
        "categories": facets["categories"],
        "styles": facets["styles"],
        "kinds": facets["kinds"],
    }
