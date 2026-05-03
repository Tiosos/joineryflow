"""WeasyPrint HTML→PDF + pypdf merge primitives.

Two functions, two responsibilities:
  - render_html_string_to_pdf / render_template_to_pdf: Jinja2 + WeasyPrint
  - merge_pdfs: pypdf concatenation

The Jinja2 environment auto-escapes HTML to prevent injection from user-controlled
fields (item description, part names, notes).
"""
from io import BytesIO
from pathlib import Path
from typing import Mapping

import jinja2
import pypdf
import weasyprint

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
)


def render_html_string_to_pdf(html: str, *, base_url: str | None = None) -> bytes:
    """Render an HTML string to PDF bytes via WeasyPrint."""
    return weasyprint.HTML(string=html, base_url=base_url or str(TEMPLATES_DIR)).write_pdf()


def render_template_to_pdf(template_name: str, ctx: Mapping) -> bytes:
    """Render a Jinja2 template to PDF bytes via WeasyPrint."""
    html = _env.get_template(template_name).render(**ctx)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()


def merge_pdfs(parts: list[bytes]) -> bytes:
    """Concatenate PDF byte sources in order. Empty list returns an empty PDF."""
    writer = pypdf.PdfWriter()
    for part in parts:
        writer.append(BytesIO(part))
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
