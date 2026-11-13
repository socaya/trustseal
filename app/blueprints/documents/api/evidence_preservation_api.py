"""Authenticated, tenant-scoped legal hold and retention management.

No deletion, retention-shortening, or public document enumeration endpoint.
Admins can place holds; only a different admin may release them.
"""
import re
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.evidence_preservation import EvidenceRetention, EvidenceLegalHold, EvidenceCheckpoint
from app.services.evidence_preservation import artifact_for, protection_status, verify_artifact
from app.services.documents.private_storage import IngestionError
from app.services.platform_pdf_seal import PdfFinalizationError
from app.services.event_delivery import enqueue
from app.services.token_security import active_token_user
from app.policies.api_access import is_admin

evidence_preservation_api = Blueprint(
    "evidence_preservation_api", __name__, url_prefix="/api/evidence-preservation"
)


def _admin():
    actor = active_token_user()
    if actor is None or not actor.is_active or actor.organization_id is None:
        abort(401)
    if not is_admin(actor.id):
        abort(403)
    return actor


def _retention(retention_id, actor, lock=False):
    query = EvidenceRetention.query.filter_by(
        id=retention_id, organization_id=actor.organization_id
    )
    result = (query.with_for_update() if lock else query).first()
    if result is None:
        abort(404)
    return result


def _hold_count(retention_id):
    return EvidenceLegalHold.query.filter_by(
        retention_id=retention_id, released_at=None
    ).count()


@evidence_preservation_api.route("/retentions", methods=["POST"])
@jwt_required()
def register_retention():
    actor = _admin()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"artifact_type", "artifact_id", "retention_days"}:
        abort(400)
    kind, artifact_id, days = data["artifact_type"], data["artifact_id"], data["retention_days"]
    if (kind not in ("finalized_pdf", "stamped_pdf")
            or type(artifact_id) is not int or type(days) is not int
            or not 365 <= days <= 36500):
        abort(400, description="Retention must be between one and 100 years")
    try:
        artifact = artifact_for(kind, artifact_id, actor.organization_id)
    except ValueError:
        abort(404)
    try:
        checked_digest = verify_artifact(artifact, kind, current_app.config)
    except (ValueError, OSError, IngestionError, PdfFinalizationError):
        abort(409, description="Evidence artifact failed integrity verification")
    if checked_digest != artifact.output_sha256:
        abort(409, description="Evidence artifact hash mismatch")
    existing = EvidenceRetention.query.filter_by(
        artifact_type=kind, artifact_id=artifact_id
    ).first()
    if existing is not None:
        abort(409, description="Retention cannot be overwritten or shortened")
    retention = EvidenceRetention(
        organization_id=actor.organization_id, artifact_type=kind,
        artifact_id=artifact_id, artifact_sha256=artifact.output_sha256,
        retain_until=datetime.utcnow() + timedelta(days=days),
        created_by_id=actor.id,
    )
    db.session.add(retention)
    try:
        db.session.flush()
        enqueue(
            event_type="evidence.retention.registered",
            aggregate_type="evidence_retention", aggregate_id=retention.id,
            organization_id=actor.organization_id, actor_id=actor.id,
            action="evidence.retention.registered",
            idempotency_key="evidence-retention:%s" % retention.id,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Retention record already exists")
    return jsonify({
        "id": retention.id, "artifact_type": kind, "artifact_id": artifact_id,
        **protection_status(retention, 0),
    }), 201


@evidence_preservation_api.route("/retentions/<int:retention_id>", methods=["GET"])
@jwt_required()
def get_retention(retention_id):
    actor = _admin()
    item = _retention(retention_id, actor)
    return jsonify({
        "id": item.id, "artifact_type": item.artifact_type,
        "artifact_id": item.artifact_id, "artifact_sha256": item.artifact_sha256,
        **protection_status(item, _hold_count(item.id)),
    })


@evidence_preservation_api.route("/retentions/<int:retention_id>/holds", methods=["POST"])
@jwt_required()
def place_hold(retention_id):
    actor = _admin()
    record = _retention(retention_id, actor, lock=True)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"reason"}:
        abort(400)
    reason = data["reason"]
    if (not isinstance(reason, str) or not 15 <= len(reason.strip()) <= 500
            or any(ord(ch) < 32 for ch in reason)):
        abort(400, description="Specific legal hold reason required")
    hold = EvidenceLegalHold(
        retention_id=record.id, organization_id=actor.organization_id,
        reason=reason.strip(), requested_by_id=actor.id,
    )
    db.session.add(hold)
    db.session.flush()
    enqueue(
        event_type="evidence.hold.placed", aggregate_type="evidence_hold",
        aggregate_id=hold.id, organization_id=actor.organization_id,
        actor_id=actor.id, action="evidence.hold.placed",
        idempotency_key="evidence-hold:%s" % hold.id,
    )
    db.session.commit()
    return jsonify({"id": hold.id, "retention_id": record.id, "active": True}), 201


