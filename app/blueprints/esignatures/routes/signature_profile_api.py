
from flask import request, jsonify
from .. import esignatures_bp
from ....extensions import db
from ....models.esignature import SignatureProfile

@esignatures_bp.route('/api/signature-profiles', methods=['GET'])
def list_signature_profiles():
    items = SignatureProfile.query.all()
    return jsonify([{"id": i.id} for i in items])

@esignatures_bp.route('/api/signature-profiles/<int:item_id>', methods=['GET'])
def get_signature_profile(item_id):
    item = SignatureProfile.query.get_or_404(item_id)
    return jsonify({ "id": item.id })

@esignatures_bp.route('/api/signature-profiles', methods=['POST'])
def create_signature_profile():
    data = request.get_json()
    item = SignatureProfile(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "SignatureProfile created", "id": item.id}), 201

@esignatures_bp.route('/api/signature-profiles/<int:item_id>', methods=['PUT'])
def update_signature_profile(item_id):
    item = SignatureProfile.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "SignatureProfile updated", "id": item.id})

@esignatures_bp.route('/api/signature-profiles/<int:item_id>', methods=['DELETE'])
def delete_signature_profile(item_id):
    item = SignatureProfile.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "SignatureProfile deleted", "id": item.id})
