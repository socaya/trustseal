"""Fail-closed, private PDF ingest and verified retrieval.

Only PDF is accepted in this first slice. DOCX/images require separate
structural parsers and isolated conversion. The scanner must be installed
and configured; no scanner -> no upload. Nothing is placed under /static.
"""
import hashlib
import os
import re
import secrets
import subprocess
import tempfile
from pathlib import Path

MAX_FILE_BYTES = 16 * 1024 * 1024
CHUNK = 64 * 1024
KEY_RE = re.compile(r"^[0-9a-f]{64}\\.pdf$")
PDF_MIME = "application/pdf"


class IngestionError(Exception):
    pass


def validate_pdf(payload):
    """Lightweight file type gate; does not replace malware/structural scanning."""
    if not payload.startswith(b"%PDF-"):
        raise IngestionError("PDF header is missing")
    if b"%%EOF" not in payload[-2048:]:
        raise IngestionError("PDF end marker is missing")


def _storage_root(config):
    configured = config.get("PRIVATE_DOCUMENT_ROOT")
    if not configured:
        raise IngestionError("Private document storage is not configured")
    root = Path(configured).resolve()
    # Do not allow serving content from the checked-in static web directory.
    from flask import current_app
    static_root = Path(current_app.static_folder).resolve()
    if root == static_root or static_root in root.parents:
        raise IngestionError("Storage may not be inside Flask static files")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise IngestionError("Symbolic-link storage root is not allowed")
    return root


def _scan_pdf(path, config):
    binary = config.get("DOCUMENT_CLAMSCAN_BINARY")
    if not binary or not Path(binary).is_absolute() or not Path(binary).is_file():
        raise IngestionError("Malware scanner is unavailable")
    try:
        result = subprocess.run(
            [binary, "--no-summary", "--", str(path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=int(config.get("DOCUMENT_SCAN_TIMEOUT", 30)),
            check=False,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise IngestionError("Malware scan did not complete") from None
    if result.returncode != 0:
        raise IngestionError("Malware scanner rejected the file or failed")
    return "clamav-clamscan"


def store_scanned_pdf(stream, filename, config):
    """Stage bytes; scan before atomic promotion to an opaque private key.

    Returns (object_key, filename, size, sha256, scanner).
    Call cleanup_object if the corresponding database commit fails.
    """
    if not isinstance(filename, str):
        raise IngestionError("A PDF filename is required")
    basename = filename.replace("\\", "/").split("/")[-1].strip()
    if (not basename or len(basename) > 180
            or not basename.lower().endswith(".pdf")
            or any(ord(ch) < 32 for ch in basename)):
        raise IngestionError("A valid PDF filename is required")
    root = _storage_root(config)
    fd, staged = tempfile.mkstemp(prefix=".quarantine-", suffix=".tmp", dir=root)
    os.chmod(staged, 0o600)
    size = 0
    digest = hashlib.sha256()
    head = b""
    tail = b""
    promoted = None
    try:
        with os.fdopen(fd, "wb") as handle:
            while True:
                part = stream.read(CHUNK)
                if not part:
                    break
                size += len(part)
                if size > MAX_FILE_BYTES:
                    raise IngestionError("File exceeds the 16 MiB limit")
                digest.update(part)
                if len(head) < 8:
                    head = (head + part)[:8]
                tail = (tail + part)[-2048:]
                handle.write(part)
            handle.flush()
            os.fsync(handle.fileno())
        if size == 0:
            raise IngestionError("Empty document is not allowed")
        if not head.startswith(b"%PDF-") or b"%%EOF" not in tail:
            raise IngestionError("File does not match PDF structure markers")
        scanner = _scan_pdf(staged, config)
        # Unpredictable key, no supplied filenames or paths in object storage.
        key = secrets.token_hex(32) + ".pdf"
        final = root / key
        # Exclusive creation prevents replacing any existing immutable object.
        with open(staged, "rb") as source:
            out_fd = os.open(str(final), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
            try:
                with os.fdopen(out_fd, "wb") as target:
                    while True:
                        part = source.read(CHUNK)
                        if not part:
                            break
                        target.write(part)
                    target.flush()
                    os.fsync(target.fileno())
            except BaseException:
                final.unlink(missing_ok=True)
                raise
        promoted = key
        return key, basename, size, digest.hexdigest(), scanner
    finally:
        Path(staged).unlink(missing_ok=True)


def object_path(key, config):
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        raise IngestionError("Invalid object identifier")
    root = _storage_root(config)
    candidate = root / key
    if candidate.is_symlink() or not candidate.is_file():
        raise IngestionError("Document file is unavailable")
    return candidate


def check_object_digest(key, digest, config):
    path = object_path(key, config)
    actual = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(CHUNK), b""):
            actual.update(part)
    if actual.hexdigest() != digest:
        raise IngestionError("Stored object digest mismatch")
    return path


def cleanup_object(key, config):
    """Rollback aid only; never use for retained, committed manifests."""
    if isinstance(key, str) and KEY_RE.fullmatch(key):
        object_path(key, config).unlink(missing_ok=True)
