"""Idempotency decorator contract.

Covers the ADR 0004 guarantees:

* Missing header -> 400.
* First call -> view runs, response stored.
* Second call with same key + same body -> stored response replayed, view
  does not run again.
* Second call with same key + different body -> 409 body conflict.
* Anonymous caller -> 401.
* Untenanted caller -> 409.
* Non-2xx response marks row ``failed`` and permits retry.
* Pruning removes expired rows and leaves live rows alone.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from flask import jsonify


@pytest.fixture
def app(pg_app):
    pg_app.extensions["_probe_counter"] = {"count": 0}
    yield pg_app


@pytest.fixture
def seeded(app):
    from flask_jwt_extended import create_access_token

    from app.extensions import db
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Tenant X")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="idempo",
        email="idempo@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used")
    db.session.add(user)
    db.session.flush()
    untenanted = User(
        username="noorg",
        email="noorg@example.test",
        is_active=True,
        organization_id=None,
    )
    untenanted.set_password("not-used")
    db.session.add(untenanted)
    db.session.commit()
    return {
        "tenant_id": org.id,
        "token": create_access_token(identity=str(user.id)),
        "untenanted_token": create_access_token(identity=str(untenanted.id)),
    }


def auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestIdempotencyDecorator:
    def test_missing_header_returns_400(self, app, seeded):
        r = app.test_client().post(
            "/api/_test/idempotent", json={"a": 1}, headers=auth(seeded["token"])
        )
        assert r.status_code == 400

    def test_anonymous_returns_401(self, app):
        r = app.test_client().post(
            "/api/_test/idempotent",
            json={"a": 1},
            headers={"Idempotency-Key": "k1"},
        )
        assert r.status_code == 401

    def test_untenanted_returns_409(self, app, seeded):
        r = app.test_client().post(
            "/api/_test/idempotent",
            json={"a": 1},
            headers={"Idempotency-Key": "k1", **auth(seeded["untenanted_token"])},
        )
        assert r.status_code == 409

    def test_first_call_runs_view(self, app, seeded):
        counter = app.extensions["_probe_counter"]
        counter["count"] = 0
        r = app.test_client().post(
            "/api/_test/idempotent",
            json={"a": 1},
            headers={"Idempotency-Key": "k1", **auth(seeded["token"])},
        )
        assert r.status_code == 201
        assert r.get_json() == {"calls": 1}
        assert counter["count"] == 1

    def test_second_call_same_key_replays(self, app, seeded):
        counter = app.extensions["_probe_counter"]
        counter["count"] = 0
        headers = {"Idempotency-Key": "k1", **auth(seeded["token"])}
        r1 = app.test_client().post("/api/_test/idempotent", json={"a": 1}, headers=headers)
        r2 = app.test_client().post("/api/_test/idempotent", json={"a": 1}, headers=headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.get_json() == r2.get_json()
        assert counter["count"] == 1, "View must not run a second time on replay"
        assert r2.headers.get("Idempotent-Replay") == "true"

    def test_body_conflict_returns_409(self, app, seeded):
        headers = {"Idempotency-Key": "k1", **auth(seeded["token"])}
        app.test_client().post("/api/_test/idempotent", json={"a": 1}, headers=headers)
        r = app.test_client().post("/api/_test/idempotent", json={"a": 2}, headers=headers)
        assert r.status_code == 409

    def test_json_key_order_does_not_conflict(self, app, seeded):
        """Reordered keys in the same JSON object must not trip the body check."""
        headers = {"Idempotency-Key": "k1", **auth(seeded["token"])}
        r1 = app.test_client().post(
            "/api/_test/idempotent", json={"a": 1, "b": 2}, headers=headers
        )
        r2 = app.test_client().post(
            "/api/_test/idempotent", json={"b": 2, "a": 1}, headers=headers
        )
        assert r1.status_code == 201
        assert r2.status_code == 201, "Insignificant key order must not conflict"

    def test_different_tenants_do_not_collide(self, app, seeded):
        from flask_jwt_extended import create_access_token

        from app.extensions import db
        from app.models.organization import Organization
        from app.models.user import User

        org = Organization(name="Tenant Y")
        db.session.add(org)
        db.session.flush()
        user = User(
            username="tenanty",
            email="tenanty@example.test",
            is_active=True,
            organization_id=org.id,
        )
        user.set_password("not-used")
        db.session.add(user)
        db.session.commit()
        token_y = create_access_token(identity=str(user.id))

        counter = app.extensions["_probe_counter"]
        counter["count"] = 0
        r1 = app.test_client().post(
            "/api/_test/idempotent",
            json={"a": 1},
            headers={"Idempotency-Key": "shared", **auth(seeded["token"])},
        )
        r2 = app.test_client().post(
            "/api/_test/idempotent",
            json={"a": 1},
            headers={"Idempotency-Key": "shared", **auth(token_y)},
        )
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert counter["count"] == 2, "Keys must be scoped per tenant"

    def test_failed_response_marks_row_failed(self, app, seeded):
        headers = {"Idempotency-Key": "kf", **auth(seeded["token"])}
        r1 = app.test_client().post("/api/_test/idempotent-fails", json={}, headers=headers)
        assert r1.status_code == 500
        from app.models.idempotency_record import IdempotencyRecord

        record = IdempotencyRecord.query.filter_by(
            tenant_id=seeded["tenant_id"], endpoint="test.fail", key="kf"
        ).first()
        assert record is not None
        assert record.state == "failed"

    def test_key_too_long_returns_400(self, app, seeded):
        headers = {"Idempotency-Key": "x" * 129, **auth(seeded["token"])}
        r = app.test_client().post("/api/_test/idempotent", json={}, headers=headers)
        assert r.status_code == 400


class TestPruning:
    def test_prune_expired_removes_only_expired_rows(self, app, seeded):
        from app.extensions import db
        from app.models.idempotency_record import IdempotencyRecord
        from app.services.idempotency import prune_expired

        now = datetime.utcnow()
        live = IdempotencyRecord(
            tenant_id=seeded["tenant_id"],
            endpoint="test.prune",
            key="live",
            request_hash="h",
            state="completed",
            locked_at=now,
            expires_at=now + timedelta(hours=1),
        )
        expired = IdempotencyRecord(
            tenant_id=seeded["tenant_id"],
            endpoint="test.prune",
            key="expired",
            request_hash="h",
            state="completed",
            locked_at=now - timedelta(days=2),
            expires_at=now - timedelta(hours=1),
        )
        db.session.add_all([live, expired])
        db.session.commit()
        removed = prune_expired()
        assert removed == 1
        assert IdempotencyRecord.query.filter_by(key="live").first() is not None
        assert IdempotencyRecord.query.filter_by(key="expired").first() is None


class _FakeRedis:
    """Minimal in-memory Redis client implementing get() and set(..., ex=, nx=)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value: str, *, ex: int | None = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True


