"""TOTP MFA enrollment and verification.

Design (ADR-grade — not a scaffold):

* **Secret storage.** The TOTP seed is a 160-bit random value. We never
  store it in plain text. The ``MfaCredential.secret_cipher`` column
  holds the value encrypted with a Fernet key derived from the app's
  ``SECRET_KEY``. Operators must rotate ``SECRET_KEY`` through the
  documented procedure in ADR 0001; rotation re-wraps existing seeds.
* **Enrollment flow.**

    1. ``begin_enrollment(user_id)`` creates (or resets) the row,
       returns the raw secret plus a ``otpauth://`` URI for a QR code.
       The credential stays in the ``pending`` state (``activated_at``
       is NULL) until the user proves possession.
    2. ``confirm_enrollment(user_id, code)`` verifies the first TOTP
       code the user supplies, flips ``activated_at`` to the current
       time, generates **ten** one-shot recovery codes, stores their
       hashes, and returns the clear-text codes exactly once.
    3. ``verify(user_id, code)`` is the per-sign-in check. It accepts
       a 6-digit TOTP within a ``window=1`` tolerance OR a recovery
       code; replayed TOTPs are refused through the ``last_counter``
       monotonic bookkeeping.
    4. ``disable(user_id)`` stops the credential and revokes all
       outstanding recovery codes.

* **Threat model.**

    * Replay — a captured TOTP cannot be reused because we record the
      last successful counter and refuse anything less-or-equal.
    * Brute force — rate-limiting is enforced by the API layer; this
      service is the inner domain and refuses to look up a credential
      without an authenticated user id.
    * Recovery-code exhaustion — codes are hashed with ``scrypt`` so
      database compromise does not reveal them.

Keep the clear-text secret in memory only long enough to return it to
the client. Nothing below logs the secret or the recovery codes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.extensions import db
from app.models.mfa import MfaCredential, MfaRecoveryCode

TOTP_DIGITS = 6
TOTP_WINDOW = 1  # ± 30 seconds of clock drift
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_BYTES = 8  # 16 hex chars
ISSUER = "TrustSeal"


class MfaError(RuntimeError):
    """Domain-level MFA failure."""


@dataclass(frozen=True)
class EnrollmentResult:
    secret: str
    otpauth_uri: str
    issuer: str


@dataclass(frozen=True)
class ConfirmationResult:
    recovery_codes: list[str]


# ----------------------------------------------------------------- crypto


def _fernet_key(app_secret: str) -> bytes:
    """Derive a Fernet key from the configured application secret.

    Fernet expects a 32-byte url-safe base64-encoded key. We derive it
    deterministically from ``SECRET_KEY`` so the key material does not
    need to live in a separate secret; rotation moves through the
    documented procedure.
    """
    if not isinstance(app_secret, str) or len(app_secret) < 32:
        raise MfaError("application SECRET_KEY too short to derive MFA key")
    raw = hashlib.sha256(("mfa:" + app_secret).encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw)


def _encrypt(secret: str, app_secret: str) -> str:
    return Fernet(_fernet_key(app_secret)).encrypt(secret.encode("ascii")).decode("ascii")


def _decrypt(cipher: str, app_secret: str) -> str:
    """Decrypt an MFA seed.

    Dual-key support (Phase L2): when the Flask app exposes a
    ``MFA_PREVIOUS_SECRET_KEYS`` list, the service tries every
    previous key after the active key fails. This lets operators
    rotate ``SECRET_KEY`` without breaking the existing credentials
    — the admin runs ``flask mfa rewrap`` afterwards to migrate
    stored seeds under the new key.
    """
    candidates = [app_secret]
    try:
        from flask import current_app

        previous = current_app.config.get("MFA_PREVIOUS_SECRET_KEYS") or []
        if isinstance(previous, str):
            previous = [previous]
        for prev in previous:
            if isinstance(prev, str) and prev:
                candidates.append(prev)
    except Exception:
        pass
    last_exc: Exception | None = None
    for candidate in candidates:
        try:
            return (
                Fernet(_fernet_key(candidate))
                .decrypt(cipher.encode("ascii"))
                .decode("ascii")
            )
        except InvalidToken as exc:
            last_exc = exc
            continue
        except MfaError as exc:
            last_exc = exc
            continue
    raise MfaError("MFA secret unwrap failed") from last_exc


# ----------------------------------------------------------------- recovery codes


def _hash_code(code: str) -> str:
    """One-way hash used at rest for recovery codes."""
    salt = b"trustseal/mfa/recovery"
    # scrypt is overkill for a 16-char random hex code but keeps the
    # compromise cost proportional to the brute-force budget.
    derived = hashlib.scrypt(
        code.encode("ascii"), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    return base64.urlsafe_b64encode(derived).decode("ascii")


def _generate_recovery_code() -> str:
    """Return a 16-character hex recovery code."""
    return secrets.token_hex(RECOVERY_CODE_BYTES)


# ----------------------------------------------------------------- API


def begin_enrollment(user, app_secret: str) -> EnrollmentResult:
    """Generate (or reset) a pending TOTP credential for ``user``.

    The caller is responsible for authenticating the user; this helper
    performs no authorization itself.
    """
    if user is None or not user.is_active:
        raise MfaError("inactive user cannot enroll in MFA")
    secret = pyotp.random_base32()
    cipher = _encrypt(secret, app_secret)
    existing = MfaCredential.query.filter_by(user_id=user.id).first()
    now = datetime.utcnow()
    if existing is None:
        existing = MfaCredential(
            user_id=user.id,
            secret_cipher=cipher,
            created_at=now,
            updated_at=now,
            last_counter=0,
        )
        db.session.add(existing)
    else:
        existing.secret_cipher = cipher
        existing.activated_at = None
        existing.disabled_at = None
        existing.last_counter = 0
        existing.updated_at = now
        # Clear any prior recovery codes; a reset invalidates them.
        MfaRecoveryCode.query.filter_by(credential_id=existing.id).delete()
    db.session.flush()
    account_name = f"{user.email or user.username}"
    uri = pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)
    return EnrollmentResult(secret=secret, otpauth_uri=uri, issuer=ISSUER)


def confirm_enrollment(user, code: str, *, app_secret: str, now: datetime | None = None) -> ConfirmationResult:
    """Confirm a pending credential and mint recovery codes.

    Returns the recovery codes in clear text — the caller must show
    them to the user and discard them afterwards.
    """
    if not isinstance(code, str) or not code.isdigit() or len(code) != TOTP_DIGITS:
        raise MfaError("enrollment code must be a 6-digit TOTP")
    credential = MfaCredential.query.filter_by(user_id=user.id).first()
    if credential is None:
        raise MfaError("no pending MFA enrollment for this user")
    if credential.activated_at is not None:
        raise MfaError("MFA is already active for this user")
    secret = _decrypt(credential.secret_cipher, app_secret)
    totp = pyotp.TOTP(secret)
    moment = (now or datetime.utcnow()).replace(tzinfo=timezone.utc)
    counter = int(totp.timecode(moment))
    if not totp.verify(code, for_time=moment, valid_window=TOTP_WINDOW):
        raise MfaError("TOTP code did not match")
    naive = moment.replace(tzinfo=None)
    credential.activated_at = naive
    credential.last_counter = counter
    credential.last_used_at = naive
    credential.updated_at = naive
    codes = [_generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for raw in codes:
        db.session.add(
            MfaRecoveryCode(credential_id=credential.id, code_hash=_hash_code(raw))
        )
    db.session.flush()
    return ConfirmationResult(recovery_codes=codes)


def verify(user, presented: str, *, app_secret: str, now: datetime | None = None) -> str:
    """Verify a presented TOTP or recovery code.

    Returns ``"totp"`` or ``"recovery"`` on success. Raises
    :class:`MfaError` on failure so the caller can emit a single
    unified "invalid MFA" response that does not disclose which path
    was tried.
    """
    credential = MfaCredential.query.filter_by(user_id=user.id).first()
    if credential is None or credential.activated_at is None or credential.disabled_at is not None:
        raise MfaError("MFA is not configured for this user")
    presented = (presented or "").strip()
    if not presented:
        raise MfaError("missing MFA code")
    if presented.isdigit() and len(presented) == TOTP_DIGITS:
        return _verify_totp(credential, presented, app_secret=app_secret, now=now)
    return _verify_recovery(credential, presented)


def _verify_totp(
    credential: MfaCredential,
    code: str,
    *,
    app_secret: str,
    now: datetime | None,
) -> str:
    secret = _decrypt(credential.secret_cipher, app_secret)
    totp = pyotp.TOTP(secret)
    moment = (now or datetime.utcnow()).replace(tzinfo=timezone.utc)
    naive = moment.replace(tzinfo=None)
    current_counter = int(totp.timecode(moment))
    # pyotp.verify with window accepts ±N counters; iterate manually so
    # we can reject a counter that matches the last successful one.
    for offset in range(-TOTP_WINDOW, TOTP_WINDOW + 1):
        candidate_counter = current_counter + offset
        if candidate_counter <= credential.last_counter:
            continue
        expected = totp.at(for_time=moment, counter_offset=offset)
        if hmac.compare_digest(expected, code):
            credential.last_counter = candidate_counter
            credential.last_used_at = naive
            credential.updated_at = naive
            db.session.flush()
            return "totp"
    raise MfaError("TOTP code did not match or was replayed")


def _verify_recovery(credential: MfaCredential, code: str) -> str:
    code = code.replace("-", "").replace(" ", "").lower()
    if not code.isalnum() or len(code) != RECOVERY_CODE_BYTES * 2:
        raise MfaError("invalid recovery code format")
    target = _hash_code(code)
    row = MfaRecoveryCode.query.filter_by(
        credential_id=credential.id, code_hash=target, consumed_at=None
    ).first()
    if row is None:
        raise MfaError("recovery code not found or already used")
    row.consumed_at = datetime.utcnow()
    credential.last_used_at = row.consumed_at
    credential.updated_at = row.consumed_at
    db.session.flush()
    return "recovery"


def disable(user) -> None:
    """Deactivate the user's credential and invalidate recovery codes."""
    credential = MfaCredential.query.filter_by(user_id=user.id).first()
    if credential is None or credential.activated_at is None:
        raise MfaError("no active MFA credential")
    credential.disabled_at = datetime.utcnow()
    credential.updated_at = credential.disabled_at
    # Mark all unused recovery codes consumed so they cannot be used
    # if the credential is later re-enabled.
    MfaRecoveryCode.query.filter_by(
        credential_id=credential.id, consumed_at=None
    ).update({"consumed_at": credential.disabled_at}, synchronize_session=False)
    db.session.flush()


