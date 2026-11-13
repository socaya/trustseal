from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models.documents.document_template import DocumentTemplate
from datetime import datetime

document_template_api = Blueprint('document_template_api', __name__, url_prefix='/api/document-templates')

# === LIST ALL ===
@document_template_api.route('/', methods=['GET'])
def list_templates():
    templates = DocumentTemplate.query.all()
    return jsonify([t.to_dict() for t in templates])

# === GET SINGLE ===
@document_template_api.route('/<int:template_id>', methods=['GET'])
def get_template(template_id):
    template = DocumentTemplate.query.get_or_404(template_id)
    return jsonify(template.to_dict())

# === CREATE ===
@document_template_api.route('/', methods=['POST'])
def create_template():
    data = request.get_json()
    template = DocumentTemplate(
        name=data.get("name"),
        description=data.get("description"),
        content=data.get("content"),
        is_active=data.get("is_active", True),
        created_by=data.get("created_by"),
        created_at=datetime.utcnow()
    )
    db.session.add(template)
    db.session.commit()
    return jsonify({"message": "Document template created", "id": template.id}), 201

# === UPDATE ===
@document_template_api.route('/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    template = DocumentTemplate.query.get_or_404(template_id)
    data = request.get_json()
    template.name = data.get("name", template.name)
    template.description = data.get("description", template.description)
    template.content = data.get("content", template.content)
    template.is_active = data.get("is_active", template.is_active)
    db.session.commit()
    return jsonify({"message": "Document template updated", "id": template.id})

# === DELETE ===
@document_template_api.route('/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    template = DocumentTemplate.query.get_or_404(template_id)
    db.session.delete(template)
    db.session.commit()
    return jsonify({"message": "Document template deleted", "id": template.id})