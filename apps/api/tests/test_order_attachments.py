"""Order attachments: the FILE and PDF boxes of the order pop-up (`orders/attachments.py`)."""
import pytest
from sqlalchemy import text

from app.db import SessionLocal

from .conftest import truncate_fixture
from .helpers import login, login_same_workspace

_cleanup = truncate_fixture("po_attachments", "file_blob")

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _sql(sql: str, **p):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), p)
        val = out.scalar() if out.returns_rows else None
        s.commit()
        return val
    finally:
        s.close()


@pytest.fixture
def ws():
    buyer, wid, _ = login("purchase_officer", prefix="oa")
    vendor = _sql("INSERT INTO vendors(name, category, workspace_id) VALUES ('V', 'Board', :w) RETURNING vendor_id", w=wid)
    viewer, _ = login_same_workspace(wid, "viewer")
    order = buyer.post("/orders", json={"vendor_id": vendor, "description": "o", "total_amount": "10"}).json()["po_id"]
    return {"buyer": buyer, "viewer": viewer, "vendor": vendor, "order": order, "wid": wid}


def _up(c, order, name, data, kind="File"):
    return c.post(f"/orders/{order}/attachments", files={"file": (name, data)}, data={"attachment_type": kind})


def test_upload_list_download_delete(ws):
    c, o = ws["buyer"], ws["order"]
    r = _up(c, o, "quote.pdf", PDF, "PDF")
    assert r.status_code == 201, r.text
    [a] = r.json()["attachments"]
    assert a["file_name"] == "quote.pdf" and a["attachment_type"] == "PDF" and a["uploaded_by_name"]
    assert c.get(f"/orders/{o}").json()["has_attachment"] is True
    d = c.get(f"/orders/{o}/attachments/{a['attachment_id']}/download")
    assert d.status_code == 200 and d.content == PDF and d.headers["content-type"] == "application/pdf"
    assert ws["viewer"].get(f"/orders/{o}/attachments").status_code == 200
    r = c.delete(f"/orders/{o}/attachments/{a['attachment_id']}")
    assert r.status_code == 200 and r.json()["attachments"] == []
    assert c.delete(f"/orders/{o}/attachments/{a['attachment_id']}").status_code == 404
    assert c.get(f"/orders/{o}").json()["has_attachment"] is False


def test_file_rules(ws):
    c, o = ws["buyer"], ws["order"]
    assert _up(c, o, "pic.png", PNG).status_code == 201                      # File box: any allowed type
    assert _up(c, o, "pic2.png", PNG + b"1", "PDF").status_code == 415       # PDF box: PDF only
    assert _up(c, o, "evil.pdf", b"not a pdf at all!!").status_code == 415   # content sniffed
    assert _up(c, o, "wrong.png", PDF).status_code == 415                    # extension must agree
    assert _up(c, o, "empty.pdf", b"").status_code == 400
    # the same bytes twice share one stored blob
    _up(c, o, "again.png", PNG)
    assert _sql("SELECT count(*) FROM file_blob") == 1


def test_rbac_and_frozen_orders(ws):
    c, o, v = ws["buyer"], ws["order"], ws["viewer"]
    assert _up(v, o, "q.pdf", PDF).status_code == 403
    aid = _up(c, o, "q.pdf", PDF).json()["attachments"][0]["attachment_id"]
    assert v.delete(f"/orders/{o}/attachments/{aid}").status_code == 403
    assert c.patch(f"/orders/{o}", json={"status": "Cancelled"}).status_code == 200
    r = _up(c, o, "late.pdf", PDF)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ORDER_LOCKED"
    assert c.delete(f"/orders/{o}/attachments/{aid}").status_code == 409
    assert c.get(f"/orders/{o}/attachments/{aid}/download").status_code == 200   # downloads stay open


def test_other_workspace_is_404(ws):
    c, o = ws["buyer"], ws["order"]
    aid = _up(c, o, "q.pdf", PDF).json()["attachments"][0]["attachment_id"]
    other, _, _ = login("admin", prefix="ob")
    for r in (other.get(f"/orders/{o}/attachments"), _up(other, o, "x.pdf", PDF),
              other.get(f"/orders/{o}/attachments/{aid}/download"), other.delete(f"/orders/{o}/attachments/{aid}")):
        assert r.status_code == 404
    assert len(c.get(f"/orders/{o}/attachments").json()["attachments"]) == 1