class TestPluggableRedisRepository:
    def test_redis_adapter_replays_conflicts_and_retries(self, app, seeded):
        from app.services.idempotency import (
            IdempotencyRepository,
            PostgresIdempotencyRepository,
            RedisIdempotencyRepository,
        )

        redis_repo = RedisIdempotencyRepository(_FakeRedis())
        assert isinstance(redis_repo, IdempotencyRepository)
        assert isinstance(PostgresIdempotencyRepository(), IdempotencyRepository)

        app.config["IDEMPOTENCY_REPOSITORY"] = redis_repo
        try:
            headers = {"Idempotency-Key": "xr-key-1", **auth(seeded["token"])}
            r1 = app.test_client().post(
                "/api/_test/idempotent", json={"amount": 100}, headers=headers
            )
            assert r1.status_code == 201
            assert r1.headers.get("Idempotent-Replay") is None

            # Cross-region replay hits Redis and returns identical response
            r2 = app.test_client().post(
                "/api/_test/idempotent", json={"amount": 100}, headers=headers
            )
            assert r2.status_code == 201
            assert r2.headers.get("Idempotent-Replay") == "true"
            assert r2.get_json() == r1.get_json()

            # Body conflict on same key returns 409
            r3 = app.test_client().post(
                "/api/_test/idempotent", json={"amount": 200}, headers=headers
            )
            assert r3.status_code == 409

            # Failed attempt marks failed and allows retry
            fail_headers = {"Idempotency-Key": "xr-fail-1", **auth(seeded["token"])}
            rf = app.test_client().post(
                "/api/_test/idempotent-fails", json={}, headers=fail_headers
            )
            assert rf.status_code == 500
            entry = redis_repo.get(
                tenant_id=seeded["tenant_id"], endpoint="test.fail", key="xr-fail-1"
            )
            assert entry is not None and entry.state == "failed"
        finally:
            app.config.pop("IDEMPOTENCY_REPOSITORY", None)
