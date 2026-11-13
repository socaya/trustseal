"""Safe platform settings API backed by the actual singleton schema.

Secrets and cryptographic/security switches are intentionally unavailable
through this generic endpoint. Provider configuration needs audited workflows.
"""
from flask import abort, jsonify, request

from .. import system_bp
from app.extensions import db
from app.models.system import SystemSettings

PUBLIC_FIELDS = ("platform_name", "terms_url", "privacy_url")


def _serialize(item):
    return {"id": item.id, **{name: getattr(item, name) for name in PUBLIC_FIELDS}}


def _settings():
    item = db.session.get(SystemSettings, 1)
    if item is None:
        item = SystemSettings(id=1)
        db.session.add(item)
        db.session.flush()
    return item


@system_bp.route("/api/settings", methods=["GET"])
def list_settings():
    item = db.session.get(SystemSettings, 1)
    return jsonify([] if item is None else [_serialize(item)])


@system_bp.route("/api/settings/<string:key>", methods=["GET"])
def get_setting_by_key(key):
    if key not in PUBLIC_FIELDS:
        abort(404)
    item = db.session.get(SystemSettings, 1)
    if item is None:
        abort(404)
    return jsonify({"key": key, "value": getattr(item, key)})


@system_bp.route("/api/settings/<string:key>", methods=["PUT"])
def update_setting(key):
    if key not in PUBLIC_FIELDS:
        abort(403, description="Protected settings require governed administration")
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"value"}:
        abort(400, description="Expected JSON object containing value only")
    value = data["value"]
    if value is not None and (not isinstance(value, str) or len(value) > 255):
        abort(400, description="Invalid setting value")
    item = _settings()
    setattr(item, key, value)
    db.session.commit()
    return jsonify({"key": key, "value": getattr(item, key)})
