"""Tenant-scoped signer attachment lookup (Phase AD1).

Mounted at ``/api/signer-attachments``. The only endpoint for now
is a SHA-256 index — public-verify tooling and forensic workflows
need to confirm "does a signer-attachment with this digest exist
in this tenant?" without downloading bytes.

The response returns metadata only (envelope id, decision id,
file name, size). Staged attachments (``decision_id IS NULL``)
are excluded so the surface cannot be used to trawl through
in-flight signer uploads.
"""
from __future__ import annotations

import re

from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required

from app.models.signer_attachment import SignerAttachment
from app.services.token_security import active_token_user


signer_attachment_api = Blueprint(
    "signer_attachment_api",
    __name__,
    url_prefix="/api/signer-attachments",
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _actor():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if user.organization_id is None:
        abort(403)
    return user


@signer_attachment_api.route("/by-sha256/<sha256>", methods=["GET"])
@jwt_required()
def lookup_by_sha256(sha256: str):
    user = _actor()
    if not _SHA256_RE.fullmatch(sha256 or ""):
        abort(400, description="sha256_invalid")
    rows = (
        SignerAttachment.query.filter_by(
            organization_id=user.organization_id, sha256=sha256
        )
        .filter(SignerAttachment.decision_id.isnot(None))
        .order_by(SignerAttachment.id.asc())
        .all()
    )
    return jsonify(
        sha256=sha256,
        found=len(rows),
        attachments=[
            {
                "id": row.id,
                "envelope_id": row.envelope_id,
                "decision_id": row.decision_id,
                "participant_id": row.participant_id,
                "file_name": row.file_name,
                "mime_type": row.mime_type,
                "file_size": row.file_size,
                "scanner": row.scanner,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    )
