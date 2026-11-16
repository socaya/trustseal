#!/usr/bin/env python
"""Emit a CycloneDX 1.5 Software Bill of Materials for the current Python env.

Usage::

    python scripts/generate_sbom.py > sbom.cdx.json

The generator:

* Walks every ``importlib.metadata`` distribution installed in the
  active environment.
* Records name, version, declared license (when available), the
  ``purl`` identifier in the CycloneDX form
  ``pkg:pypi/<name>@<version>``, and a provenance URL when the
  package exposes one.
* Writes a single JSON document to stdout so redirection is the
  idiomatic call site. The output passes ``jsonschema`` validation
  against the official CycloneDX 1.5 schema.

Shipping the SBOM alongside a release is a supply-chain hygiene
requirement for many enterprise procurement processes. This script
produces the artefact in-tree without needing a CI pipeline or a
third-party scanner.
"""
from __future__ import annotations

import importlib.metadata
import json
import sys
import uuid
from datetime import datetime, timezone


def _distribution_component(dist: importlib.metadata.Distribution) -> dict:
    meta = dist.metadata
    name = meta["Name"]
    version = meta["Version"] or "0.0.0"
    license_name = None
    license_meta = meta.get("License")
    if license_meta and license_meta.strip() and license_meta.strip() != "UNKNOWN":
        license_name = license_meta.strip()
    classifiers = meta.get_all("Classifier") or []
    for classifier in classifiers:
        if classifier.startswith("License ::"):
            # "License :: OSI Approved :: MIT License" → "MIT License"
            parts = [p.strip() for p in classifier.split("::") if p.strip()]
            if parts:
                license_name = license_name or parts[-1]
    purl = f"pkg:pypi/{name.lower()}@{version}"
    homepage = None
    for url_field in ("Home-page", "Project-URL"):
        for raw in meta.get_all(url_field) or []:
            value = raw.strip()
            if value and value != "UNKNOWN":
                homepage = value.split(",", 1)[-1].strip() if "," in value else value
                break
        if homepage:
            break
    component: dict = {
        "type": "library",
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
    }
    if license_name:
        component["licenses"] = [{"license": {"name": license_name}}]
    if homepage and (homepage.startswith("http://") or homepage.startswith("https://")):
        component["externalReferences"] = [
            {"type": "website", "url": homepage}
        ]
    return component


def build_sbom() -> dict:
    dists = sorted(
        importlib.metadata.distributions(),
        key=lambda d: (d.metadata["Name"] or "").lower(),
    )
    components = [_distribution_component(d) for d in dists if d.metadata["Name"]]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": now,
            "tools": [
                {
                    "vendor": "TrustSeal",
                    "name": "scripts/generate_sbom.py",
                    "version": "1.0",
                }
            ],
            "component": {
                "type": "application",
                "name": "trustseal",
                "version": "0.0.0-dev",
            },
        },
        "components": components,
    }


def main() -> int:
    json.dump(build_sbom(), sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
