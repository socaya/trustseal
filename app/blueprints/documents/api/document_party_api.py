from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_party import DocumentParty

document_party_api = Blueprint('document_party_api', __name__, url_prefix='/api/document-parties')


# === LIST ===
@document_party_api.route('/', methods=['GET'])
def list_document_parties():
    items = DocumentParty.query.order_by(DocumentParty.id.desc()).all()
    return jsonify([item.to_dict() for item in items])


# === GET ONE ===
@document_party_api.route('/<int:item_id>', methods=['GET'])
def get_document_party(item_id):
    item = DocumentParty.query.get_or_404(item_id)
    return jsonify(item.to_dict())


# === CREATE ===
@document_party_api.route('/', methods=['POST'])
def create_document_party():
    data = request.get_json()
    item = DocumentParty(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "DocumentParty created", "id": item.id}), 201


# === UPDATE ===
@document_party_api.route('/<int:item_id>', methods=['PUT'])
def update_document_party(item_id):
    item = DocumentParty.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "DocumentParty updated", "id": item.id})


# === DELETE ===
@document_party_api.route('/<int:item_id>', methods=['DELETE'])
def delete_document_party(item_id):
    item = DocumentParty.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "DocumentParty deleted", "id": item.id})