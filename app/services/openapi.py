"""Generate the TrustSeal OpenAPI 3.0.3 specification.

:func:`build_spec` returns an ``apispec.APISpec`` populated with every
Marshmallow schema under :mod:`app.schemas` and the endpoints we've
elected to document. Keep the documented surface explicit so the
schemas list and the endpoint list grow in lockstep.

Export the YAML through ``flask openapi dump`` or fetch the JSON at
``GET /api/openapi.json`` for runtime contract verification.
"""
from __future__ import annotations

from typing import Any

from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin

from app.schemas import (
    EnvelopeDetailSchema,
    EnvelopeParticipantSchema,
    ProblemDetailSchema,
    PublicVerifyResponseSchema,
    WebhookDeliverySchema,
    WebhookEndpointCreateSchema,
    WebhookEndpointDisclosedSchema,
    WebhookEndpointSchema,
)


DOCUMENTED_ENDPOINTS: list[dict[str, Any]] = [
    {
        "path": "/api/envelopes/{envelope_id}/prepare",
        "method": "post",
        "summary": "Prepare a signing envelope",
        "tags": ["envelopes"],
        "security": [{"bearerAuth": []}],
        "requires_idempotency_key": True,
        "parameters": [
            {
                "in": "path",
                "name": "envelope_id",
                "required": True,
                "schema": {"type": "integer"},
            }
        ],
        "responses": {
            "200": {
                "description": "Envelope successfully prepared",
                "schema": "EnvelopeDetail",
            },
            "409": {"description": "Envelope is no longer editable", "schema": "ProblemDetail"},
        },
    },
    {
        "path": "/api/public-verification/pdf",
        "method": "post",
        "summary": "Anonymous PDF verification by digest",
        "tags": ["verification"],
        "security": [],
        "requires_idempotency_key": False,
        "parameters": [],
        "responses": {
            "200": {"description": "Verification verdict", "schema": "PublicVerifyResponse"},
            "400": {"description": "Invalid request", "schema": "PublicVerifyResponse"},
            "503": {"description": "Verification disabled", "schema": "PublicVerifyResponse"},
        },
    },
    {
        "path": "/api/webhooks",
        "method": "post",
        "summary": "Register a webhook endpoint",
        "tags": ["webhooks"],
        "security": [{"bearerAuth": []}],
        "requires_idempotency_key": True,
        "parameters": [],
        "request_body_schema": "WebhookEndpointCreate",
        "responses": {
            "201": {
                "description": "Endpoint created; one-time secret returned",
                "schema": "WebhookEndpointDisclosed",
            },
            "400": {"description": "Validation failed", "schema": "ProblemDetail"},
        },
    },
    {
        "path": "/api/webhooks",
        "method": "get",
        "summary": "List registered webhook endpoints",
        "tags": ["webhooks"],
        "security": [{"bearerAuth": []}],
        "requires_idempotency_key": False,
        "parameters": [],
        "responses": {
            "200": {
                "description": "A page of endpoints",
                "schema": {"type": "array", "items_schema": "WebhookEndpoint"},
            }
        },
    },
    {
        "path": "/api/webhooks/{endpoint_id}/deliveries",
        "method": "get",
        "summary": "List deliveries for a webhook endpoint",
        "tags": ["webhooks"],
        "security": [{"bearerAuth": []}],
        "requires_idempotency_key": False,
        "parameters": [
            {
                "in": "path",
                "name": "endpoint_id",
                "required": True,
                "schema": {"type": "integer"},
            }
        ],
        "responses": {
            "200": {
                "description": "A page of deliveries",
                "schema": {"type": "array", "items_schema": "WebhookDelivery"},
            }
        },
    },
]


def build_spec() -> APISpec:
    plugin = MarshmallowPlugin()
    spec = APISpec(
        title="TrustSeal API",
        version="0.1.0",
        openapi_version="3.0.3",
        info={
            "description": (
                "Versioned API for TrustSeal document trust workflows. "
                "Endpoints under /api/ require a bearer JWT unless marked "
                "``security: []``. Trust-critical mutations require an "
                "Idempotency-Key header."
            ),
        },
        plugins=[plugin],
    )
    # Security scheme reused by every documented operation.
    spec.components.security_scheme(
        "bearerAuth",
        {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
    )

    # Register top-level schemas only. The Marshmallow plugin auto-
    # registers nested schemas (e.g. EnvelopeParticipant inside
    # EnvelopeDetail) so listing them here would collide.
    for name, schema_cls in {
        "EnvelopeDetail": EnvelopeDetailSchema,
        "ProblemDetail": ProblemDetailSchema,
        "PublicVerifyResponse": PublicVerifyResponseSchema,
        "WebhookEndpoint": WebhookEndpointSchema,
        "WebhookEndpointCreate": WebhookEndpointCreateSchema,
        "WebhookEndpointDisclosed": WebhookEndpointDisclosedSchema,
        "WebhookDelivery": WebhookDeliverySchema,
    }.items():
        spec.components.schema(name, schema=schema_cls)

    for endpoint in DOCUMENTED_ENDPOINTS:
        _add_path(spec, endpoint)
    return spec


def _schema_ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def _add_path(spec: APISpec, endpoint: dict[str, Any]) -> None:
    operation: dict[str, Any] = {
        "summary": endpoint["summary"],
        "tags": endpoint.get("tags", []),
        "security": endpoint.get("security", []),
        "parameters": list(endpoint.get("parameters", [])),
    }
    if endpoint.get("requires_idempotency_key"):
        operation["parameters"].append(
            {
                "in": "header",
                "name": "Idempotency-Key",
                "required": True,
                "schema": {"type": "string", "maxLength": 128},
            }
        )
    if endpoint.get("request_body_schema"):
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": _schema_ref(endpoint["request_body_schema"])
                }
            },
        }
    responses: dict[str, Any] = {}
    for status, response_def in endpoint["responses"].items():
        schema = response_def.get("schema")
        if isinstance(schema, dict) and schema.get("type") == "array":
            schema_obj = {
                "type": "array",
                "items": _schema_ref(schema["items_schema"]),
            }
            content_type = "application/json"
        elif schema is not None:
            schema_obj = _schema_ref(schema)
            # Problem responses must advertise application/problem+json.
            content_type = (
                "application/problem+json"
                if schema == "ProblemDetail"
                else "application/json"
            )
        else:
            schema_obj = None
            content_type = None
        responses[status] = {"description": response_def["description"]}
        if schema_obj is not None:
            responses[status]["content"] = {
                content_type: {"schema": schema_obj}
            }
    operation["responses"] = responses
    spec.path(path=endpoint["path"], operations={endpoint["method"]: operation})


def spec_as_dict() -> dict:
    return build_spec().to_dict()