@evidence_preservation_api.route("/holds/<int:hold_id>/release", methods=["POST"])
@jwt_required()
def release_hold(hold_id):
    actor = _admin()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"reason"}:
        abort(400, description="Documented hold release reason required")
    reason = data["reason"]
    if (not isinstance(reason, str) or not 15 <= len(reason.strip()) <= 500
            or any(ord(ch) < 32 for ch in reason)):
        abort(400, description="Specific legal hold release reason required")
    hold = EvidenceLegalHold.query.filter_by(
        id=hold_id, organization_id=actor.organization_id
    ).with_for_update().first()
    if hold is None:
        abort(404)
    if hold.released_at is not None:
        abort(409, description="Hold already released")
    if actor.id == hold.requested_by_id:
        abort(403, description="Independent administrator required")
    hold.released_by_id = actor.id
    hold.released_at = datetime.utcnow()
    hold.release_reason = reason.strip()
    enqueue(
        event_type="evidence.hold.released", aggregate_type="evidence_hold",
        aggregate_id=hold.id, organization_id=actor.organization_id,
        actor_id=actor.id, action="evidence.hold.released",
        idempotency_key="evidence-hold-release:%s" % hold.id,
    )
    db.session.commit()
    return jsonify({"id": hold.id, "active": False})


@evidence_preservation_api.route("/retentions/<int:retention_id>/checkpoints", methods=["GET"])
@jwt_required()
def list_checkpoints(retention_id):
    actor = _admin()
    item = _retention(retention_id, actor)
    rows = EvidenceCheckpoint.query.filter_by(
        retention_id=item.id, organization_id=actor.organization_id
    ).order_by(EvidenceCheckpoint.id.desc()).limit(100).all()
    result = jsonify([{
        "id": row.id, "key_id": row.key_id,
        "payload": row.payload, "signature": row.signature,
        "algorithm": row.algorithm,
    } for row in rows])
    result.headers["Cache-Control"] = "private, no-store"
    return result


@evidence_preservation_api.route("/retentions/<int:retention_id>/holds", methods=["GET"])
@jwt_required()
def list_holds(retention_id):
    actor = _admin()
    item = _retention(retention_id, actor)
    holds = EvidenceLegalHold.query.filter_by(
        retention_id=item.id, organization_id=actor.organization_id
    ).order_by(EvidenceLegalHold.id.desc()).limit(100).all()
    response = jsonify([{
        "id": hold.id, "reason": hold.reason,
        "requested_by_id": hold.requested_by_id,
        "requested_at": hold.requested_at.isoformat() if hold.requested_at else None,
        "released_by_id": hold.released_by_id,
        "released_at": hold.released_at.isoformat() if hold.released_at else None,
        "release_reason": hold.release_reason,
        "active": hold.released_at is None,
    } for hold in holds])
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/checkpoints/<int:checkpoint_id>/export", methods=["GET"])
@jwt_required()
def export_checkpoint(checkpoint_id):
    actor = _admin()
    row = EvidenceCheckpoint.query.filter_by(
        id=checkpoint_id, organization_id=actor.organization_id
    ).first()
    if row is None:
        abort(404)
    retention = _retention(row.retention_id, actor)
    if retention.organization_id != row.organization_id:
        abort(409)
    from app.services.evidence_preservation import (
        verify_checkpoint, trusted_checkpoint_key, checkpoint_payload,
    )
    signed = {
        "payload": row.payload, "algorithm": row.algorithm,
        "key_id": row.key_id, "signature": row.signature,
    }
    try:
        trusted = trusted_checkpoint_key(current_app.config, row.key_id)
        valid = (
            row.payload == checkpoint_payload(
                retention, row.operator_id, row.created_at
            )
            and verify_checkpoint(signed, trusted)
        )
    except (ValueError, OSError, TypeError, KeyError):
        valid = False
    if not valid:
        abort(409, description="Checkpoint signature or provenance invalid")
    response = jsonify(signed)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/retentions/<int:retention_id>/timestamps", methods=["GET"])
