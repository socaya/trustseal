from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_type import DocumentType
from datetime import datetime

document_type_api = Blueprint('document_type_api', __name__, url_prefix='/api/document-types')


# === LIST ALL ===
@document_type_api.route('/', methods=['GET'])
def list_types():
    types = DocumentType.query.all()
    return jsonify([t.to_dict() for t in types])


# === GET ONE ===
@document_type_api.route('/<int:id>', methods=['GET'])
def get_type(id):
    t = DocumentType.query.get_or_404(id)
    return jsonify(t.to_dict())


# === CREATE ===
@document_type_api.route('/', methods=['POST'])
def create_type():
    data = request.get_json()
    t = DocumentType(
        name=data.get("name"),
        description=data.get("description"),
        is_active=data.get("is_active", True),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"message": "Created", "id": t.id}), 201


# === UPDATE ===
@document_type_api.route('/<int:id>', methods=['PUT'])
def update_type(id):
    t = DocumentType.query.get_or_404(id)
    data = request.get_json()
    t.name = data.get("name", t.name)
    t.description = data.get("description", t.description)
    t.is_active = data.get("is_active", t.is_active)
    t.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Updated", "id": t.id})


# === DELETE ===
@document_type_api.route('/<int:id>', methods=['DELETE'])
def delete_type(id):
    t = DocumentType.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({"message": "Deleted", "id": t.id})