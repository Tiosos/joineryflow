"""Quote PDF rendering — sub-project #9a.

Reuses the WeasyPrint + Jinja2 stack from #5b's printing/engine.py but
loads templates from the estimating module's own templates directory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Mapping

import hashlib

import jinja2
import weasyprint
from sqlalchemy import text
from sqlalchemy.orm import Session

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


def render_quote_html(
    *, estimate: Mapping, revision: Mapping, is_draft: bool = False,
) -> str:
    """The customer-facing quote as HTML (cheap; the PDF layout is the slow part).

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
    return _env.get_template("quote.html").render(**ctx)


def html_to_pdf(html: str) -> bytes:
    return weasyprint.HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf()


def cached_quote_pdf(db: Session, *, revision_id: int, html: str) -> bytes:
    """The PDF for `html`, from `quote_pdf_cache` when this revision's last render came from the
    same HTML (0062). The key is the HTML itself, so an edit, a status change or a new day misses."""
    digest = hashlib.sha256(html.encode()).hexdigest()
    hit = db.execute(
        text("SELECT pdf FROM quote_pdf_cache WHERE revision_id = :r AND html_sha256 = :h"),
        {"r": revision_id, "h": digest},
    ).scalar()
    if hit is not None:
        return bytes(hit)
    pdf = html_to_pdf(html)
    db.execute(
        text(
            "INSERT INTO quote_pdf_cache (revision_id, html_sha256, pdf) VALUES (:r, :h, :p)"
            " ON CONFLICT (revision_id) DO UPDATE SET html_sha256 = EXCLUDED.html_sha256,"
            " pdf = EXCLUDED.pdf, created_at = now()"
        ),
        {"r": revision_id, "h": digest, "p": pdf},
    )
    return pdf
