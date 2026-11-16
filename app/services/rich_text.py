"""Server-side rich-text processing.

Two public entry points:

* :func:`sanitize_html` — takes an untrusted HTML fragment and
  returns a copy with everything outside the explicit allowlist
  removed. Nothing can smuggle in ``<script>``, ``<style>``,
  ``<iframe>``, inline event handlers, or ``javascript:`` /
  ``data:`` URIs.
* :func:`render_markdown` — a minimal CommonMark-ish Markdown
  renderer that covers the primitives the product documentation
  calls out: headings, bulleted + numbered lists, tables, bold /
  italic / inline code, fenced code blocks, links.

Both functions produce a string that is **safe to embed directly
inside a server-rendered page** after the standard output escaping
elsewhere in the request pipeline. The sanitizer is also used to
scrub Markdown output because a malicious renderer input could
inject raw HTML into a code fence.

Design goals:

* Zero new runtime dependencies (``lxml`` is already pinned).
* Deterministic: the same input always produces the same output.
* Fail closed: unknown tags / attributes / schemes are dropped,
  never rewritten.
"""
from __future__ import annotations

import html
import re
from typing import Iterable

from lxml import etree, html as lxml_html


ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "em",
        "b",
        "i",
        "u",
        "code",
        "pre",
        "blockquote",
        "ul",
        "ol",
        "li",
        "a",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "table",
        "thead",
        "tbody",
        "tr",
        "th",
        "td",
        "span",
    }
)

ALLOWED_ATTRS = {
    "a": frozenset({"href", "title", "rel"}),
    "th": frozenset({"colspan", "rowspan"}),
    "td": frozenset({"colspan", "rowspan"}),
    "span": frozenset({"class"}),
    "code": frozenset({"class"}),
    "pre": frozenset({"class"}),
}

ALLOWED_URL_SCHEMES = frozenset({"http", "https", "mailto"})

_INLINE_HREF_RE = re.compile(r"^(?P<scheme>[a-z]+):", re.IGNORECASE)


class RichTextError(ValueError):
    """Raised on structurally-invalid rich-text input."""


# -------------------------------------------------- sanitization


def sanitize_html(fragment: str, *, max_length: int = 1_000_000) -> str:
    """Return a safe HTML fragment.

    Empty / whitespace-only input returns an empty string.
    ``max_length`` guards against resource exhaustion from
    pathological inputs.
    """
    if not isinstance(fragment, str):
        raise RichTextError("fragment_type_invalid")
    if len(fragment) > max_length:
        raise RichTextError("fragment_too_large")
    stripped = fragment.strip()
    if not stripped:
        return ""
    # Parse the fragment inside a synthetic root so top-level text
    # nodes survive.
    try:
        wrapped = f"<div>{stripped}</div>"
        parser = etree.HTMLParser(
            remove_blank_text=False, no_network=True, huge_tree=False
        )
        root = lxml_html.fragment_fromstring(
            wrapped, create_parent=False, parser=parser
        )
    except (etree.XMLSyntaxError, etree.ParserError) as exc:
        raise RichTextError("fragment_malformed") from exc
    _sanitize_subtree(root)
    # Serialise back; we return the inner HTML of the synthetic root.
    rendered = lxml_html.tostring(
        root, encoding="unicode", method="html"
    )
    # Strip the wrapper <div>...</div> we added.
    if rendered.startswith("<div>") and rendered.endswith("</div>"):
        rendered = rendered[len("<div>") : -len("</div>")]
    return rendered


DANGEROUS_TAGS = frozenset({"script", "style", "iframe", "object", "embed"})


