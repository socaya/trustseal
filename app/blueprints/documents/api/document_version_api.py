from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_version import DocumentVersion
from datetime import datetime

document_version_api = Blueprint('document_version_api', __name__, url_prefix='/api/document-versions')


# === LIST ===
@document_version_api.route('/', methods=['GET'])
def list_document_versions():
    items = DocumentVersion.query.all()
    return jsonify([i.to_dict() for i in items])


# === GET ONE ===
@document_version_api.route('/<int:item_id>', methods=['GET'])
def get_document_version(item_id):
    item = DocumentVersion.query.get_or_404(item_id)
    return jsonify(item.to_dict())


# === CREATE ===
@document_version_api.route('/', methods=['POST'])
def create_document_version():
    data = request.get_json()
    item = DocumentVersion(
        version_number=data.get("version_number"),
        file_name=data.get("file_name"),
        file_path=data.get("file_path"),
        created_by_id=data.get("created_by_id"),
        document_id=data.get("document_id"),
        created_at=datetime.utcnow()
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "DocumentVersion created", "id": item.id}), 201


# === UPDATE ===
@document_version_api.route('/<int:item_id>', methods=['PUT'])
def update_document_version(item_id):
    item = DocumentVersion.query.get_or_404(item_id)
    data = request.get_json()
    item.version_number = data.get("version_number", item.version_number)
    item.file_name = data.get("file_name", item.file_name)
    item.file_path = data.get("file_path", item.file_path)
    item.created_by_id = data.get("created_by_id", item.created_by_id)
    item.document_id = data.get("document_id", item.document_id)
    db.session.commit()
    return jsonify({"message": "DocumentVersion updated", "id": item.id})


# === DELETE ===
@document_version_api.route('/<int:item_id>', methods=['DELETE'])
def delete_document_version(item_id):
    item = DocumentVersion.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "DocumentVersion deleted", "id": item.id})