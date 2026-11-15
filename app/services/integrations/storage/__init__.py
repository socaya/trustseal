"""Pluggable object storage.

See ADR 0002. Pick an implementation at startup via the
``OBJECT_STORAGE_BACKEND`` configuration key:

* ``"local"`` — :class:`LocalObjectStore` (dev / CI only).
* ``"s3"`` or ``"minio"`` — :class:`S3ObjectStore` (production).

The :func:`build_store` factory validates the combination and raises
``ObjectStoreError`` when a production deployment selects ``local``.
"""
from .base import ObjectMeta, ObjectPut, ObjectStore, ObjectStoreError, ObjectVersion
from .factory import build_store
from .local import LocalObjectStore
from .s3 import S3ObjectStore

__all__ = [
    "ObjectMeta",
    "ObjectPut",
    "ObjectStore",
    "ObjectStoreError",
    "ObjectVersion",
    "LocalObjectStore",
    "S3ObjectStore",
    "build_store",
]
