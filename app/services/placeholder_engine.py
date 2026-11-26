"""Unified Dynamic Placeholder Engine for Contracts, TSD Documents & PDF Export.

Provides:
- Comprehensive context building (document_ref, contract_number, organization_name,
  counterparty_name, project_name, project_code, effective_date, expiration_date,
  probation_end_date, deal_value, currency, governing_law, owner_name, etc.)
- Human-readable label formatting (``document_ref`` -> ``Document Ref``)
- Export/Print resolution: replaces both raw ``{{key}}`` tokens and interactive
  ``<span class="ts-field-chip" data-field-key="key">...</span>`` chips with real
  values when available, or clean handwritten fill-in lines (``________________``)
  when left blank.
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import Any

_RAW_TOKEN_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")
_CHIP_RE = re.compile(
    r'<span\b([^>]*\bdata-field-key="([^"]+)"[^>]*)>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)


def humanize_placeholder_key(key: str) -> str:
    """Convert snake_case/kebab-case key to a crisp human-readable field label."""
    parts = [p for p in re.split(r"[_\-\s.]+", str(key or "").strip()) if p]
    if not parts:
        return "Field"
    acronyms = {"id", "ref", "vat", "tin", "pin", "sla", "nda", "msa", "kpi", "okr", "hr", "it", "po", "url"}
    out = []
    for p in parts:
        out.append(p.upper() if p.lower() in acronyms else p.capitalize())
    return " ".join(out)


def _norm_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key or "").strip().lower()).strip("_")


def build_placeholder_context(
    *,
    doc: Any = None,
    wf: Any = None,
    project: Any = None,
    organization: Any = None,
    actor: Any = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build a complete, non-empty lookup dict of canonical placeholder keys."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ctx: dict[str, str] = {}

    def _put(keys: list[str], val: Any) -> None:
        s = str(val).strip() if val is not None else ""
        if not s:
            return
        for k in keys:
            if k not in ctx or not ctx[k]:
                ctx[k] = s

    if wf is not None:
        _put(["contract_number", "document_ref", "reference_number", "ref_no", "contract_ref"], getattr(wf, "contract_number", None))
        _put(["counterparty_name", "client_name", "second_party", "party_b", "vendor_name", "employee_name"], getattr(wf, "counterparty_name", None))
        _put(["deal_value", "contract_value", "amount", "total_value"], getattr(wf, "deal_value", None))
        _put(["currency"], getattr(wf, "currency", None))
        _put(["effective_date", "start_date", "execution_date"], getattr(wf, "effective_date", None))
        _put(["expiration_date", "end_date"], getattr(wf, "expiration_date", None))
        _put(["governing_law", "jurisdiction"], getattr(wf, "governing_law", None))

    if doc is not None:
        _put(["document_title", "contract_title", "title"], getattr(doc, "title", None))
        if getattr(doc, "id", None):
            _put(["document_ref", "reference_number", "ref_no"], f"TSD-{int(doc.id):05d}")

    if project is not None:
        _put(["project_name"], getattr(project, "name", None))
        _put(["project_code"], getattr(project, "project_code", None))
        _put(["currency"], getattr(project, "currency", None))
        _put(["department"], getattr(project, "category", None))

    if organization is not None:
        _put(["organization_name", "company_name", "first_party", "party_a", "employer_name"], getattr(organization, "name", None))

    if actor is not None:
        full_name = ""
        if hasattr(actor, "get_full_name"):
            try:
                full_name = (actor.get_full_name() or "").strip()
            except Exception:
                full_name = ""
        full_name = full_name or getattr(actor, "username", "") or getattr(actor, "email", "")
        _put(["owner_name", "prepared_by", "author_name", "document_owner", "signatory_name"], full_name)
        _put(["owner_email", "contact_email"], getattr(actor, "email", None))

    _put(["date", "today", "current_date", "effective_date"], today)

    if extra:
        for k, v in extra.items():
            if v is not None and str(v).strip():
                nk = _norm_key(str(k))
                if nk:
                    ctx[nk] = str(v).strip()
                    ctx[str(k).strip()] = str(v).strip()

    return ctx


def substitute_known_placeholders(html_str: str, ctx: dict[str, Any] | None) -> str:
    """Replace ``{{key}}`` tokens whose value is known in ``ctx``; leave unknown keys intact
    so the UI can present them as interactive highlighted fields."""
    if not html_str or not ctx:
        return html_str or ""
    norm_ctx = {_norm_key(k): str(v).strip() for k, v in ctx.items() if v is not None and str(v).strip()}

    def _repl(match: re.Match) -> str:
        raw_key = match.group(1)
        val = norm_ctx.get(_norm_key(raw_key))
        if val:
            return (
                f'<span class="ts-field-chip is-filled" data-field-key="{_html.escape(raw_key, quote=True)}" '
                f'data-field-label="{_html.escape(humanize_placeholder_key(raw_key), quote=True)}">'
                f"{_html.escape(val)}</span>"
            )
        return match.group(0)

    return _RAW_TOKEN_RE.sub(_repl, html_str)


def _blank_fill_line_html(label: str) -> str:
    """Render a clean, official handwritten fill-in line for unfilled fields on PDF/print."""
    return (
        '<span class="ts-blank-line" '
        'style="display:inline-block;min-width:115pt;border-bottom:0.9pt solid #1d3648;'
        'padding:0 3pt;color:#64748b;font-size:8pt;text-align:center;">'
        "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
        "</span>"
    )


def resolve_placeholders_for_export(
    html_str: str,
    ctx: dict[str, Any] | None = None,
    *,
    unfilled_style: str = "blank_line",
) -> str:
    """Prepare HTML for PDF export or printing:
    - Filled interactive chips render as clean plain text (no highlight pill chrome).
    - Unfilled chips & raw ``{{key}}`` tokens resolve from ``ctx`` if a value exists.
    - Any still-unfilled placeholder becomes a clean official ``________________`` line
      ready to be filled by hand.
    """
    if not html_str:
        return ""
    norm_ctx = {_norm_key(k): str(v).strip() for k, v in (ctx or {}).items() if v is not None and str(v).strip()}

    def _resolve_chip(match: re.Match) -> str:
        attrs = match.group(1) or ""
        raw_key = match.group(2) or ""
        inner = (match.group(3) or "").strip()
        label = humanize_placeholder_key(raw_key)
        is_empty_chip = "is-empty" in attrs or inner.lower() == label.lower() or not inner or "{{" in inner
        val = norm_ctx.get(_norm_key(raw_key))
        if not is_empty_chip and inner:
            return inner
        if val:
            return _html.escape(val)
        return _blank_fill_line_html(label)

    out = _CHIP_RE.sub(_resolve_chip, html_str)

    def _resolve_raw(match: re.Match) -> str:
        raw_key = match.group(1)
        val = norm_ctx.get(_norm_key(raw_key))
        if val:
            return _html.escape(val)
        return _blank_fill_line_html(humanize_placeholder_key(raw_key))

    out = _RAW_TOKEN_RE.sub(_resolve_raw, out)
    return out
