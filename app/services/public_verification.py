"""Deep public PDF verification against the retained validation dossier.

Closes G13 in ``docs/GAP_REMEDIATION_PLAN_2026-11-14.md``. The previous
path only compared the embedded signing certificate's SHA-256 against
the configured pinned value. Deep verification additionally:

* Resolves an :class:`EvidenceRetention` by the caller-supplied
  artifact SHA-256 (no tenant / id enumeration — 256-bit entropy).
* Loads the most recent :class:`ValidationDossier` for that retention
  and the :class:`EvidenceTimestamp`, :class:`OcspEvidence`, and
  :class:`CertificateRevocationEvidence` rows it binds.
* Delegates to :func:`app.services.validation_dossier.verify_dossier`
  so the TSA chain, OCSP, CRL, and platform signer chain are rebuilt
  and compared against the retained manifest hash.
* Hashes the uploaded PDF and demands a match against
  ``retention.artifact_sha256`` before returning ``valid``.

The returned :class:`DeepVerifyResult` is the single verdict the API
layer renders.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.extensions import db
from app.models.certificate_revocation import CertificateRevocationEvidence
from app.models.evidence_preservation import EvidenceRetention
from app.models.evidence_timestamp import EvidenceTimestamp
from app.models.ocsp_evidence import OcspEvidence
from app.models.validation_dossier import ValidationDossier
from app.services import validation_dossier as dossier_service

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class DeepVerifyResult:
    """Structured verdict returned to the API layer.

    ``verdict`` is one of:

    * ``valid`` — PDF bytes match, dossier recomputes identically.
    * ``mismatch`` — retention found but uploaded PDF bytes differ.
    * ``invalid`` — dossier recomputation failed (crypto / tamper).
    * ``unavailable`` — retention found but no dossier yet. Reason
      disambiguates (``no_dossier``, ``no_timestamp``, …).
    * ``unknown`` — no retention matches the supplied digest. Returned
      with the same shape as ``mismatch`` so the caller cannot tell
      whether the digest exists.
    """

    verdict: str
    reason: str | None
    document_sha256: str
    retention_id: int | None = None
    timestamp: dict | None = None
    revocation_observations: list[dict] | None = None
    missing_requirements: list[str] | None = None
    certificate_chain: dict | None = None
    platform_signer_chain: dict | None = None


def deep_verify(
    artifact_sha256: str,
    pdf_bytes: bytes,
    config: Any,
) -> DeepVerifyResult:
    """Run the full dossier-rebuild verification.

    The caller is responsible for rate limiting and request-size
    bounding before invoking this function.
    """
    if (
        not isinstance(artifact_sha256, str)
        or not SHA256_RE.match(artifact_sha256)
        or not isinstance(pdf_bytes, (bytes, bytearray))
        or not pdf_bytes
    ):
        raise ValueError("invalid_input")

    document_sha256 = hashlib.sha256(bytes(pdf_bytes)).hexdigest()

    retention = (
        EvidenceRetention.query.filter_by(artifact_sha256=artifact_sha256)
        .order_by(EvidenceRetention.id.desc())
        .first()
    )
    if retention is None:
        return DeepVerifyResult(
            verdict="unknown",
            reason="retention_not_found",
            document_sha256=document_sha256,
        )

    if document_sha256 != retention.artifact_sha256:
        return DeepVerifyResult(
            verdict="mismatch",
            reason="document_sha256_differs",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )

    dossier = (
        ValidationDossier.query.filter_by(retention_id=retention.id)
        .order_by(ValidationDossier.id.desc())
        .first()
    )
    if dossier is None:
        return DeepVerifyResult(
            verdict="unavailable",
            reason="no_dossier",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )

    timestamp = db.session.get(EvidenceTimestamp, dossier.timestamp_id)
    if timestamp is None:
        return DeepVerifyResult(
            verdict="unavailable",
            reason="no_timestamp",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )

    ocsp_ids = {
        ref.get("id")
        for ref in (dossier.manifest or {}).get("revocation_observations", [])
        if isinstance(ref, dict) and ref.get("type") == "ocsp"
    }
    crl_ids = {
        ref.get("id")
        for ref in (dossier.manifest or {}).get("revocation_observations", [])
        if isinstance(ref, dict) and ref.get("type") == "crl"
    }
    ocsp_rows = (
        OcspEvidence.query.filter(
            OcspEvidence.id.in_(ocsp_ids),
            OcspEvidence.timestamp_id == timestamp.id,
            OcspEvidence.organization_id == retention.organization_id,
        ).all()
        if ocsp_ids
        else []
    )
    crl_rows = (
        CertificateRevocationEvidence.query.filter(
            CertificateRevocationEvidence.id.in_(crl_ids),
            CertificateRevocationEvidence.timestamp_id == timestamp.id,
            CertificateRevocationEvidence.organization_id
            == retention.organization_id,
        ).all()
        if crl_ids
        else []
    )
    if len(ocsp_rows) != len(ocsp_ids) or len(crl_rows) != len(crl_ids):
        return DeepVerifyResult(
            verdict="invalid",
            reason="revocation_evidence_missing",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )

    try:
        manifest = dossier_service.verify_dossier(
            dossier, retention, timestamp, ocsp_rows, crl_rows, config
        )
    except ValueError as exc:
        return DeepVerifyResult(
            verdict="invalid",
            reason=str(exc)[:160] or "dossier_rebuild_failed",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return DeepVerifyResult(
            verdict="invalid",
            reason=f"dossier_verification_failed:{type(exc).__name__}",
            document_sha256=document_sha256,
            retention_id=retention.id,
        )

    return DeepVerifyResult(
        verdict="valid",
        reason=None,
        document_sha256=document_sha256,
        retention_id=retention.id,
        timestamp={
            "gen_time": manifest["timestamp"]["gen_time"],
            "tsa_certificate_sha256": manifest["timestamp"][
                "tsa_certificate_sha256"
            ],
            "token_sha256": manifest["timestamp"]["token_sha256"],
        },
        revocation_observations=[
            {
                "type": item["type"],
                "sha256": item["sha256"],
                "subject_sha256": item["subject_sha256"],
                "checked_at": item["checked_at"],
            }
            for item in manifest.get("revocation_observations", [])
        ],
        missing_requirements=list(manifest.get("missing_requirements", [])),
        certificate_chain=manifest.get("certificate_chain"),
        platform_signer_chain=manifest.get("platform_signer_chain"),
    )
