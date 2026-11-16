"""Rich-text HTML sanitizer + Markdown renderer (J1)."""
from __future__ import annotations

import pytest


class TestSanitize:
    def test_allows_plain_markup(self):
        from app.services.rich_text import sanitize_html

        html = "<p>Hello <strong>world</strong></p>"
        assert sanitize_html(html) == "<p>Hello <strong>world</strong></p>"

    def test_strips_script(self):
        from app.services.rich_text import sanitize_html

        hostile = "<p>Hi<script>alert(1)</script> there</p>"
        out = sanitize_html(hostile)
        assert "<script>" not in out
        assert "alert" not in out
        assert "Hi" in out
        assert "there" in out

    def test_strips_event_handlers(self):
        from app.services.rich_text import sanitize_html

        hostile = '<p onclick="x()">click</p>'
        out = sanitize_html(hostile)
        assert "onclick" not in out
        assert "click" in out

    def test_drops_javascript_href(self):
        from app.services.rich_text import sanitize_html

        hostile = '<a href="javascript:alert(1)">click</a>'
        out = sanitize_html(hostile)
        assert "javascript:" not in out
        # Link text survives even though the href was stripped.
        assert "click" in out

    def test_adds_rel_noopener_to_links(self):
        from app.services.rich_text import sanitize_html

        html = '<a href="https://example.com">example</a>'
        out = sanitize_html(html)
        assert 'href="https://example.com"' in out
        assert 'rel="noopener noreferrer"' in out

    def test_strips_iframe(self):
        from app.services.rich_text import sanitize_html

        hostile = '<iframe src="https://evil"></iframe><p>hi</p>'
        out = sanitize_html(hostile)
        assert "iframe" not in out
        assert "hi" in out

    def test_oversize_raises(self):
        from app.services.rich_text import RichTextError, sanitize_html

        with pytest.raises(RichTextError):
            sanitize_html("x" * (1_000_001))

    def test_empty_returns_empty(self):
        from app.services.rich_text import sanitize_html

        assert sanitize_html("") == ""
        assert sanitize_html("   ") == ""


class TestMarkdown:
    def test_headings(self):
        from app.services.rich_text import render_markdown

        out = render_markdown("# Title\n\n## Subtitle")
        assert "<h1>Title</h1>" in out
        assert "<h2>Subtitle</h2>" in out

    def test_bold_italic_code_link(self):
        from app.services.rich_text import render_markdown

        out = render_markdown(
            "This is **bold**, *italic*, `code`, and a "
            "[link](https://example.com)."
        )
        assert "<strong>bold</strong>" in out
        assert "<em>italic</em>" in out
        assert "<code>code</code>" in out
        assert '<a href="https://example.com"' in out

    def test_lists(self):
        from app.services.rich_text import render_markdown

        out = render_markdown("- one\n- two\n- three")
        assert out.count("<li>") == 3
        assert "<ul>" in out

    def test_ordered_list(self):
        from app.services.rich_text import render_markdown

        out = render_markdown("1. one\n2. two")
        assert "<ol>" in out
        assert out.count("<li>") == 2

    def test_fenced_code_escapes_html(self):
        from app.services.rich_text import render_markdown

        out = render_markdown("```python\n<script>no</script>\n```")
        assert "<pre>" in out
        assert "&lt;script&gt;" in out

    def test_table(self):
        from app.services.rich_text import render_markdown

        md = (
            "| H1 | H2 |\n"
            "|----|----|\n"
            "| a  | b  |\n"
            "| c  | d  |\n"
        )
        out = render_markdown(md)
        assert "<table>" in out
        assert "<thead>" in out
        assert out.count("<tr>") == 3

    def test_link_with_javascript_scheme_does_not_link(self):
        """A javascript: URL in Markdown degrades to inert text — never an <a>."""
        from app.services.rich_text import render_markdown

        out = render_markdown("[bad](javascript:alert(1))")
        # The crucial safety property: no anchor element is emitted,
        # so the browser cannot be tricked into following the URL.
        assert "<a " not in out
        assert "href" not in out
        # The literal brackets survive as plain text, which is fine —
        # the browser renders them inert.
        assert "bad" in out

    def test_markdown_output_passes_sanitizer(self):
        """A pathological Markdown input cannot inject raw HTML."""
        from app.services.rich_text import render_markdown

        md = "`<script>alert(1)</script>`"
        out = render_markdown(md)
        assert "<script>" not in out
