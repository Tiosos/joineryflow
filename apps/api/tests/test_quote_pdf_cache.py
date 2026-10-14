"""0062: the quote PDF is kept per revision and reused while the HTML it came from is unchanged."""
from sqlalchemy import text

from app.db import SessionLocal
from app.estimating import pdf as pdf_engine

from .conftest import truncate_fixture
from .helpers_estimating import _bootstrap, _make_estimate

_cleanup = truncate_fixture("quote_pdf_cache")


def _renders(monkeypatch) -> list[int]:
    calls: list[int] = []
    real = pdf_engine.html_to_pdf

    def counting(html: str) -> bytes:
        calls.append(1)
        return real(html)

    monkeypatch.setattr(pdf_engine, "html_to_pdf", counting)
    return calls


def _rows(rid: int) -> list[str]:
    with SessionLocal() as db:
        return [r[0] for r in db.execute(
            text("SELECT html_sha256 FROM quote_pdf_cache WHERE revision_id = :r"), {"r": rid})]


def test_second_download_is_served_from_the_cache(monkeypatch):
    calls = _renders(monkeypatch)
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    first = c.get(f"/revisions/{rid}/quote.pdf")
    second = c.get(f"/revisions/{rid}/quote.pdf")
    assert first.status_code == second.status_code == 200
    assert second.content == first.content and first.content.startswith(b"%PDF")
    assert len(calls) == 1
    assert len(_rows(rid)) == 1


def test_a_changed_quote_is_rendered_again_and_replaces_the_row(monkeypatch):
    calls = _renders(monkeypatch)
    c, *_ = _bootstrap()
    rid = _make_estimate(c)["current_revision_id"]
    c.get(f"/revisions/{rid}/quote.pdf")
    before = _rows(rid)
    r = c.post(f"/revisions/{rid}/lines", json={"description": "A new line", "qty": 1})
    assert r.status_code in (200, 201), r.text
    again = c.get(f"/revisions/{rid}/quote.pdf")
    assert again.status_code == 200
    assert len(calls) == 2
    after = _rows(rid)
    assert len(after) == 1 and after != before
