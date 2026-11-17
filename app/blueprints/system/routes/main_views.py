from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from app.blueprints.system import system_bp

main_views = Blueprint('main_views', __name__)


@main_views.route('/')
def home():
    """Root route.

    Authenticated users land on the operator overview. Anonymous users
    see the public landing page instead of being bounced to the login
    form — the landing explains the product and provides clear paths
    to "Verify a document" or "Sign in".
    """
    if not current_user.is_authenticated:
        return render_template("public/landing.html")
    return render_template("dashboard.html")


@main_views.route('/welcome')
def welcome():
    """Public landing — always rendered regardless of auth state."""
    return render_template("public/landing.html")


@main_views.route('/trust')
def trust():
    """Public Trust & Security page.

    Canonical statement of what TRUSTSEAL cryptographically proves,
    what it records as workflow evidence, and what it does not claim.
    Linked from the landing hero, every error page and the signer
    footer, so the page must stay public (no auth gating).
    """
    return render_template("public/trust.html")


@main_views.route('/pricing')
def pricing():
    """Public pricing page — honest contact-based quote flow."""
    return render_template("public/pricing.html")
