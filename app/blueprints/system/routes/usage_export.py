"""Tenant-scoped usage-ledger CSV export (Phase V2).

``GET /api/_internal/usage/export.csv`` streams the caller's
organisation's :class:`UsageLedgerEntry` rows with optional
filters. Operators use this to reconcile usage against their
billing provider offline instead of paginating through the
summary endpoint.

Filters (all optional):
* ``since`` / ``until`` — ISO-8601 timestamps against ``recorded_at``.
* ``meter`` — restrict to a single meter (e.g. ``envelopes.prepared``).
* ``max_rows`` — hard ceiling (default 50 000, max 200 000).

Response is streamed with ``Transfer-Encoding: chunked``.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from flask import Blueprint, Response, abort, request, stream_with_context
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.models.usage_ledger import UsageLedgerEntry
from app.policies.api_access import is_admin
from app.services.token_security import active_token_user


usage_export_api = Blueprint(
    "usage_export_api",
    __name__,
    url_prefix="/api/_internal/usage",
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


@usage_export_api.route("/export.csv", methods=["GET"])
@jwt_required()
def export_csv():
    user = _admin_scope()
    since = _parse_iso("since", request.args.get("since"))
    until = _parse_iso("until", request.args.get("until"))
    meter = request.args.get("meter")
    if meter is not None and (
        not isinstance(meter, str) or len(meter) > 60 or "\x00" in meter
    ):
        abort(400, description="meter_invalid")
    max_rows = (
        _parse_int("max_rows", request.args.get("max_rows"))
        or _MAX_ROWS_DEFAULT
    )
    if max_rows > _MAX_ROWS_CEILING:
        abort(400, description="max_rows_above_ceiling")

    query = UsageLedgerEntry.query.filter(
        UsageLedgerEntry.organization_id == user.organization_id
    )
    if since is not None:
        query = query.filter(UsageLedgerEntry.recorded_at >= since)
    if until is not None:
        query = query.filter(UsageLedgerEntry.recorded_at <= until)
    if meter:
        query = query.filter(UsageLedgerEntry.meter == meter)
    query = query.order_by(UsageLedgerEntry.id.asc()).limit(max_rows)

    @stream_with_context
    def _rows():
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "organization_id",
                "meter",
                "source_event_id",
                "hits",
                "actor_id",
                "recorded_at",
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
                    row.meter,
                    row.source_event_id,
                    row.hits,
                    row.actor_id if row.actor_id is not None else "",
                    row.recorded_at.isoformat(),
                ]
            )
            yield buf.getvalue()

    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": (
            f"attachment; filename=\"usage-"
            f"{user.organization_id}-{datetime.utcnow().date().isoformat()}.csv\""
        ),
        "Cache-Control": "no-store",
    }
    return Response(_rows(), headers=headers)
