from flask import request, jsonify
from .. import system_bp
from ....extensions import db
from ....models.system import Role

@system_bp.route('/api/roles', methods=['GET'])
def list_roles():
    roles = Role.query.all()
    return jsonify([{"id": r.id, "name": r.name, "description": r.description} for r in roles])

@system_bp.route('/api/roles', methods=['POST'])
def create_role():
    data = request.get_json()
    role = Role(name=data['name'], description=data.get('description'))
    db.session.add(role)
    db.session.commit()
    return jsonify({"message": "Role created", "id": role.id}), 201