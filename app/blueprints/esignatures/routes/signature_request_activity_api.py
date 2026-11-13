
from flask import request, jsonify
from .. import esignatures_bp
from ....extensions import db
from ....models.esignature import SignatureRequestActivity

@esignatures_bp.route('/api/signature-request-activitys', methods=['GET'])
def list_signature_request_activitys():
    items = SignatureRequestActivity.query.all()
    return jsonify([{"id": i.id} for i in items])

@esignatures_bp.route('/api/signature-request-activitys/<int:item_id>', methods=['GET'])
def get_signature_request_activity(item_id):
    item = SignatureRequestActivity.query.get_or_404(item_id)
    return jsonify({ "id": item.id })

@esignatures_bp.route('/api/signature-request-activitys', methods=['POST'])
def create_signature_request_activity():
    data = request.get_json()
    item = SignatureRequestActivity(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify({"message": "SignatureRequestActivity created", "id": item.id}), 201

@esignatures_bp.route('/api/signature-request-activitys/<int:item_id>', methods=['PUT'])
def update_signature_request_activity(item_id):
    item = SignatureRequestActivity.query.get_or_404(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify({"message": "SignatureRequestActivity updated", "id": item.id})

@esignatures_bp.route('/api/signature-request-activitys/<int:item_id>', methods=['DELETE'])
def delete_signature_request_activity(item_id):
    item = SignatureRequestActivity.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "SignatureRequestActivity deleted", "id": item.id})
