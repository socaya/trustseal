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
import uuid
from datetime import datetime

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
from app.services.rate_limiting import RateLimitError, consume

sign_views = Blueprint(
    "sign_views",
    __name__,
    url_prefix="/sign",
    template_folder="../../../templates",
)

_RATE_WINDOW_SECONDS = 60
_RATE_MAX = 20


def _client_identifier() -> str:
    """Hashed source identifier for rate limiting; raw IP is never stored."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    raw = forwarded.split(",")[0].strip() if forwarded else (request.remote_addr or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _rate_limited() -> bool:
    identity = _client_identifier()
    try:
        decision = consume(
            bucket_key=f"sign:{identity}",
            max_hits=_RATE_MAX,
            window_seconds=_RATE_WINDOW_SECONDS,
        )
    except RateLimitError:
        return False
    return not decision.allowed


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


@sign_views.route("/<token>/status", methods=["GET"])
def status(token: str):
    """Signer-facing status probe (Phase AD2).

    Returns the minimum envelope + decision state a signer app
    needs to know whether a review is still pending — without
    consuming the invitation. 404 on bad / revoked / expired
    tokens, and the response never carries any PII beyond the
    document digest and the participant's signing_order.
    """
    from flask import jsonify
    from app.models.signer_decision import SignerDecision

    if _rate_limited():
        return jsonify(error="rate_limited"), 429
    try:
        resolved = signer_invitations.resolve(token)
    except signer_invitations.InvitationError:
        return jsonify(error="unavailable"), 404
    decision = (
        SignerDecision.query.filter_by(
            envelope_id=resolved.envelope.id,
            participant_id=resolved.participant.id,
        )
        .first()
    )
    return jsonify(
        envelope_id=resolved.envelope.id,
        envelope_state=resolved.envelope.state,
        document_sha256=resolved.envelope.document_sha256,
        signing_order=resolved.participant.signing_order,
        role=resolved.participant.role,
        decision_recorded=decision is not None,
        decision=decision.decision if decision else None,
        decision_recorded_at=(
            decision.recorded_at.isoformat() if decision else None
        ),
        invitation_expires_at=resolved.invitation.expires_at.isoformat(),
    )


@sign_views.route("/<token>/attachments", methods=["POST"])
def upload_attachment(token: str):
    """Signer uploads a supporting attachment (Phase U1).

    Accepts a single ``file`` multipart field. The attachment is
    persisted in a staged state (``decision_id IS NULL``) and the
    returned id is referenced in the subsequent decision form so
    the recorded SignerDecision owns the attachment set.
    """
    from flask import jsonify
    from app.services import signer_attachments

    if _rate_limited():
        return (
            jsonify(error="rate_limited"),
            429,
        )
    try:
        resolved = signer_invitations.resolve(token)
    except signer_invitations.InvitationError:
        return jsonify(error="unavailable"), 404
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="file_required"), 400
    payload = uploaded.read()
    mime = (uploaded.mimetype or "").split(";", 1)[0].strip().lower()
    try:
        result = signer_attachments.store(
            envelope=resolved.envelope,
            participant=resolved.participant,
            file_name=uploaded.filename,
            mime_type=mime,
            payload=payload,
            config=current_app.config,
        )
    except signer_attachments.AttachmentError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    db.session.commit()
    return (
        jsonify(
            id=result.attachment.id,
            sha256=result.sha256,
            file_name=result.attachment.file_name,
            mime_type=result.attachment.mime_type,
            file_size=result.attachment.file_size,
        ),
        201,
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
    db.session.flush()

    # Optional drawn signature appearance. Signers may submit the
    # form without drawing (e.g. a decline) and the field is simply
    # empty. Any decode / size / format failure aborts the decision
    # so a tampered payload can never be persisted silently.
    appearance_payload = (request.form.get("appearance_png_data_url") or "").strip()
    appearance_stored = False
    if choice == "acknowledged" and appearance_payload:
        from app.services import signer_appearances

        try:
            signer_appearances.store(
                decision=decision_row,
                envelope=envelope,
                participant=participant,
                payload=appearance_payload,
                config=current_app.config,
            )
            appearance_stored = True
        except signer_appearances.AppearanceError as exc:
            db.session.rollback()
            current_app.logger.info(
                "signer_appearance_rejected",
                extra={"reason": str(exc)},
            )
            flash(
                "We could not record your drawn signature. "
                "Please redraw and try again.",
                "danger",
            )
            return redirect(url_for("sign_views.landing", token=token))

    # Optional staged supporting attachments (Phase U2). The form
    # carries attachment ids chosen by the signer; each must belong
    # to this envelope + participant and not yet be bound to another
    # decision. A rejection here rolls the whole decision back so
    # the recorded consent never lies about the attached evidence.
    attachment_ids_raw = (request.form.get("attachment_ids") or "").strip()
    attachments_bound = 0
    if attachment_ids_raw:
        from app.services import signer_attachments

        try:
            parsed = [
                int(part)
                for part in attachment_ids_raw.split(",")
                if part.strip()
            ]
        except ValueError:
            db.session.rollback()
            flash("Attachment list was malformed. Please try again.", "danger")
            return redirect(url_for("sign_views.landing", token=token))
        try:
            claimed = signer_attachments.claim_staged(
                decision=decision_row, attachment_ids=parsed
            )
        except signer_attachments.AttachmentError as exc:
            db.session.rollback()
            current_app.logger.info(
                "signer_attachment_rejected",
                extra={"reason": str(exc)},
            )
            flash(
                "We could not attach the uploaded files. "
                "Please re-upload and try again.",
                "danger",
            )
            return redirect(url_for("sign_views.landing", token=token))
        attachments_bound = len(claimed)

    signer_invitations.consume(resolved.invitation)
    db.session.commit()
    return render_template(
        "envelopes/sign/recorded.html",
        choice=choice,
        envelope=envelope,
        appearance_stored=appearance_stored,
        attachments_bound=attachments_bound,
    )
