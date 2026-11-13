from flask import request, jsonify
from .. import system_bp
from ....extensions import db
from ....models.system import RolePermission, Permission

@system_bp.route('/api/roles/<int:role_id>/permissions', methods=['POST'])
def assign_permission_to_role(role_id):
    data = request.get_json()
    permission_id = data['permission_id']
    if RolePermission.query.filter_by(role_id=role_id, permission_id=permission_id).first():
        return jsonify({"message": "Permission already assigned"}), 400
    assignment = RolePermission(role_id=role_id, permission_id=permission_id)
    db.session.add(assignment)
    db.session.commit()
    return jsonify({"message": "Permission assigned to role"}), 201

@system_bp.route('/api/roles/<int:role_id>/permissions', methods=['GET'])
def get_role_permissions(role_id):
    permissions = db.session.query(Permission).join(RolePermission).filter(RolePermission.role_id == role_id).all()
    return jsonify([{"id": p.id, "name": p.name, "description": p.description} for p in permissions])
