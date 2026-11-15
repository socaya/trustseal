"""Separation-of-duties policy (B1).

Covers the reusable policy module:

* ``assert_distinct`` raises when any conflicting id matches the
  actor; passes otherwise.
* ``enforce`` reads attributes off a record and applies the same check.
* Every violation emits a ``SecurityEvent`` row with
  ``action='separation_of_duties.<action>'`` and
  ``outcome='denied'`` so the chained audit log captures the attempt.
* The policy survives distinct actors with the same id-space (ints
  from different tables are allowed because the rule compares
  within the same actor-id namespace).

Covers the two integrated enforcement points:

* ``POST /api/stamp-custody/<id>/approve`` — admin who is also the
  custodian OR the creator is refused with 403, and the stamp
  remains ``pending``.
* ``POST /api/users/<id>/roles`` — admin cannot grant a role to
  themselves.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from flask_jwt_extended import create_access_token


@pytest.fixture
def seeded(pg_app):
    """Admin, a non-admin, an organization, and a pending ManagedStamp."""
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.stamp_custody import ManagedStamp
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="SoD Tenant", type="company")
    db.session.add(org)
    db.session.flush()

    def _mk(username, email):
        user = User(
            username=username,
            email=email,
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("sodpassword12345")
        db.session.add(user)
        db.session.flush()
        return user

    admin = _mk("sod-admin", "sod-admin@example.test")
    other_admin = _mk("sod-admin-two", "sod-admin-two@example.test")
    custodian = _mk("sod-custodian", "sod-custodian@example.test")
    requester = _mk("sod-requester", "sod-requester@example.test")
    role = Role.query.filter_by(name="admin").one_or_none() or Role(
        name="admin", description="test administrator"
    )
    db.session.add(role)
    db.session.flush()
    db.session.add_all(
        [
            UserRole(user_id=admin.id, role_id=role.id),
            UserRole(user_id=other_admin.id, role_id=role.id),
        ]
    )
    stamp = ManagedStamp(
        organization_id=org.id,
        code="SOD-STAMP-001",
        name="SoD stamp",
        custodian_id=custodian.id,
        created_by_id=requester.id,
        status="pending",
    )
    db.session.add(stamp)
    db.session.commit()
    return {
        "org": org,
        "admin": admin,
        "other_admin": other_admin,
        "custodian": custodian,
        "requester": requester,
        "stamp": stamp,
    }


class TestAssertDistinct:
    def test_passes_when_distinct(self, pg_app, seeded):
        from app.policies.separation_of_duties import assert_distinct

        assert_distinct(
            seeded["admin"].id,
            (seeded["requester"].id, "requester"),
            (seeded["custodian"].id, "custodian"),
            action="probe",
        )

    def test_raises_on_collision(self, pg_app, seeded):
        from app.policies.separation_of_duties import (
            SeparationOfDutiesViolation,
            assert_distinct,
        )

        with pytest.raises(SeparationOfDutiesViolation) as exc:
            assert_distinct(
                seeded["requester"].id,
                (seeded["requester"].id, "requester"),
                action="stamp.approve",
                organization_id=seeded["org"].id,
                resource_type="managed_stamp",
                resource_id=seeded["stamp"].id,
            )
        assert exc.value.conflict_role == "requester"

    def test_emits_security_event_on_denial(self, pg_app, seeded):
        from app.extensions import db
        from app.models.event_delivery import SecurityEvent
        from app.policies.separation_of_duties import (
            SeparationOfDutiesViolation,
            assert_distinct,
        )

        with pytest.raises(SeparationOfDutiesViolation):
            assert_distinct(
                seeded["requester"].id,
                (seeded["requester"].id, "requester"),
                action="role.assign",
                organization_id=seeded["org"].id,
                resource_type="user_role",
                resource_id=seeded["requester"].id,
            )
        db.session.commit()
        event = (
            SecurityEvent.query.filter_by(
                actor_id=seeded["requester"].id,
                action="separation_of_duties.role.assign",
            )
            .one()
        )
        assert event.outcome == "denied"
        assert event.resource_type == "user_role"


class TestEnforceRecord:
    def test_reads_fields_from_record(self, pg_app, seeded):
        from app.policies.separation_of_duties import (
            SeparationOfDutiesViolation,
            enforce,
        )

        with pytest.raises(SeparationOfDutiesViolation) as exc:
            enforce(
                seeded["requester"].id,
                seeded["stamp"],
                action="stamp.approve",
                fields=("created_by_id", "custodian_id"),
            )
        assert exc.value.conflict_role == "created_by_id"

    def test_passes_when_record_ids_differ(self, pg_app, seeded):
        from app.policies.separation_of_duties import enforce

        enforce(
            seeded["admin"].id,
            seeded["stamp"],
            action="stamp.approve",
            fields=("created_by_id", "custodian_id"),
        )


class TestStampApproveEnforcement:
    def test_admin_also_requester_blocked(self, pg_app, seeded):
        """An admin who originally requested the stamp cannot approve it."""
        from app.extensions import db
        from app.models.stamp_custody import ManagedStamp
        from app.models.system import Role, UserRole

        # Promote requester to admin so they pass _admin() but still
        # fail the SoD check.
        role = Role.query.filter_by(name="admin").one()
        db.session.add(UserRole(user_id=seeded["requester"].id, role_id=role.id))
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["requester"].id))
        r = client.post(
            f"/api/stamp-custody/{seeded['stamp'].id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        db.session.expire_all()
        stamp = db.session.get(ManagedStamp, seeded["stamp"].id)
        assert stamp.status == "pending"
        assert stamp.approved_by_id is None

    def test_admin_also_custodian_blocked(self, pg_app, seeded):
        from app.extensions import db
        from app.models.stamp_custody import ManagedStamp
        from app.models.system import Role, UserRole

        role = Role.query.filter_by(name="admin").one()
        db.session.add(UserRole(user_id=seeded["custodian"].id, role_id=role.id))
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["custodian"].id))
        r = client.post(
            f"/api/stamp-custody/{seeded['stamp'].id}/approve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        db.session.expire_all()
        stamp = db.session.get(ManagedStamp, seeded["stamp"].id)
        assert stamp.status == "pending"


class TestRoleGrantEnforcement:
    def test_self_grant_refused(self, pg_app, seeded):
        from app.extensions import db
        from app.models.system import Role, UserRole

        operator_role = Role(name="operator", description="probe")
        db.session.add(operator_role)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/users/{seeded['admin'].id}/roles",
            json={"role_id": operator_role.id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403
        db.session.expire_all()
        assert UserRole.query.filter_by(
            user_id=seeded["admin"].id, role_id=operator_role.id
        ).count() == 0

    def test_grant_to_other_user_allowed(self, pg_app, seeded):
        from app.extensions import db
        from app.models.system import Role, UserRole

        reviewer_role = Role(name="reviewer", description="probe")
        db.session.add(reviewer_role)
        db.session.commit()
        client = pg_app.test_client()
        token = create_access_token(identity=str(seeded["admin"].id))
        r = client.post(
            f"/api/users/{seeded['requester'].id}/roles",
            json={"role_id": reviewer_role.id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        db.session.expire_all()
        assert UserRole.query.filter_by(
            user_id=seeded["requester"].id, role_id=reviewer_role.id
        ).count() == 1
