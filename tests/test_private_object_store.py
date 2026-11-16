"""Pluggable private-storage backend (Phase O)."""
from __future__ import annotations

import hashlib
import io
import os
import stat as _stat
from pathlib import Path

import boto3
import pytest
from moto import mock_aws


def _pdf(label: str) -> bytes:
    return (
        b"%PDF-1.4\n% "
        + label.encode("ascii")
        + b"\n%%EOF"
    )


# ========================================================= Filesystem


@pytest.fixture
def fs_config(pg_app, tmp_path):
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    pg_app.config["PRIVATE_DOCUMENT_ROOT"] = str(root)
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "filesystem"
    return pg_app.config


class TestFilesystemStore:
    def test_put_and_read_round_trip(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
        )

        store = FilesystemObjectStore()
        data = _pdf("fs")
        result = store.put(data, config=fs_config)
        assert result.key.endswith(".pdf")
        assert result.size == len(data)
        assert result.sha256 == hashlib.sha256(data).hexdigest()
        assert store.read(result.key, config=fs_config) == data

    def test_open_local_returns_root_path(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
        )

        store = FilesystemObjectStore()
        result = store.put(_pdf("fs"), config=fs_config)
        path = store.open_local(result.key, config=fs_config)
        assert path.is_file()
        # Mode-0400 — read-only, owner only.
        mode = _stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o400

    def test_digest_matches_put(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
        )

        store = FilesystemObjectStore()
        data = _pdf("digest")
        result = store.put(data, config=fs_config)
        assert store.digest(result.key, config=fs_config) == result.sha256

    def test_delete_removes_file(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
        )

        store = FilesystemObjectStore()
        result = store.put(_pdf("del"), config=fs_config)
        store.delete(result.key, config=fs_config)
        with pytest.raises(Exception):
            store.open_local(result.key, config=fs_config)

    def test_probe_ok(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
        )

        probe = FilesystemObjectStore().probe(config=fs_config)
        assert probe["backend"] == "filesystem"
        assert probe["status"] == "ok"

    def test_invalid_key_refused(self, fs_config):
        from app.services.documents.private_object_store import (
            FilesystemObjectStore,
            StorageError,
        )

        with pytest.raises(StorageError):
            FilesystemObjectStore().read("not-a-key", config=fs_config)


# ========================================================= S3


@pytest.fixture
def s3_config(pg_app):
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "s3"
    pg_app.config["PRIVATE_STORAGE_S3_BUCKET"] = "trustseal-test-bucket"
    pg_app.config["PRIVATE_STORAGE_S3_REGION"] = "us-east-1"
    pg_app.config["PRIVATE_STORAGE_S3_ENDPOINT_URL"] = None
    pg_app.config["PRIVATE_STORAGE_S3_SSE"] = None
    yield pg_app.config
    pg_app.config["PRIVATE_STORAGE_BACKEND"] = "filesystem"


@pytest.fixture
def mocked_s3(s3_config):
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=s3_config["PRIVATE_STORAGE_S3_BUCKET"])
        yield client


