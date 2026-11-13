from flask import request, jsonify
from app.blueprints.estamp import estamp_bp
from app.extensions import db
from app.models.estamp import StampTemplate

@estamp_bp.route('/api/templates', methods=['GET'])
def list_templates():
    templates = StampTemplate.query.all()
    return jsonify([{
        "id": t.id,
        "name": t.name,
        "is_active": t.is_active,
        "is_system": t.is_system,
        "preview_path": t.preview_path
    } for t in templates])

@estamp_bp.route('/api/templates', methods=['POST'])
def create_template():
    data = request.get_json()
    template = StampTemplate(**data)
    db.session.add(template)
    db.session.commit()
    return jsonify({"message": "Stamp template created", "id": template.id}), 201