"""Team membership administration API.

Routes:

* ``POST   /api/teams``                     — create a team (admin)
* ``GET    /api/teams``                     — list the caller's org's teams
* ``POST   /api/teams/<id>/members``        — add a member (admin)
* ``DELETE /api/teams/<id>/members/<uid>``  — remove a member (admin)
* ``DELETE /api/teams/<id>``                — archive a team (admin)
* ``GET    /api/teams/me``                  — return the caller's own
                                              active team-id list.

Admin checks are delegated to :func:`app.policies.api_access.is_admin`
so the policy stays in one place. The caller's organization is drawn
from their own user record — no client-provided organization id.
"""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.team import Team, TeamMembership
from app.policies.api_access import is_admin
from app.services import teams as team_service
from app.services.token_security import active_token_user

teams_api = Blueprint("teams_api", __name__, url_prefix="/api/teams")


def _require_admin():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    return user


def _team_dict(team: Team) -> dict:
    return {
        "id": team.id,
        "name": team.name,
        "description": team.description,
        "created_by_id": team.created_by_id,
        "created_at": team.created_at.isoformat(),
        "archived": team.deleted_at is not None,
    }


@teams_api.route("", methods=["POST"])
@jwt_required()
def create_team():
    actor = _require_admin()
    data = request.get_json(silent=True) or {}
    try:
        row = team_service.create_team(
            organization_id=actor.organization_id,
            name=data.get("name", ""),
            created_by_id=actor.id,
            description=data.get("description"),
        )
    except team_service.TeamError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return jsonify(_team_dict(row)), 201


@teams_api.route("", methods=["GET"])
@jwt_required()
def list_teams():
    actor = _require_admin()
    rows = (
        Team.query.filter_by(organization_id=actor.organization_id)
        .order_by(Team.id.desc())
        .all()
    )
    return jsonify(teams=[_team_dict(r) for r in rows]), 200


@teams_api.route("/me", methods=["GET"])
@jwt_required()
def my_teams():
    actor = active_token_user()
    if actor is None or not actor.is_active:
        abort(401)
    return jsonify(team_ids=team_service.membership_ids(actor.id)), 200


@teams_api.route("/<int:team_id>/members", methods=["POST"])
@jwt_required()
def add_member(team_id):
    actor = _require_admin()
    team = db.session.get(Team, team_id)
    if team is None or team.organization_id != actor.organization_id:
        abort(404)
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    if not isinstance(user_id, int):
        abort(400, description="user_id_required")
    try:
        row = team_service.add_member(
            team_id,
            user_id,
            added_by_id=actor.id,
            role_in_team=data.get("role_in_team", "member"),
        )
    except team_service.TeamError as exc:
        db.session.rollback()
        abort(400, description=str(exc))
    db.session.commit()
    return (
        jsonify(
            membership_id=row.id,
            team_id=team_id,
            user_id=user_id,
            role_in_team=row.role_in_team,
        ),
        201,
    )


@teams_api.route(
    "/<int:team_id>/members/<int:user_id>", methods=["DELETE"]
)
@jwt_required()
def remove_member(team_id, user_id):
    actor = _require_admin()
    team = db.session.get(Team, team_id)
    if team is None or team.organization_id != actor.organization_id:
        abort(404)
    try:
        team_service.remove_member(team_id, user_id, removed_by_id=actor.id)
    except team_service.TeamError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(message="membership_removed"), 200


@teams_api.route("/<int:team_id>", methods=["DELETE"])
@jwt_required()
def archive_team(team_id):
    actor = _require_admin()
    team = db.session.get(Team, team_id)
    if team is None or team.organization_id != actor.organization_id:
        abort(404)
    try:
        row = team_service.archive_team(team_id, archived_by_id=actor.id)
    except team_service.TeamError as exc:
        db.session.rollback()
        abort(404, description=str(exc))
    db.session.commit()
    return jsonify(_team_dict(row)), 200