def _sanitize_subtree(element: etree._Element) -> None:
    for child in list(element):
        tag = (child.tag or "").lower()
        if tag in DANGEROUS_TAGS:
            # Drop the dangerous element AND its subtree outright —
            # the text inside a <script> or <style> is active content.
            parent = child.getparent()
            if parent is not None:
                # Preserve the element's tail (text AFTER the closing
                # tag) so surrounding content remains intact.
                tail = child.tail or ""
                idx = list(parent).index(child)
                if tail:
                    if idx == 0:
                        parent.text = (parent.text or "") + tail
                    else:
                        prev = list(parent)[idx - 1]
                        prev.tail = (prev.tail or "") + tail
                parent.remove(child)
            continue
        _sanitize_subtree(child)
        if tag not in ALLOWED_TAGS:
            _drop_tag_preserve_text(child)
            continue
        _sanitize_attributes(child)


def _sanitize_attributes(element: etree._Element) -> None:
    tag = element.tag.lower()
    allowed = ALLOWED_ATTRS.get(tag, frozenset())
    for name in list(element.attrib):
        lname = name.lower()
        if lname not in allowed:
            del element.attrib[name]
            continue
        value = element.attrib[name]
        if lname == "href":
            if not _safe_url(value):
                del element.attrib[name]
                continue
            # Force ``rel="noopener noreferrer"`` on links.
            element.attrib.pop("rel", None)
            element.attrib["rel"] = "noopener noreferrer"
        if lname == "class":
            # Allow a conservative class allowlist to prevent CSS
            # exfiltration; here we drop entirely.
            del element.attrib[name]


def _safe_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    if not trimmed:
        return False
    match = _INLINE_HREF_RE.match(trimmed)
    if match:
        scheme = match.group("scheme").lower()
        return scheme in ALLOWED_URL_SCHEMES
    # Relative or anchor links are fine.
    return trimmed.startswith(("/", "#"))


def _drop_tag_preserve_text(element: etree._Element) -> None:
    """Replace ``element`` with its text content + child subtree."""
    parent = element.getparent()
    if parent is None:
        return
    index = list(parent).index(element)
    # Move children up one level (they have already been sanitized).
    for child in list(element):
        parent.insert(index, child)
        index += 1
    # Preserve element.text as a tail on the previous sibling or as
    # parent.text if element was the first child.
    text_parts: list[str] = []
    if element.text:
        text_parts.append(element.text)
    if element.tail:
        text_parts.append(element.tail)
    combined = "".join(text_parts)
    if combined:
        if len(list(element)) == 0:
            # No children to anchor the text on; attach to previous
            # sibling's tail or parent's text.
            idx = list(parent).index(element)
            if idx == 0:
                parent.text = (parent.text or "") + combined
            else:
                prev = list(parent)[idx - 1]
                prev.tail = (prev.tail or "") + combined
    parent.remove(element)


# -------------------------------------------------- markdown


_H_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_HR_RE = re.compile(r"^-{3,}\s*$")
_FENCE_RE = re.compile(r"^```\s*(\w*)\s*$")
_UL_RE = re.compile(r"^[\-\*]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)\.\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*(:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$")


