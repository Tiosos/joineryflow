"""Quote PDF rendering — sub-project #9a.

Reuses the WeasyPrint + Jinja2 stack from #5b's printing/engine.py but
loads templates from the estimating module's own templates directory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import jinja2
import weasyprint

TEMPLATES_DIR = Path(__file__).parent / "templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=jinja2.select_autoescape(["html"]),
)


def _money(value) -> str:
    if value is None:
        return "$0.00"
    dec = Decimal(str(value)).quantize(Decimal("0.01"))
    return f"${dec:,.2f}"


_env.filters["money"] = _money


def render_quote_pdf(
    *, estimate: Mapping, revision: Mapping, is_draft: bool = False,
) -> bytes:
    """Render the customer-facing quote PDF.

    When `is_draft` is True the template renders a diagonal "DRAFT — NOT FOR
    CLIENT" watermark so internal reviewers can preview the PDF before
    lock-and-send.
    """
    today = datetime.now(timezone.utc).strftime("%d %b %Y")
    ctx = {
        "estimate": estimate,
        "revision": revision,
        "customer": estimate["customer"],
        "today": today,
        "is_draft": is_draft,
    }
    html = _env.get_template("quote.html").render(**ctx)
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()
