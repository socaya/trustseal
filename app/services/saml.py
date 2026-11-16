"""SAML 2.0 Service Provider.

Scope (deliberately narrow, security-first):

* SP-initiated flow only.
* HTTP-Redirect binding for the AuthnRequest (unsigned from the SP).
* HTTP-POST binding for the Response (signed by the IdP).
* Replay protection via a unique index on
  ``(provider_id, assertion_id)``.
* Strict `Audience`, `NotOnOrAfter`, `NotBefore`, `InResponseTo`
  (when supplied) and `Recipient` checks.

Out of scope for this phase (tracked in the remaining-gaps doc):

* SP-signed AuthnRequests.
* Encrypted assertions.
* Single Logout (SLO).
* IdP-initiated flow (unsolicited responses).

Signature verification uses ``signxml`` — a pure-Python XML-DSig
implementation that depends on ``lxml`` + ``cryptography`` only, so
TrustSeal does not require ``libxmlsec1`` to be installed on the
host.
"""
from __future__ import annotations

import base64
import secrets
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Optional
from urllib.parse import urlencode

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from lxml import etree
from signxml import XMLVerifier

from app.extensions import db
from app.models.saml_provider import SamlConsumedAssertion, SamlProvider


NS = {
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}


class SamlError(Exception):
    """Policy or signature failure during SAML response processing."""


@dataclass(frozen=True)
class SamlAssertion:
    """Validated SAML assertion extracted from an IdP response."""

    assertion_id: str
    name_id: str
    attributes: Mapping[str, list[str]]
    not_on_or_after: datetime
    in_response_to: Optional[str]
    issuer: str


# ----------------------------------------------------------- AuthnRequest


def build_authn_request(
    provider: SamlProvider,
    *,
    acs_url: str,
    relay_state: Optional[str] = None,
) -> tuple[str, str]:
    """Return ``(redirect_url, request_id)`` for an SP-initiated login.

    The AuthnRequest is DEFLATE-compressed + base64-encoded + URL-safe
    per the HTTP-Redirect binding (SAMLBindings §3.4).
    """
    request_id = "_" + uuid.uuid4().hex
    issued_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    root = etree.Element(
        "{%s}AuthnRequest" % NS["samlp"],
        nsmap={"samlp": NS["samlp"], "saml": NS["saml"]},
        ID=request_id,
        Version="2.0",
        IssueInstant=issued_at,
        Destination=provider.sso_url,
        AssertionConsumerServiceURL=acs_url,
        ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
    )
    issuer = etree.SubElement(root, "{%s}Issuer" % NS["saml"])
    issuer.text = provider.audience
    xml = etree.tostring(root, xml_declaration=False, encoding="utf-8")
    # DEFLATE without headers (raw) per SAMLBindings §3.4.4.1.
    compressed = zlib.compress(xml)[2:-4]
    encoded = base64.b64encode(compressed).decode("ascii")
    params = {"SAMLRequest": encoded}
    if relay_state:
        params["RelayState"] = relay_state
    separator = "&" if "?" in provider.sso_url else "?"
    return f"{provider.sso_url}{separator}{urlencode(params)}", request_id


# ----------------------------------------------------------- Response


