"""Full-fidelity vector PDF renderer for TrustSeal Official Letterheads.

Renders ALL configured Letterhead Studio settings into crisp ReportLab vector PDFs:
- Paper size (A4, Letter, Legal, A5, Executive, B5) + Portrait/Landscape + X/Y margins
- Paper stock tone, left edge bar, page frame (thin / double)
- All 18 dual-tone vector background patterns at configured opacity (5%-100%)
- Background crest image + angled text watermark
- Top dual-tone brand stripe
- Full-bleed & styled headers (none, neutral, tint, solid, gradient, angled, framed, underline_band)
  with custom min-height & padding
- Raster (PNG/JPEG/WebP with alpha) AND SVG vector logos with size, fit, offset, frame, mat, opacity
- Full typography, visibility flags, independent dividers (solid/dual/double/thin/dotted)
- Customizable Reference & Date Bar (classic/compact/boxed/memo + custom labels)
- Full-bleed & styled footers (split/centered/columns, directors, banking, page numbers, trust badge, bottom stripe)
"""
from __future__ import annotations

import base64
import io
import math
from typing import Any

from PIL import Image


def _hex_rgb(hex_color: str, fallback: tuple[float, float, float] = (0.0, 0.153, 0.412)) -> tuple[float, float, float]:
    h = (hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6:
        return fallback
    try:
        return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)
    except ValueError:
        return fallback


def _blend(rgb: tuple[float, float, float], bg: tuple[float, float, float], alpha: float) -> tuple[float, float, float]:
    return (
        rgb[0] * alpha + bg[0] * (1.0 - alpha),
        rgb[1] * alpha + bg[1] * (1.0 - alpha),
        rgb[2] * alpha + bg[2] * (1.0 - alpha),
    )


def _draw_poly(c, pts: list[tuple[float, float]], fill=1, stroke=0):
    p = c.beginPath()
    p.moveTo(pts[0][0], pts[0][1])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    p.close()
    c.drawPath(p, fill=fill, stroke=stroke)


