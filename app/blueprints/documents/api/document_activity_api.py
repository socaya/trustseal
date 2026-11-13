from flask import request, jsonify, Blueprint
from app.extensions import db
from app.models.documents.document_activity import DocumentActivity

document_activity_api = Blueprint('document_activity_api', __name__, url_prefix='/api/document-activity')

# === LIST ===
@document_activity_api.route('/', methods=['GET'])
def list_document_activities():
    items = DocumentActivity.query.order_by(DocumentActivity.created_at.desc()).all()
    return jsonify([i.to_dict() for i in items])

# === GET ONE ===
@document_activity_api.route('/<int:item_id>', methods=['GET'])
def get_document_activity(item_id):
    item = DocumentActivity.query.get_or_404(item_id)
    return jsonify(item.to_dict())

# === CREATE ===
@document_activity_api.route('/', methods=['POST'])
def create_document_activity():
    data = request.get_json()
    item = DocumentActivity(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "DocumentActivity created", "id": item.id}), 201

# === UPDATE ===
@document_activity_api.route('/<int:item_id>', methods=['PUT'])
def update_document_activity(item_id):
    item = DocumentActivity.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        if hasattr(item, key):
            setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "DocumentActivity updated", "id": item.id})

# === DELETE ===
@document_activity_api.route('/<int:item_id>', methods=['DELETE'])
def delete_document_activity(item_id):
    item = DocumentActivity.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "DocumentActivity deleted", "id": item.id})