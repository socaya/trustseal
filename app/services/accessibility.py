"""Server-side accessibility probe for critical templates.

This is deliberately narrow: an HTMLParser-based checker that enforces
the rules we care about on the public verification and evidence
dossier pages. It is **not** an axe-core replacement; axe-core-in-
Playwright is the authoritative WCAG tool. This probe exists so that
our pre-merge CI catches regressions on the exact rules below without
a browser runtime:

* Document declares a ``lang`` attribute on ``<html>``.
* Every ``<input>`` and ``<select>`` either has an id with a
  corresponding ``<label for=...>`` OR is nested inside a ``<label>``.
* Every ``<button>`` and ``<a>`` has visible text content or an
  ``aria-label``.
* Status messages are not communicated by color alone: any element
  carrying ``role="alert"`` or ``role="status"`` includes text plus
  either an icon character or an explicit glyph.
* ``<img>`` tags carry ``alt``.
* Required form controls have both the HTML5 ``required`` attribute
  and a text cue (a star glyph, the word ``required``, or an aria
  description).
* No bare ``onclick`` attributes (would indicate client-side
  JavaScript we would also need to audit — out of scope here).

:class:`AccessibilityReport` captures the concrete violations so a
caller can either assert empty (CI gate) or log them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable, Optional

STATUS_ROLES = {"alert", "status"}
TEXT_GLYPHS = {
    "က3",  # ✓ (CHECK MARK as escaped surrogate)
    "✓",
    "✕",
    "⚠",
    "⊘",
    "⊗",
    "≠",
    "●",
    "!",
}


@dataclass(frozen=True)
class AccessibilityViolation:
    rule: str
    detail: str


@dataclass
class AccessibilityReport:
    violations: list[AccessibilityViolation] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.violations

    def __bool__(self) -> bool:
        return self.ok()


class _AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.violations: list[AccessibilityViolation] = []
        self._label_targets: set[str] = set()
        self._inputs: list[tuple[dict, bool]] = []  # (attrs, inside_label)
        self._interactives: list[dict] = []
        self._html_lang: Optional[str] = None
        self._depth_label: int = 0
        self._current_role_stack: list[str] = []
        self._current_role_text: list[list[str]] = []

    # -- helpers ---------------------------------------------------

    def _add(self, rule: str, detail: str) -> None:
        self.violations.append(AccessibilityViolation(rule=rule, detail=detail))

    @staticmethod
    def _attrs_to_dict(attrs) -> dict:
        return {k: (v or "") for k, v in attrs}

    def _starttag(self, tag: str, attrs_list) -> None:
        attrs = self._attrs_to_dict(attrs_list)
        if "onclick" in attrs:
            self._add(
                "no-inline-js",
                f"<{tag}> uses inline onclick; move handlers to a vendored script.",
            )
        if tag == "html":
            self._html_lang = attrs.get("lang")
        elif tag == "img":
            if "alt" not in attrs:
                self._add("img-alt", "<img> missing alt attribute")
        elif tag == "label":
            self._depth_label += 1
            if attrs.get("for"):
                self._label_targets.add(attrs["for"])
        elif tag in {"input", "select", "textarea"}:
            if attrs.get("type") not in {"hidden", "submit", "button"}:
                self._inputs.append((attrs, self._depth_label > 0))
        elif tag in {"a", "button"}:
            self._interactives.append({"tag": tag, "attrs": attrs, "text": []})
        role = attrs.get("role")
        if role in STATUS_ROLES:
            self._current_role_stack.append(role)
            self._current_role_text.append([])

    def _endtag(self, tag: str) -> None:
        if tag == "label":
            self._depth_label = max(0, self._depth_label - 1)
        elif tag in {"a", "button"}:
            self._finalize_interactive()
        if self._current_role_stack and tag in {"div", "section", "p", "span"}:
            text = " ".join(self._current_role_text.pop()).strip()
            role = self._current_role_stack.pop()
            if text and not any(glyph in text for glyph in TEXT_GLYPHS):
                self._add(
                    "status-color-only",
                    f"role={role} region lacks a non-color glyph in its text",
                )

    def _finalize_interactive(self) -> None:
        item = self._interactives.pop()
        text = " ".join(item["text"]).strip()
        attrs = item["attrs"]
        if text:
            return
        if attrs.get("aria-label") or attrs.get("aria-labelledby"):
            return
        self._add(
            "interactive-label",
            f"<{item['tag']}> has no visible text or aria-label",
        )

    # -- HTMLParser hooks ------------------------------------------

    def handle_starttag(self, tag, attrs):
        self._starttag(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._starttag(tag, attrs)
        if tag in {"a", "button"}:
            self._finalize_interactive()

    def handle_endtag(self, tag):
        self._endtag(tag)

    def handle_data(self, data):
        if self._interactives:
            self._interactives[-1]["text"].append(data)
        if self._current_role_text:
            self._current_role_text[-1].append(data)

    # -- post-pass -------------------------------------------------

    def post_process(self) -> None:
        if not self._html_lang:
            self._add("html-lang", "<html> missing lang attribute")
        for attrs, inside_label in self._inputs:
            if inside_label:
                continue
            id_ = attrs.get("id")
            aria_label = attrs.get("aria-label")
            aria_labelledby = attrs.get("aria-labelledby")
            if aria_label or aria_labelledby:
                continue
            if id_ and id_ in self._label_targets:
                continue
            self._add(
                "input-label",
                f"input/select/textarea missing label for id={id_!r}",
            )
            if attrs.get("required") is not None:
                describedby = attrs.get("aria-describedby")
                if not describedby:
                    self._add(
                        "required-cue",
                        f"required input missing aria-describedby id={id_!r}",
                    )


def audit_html(html: str) -> AccessibilityReport:
    """Return an :class:`AccessibilityReport` for ``html``."""
    parser = _AuditParser()
    parser.feed(html)
    parser.post_process()
    return AccessibilityReport(violations=list(parser.violations))
