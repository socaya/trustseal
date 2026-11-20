"""HTML views for the TSD Stamp Studio.

* ``/stamps``                — tenant stamp library grid
* ``/stamps/templates``      — dedicated template gallery page
* ``/stamps/usage``          — org-wide usage & audit ledger page
* ``/stamps/<id>/usage``     — single-stamp usage & audit page
* ``/stamps/verify``         — dedicated TSD forensic verifier page
* ``/stamps/studio``         — designer (new)
* ``/stamps/studio/<id>``    — designer (edit)
"""
from __future__ import annotations

from flask import Blueprint, abort, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db
from app.models.tsd_stamp import TSDStamp
from app.models.tsd_stamp_insertion import TSDStampInsertion
from app.models.user import User


tsd_stamps_views = Blueprint("tsd_stamps_views", __name__, url_prefix="/stamps")


def _actor():
    if not current_user.is_authenticated:
        abort(401)
    if current_user.organization_id is None:
        abort(403, description="organization_required")
    return current_user


def _stamp_size_label(stamp: TSDStamp) -> str:
    lay = stamp.layout or {}
    if lay.get("width_mm") and lay.get("height_mm"):
        w, h = lay["width_mm"], lay["height_mm"]
        if w == h and stamp.kind in ("seal", "company_dated"):
            return f"Ø {w} mm"
        return f"{w} × {h} mm"
    if lay.get("diameter_mm"):
        return f"Ø {lay['diameter_mm']} mm"
    if lay.get("size_value") and lay["size_value"] != "custom":
        sv = str(lay["size_value"])
        return f"{sv.replace('x', ' × ')} mm" if "x" in sv else f"Ø {sv} mm"
    return "Standard"


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
    usage_counts = dict(
        db.session.query(
            TSDStampInsertion.stamp_id,
            func.count(TSDStampInsertion.id),
        )
        .filter(TSDStampInsertion.organization_id == actor.organization_id)
        .group_by(TSDStampInsertion.stamp_id)
        .all()
    )
    creator_ids = list({r.created_by_id for r in rows if r.created_by_id})
    creator_names = {}
    if creator_ids:
        for u in User.query.filter(User.id.in_(creator_ids)).all():
            full = (u.get_full_name() or "").strip() if hasattr(u, "get_full_name") else ""
            creator_names[u.id] = full or u.username or u.email or f"User #{u.id}"
    stamp_sizes = {r.id: _stamp_size_label(r) for r in rows}
    return render_template(
        "stamps/library.html",
        stamps=rows,
        usage_counts=usage_counts,
        creator_names=creator_names,
        stamp_sizes=stamp_sizes,
    )


@tsd_stamps_views.route("/templates", methods=["GET"])
@login_required
def templates_page():
    _actor()
    return render_template("stamps/templates.html")


@tsd_stamps_views.route("/usage", methods=["GET"])
@login_required
def usage_page():
    actor = _actor()
    stamps = (
        TSDStamp.query
        .filter(TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .order_by(TSDStamp.name.asc())
        .all()
    )
    return render_template("stamps/usage.html", stamp=None, stamps=stamps)


@tsd_stamps_views.route("/<int:stamp_id>/usage", methods=["GET"])
@login_required
def stamp_usage_page(stamp_id: int):
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
    stamps = (
        TSDStamp.query
        .filter(TSDStamp.organization_id == actor.organization_id,
                TSDStamp.deleted_at.is_(None))
        .order_by(TSDStamp.name.asc())
        .all()
    )
    return render_template("stamps/usage.html", stamp=stamp, stamps=stamps)


@tsd_stamps_views.route("/verify", methods=["GET"])
@login_required
def verify_page():
    _actor()
    return render_template("stamps/verify.html")


@tsd_stamps_views.route("/media", methods=["GET"])
@login_required
def media_page():
    return redirect(url_for("workspace_assets_views.media_page"), code=302)


@tsd_stamps_views.route("/letterheads", methods=["GET"])
@login_required
def letterheads_page():
    return redirect(url_for("workspace_assets_views.letterheads_page"), code=302)


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
