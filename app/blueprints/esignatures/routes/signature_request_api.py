
from flask import request, jsonify
from .. import esignatures_bp
from ....extensions import db
from ....models.esignature import SignatureRequest

@esignatures_bp.route('/api/signature-requests', methods=['GET'])
def list_signature_requests():
    items = SignatureRequest.query.all()
    return jsonify([{"id": i.id} for i in items])

@esignatures_bp.route('/api/signature-requests/<int:item_id>', methods=['GET'])
def get_signature_request(item_id):
    item = SignatureRequest.query.get_or_404(item_id)
    return jsonify({ "id": item.id })

@esignatures_bp.route('/api/signature-requests', methods=['POST'])
def create_signature_request():
    data = request.get_json()
    item = SignatureRequest(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "SignatureRequest created", "id": item.id}), 201

@esignatures_bp.route('/api/signature-requests/<int:item_id>', methods=['PUT'])
def update_signature_request(item_id):
    item = SignatureRequest.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "SignatureRequest updated", "id": item.id})

@esignatures_bp.route('/api/signature-requests/<int:item_id>', methods=['DELETE'])
def delete_signature_request(item_id):
    item = SignatureRequest.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "SignatureRequest deleted", "id": item.id})
