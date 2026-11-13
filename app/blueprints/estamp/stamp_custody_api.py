"""Governed stamp authority and dual-control approval of finalized-PDF attestations.

No generic stamp CRUD, raw image manipulation or claims of physically
impressed/sealed PDF are allowed through this API.
"""
import re
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.user import User
from app.models.pdf_finalization import FinalizedPdf
from app.models.signing_envelope import SigningEnvelope
from app.models.stamp_custody import ManagedStamp, StampApplication, StampAttestation
from app.services.token_security import active_token_user
from app.services.event_delivery import enqueue
from app.services.documents.private_storage import check_object_digest, IngestionError
from app.services.platform_pdf_seal import inspect_signed_pdf, PdfFinalizationError
from app.policies.api_access import is_admin

stamp_custody_api = Blueprint("stamp_custody_api", __name__, url_prefix="/api/stamp-custody")
CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


def actor():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    return user


def payload(required):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != required:
        abort(400, description="Unexpected stamp workflow fields")
    return data


def stamp_data(stamp):
    return {
        "id": stamp.id, "organization_id": stamp.organization_id,
        "name": stamp.name, "code": stamp.code,
        "custodian_id": stamp.custodian_id, "status": stamp.status,
        "created_by_id": stamp.created_by_id,
        "approved_by_id": stamp.approved_by_id,
        "approved_at": stamp.approved_at.isoformat() if stamp.approved_at else None,
        "revoked_at": stamp.revoked_at.isoformat() if stamp.revoked_at else None,
    }


def application_data(item):
    return {
        "id": item.id, "stamp_id": item.stamp_id,
        "finalized_pdf_id": item.finalized_pdf_id,
        "source_sha256": item.source_sha256,
        "evidence_sha256": item.evidence_sha256,
        "status": item.status, "requested_by_id": item.requested_by_id,
        "reason": item.reason, "decided_by_id": item.decided_by_id,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
        "assurance": "stamp_authorization_only_not_pdf_impression",
    }


def _stamp(stamp_id, user, lock=False):
    query = ManagedStamp.query.filter_by(id=stamp_id, organization_id=user.organization_id)
    item = (query.with_for_update() if lock else query).first()
    if item is None:
        abort(404)
    return item


def _admin(user):
    if not is_admin(user.id):
        abort(403, description="Organizational stamp approval requires administrator role")


def _verify_finalized_artifact(record):
    """Inspect only privately retained, SHA-256-verified PDF bytes."""
    try:
        path = check_object_digest(record.object_key, record.output_sha256, current_app.config)
        status = inspect_signed_pdf(
            path.read_bytes(), current_app.config,
            expected_evidence_sha256=record.evidence_sha256,
            expected_certificate_sha256=record.certificate_sha256,
        )
    except (PdfFinalizationError, IngestionError):
        abort(503, description="Finalized PDF integrity verification unavailable")
    if not status["overall_valid"]:
        abort(409, description="Finalized PDF failed certificate verification")


