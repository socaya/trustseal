#!/usr/bin/env python3
"""Local client example: sign a server-issued canonical TrustSeal challenge.

Run on a participant-controlled device, never inside the TrustSeal web worker.
The private key does not leave the machine. Supports encrypted Ed25519 PEM keys.
Outputs only a base64 signature; does not send any API request.
"""
import argparse
import base64
import json
import os
import stat
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


SCHEMAS = {
    "trustseal.signer-key-enrollment.v1",
    "trustseal.signer-document-endorsement.v1",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True, help="Absolute private Ed25519 PEM path")
    parser.add_argument("--password-env", default=None, help="Optional environment variable with PEM password")
    args = parser.parse_args()

    path = Path(args.key)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        parser.error("Private key must be an absolute, non-symlink file")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        parser.error("Private key must have mode 0600")
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        parser.error("Expected one JSON challenge payload on stdin")
    if not isinstance(payload, dict) or payload.get("schema") not in SCHEMAS:
        parser.error("Unsupported TrustSeal signature challenge")
    password = None
    if args.password_env:
        secret = os.getenv(args.password_env)
        if not secret:
            parser.error("Required password environment variable missing")
        password = secret.encode("utf-8")
    try:
        key = serialization.load_pem_private_key(path.read_bytes(), password=password)
    except (TypeError, ValueError):
        parser.error("Cannot load Ed25519 private key")
    if not isinstance(key, Ed25519PrivateKey):
        parser.error("Expected Ed25519 private key")
    message = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    print(base64.b64encode(key.sign(message)).decode("ascii"))


if __name__ == "__main__":
    main()