def is_enrolled(user) -> bool:
    """Return True iff ``user`` has an active TOTP credential."""
    credential = MfaCredential.query.filter_by(user_id=user.id).first()
    return (
        credential is not None
        and credential.activated_at is not None
        and credential.disabled_at is None
    )


def rewrap_all(*, current_secret: str) -> dict:
    """Re-encrypt every ``secret_cipher`` under ``current_secret``.

    Walks every :class:`MfaCredential`, decrypts with the dual-key
    reader, and re-encrypts with the active key. Returns a summary
    dict with ``rewrapped`` + ``already_current`` + ``failed`` counts.
    Caller commits.

    Used by the ``flask mfa rewrap`` CLI after an operator rotates
    ``SECRET_KEY`` with the previous value moved to
    ``MFA_PREVIOUS_SECRET_KEYS``.
    """
    rewrapped = 0
    already_current = 0
    failed = 0
    rows = MfaCredential.query.all()
    for credential in rows:
        try:
            seed = _decrypt(credential.secret_cipher, current_secret)
        except MfaError:
            failed += 1
            continue
        fresh_cipher = _encrypt(seed, current_secret)
        if fresh_cipher == credential.secret_cipher:
            already_current += 1
            continue
        credential.secret_cipher = fresh_cipher
        credential.updated_at = datetime.utcnow()
        rewrapped += 1
    db.session.flush()
    return {
        "rewrapped": rewrapped,
        "already_current": already_current,
        "failed": failed,
    }


def unused_recovery_code_count(user) -> int:
    credential = MfaCredential.query.filter_by(user_id=user.id).first()
    if credential is None:
        return 0
    return MfaRecoveryCode.query.filter_by(
        credential_id=credential.id, consumed_at=None
    ).count()
