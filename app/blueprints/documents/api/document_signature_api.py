from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_signature import DocumentSignature

document_signature_api = Blueprint('document_signature_api', __name__, url_prefix='/api/document-signatures')

# === LIST ===
@document_signature_api.route('/', methods=['GET'])
def list_document_signatures():
    items = DocumentSignature.query.all()
    return jsonify([i.to_dict() for i in items])

# === GET ONE ===
@document_signature_api.route('/<int:item_id>', methods=['GET'])
def get_document_signature(item_id):
    item = DocumentSignature.query.get_or_404(item_id)
    return jsonify(item.to_dict())

# === CREATE ===
@document_signature_api.route('/', methods=['POST'])
def create_document_signature():
    data = request.get_json()
    item = DocumentSignature(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "DocumentSignature created", "id": item.id}), 201

# === UPDATE ===
@document_signature_api.route('/<int:item_id>', methods=['PUT'])
def update_document_signature(item_id):
    item = DocumentSignature.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "DocumentSignature updated", "id": item.id})

# === DELETE ===
@document_signature_api.route('/<int:item_id>', methods=['DELETE'])
def delete_document_signature(item_id):
    item = DocumentSignature.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "DocumentSignature deleted", "id": item.id})