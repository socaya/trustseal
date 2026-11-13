"""Bounded RFC 3161 TSA request and independently verified response.

OpenSSL validates CMS signature, signed message imprint, certificate purpose
and chain. We additionally pin the *actual CMS signer certificate* by SHA-256,
require a matching nonce, and reject malformed/oversized responses.
"""
import base64
import hashlib
import os
import re
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from asn1crypto import tsp, x509

MAX_TOKEN = 65536
HEX = re.compile(r"^[0-9a-f]{64}$")


class TimestampError(ValueError):
    pass


def _trusted_file(path, label):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise TimestampError(label + " requires an absolute file path")
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_file() or candidate.stat().st_size > 65536:
        raise TimestampError(label + " trust file unavailable")
    return candidate


def _parse_response(raw, expected_digest, expected_nonce, tsa_cert_pem):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_TOKEN:
        raise TimestampError("RFC 3161 response exceeds bounded size")
    try:
        response = tsp.TimeStampResp.load(raw, strict=True)
        if response["status"]["status"].native not in ("granted", "granted_with_mods"):
            raise TimestampError("TSA did not grant a timestamp")
        token = response["time_stamp_token"]
        if token.native is None:
            raise TimestampError("Missing TSA signed token")
        signed = token["content"]
        certificates = signed["certificates"]
        signers = signed["signer_infos"]
        if len(signers) != 1:
            raise TimestampError("Exactly one TSA signer required")
        signer = signers[0]
        if signer["sid"].name != "issuer_and_serial_number":
            raise TimestampError("TSA signer certificate identifier unsupported")
        sid = signer["sid"].chosen
        from cryptography import x509 as crypto_x509
        from cryptography.hazmat.primitives import serialization
        pinned = crypto_x509.load_pem_x509_certificate(tsa_cert_pem)
        pinned_der = pinned.public_bytes(serialization.Encoding.DER)
        certificate_digest = hashlib.sha256(pinned_der).hexdigest()
        matched = False
        for choice in certificates:
            if choice.name != "certificate":
                continue
            certificate = choice.chosen
            if (certificate.issuer == sid["issuer"]
                    and certificate.serial_number == sid["serial_number"].native):
                if certificate.dump() != pinned_der:
                    raise TimestampError("TSA signer certificate is not pinned")
                matched = True
        if not matched:
            raise TimestampError("TSA signer certificate absent from response")
        content = signed["encap_content_info"]["content"].native
        info = tsp.TSTInfo.load(content)
        imprint = info["message_imprint"]
        if (imprint["hash_algorithm"]["algorithm"].native != "sha256"
                or imprint["hashed_message"].native != bytes.fromhex(expected_digest)):
            raise TimestampError("TSA message imprint does not match artifact")
        if info["nonce"].native != expected_nonce:
            raise TimestampError("TSA response nonce mismatch")
        when = info["gen_time"].native
        if when.tzinfo is None:
            raise TimestampError("Timestamp lacks a time zone")
        when = when.astimezone(timezone.utc).replace(tzinfo=None)
        return when, certificate_digest
    except TimestampError:
        raise
    except Exception as exc:
        raise TimestampError("Invalid ASN.1 timestamp response") from exc


def _openssl_verify(raw, digest, root, signer_cert, openssl="openssl"):
    with tempfile.TemporaryDirectory(prefix="trustseal-rfc3161-") as directory:
        path = Path(directory) / "timestamp.tsr"
        path.write_bytes(raw)
        try:
            result = subprocess.run(
                [openssl, "ts", "-verify", "-in", str(path),
                 "-digest", digest, "-sha256",
                 "-CAfile", str(root), "-untrusted", str(signer_cert)],
                capture_output=True, timeout=12, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TimestampError("Timestamp certificate verification unavailable") from exc
    if result.returncode != 0:
        raise TimestampError("TSA CMS signature or certificate chain invalid")


def verify_timestamp(raw, digest, config, expected_nonce=None):
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise TimestampError("Invalid document SHA-256")
    root = _trusted_file(config.get("RFC3161_TRUST_ROOT_PEM"), "TSA root")
    cert = _trusted_file(config.get("RFC3161_TSA_CERT_PEM"), "TSA signer")
    when, fingerprint = _parse_response(raw, digest, expected_nonce, cert.read_bytes()) if expected_nonce is not None else _parse_without_nonce(raw, digest, cert.read_bytes())
    _openssl_verify(raw, digest, root, cert, config.get("RFC3161_OPENSSL_BINARY") or "openssl")
    return {"gen_time": when, "tsa_certificate_sha256": fingerprint,
            "token_sha256": hashlib.sha256(raw).hexdigest()}


def _parse_without_nonce(raw, digest, tsa_cert):
    # Retained tokens must still carry a nonce. Extract and re-check it,
    # because the original request nonce is not stored separately.
    try:
        response = tsp.TimeStampResp.load(raw, strict=True)
        token = response["time_stamp_token"]
        info = tsp.TSTInfo.load(token["content"]["encap_content_info"]["content"].native)
        nonce = info["nonce"].native
        if nonce is None:
            raise TimestampError("Timestamp nonce missing")
    except TimestampError:
        raise
    except Exception as exc:
        raise TimestampError("Timestamp cannot be decoded") from exc
    return _parse_response(raw, digest, nonce, tsa_cert)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise TimestampError("TSA redirects are prohibited")


def request_timestamp(digest, config):
    """Request one timestamp over a SHA-256 imprint, then verify before use."""
    if not config.get("RFC3161_ENABLED", False):
        raise TimestampError("External timestamping is disabled")
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise TimestampError("Invalid digest")
    endpoint = config.get("RFC3161_TSA_URL")
    url = urlsplit(endpoint or "")
    if (url.scheme != "https" or not url.hostname
            or url.username or url.password or url.fragment
            or url.port not in (None, 443)):
        raise TimestampError("A configured HTTPS TSA endpoint is required")
    nonce = secrets.randbits(128) or 1
    request = tsp.TimeStampReq({
        "version": "v1",
        "message_imprint": {
            "hash_algorithm": {"algorithm": "sha256"},
            "hashed_message": bytes.fromhex(digest),
        },
        "nonce": nonce,
        "cert_req": True,
    }).dump()
    http = Request(
        endpoint, data=request, method="POST",
        headers={"Content-Type": "application/timestamp-query",
                 "Accept": "application/timestamp-reply"},
    )
    try:
        with build_opener(_NoRedirect).open(http, timeout=8) as response:
            if response.status != 200:
                raise TimestampError("TSA response rejected")
            if response.headers.get_content_type() != "application/timestamp-reply":
                raise TimestampError("Unexpected TSA content type")
            raw = response.read(MAX_TOKEN + 1)
    except (OSError, TimeoutError) as exc:
        raise TimestampError("TSA request failed") from exc
    if len(raw) > MAX_TOKEN:
        raise TimestampError("TSA response exceeds bounded size")
    result = verify_timestamp(raw, digest, config, expected_nonce=nonce)
    return raw, result


def encode_token(raw):
    return base64.b64encode(raw).decode("ascii")


def decode_token(encoded):
    if not isinstance(encoded, str) or len(encoded) > 90000:
        raise TimestampError("Timestamp token encoding invalid")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise TimestampError("Timestamp token base64 invalid") from exc
    if len(raw) > MAX_TOKEN:
        raise TimestampError("Timestamp token too large")
    return raw
