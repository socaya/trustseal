"""eIDAS 2.0 Electronic Signatures (SES / AES / QES), QTSP/QSCD/CSC v2, EUDI Wallet,
and SignNow-grade Multi-Recipient Send-for-eSignature workflow models.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from app.extensions import db


class QtspProviderConfig(db.Model):
    """Per-organization Qualified Trust Service Provider (QTSP) & Remote QSCD config.

    Supports:
    - CSC API v2.0 remote signing gateways (Cloud Signature Consortium)
    - EUDI Wallet ARF OpenID4VP / OpenID4VCI verifiers & wallet QES issuers
    - Qualified Electronic Seal (QSeal) & RFC 3161 Qualified TSA / OCSP endpoints
    """
    __tablename__ = "qtsp_provider_configs"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(140), nullable=False)
    provider_type = db.Column(db.String(32), nullable=False, default="csc_v2")
    # csc_v2 | eudi_wallet | qualified_seal | tsp_hsm
    country_code = db.Column(db.String(8), nullable=False, default="EU")
    lotl_trust_service_id = db.Column(db.String(180), nullable=True)
    csc_base_url = db.Column(db.String(320), nullable=True)
    oauth_token_url = db.Column(db.String(320), nullable=True)
    oauth_client_id = db.Column(db.String(160), nullable=True)
    eudi_verifier_url = db.Column(db.String(320), nullable=True)
    tsa_url = db.Column(db.String(320), nullable=True)
    ocsp_url = db.Column(db.String(320), nullable=True)
    default_pades_profile = db.Column(db.String(20), nullable=False, default="PAdES-B-LTA")
    # PAdES-B-B | PAdES-B-T | PAdES-B-LT | PAdES-B-LTA
    qscd_certified = db.Column(db.Boolean, nullable=False, default=True)
    lotl_verified = db.Column(db.Boolean, nullable=False, default=True)
    qc_statements_json = db.Column(db.JSON, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "organization_id": self.organization_id,
            "name": self.name,
            "provider_type": self.provider_type,
            "country_code": self.country_code,
            "lotl_trust_service_id": self.lotl_trust_service_id,
            "csc_base_url": self.csc_base_url,
            "eudi_verifier_url": self.eudi_verifier_url,
            "tsa_url": self.tsa_url,
            "ocsp_url": self.ocsp_url,
            "default_pades_profile": self.default_pades_profile,
            "qscd_certified": bool(self.qscd_certified),
            "lotl_verified": bool(self.lotl_verified),
            "qc_statements": self.qc_statements_json or {
                "qc_compliance": "0.4.0.1862.1.1",
                "qc_sscd_qscd": "0.4.0.1862.1.4",
                "qc_type": "0.4.0.1862.1.6.1",
            },
            "is_active": bool(self.is_active),
            "is_default": bool(self.is_default),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SignatureWorkflowPackage(db.Model):
    """SignNow-grade Send-for-eSignature Package with full eIDAS 2.0 & ETSI PAdES support."""
    __tablename__ = "signature_workflow_packages"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_ref = db.Column(db.String(40), nullable=False, unique=True, index=True)
    title = db.Column(db.String(240), nullable=False)

    # Document / Template binding
    source_type = db.Column(db.String(24), nullable=False, default="tsd_document")
    # tsd_document | pdf_upload | template
    source_id = db.Column(db.Integer, nullable=True, index=True)
    document_sha256 = db.Column(db.String(64), nullable=False)

    # Send mode (SignNow features: single invite, CSV bulk invite, shareable signing link, in-person)
    send_mode = db.Column(db.String(24), nullable=False, default="single")
    # single | bulk_batch | invite_link | in_person
    bulk_batch_id = db.Column(db.String(40), nullable=True, index=True)

    # Routing & signing order
    routing_mode = db.Column(db.String(20), nullable=False, default="sequential")
    # sequential | parallel | quorum
    quorum_required = db.Column(db.Integer, nullable=True)

    # eIDAS 2.0 & ETSI PAdES standards configuration
    eidas_level = db.Column(db.String(12), nullable=False, default="AES")
    # SES | AES | QES
    pades_profile = db.Column(db.String(20), nullable=False, default="PAdES-B-LTA")
    # PAdES-B-B | PAdES-B-T | PAdES-B-LT | PAdES-B-LTA
    qtsp_provider_id = db.Column(db.Integer, db.ForeignKey("qtsp_provider_configs.id"), nullable=True)

    # Workflow status
    status = db.Column(db.String(24), nullable=False, default="draft", index=True)
    # draft | sent | in_progress | completed | declined | expired | voided

    # Invitation customization & controls
    email_subject = db.Column(db.String(240), nullable=True)
    email_message = db.Column(db.Text, nullable=True)
    redirect_url = db.Column(db.String(400), nullable=True)
    allow_decline = db.Column(db.Boolean, nullable=False, default=True)
    allow_reassign = db.Column(db.Boolean, nullable=False, default=True)
    require_auth_method = db.Column(db.String(28), nullable=False, default="email_otp")
    # none | email_otp | totp_mfa | passcode | eudi_wallet_pid

    # Expiration & automated reminders (up to 180 days per SignNow standard)
    expires_at = db.Column(db.DateTime, nullable=True)
    reminder_every_days = db.Column(db.Integer, nullable=True, default=3)
    reminder_max_count = db.Column(db.Integer, nullable=True, default=5)
    reminders_sent = db.Column(db.Integer, nullable=False, default=0)
    last_reminded_at = db.Column(db.DateTime, nullable=True)
    pre_expiry_alert_hours = db.Column(db.Integer, nullable=True, default=24)

    # Shareable Signing Link (kiosk / self-service invite link)
    share_link_token = db.Column(db.String(96), nullable=True, unique=True, index=True)
    share_link_max_uses = db.Column(db.Integer, nullable=True)
    share_link_uses = db.Column(db.Integer, nullable=False, default=0)

    # Cryptographic sealing & long-term preservation evidence
    sealed_pdf_sha256 = db.Column(db.String(64), nullable=True)
    tsa_token_digest = db.Column(db.String(64), nullable=True)
    ocsp_status = db.Column(db.String(32), nullable=True)
    lta_archive_digest = db.Column(db.String(64), nullable=True)
    completion_cert_hash = db.Column(db.String(64), nullable=True)

    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    recipients = db.relationship(
        "SignatureWorkflowRecipient",
        backref="package",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="SignatureWorkflowRecipient.signing_order.asc()",
    )
    fields = db.relationship(
        "SignatureWorkflowField",
        backref="package",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    events = db.relationship(
        "SignatureWorkflowEvent",
        backref="package",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="SignatureWorkflowEvent.id.asc()",
    )

    def is_expired(self) -> bool:
        return bool(self.expires_at and datetime.utcnow() > self.expires_at and self.status not in ("completed", "voided"))

    def to_dict(self, include_details: bool = False) -> dict:
        recs = list(self.recipients)
        signed_count = sum(1 for r in recs if r.status == "signed")
        signer_count = sum(1 for r in recs if r.role != "cc")
        data = {
            "id": self.id,
            "package_ref": self.package_ref,
            "title": self.title,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "document_sha256": self.document_sha256,
            "send_mode": self.send_mode,
            "bulk_batch_id": self.bulk_batch_id,
            "routing_mode": self.routing_mode,
            "quorum_required": self.quorum_required,
            "eidas_level": self.eidas_level,
            "pades_profile": self.pades_profile,
            "qtsp_provider_id": self.qtsp_provider_id,
            "status": "expired" if self.is_expired() else self.status,
            "email_subject": self.email_subject,
            "email_message": self.email_message,
            "redirect_url": self.redirect_url,
            "allow_decline": bool(self.allow_decline),
            "allow_reassign": bool(self.allow_reassign),
            "require_auth_method": self.require_auth_method,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reminder_every_days": self.reminder_every_days,
            "reminder_max_count": self.reminder_max_count,
            "reminders_sent": self.reminders_sent,
            "last_reminded_at": self.last_reminded_at.isoformat() if self.last_reminded_at else None,
            "pre_expiry_alert_hours": self.pre_expiry_alert_hours,
            "share_link_token": self.share_link_token,
            "share_link_url": f"/esignatures/link/{self.share_link_token}" if self.share_link_token else None,
            "share_link_max_uses": self.share_link_max_uses,
            "share_link_uses": self.share_link_uses,
            "signed_count": signed_count,
            "signer_count": signer_count,
            "sealed_pdf_sha256": self.sealed_pdf_sha256,
            "tsa_token_digest": self.tsa_token_digest,
            "ocsp_status": self.ocsp_status,
            "lta_archive_digest": self.lta_archive_digest,
            "completion_cert_hash": self.completion_cert_hash,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_details:
            data["recipients"] = [r.to_dict() for r in recs]
            data["fields"] = [f.to_dict() for f in self.fields]
            data["events"] = [e.to_dict() for e in self.events]
        return data


class SignatureWorkflowRecipient(db.Model):
    """Recipient on a Send-for-eSignature workflow with per-signer eIDAS 2.0 level & evidence."""
    __tablename__ = "signature_workflow_recipients"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("signature_workflow_packages.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    email = db.Column(db.String(200), nullable=False, index=True)
    role = db.Column(db.String(24), nullable=False, default="signer")
    # signer | approver | witness | cc | in_person_signer
    signing_order = db.Column(db.Integer, nullable=False, default=1)

    # eIDAS 2.0 assurance level & sole-control authentication
    eidas_level = db.Column(db.String(12), nullable=False, default="AES")
    # SES | AES | QES
    auth_method = db.Column(db.String(28), nullable=False, default="email_otp")
    # none | email_otp | totp_mfa | passcode | eudi_wallet_pid
    auth_passcode_hash = db.Column(db.String(64), nullable=True)
    otp_code_hash = db.Column(db.String(64), nullable=True)
    otp_expires_at = db.Column(db.DateTime, nullable=True)
    otp_verified_at = db.Column(db.DateTime, nullable=True)

    # Secure signing link token
    invite_token = db.Column(db.String(96), nullable=False, unique=True, index=True)

    status = db.Column(db.String(24), nullable=False, default="pending")
    # pending | sent | viewed | authenticated | signed | declined | reassigned | expired
    viewed_at = db.Column(db.DateTime, nullable=True)
    signed_at = db.Column(db.DateTime, nullable=True)
    declined_at = db.Column(db.DateTime, nullable=True)
    decline_reason = db.Column(db.String(400), nullable=True)
    reassigned_to_email = db.Column(db.String(200), nullable=True)

    # Cryptographic & visual signature evidence
    signature_method = db.Column(db.String(32), nullable=True)
    # drawn | typed | uploaded | x509_aes | csc_v2_qscd | eudi_wallet_qes
    signature_appearance = db.Column(db.Text, nullable=True)
    certificate_subject = db.Column(db.String(320), nullable=True)
    certificate_issuer = db.Column(db.String(320), nullable=True)
    certificate_sha256 = db.Column(db.String(64), nullable=True)
    qc_statement_verified = db.Column(db.Boolean, nullable=False, default=False)
    qscd_attestation_id = db.Column(db.String(120), nullable=True)
    csc_sad_digest = db.Column(db.String(64), nullable=True)
    eudi_pid_loa = db.Column(db.String(24), nullable=True)
    signer_ip_hash = db.Column(db.String(64), nullable=True)
    signer_user_agent = db.Column(db.String(255), nullable=True)
    evidence_hash = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_secret(val: str) -> str:
        return hashlib.sha256(val.strip().encode("utf-8")).hexdigest()

    def issue_otp(self, ttl_minutes: int = 15) -> str:
        code = f"{secrets.randbelow(900000) + 100000:06d}"
        self.otp_code_hash = self.hash_secret(code)
        self.otp_expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)
        return code

    def verify_otp(self, code: str) -> bool:
        if not self.otp_code_hash or not self.otp_expires_at:
            return False
        if datetime.utcnow() > self.otp_expires_at:
            return False
        if secrets.compare_digest(self.otp_code_hash, self.hash_secret(code)):
            self.otp_verified_at = datetime.utcnow()
            return True
        return False

    def to_dict(self, include_token: bool = True) -> dict:
        out = {
            "id": self.id,
            "package_id": self.package_id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "signing_order": self.signing_order,
            "eidas_level": self.eidas_level,
            "auth_method": self.auth_method,
            "otp_verified": bool(self.otp_verified_at),
            "status": self.status,
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None,
            "signed_at": self.signed_at.isoformat() if self.signed_at else None,
            "declined_at": self.declined_at.isoformat() if self.declined_at else None,
            "decline_reason": self.decline_reason,
            "reassigned_to_email": self.reassigned_to_email,
            "signature_method": self.signature_method,
            "certificate_subject": self.certificate_subject,
            "certificate_issuer": self.certificate_issuer,
            "certificate_sha256": self.certificate_sha256,
            "qc_statement_verified": bool(self.qc_statement_verified),
            "qscd_attestation_id": self.qscd_attestation_id,
            "eudi_pid_loa": self.eudi_pid_loa,
            "evidence_hash": self.evidence_hash,
        }
        if include_token:
            out["sign_url"] = f"/esignatures/sign/{self.invite_token}"
        return out


class SignatureWorkflowField(db.Model):
    """Fillable document fields assigned to a recipient (SignNow field palette)."""
    __tablename__ = "signature_workflow_fields"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("signature_workflow_packages.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey("signature_workflow_recipients.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    field_type = db.Column(db.String(24), nullable=False, default="signature")
    # signature | initials | date_signed | full_name | text | checkbox | dropdown | stamp | attachment
    label = db.Column(db.String(120), nullable=False, default="Signature")
    page_number = db.Column(db.Integer, nullable=False, default=1)
    x_pct = db.Column(db.Float, nullable=False, default=10.0)
    y_pct = db.Column(db.Float, nullable=False, default=78.0)
    width_pct = db.Column(db.Float, nullable=False, default=26.0)
    height_pct = db.Column(db.Float, nullable=False, default=7.0)
    required = db.Column(db.Boolean, nullable=False, default=True)
    options_json = db.Column(db.JSON, nullable=True)
    value = db.Column(db.Text, nullable=True)
    filled_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "package_id": self.package_id,
            "recipient_id": self.recipient_id,
            "field_type": self.field_type,
            "label": self.label,
            "page_number": self.page_number,
            "x_pct": self.x_pct,
            "y_pct": self.y_pct,
            "width_pct": self.width_pct,
            "height_pct": self.height_pct,
            "required": bool(self.required),
            "options": self.options_json or [],
            "value": self.value,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
        }


class SignatureWorkflowEvent(db.Model):
    """Hash-chained tamper-evident audit trail for every signature workflow action."""
    __tablename__ = "signature_workflow_events"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("signature_workflow_packages.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("signature_workflow_recipients.id", ondelete="SET NULL"), nullable=True)
    event_type = db.Column(db.String(40), nullable=False)
    actor_email = db.Column(db.String(200), nullable=True)
    ip_hash = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details_json = db.Column(db.JSON, nullable=True)
    prev_event_hash = db.Column(db.String(64), nullable=False)
    event_hash = db.Column(db.String(64), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "package_id": self.package_id,
            "recipient_id": self.recipient_id,
            "event_type": self.event_type,
            "actor_email": self.actor_email,
            "ip_hash": self.ip_hash,
            "details": self.details_json or {},
            "prev_event_hash": self.prev_event_hash,
            "event_hash": self.event_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class EudiWalletSession(db.Model):
    """eIDAS 2.0 EUDI Wallet OpenID4VP identity & QES remote-signing session."""
    __tablename__ = "eudi_wallet_sessions"

    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey("organizations.id"), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey("signature_workflow_packages.id", ondelete="CASCADE"), nullable=True, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("signature_workflow_recipients.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = db.Column(db.String(64), nullable=False, unique=True, index=True)
    nonce = db.Column(db.String(64), nullable=False)
    purpose = db.Column(db.String(24), nullable=False, default="qes_signing")
    # pid_identity | qes_signing
    loa_requested = db.Column(db.String(20), nullable=False, default="high")
    loa_verified = db.Column(db.String(20), nullable=True)
    wallet_provider = db.Column(db.String(120), nullable=True)
    openid4vp_uri = db.Column(db.Text, nullable=False)
    document_digest_sha256 = db.Column(db.String(64), nullable=True)
    credential_id = db.Column(db.String(120), nullable=True)
    pid_claims_json = db.Column(db.JSON, nullable=True)
    qes_signature_b64 = db.Column(db.Text, nullable=True)
    certificate_sha256 = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(24), nullable=False, default="pending")
    # pending | presented | authorized | signed | expired | failed
    expires_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "package_id": self.package_id,
            "recipient_id": self.recipient_id,
            "purpose": self.purpose,
            "loa_requested": self.loa_requested,
            "loa_verified": self.loa_verified,
            "wallet_provider": self.wallet_provider,
            "openid4vp_uri": self.openid4vp_uri,
            "document_digest_sha256": self.document_digest_sha256,
            "credential_id": self.credential_id,
            "pid_claims": self.pid_claims_json or {},
            "certificate_sha256": self.certificate_sha256,
            "status": self.status,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


def ensure_eidas_tables() -> None:
    """Create eIDAS 2.0 & Send-for-eSignature workflow tables idempotently."""
    for model in (
        QtspProviderConfig,
        SignatureWorkflowPackage,
        SignatureWorkflowRecipient,
        SignatureWorkflowField,
        SignatureWorkflowEvent,
        EudiWalletSession,
    ):
        try:
            model.__table__.create(db.engine, checkfirst=True)
        except Exception:
            pass
