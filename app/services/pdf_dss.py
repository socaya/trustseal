"""Controlled DSS-only incremental PDF derivative.

No archive timestamp, signer status assertion or PAdES-LT qualification is
implied. The original CMS signed bytes must remain an identical prefix.
"""
import base64
import hashlib
import io

from app.services.platform_pdf_seal import (
    FIELD_NAME, MAX_PDF_BYTES, PdfFinalizationError, inspect_signed_pdf,
)

MAX_EVIDENCE_OBJECTS = 120
MAX_EVIDENCE_BYTES = 3 * 1024 * 1024


class DssEvidenceError(ValueError):
    pass


def _decode(value, limit):
    if not isinstance(value, str) or len(value) > (limit * 4 // 3 + 16):
        raise DssEvidenceError("DSS evidence is not bounded")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise DssEvidenceError("DSS evidence decoding failed") from exc
    if not 0 < len(result) <= limit:
        raise DssEvidenceError("DSS evidence object invalid")
    return result


def collect_dss_material(dossier, ocsp_rows, crl_rows):
    """Collect exactly the evidence records referenced in a verified dossier."""
    manifest = dossier.manifest
    if (manifest.get("complete") is not False
            or manifest.get("assurance") != "partial_tsa_status_evidence_not_full_chain_or_pades_lt"
            or "certificate_chain" not in manifest):
        raise DssEvidenceError("Reviewed certificate-chain dossier required")
    chain = manifest["certificate_chain"]
    certificates = [_decode(value, 32768) for value in
                    chain["certificates_der_b64_leaf_to_root"]]
    expected = chain["certificates_sha256_leaf_to_root"]
    if (len(certificates) != len(expected)
            or not 2 <= len(certificates) <= 6
            or any(hashlib.sha256(cert).hexdigest() != digest
                   for cert, digest in zip(certificates, expected))):
        raise DssEvidenceError("Certificate-chain inventory inconsistent")
    references = manifest.get("revocation_observations", [])
    if not isinstance(references, list) or len(references) > MAX_EVIDENCE_OBJECTS:
        raise DssEvidenceError("Unbounded dossier observation list")
    indexed = {
        ("ocsp", row.id): row for row in ocsp_rows
    }
    indexed.update({("crl", row.id): row for row in crl_rows})
    ocsps, crls = [], []
    seen = set()
    for ref in references:
        key = (ref["type"], ref["id"])
        if key in seen or key not in indexed:
            raise DssEvidenceError("Dossier revocation reference missing or duplicated")
        seen.add(key)
        record = indexed[key]
        if key[0] == "ocsp":
            raw = _decode(record.response_der_b64, 128 * 1024)
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise DssEvidenceError("OCSP source hash differs")
            ocsps.append(raw)
            certificates.append(_decode(record.responder_der_b64, 32768)
                                if record.responder_der_b64 else
                                _decode(record.issuer_der_b64, 32768))
        else:
            raw = _decode(record.crl_der_b64, 512 * 1024)
            if hashlib.sha256(raw).hexdigest() != ref["sha256"]:
                raise DssEvidenceError("CRL source hash differs")
            crls.append(raw)
    platform = manifest.get("platform_signer_chain")
    if platform is not None:
        platform_chain = platform["certificate_chain"]
        platform_certs = [
            _decode(value, 32768)
            for value in platform_chain["certificates_der_b64_leaf_to_root"]
        ]
        platform_digests = platform_chain["certificates_sha256_leaf_to_root"]
        if (len(platform_certs) != len(platform_digests)
                or any(hashlib.sha256(blob).hexdigest() != digest
                       for blob, digest in zip(platform_certs, platform_digests))):
            raise DssEvidenceError("PDF platform signing chain evidence altered")
        certificates.extend(platform_certs)
        platform_crls = platform.get("crl_inventory")
        if platform_crls:
            for observation in platform_crls["observations"]:
                raw = _decode(observation["crl_der_b64"], 512 * 1024)
                if hashlib.sha256(raw).hexdigest() != observation["crl_sha256"]:
                    raise DssEvidenceError("PDF signer CRL bytes altered")
                crls.append(raw)
    chain_crls = manifest.get("chain_revocation")
    if chain_crls is not None:
        for item in chain_crls["observations"]:
            raw = _decode(item["crl_der_b64"], 512 * 1024)
            if hashlib.sha256(raw).hexdigest() != item["crl_sha256"]:
                raise DssEvidenceError("Chain CRL bytes differ")
            crls.append(raw)
    # Deterministic, bounded de-duplication.
    certificates = list(dict.fromkeys(certificates))
    ocsps = list(dict.fromkeys(ocsps))
    crls = list(dict.fromkeys(crls))
    if (not certificates or not (ocsps or crls)
            or len(certificates) + len(ocsps) + len(crls) > MAX_EVIDENCE_OBJECTS
            or sum(map(len, certificates + ocsps + crls)) > MAX_EVIDENCE_BYTES):
        raise DssEvidenceError("Insufficient or oversized validation evidence")
    return certificates, ocsps, crls


def _dss_parts(pdf_bytes):
    from pyhanko.pdf_utils.reader import PdfFileReader
    reader = PdfFileReader(io.BytesIO(pdf_bytes))
    if len(reader.embedded_signatures) != 1:
        raise DssEvidenceError("Exactly one original platform signature is required")
    signature = reader.embedded_signatures[0]
    if signature.field_name != FIELD_NAME:
        raise DssEvidenceError("Unexpected signed PDF field")
    return reader, signature


def append_dss_derivative(signed_pdf, dossier, ocsp_rows, crl_rows, config, *,
                          evidence_sha256, certificate_sha256,
                          evidence_purpose="review"):
    if not isinstance(signed_pdf, bytes) or len(signed_pdf) > MAX_PDF_BYTES:
        raise DssEvidenceError("Original PDF bytes invalid")
    signed_status = inspect_signed_pdf(
        signed_pdf, config, expected_evidence_sha256=evidence_sha256,
        expected_certificate_sha256=certificate_sha256,
        evidence_purpose=evidence_purpose,
    )
    if not signed_status["overall_valid"]:
        raise DssEvidenceError("Source platform signature untrusted")
    cert_der, ocsp_der, crl_der = collect_dss_material(
        dossier, ocsp_rows, crl_rows
    )
    try:
        from asn1crypto import x509, ocsp, crl
        from pyhanko.sign.validation.dss import DocumentSecurityStore
        _, signature = _dss_parts(signed_pdf)
        contents = signature.sig_object.raw_get("/Contents")
        signature_contents = contents.original_bytes
        # The PDF seal signer and TSA certificate hierarchy can differ.
        if signature.signer_cert is None:
            raise DssEvidenceError("Platform seal has no signer certificate")
        certificates = [signature.signer_cert] + [
            x509.Certificate.load(blob, strict=True) for blob in cert_der
        ]
        ocsps = [ocsp.OCSPResponse.load(blob, strict=True) for blob in ocsp_der]
        crls = [crl.CertificateList.load(blob, strict=True) for blob in crl_der]
        output = io.BytesIO(signed_pdf)
        output.seek(0)
        DocumentSecurityStore.add_dss(
            output, signature_contents, certs=certificates,
            ocsps=ocsps, crls=crls, force_write=True,
        )
        derivative = output.getvalue()
        if (not derivative.startswith(signed_pdf)
                or len(derivative) <= len(signed_pdf)
                or len(derivative) > MAX_PDF_BYTES):
            raise DssEvidenceError("DSS did not create a bounded incremental revision")
        reader, modified_sig = _dss_parts(derivative)
        if (modified_sig.sig_object.raw_get("/Contents").original_bytes
                != contents.original_bytes):
            raise DssEvidenceError("Original CMS signature changed")
        store = DocumentSecurityStore.read_dss(reader)
        pdf_dss = reader.root["/DSS"]
        if ("/VRI" not in pdf_dss or not pdf_dss["/VRI"]
                or "/Certs" not in pdf_dss
                or (crls and len(pdf_dss.get("/CRLs", [])) < len(crls))
                or (ocsps and len(pdf_dss.get("/OCSPs", [])) < len(ocsps))):
            raise DssEvidenceError("DSS/VRI validation material incomplete")
        stored_certs = {
            hashlib.sha256(cert.dump()).hexdigest()
            for cert in store.load_certs()
        }
        if not set(hashlib.sha256(blob).hexdigest() for blob in cert_der).issubset(stored_certs):
            raise DssEvidenceError("DSS certificate evidence incomplete")
        confirmed = inspect_signed_pdf(
            derivative, config, expected_evidence_sha256=evidence_sha256,
            expected_certificate_sha256=certificate_sha256,
            evidence_purpose=evidence_purpose,
        )
        if not confirmed["overall_valid"]:
            raise DssEvidenceError("DSS revision invalidates platform seal")
        return derivative
    except (DssEvidenceError, PdfFinalizationError):
        raise
    except Exception as exc:
        raise DssEvidenceError("Incremental DSS construction or validation failed") from exc


def verify_dss_derivative(source_bytes, derivative_bytes, expected_digest, config,
                          *, evidence_sha256, certificate_sha256,
                          evidence_purpose="review"):
    if (not isinstance(derivative_bytes, bytes)
            or hashlib.sha256(derivative_bytes).hexdigest() != expected_digest
            or not derivative_bytes.startswith(source_bytes)
            or len(derivative_bytes) <= len(source_bytes)):
        raise DssEvidenceError("DSS derivative bytes do not match source")
    from pyhanko.sign.validation.dss import DocumentSecurityStore
    reader, _ = _dss_parts(derivative_bytes)
    DocumentSecurityStore.read_dss(reader)
    verdict = inspect_signed_pdf(
        derivative_bytes, config, expected_evidence_sha256=evidence_sha256,
        expected_certificate_sha256=certificate_sha256,
        evidence_purpose=evidence_purpose,
    )
    if not verdict["overall_valid"]:
        raise DssEvidenceError("PDF signature invalid after DSS update")
    return verdict
