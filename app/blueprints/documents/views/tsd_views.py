"""TRUSTSEAL document library — HTML views that bracket the TSD API.

* ``/documents/library``          — the library grid
* ``/documents/library/new``      — the editor for a brand-new TSD
* ``/documents/library/<id>``     — the editor loaded with an existing TSD
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.models.tsd_document import TSDocument


tsd_views = Blueprint("tsd_views", __name__, url_prefix="/documents/library")


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


@tsd_views.route("", methods=["GET"])
@login_required
def library():
    actor = _actor()
    rows = (
        TSDocument.query
        .filter(
            TSDocument.organization_id == actor.organization_id,
            TSDocument.deleted_at.is_(None),
        )
        .order_by(TSDocument.updated_at.desc())
        .all()
    )
    return render_template("documents/tsd_library.html", docs=rows)


@tsd_views.route("/new", methods=["GET"])
@login_required
def new():
    _actor()
    return render_template("documents/tsd_editor.html", doc=None)


@tsd_views.route("/<int:tsd_id>", methods=["GET"])
@login_required
def edit(tsd_id: int):
    actor = _actor()
    doc = (
        TSDocument.query
        .filter(
            TSDocument.id == tsd_id,
            TSDocument.organization_id == actor.organization_id,
            TSDocument.deleted_at.is_(None),
        )
        .first()
    )
    if doc is None:
        abort(404)
    return render_template("documents/tsd_editor.html", doc=doc)