def consume_response(
    provider: SamlProvider,
    *,
    saml_response_b64: str,
    acs_url: str,
    expected_in_response_to: Optional[str] = None,
    now: Optional[datetime] = None,
) -> SamlAssertion:
    """Validate a signed SAMLResponse and return the extracted assertion.

    Raises :class:`SamlError` with a machine-readable reason on every
    policy failure. The caller commits the ``SamlConsumedAssertion``
    row the service adds to the session.
    """
    moment = now or datetime.utcnow()
    try:
        raw = base64.b64decode(saml_response_b64, validate=True)
    except Exception as exc:
        raise SamlError("response_not_base64") from exc

    # Parse defensively — `resolve_entities` disabled by default in lxml
    # ≥4.7 but be explicit.
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, huge_tree=False
    )
    try:
        tree = etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise SamlError("response_malformed") from exc

    if not tree.tag.endswith("}Response"):
        raise SamlError("response_wrong_root_element")

    # Verify the enveloped XML-DSig signature. ``signxml`` returns the
    # verified subtree — reject anything outside it below (defends
    # against XML signature-wrapping attacks because we only trust the
    # verifier's returned ``signed_xml``).
    try:
        cert = _load_cert(provider.x509_cert_pem)
    except Exception as exc:
        raise SamlError("provider_cert_invalid") from exc
    try:
        verifier = XMLVerifier()
        result = verifier.verify(
            raw,
            x509_cert=cert,
            expect_references=1,
        )
    except Exception as exc:
        raise SamlError("signature_invalid") from exc
    signed = result.signed_xml
    if signed is None:
        raise SamlError("no_signed_element")

    # The signed subtree is the <Assertion>.
    if not signed.tag.endswith("}Assertion"):
        raise SamlError("signed_element_not_assertion")

    assertion_id = signed.get("ID")
    if not assertion_id:
        raise SamlError("assertion_missing_id")

    issuer_el = signed.find("{%s}Issuer" % NS["saml"])
    if issuer_el is None or (issuer_el.text or "").strip() != provider.entity_id:
        raise SamlError("issuer_mismatch")

    subject = signed.find("{%s}Subject" % NS["saml"])
    if subject is None:
        raise SamlError("assertion_missing_subject")
    name_id_el = subject.find("{%s}NameID" % NS["saml"])
    if name_id_el is None or not (name_id_el.text or "").strip():
        raise SamlError("subject_missing_name_id")
    name_id = name_id_el.text.strip()

    # SubjectConfirmationData checks: Recipient + NotOnOrAfter +
    # InResponseTo (when supplied).
    confirmation_data = subject.find(
        ".//{%s}SubjectConfirmationData" % NS["saml"]
    )
    if confirmation_data is None:
        raise SamlError("subject_confirmation_missing")
    recipient = confirmation_data.get("Recipient")
    if recipient != acs_url:
        raise SamlError("recipient_mismatch")
    not_on_or_after_raw = confirmation_data.get("NotOnOrAfter")
    if not not_on_or_after_raw:
        raise SamlError("not_on_or_after_missing")
    not_on_or_after = _parse_iso(not_on_or_after_raw)
    if moment >= not_on_or_after:
        raise SamlError("assertion_expired")
    if expected_in_response_to is not None:
        if confirmation_data.get("InResponseTo") != expected_in_response_to:
            raise SamlError("in_response_to_mismatch")

    # Conditions — validate NotBefore / NotOnOrAfter + Audience.
    conditions = signed.find("{%s}Conditions" % NS["saml"])
    if conditions is None:
        raise SamlError("conditions_missing")
    not_before_raw = conditions.get("NotBefore")
    if not_before_raw and moment < _parse_iso(not_before_raw):
        raise SamlError("assertion_not_yet_valid")
    conditions_not_on_or_after_raw = conditions.get("NotOnOrAfter")
    if (
        conditions_not_on_or_after_raw
        and moment >= _parse_iso(conditions_not_on_or_after_raw)
    ):
        raise SamlError("assertion_expired_conditions")
    audience_restriction = conditions.find(
        ".//{%s}AudienceRestriction" % NS["saml"]
    )
    if audience_restriction is None:
        raise SamlError("audience_restriction_missing")
    audiences = [
        (el.text or "").strip()
        for el in audience_restriction.findall("{%s}Audience" % NS["saml"])
    ]
    if provider.audience not in audiences:
        raise SamlError("audience_mismatch")

    # Attributes.
    attrs: dict[str, list[str]] = {}
    attr_statement = signed.find("{%s}AttributeStatement" % NS["saml"])
    if attr_statement is not None:
        for attr in attr_statement.findall("{%s}Attribute" % NS["saml"]):
            name = attr.get("Name")
            if not name:
                continue
            values = [
                (v.text or "").strip()
                for v in attr.findall("{%s}AttributeValue" % NS["saml"])
            ]
            attrs[name] = values

    # Replay protection — unique index does the enforcement so parallel
    # ACS calls with the same assertion race-protect each other too.
    db.session.add(
        SamlConsumedAssertion(
            provider_id=provider.id,
            assertion_id=assertion_id,
            not_on_or_after=not_on_or_after,
        )
    )
    try:
        db.session.flush()
    except Exception as exc:  # IntegrityError on the unique index
        db.session.rollback()
        raise SamlError("assertion_replay") from exc

    return SamlAssertion(
        assertion_id=assertion_id,
        name_id=name_id,
        attributes=attrs,
        not_on_or_after=not_on_or_after,
        in_response_to=confirmation_data.get("InResponseTo"),
        issuer=provider.entity_id,
    )


# ----------------------------------------------------------- Metadata


def build_sp_metadata(
    audience: str, *, acs_url: str
) -> bytes:
    """Return an SP metadata XML document for publication."""
    md_ns = "urn:oasis:names:tc:SAML:2.0:metadata"
    root = etree.Element(
        "{%s}EntityDescriptor" % md_ns,
        nsmap={"md": md_ns},
        entityID=audience,
    )
    sp = etree.SubElement(
        root,
        "{%s}SPSSODescriptor" % md_ns,
        AuthnRequestsSigned="false",
        WantAssertionsSigned="true",
        protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol",
    )
    etree.SubElement(
        sp,
        "{%s}AssertionConsumerService" % md_ns,
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
        Location=acs_url,
        index="0",
    )
    return etree.tostring(root, xml_declaration=True, encoding="utf-8")


# ----------------------------------------------------------- helpers


def _load_cert(pem: str) -> x509.Certificate:
    pem_bytes = pem.strip().encode("ascii")
    if b"BEGIN CERTIFICATE" not in pem_bytes:
        raise ValueError("expected PEM certificate")
    return x509.load_pem_x509_certificate(pem_bytes)


def _parse_iso(value: str) -> datetime:
    # SAML timestamps are always UTC; strip trailing Z for datetime parsing.
    if value.endswith("Z"):
        value = value[:-1]
    # Fractional seconds may be present; cap to microseconds.
    if "." in value:
        head, tail = value.split(".", 1)
        tail = tail[:6]
        value = f"{head}.{tail}"
    return datetime.fromisoformat(value)
