from flask import request, jsonify, abort
from flask_jwt_extended import jwt_required
from .. import system_bp
from ....extensions import db
from ....models.system import UserRole, Role
from ....policies.separation_of_duties import (
    SeparationOfDutiesViolation,
    assert_distinct,
)
from ....services.token_security import active_token_user

@system_bp.route('/api/users/<int:user_id>/roles', methods=['POST'])
@jwt_required()
def assign_role_to_user(user_id):
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    # Admin cannot grant a role to themselves — the four-eyes rule
    # for privileged role elevations. The outer api_access policy
    # already guarantees the caller is an admin.
    try:
        assert_distinct(
            actor.id,
            (user_id, "subject"),
            action="role.assign",
            organization_id=actor.organization_id,
            resource_type="user_role",
            resource_id=user_id,
        )
    except SeparationOfDutiesViolation:
        db.session.commit()
        abort(
            403,
            description="role_self_grant_forbidden",
        )
    data = request.get_json(silent=True) or {}
    role_id = data.get('role_id')
    if role_id is None:
        abort(400, description="role_id_required")
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