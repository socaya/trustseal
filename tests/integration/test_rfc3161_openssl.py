"""Real OpenSSL-issued RFC3161 token verification, no external TSA network.

Generates disposable root and timestamping-only leaf with OpenSSL and
verifies CMS, SHA256 message imprint, nonce, chain and pinned signer identity.
"""
import hashlib
import subprocess

import pytest
from asn1crypto import tsp

from app.services.rfc3161_timestamp import TimestampError, verify_timestamp


def _run(*args, cwd=None):
    response = subprocess.run(
        ["openssl", *map(str, args)], cwd=cwd,
        capture_output=True, text=True, timeout=20,
    )
    assert response.returncode == 0, response.stderr


def test_real_timestamp_rejects_imprint_nonce_and_wrong_signer(tmp_path):
    root = tmp_path / "root.pem"
    _run(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", tmp_path / "root.key", "-out", root,
        "-subj", "/CN=Disposable TSA root", "-days", "2",
    )
    _run(
        "req", "-newkey", "rsa:2048", "-nodes",
        "-keyout", tmp_path / "tsa.key", "-out", tmp_path / "tsa.csr",
        "-subj", "/CN=Disposable RFC3161 TSA",
    )
    extensions = tmp_path / "tsa-extensions.cnf"
    extensions.write_text(
        "basicConstraints=CA:FALSE\n"
        "keyUsage=critical,digitalSignature,nonRepudiation\n"
        "extendedKeyUsage=critical,timeStamping\n"
        "subjectKeyIdentifier=hash\n"
        "authorityKeyIdentifier=keyid,issuer\n"
    )
    tsa_cert = tmp_path / "tsa.pem"
    _run(
        "x509", "-req", "-in", tmp_path / "tsa.csr", "-CA", root,
        "-CAkey", tmp_path / "root.key", "-CAcreateserial",
        "-out", tsa_cert, "-days", "2", "-extfile", extensions,
    )
    (tmp_path / "serial").write_text("01\n")
    (tmp_path / "tsa.cnf").write_text(
        "[tsa]\n"
        "default_tsa=tsa_config\n"
        "[tsa_config]\n"
        "serial=serial\n"
        "signer_cert=tsa.pem\n"
        "signer_key=tsa.key\n"
        "signer_digest=sha256\n"
        "default_policy=1.2.3.4.5\n"
        "digests=sha256\n"
        "accuracy=secs:1\n"
        "ordering=yes\n"
        "tsa_name=yes\n"
        "ess_cert_id_chain=no\n"
    )
    digest = hashlib.sha256(b"complete retained TrustSeal document").hexdigest()
    query = tmp_path / "request.tsq"
    response = tmp_path / "response.tsr"
    _run("ts", "-query", "-digest", digest, "-sha256", "-cert",
         "-out", query)
    _run("ts", "-reply", "-config", "tsa.cnf", "-queryfile",
         "request.tsq", "-out", "response.tsr", cwd=tmp_path)
    raw = response.read_bytes()
    parsed = tsp.TimeStampResp.load(raw)
    info = parsed["time_stamp_token"]["content"]["encap_content_info"]["content"].parsed
    nonce = info["nonce"].native
    config = {
        "RFC3161_TRUST_ROOT_PEM": str(root),
        "RFC3161_TSA_CERT_PEM": str(tsa_cert),
    }
    result = verify_timestamp(raw, digest, config, expected_nonce=nonce)
    assert result["token_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["tsa_certificate_sha256"]
    assert result["gen_time"].year >= 2026

    # Public evidence verification can use the nonce embedded in a retained
    # response, whereas request-time verification requires the original nonce.
    assert verify_timestamp(raw, digest, config)["token_sha256"] == result["token_sha256"]
    with pytest.raises(TimestampError):
        verify_timestamp(raw, "a" * 64, config, expected_nonce=nonce)
    with pytest.raises(TimestampError):
        verify_timestamp(raw, digest, config, expected_nonce=nonce + 1)

    unrelated_root = tmp_path / "unrelated.pem"
    _run(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", tmp_path / "other.key", "-out", unrelated_root,
        "-subj", "/CN=Different TSA certificate", "-days", "2",
    )
    with pytest.raises(TimestampError):
        verify_timestamp(raw, digest, {
            **config, "RFC3161_TSA_CERT_PEM": str(unrelated_root),
        })
    with pytest.raises(TimestampError):
        verify_timestamp(raw, digest, {
            **config, "RFC3161_TRUST_ROOT_PEM": str(unrelated_root),
        })
