"""RFC 3161 validation must be fail-closed for malformed and untrusted input."""
import base64
import hashlib
from unittest.mock import patch

import pytest
from asn1crypto import tsp

from app.services.rfc3161_timestamp import (
    TimestampError, MAX_TOKEN, request_timestamp, verify_timestamp,
    decode_token, encode_token,
)


DIGEST = hashlib.sha256(b"TrustSeal retained PDF").hexdigest()


def test_timestamp_defaults_disabled():
    with pytest.raises(TimestampError, match="disabled"):
        request_timestamp(DIGEST, {"RFC3161_ENABLED": False})


@pytest.mark.parametrize("url", [
    "http://tsa.example.com",
    "https://user:secret@tsa.example.com",
    "https://tsa.example.com:8443",
    "file:///etc/passwd",
    "https://tsa.example.com/#fragment",
])
def test_rejects_unsafe_tsa_configuration_before_network(url):
    with pytest.raises(TimestampError):
        request_timestamp(DIGEST, {
            "RFC3161_ENABLED": True, "RFC3161_TSA_URL": url,
        })


def test_bad_imprint_and_missing_trust_fail_closed(tmp_path):
    with pytest.raises(TimestampError, match="Invalid document"):
        verify_timestamp(b"garbage", "wrong", {})
    with pytest.raises(TimestampError):
        verify_timestamp(b"garbage", DIGEST, {})
    with pytest.raises(TimestampError):
        verify_timestamp(b"x" * (MAX_TOKEN + 1), DIGEST, {
            "RFC3161_TRUST_ROOT_PEM": str(tmp_path / "missing"),
        })


def test_token_encoding_is_bounded_and_exact():
    raw = b"timestamp-bytes"
    assert decode_token(encode_token(raw)) == raw
    with pytest.raises(TimestampError):
        decode_token("not base64 %%")
    with pytest.raises(TimestampError):
        decode_token(base64.b64encode(b"x" * (MAX_TOKEN + 1)).decode())


def test_valid_request_contains_exact_sha256_and_nonce():
    seen = {}
    class _Response:
        status = 200
        headers = type("Headers", (), {
            "get_content_type": lambda self: "application/timestamp-reply",
        })()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, amount):
            return b"RFC3161-response"
    class _Opener:
        def open(self, req, timeout):
            parsed = tsp.TimeStampReq.load(req.data, strict=True)
            seen["imprint"] = parsed["message_imprint"]["hashed_message"].native
            seen["nonce"] = parsed["nonce"].native
            seen["cert_req"] = parsed["cert_req"].native
            seen["timeout"] = timeout
            return _Response()
    with patch("app.services.rfc3161_timestamp.build_opener", return_value=_Opener()):
        with patch("app.services.rfc3161_timestamp.verify_timestamp", return_value={
            "tsa_certificate_sha256": "a" * 64,
            "token_sha256": "b" * 64,
        }) as verify:
            raw, result = request_timestamp(DIGEST, {
                "RFC3161_ENABLED": True,
                "RFC3161_TSA_URL": "https://tsa.example.org/timestamp",
            })
    assert raw == b"RFC3161-response"
    assert result["token_sha256"] == "b" * 64
    assert seen["imprint"] == bytes.fromhex(DIGEST)
    assert seen["nonce"] > 0
    assert seen["cert_req"] is True
    assert seen["timeout"] == 8
    assert verify.call_args.kwargs["expected_nonce"] == seen["nonce"]
