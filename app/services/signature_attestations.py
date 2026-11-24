"""Platform-only attestations for signature impressions embedded in TSDs.

The visible signature graphic is not treated as proof.  TrustSeal issues a
tenant-keyed HMAC after the owner-authorized usage log has been consumed, and
the TSD write path verifies that attestation every time signed HTML is saved.
No verification key or human verification control is exposed to the browser.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser

from app.extensions import db
from app.models.esignature import SignatureProfile
from app.models.signature_governance import SignatureUsageLog
from app.models.user import User
from app.services.tsd_format import tenant_signing_key


class SignatureAttestationError(ValueError):
    """A document contains an untrusted or modified signature impression."""


@dataclass(frozen=True)
class SignatureMarker:
    signature_id: int
    usage_log_id: int
    digest: str
    attestation: str

    @property
    def legacy_key(self) -> tuple[int, int]:
        return self.signature_id, self.usage_log_id


class _MarkerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.markers: list[SignatureMarker] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        usage = values.get("data-tsd-sig-usage")
        sig_id = values.get("data-tsd-sig-id")
        if usage is None and sig_id is None:
            return
        try:
            usage_id = int(usage or "")
            signature_id = int(sig_id or "")
        except (TypeError, ValueError):
            raise SignatureAttestationError("invalid_signature_marker")
        if usage_id <= 0 or signature_id <= 0:
            raise SignatureAttestationError("invalid_signature_marker")
        self.markers.append(SignatureMarker(
            signature_id=signature_id,
            usage_log_id=usage_id,
            digest=(values.get("data-tsd-sig-digest") or "").lower(),
            attestation=(values.get("data-tsd-sig-attestation") or "").lower(),
        ))


def _payload(*, organization_id: int, document_id: int | None,
             signature_id: int, usage_log_id: int, digest: str) -> bytes:
    return (
        f"trustseal.signature.v1|{organization_id}|{document_id or 0}|"
        f"{signature_id}|{usage_log_id}|{digest}"
    ).encode("ascii")


def signature_digest(signature_data: str) -> str:
    return hashlib.sha256((signature_data or "").encode("utf-8")).hexdigest()


def _signature_graphic_present(html: str, signature_data: str) -> bool:
    """Confirm the attested source graphic is still present in saved markup."""
    source = signature_data or ""
    if not source:
        return False
    if source.startswith("data:image/") or source.startswith("/static/"):
        return source in html
    if "<svg" in source.lower():
        # Standalone signature blocks preserve a sanitized SVG. Stamp signing
        # embeds the same source as a base64 SVG image inside the stamp SVG.
        from app.services.tsd_format import sanitize_html

        sanitized = sanitize_html(source)
        encoded = "data:image/svg+xml;base64," + base64.b64encode(
            source.encode("utf-8")
        ).decode("ascii")
        return (bool(sanitized) and sanitized in html) or encoded in html
    return escape(source) in html


def issue_signature_attestation(*, organization_id: int,
                                document_id: int | None,
                                signature: SignatureProfile,
                                usage_log: SignatureUsageLog) -> dict[str, str | int]:
    """Issue the browser metadata for one already-authorized usage event."""
    if usage_log.organization_id != organization_id:
        raise SignatureAttestationError("signature_tenant_mismatch")
    if usage_log.signature_profile_id != signature.id:
        raise SignatureAttestationError("signature_usage_mismatch")
    if usage_log.status != "applied":
        raise SignatureAttestationError("signature_usage_not_applied")
    if usage_log.document_id is not None and usage_log.document_id != document_id:
        raise SignatureAttestationError("signature_document_mismatch")

    digest = signature_digest(signature.signature_data)
    key = tenant_signing_key(organization_id, label="tsd-signature-attestation")
    token = hmac.new(key, _payload(
        organization_id=organization_id,
        document_id=usage_log.document_id,
        signature_id=signature.id,
        usage_log_id=usage_log.id,
        digest=digest,
    ), hashlib.sha256).hexdigest()
    return {
        "signature_id": signature.id,
        "usage_log_id": usage_log.id,
        "signature_digest": digest,
        "signature_attestation": token,
    }


def extract_signature_markers(html: str) -> list[SignatureMarker]:
    parser = _MarkerParser()
    try:
        parser.feed(html or "")
        parser.close()
    except SignatureAttestationError:
        raise
    except Exception as exc:
        raise SignatureAttestationError("invalid_signature_markup") from exc
    return parser.markers


def validate_document_signatures(*, html: str, organization_id: int,
                                 document_id: int | None,
                                 allowed_legacy: set[tuple[int, int]] | None = None) -> int:
    """Validate every marked signature in sanitized document HTML.

    ``allowed_legacy`` lets an existing pre-attestation impression round-trip,
    but it cannot authorize a newly introduced legacy marker.
    """
    allowed_legacy = allowed_legacy or set()
    markers = extract_signature_markers(html)
    seen: set[tuple[int, int]] = set()
    for marker in markers:
        if marker.legacy_key in seen:
            raise SignatureAttestationError("duplicate_signature_usage")
        seen.add(marker.legacy_key)
        if not marker.digest or not marker.attestation:
            if marker.legacy_key in allowed_legacy:
                continue
            raise SignatureAttestationError("signature_attestation_required")
        if len(marker.digest) != 64 or len(marker.attestation) != 64:
            raise SignatureAttestationError("invalid_signature_attestation")

        usage = db.session.get(SignatureUsageLog, marker.usage_log_id)
        signature = db.session.get(SignatureProfile, marker.signature_id)
        if usage is None or signature is None:
            raise SignatureAttestationError("signature_record_not_found")
        owner = db.session.get(User, signature.user_id)
        if owner is None or owner.organization_id != organization_id:
            raise SignatureAttestationError("signature_tenant_mismatch")
        if (usage.organization_id != organization_id or
                usage.signature_profile_id != signature.id or
                usage.status != "applied"):
            raise SignatureAttestationError("signature_usage_invalid")
        if usage.document_id is not None and usage.document_id != document_id:
            raise SignatureAttestationError("signature_document_mismatch")

        expected_digest = signature_digest(signature.signature_data)
        if not hmac.compare_digest(marker.digest, expected_digest):
            raise SignatureAttestationError("signature_graphic_modified")
        if not _signature_graphic_present(html, signature.signature_data):
            raise SignatureAttestationError("signature_graphic_missing_or_modified")
        key = tenant_signing_key(organization_id, label="tsd-signature-attestation")
        expected = hmac.new(key, _payload(
            organization_id=organization_id,
            document_id=usage.document_id,
            signature_id=signature.id,
            usage_log_id=usage.id,
            digest=expected_digest,
        ), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(marker.attestation, expected):
            raise SignatureAttestationError("signature_attestation_invalid")
    return len(seen)
