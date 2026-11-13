from flask import request, jsonify
from flask_jwt_extended import jwt_required
from .. import organizations_bp
from ....models.organization import Client, Organization
from ....extensions import db

@organizations_bp.route('/api/clients', methods=['GET'])
@jwt_required()
def list_clients():
    clients = Client.query.all()
    return jsonify([{
        "id": c.id,
        "name": c.name,
        "email": c.email,
        "organization_id": c.organization_id
    } for c in clients])

@organizations_bp.route('/api/clients', methods=['POST'])
@jwt_required()
def create_client():
    data = request.get_json()
    client = Client(
        name=data['name'],
        email=data.get('email'),
        phone=data.get('phone'),
        address=data.get('address'),
        tax_id=data.get('tax_id'),
        notes=data.get('notes'),
        organization_id=data['organization_id']
    )
    db.session.add(client)
    db.session.commit()
    return jsonify({"message": "Client created", "id": client.id}), 201

@organizations_bp.route('/api/clients/<int:client_id>', methods=['PUT'])
@jwt_required()
def update_client(client_id):
    client = Client.query.get_or_404(client_id)
    data = request.get_json()
    for field in ['name', 'email', 'phone', 'address', 'tax_id', 'notes']:
        setattr(client, field, data.get(field, getattr(client, field)))
    db.session.commit()
    return jsonify({"message": "Client updated", "id": client.id})

@organizations_bp.route('/api/clients/<int:client_id>', methods=['DELETE'])
@jwt_required()
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    return jsonify({"message": "Client deleted", "id": client.id})
