from flask import request, jsonify
from .. import users_bp
from ....extensions import db
from ....models.user import UserInvitation

@users_bp.route('/api/invitations', methods=['GET'])
def list_user_invitations():
    invitations = UserInvitation.query.order_by(UserInvitation.created_at.desc()).all()
    return jsonify([{
        "id": i.id,
        "email": i.email,
        "role": i.role,
        "organization_id": i.organization_id,
        "invited_by_id": i.invited_by_id,
        "expires_at": i.expires_at.isoformat() if i.expires_at else None,
        "created_at": i.created_at.isoformat()
    } for i in invitations])

@users_bp.route('/api/invitations', methods=['POST'])
def create_user_invitation():
    data = request.get_json()
    invitation = UserInvitation(**data)
    db.session.add(invitation)
    db.session.commit()
    return jsonify({"message": "Invitation created", "id": invitation.id}), 201
