"""HTML views for the TSD Stamp Studio.

* ``/stamps``            — tenant stamp library grid
* ``/stamps/studio``     — designer (new)
* ``/stamps/studio/<id>``— designer (edit)
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.models.tsd_stamp import TSDStamp


tsd_stamps_views = Blueprint("tsd_stamps_views", __name__, url_prefix="/stamps")


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


@tsd_stamps_views.route("", methods=["GET"])
@login_required
def library():
    actor = _actor()
    rows = (
        TSDStamp.query
        .filter(TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .order_by(TSDStamp.updated_at.desc())
        .all()
    )
    return render_template("stamps/library.html", stamps=rows)


@tsd_stamps_views.route("/studio", methods=["GET"])
@login_required
def studio_new():
    _actor()
    return render_template("stamps/studio.html", stamp=None)


@tsd_stamps_views.route("/studio/<int:stamp_id>", methods=["GET"])
@login_required
def studio_edit(stamp_id: int):
    actor = _actor()
    stamp = (
        TSDStamp.query
        .filter(TSDStamp.id == stamp_id,
                TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .first()
    )
    if stamp is None:
        abort(404)
    return render_template("stamps/studio.html", stamp=stamp)
