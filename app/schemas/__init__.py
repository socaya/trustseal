"""Marshmallow schemas feeding the OpenAPI specification.

These schemas intentionally cover a tight subset of endpoints first —
the ones most likely to be integrated against: envelope prepare,
public verification, webhook lifecycle. New endpoints migrate to
schemas incrementally; the contract test only asserts the endpoints
already declared below.
"""
from .envelope_schemas import EnvelopeDetailSchema, EnvelopeParticipantSchema
from .error_schemas import ProblemDetailSchema
from .verify_schemas import PublicVerifyResponseSchema
from .webhook_schemas import (
    WebhookDeliverySchema,
    WebhookEndpointCreateSchema,
    WebhookEndpointDisclosedSchema,
    WebhookEndpointSchema,
)

__all__ = [
    "EnvelopeDetailSchema",
    "EnvelopeParticipantSchema",
    "ProblemDetailSchema",
    "PublicVerifyResponseSchema",
    "WebhookDeliverySchema",
    "WebhookEndpointCreateSchema",
    "WebhookEndpointDisclosedSchema",
    "WebhookEndpointSchema",
]
