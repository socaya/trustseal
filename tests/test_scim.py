"""SCIM 2.0 Users endpoint contract.

Covers:

* Anonymous callers receive 401 with an application/scim+json error.
* An inactive service account is rejected.
* List returns a SCIM ListResponse with totalResults.
* Pagination ``startIndex``/``count`` is honored.
* POST creates a user bound to the service-account's tenant.
* POST with a duplicate userName or email returns 409.
* GET /Users/<id> returns the resource; cross-tenant returns 404.
* PATCH replaces ``active``, ``name.givenName``, email.
* PUT does a full-resource replace.
* DELETE soft-deletes (marks inactive) — subsequent GET is still 200.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def tenants(pg_app):
    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User
    from app.services.scim import mint_token

    org_a = Organization(name="SCIM Tenant A")
    org_b = Organization(name="SCIM Tenant B")
    db.session.add_all([org_a, org_b])
    db.session.flush()
    admin_a = User(
        username="scim-admin-a",
        email="scim-admin-a@example.test",
        is_active=True,
        organization_id=org_a.id,
    )
    admin_a.set_password("not-used-strong-password")
    admin_b = User(
        username="scim-admin-b",
        email="scim-admin-b@example.test",
        is_active=True,
        organization_id=org_b.id,
    )
    admin_b.set_password("not-used-strong-password")
    db.session.add_all([admin_a, admin_b])
    db.session.flush()
    _acct_a, token_a = mint_token(
        tenant_id=org_a.id, created_by_id=admin_a.id, display_name="Okta"
    )
    _acct_b, token_b = mint_token(
        tenant_id=org_b.id, created_by_id=admin_b.id, display_name="Azure"
    )
    db.session.commit()
    return {
        "a": {"org": org_a, "admin": admin_a, "token": token_a},
        "b": {"org": org_b, "admin": admin_b, "token": token_b},
    }


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _scim_body(client, token):
    return {"Content-Type": "application/scim+json", **_auth(token)}


class TestAuthentication:
    def test_missing_bearer_denied(self, pg_app, tenants):
        r = pg_app.test_client().get("/scim/v2/Users")
        assert r.status_code == 401
        body = r.get_json()
        assert "urn:ietf:params:scim:api:messages:2.0:Error" in body["schemas"]

    def test_wrong_bearer_denied(self, pg_app, tenants):
        r = pg_app.test_client().get(
            "/scim/v2/Users", headers={"Authorization": "Bearer nope"}
        )
        assert r.status_code == 401

    def test_inactive_service_account_denied(self, pg_app, tenants):
        from app.extensions import db
        from app.models.scim import ScimServiceAccount

        account = ScimServiceAccount.query.filter_by(
            organization_id=tenants["a"]["org"].id
        ).first()
        account.active = False
        db.session.commit()
        r = pg_app.test_client().get(
            "/scim/v2/Users", headers=_auth(tenants["a"]["token"])
        )
        assert r.status_code == 401


class TestList:
    def test_list_is_tenant_scoped(self, pg_app, tenants):
        client = pg_app.test_client()
        # Admin in tenant A is already in the DB, so listing returns it.
        r = client.get("/scim/v2/Users", headers=_auth(tenants["a"]["token"]))
        assert r.status_code == 200
        body = r.get_json()
        assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
        assert body["totalResults"] == 1
        assert body["Resources"][0]["userName"] == "scim-admin-a"
        # Cross-tenant: tenant B's token only sees tenant B's admin.
        r2 = client.get("/scim/v2/Users", headers=_auth(tenants["b"]["token"]))
        assert r2.status_code == 200
        names = [r["userName"] for r in r2.get_json()["Resources"]]
        assert "scim-admin-b" in names and "scim-admin-a" not in names

    def test_pagination(self, pg_app, tenants):
        from app.extensions import db
        from app.models.user import User

        org_a = tenants["a"]["org"]
        for i in range(5):
            u = User(
                username=f"user-{i}",
                email=f"user-{i}@example.test",
                is_active=True,
                organization_id=org_a.id,
            )
            u.set_password("x" * 20)
            db.session.add(u)
        db.session.commit()
        r = pg_app.test_client().get(
            "/scim/v2/Users?startIndex=2&count=2",
            headers=_auth(tenants["a"]["token"]),
        )
        body = r.get_json()
        assert body["startIndex"] == 2
        assert body["itemsPerPage"] == 2
        assert body["totalResults"] == 6


class TestCreate:
    def test_create_user(self, pg_app, tenants):
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "new-user",
            "name": {"givenName": "New", "familyName": "User"},
            "emails": [
                {"value": "new-user@example.test", "primary": True, "type": "work"}
            ],
            "active": True,
        }
        r = pg_app.test_client().post(
            "/scim/v2/Users",
            json=payload,
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        body = r.get_json()
        assert body["userName"] == "new-user"
        assert body["emails"][0]["value"] == "new-user@example.test"
        assert body["active"] is True
        assert r.headers["Location"].startswith("/scim/v2/Users/")

    def test_create_conflict(self, pg_app, tenants):
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "scim-admin-a",  # already exists
            "emails": [{"value": "x@example.test", "primary": True}],
        }
        r = pg_app.test_client().post(
            "/scim/v2/Users",
            json=payload,
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 409

    def test_create_missing_username(self, pg_app, tenants):
        r = pg_app.test_client().post(
            "/scim/v2/Users",
            json={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "emails": [{"value": "a@example.test", "primary": True}],
            },
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 400


class TestFetchAndPatch:
    def test_fetch_cross_tenant_returns_404(self, pg_app, tenants):
        r = pg_app.test_client().get(
            f"/scim/v2/Users/{tenants['a']['admin'].id}",
            headers=_auth(tenants["b"]["token"]),
        )
        assert r.status_code == 404

    def test_patch_sets_active_false(self, pg_app, tenants):
        user_id = tenants["a"]["admin"].id
        r = pg_app.test_client().patch(
            f"/scim/v2/Users/{user_id}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "replace", "path": "active", "value": False}
                ],
            },
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 200
        assert r.get_json()["active"] is False

    def test_patch_updates_name(self, pg_app, tenants):
        user_id = tenants["a"]["admin"].id
        r = pg_app.test_client().patch(
            f"/scim/v2/Users/{user_id}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "replace", "path": "name.givenName", "value": "Alice"},
                    {"op": "replace", "path": "name.familyName", "value": "Admin"},
                ],
            },
            headers=_auth(tenants["a"]["token"]),
        )
        body = r.get_json()
        assert body["name"]["givenName"] == "Alice"
        assert body["name"]["familyName"] == "Admin"

    def test_patch_unsupported_path(self, pg_app, tenants):
        user_id = tenants["a"]["admin"].id
        r = pg_app.test_client().patch(
            f"/scim/v2/Users/{user_id}",
            json={
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [
                    {"op": "replace", "path": "roles", "value": ["admin"]}
                ],
            },
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 400

    def test_put_replaces_fields(self, pg_app, tenants):
        user_id = tenants["a"]["admin"].id
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "scim-admin-a",
            "name": {"givenName": "Alice", "familyName": "Replaced"},
            "emails": [
                {"value": "renamed@example.test", "primary": True}
            ],
            "active": True,
        }
        r = pg_app.test_client().put(
            f"/scim/v2/Users/{user_id}",
            json=payload,
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["emails"][0]["value"] == "renamed@example.test"
        assert body["name"]["givenName"] == "Alice"

    def test_delete_soft_deactivates(self, pg_app, tenants):
        user_id = tenants["a"]["admin"].id
        client = pg_app.test_client()
        r = client.delete(
            f"/scim/v2/Users/{user_id}",
            headers=_auth(tenants["a"]["token"]),
        )
        assert r.status_code == 204
        follow = client.get(
            f"/scim/v2/Users/{user_id}",
            headers=_auth(tenants["a"]["token"]),
        )
        assert follow.status_code == 200
        assert follow.get_json()["active"] is False
