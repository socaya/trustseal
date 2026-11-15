"""RFC 7807 problem+json schema."""
from __future__ import annotations

from marshmallow import Schema, fields


class ProblemDetailSchema(Schema):
    type = fields.String(required=True, metadata={"description": "Problem type URI"})
    title = fields.String(required=True)
    status = fields.Integer(required=True)
    instance = fields.String(required=True)
    detail = fields.String()
    request_id = fields.String()
