"""DOCX → PDF conversion (I4).

The real binary is LibreOffice. In the test environment we point
``DOCX_LIBREOFFICE_BINARY`` at a disposable shell script that
mimics the subset of the ``soffice`` CLI we use: when invoked with
``--convert-to pdf --outdir <dir> <source>`` it emits a stub PDF
next to the source. This is the same pattern tests use for ClamAV.
"""
from __future__ import annotations

import io
import os
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest


def _docx_bytes() -> bytes:
    """Minimal valid DOCX (a ZIP with the magic signature)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0'?><Types/>",
        )
        zf.writestr("word/document.xml", "<document/>")
    return buf.getvalue()


@pytest.fixture
def libreoffice_stub(tmp_path):
    """A fake ``soffice`` shell script that emits a stub PDF."""
    script = tmp_path / "soffice-stub.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "outdir=\n"
        "source=\n"
        "while [[ $# -gt 0 ]]; do\n"
        "  case \"$1\" in\n"
        "    --outdir)\n"
        "      outdir=\"$2\"; shift 2;;\n"
        "    --convert-to|--headless|--nologo|--nofirststartwizard)\n"
        "      shift;;\n"
        "    pdf)\n"
        "      shift;;\n"
        "    *)\n"
        "      source=\"$1\"; shift;;\n"
        "  esac\n"
        "done\n"
        "base=$(basename \"$source\" .docx)\n"
        "cat > \"$outdir/${base}.pdf\" <<'EOF'\n"
        "%PDF-1.4\n"
        "% docx-stub\n"
        "%%EOF\n"
        "EOF\n"
    )
    mode = script.stat().st_mode
    script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@pytest.fixture
def enabled(pg_app, libreoffice_stub):
    pg_app.config["DOCX_LIBREOFFICE_BINARY"] = str(libreoffice_stub)
    pg_app.config["DOCX_CONVERSION_TIMEOUT"] = 30
    pg_app.config["DOCX_CONVERSION_MAX_BYTES"] = 25 * 1024 * 1024
    yield pg_app
    pg_app.config["DOCX_LIBREOFFICE_BINARY"] = None


class TestEnabled:
    def test_disabled_without_binary(self, pg_app):
        from app.services.documents.docx_conversion import enabled

        pg_app.config["DOCX_LIBREOFFICE_BINARY"] = None
        assert enabled(pg_app.config) is False

    def test_disabled_without_exec_bit(self, pg_app, tmp_path):
        from app.services.documents.docx_conversion import enabled

        script = tmp_path / "no-exec"
        script.write_text("#!/bin/sh\n")
        pg_app.config["DOCX_LIBREOFFICE_BINARY"] = str(script)
        assert enabled(pg_app.config) is False

    def test_enabled_with_valid_binary(self, pg_app, libreoffice_stub):
        from app.services.documents.docx_conversion import enabled

        pg_app.config["DOCX_LIBREOFFICE_BINARY"] = str(libreoffice_stub)
        assert enabled(pg_app.config) is True


class TestConvert:
    def test_valid_docx_returns_pdf(self, enabled):
        from app.services.documents.docx_conversion import convert_to_pdf

        out = convert_to_pdf(_docx_bytes(), config=enabled.config)
        assert out.startswith(b"%PDF-")
        assert b"%%EOF" in out

    def test_refuses_without_docx_magic(self, enabled):
        from app.services.documents.docx_conversion import (
            DocxConversionError,
            convert_to_pdf,
        )

        with pytest.raises(DocxConversionError):
            convert_to_pdf(b"not a docx", config=enabled.config)

    def test_refuses_oversized(self, enabled):
        from app.services.documents.docx_conversion import (
            DocxConversionError,
            convert_to_pdf,
        )

        enabled.config["DOCX_CONVERSION_MAX_BYTES"] = 100
        with pytest.raises(DocxConversionError):
            convert_to_pdf(_docx_bytes() + b"\x00" * 200, config=enabled.config)

    def test_refuses_when_disabled(self, pg_app):
        from app.services.documents.docx_conversion import (
            DocxConversionError,
            convert_to_pdf,
        )

        pg_app.config["DOCX_LIBREOFFICE_BINARY"] = None
        with pytest.raises(DocxConversionError):
            convert_to_pdf(_docx_bytes(), config=pg_app.config)
