from flask import request, jsonify
from flask_jwt_extended import jwt_required
from .. import organizations_bp
from ....models.organization import Organization
from ....extensions import db

@organizations_bp.route('/api/organizations', methods=['GET'], endpoint='all_organizations')
@jwt_required()
def all_organizations():
    orgs = Organization.query.all()
    return jsonify([{
        "id": o.id,
        "name": o.name,
        "email": o.email,
        "type": o.type,
        "is_verified": o.is_verified
    } for o in orgs])

@organizations_bp.route('/api/organizations/<int:org_id>', methods=['GET'])
@jwt_required()
def get_organization(org_id):
    o = Organization.query.get_or_404(org_id)
    return jsonify({
        "id": o.id,
        "name": o.name,
        "email": o.email,
        "country": o.country,
        "website": o.website,
        "type": o.type,
        "is_verified": o.is_verified,
        "verified_at": o.verified_at
    })

@organizations_bp.route('/api/organizations', methods=['POST'])
@jwt_required()
def create_organization():
    data = request.get_json()
    org = Organization(
        name=data['name'],
        legal_name=data.get('legal_name'),
        registration_number=data.get('registration_number'),
        email=data.get('email'),
        phone=data.get('phone'),
        website=data.get('website'),
        country=data.get('country'),
        type=data.get('type', 'company'),
        is_verified=data.get('is_verified', False)
    )
    db.session.add(org)
    db.session.commit()
    return jsonify({"message": "Organization created", "id": org.id}), 201

@organizations_bp.route('/api/organizations/<int:org_id>', methods=['PUT'])
@jwt_required()
def update_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    data = request.get_json()
    for field in ['name', 'email', 'website', 'phone', 'country', 'type', 'is_verified']:
        setattr(org, field, data.get(field, getattr(org, field)))
    db.session.commit()
    return jsonify({"message": "Organization updated", "id": org.id})

@organizations_bp.route('/api/organizations/<int:org_id>', methods=['DELETE'])
@jwt_required()
def delete_organization(org_id):
    org = Organization.query.get_or_404(org_id)
    db.session.delete(org)
    db.session.commit()
    return jsonify({"message": "Organization deleted", "id": org.id})