class TestS3Store:
    def test_put_and_read_round_trip(self, mocked_s3, s3_config):
        from app.services.documents.private_object_store import S3ObjectStore

        store = S3ObjectStore()
        data = _pdf("s3")
        result = store.put(data, config=s3_config)
        assert result.key.endswith(".pdf")
        assert result.size == len(data)
        assert store.read(result.key, config=s3_config) == data

    def test_open_local_creates_mode_0400_tempfile(
        self, mocked_s3, s3_config
    ):
        from app.services.documents.private_object_store import (
            S3ObjectStore,
            cleanup_local,
        )

        store = S3ObjectStore()
        result = store.put(_pdf("s3-open"), config=s3_config)
        path = store.open_local(result.key, config=s3_config)
        try:
            assert path.is_file()
            assert path.name.startswith("trustseal-s3-")
            mode = _stat.S_IMODE(path.stat().st_mode)
            assert mode == 0o400
        finally:
            cleanup_local(path)
        assert not path.exists()

    def test_delete_removes_object(self, mocked_s3, s3_config):
        from app.services.documents.private_object_store import S3ObjectStore

        store = S3ObjectStore()
        result = store.put(_pdf("s3-del"), config=s3_config)
        store.delete(result.key, config=s3_config)
        from botocore.exceptions import ClientError

        with pytest.raises(ClientError):
            mocked_s3.get_object(
                Bucket=s3_config["PRIVATE_STORAGE_S3_BUCKET"], Key=result.key
            )

    def test_digest_streams_correctly(self, mocked_s3, s3_config):
        from app.services.documents.private_object_store import S3ObjectStore

        data = _pdf("digest-s3")
        store = S3ObjectStore()
        result = store.put(data, config=s3_config)
        assert store.digest(result.key, config=s3_config) == hashlib.sha256(data).hexdigest()

    def test_probe_ok(self, mocked_s3, s3_config):
        from app.services.documents.private_object_store import S3ObjectStore

        probe = S3ObjectStore().probe(config=s3_config)
        assert probe["backend"] == "s3"
        assert probe["status"] == "ok"

    def test_probe_missing_bucket_fails(self, s3_config):
        from app.services.documents.private_object_store import S3ObjectStore

        s3_config["PRIVATE_STORAGE_S3_BUCKET"] = ""
        probe = S3ObjectStore().probe(config=s3_config)
        assert probe["status"] == "failed"

    def test_invalid_key_refused(self, mocked_s3, s3_config):
        from app.services.documents.private_object_store import (
            S3ObjectStore,
            StorageError,
        )

        with pytest.raises(StorageError):
            S3ObjectStore().read("not-valid", config=s3_config)


# ========================================================= dispatcher


class TestDispatcher:
    def test_fs_dispatcher_matches_legacy_contract(
        self, fs_config, monkeypatch
    ):
        from app.services.documents import private_storage
        from app.services.documents.private_object_store import (
            store_scanned_pdf_via_active_store,
        )

        monkeypatch.setattr(
            private_storage, "_scan_pdf", lambda path, config: "noop-scanner"
        )
        key, name, size, digest, scanner = (
            store_scanned_pdf_via_active_store(
                io.BytesIO(_pdf("legacy")), "probe.pdf", fs_config
            )
        )
        assert name == "probe.pdf"
        assert size > 0
        assert digest == hashlib.sha256(_pdf("legacy")).hexdigest()
        assert scanner == "noop-scanner"

    def test_s3_dispatcher_uses_s3_backend(
        self, mocked_s3, s3_config, monkeypatch
    ):
        from app.services.documents import private_storage
        from app.services.documents.private_object_store import (
            store_scanned_pdf_via_active_store,
        )

        monkeypatch.setattr(
            private_storage,
            "_scan_pdf",
            lambda path, config: "noop-s3-scanner",
        )
        key, name, size, digest, scanner = (
            store_scanned_pdf_via_active_store(
                io.BytesIO(_pdf("via-s3")), "probe.pdf", s3_config
            )
        )
        assert scanner == "noop-s3-scanner"
        # The object exists in S3.
        obj = mocked_s3.get_object(
            Bucket=s3_config["PRIVATE_STORAGE_S3_BUCKET"], Key=key
        )
        assert obj["Body"].read() == _pdf("via-s3")


# ========================================================= readiness


class TestReadinessIntegration:
    def test_ready_reports_filesystem_backend(self, pg_app, fs_config):
        client = pg_app.test_client()
        r = client.get("/ready")
        body = r.get_json()
        storage = [c for c in body["checks"] if c["name"] == "private_storage"][0]
        assert storage["backend"] == "filesystem"
        assert storage["status"] == "ok"

    def test_ready_reports_s3_backend(self, pg_app, mocked_s3, s3_config):
        client = pg_app.test_client()
        r = client.get("/ready")
        body = r.get_json()
        storage = [c for c in body["checks"] if c["name"] == "private_storage"][0]
        assert storage["backend"] == "s3"
        assert storage["status"] == "ok"
