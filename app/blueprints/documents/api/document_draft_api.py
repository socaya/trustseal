from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_draft import DocumentDraft

document_draft_api = Blueprint('document_draft_api', __name__, url_prefix='/api/document-drafts')


# === LIST ALL DRAFTS ===
@document_draft_api.route('/', methods=['GET'])
def list_drafts():
    drafts = DocumentDraft.query.order_by(DocumentDraft.created_at.desc()).all()
    return jsonify([draft.to_dict() for draft in drafts])


# === GET A SPECIFIC DRAFT ===
@document_draft_api.route('/<int:id>', methods=['GET'])
def get_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    return jsonify(draft.to_dict())


# === CREATE A NEW DRAFT ===
@document_draft_api.route('/', methods=['POST'])
def create_draft():
    data = request.get_json()
    draft = DocumentDraft(**data)
    db.session.add(draft)
    db.session.commit()
    return jsonify({"message": "Draft created", "id": draft.id}), 201


# === UPDATE EXISTING DRAFT ===
@document_draft_api.route('/<int:id>', methods=['PUT'])
def update_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    data = request.get_json()
    for key, value in data.items():
        setattr(draft, key, value)
    db.session.commit()
    return jsonify({"message": "Draft updated", "id": draft.id})


# === DELETE DRAFT ===
@document_draft_api.route('/<int:id>', methods=['DELETE'])
def delete_draft(id):
    draft = DocumentDraft.query.get_or_404(id)
    db.session.delete(draft)
    db.session.commit()
    return jsonify({"message": "Draft deleted", "id": id})