def _draw_bg_pattern(c, pattern: str, pw: float, ph: float, p_rgb, b_rgb, opacity_pct: int) -> None:
    if not pattern or pattern == "none":
        return
    op = max(0.05, min(1.0, float(opacity_pct if opacity_pct is not None else 85) / 100.0))
    sx = pw / 800.0
    sy = ph / 1120.0

    def pt(x: float, y_top: float) -> tuple[float, float]:
        return (x * sx, ph - y_top * sy)

    c.saveState()
    try:
        c.setFillAlpha(op)
        c.setStrokeAlpha(op)
    except Exception:
        pass

    if pattern == "geometric_corners":
        c.setFillColorRGB(*p_rgb)
        _draw_poly(c, [pt(800, 0), pt(590, 0), pt(800, 190)])
        _draw_poly(c, [pt(0, 1120), pt(210, 1120), pt(0, 930)])
        c.setFillColorRGB(*b_rgb)
        _draw_poly(c, [pt(800, 0), pt(675, 0), pt(800, 115)])
        _draw_poly(c, [pt(0, 1120), pt(125, 1120), pt(0, 1005)])

    elif pattern == "top_diagonal_slash":
        c.setFillColorRGB(*p_rgb)
        _draw_poly(c, [pt(0, 0), pt(800, 0), pt(800, 72), pt(0, 136)])
        _draw_poly(c, [pt(0, 1084), pt(800, 1050), pt(800, 1120), pt(0, 1120)])
        c.setFillColorRGB(*b_rgb)
        _draw_poly(c, [pt(0, 130), pt(800, 66), pt(800, 80), pt(0, 144)])
        _draw_poly(c, [pt(0, 1078), pt(800, 1044), pt(800, 1052), pt(0, 1086)])

    elif pattern == "executive_curve_split":
        c.setFillColorRGB(*p_rgb)
        p1 = c.beginPath()
        p1.moveTo(*pt(0, 0))
        p1.lineTo(*pt(520, 0))
        p1.curveTo(*pt(420, 90), *pt(240, 120), *pt(0, 95))
        p1.close()
        c.drawPath(p1, fill=1, stroke=0)
        p2 = c.beginPath()
        p2.moveTo(*pt(800, 1120))
        p2.lineTo(*pt(280, 1120))
        p2.curveTo(*pt(380, 1040), *pt(560, 1020), *pt(800, 1045))
        p2.close()
        c.drawPath(p2, fill=1, stroke=0)
        c.setStrokeColorRGB(*b_rgb)
        c.setLineWidth(5 * sy)
        p3 = c.beginPath()
        p3.moveTo(*pt(540, 0))
        p3.curveTo(*pt(435, 96), *pt(250, 126), *pt(0, 100))
        c.drawPath(p3, fill=0, stroke=1)

    elif pattern == "side_accent_ribbon":
        c.setFillColorRGB(*p_rgb)
        c.rect(0, 0, 20 * sx, ph, fill=1, stroke=0)
        c.setFillColorRGB(*b_rgb)
        c.rect(20 * sx, 0, 6 * sx, ph, fill=1, stroke=0)
        c.setFillColorRGB(*p_rgb)
        c.rect(30 * sx, 0, 2 * sx, ph, fill=1, stroke=0)

    elif pattern == "dual_side_bars":
        c.setFillColorRGB(*p_rgb)
        c.rect(0, 0, 12 * sx, ph, fill=1, stroke=0)
        c.rect(pw - 12 * sx, 0, 12 * sx, ph, fill=1, stroke=0)
        c.setFillColorRGB(*b_rgb)
        c.rect(12 * sx, 0, 3 * sx, ph, fill=1, stroke=0)
        c.rect(pw - 15 * sx, 0, 3 * sx, ph, fill=1, stroke=0)

    elif pattern == "angled_side_panel":
        c.setFillColorRGB(*p_rgb)
        _draw_poly(c, [pt(0, 0), pt(52, 0), pt(16, 1120), pt(0, 1120)])
        c.setFillColorRGB(*b_rgb)
        _draw_poly(c, [pt(56, 0), pt(66, 0), pt(30, 1120), pt(20, 1120)])

    elif pattern == "top_wave_arch":
        c.setFillColorRGB(*p_rgb)
        p1 = c.beginPath()
        p1.moveTo(*pt(0, 0))
        p1.lineTo(*pt(800, 0))
        p1.lineTo(*pt(800, 122))
        p1.curveTo(*pt(600, 175), *pt(200, 175), *pt(0, 122))
        p1.close()
        c.drawPath(p1, fill=1, stroke=0)
        p2 = c.beginPath()
        p2.moveTo(*pt(0, 1120))
        p2.lineTo(*pt(800, 1120))
        p2.lineTo(*pt(800, 1055))
        p2.curveTo(*pt(600, 1018), *pt(200, 1018), *pt(0, 1055))
        p2.close()
        c.drawPath(p2, fill=1, stroke=0)
        c.setStrokeColorRGB(*b_rgb)
        c.setLineWidth(6 * sy)
        p3 = c.beginPath()
        p3.moveTo(*pt(0, 125))
        p3.curveTo(*pt(200, 178), *pt(600, 178), *pt(800, 125))
        c.drawPath(p3, fill=0, stroke=1)

    elif pattern == "bottom_dual_wave":
        c.setFillColorRGB(*b_rgb)
        p1 = c.beginPath()
        p1.moveTo(*pt(0, 1008))
        p1.curveTo(*pt(220, 942), *pt(520, 1068), *pt(800, 990))
        p1.lineTo(*pt(800, 1120))
        p1.lineTo(*pt(0, 1120))
        p1.close()
        c.drawPath(p1, fill=1, stroke=0)
        c.setFillColorRGB(*p_rgb)
        p2 = c.beginPath()
        p2.moveTo(*pt(0, 1042))
        p2.curveTo(*pt(280, 992), *pt(540, 1088), *pt(800, 1022))
        p2.lineTo(*pt(800, 1120))
        p2.lineTo(*pt(0, 1120))
        p2.close()
        c.drawPath(p2, fill=1, stroke=0)

    elif pattern == "corner_brackets":
        for rgb, lw, off, span in ((p_rgb, 3.0, 22, 60), (b_rgb, 1.5, 32, 42)):
            c.setStrokeColorRGB(*rgb)
            c.setLineWidth(lw)
            for (x0, y0, dx, dy) in (
                (off, off, span, span),
                (800 - off, off, -span, span),
                (off, 1120 - off, span, -span),
                (800 - off, 1120 - off, -span, -span),
            ):
                p = c.beginPath()
                p.moveTo(*pt(x0, y0 + dy))
                p.lineTo(*pt(x0, y0))
                p.lineTo(*pt(x0 + dx, y0))
                c.drawPath(p, fill=0, stroke=1)

    elif pattern == "certificate_frame":
        c.setStrokeColorRGB(*p_rgb)
        c.setLineWidth(2.6)
        c.rect(18 * sx, 18 * sy, pw - 36 * sx, ph - 36 * sy, fill=0, stroke=1)
        c.setStrokeColorRGB(*b_rgb)
        c.setLineWidth(1.2)
        c.rect(26 * sx, 26 * sy, pw - 52 * sx, ph - 52 * sy, fill=0, stroke=1)
        c.setFillColorRGB(*b_rgb)
        for cx, cy in (pt(34, 34), pt(766, 34), pt(34, 1086), pt(766, 1086)):
            c.circle(cx, cy, 4.5, fill=1, stroke=0)

    elif pattern == "guilloche_wave":
        for y_base, rgb in ((175, p_rgb), (190, b_rgb), (205, p_rgb), (965, p_rgb), (980, b_rgb), (995, p_rgb)):
            c.setStrokeColorRGB(*rgb)
            c.setLineWidth(1.1)
            p = c.beginPath()
            p.moveTo(*pt(0, y_base))
            p.curveTo(*pt(200, y_base - 55), *pt(200, y_base - 55), *pt(400, y_base))
            p.curveTo(*pt(600, y_base + 55), *pt(600, y_base + 55), *pt(800, y_base))
            c.drawPath(p, fill=0, stroke=1)

    elif pattern == "diagonal_lines":
        step = 18.0
        c.setLineWidth(0.9)
        idx = 0
        x = -ph
        while x < pw + ph:
            c.setStrokeColorRGB(*(p_rgb if idx % 2 == 0 else b_rgb))
            c.line(x, 0, x + ph, ph)
            x += step
            idx += 1

    elif pattern == "subtle_grid":
        step = 18.0
        c.setStrokeColorRGB(*p_rgb)
        c.setLineWidth(0.5)
        x = 0.0
        while x <= pw:
            c.line(x, 0, x, ph)
            x += step
        y = 0.0
        while y <= ph:
            c.line(0, y, pw, y)
            y += step

    elif pattern == "diamond_lattice":
        step = 26.0
        c.setStrokeColorRGB(*p_rgb)
        c.setLineWidth(0.55)
        x = -ph
        while x < pw + ph:
            c.line(x, 0, x + ph, ph)
            c.line(x + ph, 0, x, ph)
            x += step

    elif pattern == "modern_hex_mesh":
        step_x, step_y = 33.0, 28.5
        c.setStrokeColorRGB(*p_rgb)
        c.setLineWidth(0.55)
        row = 0
        y = 0.0
        while y < ph + step_y:
            x = (step_x / 2.0) if (row % 2) else 0.0
            while x < pw + step_x:
                c.circle(x, y, 10.0, fill=0, stroke=1)
                x += step_x
            y += step_y
            row += 1

    elif pattern == "sunburst_crest":
        cx, cy = pw / 2.0, ph / 2.0
        r = min(pw, ph) * 0.36
        c.setLineWidth(0.9)
        for i in range(24):
            ang = math.radians(i * 15)
            c.setStrokeColorRGB(*(p_rgb if i % 2 == 0 else b_rgb))
            c.line(cx, cy, cx + math.cos(ang) * r, cy + math.sin(ang) * r)
        c.setStrokeColorRGB(*p_rgb)
        c.setLineWidth(1.4)
        c.circle(cx, cy, r * 0.45, fill=0, stroke=1)
        c.setStrokeColorRGB(*b_rgb)
        c.setLineWidth(1.0)
        c.circle(cx, cy, r * 0.50, fill=0, stroke=1)

    elif pattern == "swiss_dots":
        step = 18.0
        y = 9.0
        row = 0
        while y < ph:
            x = 9.0
            col = 0
            while x < pw:
                c.setFillColorRGB(*(p_rgb if (row + col) % 2 == 0 else b_rgb))
                c.circle(x, y, 0.9, fill=1, stroke=0)
                x += step
                col += 1
            y += step
            row += 1

    c.restoreState()


