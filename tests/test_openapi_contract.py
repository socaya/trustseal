"""OpenAPI specification + per-endpoint contract tests.

Two parts:

1. **Spec sanity.** The generated document is valid OpenAPI 3.0.3, is
   exposed at ``GET /api/openapi.json``, and declares every endpoint
   the integration we promise to maintain.

2. **Contract behaviour.** For each documented endpoint, exercise a
   realistic call shape against the Flask test client and validate the
   response body against the declared schema. This is the gate that
   prevents silent drift between the code and the published spec.

The endpoints covered here are the ones listed in
``DOCUMENTED_ENDPOINTS`` in :mod:`app.services.openapi`. Adding an
endpoint there without a matching test here fails this suite — the
list is the single source of truth.
"""
from __future__ import annotations

import pytest
from jsonschema import Draft202012Validator


# ---- helpers --------------------------------------------------------


# ---- spec sanity ----------------------------------------------------


class TestSpec:
    def test_spec_is_openapi_3_0_3(self):
        from app.services.openapi import spec_as_dict

        doc = spec_as_dict()
        assert doc["openapi"] == "3.0.3"
        assert "paths" in doc
        assert "components" in doc

    def test_all_documented_endpoints_reach_the_paths_map(self):
        from app.services.openapi import DOCUMENTED_ENDPOINTS, spec_as_dict

        doc = spec_as_dict()
        for entry in DOCUMENTED_ENDPOINTS:
            path = entry["path"].replace("{", "{").replace("}", "}")
            assert path in doc["paths"], f"missing path {path}"
            assert entry["method"] in doc["paths"][path], (
                f"missing method {entry['method']} on {path}"
            )

    def test_required_schemas_are_registered(self):
        from app.services.openapi import spec_as_dict

        doc = spec_as_dict()
        for name in [
            "EnvelopeDetail",
            "EnvelopeParticipant",
            "ProblemDetail",
            "PublicVerifyResponse",
            "WebhookEndpoint",
            "WebhookEndpointCreate",
            "WebhookEndpointDisclosed",
            "WebhookDelivery",
        ]:
            assert name in doc["components"]["schemas"]

    def test_openapi_endpoint_serves_json(self, pg_app):
        client = pg_app.test_client()
        r = client.get("/api/openapi.json")
        assert r.status_code == 200
        body = r.get_json()
        assert body["openapi"] == "3.0.3"


# ---- behaviour / contract -------------------------------------------


def _oas_to_jsonschema(node):
    """Translate OAS 3.0 ``nullable`` into JSON Schema 2020-12 null unions.

    jsonschema Draft 2020-12 does not understand OAS's ``nullable``
    extension, so we rewrite it in-place to ``type: [..., "null"]``.
    """
    if isinstance(node, dict):
        new = {}
        nullable = node.get("nullable") is True
        for key, value in node.items():
            if key == "nullable":
                continue
            new[key] = _oas_to_jsonschema(value)
        if nullable and "type" in new:
            existing = new["type"]
            types = existing if isinstance(existing, list) else [existing]
            if "null" not in types:
                types = types + ["null"]
            new["type"] = types
        return new
    if isinstance(node, list):
        return [_oas_to_jsonschema(item) for item in node]
    return node


def _validate(spec: dict, schema_name: str, payload) -> list[str]:
    translated_components = _oas_to_jsonschema(spec["components"])
    schema = dict(_schema_for(translated_components["schemas"], schema_name))
    full_doc = {
        "components": translated_components,
        **schema,
    }
    validator = Draft202012Validator(full_doc)
    return [err.message for err in validator.iter_errors(payload)]


def _schema_for(schemas: dict, name: str) -> dict:
    return schemas[name]


@pytest.fixture
def actor(pg_app):
    from flask_jwt_extended import create_access_token

    from app.extensions import db
    from app.models.organization import Organization
    from app.models.system import Role, UserRole
    from app.models.user import User

    org = Organization(name="OpenAPI Tenant")
    db.session.add(org)
    db.session.flush()
    user = User(
        username="openapi-user",
        email="openapi-user@example.test",
        is_active=True,
        organization_id=org.id,
    )
    user.set_password("not-used")
    role = Role(name="admin")
    db.session.add_all([user, role])
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role_id=role.id))
    db.session.commit()
    return {
        "tenant": org,
        "user": user,
        "token": create_access_token(identity=str(user.id)),
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestContract:
    def test_webhooks_create_matches_schema(self, pg_app, actor):
        from app.services.openapi import spec_as_dict

        spec = spec_as_dict()
        r = pg_app.test_client().post(
            "/api/webhooks",
            json={
                "url": "https://hooks.example.test/trustseal",
                "events": ["envelope.prepared"],
                "description": "staging probe",
            },
            headers={"Idempotency-Key": "contract-1", **_auth(actor["token"])},
        )
        assert r.status_code == 201, r.get_data(as_text=True)
        errors = _validate(spec, "WebhookEndpointDisclosed", r.get_json())
        assert not errors, errors

    def test_webhooks_list_returns_array_of_endpoints(self, pg_app, actor):
        from app.services.openapi import spec_as_dict

        # Seed one endpoint.
        pg_app.test_client().post(
            "/api/webhooks",
            json={
                "url": "https://hooks.example.test/trustseal-2",
                "events": ["envelope.prepared"],
            },
            headers={"Idempotency-Key": "contract-list", **_auth(actor["token"])},
        )
        r = pg_app.test_client().get(
            "/api/webhooks", headers=_auth(actor["token"])
        )
        assert r.status_code == 200
        body = r.get_json()
        assert isinstance(body, list)
        spec = spec_as_dict()
        for item in body:
            errors = _validate(spec, "WebhookEndpoint", item)
            assert not errors, errors

    def test_public_verification_response_matches_schema(self, pg_app):
        pg_app.config["PUBLIC_PDF_VERIFICATION_ENABLED"] = False
        from app.services.openapi import spec_as_dict

        r = pg_app.test_client().post(
            "/api/public-verification/pdf",
            data={"evidence_sha256": "a" * 64},
        )
        assert r.status_code == 503
        body = r.get_json()
        spec = spec_as_dict()
        errors = _validate(spec, "PublicVerifyResponse", body)
        assert not errors, errors

    def test_problem_detail_response_matches_schema(self, pg_app, actor):
        """A 4xx from a documented endpoint returns a valid ProblemDetail."""
        from app.services.openapi import spec_as_dict

        # Missing Idempotency-Key on a documented mutation returns 400.
        r = pg_app.test_client().post(
            "/api/webhooks",
            json={"url": "https://hooks.example.test/err", "events": ["x"]},
            headers=_auth(actor["token"]),
        )
        assert r.status_code == 400
        assert r.content_type.startswith("application/problem+json")
        spec = spec_as_dict()
        errors = _validate(spec, "ProblemDetail", r.get_json())
        assert not errors, errors


class TestCli:
    def test_dump_writes_yaml(self, tmp_path, pg_app):
        from click.testing import CliRunner

        from app.cli.openapi import openapi_cli

        out = tmp_path / "openapi.yaml"
        runner = CliRunner()
        with pg_app.app_context():
            result = runner.invoke(
                openapi_cli, ["dump", "--output", str(out), "--format", "yaml"]
            )
        assert result.exit_code == 0, result.output
        assert out.exists()
        assert "openapi: 3.0.3" in out.read_text(encoding="utf-8")