@jwt_required()
def list_timestamps(retention_id):
    actor = _admin()
    retention = _retention(retention_id, actor)
    from app.models.evidence_timestamp import EvidenceTimestamp
    records = EvidenceTimestamp.query.filter_by(
        retention_id=retention.id, organization_id=actor.organization_id,
    ).order_by(EvidenceTimestamp.id.desc()).limit(100).all()
    response = jsonify([{
        "id": record.id,
        "artifact_sha256": record.artifact_sha256,
        "tsa_certificate_sha256": record.tsa_certificate_sha256,
        "token_sha256": record.token_sha256,
        "gen_time": record.gen_time.isoformat() + "Z",
    } for record in records])
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/timestamps/<int:timestamp_id>/export", methods=["GET"])
@jwt_required()
def export_timestamp(timestamp_id):
    actor = _admin()
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.services.rfc3161_timestamp import decode_token, verify_timestamp, TimestampError
    item = EvidenceTimestamp.query.filter_by(
        id=timestamp_id, organization_id=actor.organization_id,
    ).first()
    if item is None:
        abort(404)
    retention = _retention(item.retention_id, actor)
    if item.artifact_sha256 != retention.artifact_sha256:
        abort(409, description="Timestamp retention binding mismatch")
    try:
        raw = decode_token(item.token_der_b64)
        verified = verify_timestamp(raw, item.artifact_sha256, current_app.config)
        if (verified["token_sha256"] != item.token_sha256
                or verified["tsa_certificate_sha256"] != item.tsa_certificate_sha256
                or verified["gen_time"] != item.gen_time):
            raise TimestampError("Retained timestamp changed")
    except (TimestampError, OSError):
        abort(409, description="Timestamp trust verification failed")
    from flask import Response
    response = Response(
        raw, mimetype="application/timestamp-reply",
        headers={"Content-Disposition": 'attachment; filename="trustseal-timestamp-%s.tsr"' % item.id},
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@evidence_preservation_api.route("/timestamps/<int:timestamp_id>/revocations", methods=["GET"])
@jwt_required()
def list_revocations(timestamp_id):
    actor = _admin()
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.certificate_revocation import CertificateRevocationEvidence
    token = EvidenceTimestamp.query.filter_by(
        id=timestamp_id, organization_id=actor.organization_id
    ).first()
    if token is None:
        abort(404)
    _retention(token.retention_id, actor)
    items = CertificateRevocationEvidence.query.filter_by(
        timestamp_id=token.id, organization_id=actor.organization_id
    ).order_by(CertificateRevocationEvidence.id.desc()).limit(100).all()
    response = jsonify([{
        "id": item.id, "status": item.status,
        "subject_certificate_sha256": item.subject_certificate_sha256,
        "issuer_certificate_sha256": item.issuer_certificate_sha256,
        "crl_sha256": item.crl_sha256,
        "this_update": item.this_update.isoformat() + "Z",
        "next_update": item.next_update.isoformat() + "Z",
        "checked_at": item.checked_at.isoformat() + "Z",
        "assurance": "historical_signed_crl_observation_not_ocsp",
    } for item in items])
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/revocations/<int:revocation_id>/export", methods=["GET"])
@jwt_required()
def export_revocation(revocation_id):
    actor = _admin()
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.certificate_revocation import CertificateRevocationEvidence
    from app.services.certificate_revocation import (
        RevocationEvidenceError, verify_snapshot, _read_pem,
    )
    item = CertificateRevocationEvidence.query.filter_by(
        id=revocation_id, organization_id=actor.organization_id,
    ).first()
    if item is None:
        abort(404)
    timestamp = EvidenceTimestamp.query.filter_by(
        id=item.timestamp_id, organization_id=actor.organization_id,
    ).first()
    if timestamp is None:
        abort(409, description="CRL timestamp reference invalid")
    _retention(timestamp.retention_id, actor)
    try:
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Trusted TSA root")
        result = verify_snapshot(item, root)
        if (result["subject_certificate_sha256"] != timestamp.tsa_certificate_sha256
                or item.organization_id != timestamp.organization_id):
            raise RevocationEvidenceError("CRL not bound to retained TSA")
    except (RevocationEvidenceError, OSError, ValueError):
        abort(409, description="CRL evidence verification failed")
    response = jsonify({
        "id": item.id, "timestamp_id": item.timestamp_id,
        "subject_certificate_der_b64": item.subject_der_b64,
        "issuer_certificate_der_b64": item.issuer_der_b64,
        "crl_der_b64": item.crl_der_b64,
        "crl_sha256": item.crl_sha256,
        "status": item.status,
        "checked_at": item.checked_at.isoformat() + "Z",
        "assurance": "historical_signed_crl_observation_not_ocsp",
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/timestamps/<int:timestamp_id>/ocsp", methods=["GET"])
@jwt_required()
def list_ocsp(timestamp_id):
    actor = _admin()
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.models.ocsp_evidence import OcspEvidence
    token = EvidenceTimestamp.query.filter_by(
        id=timestamp_id, organization_id=actor.organization_id
    ).first()
    if token is None:
        abort(404)
    _retention(token.retention_id, actor)
    records = OcspEvidence.query.filter_by(
        timestamp_id=token.id, organization_id=actor.organization_id
    ).order_by(OcspEvidence.id.desc()).limit(100).all()
    response = jsonify([{
        "id": row.id, "response_sha256": row.response_sha256,
        "subject_certificate_sha256": row.subject_certificate_sha256,
        "issuer_certificate_sha256": row.issuer_certificate_sha256,
        "status": row.status,
        "produced_at": row.produced_at.isoformat() + "Z",
        "this_update": row.this_update.isoformat() + "Z",
        "next_update": row.next_update.isoformat() + "Z",
        "checked_at": row.checked_at.isoformat() + "Z",
        "assurance": "historical_issuer_signed_ocsp_observation",
    } for row in records])
    response.headers["Cache-Control"] = "private, no-store"
    return response


@evidence_preservation_api.route("/ocsp/<int:evidence_id>/export", methods=["GET"])
@jwt_required()
def export_ocsp(evidence_id):
    actor = _admin()
    from app.models.ocsp_evidence import OcspEvidence
    from app.models.evidence_timestamp import EvidenceTimestamp
    from app.services.ocsp_evidence import verify_ocsp_snapshot, OcspEvidenceError
    from app.services.certificate_revocation import _read_pem
    record = OcspEvidence.query.filter_by(
        id=evidence_id, organization_id=actor.organization_id
    ).first()
    if record is None:
        abort(404)
    token = EvidenceTimestamp.query.filter_by(
        id=record.timestamp_id, organization_id=actor.organization_id
    ).first()
    if token is None:
        abort(409, description="OCSP evidence has no retained timestamp")
    _retention(token.retention_id, actor)
    try:
        root = _read_pem(current_app.config.get("RFC3161_TRUST_ROOT_PEM"), "Approved root")
        checked = verify_ocsp_snapshot(record, root)
        from app.services.rfc3161_timestamp import decode_token, verify_timestamp
        source = verify_timestamp(
            decode_token(token.token_der_b64), token.artifact_sha256,
            current_app.config,
        )
        if (checked["subject_certificate_sha256"] != token.tsa_certificate_sha256
                or source["tsa_certificate_sha256"] != token.tsa_certificate_sha256
                or source["token_sha256"] != token.token_sha256
                or source["gen_time"] != token.gen_time):
            raise OcspEvidenceError("OCSP evidence not bound to an intact TSA timestamp")
    except (OcspEvidenceError, ValueError, OSError):
        abort(409, description="OCSP response validation failed")
    response = jsonify({
        "timestamp_id": token.id,
        "id": record.id,
        "response_der_b64": record.response_der_b64,
        "responder_certificate_sha256": record.responder_certificate_sha256,
        "responder_certificate_der_b64": record.responder_der_b64,
        "subject_certificate_der_b64": record.subject_der_b64,
        "issuer_certificate_der_b64": record.issuer_der_b64,
        "status": record.status,
        "response_sha256": record.response_sha256,
        "checked_at": record.checked_at.isoformat() + "Z",
        "assurance": "historical_issuer_signed_ocsp_observation",
    })
    response.headers["Cache-Control"] = "private, no-store"
    return response
