"""Signer landing page.

``/sign/<token>`` is the anonymous-but-authorized surface a signer
clicks through to review an envelope and record their decision.
Design:

* The token is resolved via a hashed lookup. A bad or expired token
  reveals nothing — the page shows a uniform "unavailable" message.
* A valid token loads the envelope, the participant, and the bound
  document digest. The page renders the document's metadata plus a
  download link routed through the authenticated-signer channel
  (not the generic document API). No inline PDF viewer is embedded;
  the signer downloads the file and reviews it out-of-band.
* The signer POSTs ``acknowledge`` or ``decline`` with the token in
  the form body. Both actions:
    * re-resolve the token (so a concurrent revocation is honoured),
    * consume the invitation,
    * create a :class:`SignerDecision` referencing the envelope's
      document digest so the orchestrator can verify the chain.
* A simple in-process rate limiter protects the resolve endpoint
  from enumeration attempts.

The view is intentionally server-rendered Jinja — the same flat UX
spec the verify and evidence pages follow. No JS framework, no
client-side crypto.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from collections import deque
from datetime import datetime
from threading import Lock

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.extensions import db
from app.models.signer_decision import SignerChallenge, SignerDecision
from app.services import signer_invitations

sign_views = Blueprint(
    "sign_views",
    __name__,
    url_prefix="/sign",
    template_folder="../../../templates",
)

_RATE_WINDOW_SECONDS = 60
_RATE_MAX = 20
_RATE_LOCK = Lock()
_RATE_TRACKER: dict[str, deque] = {}


def _client_identifier() -> str:
    """Hashed source identifier for rate limiting; raw IP is never stored."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    raw = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _rate_limited() -> bool:
    identity = _client_identifier()
    now = time.monotonic()
    with _RATE_LOCK:
        bucket = _RATE_TRACKER.setdefault(identity, deque())
        while bucket and (now - bucket[0]) > _RATE_WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _RATE_MAX:
            return True
        bucket.append(now)
    return False


def _unavailable(token: str, status: int = 404):
    return (
        render_template(
            "envelopes/sign/unavailable.html",
            back_url=url_for("verify_views.verify_form"),
        ),
        status,
    )


def _consent_version() -> str:
    return (
        current_app.config.get("SIGNER_CONSENT_VERSION")
        or "trustseal-review-consent-v1"
    )


def _consent_text(version: str) -> str:
    """Return the consent text for the given version.

    Keep the text versioned: the signer's decision records the version
    so an auditor can later tell exactly what the user agreed to.
    """
    if version == "trustseal-review-consent-v1":
        return (
            "By submitting, I acknowledge that I have reviewed the document "
            "identified above, agree to its content as presented, and "
            "consent to being recorded as a reviewing participant on "
            "the envelope evidence record."
        )
    return current_app.config.get(
        "SIGNER_CONSENT_FALLBACK",
        "By submitting, I acknowledge my review and consent to the record.",
    )


def _consent_digest(envelope_id: int, participant_id: int, version: str, text: str) -> str:
    base = f"{envelope_id}|{participant_id}|{version}|{text}".encode("utf-8")
    return hashlib.sha256(base).hexdigest()


@sign_views.route("/<token>", methods=["GET"])
def landing(token: str):
    if _rate_limited():
        return (
            render_template("envelopes/sign/rate_limited.html"),
            429,
        )
    try:
        resolved = signer_invitations.resolve(token)
    except signer_invitations.InvitationError as exc:
        current_app.logger.info(
            "signer_invitation_rejected",
            extra={"reason": exc.reason, "path": request.path},
        )
        return _unavailable(token)
    version = _consent_version()
    return render_template(
        "envelopes/sign/review.html",
        token=token,
        envelope=resolved.envelope,
        participant=resolved.participant,
        consent_version=version,
        consent_text=_consent_text(version),
        download_url=url_for(
            "sign_views.download", token=token
        ),
    )


@sign_views.route("/<token>/download", methods=["GET"])
def download(token: str):
    """Return an authenticated-but-signer-scoped PDF download.

    The signer never sees a tenant-level URL. The file is resolved
    through the private storage adapter the authenticated API path
    uses and is streamed through Flask.
    """
    if _rate_limited():
        return (
            render_template("envelopes/sign/rate_limited.html"),
            429,
        )
    try:
        resolved = signer_invitations.resolve(token)
    except signer_invitations.InvitationError:
        return _unavailable(token)
    from app.models.documents.document_blob import DocumentBlob
    from app.services.documents.private_storage import (
        IngestionError,
        check_object_digest,
    )
    from flask import send_file

    blob = db.session.get(DocumentBlob, resolved.envelope.document_blob_id)
    if blob is None:
        return _unavailable(token, status=503)
    try:
        path = check_object_digest(
            blob.object_key, blob.sha256, current_app.config
        )
    except IngestionError:
        return _unavailable(token, status=503)
    return send_file(
        str(path),
        mimetype=blob.mime_type or "application/pdf",
        as_attachment=True,
        download_name=f"envelope-{resolved.envelope.id}.pdf",
    )


@sign_views.route("/<token>/decision", methods=["POST"])
def decision(token: str):
    if _rate_limited():
        return (
            render_template("envelopes/sign/rate_limited.html"),
            429,
        )
    choice = (request.form.get("choice") or "").strip().lower()
    if choice not in {"acknowledged", "declined"}:
        flash("Pick acknowledge or decline.", "danger")
        return redirect(url_for("sign_views.landing", token=token))
    try:
        resolved = signer_invitations.resolve(token)
    except signer_invitations.InvitationError:
        return _unavailable(token)
    envelope = resolved.envelope
    participant = resolved.participant
    version = _consent_version()
    text = _consent_text(version)
    now = datetime.utcnow()
    challenge = SignerChallenge(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=participant.user_id,
        nonce_sha256=hashlib.sha256(
            f"{token}|{choice}|{now.isoformat()}".encode("utf-8")
        ).hexdigest(),
        document_sha256=envelope.document_sha256,
        issued_at=now,
        expires_at=now + __import__("datetime").timedelta(minutes=5),
        consumed_at=now,
    )
    db.session.add(challenge)
    db.session.flush()
    decision_row = SignerDecision(
        envelope_id=envelope.id,
        participant_id=participant.id,
        user_id=participant.user_id,
        challenge_id=challenge.id,
        decision=choice,
        document_sha256=envelope.document_sha256,
        consent_version=version,
        consent_sha256=_consent_digest(envelope.id, participant.id, version, text),
        recorded_at=now,
    )
    db.session.add(decision_row)
    signer_invitations.consume(resolved.invitation)
    db.session.commit()
    return render_template(
        "envelopes/sign/recorded.html",
        choice=choice,
        envelope=envelope,
    )
