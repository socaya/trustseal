"""ObjectStore interface.

Narrow by design: every method is used by at least one existing caller
in ``app/services/documents/``. Adding a method here forces every
implementation to grow a corresponding method, so keep the surface
small.

Keys are opaque strings. Callers must not interpret them. Implementations
are free to encode a tenant prefix; the domain layer treats keys as
identifiers only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterator


class ObjectStoreError(Exception):
    """Transport-level failure (missing key, permission, config)."""


@dataclass(frozen=True)
class ObjectMeta:
    key: str
    size: int
    content_type: str
    etag: str
    last_modified_epoch: int


@dataclass(frozen=True)
class ObjectPut:
    key: str
    size: int
    etag: str
    version_id: str | None


@dataclass(frozen=True)
class ObjectVersion:
    key: str
    version_id: str
    size: int
    created_at_epoch: int
    is_latest: bool


class ObjectStore(ABC):
    """Read/write access to a logical object bucket.

    Implementations MUST:

    * Reject keys containing ``..`` or leading ``/`` (anti-traversal).
    * Treat ``put`` as creating a new immutable version when versioning
      is enabled by the backend; never destructively overwrite without
      a documented contract.
    * Never log object bytes or the raw ``body`` argument.
    """

    @abstractmethod
    def put(
        self,
        key: str,
        body: bytes | BinaryIO,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> ObjectPut:
        ...

    @abstractmethod
    def get(self, key: str) -> bytes:
        ...

    @abstractmethod
    def stream(self, key: str) -> Iterator[bytes]:
        ...

    @abstractmethod
    def head(self, key: str) -> ObjectMeta:
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...

    @abstractmethod
    def list_versions(self, key: str) -> list[ObjectVersion]:
        ...

    @abstractmethod
    def presign_get(self, key: str, ttl_seconds: int) -> str:
        """Return a short-lived authorized URL for ``key``.

        ``ttl_seconds`` must be bounded by the implementation; raising
        ``ValueError`` on out-of-range input is acceptable.
        """

    # ----- helpers all implementations share ---------------------------

    @staticmethod
    def validate_key(key: Any) -> str:
        if not isinstance(key, str) or not key:
            raise ObjectStoreError("Object key must be a non-empty string")
        if key.startswith("/") or ".." in key.split("/"):
            raise ObjectStoreError("Object key is not permitted")
        if any(ord(ch) < 32 for ch in key):
            raise ObjectStoreError("Object key contains control characters")
        if len(key) > 1024:
            raise ObjectStoreError("Object key is too long")
        return key
