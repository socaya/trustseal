from flask import request, jsonify
from .. import system_bp
from ....extensions import db
from ....models.system import UserRole, Role

@system_bp.route('/api/users/<int:user_id>/roles', methods=['POST'])
def assign_role_to_user(user_id):
    data = request.get_json()
    role_id = data['role_id']
    if UserRole.query.filter_by(user_id=user_id, role_id=role_id).first():
        return jsonify({"message": "User already has this role"}), 400
    assignment = UserRole(user_id=user_id, role_id=role_id)
    db.session.add(assignment)
    db.session.commit()
    return jsonify({"message": "Role assigned to user"}), 201

@system_bp.route('/api/users/<int:user_id>/roles', methods=['GET'])
def get_user_roles(user_id):
    roles = db.session.query(Role).join(UserRole).filter(UserRole.user_id == user_id).all()
    return jsonify([{"id": r.id, "name": r.name, "description": r.description} for r in roles])