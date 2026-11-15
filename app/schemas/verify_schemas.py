"""Public PDF verification response."""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class PublicVerifyResponseSchema(Schema):
    status = fields.String(
        required=True,
        validate=validate.OneOf(
            [
                "valid",
                "invalid",
                "invalid_request",
                "unavailable",
                "unknown",
                "mismatch",
            ]
        ),
    )
    assurance = fields.String(required=True)
    not_individual_signatures = fields.Boolean(required=True)
    document_sha256 = fields.String(validate=validate.Length(equal=64))
    # Shallow-path fields (preserved for backwards compatibility).
    signature_valid = fields.Boolean()
    intact = fields.Boolean()
    trusted = fields.Boolean()
    certificate_sha256 = fields.String(validate=validate.Length(equal=64))
    evidence_sha256 = fields.String(validate=validate.Length(equal=64))
    # Deep-path fields produced when
    # PUBLIC_VERIFICATION_DEEP_ENABLED=true.
    reason = fields.String()
    retention_id = fields.Integer()
    asserted_sha256 = fields.String(validate=validate.Length(equal=64))
    timestamp = fields.Dict()
    revocation_observations = fields.List(fields.Dict())
    missing_requirements = fields.List(fields.String())
    certificate_chain = fields.Dict()
    platform_signer_chain = fields.Dict()
