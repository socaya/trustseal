"""Certificate-backed platform PDF seal, with explicit trust-root verification.

This signs with TrustSeal's configured platform certificate, not individual
participants' certificates. It does not confer personal signer status.

Requires pyHanko in an isolated worker, an approved PKCS#12 key, and a pinned
trust root. Signing is disabled if any prerequisite is unavailable.
"""
import hashlib
import io
import os
from pathlib import Path

MAX_PDF_BYTES = 20 * 1024 * 1024
FIELD_NAME = "TrustSealPlatformSeal"
PROFILE = "platform_pades_b_b"


class PdfFinalizationError(RuntimeError):
    pass


def _required_file(path, label, *, private=False):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise PdfFinalizationError("%s requires an absolute path" % label)
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file():
        raise PdfFinalizationError("%s is not a regular protected file" % label)
    if private and candidate.stat().st_mode & 0o077:
        raise PdfFinalizationError("%s must not be group/world accessible" % label)
    return candidate


def _trust_context(config):
    try:
        from pyhanko.keys import load_cert_from_pemder
        from pyhanko_certvalidator import ValidationContext
    except ImportError as exc:
        raise PdfFinalizationError("PDF signing dependencies unavailable") from exc
    root_path = _required_file(config.get("PDF_TRUST_ROOT_PEM"), "Trusted root")
    return ValidationContext(
        trust_roots=[load_cert_from_pemder(str(root_path))],
        allow_fetching=False,
    )


def _signing_credentials(config):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.serialization import pkcs12
        from pyhanko.sign import signers
    except ImportError as exc:
        raise PdfFinalizationError("PDF signing dependencies unavailable") from exc
    path = _required_file(config.get("PDF_PLATFORM_PKCS12"), "Platform key", private=True)
    secret = config.get("PDF_PLATFORM_PKCS12_PASSWORD")
    if not isinstance(secret, str) or not secret:
        raise PdfFinalizationError("Platform signing key password missing")
    password = secret.encode("utf-8")
    material = path.read_bytes()
    try:
        _key, cert, _chain = pkcs12.load_key_and_certificates(material, password)
        if cert is None or _key is None:
            raise ValueError("Missing certificate or private key")
        signer = signers.SimpleSigner.load_pkcs12(str(path), passphrase=password)
        if signer is None:
            raise ValueError("PKCS12 signer unavailable")
    except (ValueError, TypeError) as exc:
        raise PdfFinalizationError("Invalid platform signing credentials") from exc
    return signer, cert.fingerprint(hashes.SHA256()).hex()


def inspect_signed_pdf(pdf_bytes, config):
    """Validate embedded CMS, byte range, and certificate chain with pinned CA."""
    if not isinstance(pdf_bytes, bytes) or not 0 < len(pdf_bytes) <= MAX_PDF_BYTES:
        raise PdfFinalizationError("Signed PDF size is invalid")
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        signatures = reader.embedded_signatures
        if len(signatures) != 1 or signatures[0].field_name != FIELD_NAME:
            raise PdfFinalizationError("Expected one platform seal field")
        status = validate_pdf_signature(
            signatures[0], signer_validation_context=_trust_context(config)
        )
        return {
            "signature_valid": bool(status.valid),
            "intact": bool(status.intact),
            "trusted": bool(status.trusted),
            "overall_valid": bool(status.bottom_line),
            "field": FIELD_NAME,
            "profile": PROFILE,
        }
    except PdfFinalizationError:
        raise
    except Exception as exc:
        raise PdfFinalizationError("PDF signature validation failed") from exc


def seal_pdf(source_bytes, config):
    """Apply an invisible CMS signature in the designated platform field.

    An approved platform certificate and explicit trust root are mandatory.
    """
    if not isinstance(source_bytes, bytes) or not 0 < len(source_bytes) <= MAX_PDF_BYTES:
        raise PdfFinalizationError("Source PDF size is invalid")
    if not source_bytes.startswith(b"%PDF-"):
        raise PdfFinalizationError("Invalid source PDF")
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import fields, signers
    except ImportError as exc:
        raise PdfFinalizationError("PDF signing dependencies unavailable") from exc

    # Refuse already-signed PDFs for this single-seal profile, avoiding
    # accidental edits of a document with earlier signatures.
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        reader = PdfFileReader(io.BytesIO(source_bytes))
        if reader.embedded_signatures:
            raise PdfFinalizationError("Source already contains a PDF signature")
    except PdfFinalizationError:
        raise
    except Exception as exc:
        raise PdfFinalizationError("Source PDF structural parsing failed") from exc

    signer, certificate_sha256 = _signing_credentials(config)
    meta = signers.PdfSignatureMetadata(
        field_name=FIELD_NAME,
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason="TrustSeal platform attestation of completed review workflow",
        embed_validation_info=False,
    )
    try:
        output = signers.sign_pdf(
            IncrementalPdfFileWriter(io.BytesIO(source_bytes)),
            signature_meta=meta,
            signer=signer,
        )
        signed = output.getvalue()
    except Exception as exc:
        raise PdfFinalizationError("PDF signing operation failed") from exc
    validation = inspect_signed_pdf(signed, config)
    if not validation["overall_valid"]:
        raise PdfFinalizationError("New PDF seal did not pass trusted validation")
    return signed, certificate_sha256, validation