def _draw_logo(c, logo_uri: str, x: float, y: float, max_w: float, target_h: float, fit: str,
               mat: str, frame: str, accent_rgb, brand2_rgb, opacity_pct: int, dark_bg: bool,
               h_align: str = "left") -> tuple[float, float]:
    """Draw either an SVG or raster (PNG/JPEG/WebP) logo at (x, y) bottom-left and return (drawn_w, drawn_h)."""
    if not logo_uri or not logo_uri.startswith("data:image/") or "," not in logo_uri:
        return (0.0, 0.0)

    op = max(0.2, min(1.0, float(opacity_pct if opacity_pct is not None else 100) / 100.0))
    is_svg = "svg" in logo_uri[:35].lower()
    raw = base64.b64decode(logo_uri.split(",", 1)[1])

    c.saveState()
    try:
        c.setFillAlpha(op)
        c.setStrokeAlpha(op)
    except Exception:
        pass

    def _aligned_xy(dw: float, dh: float) -> tuple[float, float]:
        ax = x
        if h_align == "center":
            ax = x + (max_w - dw) / 2.0
        elif h_align == "right":
            ax = x + (max_w - dw)
        ay = y + (target_h - dh) / 2.0
        return ax, ay

    drawn_w, drawn_h = target_h, target_h
    if is_svg:
        try:
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            drawing = svg2rlg(io.BytesIO(raw))
            if drawing and drawing.width and drawing.height:
                ar = float(drawing.width) / max(1.0, float(drawing.height))
                if fit == "fill":
                    drawn_w, drawn_h = max_w, target_h
                else:
                    drawn_h = target_h
                    drawn_w = min(max_w, target_h * ar)
                    if drawn_w >= max_w:
                        drawn_h = drawn_w / max(0.2, ar)
                dx, dy = _aligned_xy(drawn_w, drawn_h)
                pad = 4.0 if mat in ("white", "brand") or frame in ("square", "circle") else 0.0
                if mat == "white":
                    c.setFillColorRGB(1, 1, 1)
                    c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=1, stroke=0)
                elif mat == "brand":
                    c.setFillColorRGB(*accent_rgb)
                    c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=1, stroke=0)
                drawing.scale(drawn_w / float(drawing.width), drawn_h / float(drawing.height))
                renderPDF.draw(drawing, c, dx, dy)
                if frame == "square":
                    c.setStrokeColorRGB(*accent_rgb)
                    c.setLineWidth(1.2)
                    c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=0, stroke=1)
                c.restoreState()
                return (drawn_w, drawn_h)
        except Exception:
            c.restoreState()
            return (0.0, 0.0)
    else:
        try:
            from reportlab.lib.utils import ImageReader
            pil_im = Image.open(io.BytesIO(raw)).convert("RGBA")
            ar = pil_im.width / max(1, pil_im.height)
            if fit == "fill":
                drawn_w, drawn_h = max_w, target_h
            else:
                drawn_h = target_h
                drawn_w = min(max_w, target_h * ar)
                if drawn_w >= max_w:
                    drawn_h = drawn_w / max(0.2, ar)
            dx, dy = _aligned_xy(drawn_w, drawn_h)
            pad = 4.0 if mat in ("white", "brand") or frame in ("square", "circle") else 0.0
            if mat == "white":
                c.setFillColorRGB(1, 1, 1)
                c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=1, stroke=0)
            elif mat == "brand":
                c.setFillColorRGB(*accent_rgb)
                c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=1, stroke=0)
            im_buf = io.BytesIO()
            pil_im.save(im_buf, format="PNG")
            im_buf.seek(0)
            c.drawImage(ImageReader(im_buf), dx, dy, width=drawn_w, height=drawn_h, mask="auto")
            if frame == "square":
                c.setStrokeColorRGB(*accent_rgb)
                c.setLineWidth(1.2)
                c.rect(dx - pad, dy - pad, drawn_w + pad * 2, drawn_h + pad * 2, fill=0, stroke=1)
            c.restoreState()
            return (drawn_w, drawn_h)
        except Exception:
            c.restoreState()
            return (0.0, 0.0)
    c.restoreState()
    return (0.0, 0.0)


