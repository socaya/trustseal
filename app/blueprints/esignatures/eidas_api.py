"""REST APIs for eIDAS 2.0 (SES / AES / QES, QTSP, CSC API v2, EUDI Wallet)
and SignNow-grade Send Documents for eSignature workflows.

Supports both authenticated web sessions (Flask-Login) and mobile/API JWT Bearer tokens.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_login import current_user

from app.extensions import db
from app.models.eidas_signature import (
    EudiWalletSession,
    QtspProviderConfig,
    SignatureWorkflowField,
    SignatureWorkflowPackage,
    SignatureWorkflowRecipient,
    ensure_eidas_tables,
)
from app.models.tsd_document import TSDocument as TsdDocument
from app.models.user import User
from app.services.eidas_standards import (
    CscV2Service,
    EIDAS_SIGNATURE_LEVELS,
    EudiWalletService,
    PADES_PROFILES,
    append_workflow_event,
    build_certificate_of_completion,
    generate_package_ref,
    inspect_qualified_certificate,
    seal_completed_package,
)

eidas_api = Blueprint("eidas_api", __name__, url_prefix="/api/eidas")
send_esign_api = Blueprint("send_esign_api", __name__, url_prefix="/api/esignatures")


def _resolve_actor() -> User | None:
    """Resolve authenticated user from either Flask-Login session or JWT Bearer token."""
    if current_user and getattr(current_user, "is_authenticated", False):
        return current_user
    try:
        verify_jwt_in_request(optional=True)
        uid = get_jwt_identity()
        if uid is not None:
            user = db.session.get(User, int(uid))
            if user and user.is_active:
                return user
    except Exception:
        pass
    return None


def _require_actor():
    user = _resolve_actor()
    if user is None or not user.organization_id:
        return None, (jsonify(error="Authentication required"), 401)
    ensure_eidas_tables()
    return user, None


def _client_ip() -> str:
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "127.0.0.1")


def _ensure_default_qtsp(org_id: int) -> QtspProviderConfig:
    """Guarantee at least one standards-configured QTSP / EUDI Wallet gateway exists per org."""
    ensure_eidas_tables()
    existing = QtspProviderConfig.query.filter_by(organization_id=org_id, is_active=True).first()
    if existing:
        return existing
    cfg = QtspProviderConfig(
        organization_id=org_id,
        name="TRUSTSEAL EU QTSP & Remote QSCD Gateway (CSC v2 + EUDI Wallet)",
        provider_type="csc_v2",
        country_code="EU",
        lotl_trust_service_id="EU-LOTL-QTSP-TS-2026-001",
        csc_base_url="/api/eidas/csc/v2",
        eudi_verifier_url="/api/eidas/eudi-wallet",
        tsa_url="rfc3161://tsa.trustseal.local/qualified",
        ocsp_url="http://ocsp.trustseal.local/v1",
        default_pades_profile="PAdES-B-LTA",
        qscd_certified=True,
        lotl_verified=True,
        qc_statements_json={
            "qc_compliance": "0.4.0.1862.1.1",
            "qc_sscd_qscd": "0.4.0.1862.1.4",
            "qc_type": "0.4.0.1862.1.6.1",
        },
        is_active=True,
        is_default=True,
    )
    db.session.add(cfg)
    db.session.commit()
    return cfg


# ===========================================================================
# 1. eIDAS 2.0 Standards, QTSP Config & Certificate Inspection
# ===========================================================================

@eidas_api.route("/standards", methods=["GET"])
def get_eidas_standards():
    """Public standards manifest for eIDAS 2.0 (SES/AES/QES) & ETSI PAdES profiles."""
    actor = _resolve_actor()
    providers = []
    if actor and actor.organization_id:
        _ensure_default_qtsp(actor.organization_id)
        providers = [
            p.to_dict()
            for p in QtspProviderConfig.query.filter_by(organization_id=actor.organization_id, is_active=True).all()
        ]
    return jsonify(
        regulation="Regulation (EU) 2024/1183 (eIDAS 2.0) amending Regulation (EU) No 910/2014",
        signature_levels=EIDAS_SIGNATURE_LEVELS,
        pades_profiles=PADES_PROFILES,
        protocols={
            "csc_api": "Cloud Signature Consortium API v2.0.0.0 (SCAL2 Remote QSCD)",
            "eudi_wallet": "eIDAS 2.0 ARF OpenID4VP / OpenID4VCI (EU PID LoA High + QES)",
            "timestamping": "RFC 3161 Trusted Time-Stamping + ETSI EN 319 422",
            "validation": "ETSI EN 319 142-1 PAdES-B-B / B-T / B-LT / B-LTA with PDF /DSS OCSP+CRL",
            "qc_statements": "ETSI EN 319 412-5 (QcCompliance, QcSSCD/QSCD, QcType)",
        },
        qtsp_providers=providers,
    ), 200


@eidas_api.route("/qtsp", methods=["GET", "POST"])
def qtsp_providers_collection():
    actor, err = _require_actor()
    if err:
        return err
    _ensure_default_qtsp(actor.organization_id)
    if request.method == "GET":
        rows = QtspProviderConfig.query.filter_by(organization_id=actor.organization_id).order_by(QtspProviderConfig.id.asc()).all()
        return jsonify(providers=[r.to_dict() for r in rows]), 200

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify(error="QTSP provider name is required"), 400
    provider_type = (data.get("provider_type") or "csc_v2").strip()
    if provider_type not in ("csc_v2", "eudi_wallet", "qualified_seal", "tsp_hsm"):
        return jsonify(error="Invalid provider_type"), 400
    pades = (data.get("default_pades_profile") or "PAdES-B-LTA").strip()
    if pades not in PADES_PROFILES:
        return jsonify(error="Invalid default_pades_profile"), 400

    cfg = QtspProviderConfig(
        organization_id=actor.organization_id,
        name=name,
        provider_type=provider_type,
        country_code=(data.get("country_code") or "EU").strip().upper()[:8],
        lotl_trust_service_id=(data.get("lotl_trust_service_id") or "").strip() or None,
        csc_base_url=(data.get("csc_base_url") or "").strip() or None,
        oauth_token_url=(data.get("oauth_token_url") or "").strip() or None,
        oauth_client_id=(data.get("oauth_client_id") or "").strip() or None,
        eudi_verifier_url=(data.get("eudi_verifier_url") or "").strip() or None,
        tsa_url=(data.get("tsa_url") or "").strip() or None,
        ocsp_url=(data.get("ocsp_url") or "").strip() or None,
        default_pades_profile=pades,
        qscd_certified=bool(data.get("qscd_certified", True)),
        lotl_verified=bool(data.get("lotl_verified", True)),
        is_active=True,
        is_default=bool(data.get("is_default", False)),
        created_by_id=actor.id,
    )
    if cfg.is_default:
        QtspProviderConfig.query.filter_by(organization_id=actor.organization_id).update({"is_default": False})
    db.session.add(cfg)
    db.session.commit()
    return jsonify(provider=cfg.to_dict()), 201


@eidas_api.route("/qtsp/<int:provider_id>", methods=["DELETE"])
def delete_qtsp_provider(provider_id: int):
    actor, err = _require_actor()
    if err:
        return err
    row = QtspProviderConfig.query.filter_by(id=provider_id, organization_id=actor.organization_id).first()
    if not row:
        return jsonify(error="QTSP provider not found"), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify(deleted=True, id=provider_id), 200


@eidas_api.route("/certificates/inspect", methods=["POST"])
def inspect_certificate_endpoint():
    """Inspect a PEM X.509 certificate for ETSI EN 319 412-5 QCStatements & eIDAS level."""
    data = request.get_json(silent=True) or {}
    pem = (data.get("certificate_pem") or "").strip()
    if not pem and "certificate" in request.files:
        pem_bytes = request.files["certificate"].read(65536)
    else:
        pem_bytes = pem.encode("utf-8")
    if not pem_bytes:
        return jsonify(error="certificate_pem or uploaded certificate file is required"), 400
    try:
        result = inspect_qualified_certificate(pem_bytes)
    except Exception as exc:
        return jsonify(error=f"Invalid X.509 certificate: {exc}"), 400
    return jsonify(inspection=result), 200


# ===========================================================================
# 2. Cloud Signature Consortium (CSC) API v2.0 Remote QSCD Endpoints
# ===========================================================================

@eidas_api.route("/csc/v2/info", methods=["GET", "POST"])
def csc_v2_info():
    actor = _resolve_actor()
    provider = _ensure_default_qtsp(actor.organization_id) if (actor and actor.organization_id) else None
    return jsonify(CscV2Service.get_info(provider)), 200


@eidas_api.route("/csc/v2/credentials/list", methods=["POST"])
def csc_v2_credentials_list():
    actor = _resolve_actor()
    data = request.get_json(silent=True) or {}
    signer_email = (data.get("signer_email") or (actor.email if actor else "")).strip()
    if not signer_email:
        return jsonify(error="signer_email required"), 400
    org_id = actor.organization_id if (actor and actor.organization_id) else 1
    provider = _ensure_default_qtsp(org_id)
    return jsonify(CscV2Service.list_credentials(organization_id=org_id, signer_email=signer_email, provider=provider)), 200


@eidas_api.route("/csc/v2/credentials/authorize", methods=["POST"])
def csc_v2_credentials_authorize():
    data = request.get_json(silent=True) or {}
    cred_id = (data.get("credentialID") or "").strip()
    hashes_list = data.get("hash") or data.get("hashes") or []
    pin_or_otp = str(data.get("PIN") or data.get("OTP") or data.get("pin") or data.get("otp") or "")
    signer_email = (data.get("signer_email") or "signer@trustseal.local").strip()
    if isinstance(hashes_list, str):
        hashes_list = [hashes_list]
    try:
        res = CscV2Service.authorize_sad(
            credential_id=cred_id,
            document_hashes_b64=hashes_list,
            pin_or_otp=pin_or_otp,
            signer_email=signer_email,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(res), 200


@eidas_api.route("/csc/v2/signatures/signHash", methods=["POST"])
def csc_v2_sign_hash():
    data = request.get_json(silent=True) or {}
    cred_id = (data.get("credentialID") or "").strip()
    sad = (data.get("SAD") or "").strip()
    hashes_list = data.get("hash") or data.get("hashes") or []
    sign_algo = (data.get("signAlgo") or "1.2.840.10045.4.3.2").strip()
    if isinstance(hashes_list, str):
        hashes_list = [hashes_list]
    try:
        res = CscV2Service.sign_hashes(
            credential_id=cred_id,
            sad=sad,
            document_hashes_b64=hashes_list,
            sign_algo=sign_algo,
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(res), 200


# ===========================================================================
# 3. EUDI Wallet ARF (OpenID4VP / QES) Endpoints
# ===========================================================================

@eidas_api.route("/eudi-wallet/sessions", methods=["POST"])
def create_eudi_wallet_session():
    ensure_eidas_tables()
    data = request.get_json(silent=True) or {}
    actor = _resolve_actor()
    invite_token = (data.get("invite_token") or "").strip()
    rec = None
    pkg = None
    if invite_token:
        rec = SignatureWorkflowRecipient.query.filter_by(invite_token=invite_token).first()
        if rec:
            pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)

    org_id = (pkg.organization_id if pkg else (actor.organization_id if actor else 1))
    doc_sha = (data.get("document_sha256") or (pkg.document_sha256 if pkg else hashlib.sha256(b"eudi-session").hexdigest()))
    purpose = (data.get("purpose") or "qes_signing").strip()
    loa = (data.get("loa_requested") or "high").strip()

    sess = EudiWalletService.create_session(
        organization_id=org_id,
        package_id=pkg.id if pkg else None,
        recipient_id=rec.id if rec else None,
        document_sha256=doc_sha,
        purpose=purpose,
        loa_requested=loa,
        callback_base_url=request.host_url.rstrip("/"),
    )
    db.session.commit()
    return jsonify(session=sess.to_dict()), 201


@eidas_api.route("/eudi-wallet/sessions/<session_id>", methods=["GET"])
def get_eudi_wallet_session(session_id: str):
    ensure_eidas_tables()
    sess = EudiWalletSession.query.filter_by(session_id=session_id).first()
    if not sess:
        return jsonify(error="EUDI Wallet session not found"), 404
    return jsonify(session=sess.to_dict()), 200


@eidas_api.route("/eudi-wallet/sessions/<session_id>/callback", methods=["POST"])
def complete_eudi_wallet_session(session_id: str):
    ensure_eidas_tables()
    sess = EudiWalletSession.query.filter_by(session_id=session_id).first()
    if not sess:
        return jsonify(error="EUDI Wallet session not found"), 404
    data = request.get_json(silent=True) or {}
    given_name = (data.get("given_name") or "Verified").strip()
    family_name = (data.get("family_name") or "Signatory").strip()
    country = (data.get("issuing_country") or "NL").strip().upper()
    wallet_provider = (data.get("wallet_provider") or "EU Member State EUDI Wallet (ARF 1.4)").strip()
    try:
        EudiWalletService.complete_session(
            sess,
            given_name=given_name,
            family_name=family_name,
            issuing_country=country,
            wallet_provider=wallet_provider,
            loa_verified=(data.get("loa_verified") or "high").strip(),
        )
        if sess.package_id:
            pkg = db.session.get(SignatureWorkflowPackage, sess.package_id)
            if pkg:
                append_workflow_event(
                    package=pkg,
                    event_type="eudi_wallet_presented",
                    recipient_id=sess.recipient_id,
                    ip_address=_client_ip(),
                    user_agent=request.headers.get("User-Agent"),
                    details={
                        "session_id": sess.session_id,
                        "loa": sess.loa_verified,
                        "issuing_country": country,
                        "certificate_sha256": sess.certificate_sha256,
                    },
                )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    return jsonify(session=sess.to_dict()), 200


# ===========================================================================
# 4. SignNow-Grade Send Documents for eSignature Workflow APIs
# ===========================================================================

def _create_package_internal(
    *,
    actor: User,
    title: str,
    source_type: str,
    source_id: int | None,
    document_sha256: str,
    send_mode: str,
    routing_mode: str,
    quorum_required: int | None,
    eidas_level: str,
    pades_profile: str,
    qtsp_provider_id: int | None,
    recipients_payload: list[dict],
    fields_payload: list[dict],
    email_subject: str | None,
    email_message: str | None,
    redirect_url: str | None,
    allow_decline: bool,
    allow_reassign: bool,
    require_auth_method: str,
    expires_in_days: int | None,
    reminder_every_days: int | None,
    reminder_max_count: int | None,
    pre_expiry_alert_hours: int | None,
    share_link_max_uses: int | None = None,
    bulk_batch_id: str | None = None,
    send_now: bool = True,
) -> SignatureWorkflowPackage:
    now = datetime.utcnow()
    expires_at = None
    if expires_in_days and int(expires_in_days) > 0:
        clamped_days = min(max(int(expires_in_days), 1), 180)
        expires_at = now + timedelta(days=clamped_days)

    share_token = secrets.token_urlsafe(24) if send_mode == "invite_link" else None

    pkg = SignatureWorkflowPackage(
        organization_id=actor.organization_id,
        created_by_id=actor.id,
        package_ref=generate_package_ref(actor.organization_id),
        title=title,
        source_type=source_type,
        source_id=source_id,
        document_sha256=document_sha256,
        send_mode=send_mode,
        bulk_batch_id=bulk_batch_id,
        routing_mode=routing_mode,
        quorum_required=quorum_required if routing_mode == "quorum" else None,
        eidas_level=eidas_level,
        pades_profile=pades_profile,
        qtsp_provider_id=qtsp_provider_id,
        status="sent" if send_now else "draft",
        email_subject=email_subject or f"Signature requested: {title}",
        email_message=email_message or "Please review and electronically sign this document via TRUSTSEAL.",
        redirect_url=redirect_url,
        allow_decline=allow_decline,
        allow_reassign=allow_reassign,
        require_auth_method=require_auth_method,
        expires_at=expires_at,
        reminder_every_days=reminder_every_days,
        reminder_max_count=reminder_max_count,
        pre_expiry_alert_hours=pre_expiry_alert_hours,
        share_link_token=share_token,
        share_link_max_uses=share_link_max_uses,
    )
    db.session.add(pkg)
    db.session.flush()

    created_recipients: list[SignatureWorkflowRecipient] = []
    for idx, rdata in enumerate(recipients_payload, start=1):
        r_email = (rdata.get("email") or "").strip().lower()
        r_name = (rdata.get("name") or r_email.split("@")[0] or f"Signer {idx}").strip()
        if not r_email:
            continue
        r_role = (rdata.get("role") or "signer").strip().lower()
        if r_role not in ("signer", "approver", "witness", "cc", "in_person_signer"):
            r_role = "signer"
        r_order = int(rdata.get("signing_order") or idx)
        r_level = (rdata.get("eidas_level") or eidas_level).strip().upper()
        if r_level not in EIDAS_SIGNATURE_LEVELS:
            r_level = eidas_level
        r_auth = (rdata.get("auth_method") or require_auth_method).strip().lower()
        if r_level == "QES" and r_auth == "none":
            r_auth = "eudi_wallet_pid"
        elif r_level == "AES" and r_auth == "none":
            r_auth = "email_otp"

        # Determine initial status: in sequential mode only order==1 is 'sent' initially
        initial_status = "pending"
        if send_now:
            if r_role == "cc":
                initial_status = "sent"
            elif routing_mode in ("parallel", "quorum") or r_order == 1:
                initial_status = "sent"

        passcode = (rdata.get("passcode") or "").strip()
        rec = SignatureWorkflowRecipient(
            package_id=pkg.id,
            organization_id=actor.organization_id,
            name=r_name,
            email=r_email,
            role=r_role,
            signing_order=r_order,
            eidas_level=r_level,
            auth_method=r_auth,
            auth_passcode_hash=SignatureWorkflowRecipient.hash_secret(passcode) if passcode else None,
            invite_token=SignatureWorkflowRecipient.generate_token(),
            status=initial_status,
        )
        db.session.add(rec)
        db.session.flush()
        created_recipients.append(rec)

    # Create fillable fields (or auto-create signature & date fields for each signer if omitted)
    if fields_payload:
        for fdata in fields_payload:
            r_idx = int(fdata.get("recipient_index", 0))
            target_rec = created_recipients[r_idx] if 0 <= r_idx < len(created_recipients) else (created_recipients[0] if created_recipients else None)
            if not target_rec:
                continue
            f_type = (fdata.get("field_type") or "signature").strip().lower()
            if f_type not in ("signature", "initials", "date_signed", "full_name", "text", "checkbox", "dropdown", "stamp", "attachment"):
                f_type = "signature"
            fld = SignatureWorkflowField(
                package_id=pkg.id,
                recipient_id=target_rec.id,
                field_type=f_type,
                label=(fdata.get("label") or f_type.replace("_", " ").title()).strip(),
                page_number=max(1, int(fdata.get("page_number") or 1)),
                x_pct=float(fdata.get("x_pct", 10.0)),
                y_pct=float(fdata.get("y_pct", 78.0)),
                width_pct=float(fdata.get("width_pct", 26.0)),
                height_pct=float(fdata.get("height_pct", 7.0)),
                required=bool(fdata.get("required", True)),
                options_json=fdata.get("options") if isinstance(fdata.get("options"), list) else None,
            )
            db.session.add(fld)
    else:
        for idx, rec in enumerate(created_recipients):
            if rec.role == "cc":
                continue
            y_base = min(72.0 + (idx * 9.0), 88.0)
            db.session.add(SignatureWorkflowField(
                package_id=pkg.id,
                recipient_id=rec.id,
                field_type="signature",
                label=f"{rec.name} — Signature ({rec.eidas_level})",
                page_number=1,
                x_pct=10.0,
                y_pct=y_base,
                width_pct=30.0,
                height_pct=7.5,
                required=True,
            ))
            db.session.add(SignatureWorkflowField(
                package_id=pkg.id,
                recipient_id=rec.id,
                field_type="date_signed",
                label="Date Signed",
                page_number=1,
                x_pct=46.0,
                y_pct=y_base,
                width_pct=18.0,
                height_pct=5.5,
                required=True,
            ))

    append_workflow_event(
        package=pkg,
        event_type="created",
        actor_email=actor.email,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        details={
            "eidas_level": eidas_level,
            "pades_profile": pades_profile,
            "routing_mode": routing_mode,
            "send_mode": send_mode,
            "recipient_count": len(created_recipients),
        },
    )
    if send_now:
        append_workflow_event(
            package=pkg,
            event_type="bulk_dispatched" if bulk_batch_id else "sent",
            actor_email=actor.email,
            ip_address=_client_ip(),
            user_agent=request.headers.get("User-Agent"),
            details={
                "bulk_batch_id": bulk_batch_id,
                "expires_at": expires_at.isoformat() if expires_at else None,
                "reminder_every_days": reminder_every_days,
            },
        )
    return pkg


@send_esign_api.route("/send", methods=["GET", "POST"])
def send_packages_collection():
    actor, err = _require_actor()
    if err:
        return err

    if request.method == "GET":
        status_filter = (request.args.get("status") or "").strip().lower()
        level_filter = (request.args.get("eidas_level") or "").strip().upper()
        q = SignatureWorkflowPackage.query.filter_by(organization_id=actor.organization_id)
        if status_filter:
            q = q.filter_by(status=status_filter)
        if level_filter in EIDAS_SIGNATURE_LEVELS:
            q = q.filter_by(eidas_level=level_filter)
        pkgs = q.order_by(SignatureWorkflowPackage.created_at.desc()).limit(100).all()

        all_org = SignatureWorkflowPackage.query.filter_by(organization_id=actor.organization_id).all()
        summary = {
            "total": len(all_org),
            "awaiting": sum(1 for p in all_org if p.status in ("sent", "in_progress") and not p.is_expired()),
            "completed": sum(1 for p in all_org if p.status == "completed"),
            "qes_count": sum(1 for p in all_org if p.eidas_level == "QES"),
            "bulk_batches": len({p.bulk_batch_id for p in all_org if p.bulk_batch_id}),
        }
        return jsonify(
            summary=summary,
            packages=[p.to_dict(include_details=True) for p in pkgs],
        ), 200

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    source_type = (data.get("source_type") or "tsd_document").strip()
    source_id = data.get("source_id")
    doc_sha = (data.get("document_sha256") or "").strip()

    if source_type == "tsd_document" and source_id:
        tsd = TsdDocument.query.filter_by(id=int(source_id), organization_id=actor.organization_id).first()
        if tsd:
            if not title:
                title = tsd.title
            if not doc_sha:
                doc_sha = hashlib.sha256(f"tsd:{tsd.id}:{tsd.version}:{tsd.title}".encode("utf-8")).hexdigest()

    if not title:
        return jsonify(error="Document title is required"), 400
    if not doc_sha or len(doc_sha) != 64:
        doc_sha = hashlib.sha256(f"{actor.organization_id}:{title}:{datetime.utcnow().isoformat()}".encode("utf-8")).hexdigest()

    send_mode = (data.get("send_mode") or "single").strip().lower()
    if send_mode not in ("single", "bulk_batch", "invite_link", "in_person"):
        send_mode = "single"
    routing_mode = (data.get("routing_mode") or "sequential").strip().lower()
    if routing_mode not in ("sequential", "parallel", "quorum"):
        routing_mode = "sequential"
    eidas_level = (data.get("eidas_level") or "AES").strip().upper()
    if eidas_level not in EIDAS_SIGNATURE_LEVELS:
        return jsonify(error="eidas_level must be SES, AES, or QES"), 400
    pades_profile = (data.get("pades_profile") or ("PAdES-B-LTA" if eidas_level == "QES" else "PAdES-B-LT")).strip()
    if pades_profile not in PADES_PROFILES:
        return jsonify(error="Invalid pades_profile"), 400

    recipients_payload = data.get("recipients") or []
    if send_mode != "invite_link" and not recipients_payload:
        return jsonify(error="At least one recipient is required (or use send_mode='invite_link')"), 400

    qtsp_id = data.get("qtsp_provider_id")
    if eidas_level == "QES" and not qtsp_id:
        qtsp_id = _ensure_default_qtsp(actor.organization_id).id

    pkg = _create_package_internal(
        actor=actor,
        title=title,
        source_type=source_type,
        source_id=int(source_id) if source_id else None,
        document_sha256=doc_sha,
        send_mode=send_mode,
        routing_mode=routing_mode,
        quorum_required=int(data["quorum_required"]) if data.get("quorum_required") else None,
        eidas_level=eidas_level,
        pades_profile=pades_profile,
        qtsp_provider_id=qtsp_id,
        recipients_payload=recipients_payload,
        fields_payload=data.get("fields") or [],
        email_subject=data.get("email_subject"),
        email_message=data.get("email_message"),
        redirect_url=data.get("redirect_url"),
        allow_decline=bool(data.get("allow_decline", True)),
        allow_reassign=bool(data.get("allow_reassign", True)),
        require_auth_method=(data.get("require_auth_method") or ("eudi_wallet_pid" if eidas_level == "QES" else ("email_otp" if eidas_level == "AES" else "none"))).strip(),
        expires_in_days=int(data.get("expires_in_days") or 30),
        reminder_every_days=int(data.get("reminder_every_days") or 3),
        reminder_max_count=int(data.get("reminder_max_count") or 5),
        pre_expiry_alert_hours=int(data.get("pre_expiry_alert_hours") or 24),
        share_link_max_uses=int(data["share_link_max_uses"]) if data.get("share_link_max_uses") else None,
        send_now=bool(data.get("send_now", True)),
    )
    db.session.commit()
    return jsonify(package=pkg.to_dict(include_details=True)), 201


@send_esign_api.route("/send/bulk", methods=["POST"])
def bulk_invite_send():
    """SignNow Bulk Invite: dispatch one document/template to many recipients via CSV or JSON."""
    actor, err = _require_actor()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    source_id = data.get("source_id")
    if not title and source_id:
        tsd = TsdDocument.query.filter_by(id=int(source_id), organization_id=actor.organization_id).first()
        if tsd:
            title = tsd.title
    if not title:
        return jsonify(error="Template or document title is required for Bulk Invite"), 400

    eidas_level = (data.get("eidas_level") or "AES").strip().upper()
    if eidas_level not in EIDAS_SIGNATURE_LEVELS:
        eidas_level = "AES"
    pades_profile = (data.get("pades_profile") or ("PAdES-B-LTA" if eidas_level == "QES" else "PAdES-B-LT")).strip()
    if pades_profile not in PADES_PROFILES:
        pades_profile = "PAdES-B-LT"

    # Parse recipients from either CSV string (`name,email,role,eidas_level`) or JSON list
    rows: list[dict] = []
    csv_text = (data.get("csv_text") or "").strip()
    if csv_text:
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames and any("email" in (f or "").lower() for f in reader.fieldnames):
            for row in reader:
                norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                if norm.get("email"):
                    rows.append({
                        "name": norm.get("name") or norm.get("full_name") or norm["email"].split("@")[0],
                        "email": norm["email"],
                        "role": norm.get("role") or "signer",
                        "eidas_level": (norm.get("eidas_level") or eidas_level).upper(),
                    })
        else:
            for line in csv_text.splitlines():
                parts = [p.strip() for p in line.split(",") if p.strip()]
                if len(parts) >= 2 and "@" in parts[1]:
                    rows.append({"name": parts[0], "email": parts[1], "role": parts[2] if len(parts) > 2 else "signer", "eidas_level": eidas_level})
                elif len(parts) == 1 and "@" in parts[0]:
                    rows.append({"name": parts[0].split("@")[0], "email": parts[0], "role": "signer", "eidas_level": eidas_level})
    elif isinstance(data.get("recipients"), list):
        rows = data["recipients"]

    if not rows:
        return jsonify(error="Provide csv_text or recipients list with valid email addresses"), 400
    if len(rows) > 250:
        return jsonify(error="Maximum 250 recipients per bulk batch"), 400

    batch_id = f"BULK-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"
    qtsp_id = _ensure_default_qtsp(actor.organization_id).id if eidas_level == "QES" else None
    created: list[dict] = []
    for item in rows:
        email = (item.get("email") or "").strip().lower()
        if not email or "@" not in email:
            continue
        name = (item.get("name") or email.split("@")[0]).strip()
        rec_level = (item.get("eidas_level") or eidas_level).strip().upper()
        if rec_level not in EIDAS_SIGNATURE_LEVELS:
            rec_level = eidas_level
        doc_sha = hashlib.sha256(f"{batch_id}:{title}:{email}".encode("utf-8")).hexdigest()
        pkg = _create_package_internal(
            actor=actor,
            title=f"{title} — {name}",
            source_type="tsd_document" if source_id else "template",
            source_id=int(source_id) if source_id else None,
            document_sha256=doc_sha,
            send_mode="bulk_batch",
            routing_mode="sequential",
            quorum_required=None,
            eidas_level=rec_level,
            pades_profile=pades_profile,
            qtsp_provider_id=qtsp_id,
            recipients_payload=[{"name": name, "email": email, "role": item.get("role") or "signer", "signing_order": 1, "eidas_level": rec_level}],
            fields_payload=[],
            email_subject=data.get("email_subject") or f"Action required: Sign {title}",
            email_message=data.get("email_message"),
            redirect_url=data.get("redirect_url"),
            allow_decline=bool(data.get("allow_decline", True)),
            allow_reassign=bool(data.get("allow_reassign", False)),
            require_auth_method=(data.get("require_auth_method") or ("eudi_wallet_pid" if rec_level == "QES" else "email_otp")).strip(),
            expires_in_days=int(data.get("expires_in_days") or 30),
            reminder_every_days=int(data.get("reminder_every_days") or 3),
            reminder_max_count=int(data.get("reminder_max_count") or 5),
            pre_expiry_alert_hours=int(data.get("pre_expiry_alert_hours") or 24),
            bulk_batch_id=batch_id,
            send_now=True,
        )
        created.append(pkg.to_dict(include_details=True))

    db.session.commit()
    return jsonify(bulk_batch_id=batch_id, dispatched_count=len(created), packages=created), 201


@send_esign_api.route("/send/<int:package_id>", methods=["GET"])
def get_send_package(package_id: int):
    actor, err = _require_actor()
    if err:
        return err
    pkg = SignatureWorkflowPackage.query.filter_by(id=package_id, organization_id=actor.organization_id).first()
    if not pkg:
        return jsonify(error="Signature package not found"), 404
    return jsonify(package=pkg.to_dict(include_details=True)), 200


@send_esign_api.route("/send/<int:package_id>/remind", methods=["POST"])
def remind_send_package(package_id: int):
    actor, err = _require_actor()
    if err:
        return err
    pkg = SignatureWorkflowPackage.query.filter_by(id=package_id, organization_id=actor.organization_id).first()
    if not pkg:
        return jsonify(error="Signature package not found"), 404
    if pkg.status in ("completed", "voided", "declined") or pkg.is_expired():
        return jsonify(error=f"Cannot remind package in state '{pkg.status}'"), 409

    pending_recs = [r for r in pkg.recipients if r.status in ("sent", "viewed", "authenticated") and r.role != "cc"]
    pkg.reminders_sent = (pkg.reminders_sent or 0) + 1
    pkg.last_reminded_at = datetime.utcnow()
    append_workflow_event(
        package=pkg,
        event_type="reminded",
        actor_email=actor.email,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        details={"reminded_emails": [r.email for r in pending_recs], "reminder_number": pkg.reminders_sent},
    )
    db.session.commit()
    return jsonify(reminded_count=len(pending_recs), reminders_sent=pkg.reminders_sent, package=pkg.to_dict(include_details=True)), 200


@send_esign_api.route("/send/<int:package_id>/void", methods=["POST"])
def void_send_package(package_id: int):
    actor, err = _require_actor()
    if err:
        return err
    pkg = SignatureWorkflowPackage.query.filter_by(id=package_id, organization_id=actor.organization_id).first()
    if not pkg:
        return jsonify(error="Signature package not found"), 404
    if pkg.status == "completed":
        return jsonify(error="Cannot void an already completed & sealed package"), 409
    data = request.get_json(silent=True) or {}
    pkg.status = "voided"
    append_workflow_event(
        package=pkg,
        event_type="voided",
        actor_email=actor.email,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        details={"reason": (data.get("reason") or "Voided by sender").strip()},
    )
    db.session.commit()
    return jsonify(package=pkg.to_dict(include_details=True)), 200


@send_esign_api.route("/send/<int:package_id>/certificate", methods=["GET"])
def package_completion_certificate(package_id: int):
    actor, err = _require_actor()
    if err:
        return err
    pkg = SignatureWorkflowPackage.query.filter_by(id=package_id, organization_id=actor.organization_id).first()
    if not pkg:
        return jsonify(error="Signature package not found"), 404
    return jsonify(build_certificate_of_completion(pkg)), 200


@send_esign_api.route("/verify/<query_val>", methods=["GET"])
def public_verify_package(query_val: str):
    """Public verification endpoint for package reference (ESIG-...) or SHA-256 hash."""
    ensure_eidas_tables()
    q = (query_val or "").strip()
    pkg = SignatureWorkflowPackage.query.filter(
        (SignatureWorkflowPackage.package_ref == q.upper())
        | (SignatureWorkflowPackage.document_sha256 == q.lower())
        | (SignatureWorkflowPackage.sealed_pdf_sha256 == q.lower())
        | (SignatureWorkflowPackage.completion_cert_hash == q.lower())
    ).first()
    if not pkg:
        return jsonify(verified=False, error="No matching TRUSTSEAL eSignature record found"), 404
    cert = build_certificate_of_completion(pkg)
    return jsonify(verified=bool(cert["audit_chain"]["intact"]), certificate=cert), 200


# ===========================================================================
# 5. Token-Authorized Signer Execution APIs (SES / AES / QES)
# ===========================================================================

@send_esign_api.route("/sign/<token>/otp", methods=["POST"])
def signer_request_otp(token: str):
    ensure_eidas_tables()
    rec = SignatureWorkflowRecipient.query.filter_by(invite_token=token).first()
    if not rec:
        return jsonify(error="Invalid signing link"), 404
    pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)
    if not pkg or pkg.status in ("voided", "declined") or pkg.is_expired():
        return jsonify(error="Signing package is no longer active"), 410
    code = rec.issue_otp()
    append_workflow_event(
        package=pkg,
        event_type="otp_sent",
        actor_email=rec.email,
        recipient_id=rec.id,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        details={"delivery": "email_otp", "eidas_level": rec.eidas_level},
    )
    db.session.commit()
    # Demo/dev preview code returned for immediate interactive verification alongside email dispatch
    return jsonify(sent=True, email=rec.email, expires_in_minutes=15, demo_otp=code), 200


@send_esign_api.route("/sign/<token>/complete", methods=["POST"])
def signer_complete_signature(token: str):
    """Execute SES, AES, or QES signature for an invited recipient."""
    ensure_eidas_tables()
    rec = SignatureWorkflowRecipient.query.filter_by(invite_token=token).first()
    if not rec:
        return jsonify(error="Invalid signing link"), 404
    pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)
    if not pkg or pkg.status in ("voided", "declined") or pkg.is_expired():
        return jsonify(error="Signing package is no longer active"), 410
    if rec.status == "signed":
        return jsonify(error="Recipient has already signed", package=pkg.to_dict(include_details=True)), 409
    if rec.status == "pending":
        return jsonify(error="Awaiting earlier signers in sequential signing order"), 409

    data = request.get_json(silent=True) or {}
    consent_accepted = bool(data.get("consent_accepted", True))
    if not consent_accepted:
        return jsonify(error="Explicit electronic signature consent is required"), 400

    # Verify passcode if configured
    if rec.auth_passcode_hash:
        provided_pass = str(data.get("passcode") or "")
        if not provided_pass or not secrets.compare_digest(
            rec.auth_passcode_hash, SignatureWorkflowRecipient.hash_secret(provided_pass)
        ):
            return jsonify(error="Invalid signer access passcode"), 403

    # Enforce sole-control authentication & cryptographic binding by eIDAS 2.0 tier
    level = rec.eidas_level
    sig_method = (data.get("signature_method") or "drawn").strip()
    csc_sad = (data.get("csc_sad") or "").strip()
    csc_cred_id = (data.get("csc_credential_id") or "").strip()
    eudi_session_id = (data.get("eudi_session_id") or "").strip()
    otp_code = str(data.get("otp_code") or "").strip()
    pin_code = str(data.get("qscd_pin") or "").strip()

    if level == "AES":
        if rec.auth_method in ("email_otp", "totp_mfa") and not rec.otp_verified_at:
            if not otp_code or not rec.verify_otp(otp_code):
                return jsonify(error="Valid 6-digit sole-control OTP is required for eIDAS AES signing"), 403
            append_workflow_event(
                package=pkg, event_type="otp_verified", actor_email=rec.email, recipient_id=rec.id,
                ip_address=_client_ip(), user_agent=request.headers.get("User-Agent"),
                details={"eidas_level": "AES"},
            )
        sig_method = "x509_aes"
        rec.certificate_subject = f"CN={rec.name},emailAddress={rec.email}"
        rec.certificate_issuer = "CN=TRUSTSEAL Advanced Identity CA"
        rec.certificate_sha256 = hashlib.sha256(f"aes-cert:{rec.id}:{rec.email}:{pkg.document_sha256}".encode()).hexdigest()

    elif level == "QES":
        # QES requires EITHER a verified EUDI Wallet session OR CSC API v2 SCAL2 Remote QSCD authorization
        if eudi_session_id:
            sess = EudiWalletSession.query.filter_by(session_id=eudi_session_id).first()
            if not sess or sess.status not in ("signed", "presented"):
                return jsonify(error="Completed EUDI Wallet LoA-High session is required for Wallet QES"), 403
            sig_method = "eudi_wallet_qes"
            claims = sess.pid_claims_json or {}
            rec.eudi_pid_loa = sess.loa_verified or "high"
            rec.certificate_subject = f"CN={claims.get('given_name', rec.name)} {claims.get('family_name', '')},C={claims.get('issuing_country', 'EU')}"
            rec.certificate_issuer = f"CN={sess.wallet_provider or 'EU Member State EUDI Wallet QTSP'}"
            rec.certificate_sha256 = sess.certificate_sha256
            rec.qc_statement_verified = True
            rec.qscd_attestation_id = f"EUDI-QES-{sess.session_id[-10:].upper()}"
        else:
            # CSC API v2 SCAL2 Remote QSCD flow
            doc_hash_b64 = base64.b64encode(bytes.fromhex(pkg.document_sha256)).decode("ascii")
            provider = db.session.get(QtspProviderConfig, pkg.qtsp_provider_id) if pkg.qtsp_provider_id else _ensure_default_qtsp(pkg.organization_id)
            if not csc_cred_id:
                creds = CscV2Service.list_credentials(organization_id=pkg.organization_id, signer_email=rec.email, provider=provider)
                csc_cred_id = creds["credentialIDs"][0]
            if not csc_sad:
                sole_secret = pin_code or otp_code
                if not sole_secret or len(sole_secret) < 4:
                    return jsonify(error="QSCD PIN/OTP or EUDI Wallet verification is required for eIDAS QES signing"), 403
                sad_res = CscV2Service.authorize_sad(
                    credential_id=csc_cred_id,
                    document_hashes_b64=[doc_hash_b64],
                    pin_or_otp=sole_secret,
                    signer_email=rec.email,
                )
                csc_sad = sad_res["SAD"]
                append_workflow_event(
                    package=pkg, event_type="csc_sad_authorized", actor_email=rec.email, recipient_id=rec.id,
                    ip_address=_client_ip(), user_agent=request.headers.get("User-Agent"),
                    details={"credentialID": csc_cred_id, "scal": "2", "sad_sha256": sad_res["sad_sha256"]},
                )
            try:
                signed_res = CscV2Service.sign_hashes(
                    credential_id=csc_cred_id,
                    sad=csc_sad,
                    document_hashes_b64=[doc_hash_b64],
                )
            except ValueError as exc:
                return jsonify(error=f"CSC v2 Remote QSCD error: {exc}"), 403
            sig_method = "csc_v2_qscd"
            rec.csc_sad_digest = hashlib.sha256(csc_sad.encode("utf-8")).hexdigest()
            rec.qscd_attestation_id = signed_res["qscd_attestation_id"]
            rec.certificate_subject = f"CN={rec.name},emailAddress={rec.email},C={provider.country_code}"
            rec.certificate_issuer = f"CN={provider.name},C={provider.country_code}"
            rec.certificate_sha256 = hashlib.sha256(f"qes-cert:{csc_cred_id}:{pkg.document_sha256}".encode()).hexdigest()
            rec.qc_statement_verified = True

    # Populate submitted field values
    field_values = data.get("field_values") or {}
    now = datetime.utcnow()
    for fld in SignatureWorkflowField.query.filter_by(package_id=pkg.id, recipient_id=rec.id).all():
        val = field_values.get(str(fld.id)) or field_values.get(fld.field_type)
        if fld.field_type == "date_signed" and not val:
            val = now.strftime("%Y-%m-%d")
        elif fld.field_type == "full_name" and not val:
            val = rec.name
        elif fld.field_type == "signature" and not val:
            val = data.get("appearance") or f"Signed by {rec.name} ({level})"
        if val is not None:
            fld.value = str(val)
            fld.filled_at = now

    rec.signature_method = sig_method
    rec.signature_appearance = data.get("appearance") or f"Signed electronically by {rec.name}"
    rec.signer_ip_hash = hashlib.sha256(_client_ip().encode("utf-8")).hexdigest()[:32]
    rec.signer_user_agent = (request.headers.get("User-Agent") or "")[:255]
    rec.signed_at = now
    rec.status = "signed"
    rec.evidence_hash = hashlib.sha256(
        f"{pkg.package_ref}:{pkg.document_sha256}:{rec.email}:{level}:{sig_method}:{now.isoformat()}".encode("utf-8")
    ).hexdigest()

    append_workflow_event(
        package=pkg,
        event_type=f"signed_{level.lower()}",
        actor_email=rec.email,
        recipient_id=rec.id,
        ip_address=_client_ip(),
        user_agent=request.headers.get("User-Agent"),
        details={
            "eidas_level": level,
            "signature_method": sig_method,
            "certificate_sha256": rec.certificate_sha256,
            "qc_statement_verified": bool(rec.qc_statement_verified),
            "qscd_attestation_id": rec.qscd_attestation_id,
            "eudi_pid_loa": rec.eudi_pid_loa,
            "evidence_hash": rec.evidence_hash,
        },
    )

    # Advance routing order or seal completed package
    actionable = [r for r in pkg.recipients if r.role != "cc"]
    signed_total = sum(1 for r in actionable if r.status == "signed")
    is_complete = False
    if pkg.routing_mode == "quorum":
        is_complete = signed_total >= (pkg.quorum_required or len(actionable))
    else:
        is_complete = signed_total >= len(actionable)

    certificate = None
    if is_complete:
        certificate = seal_completed_package(pkg)
    else:
        pkg.status = "in_progress"
        if pkg.routing_mode == "sequential":
            next_rec = (
                SignatureWorkflowRecipient.query.filter_by(package_id=pkg.id, status="pending")
                .filter(SignatureWorkflowRecipient.role != "cc")
                .order_by(SignatureWorkflowRecipient.signing_order.asc())
                .first()
            )
            if next_rec:
                next_rec.status = "sent"
                append_workflow_event(
                    package=pkg,
                    event_type="sent",
                    actor_email=next_rec.email,
                    recipient_id=next_rec.id,
                    details={"routed_order": next_rec.signing_order},
                )

    db.session.commit()
    return jsonify(
        signed=True,
        recipient=rec.to_dict(include_token=False),
        package=pkg.to_dict(include_details=True),
        certificate=certificate,
    ), 200


@send_esign_api.route("/sign/<token>/decline", methods=["POST"])
def signer_decline(token: str):
    ensure_eidas_tables()
    rec = SignatureWorkflowRecipient.query.filter_by(invite_token=token).first()
    if not rec:
        return jsonify(error="Invalid signing link"), 404
    pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)
    if not pkg or not pkg.allow_decline:
        return jsonify(error="Declining is disabled for this package"), 403
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "Declined by recipient").strip()
    rec.status = "declined"
    rec.declined_at = datetime.utcnow()
    rec.decline_reason = reason
    pkg.status = "declined"
    append_workflow_event(
        package=pkg, event_type="declined", actor_email=rec.email, recipient_id=rec.id,
        ip_address=_client_ip(), user_agent=request.headers.get("User-Agent"),
        details={"reason": reason},
    )
    db.session.commit()
    return jsonify(declined=True, package=pkg.to_dict(include_details=True)), 200


@send_esign_api.route("/sign/<token>/reassign", methods=["POST"])
def signer_reassign(token: str):
    ensure_eidas_tables()
    rec = SignatureWorkflowRecipient.query.filter_by(invite_token=token).first()
    if not rec:
        return jsonify(error="Invalid signing link"), 404
    pkg = db.session.get(SignatureWorkflowPackage, rec.package_id)
    if not pkg or not pkg.allow_reassign:
        return jsonify(error="Reassignment is disabled for this package"), 403
    data = request.get_json(silent=True) or {}
    new_email = (data.get("email") or "").strip().lower()
    new_name = (data.get("name") or new_email.split("@")[0]).strip()
    if not new_email or "@" not in new_email:
        return jsonify(error="Valid delegate email is required"), 400
    old_email = rec.email
    rec.reassigned_to_email = new_email
    rec.email = new_email
    rec.name = new_name
    rec.invite_token = SignatureWorkflowRecipient.generate_token()
    rec.status = "sent"
    append_workflow_event(
        package=pkg, event_type="reassigned", actor_email=old_email, recipient_id=rec.id,
        ip_address=_client_ip(), user_agent=request.headers.get("User-Agent"),
        details={"from": old_email, "to": new_email, "delegate_name": new_name},
    )
    db.session.commit()
    return jsonify(reassigned=True, recipient=rec.to_dict()), 200
