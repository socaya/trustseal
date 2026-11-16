"""Sandboxed DOCX → PDF conversion via LibreOffice.

Design:

* The operator points ``DOCX_LIBREOFFICE_BINARY`` at an absolute,
  executable binary. If that binary is missing, the service refuses
  cleanly rather than falling back to an unsafe path.
* ``subprocess.run`` is invoked with ``timeout=DOCX_CONVERSION_TIMEOUT``
  and a fresh temporary working directory so the conversion is
  deterministic and cannot touch the Flask static tree.
* The input bytes are written to the temp dir with a random name,
  then we invoke ``libreoffice --headless --convert-to pdf`` and read
  the resulting PDF back. The temp directory is wiped at the end
  regardless of outcome.
* We cap the input DOCX at ``DOCX_CONVERSION_MAX_BYTES`` before
  writing it to disk.
* We validate the output as a real PDF (starts with ``%PDF-``, ends
  with ``%%EOF``) before returning it. A malformed output is treated
  as a conversion failure.

This service does not touch the database. The caller writes the
resulting PDF through :mod:`private_storage` so the scanner, digest,
and manifest invariants still apply.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

DOCX_MAGIC = b"PK\x03\x04"  # DOCX is a ZIP container
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_TIMEOUT = 60


class DocxConversionError(RuntimeError):
    """Raised when a DOCX cannot be converted to PDF."""


def enabled(config: Mapping) -> bool:
    binary = config.get("DOCX_LIBREOFFICE_BINARY")
    if not binary:
        return False
    path = Path(binary)
    return path.is_absolute() and path.is_file() and os.access(path, os.X_OK)


def _max_bytes(config: Mapping) -> int:
    return int(config.get("DOCX_CONVERSION_MAX_BYTES") or DEFAULT_MAX_BYTES)


def _timeout(config: Mapping) -> int:
    return int(config.get("DOCX_CONVERSION_TIMEOUT") or DEFAULT_TIMEOUT)


def convert_to_pdf(payload: bytes, *, config: Mapping) -> bytes:
    """Return PDF bytes for a DOCX ``payload``.

    Raises :class:`DocxConversionError` for every failure mode so the
    caller can map to a user-visible message.
    """
    if not enabled(config):
        raise DocxConversionError("docx_conversion_disabled")
    if not isinstance(payload, (bytes, bytearray)):
        raise DocxConversionError("payload_type_invalid")
    if not payload:
        raise DocxConversionError("payload_empty")
    if len(payload) > _max_bytes(config):
        raise DocxConversionError("payload_too_large")
    if not payload.startswith(DOCX_MAGIC):
        raise DocxConversionError("payload_not_docx_zip")
    binary = str(config["DOCX_LIBREOFFICE_BINARY"])
    work = tempfile.mkdtemp(prefix="trustseal-docx-")
    try:
        work_path = Path(work)
        source = work_path / "source.docx"
        source.write_bytes(payload)
        try:
            result = subprocess.run(
                [
                    binary,
                    "--headless",
                    "--nologo",
                    "--nofirststartwizard",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(work_path),
                    str(source),
                ],
                capture_output=True,
                timeout=_timeout(config),
                check=False,
                env={"HOME": work, "PATH": os.environ.get("PATH", "")},
            )
        except subprocess.TimeoutExpired as exc:
            raise DocxConversionError("conversion_timeout") from exc
        except FileNotFoundError as exc:
            raise DocxConversionError("binary_missing") from exc
        if result.returncode != 0:
            raise DocxConversionError(
                "conversion_failed:" + str(result.returncode)
            )
        pdf_path = work_path / "source.pdf"
        if not pdf_path.is_file():
            raise DocxConversionError("conversion_no_output")
        pdf = pdf_path.read_bytes()
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-2048:]:
            raise DocxConversionError("output_not_valid_pdf")
        return pdf
    finally:
        shutil.rmtree(work, ignore_errors=True)
