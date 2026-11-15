"""Fixtures for tenant-isolation security tests.

Uses the shared PostgreSQL harness defined in ``tests/conftest.py``.
Two adjacent tenants are provisioned, each with one user and one
document, so the matrix test can prove 404-for-cross-tenant.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def app(pg_app):
    return pg_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def tenants(app):
    """Return a mapping with two tenants, each pre-populated with resources."""
    from flask_jwt_extended import create_access_token

    from app.extensions import db
    from app.models.documents.document import Document
    from app.models.organization import Organization
    from app.models.user import User

    def make_tenant(name: str) -> dict:
        org = Organization(name=f"Tenant {name}")
        db.session.add(org)
        db.session.flush()
        user = User(
            username=f"user_{name.lower()}",
            email=f"user-{name.lower()}@example.test",
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("not-used")
        db.session.add(user)
        db.session.flush()
        doc = Document(
            title=f"Tenant {name} document",
            status="draft",
            created_by=user.id,
            organization_id=org.id,
        )
        db.session.add(doc)
        db.session.flush()
        token = create_access_token(identity=str(user.id))
        return {"org": org, "user": user, "token": token, "document": doc}

    a = make_tenant("A")
    b = make_tenant("B")
    db.session.commit()
    yield {"A": a, "B": b}


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
