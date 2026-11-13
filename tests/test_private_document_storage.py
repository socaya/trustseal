"""Isolated private-file storage tests.

Run: pytest -q tests/test_private_document_storage.py
Scanner behavior is mocked; production ClamAV must be tested separately.
"""
import hashlib
import io

import pytest
from flask import Flask

from app.services.documents import private_storage as storage


@pytest.fixture
def private_config(tmp_path):
    flask = Flask(__name__)
    destination = tmp_path / "objects"
    destination.mkdir(mode=0o700)
    config = {"PRIVATE_DOCUMENT_ROOT": str(destination)}
    with flask.app_context():
        yield config


def sample_pdf(contents=b"test"):
    return b"%PDF-1.4\n" + contents + b"\n%%EOF\n"


def test_private_pdf_promotion_and_digest(monkeypatch, private_config):
    monkeypatch.setattr(storage, "_scan_pdf", lambda path, config: "clamav-clamscan")
    pdf = sample_pdf()
    key, name, size, digest, scanner = storage.store_scanned_pdf(
        io.BytesIO(pdf), "contract.pdf", private_config
    )
    assert name == "contract.pdf"
    assert size == len(pdf)
    assert digest == hashlib.sha256(pdf).hexdigest()
    assert scanner == "clamav-clamscan"
    path = storage.check_object_digest(key, digest, private_config)
    assert path.read_bytes() == pdf
    assert not list(path.parent.glob(".quarantine-*"))


def test_refuses_missing_scanner(private_config):
    with pytest.raises(storage.IngestionError, match="scanner"):
        storage.store_scanned_pdf(
            io.BytesIO(sample_pdf()), "contract.pdf", private_config
        )


@pytest.mark.parametrize("name", [
    "contract.docx", "../contract.exe", "invoice.pdf\x00", "",
])
def test_filename_validation(private_config, name):
    with pytest.raises(storage.IngestionError):
        storage.store_scanned_pdf(io.BytesIO(sample_pdf()), name, private_config)


@pytest.mark.parametrize("payload", [
    b"", b"not a pdf", b"%PDF-1.5\nwithout end marker",
])
def test_rejects_invalid_pdf(monkeypatch, private_config, payload):
    monkeypatch.setattr(storage, "_scan_pdf", lambda path, config: "clamav-clamscan")
    with pytest.raises(storage.IngestionError):
        storage.store_scanned_pdf(io.BytesIO(payload), "a.pdf", private_config)


def test_digest_mismatch_fails_closed(monkeypatch, private_config):
    monkeypatch.setattr(storage, "_scan_pdf", lambda path, config: "clamav-clamscan")
    key, _, _, digest, _ = storage.store_scanned_pdf(
        io.BytesIO(sample_pdf()), "a.pdf", private_config
    )
    path = storage.object_path(key, private_config)
    path.chmod(0o600)
    path.write_bytes(sample_pdf(b"altered"))
    with pytest.raises(storage.IngestionError, match="digest mismatch"):
        storage.check_object_digest(key, digest, private_config)


def test_rejects_traversal_key(private_config):
    with pytest.raises(storage.IngestionError):
        storage.object_path("../../other.pdf", private_config)


def test_rejects_public_storage_root(tmp_path):
    flask = Flask(__name__)
    with flask.app_context():
        with pytest.raises(storage.IngestionError, match="static"):
            storage._storage_root({
                "PRIVATE_DOCUMENT_ROOT": str(flask.static_folder) + "/uploads"
            })


def test_file_exceeds_limit(monkeypatch, private_config):
    monkeypatch.setattr(storage, "_scan_pdf", lambda path, config: "clamav-clamscan")
    with pytest.raises(storage.IngestionError, match="exceeds"):
        storage.store_scanned_pdf(
            io.BytesIO(b"%PDF-1.4\n" + b"A" * (storage.MAX_FILE_BYTES + 1) + b"%%EOF"),
            "too-big.pdf",
            private_config,
        )
