from flask import request, jsonify
from .. import system_bp
from ....extensions import db
from ....models.system import SystemSettings

@system_bp.route('/api/settings', methods=['GET'])
def list_settings():
    settings = SystemSettings.query.all()
    return jsonify([{
        "id": s.id,
        "key": str(s.key),
        "value": s.value,
        "description": s.description,
        "is_public": s.is_public
    } for s in settings])

@system_bp.route('/api/settings/<string:key>', methods=['GET'])
def get_setting_by_key(key):
    setting = SystemSettings.query.filter_by(key=key).first_or_404()
    return jsonify({
        "id": setting.id,
        "key": str(setting.key),
        "value": setting.value,
        "description": setting.description,
        "is_public": setting.is_public
    })

@system_bp.route('/api/settings/<string:key>', methods=['PUT'])
def update_setting(key):
    setting = SystemSettings.query.filter_by(key=key).first_or_404()
    data = request.get_json()
    setting.value = data.get('value', setting.value)
    db.session.commit()
    return jsonify({"message": "Setting updated", "key": str(setting.key)})