from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_section import DocumentSection
from datetime import datetime

document_section_api = Blueprint('document_section_api', __name__, url_prefix='/api/document-sections')


# === LIST ALL ===
@document_section_api.route('/', methods=['GET'])
def list_sections():
    sections = DocumentSection.query.order_by(DocumentSection.position.asc()).all()
    return jsonify([s.to_dict() for s in sections])


# === GET ONE ===
@document_section_api.route('/<int:section_id>', methods=['GET'])
def get_section(section_id):
    section = DocumentSection.query.get_or_404(section_id)
    return jsonify(section.to_dict())


# === CREATE ===
@document_section_api.route('/', methods=['POST'])
def create_section():
    data = request.get_json()
    section = DocumentSection(
        title=data.get("title"),
        content=data.get("content"),
        position=data.get("position", 1),
        document_draft_id=data.get("document_draft_id")
    )
    db.session.add(section)
    db.session.commit()
    return jsonify({"message": "Section created", "id": section.id}), 201


# === UPDATE ===
@document_section_api.route('/<int:section_id>', methods=['PUT'])
def update_section(section_id):
    section = DocumentSection.query.get_or_404(section_id)
    data = request.get_json()

    section.title = data.get("title", section.title)
    section.content = data.get("content", section.content)
    section.position = data.get("position", section.position)
    section.document_draft_id = data.get("document_draft_id", section.document_draft_id)

    db.session.commit()
    return jsonify({"message": "Section updated", "id": section.id})


# === DELETE ===
@document_section_api.route('/<int:section_id>', methods=['DELETE'])
def delete_section(section_id):
    section = DocumentSection.query.get_or_404(section_id)
    db.session.delete(section)
    db.session.commit()
    return jsonify({"message": "Section deleted", "id": section.id})
