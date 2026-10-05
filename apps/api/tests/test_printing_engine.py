"""Print engine primitives — render_html_to_pdf + merge_pdfs.

Pure engine tests; no DB, no HTTP, no templates from disk (use inline strings).
"""
import io

import pypdf

from app.printing.engine import merge_pdfs, render_html_string_to_pdf


def test_render_html_string_returns_valid_pdf():
    pdf = render_html_string_to_pdf("<html><body><h1>hello</h1></body></html>")
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 100


def test_merge_pdfs_concatenates_pages():
    a = render_html_string_to_pdf("<h1>A</h1>")
    b = render_html_string_to_pdf("<h1>B</h1>")
    c = render_html_string_to_pdf("<h1>C</h1>")
    merged = merge_pdfs([a, b, c])
    reader = pypdf.PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 3


def test_merge_pdfs_empty_list_returns_empty_pdf():
    merged = merge_pdfs([])
    # pypdf produces a valid (empty) PDF when given no parts.
    assert merged[:5] == b"%PDF-"


def test_merge_pdfs_single_part_roundtrips():
    a = render_html_string_to_pdf("<h1>solo</h1>")
    merged = merge_pdfs([a])
    reader = pypdf.PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 1


def test_jinja_env_autoescapes_html_templates():
    """User-controlled fields (item description, part names, notes) must be escaped
    in every .html template the engine loads, and in string templates."""
    from app.printing.engine import _env

    assert _env.autoescape("cutlist.html") is True
    assert _env.from_string("{{ x }}").render(x="<script>") == "&lt;script&gt;"


def test_render_html_string_handles_unicode():
    pdf = render_html_string_to_pdf("<html><body>café — 25mm</body></html>")
    assert pdf[:5] == b"%PDF-"
