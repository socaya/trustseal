"""Teams and team memberships.

A team is a sub-grouping inside an organization. Users can belong to
zero or more teams. Documents and envelopes can optionally be scoped
to a team so visibility is narrower than the whole organization.

Design decisions:

* Teams never cross organization boundaries. Every row is
  tenant-scoped via ``organization_id`` and the ``TenantScopedRepository``
  already enforces that filter.
* ``TeamMembership.role_in_team`` names the role a user plays inside
  the team (``member``, ``lead``, ``approver``). The role is advisory
  for the UI — authorization decisions remain driven by the
  organization-level RBAC model. A future phase can map
  team-roles-to-permissions if the product needs finer control.
* ``Team.deleted_at`` supports soft-delete so an archived team keeps
  its membership history for audit.
"""
from datetime import datetime

from app.extensions import db


class Team(db.Model):
    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(
        db.Integer,
        db.ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "organization_id", "name", name="uq_teams_org_name"
        ),
    )

    memberships = db.relationship(
        "TeamMembership", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMembership(db.Model):
    __tablename__ = "team_memberships"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(
        db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, index=True
    )
    role_in_team = db.Column(db.String(40), nullable=False, default="member")
    added_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False
    )
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    removed_at = db.Column(db.DateTime, nullable=True)
    removed_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )

    team = db.relationship("Team", back_populates="memberships")

    __table_args__ = (
        db.Index(
            "ix_team_memberships_active",
            "team_id",
            "user_id",
            unique=True,
            postgresql_where=db.text("removed_at IS NULL"),
        ),
    )
