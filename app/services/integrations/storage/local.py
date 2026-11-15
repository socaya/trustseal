"""Filesystem-backed :class:`ObjectStore` for development and CI.

This implementation preserves the layout the prototype already uses —
the configured ``PRIVATE_DOCUMENT_ROOT`` directory with mode 0700 and
exclusive creation — so existing code that touches the filesystem keeps
working while the interface is adopted blueprint-by-blueprint.

Not for production: lacks server-side encryption, replication, and
object lock. Deployment selects ``S3ObjectStore`` instead.
"""
from __future__ import annotations

import hashlib
import os
import stat
import time
from pathlib import Path
from typing import BinaryIO, Iterator

from .base import ObjectMeta, ObjectPut, ObjectStore, ObjectStoreError, ObjectVersion

CHUNK = 64 * 1024


class LocalObjectStore(ObjectStore):
    def __init__(self, root: str | Path) -> None:
        candidate = Path(root)
        if not candidate.is_absolute():
            raise ObjectStoreError("LocalObjectStore root must be an absolute path")
        walked = Path(candidate.anchor)
        for component in candidate.parts[1:]:
            walked = walked / component
            if walked.is_symlink():
                raise ObjectStoreError("Symlinked storage paths are forbidden")
        resolved = candidate.resolve()
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(resolved.stat().st_mode) & 0o077:
            raise ObjectStoreError("LocalObjectStore root must have mode 0700")
        self._root = resolved

    # ----- helpers --------------------------------------------------

    def _resolve(self, key: str) -> Path:
        self.validate_key(key)
        candidate = (self._root / key).resolve()
        # Ensure the resolved path stays under the root.
        if self._root not in candidate.parents and candidate != self._root:
            raise ObjectStoreError("Resolved object path escapes the storage root")
        return candidate

    # ----- interface ------------------------------------------------

    def put(
        self,
        key: str,
        body: bytes | BinaryIO,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> ObjectPut:
        target = self._resolve(key)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if stat.S_IMODE(target.parent.stat().st_mode) & 0o077:
            raise ObjectStoreError("Storage sub-directory must be mode 0700")
        size = 0
        hasher = hashlib.sha256()
        # Exclusive creation so a put never silently overwrites an
        # immutable object. Callers that intend to replace must delete
        # first and accept the policy consequences.
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        try:
            with os.fdopen(fd, "wb") as fh:
                if isinstance(body, (bytes, bytearray)):
                    fh.write(body)
                    hasher.update(body)
                    size = len(body)
                else:
                    while True:
                        chunk = body.read(CHUNK)
                        if not chunk:
                            break
                        fh.write(chunk)
                        hasher.update(chunk)
                        size += len(chunk)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return ObjectPut(key=key, size=size, etag=hasher.hexdigest(), version_id=None)

    def get(self, key: str) -> bytes:
        path = self._resolve(key)
        if path.is_symlink() or not path.is_file():
            raise ObjectStoreError("Object unavailable")
        return path.read_bytes()

    def stream(self, key: str) -> Iterator[bytes]:
        path = self._resolve(key)
        if path.is_symlink() or not path.is_file():
            raise ObjectStoreError("Object unavailable")
        with path.open("rb") as fh:
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    return
                yield chunk

    def head(self, key: str) -> ObjectMeta:
        path = self._resolve(key)
        if not path.is_file():
            raise ObjectStoreError("Object unavailable")
        st = path.stat()
        # ETag is the sha256 of the bytes so the local backend has a
        # stable identifier without needing an extra side table.
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(CHUNK), b""):
                hasher.update(chunk)
        return ObjectMeta(
            key=key,
            size=st.st_size,
            content_type="application/octet-stream",
            etag=hasher.hexdigest(),
            last_modified_epoch=int(st.st_mtime),
        )

    def exists(self, key: str) -> bool:
        try:
            path = self._resolve(key)
        except ObjectStoreError:
            return False
        return path.is_file() and not path.is_symlink()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ObjectStoreError(f"Delete failed: {exc.strerror}") from exc

    def list_versions(self, key: str) -> list[ObjectVersion]:
        path = self._resolve(key)
        if not path.is_file():
            return []
        st = path.stat()
        return [
            ObjectVersion(
                key=key,
                version_id="local",
                size=st.st_size,
                created_at_epoch=int(st.st_mtime),
                is_latest=True,
            )
        ]

    def presign_get(self, key: str, ttl_seconds: int) -> str:
        """Local backend has no HTTP presign; return an opaque token-URI.

        Callers that need a user-facing URL must wire the local backend
        through a Flask streaming route. This returns a stable URI so
        that log messages and audit records can reference an object
        without leaking the filesystem path.
        """
        if not 1 <= ttl_seconds <= 3600:
            raise ValueError("ttl_seconds must be between 1 and 3600")
        self._resolve(key)  # Validates and resolves.
        expires = int(time.time()) + ttl_seconds
        return f"local-object:{key}?expires={expires}"
