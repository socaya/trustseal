"""SBOM generator (J3).

Covers the pure-function path. Import the module directly rather
than invoking the script so we do not shell out from pytest.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load_generator():
    name = "generate_sbom_test_module"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent.parent / "scripts" / "generate_sbom.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestBuildSbom:
    def test_shape_is_cyclonedx_1_5(self):
        generator = _load_generator()
        sbom = generator.build_sbom()
        assert sbom["bomFormat"] == "CycloneDX"
        assert sbom["specVersion"] == "1.5"
        assert sbom["version"] == 1
        assert sbom["serialNumber"].startswith("urn:uuid:")

    def test_metadata_has_trustseal_component(self):
        generator = _load_generator()
        sbom = generator.build_sbom()
        assert sbom["metadata"]["component"]["name"] == "trustseal"

    def test_components_include_pinned_deps(self):
        """At least a few known pinned packages must appear."""
        generator = _load_generator()
        sbom = generator.build_sbom()
        names = {c["name"].lower() for c in sbom["components"]}
        # Any build of the project pins these.
        assert "flask" in names
        assert "sqlalchemy" in names
        assert "cryptography" in names

    def test_components_have_purl_and_bomref(self):
        generator = _load_generator()
        sbom = generator.build_sbom()
        assert sbom["components"], "SBOM contains at least one component"
        for component in sbom["components"]:
            assert component["purl"].startswith("pkg:pypi/")
            assert component["bom-ref"] == component["purl"]
            assert component["type"] == "library"
            assert component["version"]

    def test_serialisable(self):
        generator = _load_generator()
        serialised = json.dumps(generator.build_sbom())
        assert '"bomFormat": "CycloneDX"' in serialised
