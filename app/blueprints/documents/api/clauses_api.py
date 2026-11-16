"""Clause library API (Phase E2)."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.clause import Clause, ClauseVersion
from app.policies.separation_of_duties import (
    SeparationOfDutiesViolation,
    assert_distinct,
)
from app.services import clauses as clause_service
from app.services.token_security import active_token_user

clauses_api = Blueprint("clauses_api", __name__, url_prefix="/api/clauses")


def _actor():
    user = active_token_user()
    if user is None or not user.is_active or user.organization_id is None:
        abort(401)
    return user


def _owned(clause_id, user):
    row = Clause.query.filter_by(
        id=clause_id, organization_id=user.organization_id
    ).first()
    if row is None:
        abort(404)
    return row


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="json_object_required")
    return data


@clauses_api.route("", methods=["POST"])
@jwt_required()
def create_clause():
    user = _actor()
    data = _payload()
    try:
        row = clause_service.create_clause(
            organization_id=user.organization_id,
            name=str(data.get("name", "")),
            body=str(data.get("body", "")),
            created_by_id=user.id,
            category=data.get("category"),
        )
    except clause_service.ClauseError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(row.to_dict()), 201


@clauses_api.route("", methods=["GET"])
@jwt_required()
def list_clauses():
    user = _actor()
    state = request.args.get("state")
    query = Clause.query.filter_by(organization_id=user.organization_id)
    if state in ("draft", "approved", "archived"):
        query = query.filter_by(state=state)
    rows = query.order_by(Clause.id.desc()).all()
    return jsonify(clauses=[r.to_dict() for r in rows]), 200


@clauses_api.route("/<int:clause_id>", methods=["GET"])
@jwt_required()
def get_clause(clause_id):
    user = _actor()
    return jsonify(_owned(clause_id, user).to_dict()), 200


@clauses_api.route("/<int:clause_id>/versions", methods=["POST"])
@jwt_required()
def add_version(clause_id):
    user = _actor()
    clause = _owned(clause_id, user)
    data = _payload()
    try:
        version = clause_service.new_version(
            clause, str(data.get("body", "")), author_id=user.id
        )
    except clause_service.ClauseError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(version.to_dict()), 201


@clauses_api.route("/<int:clause_id>/versions", methods=["GET"])
@jwt_required()
def list_versions(clause_id):
    user = _actor()
    clause = _owned(clause_id, user)
    rows = (
        ClauseVersion.query.filter_by(clause_id=clause.id)
        .order_by(ClauseVersion.revision.asc())
        .all()
    )
    return jsonify(versions=[r.to_dict() for r in rows]), 200


@clauses_api.route("/<int:clause_id>/reopen", methods=["POST"])
@jwt_required()
def reopen_clause(clause_id):
    user = _actor()
    clause = _owned(clause_id, user)
    try:
        clause_service.reopen(clause, author_id=user.id)
    except clause_service.ClauseError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(clause.to_dict()), 200


@clauses_api.route("/<int:clause_id>/approve", methods=["POST"])
@jwt_required()
def approve_clause(clause_id):
    user = _actor()
    clause = _owned(clause_id, user)
    current_version = db.session.get(
        ClauseVersion, clause.current_version_id
    )
    if current_version is not None:
        try:
            assert_distinct(
                user.id,
                (current_version.created_by_id, "current_version_author"),
                action="clause.approve",
                organization_id=clause.organization_id,
                resource_type="clause",
                resource_id=clause.id,
            )
        except SeparationOfDutiesViolation:
            db.session.commit()
            abort(403, description="author_cannot_approve_own_clause")
    try:
        clause_service.approve(clause, approved_by_id=user.id)
    except clause_service.ClauseError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(clause.to_dict()), 200


@clauses_api.route("/<int:clause_id>/archive", methods=["POST"])
@jwt_required()
def archive_clause(clause_id):
    user = _actor()
    clause = _owned(clause_id, user)
    try:
        clause_service.archive(clause, archived_by_id=user.id)
    except clause_service.ClauseError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    db.session.commit()
    return jsonify(clause.to_dict()), 200