@stamp_custody_api.route("", methods=["POST"])
@jwt_required()
def request_stamp_registration():
    user = actor()
    data = payload({"code", "name", "custodian_id"})
    code, name, custodian_id = data["code"], data["name"], data["custodian_id"]
    if (not isinstance(code, str) or not CODE.fullmatch(code)
            or not isinstance(name, str) or not 3 <= len(name.strip()) <= 120
            or type(custodian_id) is not int):
        abort(400, description="Invalid stamp identity")
    custodian = db.session.get(User, custodian_id)
    if custodian is None or not custodian.is_active or custodian.organization_id != user.organization_id:
        abort(404, description="Active custodian not found")
    item = ManagedStamp(
        organization_id=user.organization_id, code=code, name=name.strip(),
        custodian_id=custodian.id, created_by_id=user.id, status="pending",
    )
    db.session.add(item)
    try:
        db.session.flush()
        enqueue(
            event_type="stamp.registration.requested", aggregate_type="stamp",
            aggregate_id=item.id, organization_id=user.organization_id,
            actor_id=user.id, action="stamp.registration.requested",
            idempotency_key="stamp-registration:%s" % item.id,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Stamp code already registered")
    return jsonify(stamp_data(item)), 201


@stamp_custody_api.route("", methods=["GET"])
@jwt_required()
def list_stamps():
    user = actor()
    query = ManagedStamp.query.filter_by(organization_id=user.organization_id)
    if not is_admin(user.id):
        query = query.filter(
            db.or_(ManagedStamp.custodian_id == user.id, ManagedStamp.created_by_id == user.id)
        )
    return jsonify([stamp_data(s) for s in query.order_by(ManagedStamp.id.desc()).limit(100).all()])


@stamp_custody_api.route("/<int:stamp_id>/approve", methods=["POST"])
@jwt_required()
def approve_registration(stamp_id):
    user = actor()
    _admin(user)
    item = _stamp(stamp_id, user, lock=True)
    if item.status != "pending":
        abort(409, description="Stamp is not pending")
    if user.id in (item.created_by_id, item.custodian_id):
        abort(403, description="Stamp approval requires independent administrator")
    custodian = db.session.get(User, item.custodian_id)
    if custodian is None or not custodian.is_active or custodian.organization_id != user.organization_id:
        abort(409, description="Custodian is unavailable")
    item.status = "active"
    item.approved_by_id = user.id
    item.approved_at = datetime.utcnow()
    enqueue(
        event_type="stamp.registration.approved", aggregate_type="stamp",
        aggregate_id=item.id, organization_id=user.organization_id,
        actor_id=user.id, action="stamp.registration.approved",
        idempotency_key="stamp-activated:%s" % item.id,
    )
    db.session.commit()
    return jsonify(stamp_data(item))


@stamp_custody_api.route("/<int:stamp_id>/revoke", methods=["POST"])
@jwt_required()
def revoke_registration(stamp_id):
    user = actor()
    _admin(user)
    item = _stamp(stamp_id, user, lock=True)
    if item.status == "revoked":
        return jsonify(stamp_data(item))
    if user.id == item.custodian_id:
        abort(403, description="Custodian cannot revoke own approval record")
    item.status = "revoked"
    item.revoked_by_id = user.id
    item.revoked_at = datetime.utcnow()
    enqueue(
        event_type="stamp.registration.revoked", aggregate_type="stamp",
        aggregate_id=item.id, organization_id=user.organization_id,
        actor_id=user.id, action="stamp.registration.revoked",
        idempotency_key="stamp-revoked:%s" % item.id,
    )
    db.session.commit()
    return jsonify(stamp_data(item))


@stamp_custody_api.route("/<int:stamp_id>/applications", methods=["POST"])
@jwt_required()
def request_stamp_application(stamp_id):
    user = actor()
    item = _stamp(stamp_id, user, lock=True)
    if item.status != "active" or item.custodian_id != user.id:
        abort(403, description="Only active stamp custodian can request use")
    data = payload({"finalized_pdf_id", "reason"})
    pdf_id, reason = data["finalized_pdf_id"], data["reason"]
    if type(pdf_id) is not int or not isinstance(reason, str) or not 8 <= len(reason.strip()) <= 240:
        abort(400, description="Document and purpose are required")
    pdf = FinalizedPdf.query.filter_by(
        id=pdf_id, organization_id=user.organization_id
    ).first()
    if pdf is None:
        abort(404)
    _verify_finalized_artifact(pdf)
    application = StampApplication(
        stamp_id=item.id, organization_id=user.organization_id,
        finalized_pdf_id=pdf.id, source_sha256=pdf.output_sha256,
        evidence_sha256=pdf.evidence_sha256, requested_by_id=user.id,
        reason=reason.strip(), status="pending",
    )
    db.session.add(application)
    try:
        db.session.flush()
        enqueue(
            event_type="stamp.use.requested", aggregate_type="stamp_application",
            aggregate_id=application.id, organization_id=user.organization_id,
            actor_id=user.id, action="stamp.use.requested",
            idempotency_key="stamp-use-requested:%s" % application.id,
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, description="Stamp already requested for this PDF")
    return jsonify(application_data(application)), 201


@stamp_custody_api.route("/applications/<int:application_id>", methods=["GET"])
@jwt_required()
def get_stamp_application(application_id):
    user = actor()
    application = StampApplication.query.filter_by(
        id=application_id, organization_id=user.organization_id
    ).first()
    if application is None:
        abort(404)
    if not is_admin(user.id) and application.requested_by_id != user.id:
        abort(404)
    return jsonify(application_data(application))


@stamp_custody_api.route("/applications/<int:application_id>/decision", methods=["POST"])
@jwt_required()
def decide_stamp_application(application_id):
    user = actor()
    _admin(user)
    decision = payload({"decision"})["decision"]
    if type(decision) is not str or decision not in ("approved", "rejected"):
        abort(400, description="Decision must be approved or rejected")
    item = StampApplication.query.filter_by(
        id=application_id, organization_id=user.organization_id
    ).with_for_update().first()
    if item is None:
        abort(404)
    if item.status != "pending":
        abort(409, description="Stamp request already decided")
    stamp = _stamp(item.stamp_id, user, lock=True)
    if user.id in (item.requested_by_id, stamp.custodian_id):
        abort(403, description="Independent reviewer required")
    if stamp.status != "active":
        abort(409, description="Stamp authority is inactive")
    pdf = db.session.get(FinalizedPdf, item.finalized_pdf_id)
    if (pdf is None or pdf.organization_id != item.organization_id
            or pdf.output_sha256 != item.source_sha256
            or pdf.evidence_sha256 != item.evidence_sha256):
        abort(409, description="Referenced finalized PDF has changed")
    if decision == "approved":
        _verify_finalized_artifact(pdf)
    item.status = decision
    item.decided_by_id = user.id
    item.decided_at = datetime.utcnow()
    enqueue(
        event_type="stamp.use." + decision, aggregate_type="stamp_application",
        aggregate_id=item.id, organization_id=user.organization_id,
        actor_id=user.id, action="stamp.use." + decision,
        idempotency_key="stamp-use-decision:%s" % item.id,
    )
    db.session.commit()
    return jsonify(application_data(item))
