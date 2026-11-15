"""Authenticated evidence dossier viewer.

Renders every preservation artifact associated with a retained PDF in
one navigable tree. Tenant scoping is enforced through the per-resource
policy predicates in :mod:`app.policies.authorization`.

Routes:

* ``GET /evidence/retentions`` — list of retentions the actor can read.
* ``GET /evidence/retentions/<id>`` — the dossier for one retention.

No JSON export happens here; those endpoints already exist under
``/api/evidence/*``. This surface is for a human operator or compliance
officer.
"""
from __future__ import annotations

from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models.certificate_revocation import CertificateRevocationEvidence
from app.models.evidence_preservation import (
    EvidenceCheckpoint,
    EvidenceLegalHold,
    EvidenceRetention,
)
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.ocsp_evidence import OcspEvidence
from app.models.pdf_dss_derivative import PdfDssDerivative
from app.models.validation_dossier import ValidationDossier

evidence_views = Blueprint(
    "evidence_views",
    __name__,
    url_prefix="/evidence",
    template_folder="../../../templates",
)


def _actor_tenant() -> int:
    """Resolve the caller's tenant for an HTML view route.

    Views authenticate through Flask-Login (session cookie) rather than
    JWT, so we read ``current_user`` directly. ``@login_required`` is
    already applied on each route and will reject anonymous callers
    before this helper runs; the explicit check here is a defence-in-
    depth guard for untenanted users.
    """
    if not current_user.is_authenticated:
        abort(401)
    tenant_id = getattr(current_user, "organization_id", None)
    if tenant_id is None:
        abort(403)
    return int(tenant_id)


@evidence_views.route("/retentions", methods=["GET"])
@login_required
def list_retentions():
    tenant_id = _actor_tenant()
    rows = (
        EvidenceRetention.query.filter_by(organization_id=tenant_id)
        .order_by(EvidenceRetention.id.desc())
        .limit(200)
        .all()
    )
    return render_template("trust/evidence_list.html", retentions=rows)


@evidence_views.route("/retentions/<int:retention_id>", methods=["GET"])
@login_required
def show_retention(retention_id: int):
    tenant_id = _actor_tenant()
    retention = EvidenceRetention.query.filter_by(
        id=retention_id, organization_id=tenant_id
    ).first()
    if retention is None:
        # 404 for anti-enumeration (ADR 0003).
        abort(404)

    holds = (
        EvidenceLegalHold.query.filter_by(
            retention_id=retention.id, organization_id=tenant_id
        )
        .order_by(EvidenceLegalHold.id.desc())
        .all()
    )
    checkpoints = (
        EvidenceCheckpoint.query.filter_by(
            retention_id=retention.id, organization_id=tenant_id
        )
        .order_by(EvidenceCheckpoint.id.desc())
        .all()
    )
    timestamps = (
        EvidenceTimestamp.query.filter_by(
            retention_id=retention.id, organization_id=tenant_id
        )
        .order_by(EvidenceTimestamp.id.desc())
        .all()
    )
    timestamp_ids = [t.id for t in timestamps]
    ocsp_rows = (
        OcspEvidence.query.filter(
            OcspEvidence.timestamp_id.in_(timestamp_ids),
            OcspEvidence.organization_id == tenant_id,
        ).all()
        if timestamp_ids
        else []
    )
    crl_rows = (
        CertificateRevocationEvidence.query.filter(
            CertificateRevocationEvidence.timestamp_id.in_(timestamp_ids),
            CertificateRevocationEvidence.organization_id == tenant_id,
        ).all()
        if timestamp_ids
        else []
    )
    dossiers = (
        ValidationDossier.query.filter_by(
            retention_id=retention.id, organization_id=tenant_id
        )
        .order_by(ValidationDossier.id.desc())
        .all()
    )
    dss_rows = (
        PdfDssDerivative.query.filter_by(
            retention_id=retention.id, organization_id=tenant_id
        )
        .order_by(PdfDssDerivative.id.desc())
        .all()
    )

    # The chained-hash integrity check is a lightweight scan: each
    # checkpoint payload must declare its predecessor's digest. If the
    # chain is broken, surface it in the template so a reviewer sees it
    # immediately rather than discovering it only via the API.
    integrity = _check_checkpoint_chain(checkpoints)

    return render_template(
        "trust/evidence_show.html",
        retention=retention,
        holds=holds,
        checkpoints=checkpoints,
        timestamps=timestamps,
        ocsp_rows=ocsp_rows,
        crl_rows=crl_rows,
        dossiers=dossiers,
        dss_rows=dss_rows,
        integrity=integrity,
    )


def _check_checkpoint_chain(checkpoints: list[EvidenceCheckpoint]) -> dict:
    """Walk checkpoints newest-to-oldest and surface chain inconsistencies.

    The service that signs checkpoints is responsible for the full
    verification; this is a surface-level sanity probe. A break in the
    chain is flagged, but a passing probe is not a cryptographic
    guarantee — a dedicated verifier is still required for that.
    """
    if not checkpoints:
        return {"status": "no_checkpoints", "break_at": None}
    ordered = sorted(checkpoints, key=lambda c: c.id)
    previous_digest = None
    for checkpoint in ordered:
        declared = (checkpoint.payload or {}).get("previous_digest")
        if previous_digest is not None and declared not in (previous_digest, None):
            return {"status": "chain_break", "break_at": checkpoint.id}
        previous_digest = (checkpoint.payload or {}).get("digest")
    return {"status": "chain_ok", "break_at": None}
