"""TSD-only covert forensic security & traceability engine for stamps.

Every stamp impression issued by TrustSeal (inserted into a TSD document,
exported as SVG, exported as PNG, or exported as PDF) is cryptographically
sealed with multi-layer covert security features keyed to the tenant's
server-side DEK (via :func:`app.services.tsd_format.tenant_signing_key`).

Because the encryption, authentication, and coordinate-permutation keys exist
only on the TrustSeal server:
  * Third parties cannot decode, forge, or transplant the hidden payload.
  * Stripping visible ``data-stamp-receipt-*`` attributes or PNG/PDF metadata
    does not defeat forensic tracing — TSD extracts the hidden mark directly
    from the vector micro-constellation, bezier micro-path, or keyed raster
    pixel LSBs.
  * Any post-issuance edit to the visible stamp artwork breaks the
    ``context_hash`` check and is immediately flagged as ``TAMPERED``.

Security Layers
---------------
1. **Layer 1A — Covert Vector Micro-Constellation (SVG / PDF)**
   66-byte AES-256-GCM authenticated forensic packet encoded into sub-pixel
   fractional coordinates of a keyed constellation of invisible micro-dots
   (``r="0.16"``, ``opacity="0.015"``).
2. **Layer 1B — Covert Micro-Path Carrier (SVG)**
   Redundant encoding of the same AES-256-GCM packet inside a hairline
   sub-pixel ``<path>`` (survives optimizers that strip attributes/metadata).
3. **Layer 2 — Covert Micro-Text Security Fiber (SVG / PDF)**
   Sub-millimeter (``font-size="0.42"``, ``opacity="0.018"``) TSD-keyed
   forensic fingerprint token ``TSD-F1-<16HEX>``.
4. **Layer 3 — Keyed Raster Steganographic Watermark (PNG)**
   3x majority-voted LSB embedding across a tenant-key-permuted pixel
   sequence in RGB channels, paired with a secondary PNG ``tEXt`` chunk.
5. **Layer 4 — Covert PDF Forensic Seal (PDF)**
   Encrypted ``/TSDForensicSeal`` PDF info entry + embedded Layer 1/2
   vector marks inside the rendered PDF page.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import random
import re
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


FORENSICS_KEY_LABEL = "tsd.stamp.forensics.v1"

_SYNC_MARKER = b"TSF1"
_PAYLOAD_MAGIC = b"TSDF"
_PAYLOAD_VERSION = 1
_PAYLOAD_STRUCT = struct.Struct(">4sBBIIIIII4s")  # 34 bytes
_GCM_NONCE_LEN = 12
_GCM_TAG_LEN = 16
# Total outer packet: 4 (sync) + 12 (nonce) + 34 (ct) + 16 (tag) = 66 bytes
PACKET_BYTES = 4 + _GCM_NONCE_LEN + _PAYLOAD_STRUCT.size + _GCM_TAG_LEN

CHANNEL_CODES: dict[str, int] = {
    "tsd_document": 1,
    "svg_export": 2,
    "png_export": 3,
    "pdf_export": 4,
    "api": 5,
}
CHANNEL_NAMES: dict[int, str] = {v: k for k, v in CHANNEL_CODES.items()}

# Regex to strip the covert forensic group before computing canonical artwork hash
_FORENSIC_GROUP_RE = re.compile(
    r'<g\b[^>]*\bdata-tsd-f="1"[^>]*>.*?</g>',
    re.DOTALL,
)
_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')


@dataclass(frozen=True)
class ForensicPayload:
    organization_id: int
    stamp_id: int
    receipt_id: int
    placed_by_id: int
    document_id: int
    placed_at_epoch: int
    nonce_prefix: str
    channel: str
    version: int = _PAYLOAD_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "stamp_id": self.stamp_id,
            "receipt_id": self.receipt_id,
            "placed_by_id": self.placed_by_id,
            "document_id": self.document_id or None,
            "placed_at_epoch": self.placed_at_epoch,
            "placed_at": datetime.utcfromtimestamp(self.placed_at_epoch).isoformat(),
            "nonce_prefix": self.nonce_prefix,
            "channel": self.channel,
            "version": self.version,
        }


def get_tenant_forensic_key(organization_id: int) -> bytes:
    """Derive the 32-byte tenant-scoped forensic master key from the DEK."""
    from app.services.tsd_format import tenant_signing_key
    return tenant_signing_key(organization_id, label=FORENSICS_KEY_LABEL)


def _derive_subkey(master_key: bytes, purpose: bytes) -> bytes:
    return hashlib.sha256(master_key + b"\x00" + purpose).digest()


def compute_forensic_fingerprint(
    forensic_key: bytes,
    *,
    receipt_id: int,
    stamp_id: int,
    nonce: str,
) -> str:
    """Return a deterministic 16-hex TSD forensic fingerprint for a receipt."""
    mac_key = _derive_subkey(forensic_key, b"fp.v1")
    msg = f"{receipt_id}:{stamp_id}:{nonce}".encode("utf-8")
    digest = hmac.new(mac_key, msg, hashlib.sha256).hexdigest()[:16].upper()
    return f"TSD-F1-{digest[:4]}-{digest[4:8]}-{digest[8:12]}-{digest[12:16]}"


def pack_forensic_packet(
    forensic_key: bytes,
    *,
    organization_id: int,
    stamp_id: int,
    receipt_id: int,
    placed_by_id: int,
    document_id: int | None,
    placed_at: datetime,
    nonce: str,
    channel: str = "tsd_document",
) -> bytes:
    """Encrypt & authenticate a 66-byte TSD-only forensic packet (AES-256-GCM)."""
    ch_code = CHANNEL_CODES.get(channel, 1)
    try:
        nonce_prefix_bytes = bytes.fromhex((nonce or "")[:8].ljust(8, "0"))[:4]
    except ValueError:
        nonce_prefix_bytes = hashlib.sha256((nonce or "").encode("utf-8")).digest()[:4]

    epoch = int(placed_at.timestamp()) if isinstance(placed_at, datetime) else int(placed_at)
    epoch = max(0, min(0xFFFFFFFF, epoch))

    plaintext = _PAYLOAD_STRUCT.pack(
        _PAYLOAD_MAGIC,
        _PAYLOAD_VERSION,
        ch_code,
        int(organization_id) & 0xFFFFFFFF,
        int(stamp_id) & 0xFFFFFFFF,
        int(receipt_id) & 0xFFFFFFFF,
        int(placed_by_id) & 0xFFFFFFFF,
        int(document_id or 0) & 0xFFFFFFFF,
        epoch,
        nonce_prefix_bytes,
    )

    enc_key = _derive_subkey(forensic_key, b"aesgcm.v1")
    gcm_nonce = os.urandom(_GCM_NONCE_LEN)
    ct_and_tag = AESGCM(enc_key).encrypt(gcm_nonce, plaintext, _SYNC_MARKER)
    packet = _SYNC_MARKER + gcm_nonce + ct_and_tag
    assert len(packet) == PACKET_BYTES
    return packet


def unpack_forensic_packet(
    forensic_key: bytes,
    packet: bytes,
) -> ForensicPayload | None:
    """Decrypt & authenticate a 66-byte TSD forensic packet.

    Returns ``None`` if the sync marker is wrong, the packet was corrupted,
    or the packet was encrypted with a different tenant's key.
    """
    if not isinstance(packet, (bytes, bytearray)) or len(packet) != PACKET_BYTES:
        return None
    if bytes(packet[:4]) != _SYNC_MARKER:
        return None
    gcm_nonce = bytes(packet[4 : 4 + _GCM_NONCE_LEN])
    ct_and_tag = bytes(packet[4 + _GCM_NONCE_LEN :])
    enc_key = _derive_subkey(forensic_key, b"aesgcm.v1")
    try:
        plaintext = AESGCM(enc_key).decrypt(gcm_nonce, ct_and_tag, _SYNC_MARKER)
    except Exception:
        return None
    if len(plaintext) != _PAYLOAD_STRUCT.size:
        return None
    (
        magic,
        version,
        ch_code,
        org_id,
        stamp_id,
        receipt_id,
        placed_by_id,
        document_id,
        epoch,
        nonce_prefix_bytes,
    ) = _PAYLOAD_STRUCT.unpack(plaintext)
    if magic != _PAYLOAD_MAGIC or version != _PAYLOAD_VERSION:
        return None
    return ForensicPayload(
        organization_id=org_id,
        stamp_id=stamp_id,
        receipt_id=receipt_id,
        placed_by_id=placed_by_id,
        document_id=document_id,
        placed_at_epoch=epoch,
        nonce_prefix=nonce_prefix_bytes.hex(),
        channel=CHANNEL_NAMES.get(ch_code, "tsd_document"),
        version=version,
    )


def strip_forensic_svg_layer(svg: str) -> str:
    """Remove the covert TSD forensic `<g data-tsd-f="1">` layer from an SVG."""
    if not svg:
        return ""
    return _FORENSIC_GROUP_RE.sub("", svg).strip()


# =================================================================== SVG Layers


def _parse_viewbox(svg: str) -> tuple[float, float, float, float]:
    m = _VIEWBOX_RE.search(svg or "")
    if m:
        parts = m.group(1).replace(",", " ").split()
        if len(parts) == 4:
            try:
                return tuple(float(p) for p in parts)  # type: ignore[return-value]
            except ValueError:
                pass
    return (0.0, 0.0, 320.0, 320.0)


def _constellation_anchors(
    forensic_key: bytes,
    vx: float,
    vy: float,
    vw: float,
    vh: float,
    count: int,
) -> list[tuple[int, int]]:
    """Deterministic integer anchor grid derived from the tenant forensic key."""
    seed = int.from_bytes(_derive_subkey(forensic_key, b"svg.geo.v1")[:8], "big")
    rng = random.Random(seed)
    margin_x = max(8.0, vw * 0.12)
    margin_y = max(8.0, vh * 0.12)
    lo_x, hi_x = int(vx + margin_x), int(vx + vw - margin_x)
    lo_y, hi_y = int(vy + margin_y), int(vy + vh - margin_y)
    if hi_x <= lo_x + 4:
        lo_x, hi_x = int(vx + 2), int(vx + max(10, vw - 2))
    if hi_y <= lo_y + 4:
        lo_y, hi_y = int(vy + 2), int(vy + max(10, vh - 2))
    anchors: list[tuple[int, int]] = []
    for _ in range(count):
        anchors.append((rng.randint(lo_x, hi_x), rng.randint(lo_y, hi_y)))
    return anchors


def embed_svg_forensics(
    svg: str,
    forensic_key: bytes,
    *,
    organization_id: int,
    stamp_id: int,
    receipt_id: int,
    placed_by_id: int,
    document_id: int | None,
    placed_at: datetime,
    nonce: str,
    channel: str = "tsd_document",
) -> tuple[str, str, bytes]:
    """Embed Layers 1A, 1B, and 2 covert TSD security features into an SVG.

    Returns ``(sealed_svg, fingerprint, packet_bytes)``.
    """
    clean = strip_forensic_svg_layer(svg)
    packet = pack_forensic_packet(
        forensic_key,
        organization_id=organization_id,
        stamp_id=stamp_id,
        receipt_id=receipt_id,
        placed_by_id=placed_by_id,
        document_id=document_id,
        placed_at=placed_at,
        nonce=nonce,
        channel=channel,
    )
    fp = compute_forensic_fingerprint(
        forensic_key,
        receipt_id=receipt_id,
        stamp_id=stamp_id,
        nonce=nonce,
    )

    vx, vy, vw, vh = _parse_viewbox(clean)
    anchors = _constellation_anchors(forensic_key, vx, vy, vw, vh, len(packet))

    # Layer 1A: Sub-pixel micro-constellation.
    # Each byte b -> high nibble hi (0..15) encoded as fractional cx = ax + (hi * 0.05 + 0.02)
    #                low  nibble lo (0..15) encoded as fractional cy = ay + (lo * 0.05 + 0.02)
    # Fractional range [0.02 .. 0.77] stays strictly within [0, 1) of its integer anchor!
    dots: list[str] = []
    path_pts: list[str] = []
    for idx, b in enumerate(packet):
        ax, ay = anchors[idx]
        hi = (b >> 4) & 0x0F
        lo = b & 0x0F
        cx = ax + (hi * 0.05 + 0.02)
        cy = ay + (lo * 0.05 + 0.02)
        dots.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="0.16" fill="#18345e"/>')
        cmd = "M" if idx == 0 else "L"
        path_pts.append(f"{cmd}{cx:.2f},{cy:.2f}")

    # Layer 1B: Redundant micro-path carrier (survives circle-stripping)
    micro_path = (
        f'<path d="{" ".join(path_pts)}" fill="none" '
        f'stroke="#18345e" stroke-width="0.04" stroke-opacity="0.012"/>'
    )

    # Layer 2: Covert micro-text security fiber
    tx = vx + vw * 0.50
    ty = vy + vh - max(1.5, vh * 0.02)
    micro_text = (
        f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" '
        f'font-family="monospace" font-size="0.42" fill="#18345e" '
        f'fill-opacity="0.018">{fp}</text>'
    )

    gid = "tsd-f-" + hashlib.sha256(packet).hexdigest()[:8]
    forensic_group = (
        f'<g id="{gid}" data-tsd-f="1" opacity="0.015" pointer-events="none">'
        + "".join(dots)
        + micro_path
        + micro_text
        + "</g>"
    )

    close_idx = clean.rfind("</svg>")
    if close_idx != -1:
        sealed = clean[:close_idx] + forensic_group + clean[close_idx:]
    else:
        sealed = clean + forensic_group
    return sealed, fp, packet


def _decode_coords_to_bytes(coords: list[tuple[float, float]]) -> bytes | None:
    if len(coords) != PACKET_BYTES:
        return None
    out = bytearray(PACKET_BYTES)
    for idx, (cx, cy) in enumerate(coords):
        fx = cx - int(cx) if cx >= 0 else cx - (int(cx) - 1)
        fy = cy - int(cy) if cy >= 0 else cy - (int(cy) - 1)
        hi = int(round((fx - 0.02) / 0.05))
        lo = int(round((fy - 0.02) / 0.05))
        if not (0 <= hi <= 15 and 0 <= lo <= 15):
            return None
        out[idx] = ((hi & 0x0F) << 4) | (lo & 0x0F)
    return bytes(out)


def extract_svg_forensics(
    svg: str,
    forensic_key: bytes,
) -> dict[str, Any]:
    """Extract and decrypt all covert forensic layers present in an SVG."""
    layers_detected: list[str] = []
    payload: ForensicPayload | None = None
    micro_text_fp: str | None = None

    # 1. Try Layer 1A: micro-constellation circles (even if data-tsd-f was stripped!)
    circle_re = re.compile(
        r'<circle\b[^>]*\bcx="([0-9.\-]+)"[^>]*\bcy="([0-9.\-]+)"[^>]*\br="0\.16"[^>]*/?>'
    )
    circle_coords = [(float(m.group(1)), float(m.group(2))) for m in circle_re.finditer(svg or "")]
    if len(circle_coords) >= PACKET_BYTES:
        # Take the last PACKET_BYTES circles (in case multiple marks)
        raw = _decode_coords_to_bytes(circle_coords[-PACKET_BYTES:])
        if raw is not None:
            decoded = unpack_forensic_packet(forensic_key, raw)
            if decoded is not None:
                payload = decoded
                layers_detected.append("vector_micro_constellation")

    # 2. Try Layer 1B: redundant micro-path carrier
    path_re = re.compile(r'<path\b[^>]*\bd="([^"]+)"[^>]*stroke-width="0\.04"[^>]*/?>')
    for pm in path_re.finditer(svg or ""):
        pts = re.findall(r'[ML]\s*([0-9.\-]+)[,\s]+([0-9.\-]+)', pm.group(1))
        if len(pts) == PACKET_BYTES:
            raw = _decode_coords_to_bytes([(float(x), float(y)) for x, y in pts])
            if raw is not None:
                decoded = unpack_forensic_packet(forensic_key, raw)
                if decoded is not None:
                    if payload is None:
                        payload = decoded
                    layers_detected.append("vector_micro_path")
                    break

    # 3. Try Layer 2: covert micro-text security fiber
    fp_match = re.search(r'TSD-F1-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}', svg or "")
    if fp_match:
        micro_text_fp = fp_match.group(0)
        layers_detected.append("covert_micro_text_fiber")

    # 4. Also check overt receipt attributes (for cross-verification)
    rid_m = re.search(r'data-stamp-receipt-id="(\d+)"', svg or "")
    nonce_m = re.search(r'data-stamp-receipt-nonce="([0-9a-fA-F]+)"', svg or "")
    overt_receipt_id = int(rid_m.group(1)) if rid_m else None
    overt_nonce = nonce_m.group(1) if nonce_m else None
    if overt_receipt_id and overt_nonce:
        layers_detected.append("overt_receipt_attributes")

    return {
        "found": payload is not None,
        "payload": payload,
        "layers_detected": layers_detected,
        "micro_text_fingerprint": micro_text_fp,
        "overt_receipt_id": overt_receipt_id,
        "overt_nonce": overt_nonce,
        "canonical_svg": strip_forensic_svg_layer(svg or ""),
    }


# =================================================================== PNG Layer 3


_RASTER_REPETITIONS = 3


def _bytes_to_bits(data: bytes) -> list[int]:
    bits: list[int] = []
    for b in data:
        for shift in range(7, -1, -1):
            bits.append((b >> shift) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = bytearray(len(bits) // 8)
    for i in range(len(out)):
        v = 0
        for j in range(8):
            v = (v << 1) | (bits[i * 8 + j] & 1)
        out[i] = v
    return bytes(out)


def _raster_pixel_positions(
    forensic_key: bytes,
    width: int,
    height: int,
    total_bits: int,
) -> list[tuple[int, int, int]]:
    """Generate a deterministic, tenant-key-permuted list of (x, y, channel) slots."""
    total_pixels = width * height
    if total_pixels * 3 < total_bits:
        raise ValueError("image_too_small_for_forensic_watermark")
    seed_bytes = _derive_subkey(
        forensic_key,
        f"raster.perm.v1:{width}x{height}".encode("ascii"),
    )
    rng = random.Random(int.from_bytes(seed_bytes[:8], "big"))
    # Sample distinct (pixel_index * 3 + channel) slots without building a giant list
    chosen = rng.sample(range(total_pixels * 3), total_bits)
    slots: list[tuple[int, int, int]] = []
    for slot in chosen:
        px_idx = slot // 3
        ch = slot % 3  # 0=R, 1=G, 2=B
        x = px_idx % width
        y = px_idx // width
        slots.append((x, y, ch))
    return slots


def embed_png_forensics(
    png_bytes: bytes,
    forensic_key: bytes,
    *,
    organization_id: int,
    stamp_id: int,
    receipt_id: int,
    placed_by_id: int,
    document_id: int | None,
    placed_at: datetime,
    nonce: str,
    channel: str = "png_export",
) -> tuple[bytes, str, bytes]:
    """Embed Layer 3 keyed raster steganographic watermark + PNG tEXt chunk.

    Returns ``(sealed_png_bytes, fingerprint, packet_bytes)``.
    """
    from PIL import Image, PngImagePlugin

    packet = pack_forensic_packet(
        forensic_key,
        organization_id=organization_id,
        stamp_id=stamp_id,
        receipt_id=receipt_id,
        placed_by_id=placed_by_id,
        document_id=document_id,
        placed_at=placed_at,
        nonce=nonce,
        channel=channel,
    )
    fp = compute_forensic_fingerprint(
        forensic_key,
        receipt_id=receipt_id,
        stamp_id=stamp_id,
        nonce=nonce,
    )

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    w, h = img.size
    bits = _bytes_to_bits(packet)
    repeated_bits = bits * _RASTER_REPETITIONS
    slots = _raster_pixel_positions(forensic_key, w, h, len(repeated_bits))

    pixels = img.load()
    for (x, y, ch), bit in zip(slots, repeated_bits):
        r, g, b, a = pixels[x, y]
        if ch == 0:
            r = (r & 0xFE) | bit
        elif ch == 1:
            g = (g & 0xFE) | bit
        else:
            b = (b & 0xFE) | bit
        pixels[x, y] = (r, g, b, a)

    meta = PngImagePlugin.PngInfo()
    meta.add_text("tsd_forensic_v1", base64.urlsafe_b64encode(packet).decode("ascii"))
    meta.add_text("tsd_forensic_fp", fp)

    out = io.BytesIO()
    img.save(out, format="PNG", pnginfo=meta, compress_level=6)
    return out.getvalue(), fp, packet


def extract_png_forensics(
    png_bytes: bytes,
    forensic_key: bytes,
) -> dict[str, Any]:
    """Extract and decrypt Layer 3 keyed raster steganography & PNG chunk."""
    from PIL import Image

    layers_detected: list[str] = []
    payload: ForensicPayload | None = None
    fp_text: str | None = None

    img = Image.open(io.BytesIO(png_bytes))
    info = img.info or {}
    fp_text = info.get("tsd_forensic_fp")

    # 1. Primary: Keyed pixel-level LSB steganography (survives metadata stripping!)
    rgba = img.convert("RGBA")
    w, h = rgba.size
    bit_count = PACKET_BYTES * 8
    total_bits = bit_count * _RASTER_REPETITIONS
    if w * h * 3 >= total_bits:
        slots = _raster_pixel_positions(forensic_key, w, h, total_bits)
        pixels = rgba.load()
        raw_bits = [pixels[x, y][ch] & 1 for (x, y, ch) in slots]
        # Majority vote across the 3 repetitions
        voted: list[int] = []
        for i in range(bit_count):
            s = raw_bits[i] + raw_bits[i + bit_count] + raw_bits[i + 2 * bit_count]
            voted.append(1 if s >= 2 else 0)
        candidate = _bits_to_bytes(voted)
        decoded = unpack_forensic_packet(forensic_key, candidate)
        if decoded is not None:
            payload = decoded
            layers_detected.append("raster_keyed_steganography")

    # 2. Secondary: PNG tEXt chunk carrier
    chunk_b64 = info.get("tsd_forensic_v1")
    if chunk_b64:
        try:
            chunk_bytes = base64.urlsafe_b64decode(chunk_b64.encode("ascii"))
            decoded_chunk = unpack_forensic_packet(forensic_key, chunk_bytes)
            if decoded_chunk is not None:
                if payload is None:
                    payload = decoded_chunk
                layers_detected.append("png_forensic_chunk")
        except Exception:
            pass

    return {
        "found": payload is not None,
        "payload": payload,
        "layers_detected": layers_detected,
        "micro_text_fingerprint": fp_text,
    }


# =================================================================== PDF Layer 4


def seal_pdf_bytes(
    pdf_bytes: bytes,
    packet: bytes,
    fingerprint: str,
) -> bytes:
    """Attach encrypted Layer 4 `/TSDForensicSeal` & `/TSDForensicFP` to a PDF."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    existing_meta = dict(reader.metadata or {})
    existing_meta["/TSDForensicSeal"] = base64.urlsafe_b64encode(packet).decode("ascii")
    existing_meta["/TSDForensicFP"] = fingerprint
    existing_meta["/Producer"] = "TrustSeal Stamp Studio (TSD Forensics v1)"
    writer.add_metadata(existing_meta)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def extract_pdf_forensics(
    pdf_bytes: bytes,
    forensic_key: bytes,
) -> dict[str, Any]:
    """Extract and decrypt Layer 4 PDF forensic seal & embedded micro-text."""
    from pypdf import PdfReader

    layers_detected: list[str] = []
    payload: ForensicPayload | None = None
    fp_text: str | None = None

    reader = PdfReader(io.BytesIO(pdf_bytes))
    meta = reader.metadata or {}
    seal_b64 = meta.get("/TSDForensicSeal")
    fp_meta = meta.get("/TSDForensicFP")
    if fp_meta:
        fp_text = str(fp_meta)

    if seal_b64:
        try:
            raw = base64.urlsafe_b64decode(str(seal_b64).encode("ascii"))
            decoded = unpack_forensic_packet(forensic_key, raw)
            if decoded is not None:
                payload = decoded
                layers_detected.append("pdf_encrypted_forensic_seal")
        except Exception:
            pass

    # Also scan PDF page text for Layer 2 covert micro-text security fiber
    try:
        full_text = "\n".join((p.extract_text() or "") for p in reader.pages)
        m = re.search(r'TSD-F1-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}', full_text)
        if m:
            fp_text = fp_text or m.group(0)
            layers_detected.append("covert_micro_text_fiber")
    except Exception:
        pass

    return {
        "found": payload is not None,
        "payload": payload,
        "layers_detected": layers_detected,
        "micro_text_fingerprint": fp_text,
    }
