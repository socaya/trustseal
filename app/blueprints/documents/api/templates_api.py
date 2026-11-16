"""Document template publication API (Phase E1).

Separate from the legacy ``document_template_api`` blueprint which
remains for backward-compatible CRUD. The new blueprint enforces the
``draft → published → archived`` state machine and requires
separation-of-duties on ``publish`` so a template's author cannot
also certify it.

Routes:

* ``POST /api/document-templates`` — create (starts in draft).
* ``GET /api/document-templates`` — list the caller's tenant.
* ``GET /api/document-templates/<id>`` — read.
* ``POST /api/document-templates/<id>/versions`` — append a new
  revision; refuses on archived; refuses on published without
  ``start_revision`` first.
* ``POST /api/document-templates/<id>/start-revision`` — move
  published → draft so a new version can land.
* ``POST /api/document-templates/<id>/publish`` — flip to
  published; requester ≠ most recent version author.
* ``POST /api/document-templates/<id>/archive`` — final state.
* ``GET /api/document-templates/<id>/versions`` — history.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.documents.document_template import (
    DocumentTemplate,
    DocumentTemplateVersion,
)
from app.policies.separation_of_duties import (
    SeparationOfDutiesViolation,
    assert_distinct,
)
from app.services import templates as template_service
from app.services.token_security import active_token_user

templates_api = Blueprint(
    "templates_api", __name__, url_prefix="/api/document-templates"
)


def _actor():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    return user


def _owned(template_id, user):
    row = DocumentTemplate.query.filter_by(
        id=template_id, organization_id=user.organization_id
    ).first()
    if row is None:
        abort(404)
    return row


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="json_object_required")
    return data


@templates_api.route("", methods=["POST"])
@jwt_required()
def create_template():
    user = _actor()
    data = _payload()
    try:
        row = template_service.create_template(
            organization_id=user.organization_id,
            name=str(data.get("name", "")),
            content=str(data.get("content", "")),
            description=data.get("description"),
            created_by_id=user.id,
        )
    except template_service.TemplateError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(row.to_dict()), 201


@templates_api.route("", methods=["GET"])
@jwt_required()
def list_templates():
    user = _actor()
    rows = (
        DocumentTemplate.query.filter_by(
            organization_id=user.organization_id
        )
        .order_by(DocumentTemplate.id.desc())
        .all()
    )
    return jsonify(templates=[r.to_dict() for r in rows]), 200


@templates_api.route("/<int:template_id>", methods=["GET"])
@jwt_required()
def get_template(template_id):
    user = _actor()
    return jsonify(_owned(template_id, user).to_dict()), 200


@templates_api.route("/<int:template_id>/versions", methods=["POST"])
@jwt_required()
def add_version(template_id):
    user = _actor()
    template = _owned(template_id, user)
    data = _payload()
    try:
        version = template_service.new_version(
            template,
            name=str(data.get("name", template.name)),
            content=str(data.get("content", "")),
            description=data.get("description"),
            author_id=user.id,
        )
    except template_service.TemplateError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(version.to_dict()), 201


@templates_api.route("/<int:template_id>/versions", methods=["GET"])
@jwt_required()
def list_versions(template_id):
    user = _actor()
    template = _owned(template_id, user)
    rows = (
        DocumentTemplateVersion.query.filter_by(template_id=template.id)
        .order_by(DocumentTemplateVersion.revision.asc())
        .all()
    )
    return jsonify(versions=[r.to_dict() for r in rows]), 200


@templates_api.route("/<int:template_id>/start-revision", methods=["POST"])
@jwt_required()
def start_revision(template_id):
    user = _actor()
    template = _owned(template_id, user)
    try:
        template_service.start_revision(template, user.id)
    except template_service.TemplateError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(template.to_dict()), 200


@templates_api.route("/<int:template_id>/publish", methods=["POST"])
@jwt_required()
def publish_template(template_id):
    user = _actor()
    template = _owned(template_id, user)
    # Separation of duties: the user publishing must not be the
    # author of the current version. A second pair of eyes signs off
    # that the template is fit for use.
    current_version = db.session.get(
        DocumentTemplateVersion, template.current_version_id
    )
    if current_version is not None:
        try:
            assert_distinct(
                user.id,
                (current_version.created_by_id, "current_version_author"),
                action="template.publish",
                organization_id=template.organization_id,
                resource_type="document_template",
                resource_id=template.id,
            )
        except SeparationOfDutiesViolation:
            db.session.commit()
            abort(403, description="author_cannot_publish_own_template")
    try:
        template_service.publish(template, published_by_id=user.id)
    except template_service.TemplateError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(template.to_dict()), 200


@templates_api.route("/<int:template_id>/archive", methods=["POST"])
@jwt_required()
def archive_template(template_id):
    user = _actor()
    template = _owned(template_id, user)
    try:
        template_service.archive(template, archived_by_id=user.id)
    except template_service.TemplateError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(template.to_dict()), 200
