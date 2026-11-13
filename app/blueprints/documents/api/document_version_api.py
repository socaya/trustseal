"""Read-only, document-authorized access to legacy file version metadata.

Legacy file paths and audit attribution must never be client-editable. New
versions require validated private ingestion and immutable object manifests.
"""
from flask import Blueprint, abort, jsonify
from flask_jwt_extended import jwt_required
from app.models.documents.document_version import DocumentVersion
from app.models.documents.document import Document
from app.blueprints.documents.api.document_api import get_authorized_document_or_abort

document_version_api = Blueprint("document_version_api", __name__, url_prefix="/api/document-versions")


def _view(version):
    return {
        "id": version.id, "version_number": version.version_number,
        "file_name": version.file_name, "document_id": version.document_id,
        "created_at": version.created_at.isoformat() if version.created_at else None,
        "created_by_id": version.created_by_id,
    }


@document_version_api.route("/", methods=["GET"])
@jwt_required()
def list_document_versions():
    # Avoid a global cross-tenant enumeration. Clients must supply a document
    # identifier and pass the underlying document access policy.
    from flask import request
    raw = request.args.get("document_id")
    if raw is None or not raw.isdecimal():
        abort(400, description="document_id query parameter required")
    doc = get_authorized_document_or_abort(int(raw))
    items = DocumentVersion.query.filter_by(document_id=doc.id).order_by(
        DocumentVersion.version_number.desc()
    ).limit(100).all()
    return jsonify([_view(item) for item in items])


@document_version_api.route("/<int:item_id>", methods=["GET"])
@jwt_required()
def get_document_version(item_id):
    item = DocumentVersion.query.get_or_404(item_id)
    get_authorized_document_or_abort(item.document_id)
    return jsonify(_view(item))


@document_version_api.route("/", methods=["POST"])
@document_version_api.route("/<int:item_id>", methods=["PUT", "PATCH", "DELETE"])
@jwt_required()
def reject_legacy_version_mutation(item_id=None):
    abort(409, description="Versions require immutable, validated ingestion")
