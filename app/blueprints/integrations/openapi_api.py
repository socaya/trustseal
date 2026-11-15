"""Serve the generated OpenAPI 3.x document.

``GET /api/openapi.json`` returns the canonical specification used for
contract testing and SDK generation. The document is cacheable (the
schemas only change on code deployment) but we default to ``no-store``
so integration environments never read a stale spec through an
intermediate cache.
"""
from __future__ import annotations

from flask import Blueprint, jsonify

from app.services.openapi import spec_as_dict

openapi_api = Blueprint("openapi_api", __name__, url_prefix="/api")


@openapi_api.route("/openapi.json", methods=["GET"])
def dump():
    response = jsonify(spec_as_dict())
    response.headers["Cache-Control"] = "no-store"
    return response
