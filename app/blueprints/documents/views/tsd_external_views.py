"""Public landing page for external TSD share grants (magic links).

A recipient opens ``/tsd/external/<share_id>?token=…`` from the email
and lands on a read-only view of the decrypted document. No login is
required but:

* The token is validated against the stored SHA-256 hash.
* The share must be unrevoked and unexpired.
* Access is counted (``access_count`` incremented, ``consumed_at``
  stamped on first use) so the owner can audit usage.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, render_template, request

from app.extensions import db
from app.models.tsd_document import TSDocument
from app.models.tsd_external_share import TSDExternalShare, hash_token
from app.services.tsd_format import TSDError, decrypt_content_envelope


tsd_external_views = Blueprint(
    "tsd_external_views", __name__, url_prefix="/tsd/external"
)


@tsd_external_views.route("/<int:share_id>", methods=["GET"])
def landing(share_id: int):
    token = (request.args.get("token") or "").strip()
    if not token:
        abort(404)

    share = db.session.get(TSDExternalShare, share_id)
    if share is None or share.token_hash != hash_token(token):
        abort(404)
    if not share.is_active():
        return render_template("documents/tsd_external_denied.html",
                               reason="revoked" if share.revoked_at else "expired"), 410

    doc = db.session.get(TSDocument, share.tsd_id)
    if doc is None or doc.deleted_at is not None:
        abort(404)

    try:
        content = decrypt_content_envelope(
            doc.ciphertext, organization_id=doc.organization_id
        )
    except TSDError:
        abort(500)

    # Audit the access.
    share.access_count = (share.access_count or 0) + 1
    share.last_access_at = datetime.utcnow()
    if share.consumed_at is None:
        share.consumed_at = datetime.utcnow()
    db.session.commit()

    return render_template(
        "documents/tsd_external_view.html",
        doc=doc,
        share=share,
        content_html=content.get("html") or "",
    )
