from flask import request, jsonify
from .. import system_bp
from ....extensions import db
from ....models.system import Permission

@system_bp.route('/api/permissions', methods=['GET'])
def list_permissions():
    permissions = Permission.query.all()
    return jsonify([{"id": p.id, "name": p.name, "description": p.description} for p in permissions])

@system_bp.route('/api/permissions', methods=['POST'])
def create_permission():
    data = request.get_json()
    permission = Permission(name=data['name'], description=data.get('description'))
    db.session.add(permission)
    db.session.commit()
    return jsonify({"message": "Permission created", "id": permission.id}), 201