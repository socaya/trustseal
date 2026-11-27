"""Web views for the SignNow-grade Send for eSignature & eIDAS 2.0 Studio,
public recipient signing flow, shareable signing links, and Certificate of Completion.
"""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models.eidas_signature import (
    QtspProviderConfig,
    SignatureWorkflowField,
    SignatureWorkflowPackage,
    SignatureWorkflowRecipient,
    ensure_eidas_tables,
)
from app.models.tsd_document import TSDocument as TsdDocument
from app.services.eidas_standards import (
    EIDAS_SIGNATURE_LEVELS,
    PADES_PROFILES,
    append_workflow_event,
    build_certificate_of_completion,
)

send_studio_views = Blueprint(
    "send_studio_views",
    __name__,
    url_prefix="/esignatures",
    template_folder="../../templates",
)


@send_studio_views.route("/send", methods=["GET"])
@login_required
def send_studio():
    """Executive Send for eSignature & eIDAS 2.0 Studio."""
    ensure_eidas_tables()
    org_id = current_user.organization_id
    docs = (
        TsdDocument.query.filter_by(organization_id=org_id, deleted_at=None)
        .order_by(TsdDocument.updated_at.desc())
        .limit(60)
        .all()
    )
    providers = QtspProviderConfig.query.filter_by(organization_id=org_id, is_active=True).all()
    return render_template(
        "esignatures/send_studio.html",
        active_nav_item="send-esign",
        documents=docs,
        eidas_levels=EIDAS_SIGNATURE_LEVELS,
        pades_profiles=PADES_PROFILES,
        providers=providers,
    )


@send_studio_views.route("/sign/<token>", methods=["GET"])
def sign_package_page(token: str):
    """Public token-authorized recipient signing experience (SES / AES / QES)."""
    ensure_eidas_tables()
    rec = SignatureWorkflowRecipient.query.filter_by(invite_token=token).first()
    if not rec:
        abort(404)
    pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)
    if not pkg:
        abort(404)

    if rec.status == "sent" and not rec.viewed_at:
        rec.viewed_at = datetime.utcnow()
        rec.status = "viewed"
        append_workflow_event(
            package=pkg,
            event_type="viewed",
            actor_email=rec.email,
            recipient_id=rec.id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        db.session.commit()

    fields = SignatureWorkflowField.query.filter_by(package_id=pkg.id, recipient_id=rec.id).all()
    eidas_meta = EIDAS_SIGNATURE_LEVELS.get(rec.eidas_level, EIDAS_SIGNATURE_LEVELS["AES"])
    pades_meta = PADES_PROFILES.get(pkg.pades_profile, PADES_PROFILES["PAdES-B-LTA"])
    return render_template(
        "esignatures/sign_package.html",
        package=pkg,
        recipient=rec,
        fields=fields,
        eidas_meta=eidas_meta,
        pades_meta=pades_meta,
        token=token,
    )


@send_studio_views.route("/link/<share_token>", methods=["GET", "POST"])
def share_link_kiosk(share_token: str):
    """Shareable Signing Link (SignNow Invite Link / Kiosk self-enrollment)."""
    ensure_eidas_tables()
    pkg = SignatureWorkflowPackage.query.filter_by(share_link_token=share_token).first()
    if not pkg or pkg.status in ("voided", "declined") or pkg.is_expired():
        abort(404)
    if pkg.share_link_max_uses and pkg.share_link_uses >= pkg.share_link_max_uses:
        abort(410)

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        if name and email and "@" in email:
            rec = SignatureWorkflowRecipient(
                package_id=pkg.id,
                organization_id=pkg.organization_id,
                name=name,
                email=email,
                role="signer",
                signing_order=(pkg.recipients.count() + 1),
                eidas_level=pkg.eidas_level,
                auth_method=pkg.require_auth_method,
                invite_token=SignatureWorkflowRecipient.generate_token(),
                status="sent",
            )
            db.session.add(rec)
            pkg.share_link_uses = (pkg.share_link_uses or 0) + 1
            db.session.flush()
            db.session.add(SignatureWorkflowField(
                package_id=pkg.id,
                recipient_id=rec.id,
                field_type="signature",
                label=f"{name} — Signature ({pkg.eidas_level})",
                page_number=1,
                x_pct=10.0,
                y_pct=78.0,
                width_pct=30.0,
                height_pct=7.5,
                required=True,
            ))
            append_workflow_event(
                package=pkg,
                event_type="link_opened",
                actor_email=email,
                recipient_id=rec.id,
                ip_address=request.remote_addr,
                user_agent=request.headers.get("User-Agent"),
                details={"via": "shareable_signing_link"},
            )
            db.session.commit()
            return redirect(url_for("send_studio_views.sign_package_page", token=rec.invite_token))

    return render_template("esignatures/share_link.html", package=pkg, share_token=share_token)


@send_studio_views.route("/certificate/<package_ref>", methods=["GET"])
def completion_certificate_page(package_ref: str):
    """Printable Tamper-Evident Certificate of Completion & eIDAS 2.0 Audit Trail."""
    ensure_eidas_tables()
    pkg = SignatureWorkflowPackage.query.filter_by(package_ref=package_ref.upper()).first()
    if not pkg:
        abort(404)
    cert = build_certificate_of_completion(pkg)
    return render_template("esignatures/completion_certificate.html", package=pkg, cert=cert)
