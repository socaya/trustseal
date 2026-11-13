"""Revalidated, bounded PKIX evidence dossiers.

The dossier is a *partial evidence inventory*. It explicitly never infers
full-chain historical PKIX trust or PAdES-LT/LTA from isolated TSA observations.
"""
import hashlib
import json

from app.services.evidence_preservation import artifact_for, verify_artifact
from app.services.rfc3161_timestamp import decode_token, verify_timestamp
from app.services.certificate_revocation import verify_snapshot, _read_pem
from app.services.ocsp_evidence import verify_ocsp_snapshot
from app.services.explicit_certificate_chain import chain_from_config

SCHEMA = "trustseal.validation-dossier.v1"
ASSURANCE = "partial_tsa_status_evidence_not_full_chain_or_pades_lt"
MAX_STATUS_OBSERVATIONS = 100


def digest_manifest(manifest):
    return hashlib.sha256(json.dumps(
        manifest, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _timestamp_proof(timestamp, retention, config):
    if (timestamp.retention_id != retention.id
            or timestamp.organization_id != retention.organization_id
            or timestamp.artifact_sha256 != retention.artifact_sha256):
        raise ValueError("Timestamp and retained artifact do not match")
    proof = verify_timestamp(
        decode_token(timestamp.token_der_b64),
        retention.artifact_sha256, config,
    )
    if (proof["token_sha256"] != timestamp.token_sha256
            or proof["tsa_certificate_sha256"] != timestamp.tsa_certificate_sha256
            or proof["gen_time"] != timestamp.gen_time):
        raise ValueError("Timestamp proof changed")
    return proof


def _approved_observation(record, timestamp, root, *, ocsp):
    if (record.organization_id != timestamp.organization_id
            or record.timestamp_id != timestamp.id or record.status != "good"):
        raise ValueError("Revocation evidence context is inconsistent")
    checked = verify_ocsp_snapshot(record, root) if ocsp else verify_snapshot(record, root)
    if (checked["status"] != "good"
            or checked["subject_certificate_sha256"] != timestamp.tsa_certificate_sha256):
        raise ValueError("Revocation evidence cannot establish a positive observation")
    return {
        "id": record.id,
        "sha256": record.response_sha256 if ocsp else record.crl_sha256,
        "checked_at": record.checked_at.isoformat(timespec="microseconds") + "Z",
        "subject_sha256": checked["subject_certificate_sha256"],
    }


def build_dossier(retention, timestamp, ocsp_rows, crl_rows, config, *,
                  require_original=True, chain_mode="auto"):
    if len(ocsp_rows) > MAX_STATUS_OBSERVATIONS or len(crl_rows) > MAX_STATUS_OBSERVATIONS:
        raise ValueError("Too many revocation evidence observations")
    if require_original:
        source = artifact_for(
            retention.artifact_type, retention.artifact_id, retention.organization_id
        )
        if (source.output_sha256 != retention.artifact_sha256
                or verify_artifact(source, retention.artifact_type, config)
                != retention.artifact_sha256):
            raise ValueError("Retained PDF is not valid")
    proof = _timestamp_proof(timestamp, retention, config)
    root = _read_pem(config.get("RFC3161_TRUST_ROOT_PEM"), "TSA trust root")
    seen = set()
    observations = []
    for kind, records in (("ocsp", ocsp_rows), ("crl", crl_rows)):
        for record in records:
            key = (kind, record.id)
            if key in seen:
                raise ValueError("Repeated revocation observation")
            seen.add(key)
            item = _approved_observation(record, timestamp, root, ocsp=kind == "ocsp")
            observations.append({"type": kind, **item})
    observations.sort(key=lambda item: (item["type"], item["id"]))
    if chain_mode not in ("auto", "included", "none"):
        raise ValueError("Unsupported historical chain verification mode")
    certificate_chain = None
    if chain_mode != "none":
        certificate_chain = chain_from_config(config, timestamp.gen_time)
        if chain_mode == "included" and certificate_chain is None:
            raise ValueError("Historical certificate chain trust config is unavailable")
        if (certificate_chain is not None
                and certificate_chain["leaf_sha256"] != timestamp.tsa_certificate_sha256):
            raise ValueError("Pinned TSA certificate does not match signed timestamp")
    missing = [
        "full_certificate_path_validation",
        "revocation_status_for_each_chain_certificate",
        "historical_trust_list_and_certificate_policy",
        "pades_lt_dss_and_archive_timestamp",
    ]
    if not any(item["type"] == "ocsp" for item in observations):
        missing.append("tsa_ocsp_observation")
    if not any(item["type"] == "crl" for item in observations):
        missing.append("tsa_crl_observation")
    result = {
        "schema": SCHEMA,
        "assurance": ASSURANCE,
        "complete": False,
        "retention_id": retention.id,
        "organization_id": retention.organization_id,
        "artifact": {
            "type": retention.artifact_type,
            "id": retention.artifact_id,
            "sha256": retention.artifact_sha256,
        },
        "timestamp": {
            "id": timestamp.id,
            "token_sha256": proof["token_sha256"],
            "tsa_certificate_sha256": proof["tsa_certificate_sha256"],
            "gen_time": timestamp.gen_time.isoformat(timespec="microseconds") + "Z",
        },
        "revocation_observations": observations,
        "missing_requirements": sorted(missing),
    }
    if certificate_chain is not None:
        result["certificate_chain"] = certificate_chain
    else:
        result["missing_requirements"].append("bounded_explicit_tsa_certificate_path")
        result["missing_requirements"].sort()
    return result


def verify_dossier(dossier, retention, timestamp, ocsp_rows, crl_rows, config):
    manifest = build_dossier(
        retention, timestamp, ocsp_rows, crl_rows, config,
        chain_mode="included" if "certificate_chain" in dossier.manifest else "none",
    )
    if (dossier.retention_id != retention.id
            or dossier.organization_id != retention.organization_id
            or dossier.timestamp_id != timestamp.id
            or dossier.manifest != manifest
            or dossier.manifest_sha256 != digest_manifest(manifest)):
        raise ValueError("Dossier evidence differs from retained signed sources")
    return manifest