def render_letterhead_pdf_from_config(cfg: dict[str, Any], title: str = "Official Letterhead") -> bytes:
    """Render a full-fidelity vector PDF directly from a letterhead layout config dict."""
    from reportlab.lib.pagesizes import A4, A5, B5, LEGAL, LETTER, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as pdf_canvas

    cfg = cfg or {}
    paper_key = str(cfg.get("paper_size") or "a4").lower()
    size_map = {
        "a4": A4,
        "letter": LETTER,
        "legal": LEGAL,
        "a5": A5,
        "executive": (184.15 * mm, 266.7 * mm),
        "b5": B5,
    }
    pagesize = size_map.get(paper_key, A4)
    if str(cfg.get("orientation") or "portrait").lower() == "landscape":
        pagesize = landscape(pagesize)
    pw, ph = pagesize
    margin_x = max(10, min(40, int(cfg.get("margin_mm") or 22))) * mm
    margin_y = max(10, min(40, int(cfg.get("margin_y_mm") or 20))) * mm

    accent_rgb = _hex_rgb(str(cfg.get("accent_color") or "#002769"), (0.0, 0.153, 0.412))
    brand2_rgb = _hex_rgb(str(cfg.get("brand_secondary") or "#c59b27"), (0.77, 0.61, 0.15))
    sec_rgb = _hex_rgb(str(cfg.get("secondary_color") or "#334155"), (0.20, 0.25, 0.33))
    paper_rgb = _hex_rgb(str(cfg.get("paper_bg") or "#ffffff"), (1.0, 1.0, 1.0))

    font_key = str(cfg.get("font_style") or "sans").lower()
    if font_key in ("serif", "legal", "garamond"):
        f_reg, f_bold = "Times-Roman", "Times-Bold"
    elif font_key == "mono":
        f_reg, f_bold = "Courier", "Courier-Bold"
    else:
        f_reg, f_bold = "Helvetica", "Helvetica-Bold"

    buf = io.BytesIO()
    c = pdf_canvas.Canvas(buf, pagesize=pagesize)
    c.setTitle(title or "Official Letterhead")

    # 1. Paper stock fill
    if paper_rgb != (1.0, 1.0, 1.0):
        c.setFillColorRGB(*paper_rgb)
        c.rect(0, 0, pw, ph, fill=1, stroke=0)

    # 2. Dual-tone vector background pattern (supports all 120+ luxury SVG patterns + native fallback)
    bg_pat_svg = str(cfg.get("bg_pattern_svg") or "").strip()
    bg_pat_op = int(cfg.get("bg_pattern_opacity") if cfg.get("bg_pattern_opacity") is not None else 85)
    drew_svg_pat = False
    if bg_pat_svg and "<svg" in bg_pat_svg and str(cfg.get("bg_pattern") or "none").lower() != "none":
        try:
            from reportlab.graphics import renderPDF
            from svglib.svglib import svg2rlg
            drawing = svg2rlg(io.BytesIO(bg_pat_svg.encode("utf-8")))
            if drawing and drawing.width and drawing.height:
                c.saveState()
                try:
                    op_val = max(0.05, min(1.0, bg_pat_op / 100.0))
                    c.setFillAlpha(op_val)
                    c.setStrokeAlpha(op_val)
                except Exception:
                    pass
                drawing.scale(pw / float(drawing.width), ph / float(drawing.height))
                renderPDF.draw(drawing, c, 0, 0)
                c.restoreState()
                drew_svg_pat = True
        except Exception:
            drew_svg_pat = False
    if not drew_svg_pat:
        _draw_bg_pattern(
            c,
            str(cfg.get("bg_pattern") or "none").lower(),
            pw, ph, accent_rgb, brand2_rgb,
            bg_pat_op,
        )

    # 3. Left edge bar
    left_bar_px = max(0, min(16, int(cfg.get("left_bar_px") or 0)))
    if left_bar_px > 0:
        c.setFillColorRGB(*accent_rgb)
        c.rect(0, 0, left_bar_px * 0.75, ph, fill=1, stroke=0)

    # 4. Page frame border
    page_border = str(cfg.get("page_border") or "none").lower()
    if page_border == "thin":
        c.setStrokeColorRGB(0.75, 0.78, 0.82)
        c.setLineWidth(0.75)
        c.rect(10.5, 10.5, pw - 21, ph - 21, fill=0, stroke=1)
    elif page_border == "double":
        c.setStrokeColorRGB(*accent_rgb)
        c.setLineWidth(1.6)
        c.rect(10.5, 10.5, pw - 21, ph - 21, fill=0, stroke=1)
        c.setLineWidth(0.6)
        c.rect(13.5, 13.5, pw - 27, ph - 27, fill=0, stroke=1)

    # 5. Optional Background Crest Image
    bg_img_uri = str(cfg.get("bg_image_data_uri") or "").strip()
    if bg_img_uri.startswith("data:image/") and "," in bg_img_uri and "svg" not in bg_img_uri[:35].lower():
        try:
            raw_bg = base64.b64decode(bg_img_uri.split(",", 1)[1])
            pil_bg = Image.open(io.BytesIO(raw_bg)).convert("RGBA")
            scale_pct = max(20, min(85, int(cfg.get("bg_image_scale") or 42))) / 100.0
            op_bg = max(2, min(40, int(cfg.get("bg_image_opacity") or 8))) / 100.0
            bw = pw * scale_pct
            bh = bw / max(0.2, pil_bg.width / max(1, pil_bg.height))
            bh = min(bh, ph * 0.55)
            bw = bh * (pil_bg.width / max(1, pil_bg.height))
            im_buf = io.BytesIO()
            pil_bg.save(im_buf, format="PNG")
            im_buf.seek(0)
            c.saveState()
            try:
                c.setFillAlpha(op_bg)
            except Exception:
                pass
            c.drawImage(ImageReader(im_buf), (pw - bw) / 2.0, (ph - bh) / 2.0, width=bw, height=bh, mask="auto")
            c.restoreState()
        except Exception:
            pass

    # 6. Optional Text Watermark
    wm_text = str(cfg.get("watermark_text") or "").strip()
    if wm_text:
        wm_op = max(3, min(25, int(cfg.get("watermark_opacity") or 6))) / 100.0
        wm_ang = -int(cfg.get("watermark_angle") if cfg.get("watermark_angle") is not None else -28)
        c.saveState()
        c.translate(pw / 2.0, ph / 2.0)
        c.rotate(wm_ang)
        try:
            c.setFillAlpha(wm_op)
        except Exception:
            pass
        c.setFillColorRGB(*accent_rgb)
        c.setFont(f_bold, 42)
        c.drawCentredString(0, 0, wm_text)
        c.restoreState()

    # 7. Header geometry & styles
    align = str(cfg.get("header_align") or "left").lower()
    hdr_bg = str(cfg.get("header_bg") or "none").lower()
    hdr_bleed = str(cfg.get("header_bleed") or ("bleed" if align == "banner" else "margin")).lower()
    is_bleed_hdr = (hdr_bleed == "bleed" or align == "banner")
    is_dark_hdr = (align == "banner" or hdr_bg in ("solid", "gradient", "angled"))
    top_bar_px = max(0, min(12, int(cfg.get("top_bar_px") or 0)))

    # Top dual-tone brand stripe (when not full-bleed banner)
    if top_bar_px > 0 and not is_bleed_hdr:
        t_pt = top_bar_px * 0.75
        c.setFillColorRGB(*accent_rgb)
        c.rect(0, ph - t_pt, pw * 0.72, t_pt, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        c.rect(pw * 0.72, ph - t_pt, pw * 0.28, t_pt, fill=1, stroke=0)

    # Measure header block height
    hide_org = bool(cfg.get("hide_org_name", False))
    show_tag = cfg.get("show_tagline", True)
    show_ct = cfg.get("show_contact", True)
    org_name = "" if hide_org else str(cfg.get("org_name") or "").strip()
    if org_name and cfg.get("org_uppercase", False):
        org_name = org_name.upper()
    org_pt = max(10, min(28, int(cfg.get("org_font_pt") or 15)))
    tag_pt = max(6.5, min(14.0, float(cfg.get("tagline_font_pt") or 8.5)))
    ct_pt = max(6.5, min(12.0, float(cfg.get("contact_font_pt") or 8.2)))
    tagline = str(cfg.get("tagline") or "").strip() if show_tag else ""
    dept = str(cfg.get("department") or "").strip() if show_tag else ""
    addr_line = "  ·  ".join(p for p in (str(cfg.get("address") or "").strip(), str(cfg.get("postal_address") or "").strip()) if p) if show_ct else ""
    contact_line = "  ·  ".join(p for p in (
        str(cfg.get("phone") or "").strip(),
        str(cfg.get("secondary_phone") or "").strip(),
        str(cfg.get("email") or "").strip(),
        str(cfg.get("website") or "").strip(),
    ) if p) if show_ct else ""
    reg_line = "  ·  ".join(p for p in (
        str(cfg.get("reg_no") or "").strip(),
        str(cfg.get("tax_id") or "").strip(),
        str(cfg.get("license_no") or "").strip(),
    ) if p)

    logo_uri = str(cfg.get("logo_data_uri") or "").strip()
    logo_h_pt = max(18.0, min(120.0, float(cfg.get("logo_height_px") or 50) * 0.75)) if logo_uri else 0.0
    logo_w_pt = max(30.0, min(240.0, float(cfg.get("logo_width_px") or 220) * 0.75)) if logo_uri else 0.0
    logo_ox = float(cfg.get("logo_offset_x") or 0) * 0.75
    logo_oy = -float(cfg.get("logo_offset_y") or 0) * 0.75
    logo_fit = str(cfg.get("logo_fit") or "contain").lower()
    logo_mat = str(cfg.get("logo_mat") or "none").lower()
    logo_frame = str(cfg.get("logo_frame") or "none").lower()
    logo_op = int(cfg.get("logo_opacity") if cfg.get("logo_opacity") is not None else 100)

    h_pad_y = max(0.0, float(cfg.get("header_pad_y") if cfg.get("header_pad_y") is not None else 14) * 0.75)
    h_pad_x = float(cfg.get("header_pad_x") if cfg.get("header_pad_x") is not None else 24) * 0.75
    h_min_h = max(0.0, float(cfg.get("header_min_height") or 0) * 0.75)

    text_lines_h = (org_pt + 4 if org_name else 0) + (tag_pt + 4 if tagline else 0) + (tag_pt + 3 if dept else 0)
    if align != "split" and align != "banner":
        text_lines_h += (ct_pt + 4 if addr_line else 0) + (ct_pt + 4 if contact_line else 0)
    content_h = max(logo_h_pt, text_lines_h, 16.0)
    if align == "center" and logo_h_pt > 0:
        content_h = logo_h_pt + (8 + text_lines_h if text_lines_h > 0 else 0) + (ct_pt + 3 if reg_line and show_ct else 0)

    # Match Designer exact vertical geometry:
    # - When top_bar_px > 0 and not bleed, top_bar sits at page top (y=0) with 18px bottom gap.
    # - When header_bg == 'none' and not bleed, header top padding is 0px (content starts immediately).
    h_pad_top = max(12.0, h_pad_y) if is_bleed_hdr else (h_pad_y if hdr_bg != "none" else 0.0)
    h_pad_bot = max(12.0, h_pad_y) if is_bleed_hdr else max(6.0, h_pad_y)
    hdr_box_h = max(h_min_h, content_h + h_pad_top + h_pad_bot)

    if is_bleed_hdr:
        hdr_top_y = ph
    elif top_bar_px > 0:
        hdr_top_y = ph - (top_bar_px + 18.0) * 0.75
    else:
        hdr_top_y = ph - margin_y
    hdr_bot_y = hdr_top_y - hdr_box_h
    hdr_left_x = 0.0 if is_bleed_hdr else margin_x
    hdr_box_w = pw if is_bleed_hdr else (pw - 2 * margin_x)
    inner_left = (max(9.0, h_pad_x) if is_bleed_hdr else (margin_x + (max(9.0, min(27.0, h_pad_x)) if hdr_bg != "none" else 0.0)))
    inner_right = pw - inner_left

    # Header background fill
    if hdr_bg == "solid" or (align == "banner" and hdr_bg == "none"):
        c.setFillColorRGB(*accent_rgb)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, 2.5, fill=1, stroke=0)
    elif hdr_bg == "gradient":
        steps = 24
        sw = hdr_box_w / steps
        for i in range(steps):
            t = i / float(steps - 1)
            rgb = _blend(brand2_rgb, accent_rgb, t * 0.55)
            c.setFillColorRGB(*rgb)
            c.rect(hdr_left_x + i * sw, hdr_bot_y, sw + 0.5, hdr_box_h, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, 2.5, fill=1, stroke=0)
    elif hdr_bg == "angled":
        c.setFillColorRGB(*accent_rgb)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        _draw_poly(c, [
            (hdr_left_x + hdr_box_w * 0.70, hdr_top_y),
            (hdr_left_x + hdr_box_w, hdr_top_y),
            (hdr_left_x + hdr_box_w, hdr_bot_y),
            (hdr_left_x + hdr_box_w * 0.62, hdr_bot_y),
        ])
    elif hdr_bg == "neutral":
        c.setFillColorRGB(0.965, 0.973, 0.984)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
    elif hdr_bg == "tint":
        c.setFillColorRGB(*_blend(accent_rgb, (1.0, 1.0, 1.0), 0.08))
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
    elif hdr_bg == "framed":
        c.setFillColorRGB(0.973, 0.98, 0.988)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
        c.setFillColorRGB(*accent_rgb)
        c.rect(hdr_left_x, hdr_bot_y, 3.2, hdr_box_h, fill=1, stroke=0)
    elif hdr_bg == "underline_band":
        c.setFillColorRGB(0.973, 0.98, 0.988)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, hdr_box_h, fill=1, stroke=0)
        c.setFillColorRGB(*accent_rgb)
        c.rect(hdr_left_x, hdr_top_y - 3.0, hdr_box_w, 3.0, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        c.rect(hdr_left_x, hdr_bot_y, hdr_box_w, 1.8, fill=1, stroke=0)

    ink_prim = (1.0, 1.0, 1.0) if is_dark_hdr else accent_rgb
    ink_sec = (0.90, 0.92, 0.96) if is_dark_hdr else sec_rgb
    ink_tag = brand2_rgb if is_dark_hdr else sec_rgb

    # Per-element position offsets (px -> pt), text alignment overrides, and exact Editor measured boxes
    el_pos = cfg.get("el_pos") if isinstance(cfg.get("el_pos"), dict) else {}
    el_align = cfg.get("el_align") if isinstance(cfg.get("el_align"), dict) else {}
    m_boxes = cfg.get("measured_boxes") if isinstance(cfg.get("measured_boxes"), dict) else {}

    def _el_delta(key: str) -> tuple[float, float]:
        p = el_pos.get(key)
        if not isinstance(p, dict):
            return 0.0, 0.0
        return float(p.get("x") or 0) * 0.75, -float(p.get("y") or 0) * 0.75

    def _draw_el_text(key: str, txt: str, def_x: float, y: float, def_al: str, lx: float, rx: float) -> None:
        dx, dy = _el_delta(key)
        al = str(el_align.get(key) or def_al).lower()
        yy = y + dy
        if al == "center":
            c.drawCentredString((lx + rx) / 2.0 + dx, yy, txt)
        elif al == "right":
            c.drawRightString(rx + dx, yy, txt)
        else:
            c.drawString(def_x + dx, yy, txt)

    def _draw_measured_lines(key: str, font_name: str, font_pt: float, rgb_color) -> bool:
        mb = m_boxes.get(key)
        if not isinstance(mb, dict) or not mb.get("lines"):
            return False
        c.setFillColorRGB(*rgb_color)
        c.setFont(font_name, font_pt)
        al_override = str(el_align.get(key) or "").lower()
        for ln in mb["lines"]:
            txt = str(ln.get("text") or "").strip()
            if not txt:
                continue
            bx = float(ln.get("rx", mb.get("rx", 0))) * pw
            by_top = ph - float(ln.get("ry", mb.get("ry", 0))) * ph
            bw = float(ln.get("rw", mb.get("rw", 0))) * pw
            bh = float(ln.get("rh", 0)) * ph
            baseline_y = by_top - (bh * 0.76 if bh > 2 else font_pt * 0.82)
            al = al_override or str(ln.get("align") or mb.get("align") or "left").lower()
            if al == "center":
                c.drawCentredString(bx + bw / 2.0, baseline_y, txt)
            elif al == "right":
                c.drawRightString(bx + bw, baseline_y, txt)
            else:
                c.drawString(bx, baseline_y, txt)
        return True

    # Draw Header Content — prefer exact 1:1 Editor measured boxes when available
    if m_boxes and any(k in m_boxes for k in ("logo", "org_title", "tagline", "contact")):
        if logo_uri and isinstance(m_boxes.get("logo"), dict):
            lb = m_boxes["logo"]
            lx = float(lb["rx"]) * pw
            lw = max(8.0, float(lb["rw"]) * pw)
            lh = max(8.0, float(lb["rh"]) * ph)
            ly = ph - (float(lb["ry"]) + float(lb["rh"])) * ph
            _draw_logo(c, logo_uri, lx, ly, lw, lh, "fill", logo_mat, logo_frame, accent_rgb, brand2_rgb, logo_op, is_dark_hdr)
        if org_name:
            if not _draw_measured_lines("org_title", f_bold, org_pt, ink_prim):
                mb = m_boxes.get("org_title")
                if isinstance(mb, dict):
                    bx, bw = float(mb["rx"]) * pw, float(mb["rw"]) * pw
                    by = ph - float(mb["ry"]) * ph - org_pt * 0.82
                    al = str(el_align.get("org_title") or mb.get("align") or "left").lower()
                    c.setFillColorRGB(*ink_prim); c.setFont(f_bold, org_pt)
                    if al == "center": c.drawCentredString(bx + bw / 2.0, by, org_name)
                    elif al == "right": c.drawRightString(bx + bw, by, org_name)
                    else: c.drawString(bx, by, org_name)
        if tagline or dept:
            if not _draw_measured_lines("tagline", f_bold, tag_pt, ink_tag):
                pass
        if addr_line or contact_line or (reg_line and show_ct):
            _draw_measured_lines("contact", f_reg, ct_pt, ink_sec)
    elif align == "center":
        y_cur = hdr_top_y - h_pad_top
        cx = pw / 2.0
        if logo_uri:
            dw, dh = _draw_logo(c, logo_uri, cx - logo_w_pt / 2.0 + logo_ox, y_cur - logo_h_pt + logo_oy,
                                logo_w_pt, logo_h_pt, logo_fit, logo_mat, logo_frame, accent_rgb, brand2_rgb, logo_op, is_dark_hdr,
                                h_align="center")
            y_cur -= (dh + 8)
        if org_name:
            c.setFillColorRGB(*ink_prim)
            c.setFont(f_bold, org_pt)
            _draw_el_text("org_title", org_name, inner_left, y_cur - org_pt * 0.8, "center", inner_left, inner_right)
            y_cur -= (org_pt + 4)
        if tagline:
            c.setFillColorRGB(*ink_tag)
            c.setFont(f_bold, tag_pt)
            _draw_el_text("tagline", tagline.upper(), inner_left, y_cur - tag_pt, "center", inner_left, inner_right)
            y_cur -= (tag_pt + 4)
        if dept:
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, tag_pt)
            _draw_el_text("tagline", dept, inner_left, y_cur - tag_pt, "center", inner_left, inner_right)
            y_cur -= (tag_pt + 4)
        if addr_line:
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, ct_pt)
            _draw_el_text("contact", addr_line, inner_left, y_cur - ct_pt, "center", inner_left, inner_right)
            y_cur -= (ct_pt + 3)
        if contact_line:
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, ct_pt)
            _draw_el_text("contact", contact_line, inner_left, y_cur - ct_pt, "center", inner_left, inner_right)
    else:
        text_x = inner_left
        mid_y = hdr_top_y - h_pad_top - content_h / 2.0
        if logo_uri and align != "right":
            dw, dh = _draw_logo(c, logo_uri, inner_left + logo_ox, mid_y - logo_h_pt / 2.0 + logo_oy,
                                logo_w_pt, logo_h_pt, logo_fit, logo_mat, logo_frame, accent_rgb, brand2_rgb, logo_op, is_dark_hdr)
            text_x = inner_left + dw + 12
        elif logo_uri and align == "right":
            _draw_logo(c, logo_uri, inner_right - logo_w_pt + logo_ox, mid_y - logo_h_pt / 2.0 + logo_oy,
                       logo_w_pt, logo_h_pt, logo_fit, logo_mat, logo_frame, accent_rgb, brand2_rgb, logo_op, is_dark_hdr,
                       h_align="right")

        ty = hdr_top_y - h_pad_top - org_pt * 0.85
        if org_name:
            c.setFillColorRGB(*ink_prim)
            c.setFont(f_bold, org_pt)
            _draw_el_text("org_title", org_name, text_x, ty, "left", text_x, inner_right)
            ty -= (org_pt * 0.95 + 3)
        if tagline:
            c.setFillColorRGB(*ink_tag)
            c.setFont(f_bold, tag_pt)
            _draw_el_text("tagline", tagline.upper(), text_x, ty, "left", text_x, inner_right)
            ty -= (tag_pt + 3)
        if dept:
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, tag_pt)
            _draw_el_text("tagline", dept, text_x, ty, "left", text_x, inner_right)
            ty -= (tag_pt + 3)

        if align in ("split", "banner"):
            ry = hdr_top_y - h_pad_top - ct_pt
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, ct_pt)
            for line in (addr_line, contact_line, reg_line if show_ct else ""):
                if line:
                    _draw_el_text("contact", line, text_x, ry, "right", text_x, inner_right)
                    ry -= (ct_pt + 3.5)
        else:
            c.setFillColorRGB(*ink_sec)
            c.setFont(f_reg, ct_pt)
            if addr_line:
                _draw_el_text("contact", addr_line, text_x, ty, "left", text_x, inner_right)
                ty -= (ct_pt + 3)
            if contact_line:
                _draw_el_text("contact", contact_line, text_x, ty, "left", text_x, inner_right)

    # 8. Header Divider Line (FULL PAGE WIDTH, edge-to-edge, 0 margin)
    div_style = str(cfg.get("divider_style") or "solid").lower()
    div_px = max(1, min(8, int(cfg.get("divider_px") or 2))) * 0.75
    if isinstance(m_boxes.get("divider"), dict):
        y_div = ph - (float(m_boxes["divider"]["ry"]) + float(m_boxes["divider"].get("rh", 0)) / 2.0) * ph
    else:
        y_div = hdr_bot_y - 4
    if cfg.get("show_divider", True) and div_style != "none" and not is_dark_hdr:
        if div_style == "dual":
            c.setFillColorRGB(*accent_rgb)
            c.rect(0, y_div - div_px, pw * 0.72, div_px, fill=1, stroke=0)
            c.setFillColorRGB(*brand2_rgb)
            c.rect(pw * 0.72, y_div - div_px, pw * 0.28, div_px, fill=1, stroke=0)
        elif div_style == "double":
            c.setStrokeColorRGB(*accent_rgb)
            c.setLineWidth(div_px)
            c.line(0, y_div, pw, y_div)
            c.setLineWidth(0.6)
            c.line(0, y_div - div_px - 1.5, pw, y_div - div_px - 1.5)
        elif div_style == "thin":
            c.setStrokeColorRGB(0.84, 0.87, 0.90)
            c.setLineWidth(max(0.6, div_px * 0.5))
            c.line(0, y_div, pw, y_div)
        elif div_style == "dotted":
            c.setStrokeColorRGB(*accent_rgb)
            c.setLineWidth(div_px)
            c.setDash(1.5, 2.5)
            c.line(0, y_div, pw, y_div)
            c.setDash()
        else:
            c.setFillColorRGB(*accent_rgb)
            c.rect(0, y_div - div_px, pw, div_px, fill=1, stroke=0)

    # 9. Reference & Date Bar
    if cfg.get("show_ref_bar", False):
        ref_pt = max(7.0, min(12.0, float(cfg.get("ref_font_pt") or 8.5)))
        ref_style = str(cfg.get("ref_bar_style") or "classic").lower()
        l1 = str(cfg.get("ref_label_1") if cfg.get("ref_label_1") is not None else "Our Ref").strip()
        l2 = str(cfg.get("ref_label_2") if cfg.get("ref_label_2") is not None else "Your Ref").strip()
        l3 = str(cfg.get("ref_label_3") if cfg.get("ref_label_3") is not None else "Date").strip()
        ry_bar = y_div - 18
        c.setFillColorRGB(*sec_rgb)
        c.setFont(f_reg, ref_pt)
        if ref_style == "memo":
            c.setFillColorRGB(0.965, 0.973, 0.984)
            c.rect(margin_x, ry_bar - 22, pw - 2 * margin_x, 32, fill=1, stroke=0)
            c.setFillColorRGB(*brand2_rgb)
            c.rect(margin_x, ry_bar - 22, 2.5, 32, fill=1, stroke=0)
            c.setFillColorRGB(*sec_rgb)
            c.drawString(margin_x + 8, ry_bar - 4, "TO: _____________________")
            c.drawString(pw / 2.0, ry_bar - 4, "DATE: ___________________")
            c.drawString(margin_x + 8, ry_bar - 16, "FROM: ___________________")
            c.drawString(pw / 2.0, ry_bar - 16, "REF: ____________________")
        elif ref_style == "compact":
            if l1:
                c.drawString(margin_x, ry_bar, f"{l1}: ________________")
            if l3:
                c.drawRightString(pw - margin_x, ry_bar, f"{l3}: ________________")
        else:
            if ref_style == "boxed":
                c.setFillColorRGB(0.965, 0.973, 0.984)
                c.rect(margin_x, ry_bar - 6, pw - 2 * margin_x, 18, fill=1, stroke=0)
                c.setFillColorRGB(*brand2_rgb)
                c.rect(margin_x, ry_bar - 6, 2.5, 18, fill=1, stroke=0)
                c.setFillColorRGB(*sec_rgb)
            pad_in = 8 if ref_style == "boxed" else 0
            if l1:
                c.drawString(margin_x + pad_in, ry_bar, f"{l1}: ________________")
            if l2:
                c.drawCentredString(pw / 2.0, ry_bar, f"{l2}: ________________")
            if l3:
                c.drawRightString(pw - margin_x - pad_in, ry_bar, f"{l3}: ________________")

    # 10. Official Footer (with Full-Bleed, Styles, Directors, Banking, Bottom Stripe)
    show_footer = cfg.get("show_footer", True)
    ftr_bleed = str(cfg.get("footer_bleed") or "margin").lower() == "bleed"
    ftr_bg = str(cfg.get("footer_bg") or "none").lower()
    is_dark_ftr = ftr_bg in ("solid", "gradient")
    ftr_pt = max(6.5, min(11.0, float(cfg.get("footer_font_pt") or 8.0)))
    ftr_pad_y = max(4.0, float(cfg.get("footer_pad_y") if cfg.get("footer_pad_y") is not None else 10) * 0.75)
    ftr_min_h = max(0.0, float(cfg.get("footer_min_height") or 0) * 0.75)

    directors = str(cfg.get("directors") or "").strip()
    bank_details = str(cfg.get("bank_details") or "").strip()
    footer_text = str(cfg.get("footer_text") or "").strip() or reg_line or org_name
    ftr_lines = (1 if directors else 0) + (1 if bank_details else 0) + 1
    ftr_box_h = max(ftr_min_h, ftr_lines * (ftr_pt + 3.5) + ftr_pad_y * 2)

    ftr_bot_y = 0.0 if ftr_bleed else margin_y
    ftr_top_y = ftr_bot_y + ftr_box_h
    ftr_left_x = 0.0 if ftr_bleed else margin_x
    ftr_box_w = pw if ftr_bleed else (pw - 2 * margin_x)

    if show_footer:
        if ftr_bg == "solid":
            c.setFillColorRGB(*accent_rgb)
            c.rect(ftr_left_x, ftr_bot_y, ftr_box_w, ftr_box_h, fill=1, stroke=0)
        elif ftr_bg == "gradient":
            steps = 20
            sw = ftr_box_w / steps
            for i in range(steps):
                c.setFillColorRGB(*_blend(brand2_rgb, accent_rgb, (i / float(steps - 1)) * 0.5))
                c.rect(ftr_left_x + i * sw, ftr_bot_y, sw + 0.5, ftr_box_h, fill=1, stroke=0)
        elif ftr_bg == "neutral":
            c.setFillColorRGB(0.965, 0.973, 0.984)
            c.rect(ftr_left_x, ftr_bot_y, ftr_box_w, ftr_box_h, fill=1, stroke=0)
        elif ftr_bg == "tint":
            c.setFillColorRGB(*_blend(accent_rgb, (1.0, 1.0, 1.0), 0.08))
            c.rect(ftr_left_x, ftr_bot_y, ftr_box_w, ftr_box_h, fill=1, stroke=0)

        if cfg.get("show_footer_rule", True) and not is_dark_ftr:
            c.setStrokeColorRGB(0.86, 0.88, 0.91)
            c.setLineWidth(0.7)
            y_frule = (ph - (float(m_boxes["footer_rule"]["ry"]) + float(m_boxes["footer_rule"].get("rh", 0)) / 2.0) * ph) if isinstance(m_boxes.get("footer_rule"), dict) else ftr_top_y
            c.line(0, y_frule, pw, y_frule)

        f_ink = (0.94, 0.95, 0.98) if is_dark_ftr else sec_rgb
        f_mut = (0.78, 0.82, 0.88) if is_dark_ftr else (0.48, 0.53, 0.60)
        ftr_dx, ftr_dy = _el_delta("footer_content")
        ftr_al = str(el_align.get("footer_content") or "").lower()
        fy = (ph - float(m_boxes["footer_content"]["ry"]) * ph - ftr_pt * 0.9) if isinstance(m_boxes.get("footer_content"), dict) else (ftr_top_y - ftr_pad_y - ftr_pt + ftr_dy)
        if directors:
            c.setFillColorRGB(*f_mut)
            c.setFont(f_reg, max(6.5, ftr_pt - 0.5))
            c.drawString(margin_x + ftr_dx, fy, f"Directors / Officers: {directors[:120]}")
            fy -= (ftr_pt + 2.5)
        if bank_details:
            c.setFillColorRGB(*f_mut)
            c.setFont(f_reg, max(6.5, ftr_pt - 0.5))
            c.drawString(margin_x + ftr_dx, fy, f"Banking: {bank_details[:120]}")
            fy -= (ftr_pt + 2.5)

        right_bits = []
        if cfg.get("show_page_numbers", False):
            right_bits.append("Page 1 of 1")
        if cfg.get("show_trust_badge", True):
            right_bits.append("Verified · TrustSeal Document")
        right_str = "  ·  ".join(right_bits)

        ftr_layout = str(cfg.get("footer_layout") or "split").lower()
        c.setFont(f_reg, ftr_pt)
        if ftr_al == "center" or ftr_layout == "centered":
            c.setFillColorRGB(*f_ink)
            c.drawCentredString(pw / 2.0 + ftr_dx, fy, footer_text[:110])
            if right_str:
                c.setFillColorRGB(*f_mut)
                c.drawCentredString(pw / 2.0 + ftr_dx, fy - ftr_pt - 2, right_str)
        elif ftr_al == "right":
            c.setFillColorRGB(*f_ink)
            c.drawRightString(pw - margin_x + ftr_dx, fy, footer_text[:110])
            if right_str:
                c.setFillColorRGB(*f_mut)
                c.drawRightString(pw - margin_x + ftr_dx, fy - ftr_pt - 2, right_str)
        else:
            c.setFillColorRGB(*f_ink)
            c.drawString(margin_x + ftr_dx, fy, footer_text[:110])
            if right_str:
                c.setFillColorRGB(*f_mut)
                c.drawRightString(pw - margin_x + ftr_dx, fy, right_str)

    if cfg.get("show_bottom_bar", False) and not ftr_bleed:
        b_pt = max(2, min(14, int(cfg.get("bottom_bar_px") or 5))) * 0.75
        c.setFillColorRGB(*accent_rgb)
        c.rect(0, 0, pw * 0.72, b_pt, fill=1, stroke=0)
        c.setFillColorRGB(*brand2_rgb)
        c.rect(pw * 0.72, 0, pw * 0.28, b_pt, fill=1, stroke=0)

    c.showPage()
    c.save()
    return buf.getvalue()
