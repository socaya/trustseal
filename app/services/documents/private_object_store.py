"""Pluggable backend for private document storage (Phase O).

The historic ``private_storage`` module wrote to a local directory
specified by ``PRIVATE_DOCUMENT_ROOT``. Phase O introduces a small
adapter interface so the same callers work against either the local
filesystem or an S3-compatible object store (AWS S3, MinIO, Ceph).

Layering:

1. The adapter interface :class:`PrivateObjectStore` only accepts
   **already-validated, already-scanned** PDF bytes. Its contract is
   durable write + read + delete + local-file materialisation.
2. The high-level dispatcher
   :func:`store_scanned_pdf_via_active_store` handles PDF-structure
   validation, antivirus scanning, and the hand-off to the active
   adapter. Existing callers may continue to use the legacy
   ``private_storage.store_scanned_pdf`` function; the filesystem
   backend is wire-compatible with it.

Adapter interface:

* ``put(data, config) -> (key, size, sha256)`` — writes the bytes
  under a freshly-minted opaque key (``<sha256 of a random nonce>.pdf``)
  and returns the metadata needed to persist a ``DocumentBlob`` row.
* ``read(key, config) -> bytes``.
* ``open_local(key, config) -> Path`` — returns a filesystem path the
  caller can stream through pyHanko / ``send_file`` / a PDF viewer.
  On the S3 backend the object is materialised into a mode-0400 temp
  file; the caller calls :func:`cleanup_local` when done.
* ``digest(key, config) -> hex`` — stream-and-hash without a local copy.
* ``delete(key, config)`` — best-effort erase.
* ``probe(config) -> dict`` — readiness-probe payload.

The S3 backend honours:

* ``PRIVATE_STORAGE_S3_BUCKET`` — required.
* ``PRIVATE_STORAGE_S3_REGION`` — defaults to the AWS SDK's region.
* ``PRIVATE_STORAGE_S3_ENDPOINT_URL`` — optional override used with
  MinIO or a local mock.
* ``PRIVATE_STORAGE_S3_SSE`` — optional ``"AES256"`` or
  ``"aws:kms"`` server-side encryption directive.

Object keys follow the ``^[0-9a-f]{64}\\.pdf$`` convention so tenant
bundle exports can enumerate keys without leaking internal structure.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import stat
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping, Optional


MAX_FILE_BYTES = 16 * 1024 * 1024
CHUNK = 64 * 1024
KEY_RE = re.compile(r"^[0-9a-f]{64}\.pdf$")


class StorageError(RuntimeError):
    """Raised for policy, I/O, or configuration failures."""


@dataclass(frozen=True)
class StoreResult:
    key: str
    size: int
    sha256: str


class PrivateObjectStore(ABC):
    name: str = "abstract"

    @abstractmethod
    def put(self, data: bytes, *, config: Mapping) -> StoreResult: ...

    @abstractmethod
    def read(self, key: str, *, config: Mapping) -> bytes: ...

    @abstractmethod
    def open_local(self, key: str, *, config: Mapping) -> Path: ...

    @abstractmethod
    def digest(self, key: str, *, config: Mapping) -> str: ...

    @abstractmethod
    def delete(self, key: str, *, config: Mapping) -> None: ...

    @abstractmethod
    def probe(self, *, config: Mapping) -> dict: ...

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not KEY_RE.fullmatch(key):
            raise StorageError("invalid_object_key")


# ----------------------------------------------------- Filesystem


class FilesystemObjectStore(PrivateObjectStore):
    """Stores objects under ``PRIVATE_DOCUMENT_ROOT`` with mode-0400 files."""

    name = "filesystem"

    def _root(self, config: Mapping) -> Path:
        from app.services.documents.private_storage import _storage_root

        return _storage_root(config)

    def put(self, data: bytes, *, config: Mapping) -> StoreResult:
        root = self._root(config)
        key = secrets.token_hex(32) + ".pdf"
        target = root / key
        fd = os.open(
            str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return StoreResult(
            key=key,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def read(self, key: str, *, config: Mapping) -> bytes:
        self._validate_key(key)
        return self.open_local(key, config=config).read_bytes()

    def open_local(self, key: str, *, config: Mapping) -> Path:
        self._validate_key(key)
        path = self._root(config) / key
        if path.is_symlink() or not path.is_file():
            raise StorageError("object_not_found")
        return path

    def digest(self, key: str, *, config: Mapping) -> str:
        path = self.open_local(key, config=config)
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()

    def delete(self, key: str, *, config: Mapping) -> None:
        self._validate_key(key)
        try:
            (self._root(config) / key).unlink()
        except FileNotFoundError:
            pass

    def probe(self, *, config: Mapping) -> dict:
        root = config.get("PRIVATE_DOCUMENT_ROOT")
        if not root:
            return {"backend": "filesystem", "status": "not_configured"}
        path = Path(root)
        if not path.is_absolute():
            return {
                "backend": "filesystem",
                "status": "failed",
                "detail": "path_not_absolute",
            }
        if not path.is_dir():
            return {
                "backend": "filesystem",
                "status": "failed",
                "detail": "path_missing",
            }
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            return {
                "backend": "filesystem",
                "status": "failed",
                "detail": f"permissions_too_open:0o{mode:03o}",
            }
        if not os.access(path, os.R_OK | os.W_OK | os.X_OK):
            return {
                "backend": "filesystem",
                "status": "failed",
                "detail": "permissions_not_rwx",
            }
        return {"backend": "filesystem", "status": "ok"}


# ----------------------------------------------------- S3


class S3ObjectStore(PrivateObjectStore):
    """boto3-backed object store compatible with AWS S3, MinIO, and Ceph."""

    name = "s3"

    def _client(self, config: Mapping):
        import boto3

        kwargs = {}
        if config.get("PRIVATE_STORAGE_S3_REGION"):
            kwargs["region_name"] = config["PRIVATE_STORAGE_S3_REGION"]
        if config.get("PRIVATE_STORAGE_S3_ENDPOINT_URL"):
            kwargs["endpoint_url"] = config["PRIVATE_STORAGE_S3_ENDPOINT_URL"]
        return boto3.client("s3", **kwargs)

    def _bucket(self, config: Mapping) -> str:
        bucket = config.get("PRIVATE_STORAGE_S3_BUCKET")
        if not bucket:
            raise StorageError("s3_bucket_not_configured")
        return bucket

    def put(self, data: bytes, *, config: Mapping) -> StoreResult:
        if not isinstance(data, (bytes, bytearray)):
            raise StorageError("payload_type_invalid")
        if len(data) == 0:
            raise StorageError("payload_empty")
        if len(data) > MAX_FILE_BYTES:
            raise StorageError("payload_too_large")
        bucket = self._bucket(config)
        client = self._client(config)
        key = secrets.token_hex(32) + ".pdf"
        put_args = {
            "Bucket": bucket,
            "Key": key,
            "Body": bytes(data),
            "ContentType": "application/pdf",
        }
        sse = config.get("PRIVATE_STORAGE_S3_SSE")
        if sse:
            put_args["ServerSideEncryption"] = sse
        client.put_object(**put_args)
        return StoreResult(
            key=key,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def read(self, key: str, *, config: Mapping) -> bytes:
        self._validate_key(key)
        bucket = self._bucket(config)
        client = self._client(config)
        try:
            obj = client.get_object(Bucket=bucket, Key=key)
        except Exception as exc:  # pragma: no cover - defensive
            raise StorageError("s3_read_failed") from exc
        return obj["Body"].read()

    def open_local(self, key: str, *, config: Mapping) -> Path:
        data = self.read(key, config=config)
        fd, path_str = tempfile.mkstemp(
            prefix="trustseal-s3-", suffix=".pdf"
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
        except BaseException:
            Path(path_str).unlink(missing_ok=True)
            raise
        os.chmod(path_str, 0o400)
        return Path(path_str)

    def digest(self, key: str, *, config: Mapping) -> str:
        return hashlib.sha256(self.read(key, config=config)).hexdigest()

    def delete(self, key: str, *, config: Mapping) -> None:
        self._validate_key(key)
        bucket = self._bucket(config)
        client = self._client(config)
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except Exception:
            pass

    def probe(self, *, config: Mapping) -> dict:
        try:
            bucket = self._bucket(config)
            client = self._client(config)
            client.head_bucket(Bucket=bucket)
            return {"backend": "s3", "status": "ok", "bucket": bucket}
        except Exception as exc:
            return {
                "backend": "s3",
                "status": "failed",
                "detail": str(exc)[:160],
            }


# ----------------------------------------------------- registry


_STORES: dict[str, PrivateObjectStore] = {
    "filesystem": FilesystemObjectStore(),
    "s3": S3ObjectStore(),
}


def register_store(store: PrivateObjectStore) -> None:
    _STORES[store.name] = store


def active_store(config: Optional[Mapping] = None) -> PrivateObjectStore:
    from flask import current_app

    cfg = config if config is not None else current_app.config
    name = (cfg.get("PRIVATE_STORAGE_BACKEND") or "filesystem").lower()
    store = _STORES.get(name)
    if store is None:
        raise StorageError(f"unknown_storage_backend:{name}")
    return store


def cleanup_local(path: Path) -> None:
    """Delete a temp file produced by ``S3ObjectStore.open_local``.

    No-op when the path was not created by the S3 backend (filesystem
    backend returns paths inside ``PRIVATE_DOCUMENT_ROOT`` which must
    survive).
    """
    if not isinstance(path, Path):
        return
    if not path.name.startswith("trustseal-s3-"):
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


# ----------------------------------------------------- dispatcher


def store_scanned_pdf_via_active_store(
    stream: BinaryIO, filename: str, config: Mapping
) -> tuple[str, str, int, str, str]:
    """Validate, scan, and write a PDF via the active adapter.

    Returns ``(key, basename, size, sha256, scanner)`` to match the
    legacy ``store_scanned_pdf`` contract so existing callers can
    swap to the dispatcher without changing the unpack.

    On the filesystem backend we delegate to the legacy function so
    the atomic-rename + mode-0400 behaviour is preserved verbatim.
    On the S3 backend we buffer, scan via tempfile, upload.
    """
    from app.services.documents import private_storage

    store = active_store(config)
    if store.name == "filesystem":
        return private_storage.store_scanned_pdf(stream, filename, config)
    if store.name != "s3":
        raise StorageError(f"unsupported_backend_for_dispatch:{store.name}")
    basename = (filename or "upload.pdf").replace("\\", "/").split("/")[-1].strip()
    if (
        not basename
        or len(basename) > 180
        or not basename.lower().endswith(".pdf")
        or any(ord(ch) < 32 for ch in basename)
    ):
        raise StorageError("filename_invalid")
    body = stream.read(MAX_FILE_BYTES + 1)
    if len(body) > MAX_FILE_BYTES:
        raise StorageError("payload_too_large")
    if not body:
        raise StorageError("payload_empty")
    if not body.startswith(b"%PDF-") or b"%%EOF" not in body[-2048:]:
        raise StorageError("payload_not_pdf")
    # Scan the buffer by writing to a temp file (matches the existing
    # clamscan interface on the filesystem backend).
    fd, staged = tempfile.mkstemp(prefix="trustseal-scan-", suffix=".pdf")
    os.chmod(staged, 0o600)
    scanner = "noop"
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        scanner = private_storage._scan_pdf(Path(staged), config)
    finally:
        Path(staged).unlink(missing_ok=True)
    result = store.put(body, config=config)
    return result.key, basename, result.size, result.sha256, scanner
