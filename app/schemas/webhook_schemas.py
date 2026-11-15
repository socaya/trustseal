"""Webhook endpoint and delivery schemas."""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class WebhookEndpointCreateSchema(Schema):
    url = fields.URL(required=True, schemes=("http", "https"))
    events = fields.List(
        fields.String(validate=validate.Length(min=1, max=80)),
        required=True,
        validate=validate.Length(min=1),
    )
    description = fields.String(allow_none=True, metadata={"nullable": True}, validate=validate.Length(max=200))


class WebhookEndpointSchema(Schema):
    id = fields.Integer(required=True)
    url = fields.String(required=True)
    events = fields.List(fields.String(), required=True)
    active = fields.Boolean(required=True)
    description = fields.String(allow_none=True, metadata={"nullable": True})
    created_by_id = fields.Integer(required=True)
    created_at = fields.String(allow_none=True, metadata={"nullable": True})
    updated_at = fields.String(allow_none=True, metadata={"nullable": True})


class WebhookEndpointDisclosedSchema(WebhookEndpointSchema):
    secret = fields.String(
        required=True,
        metadata={"description": "One-time webhook signing secret"},
    )
    secret_disclosure_once = fields.Boolean(required=True)


class WebhookDeliverySchema(Schema):
    id = fields.Integer(required=True)
    endpoint_id = fields.Integer(required=True)
    event_id = fields.String(required=True)
    event_type = fields.String(required=True)
    status = fields.String(
        required=True,
        validate=validate.OneOf(
            ["pending", "in_flight", "succeeded", "failed", "dead"]
        ),
    )
    retry_count = fields.Integer(required=True)
    response_status = fields.Integer(allow_none=True, metadata={"nullable": True})
    last_error = fields.String(allow_none=True, metadata={"nullable": True})
    next_retry_at = fields.String(allow_none=True, metadata={"nullable": True})
    sent_at = fields.String(allow_none=True, metadata={"nullable": True})
    completed_at = fields.String(allow_none=True, metadata={"nullable": True})
    created_at = fields.String(allow_none=True, metadata={"nullable": True})
