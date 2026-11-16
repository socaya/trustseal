"""Tenant-scoped SecurityEvent CSV export (Phase T1).

``GET /api/_internal/security-events/export.csv`` streams a CSV of
the caller's organisation's SecurityEvent rows. Compliance teams
export a tenant-scoped slice offline instead of paginating through
the JSON endpoint.

Filters (all optional):
* ``since`` / ``until`` — ISO-8601 timestamps.
* ``actor_id`` — limit to a single user id.
* ``action_prefix`` — case-sensitive prefix of the ``action`` column
  (e.g. ``envelope.`` to pull every envelope event).

The response is streamed with ``Transfer-Encoding: chunked`` so very
large slices never materialise the whole row set in memory. Results
are capped at ``max_rows`` (default 50 000, max 200 000) to keep
auditor exports bounded; callers that need more can paginate with
``since``/``until``.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Blueprint, Response, abort, request, stream_with_context
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.event_delivery import SecurityEvent
from app.policies.api_access import is_admin
from app.services.token_security import active_token_user


security_events_export_api = Blueprint(
    "security_events_export_api",
    __name__,
    url_prefix="/api/_internal/security-events",
)


_MAX_ROWS_DEFAULT = 50_000
_MAX_ROWS_CEILING = 200_000


def _admin_scope():
    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403, description="admin_required")
    if user.organization_id is None:
        abort(403, description="organization_required")
    return user


def _parse_iso(name: str, raw: str | None) -> datetime | None:
    if raw is None or raw == "":
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        abort(400, description=f"{name}_invalid_iso")


def _parse_int(name: str, raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        abort(400, description=f"{name}_not_integer")
    if value < 0:
        abort(400, description=f"{name}_negative")
    return value


@security_events_export_api.route("/export.csv", methods=["GET"])
@jwt_required()
def export_csv():
    user = _admin_scope()
    since = _parse_iso("since", request.args.get("since"))
    until = _parse_iso("until", request.args.get("until"))
    actor_id = _parse_int("actor_id", request.args.get("actor_id"))
    action_prefix = request.args.get("action_prefix")
    if action_prefix is not None and (
        not isinstance(action_prefix, str)
        or len(action_prefix) > 100
        or "\x00" in action_prefix
    ):
        abort(400, description="action_prefix_invalid")
    max_rows = (
        _parse_int("max_rows", request.args.get("max_rows"))
        or _MAX_ROWS_DEFAULT
    )
    if max_rows > _MAX_ROWS_CEILING:
        abort(400, description="max_rows_above_ceiling")

    query = SecurityEvent.query.filter(
        SecurityEvent.organization_id == user.organization_id
    )
    if since is not None:
        query = query.filter(SecurityEvent.created_at >= since)
    if until is not None:
        query = query.filter(SecurityEvent.created_at <= until)
    if actor_id is not None:
        query = query.filter(SecurityEvent.actor_id == actor_id)
    if action_prefix:
        # SQLAlchemy escapes the raw % / _ so this stays safe against
        # operator-supplied wildcards.
        query = query.filter(SecurityEvent.action.like(f"{action_prefix}%"))
    query = query.order_by(SecurityEvent.id.asc()).limit(max_rows)

    @stream_with_context
    def _rows():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "organization_id",
                "actor_id",
                "action",
                "resource_type",
                "resource_id",
                "outcome",
                "correlation_id",
                "created_at",
                "event_hash",
                "prev_event_hash",
            ]
        )
        yield buf.getvalue()
        for row in query.yield_per(500):
            buf.seek(0)
            buf.truncate(0)
            writer.writerow(
                [
                    row.id,
                    row.organization_id,
                    row.actor_id if row.actor_id is not None else "",
                    row.action,
                    row.resource_type,
                    row.resource_id if row.resource_id is not None else "",
                    row.outcome,
                    row.correlation_id,
                    row.created_at.isoformat(),
                    row.event_hash or "",
                    row.prev_event_hash or "",
                ]
            )
            yield buf.getvalue()

    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": (
            f"attachment; filename=\"security-events-"
            f"{user.organization_id}-{datetime.utcnow().date().isoformat()}.csv\""
        ),
        "Cache-Control": "no-store",
    }
    return Response(_rows(), headers=headers)