def render_markdown(source: str) -> str:
    """Render a tiny, safe subset of Markdown to sanitized HTML.

    Scope:

    * ``#``, ``##`` … ``######`` headings.
    * ``---`` horizontal rule.
    * Unordered lists (``-`` or ``*``) and ordered lists (``1.``).
    * Fenced code blocks ``` ``` ```.
    * Pipe tables with a ``|---|---|`` separator row.
    * Inline **bold**, *italic*, ``code``, and ``[text](url)``.
    * Paragraphs (blank line separated).

    The output goes through :func:`sanitize_html` so even if the
    renderer emits unexpected HTML a malicious input cannot escape.
    """
    if not isinstance(source, str):
        raise RichTextError("source_type_invalid")
    lines = source.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    buffer: list[str] = []
    i = 0
    in_code = False
    code_lang = ""
    while i < len(lines):
        line = lines[i]
        if in_code:
            if line.strip().startswith("```"):
                code_class = (
                    f' class="language-{html.escape(code_lang)}"'
                    if code_lang
                    else ""
                )
                blocks.append(
                    f"<pre><code{code_class}>"
                    + html.escape("\n".join(buffer))
                    + "</code></pre>"
                )
                buffer = []
                in_code = False
                code_lang = ""
            else:
                buffer.append(line)
            i += 1
            continue
        fence = _FENCE_RE.match(line.strip())
        if fence:
            _flush_paragraph(buffer, blocks)
            in_code = True
            code_lang = fence.group(1) or ""
            i += 1
            continue
        heading = _H_RE.match(line.strip())
        if heading:
            _flush_paragraph(buffer, blocks)
            level = len(heading.group(1))
            text = _render_inline(heading.group(2).strip())
            blocks.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue
        if _HR_RE.match(line.strip()):
            _flush_paragraph(buffer, blocks)
            blocks.append("<hr>")
            i += 1
            continue
        # Lists — consume consecutive list items.
        ul_match = _UL_RE.match(line)
        ol_match = _OL_RE.match(line)
        if ul_match or ol_match:
            _flush_paragraph(buffer, blocks)
            kind = "ul" if ul_match else "ol"
            items: list[str] = []
            while i < len(lines):
                row = lines[i]
                m = _UL_RE.match(row) if kind == "ul" else _OL_RE.match(row)
                if not m:
                    break
                text = m.group(1) if kind == "ul" else m.group(2)
                items.append(f"<li>{_render_inline(text)}</li>")
                i += 1
            blocks.append(f"<{kind}>" + "".join(items) + f"</{kind}>")
            continue
        # Tables — header row + separator + body rows.
        if "|" in line and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            _flush_paragraph(buffer, blocks)
            header_cells = _split_table_row(line)
            i += 2  # skip separator
            body_rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                body_rows.append(_split_table_row(lines[i]))
                i += 1
            parts = ["<table><thead><tr>"]
            parts.extend(
                f"<th>{_render_inline(c)}</th>" for c in header_cells
            )
            parts.append("</tr></thead><tbody>")
            for row in body_rows:
                parts.append("<tr>")
                parts.extend(f"<td>{_render_inline(c)}</td>" for c in row)
                parts.append("</tr>")
            parts.append("</tbody></table>")
            blocks.append("".join(parts))
            continue
        if not line.strip():
            _flush_paragraph(buffer, blocks)
        else:
            buffer.append(line)
        i += 1
    if in_code:
        # Un-terminated fence: emit as paragraph, safely escaped.
        blocks.append(
            "<pre><code>" + html.escape("\n".join(buffer)) + "</code></pre>"
        )
        buffer = []
    _flush_paragraph(buffer, blocks)
    rendered = "".join(blocks)
    return sanitize_html(rendered)


def _flush_paragraph(buffer: list[str], blocks: list[str]) -> None:
    if not buffer:
        return
    text = " ".join(line.strip() for line in buffer).strip()
    if text:
        blocks.append(f"<p>{_render_inline(text)}</p>")
    buffer.clear()


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")
_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[(.+?)\]\((.+?)\)")


def _render_inline(fragment: str) -> str:
    """Convert a line of Markdown inline syntax to HTML."""
    escaped = html.escape(fragment, quote=False)
    # Order matters: inline code first so stars inside backticks are
    # preserved literally.
    escaped = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", escaped)
    escaped = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", escaped)
    escaped = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", escaped)
    escaped = _LINK_RE.sub(_link_replace, escaped)
    return escaped


def _link_replace(match: re.Match) -> str:
    text, url = match.group(1), match.group(2).strip()
    if not _safe_url(url):
        return html.escape(f"[{text}]({url})")
    return f'<a href="{html.escape(url, quote=True)}">{text}</a>'


def _split_table_row(row: str) -> list[str]:
    cleaned = row.strip()
    if cleaned.startswith("|"):
        cleaned = cleaned[1:]
    if cleaned.endswith("|"):
        cleaned = cleaned[:-1]
    return [cell.strip() for cell in cleaned.split("|")]
