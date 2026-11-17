"""TRUSTSEAL design-system gallery.

Internal reference surface. Not linked from the production menus by
default; the route is admin-only so unreleased states cannot be
canvassed by anonymous users.
"""
from __future__ import annotations

from flask import Blueprint, abort, current_app, render_template, url_for
from flask_jwt_extended import jwt_required


design_gallery_bp = Blueprint(
    "design_gallery_bp", __name__, url_prefix="/design"
)


_ASSETS = [
    {
        "key": "primary-horizontal",
        "file": "brand/trustseal/trustseal-horizontal.png",
        "use": "Primary authenticated UI topbar; horizontal lockup without tagline.",
        "bg": "var(--ts-surface)",
    },
    {
        "key": "horizontal-tagline",
        "file": "brand/trustseal/trustseal-horizontal-tagline.png",
        "use": "Public marketing, verification, document cover sheets.",
        "bg": "var(--ts-surface)",
    },
    {
        "key": "stacked-tagline",
        "file": "brand/trustseal/trustseal-stacked-tagline.png",
        "use": "Narrow surfaces where the vertical stack reads better.",
        "bg": "var(--ts-surface)",
    },
    {
        "key": "shield-color",
        "file": "brand/trustseal/trustseal-shield-color.png",
        "use": "Favicon, collapsed sidebar rail, PWA icon.",
        "bg": "var(--ts-canvas)",
    },
    {
        "key": "shield-mono-navy",
        "file": "brand/trustseal/trustseal-shield-mono-navy.png",
        "use": "Minimalist navy shield (document corners, letterhead).",
        "bg": "var(--ts-surface)",
    },
    {
        "key": "horizontal-mono-black",
        "file": "brand/trustseal/trustseal-horizontal-mono-black.png",
        "use": "Monochrome black horizontal lockup — print/grayscale.",
        "bg": "var(--ts-surface)",
    },
    {
        "key": "horizontal-mono-white-on-navy",
        "file": "brand/trustseal/trustseal-horizontal-mono-white-on-navy.png",
        "use": "White lockup on dark surfaces (signer footer, email dark).",
        "bg": "var(--ts-brand-primary)",
    },
    {
        "key": "wordmark-navy",
        "file": "brand/trustseal/trustseal-wordmark-navy.png",
        "use": "Wordmark only — embedded body text where shield is impractical.",
        "bg": "var(--ts-surface)",
    },
]


@design_gallery_bp.route("/gallery", methods=["GET"])
@jwt_required()
def gallery():
    # Only superusers / admins should see this.
    from app.policies.api_access import is_admin
    from app.services.token_security import active_token_user

    user = active_token_user()
    if user is None or not user.is_active:
        abort(401)
    if not is_admin(user.id):
        abort(403)
    return render_template(
        "design/gallery.html",
        assets=_ASSETS,
    )
