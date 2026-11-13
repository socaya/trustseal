from flask import request, jsonify, Blueprint, current_app
from ....extensions import db, jwt
from ....models.user import User
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt
)

auth_api = Blueprint('auth_api', __name__, url_prefix='/api/auth')

REVOKED_TOKENS = set()

@auth_api.route('/register', methods=['POST'])
def register_api():
    data = request.get_json()
    current_app.logger.debug(f"📩 Register request: {data}")

    if not data:
        return jsonify({"error": "No input data provided"}), 400

    if User.query.filter((User.email == data['email']) | (User.username == data['username'])).first():
        return jsonify({"error": "Email or username already exists"}), 400

    user = User(
        username=data['username'],
        email=data['email'],
        first_name=data.get('first_name'),
        last_name=data.get('last_name'),
        phone=data.get('phone')
    )
    user.set_password(data['password'])

    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "message": "Registration successful",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user_id": user.id
    })

@auth_api.route('/login', methods=['POST'])
def login_api():
    data = request.get_json()
    identifier = data.get("identifier")
    password = data.get("password")

    if not identifier or not password:
        return jsonify({"error": "Missing credentials"}), 400

    user = User.query.filter((User.email == identifier) | (User.username == identifier)).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict()
    }), 200

@auth_api.route('/logout', methods=['POST'])
@jwt_required()
def logout_api():
    jti = get_jwt()["jti"]
    REVOKED_TOKENS.add(jti)
    current_app.logger.info(f"👋 Token {jti} logged out.")
    return jsonify({"message": "Logout successful", "redirect": "/auth/login"})

@auth_api.route('/me', methods=['GET'])
@jwt_required()
def me_api():
    user_identity_str = get_jwt_identity()
    try:
        user_id = int(user_identity_str)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid token identity"}), 422

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "phone": user.phone
    })

@auth_api.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh_token():
    current_user = get_jwt_identity()
    new_token = create_access_token(identity=current_user)
    return jsonify(access_token=new_token)