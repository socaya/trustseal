"""Idempotent local-dev seed.

Creates (or leaves alone) a demo tenant + admin user so an operator can
sign in and click through the migrated design-system pages. Runs
against whatever database URL the environment points at — for local
browser testing this is typically the Postgres database configured in
``.env``.

Usage:
    .venv/bin/python scripts/seed_dev.py

The script never deletes or rewrites existing rows. Safe to re-run.
"""
from __future__ import annotations

import os
import sys

# Allow invocation from any working directory.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from app import create_app  # noqa: E402
from app.extensions import db
from app.models.organization import Organization
from app.models.system import Role, UserRole
from app.models.user import User


DEMO_ORG_NAME = "TrustSeal Demo Workspace"
DEMO_EMAIL = "admin@trustseal.local"
DEMO_USERNAME = "demo-admin"
DEMO_PASSWORD = "trustseal-demo-password-2026"


def main() -> int:
    app = create_app()
    with app.app_context():
        db.create_all()

        org = Organization.query.filter_by(name=DEMO_ORG_NAME).one_or_none()
        if org is None:
            org = Organization(name=DEMO_ORG_NAME, type="company")
            db.session.add(org)
            db.session.flush()
            print(f"[seed] Created organization #{org.id} — {org.name}")
        else:
            print(f"[seed] Reusing organization #{org.id} — {org.name}")

        user = User.query.filter_by(email=DEMO_EMAIL).one_or_none()
        if user is None:
            user = User(
                username=DEMO_USERNAME,
                email=DEMO_EMAIL,
                first_name="Demo",
                last_name="Admin",
                phone=None,
                is_active=True,
                organization_id=org.id,
            )
            user.set_password(DEMO_PASSWORD)
            db.session.add(user)
            db.session.flush()
            print(f"[seed] Created user #{user.id} — {user.email}")
        else:
            print(f"[seed] Reusing user #{user.id} — {user.email}")

        role = Role.query.filter_by(name="admin").one_or_none()
        if role is None:
            role = Role(name="admin", description="Workspace administrator")
            db.session.add(role)
            db.session.flush()
            print(f"[seed] Created role #{role.id} — admin")

        link = UserRole.query.filter_by(
            user_id=user.id, role_id=role.id
        ).one_or_none()
        if link is None:
            db.session.add(UserRole(user_id=user.id, role_id=role.id))
            print(f"[seed] Granted admin role to {user.email}")

        db.session.commit()

    print()
    print("Sign in at: http://127.0.0.1:5017/auth/login")
    print(f"  Email:    {DEMO_EMAIL}")
    print(f"  Password: {DEMO_PASSWORD}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
