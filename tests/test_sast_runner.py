"""SAST runner (J4) — exercises the pure-function paths."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_runner():
    """Load the SAST runner fresh on each call so pattern edits reload."""
    name = "run_sast_test_module"
    path = Path(__file__).resolve().parent.parent / "scripts" / "run_sast.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # ``dataclasses`` resolves ``__module__`` via ``sys.modules`` so
    # the module must be registered BEFORE exec_module runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestSecretScan:
    def test_clean_file_no_findings(self, tmp_path):
        runner = _load_runner()
        (tmp_path / "ok.py").write_text("hello = 'world'\n")
        result = runner._run_secret_scan(tmp_path)
        assert result.status == "ok"
        assert result.findings == []

    def test_detects_aws_access_key(self, tmp_path):
        runner = _load_runner()
        (tmp_path / "config.py").write_text(
            "AWS = 'AKIAEXAMPLEKEYAAAAAAA'\n"
        )
        result = runner._run_secret_scan(tmp_path)
        assert result.status == "found"
        labels = {f["label"] for f in result.findings}
        assert "aws_access_key" in labels

    def test_detects_private_key_block(self, tmp_path):
        runner = _load_runner()
        (tmp_path / "key.pem").write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKxx\n"
        )
        result = runner._run_secret_scan(tmp_path)
        assert result.status == "found"
        assert any(
            f["label"] == "private_key_block" for f in result.findings
        )

    def test_skips_node_modules(self, tmp_path):
        runner = _load_runner()
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "evil.js").write_text(
            "const k = 'AKIAEXAMPLEKEYAAAAAAA';"
        )
        result = runner._run_secret_scan(tmp_path)
        assert result.status == "ok"


class TestBanditSkip:
    def test_bandit_skipped_when_not_installed(self, tmp_path, monkeypatch):
        runner = _load_runner()
        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        result = runner._run_bandit(tmp_path)
        assert result.status == "skipped"
        assert result.message == "bandit_not_installed"


class TestMainExit:
    def test_main_returns_zero_without_findings(self, tmp_path, monkeypatch, capsys):
        runner = _load_runner()
        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        (tmp_path / "clean.py").write_text("print('hi')\n")
        exit_code = runner.main(["--project-root", str(tmp_path)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert '"overall": "ok"' in captured.out

    def test_main_returns_one_on_finding(self, tmp_path, monkeypatch, capsys):
        runner = _load_runner()
        monkeypatch.setattr(runner.shutil, "which", lambda name: None)
        (tmp_path / "leak.py").write_text(
            "AWS_KEY = 'AKIAEXAMPLEKEYAAAAAAA'\n"
        )
        exit_code = runner.main(["--project-root", str(tmp_path)])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert '"overall": "fail"' in captured.out
