from flask import request, jsonify
from app.blueprints.estamp import estamp_bp
from app.extensions import db
from app.models.estamp import DigitalStamp

@estamp_bp.route('/api/stamps', methods=['GET'])
def list_stamps():
    stamps = DigitalStamp.query.all()
    return jsonify([{
        "id": s.id,
        "name": s.name,
        "image_path": s.image_path,
        "is_active": s.is_active,
        "organization_id": s.organization_id
    } for s in stamps])

@estamp_bp.route('/api/stamps/<int:stamp_id>', methods=['GET'])
def get_stamp(stamp_id):
    stamp = DigitalStamp.query.get_or_404(stamp_id)
    return jsonify({
        "id": stamp.id,
        "name": stamp.name,
        "image_path": stamp.image_path,
        "is_active": stamp.is_active,
        "organization_id": stamp.organization_id
    })

@estamp_bp.route('/api/stamps', methods=['POST'])
def create_stamp():
    data = request.get_json()
    stamp = DigitalStamp(**data)
    db.session.add(stamp)
    db.session.commit()
    return jsonify({"message": "Digital stamp created", "id": stamp.id}), 201

@estamp_bp.route('/api/stamps/<int:stamp_id>', methods=['PUT'])
def update_stamp(stamp_id):
    stamp = DigitalStamp.query.get_or_404(stamp_id)
    data = request.get_json()
    for field in ['name', 'image_path', 'is_active']:
        setattr(stamp, field, data.get(field, getattr(stamp, field)))
    db.session.commit()
    return jsonify({"message": "Stamp updated", "id": stamp.id})

@estamp_bp.route('/api/stamps/<int:stamp_id>', methods=['DELETE'])
def delete_stamp(stamp_id):
    stamp = DigitalStamp.query.get_or_404(stamp_id)
    db.session.delete(stamp)
    db.session.commit()
    return jsonify({"message": "Stamp deleted", "id": stamp.id})