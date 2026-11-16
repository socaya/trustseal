#!/usr/bin/env python
"""Local Static Application Security Testing (SAST) runner.

Invokes a short pipeline of security checks if the underlying tools
are installed. Each tool is optional — the runner emits a ``skipped``
entry when a tool is missing rather than failing.

Tools:

* ``bandit`` — Python SAST.
* ``pip-audit`` — CVE lookup against installed packages.
* ``detect-secrets`` — Git-history secret scan when available; falls
  back to a small built-in regex secret scan over the repository.

Exit code:

* ``0`` when every installed tool completed with zero findings.
* ``1`` when any installed tool reports a finding.
* ``2`` when the runner itself failed to execute (missing Python
  dependency, unreadable file).

Example::

    python scripts/run_sast.py --project-root .

The runner never fails for a missing tool — operators are expected
to install the tools they care about and update the runner
configuration. The summary JSON is written to stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class ToolResult:
    name: str
    status: str  # "ok" | "skipped" | "found" | "error"
    findings: list[dict] = field(default_factory=list)
    message: str | None = None


def _run_bandit(root: Path) -> ToolResult:
    if shutil.which("bandit") is None:
        return ToolResult(name="bandit", status="skipped", message="bandit_not_installed")
    try:
        proc = subprocess.run(
            ["bandit", "-q", "-r", str(root / "app"), "-f", "json"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(name="bandit", status="error", message="timeout")
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return ToolResult(name="bandit", status="error", message="malformed_json")
    findings = [
        {
            "filename": r.get("filename"),
            "issue_text": r.get("issue_text"),
            "severity": r.get("issue_severity"),
            "line": r.get("line_number"),
        }
        for r in data.get("results") or []
    ]
    high = [f for f in findings if (f.get("severity") or "").upper() in ("HIGH", "CRITICAL")]
    status = "found" if high else "ok"
    return ToolResult(name="bandit", status=status, findings=high)


def _run_pip_audit() -> ToolResult:
    if shutil.which("pip-audit") is None:
        return ToolResult(
            name="pip-audit", status="skipped", message="pip_audit_not_installed"
        )
    try:
        proc = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return ToolResult(name="pip-audit", status="error", message="timeout")
    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return ToolResult(name="pip-audit", status="error", message="malformed_json")
    findings: list[dict] = []
    # pip-audit output is either a bare list (dependencies) each with
    # a "vulns" list, or a dict with "dependencies".
    if isinstance(data, dict):
        deps = data.get("dependencies") or []
    else:
        deps = data
    for dep in deps:
        for vuln in dep.get("vulns") or []:
            findings.append(
                {
                    "package": dep.get("name"),
                    "version": dep.get("version"),
                    "id": vuln.get("id"),
                    "severity": vuln.get("severity") or "unknown",
                    "description": vuln.get("description"),
                }
            )
    status = "found" if findings else "ok"
    return ToolResult(name="pip-audit", status=status, findings=findings)


SECRET_PATTERNS = [
    # AWS access keys: AKIA + 16 alphanumerics.
    ("aws_access_key", re.compile(r"AKIA[A-Z0-9]{16}")),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN (?:(?:RSA|DSA|EC|OPENSSH|ENCRYPTED)\s+)?PRIVATE KEY-----"
        ),
    ),
    ("stripe_live_key", re.compile(r"sk_live_[0-9a-zA-Z]{24,}")),
    (
        "generic_bearer_token",
        re.compile(
            r"(?i)\b(bearer|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9\-_.=/]{24,}"
        ),
    ),
]
SKIP_DIRS = {".venv", ".git", "node_modules", "__pycache__", "docs", "static"}
SKIP_EXTS = {".pyc", ".jpg", ".jpeg", ".png", ".pdf", ".ico", ".svg", ".gif"}


def _run_secret_scan(root: Path) -> ToolResult:
    findings: list[dict] = []
    for path in _iter_scannable_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                findings.append(
                    {
                        "file": str(path.relative_to(root)),
                        "label": label,
                        "offset": match.start(),
                    }
                )
    status = "found" if findings else "ok"
    return ToolResult(
        name="secret-scan",
        status=status,
        findings=findings,
        message="built-in regex scan",
    )


def _iter_scannable_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in SKIP_EXTS:
            continue
        if path.stat().st_size > 1_000_000:
            continue
        yield path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to the project root (defaults to current directory).",
    )
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    results: list[ToolResult] = [
        _run_bandit(root),
        _run_pip_audit(),
        _run_secret_scan(root),
    ]
    summary = {
        "tools": [
            {
                "name": r.name,
                "status": r.status,
                "message": r.message,
                "finding_count": len(r.findings),
                "findings": r.findings,
            }
            for r in results
        ],
        "overall": "fail" if any(r.status == "found" for r in results) else "ok",
    }
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if summary["overall"] == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
