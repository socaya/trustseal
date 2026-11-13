"""Authorized export and verification of organizational stamp attestations.

Verifies a detached proof of an approved organizational action. No PDF
modification, visual stamp, public tenant enumeration or impersonated seal.
"""
from flask import Blueprint, abort, current_app, jsonify
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.models.pdf_finalization import FinalizedPdf
from app.services.token_security import active_token_user
from app.policies.api_access import is_admin
from app.services.stamp_attestation import (
    stamp_payload, trusted_stamp_key, verify_attestation, attestation_digest,
)

stamp_attestation_api = Blueprint(
    "stamp_attestation_api", __name__, url_prefix="/api/stamp-attestations"
)


def _authorized(receipt_id):
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    record = StampAttestation.query.filter_by(
        id=receipt_id, organization_id=actor.organization_id
    ).first()
    if record is None:
        abort(404)
    application = StampApplication.query.filter_by(
        id=record.application_id, organization_id=actor.organization_id
    ).first()
    stamp = ManagedStamp.query.filter_by(
        id=record.stamp_id, organization_id=actor.organization_id
    ).first()
    if application is None or stamp is None:
        abort(409, description="Stamp evidence references are incomplete")
    if not is_admin(actor.id) and actor.id not in (
        stamp.custodian_id, application.requested_by_id
    ):
        abort(404)
    return record, application, stamp


def _verified(record, application, stamp):
    pdf = db.session.get(FinalizedPdf, application.finalized_pdf_id)
    if pdf is None or pdf.organization_id != stamp.organization_id:
        return False
    try:
        expected = stamp_payload(
            stamp, application, pdf, record.operator_id, record.created_at
        )
        trusted = trusted_stamp_key(current_app.config, record.key_id)
        signed = {
            "payload": record.payload, "algorithm": record.algorithm,
            "key_id": record.key_id, "signature": record.signature,
        }
        return bool(
            expected == record.payload
            and verify_attestation(signed, trusted)
            and record.organization_id == stamp.organization_id
            and record.stamp_id == stamp.id
            and record.application_id == application.id
        )
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        return False


@stamp_attestation_api.route("/<int:attestation_id>", methods=["GET"])
@jwt_required()
def verify_stamp_attestation(attestation_id):
    record, application, stamp = _authorized(attestation_id)
    verified = _verified(record, application, stamp)
    result = jsonify({
        "attestation_id": record.id,
        "valid": verified,
        "stamp_currently_active": stamp.status == "active",
        "key_id": record.key_id,
        "assurance": "organizational_authorization_attestation_not_pdf_impression",
        "not_pdf_signature": True,
    })
    result.headers["Cache-Control"] = "private, no-store"
    return result


@stamp_attestation_api.route("/<int:attestation_id>/export", methods=["GET"])
@jwt_required()
def export_stamp_attestation(attestation_id):
    record, application, stamp = _authorized(attestation_id)
    if not _verified(record, application, stamp):
        abort(409, description="Stamp attestation failed verification")
    signed = {
        "payload": record.payload, "algorithm": record.algorithm,
        "key_id": record.key_id, "signature": record.signature,
    }
    response = jsonify({
        "attestation": signed,
        "sha256": attestation_digest(signed),
        "assurance": "organizational_authorization_attestation_not_pdf_impression",
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response
