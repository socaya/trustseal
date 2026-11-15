"""Contract tests for :class:`ObjectStore` implementations.

The same contract is enforced against the local and S3 backends so we
catch regressions in either when porting a caller.

The S3 tests use moto's in-process mock so no AWS credentials, no
live network, and no container runtime are required.
"""
from __future__ import annotations

import io

import pytest

from app.services.integrations.storage import (
    LocalObjectStore,
    ObjectStoreError,
    S3ObjectStore,
    build_store,
)
from app.services.integrations.storage.base import ObjectStore


# --- fixtures --------------------------------------------------------


@pytest.fixture
def local_store(tmp_path):
    root = tmp_path / "objects"
    root.mkdir(mode=0o700)
    return LocalObjectStore(str(root))


@pytest.fixture
def s3_store():
    boto3 = pytest.importorskip("boto3")
    moto = pytest.importorskip("moto")

    with moto.mock_aws():
        import boto3 as boto

        s3 = boto.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="trustseal-test")
        s3.put_bucket_versioning(
            Bucket="trustseal-test",
            VersioningConfiguration={"Status": "Enabled"},
        )
        store = S3ObjectStore(
            bucket="trustseal-test",
            sse_kms_key_id="alias/aws/s3",
            region="us-east-1",
            client=s3,
        )
        yield store


# --- shared contract -------------------------------------------------


class _Contract:
    """Mix-in that sub-classes point at their store fixture."""

    @pytest.fixture
    def store(self, request) -> ObjectStore:
        raise NotImplementedError

    def test_put_then_get_round_trip(self, store):
        payload = b"hello trustseal"
        put = store.put("tenants/1/orig/abc", payload, content_type="text/plain")
        assert put.size == len(payload)
        assert store.exists("tenants/1/orig/abc")
        assert store.get("tenants/1/orig/abc") == payload

    def test_stream_yields_all_bytes(self, store):
        payload = b"x" * 10_000
        store.put("stream/key", payload, content_type="application/octet-stream")
        chunks = list(store.stream("stream/key"))
        assert b"".join(chunks) == payload

    def test_head_reports_size(self, store):
        payload = b"metadata probe"
        store.put("meta/key", payload, content_type="text/plain")
        meta = store.head("meta/key")
        assert meta.size == len(payload)
        assert meta.etag

    def test_missing_key_raises(self, store):
        with pytest.raises(ObjectStoreError):
            store.get("missing/object")

    def test_exists_false_for_missing(self, store):
        assert store.exists("not/there") is False

    def test_delete_is_idempotent(self, store):
        store.put("del/key", b"gone", content_type="text/plain")
        store.delete("del/key")
        assert store.exists("del/key") is False
        # Second delete must not raise.
        store.delete("del/key")

    def test_key_validation_rejects_traversal(self, store):
        with pytest.raises(ObjectStoreError):
            store.put("../etc/passwd", b"nope", content_type="text/plain")
        with pytest.raises(ObjectStoreError):
            store.put("/leading-slash", b"nope", content_type="text/plain")

    def test_key_validation_rejects_control_chars(self, store):
        with pytest.raises(ObjectStoreError):
            store.put("a\nb", b"nope", content_type="text/plain")

    def test_put_bytesio_body(self, store):
        payload = b"stream payload"
        buf = io.BytesIO(payload)
        put = store.put("b/key", buf, content_type="application/octet-stream")
        assert put.size == len(payload)
        assert store.get("b/key") == payload

    def test_presign_rejects_bad_ttl(self, store):
        store.put("presign/key", b"present", content_type="text/plain")
        with pytest.raises(ValueError):
            store.presign_get("presign/key", 0)
        with pytest.raises(ValueError):
            store.presign_get("presign/key", 4000)

    def test_presign_returns_url_or_token(self, store):
        store.put("presign/good", b"present", content_type="text/plain")
        assert store.presign_get("presign/good", 60)


class TestLocalContract(_Contract):
    @pytest.fixture
    def store(self, local_store):
        return local_store


class TestS3Contract(_Contract):
    @pytest.fixture
    def store(self, s3_store):
        return s3_store


# --- local-only invariants ------------------------------------------


class TestLocalSpecifics:
    def test_requires_absolute_root(self):
        with pytest.raises(ObjectStoreError):
            LocalObjectStore("relative/path")

    def test_resolved_path_stays_inside_root(self, local_store, tmp_path):
        # Even a carefully crafted key must not escape the configured root.
        with pytest.raises(ObjectStoreError):
            local_store.put("../outside", b"nope", content_type="text/plain")

    def test_mode_0700_enforced(self, tmp_path):
        root = tmp_path / "loose"
        root.mkdir(mode=0o755)
        with pytest.raises(ObjectStoreError):
            LocalObjectStore(str(root))


# --- S3-only invariants ---------------------------------------------


class TestS3Specifics:
    def test_requires_bucket_and_kms_key(self):
        with pytest.raises(ObjectStoreError):
            S3ObjectStore(bucket="", sse_kms_key_id="k")
        with pytest.raises(ObjectStoreError):
            S3ObjectStore(bucket="b", sse_kms_key_id="")

    def test_put_sets_sse_kms(self, s3_store):
        s3_store.put("sse/probe", b"secret", content_type="text/plain")
        response = s3_store._s3.head_object(  # noqa: SLF001
            Bucket="trustseal-test", Key="sse/probe"
        )
        # moto records the SSE directive passed to put_object.
        assert response.get("ServerSideEncryption") == "aws:kms"

    def test_list_versions_returns_latest(self, s3_store):
        s3_store.put("v/key", b"v1", content_type="text/plain")
        s3_store.put(
            "v/key", b"v2", content_type="text/plain"
        )  # new version in versioned bucket
        versions = s3_store.list_versions("v/key")
        assert any(v.is_latest for v in versions)
        assert len(versions) >= 2


# --- factory --------------------------------------------------------


class TestFactory:
    def test_local_backend_requires_root(self):
        with pytest.raises(ObjectStoreError):
            build_store({"OBJECT_STORAGE_BACKEND": "local"})

    def test_production_refuses_local(self, tmp_path):
        with pytest.raises(ObjectStoreError):
            build_store(
                {
                    "OBJECT_STORAGE_BACKEND": "local",
                    "PRIVATE_DOCUMENT_ROOT": str(tmp_path),
                    "FLASK_ENV": "production",
                }
            )

    def test_s3_requires_bucket_and_key(self):
        with pytest.raises(ObjectStoreError):
            build_store({"OBJECT_STORAGE_BACKEND": "s3"})
        with pytest.raises(ObjectStoreError):
            build_store(
                {
                    "OBJECT_STORAGE_BACKEND": "s3",
                    "OBJECT_STORAGE_S3_BUCKET": "b",
                }
            )

    def test_unknown_backend_rejected(self):
        with pytest.raises(ObjectStoreError):
            build_store({"OBJECT_STORAGE_BACKEND": "google-cloud"})

    def test_local_backend_round_trip(self, tmp_path):
        root = tmp_path / "factory"
        root.mkdir(mode=0o700)
        store = build_store(
            {
                "OBJECT_STORAGE_BACKEND": "local",
                "PRIVATE_DOCUMENT_ROOT": str(root),
            }
        )
        store.put("x/y", b"factory", content_type="text/plain")
        assert store.get("x/y") == b"factory"
