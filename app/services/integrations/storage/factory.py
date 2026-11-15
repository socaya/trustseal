"""Construct the configured :class:`ObjectStore` from Flask config."""
from __future__ import annotations

from typing import Any

from .base import ObjectStore, ObjectStoreError
from .local import LocalObjectStore
from .s3 import S3ObjectStore


def build_store(config: Any) -> ObjectStore:
    """Return the :class:`ObjectStore` selected by ``OBJECT_STORAGE_BACKEND``.

    The function is pure — it does not consult the app context — so it
    can be called from CLI commands, workers, and tests without a
    request scope.
    """
    backend = (config.get("OBJECT_STORAGE_BACKEND") or "local").strip().lower()
    if backend == "local":
        if str(config.get("FLASK_ENV", "")).lower() == "production":
            raise ObjectStoreError(
                "OBJECT_STORAGE_BACKEND=local is not permitted in production"
            )
        root = config.get("PRIVATE_DOCUMENT_ROOT")
        if not root:
            raise ObjectStoreError(
                "PRIVATE_DOCUMENT_ROOT is required for the local backend"
            )
        return LocalObjectStore(root)
    if backend in {"s3", "minio"}:
        bucket = config.get("OBJECT_STORAGE_S3_BUCKET")
        kms_key = config.get("OBJECT_STORAGE_S3_SSE_KMS_KEY_ID")
        region = config.get("OBJECT_STORAGE_S3_REGION")
        endpoint = config.get("OBJECT_STORAGE_S3_ENDPOINT_URL")
        if not bucket or not kms_key:
            raise ObjectStoreError(
                "S3 backend requires OBJECT_STORAGE_S3_BUCKET and "
                "OBJECT_STORAGE_S3_SSE_KMS_KEY_ID"
            )
        return S3ObjectStore(
            bucket=bucket,
            sse_kms_key_id=kms_key,
            region=region,
            endpoint_url=endpoint,
        )
    raise ObjectStoreError(
        f"Unknown OBJECT_STORAGE_BACKEND {backend!r}; expected local, s3, minio"
    )
