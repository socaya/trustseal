"""Guard tests for the platform certificate seal.

Requires the Flask runtime dependencies and pyHanko for the full suite.
Signer integration must also be exercised with a disposable test CA/PKCS12.
"""
import pytest

from app.services.platform_pdf_seal import (
    PdfFinalizationError, _required_file, seal_pdf, MAX_PDF_BYTES,
)


def test_missing_platform_key_is_rejected(tmp_path):
    with pytest.raises(PdfFinalizationError):
        _required_file(None, "Platform key", private=True)


def test_relative_platform_key_is_rejected():
    with pytest.raises(PdfFinalizationError):
        _required_file("keys/company.p12", "Platform key", private=True)


def test_symlink_private_key_is_rejected(tmp_path):
    original = tmp_path / "actual.p12"
    original.write_bytes(b"not-a-key")
    alias = tmp_path / "alias.p12"
    alias.symlink_to(original)
    with pytest.raises(PdfFinalizationError):
        _required_file(str(alias), "Platform key", private=True)


def test_world_readable_private_key_is_rejected(tmp_path):
    key = tmp_path / "key.p12"
    key.write_bytes(b"not-a-key")
    key.chmod(0o644)
    with pytest.raises(PdfFinalizationError):
        _required_file(str(key), "Platform key", private=True)


def test_non_pdf_rejected_without_invoking_signing_engine():
    with pytest.raises(PdfFinalizationError, match="Invalid source PDF"):
        seal_pdf(b"not-a-pdf", {})


def test_large_source_rejected_without_invoking_signing_engine():
    with pytest.raises(PdfFinalizationError, match="size"):
        seal_pdf(b"%PDF-1.7" + b"x" * MAX_PDF_BYTES, {})
