"""Signing envelope schemas."""
from __future__ import annotations

from marshmallow import Schema, fields, validate


class EnvelopeParticipantSchema(Schema):
    id = fields.Integer(required=True)
    user_id = fields.Integer(required=True)
    role = fields.String(required=True)
    signing_order = fields.Integer(required=True)


class EnvelopeDetailSchema(Schema):
    id = fields.Integer(required=True)
    document_id = fields.Integer(required=True)
    document_blob_id = fields.Integer(required=True)
    document_sha256 = fields.String(
        required=True, validate=validate.Length(equal=64)
    )
    state = fields.String(
        required=True, validate=validate.OneOf(["draft", "prepared", "cancelled"])
    )
    created_by_id = fields.Integer(required=True)
    participants = fields.List(fields.Nested(EnvelopeParticipantSchema), required=True)
    created_at = fields.String(allow_none=True, metadata={"nullable": True})
    prepared_at = fields.String(allow_none=True, metadata={"nullable": True})
    cancelled_at = fields.String(allow_none=True, metadata={"nullable": True})
    assurance = fields.String(
        required=True,
        validate=validate.OneOf(["preparation_only_not_signed"]),
    )
