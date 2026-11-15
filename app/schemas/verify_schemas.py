"""Public PDF verification response."""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class PublicVerifyResponseSchema(Schema):
    status = fields.String(
        required=True,
        validate=validate.OneOf(
            ["valid", "invalid", "invalid_request", "unavailable"]
        ),
    )
    assurance = fields.String(required=True)
    not_individual_signatures = fields.Boolean(required=True)
    document_sha256 = fields.String(validate=validate.Length(equal=64))
    signature_valid = fields.Boolean()
    intact = fields.Boolean()
    trusted = fields.Boolean()
    certificate_sha256 = fields.String(validate=validate.Length(equal=64))
    evidence_sha256 = fields.String(validate=validate.Length(equal=64))
