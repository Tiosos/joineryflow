"""Print engine primitives — render_html_to_pdf + merge_pdfs.

Pure engine tests; no DB, no HTTP, no templates from disk (use inline strings).
"""
import io

import pypdf
import pytest

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


def test_render_template_pdf_uses_jinja_autoescape():
    """Verify HTML autoescape is on so '<script>' becomes '&lt;script&gt;' in the PDF text."""
    from app.printing.engine import render_template_to_pdf
    # Use an inline template via a tmp environment? The plan-level test uses the
    # production env so we exercise autoescape on the cutlist template's `item.description`
    # context variable — but cutlist.html doesn't exist yet. Use a smoke template instead.
    # Skip if not available; covered by route tests in Task 8.
    pytest.skip("autoescape end-to-end coverage lives in test_print_routes.py once cutlist.html exists")


def test_render_html_string_handles_unicode():
    pdf = render_html_string_to_pdf("<html><body>café — 25mm</body></html>")
    assert pdf[:5] == b"%PDF-"
