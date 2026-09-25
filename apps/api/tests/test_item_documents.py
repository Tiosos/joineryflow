"""Item Document Register (migration 0036, Item & Project Detail 2.0 T06).

What these pin down:

  - list / bind / relabel-reorder / unbind round-trip
  - PDF, PNG and JPEG are accepted; anything else is 415
  - every mutation writes audit_log AND item_edit_log
  - another workspace's item, blob or document is 404, never a leak
  - related parts have no register (same rule as the named attachment slots)
  - RBAC is list:read to list, list:write to mutate — so editors may bind
"""
import io
import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    shutil.rmtree(tmp_path, ignore_errors=True)


def _sql(sql: str, params: dict | None = None):
    s = SessionLocal()
    try:
        out = s.execute(text(sql), params or {})
        rows = out.mappings().all() if out.returns_rows else None
        s.commit()
        return rows
    finally:
        s.close()


def _workspace(roles=("drafter",)) -> dict:
    """A workspace with one user per role, a project, a joinery item and a related part."""
    slug = f"doc-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        s.execute(text("INSERT INTO status_options(status_key, sort_order)"
                       " VALUES('CLEAR',1) ON CONFLICT DO NOTHING"))
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'Doc') RETURNING id"),
                        {"s": slug}).scalar()
        for role in roles:
            s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                              VALUES(:w,:e,:n,:p,:r)"""),
                      {"w": wid, "e": f"{role}@{slug}.test", "n": role.title(),
                       "p": hash_password("pw"), "r": role})
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:c,:c,:w) RETURNING project_id"""),
                        {"c": slug.upper(), "w": wid}).scalar()
        iid = s.execute(text("""INSERT INTO items(num, project_id, description, status)
                                VALUES (nextval('joinery_number_seq'), :p, 'Vanity', 'CLEAR')
                                RETURNING item_id"""), {"p": pid}).scalar()
        rp = s.execute(text("""INSERT INTO items(num, project_id, description, status, row_type,
                                                 parent_item_id, related_part_type_key)
                               VALUES (nextval('joinery_number_seq'), :p, 'Top', 'CLEAR',
                                       'related_part', :par, 'benchtop')
                               RETURNING item_id"""), {"p": pid, "par": iid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"slug": slug, "wid": wid, "pid": pid, "iid": iid, "rp": rp}


def _client(ws: dict, role: str = "drafter") -> TestClient:
    c = TestClient(app)
    r = c.post("/auth/login", json={"workspace_slug": ws["slug"],
                                    "email": f"{role}@{ws['slug']}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return c


def _upload(c: TestClient, name="a.pdf", data=PDF_BYTES, mime="application/pdf") -> int:
    r = c.post("/files", files={"file": (name, io.BytesIO(data), mime)})
    assert r.status_code == 201, r.text
    return r.json()["file_blob_id"]


@pytest.fixture
def ws(truncate_all):
    truncate_all()
    return _workspace(roles=("drafter", "editor", "viewer", "purchase_officer"))


def test_bind_list_patch_unbind_round_trip(ws):
    c = _client(ws)
    assert c.get(f"/items/{ws['iid']}/documents").json() == []

    bid = _upload(c, name="site-photo-plan.pdf")
    r = c.post(f"/items/{ws['iid']}/documents", json={"file_blob_id": bid, "label": "Plan"})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["item_id"] == ws["iid"]
    assert doc["label"] == "Plan"
    assert doc["original_filename"] == "site-photo-plan.pdf"
    assert doc["mime_type"] == "application/pdf"
    assert doc["uploaded_by_name"] == "Drafter"

    listed = c.get(f"/items/{ws['iid']}/documents").json()
    assert [d["document_id"] for d in listed] == [doc["document_id"]]

    r = c.patch(f"/documents/{doc['document_id']}", json={"label": "Floor plan", "sort_order": 5})
    assert r.status_code == 200, r.text
    assert (r.json()["label"], r.json()["sort_order"]) == ("Floor plan", 5)

    r = c.patch(f"/documents/{doc['document_id']}", json={"label": None})
    assert r.status_code == 200
    assert r.json()["label"] is None
    assert r.json()["sort_order"] == 5

    assert c.delete(f"/documents/{doc['document_id']}").status_code == 204
    assert c.get(f"/items/{ws['iid']}/documents").json() == []
    assert c.delete(f"/documents/{doc['document_id']}").status_code == 404
    # Unbinding removes the register row only; the blob is still downloadable.
    assert c.get(f"/files/{bid}").status_code == 200


def test_list_orders_by_sort_order(ws):
    c = _client(ws)
    bid = _upload(c)
    for label, order in (("C", 30), ("A", 10), ("B", 20)):
        c.post(f"/items/{ws['iid']}/documents",
               json={"file_blob_id": bid, "label": label, "sort_order": order})
    labels = [d["label"] for d in c.get(f"/items/{ws['iid']}/documents").json()]
    assert labels == ["A", "B", "C"]


def test_png_accepted_and_other_mime_is_415(ws):
    c = _client(ws)
    png = _upload(c, name="p.png", data=PNG_BYTES, mime="image/png")
    assert c.post(f"/items/{ws['iid']}/documents", json={"file_blob_id": png}).status_code == 201

    # /files only ever stores PDF/PNG/JPEG, but file_blob itself is generic.
    txt = _sql("""INSERT INTO file_blob(workspace_id, sha256, mime, byte_size,
                                        original_filename, storage_key, uploaded_by)
                  SELECT :w, :h, 'text/plain', 3, 'n.txt', 'k', id
                    FROM app_user WHERE workspace_id = :w LIMIT 1
                  RETURNING file_blob_id""",
               {"w": ws["wid"], "h": uuid.uuid4().hex * 2})[0]["file_blob_id"]
    r = c.post(f"/items/{ws['iid']}/documents", json={"file_blob_id": txt})
    assert r.status_code == 415


def test_mutations_write_audit_and_edit_log(ws):
    c = _client(ws)
    bid = _upload(c)
    did = c.post(f"/items/{ws['iid']}/documents",
                 json={"file_blob_id": bid, "label": "Spec"}).json()["document_id"]
    c.patch(f"/documents/{did}", json={"label": "Spec v2"})
    c.patch(f"/documents/{did}", json={"label": "Spec v2"})  # no-op: nothing logged
    c.delete(f"/documents/{did}")

    events = [r["event"] for r in _sql(
        "SELECT event FROM audit_log WHERE event LIKE 'item.document.%' ORDER BY id")]
    assert events == ["item.document.bind", "item.document.update", "item.document.unbind"]

    log = _sql("SELECT field, old_value, new_value FROM item_edit_log"
               " WHERE item_id = :i ORDER BY log_id", {"i": ws["iid"]})
    assert [tuple(r.values()) for r in log] == [
        ("_document_bind", None, "Spec"),
        (f"document.{did}.label", "Spec", "Spec v2"),
        ("_document_unbind", "Spec v2", None),
    ]


def test_null_sort_order_is_422(ws):
    c = _client(ws)
    did = c.post(f"/items/{ws['iid']}/documents",
                 json={"file_blob_id": _upload(c)}).json()["document_id"]
    assert c.patch(f"/documents/{did}", json={"sort_order": None}).status_code == 422


def test_related_part_has_no_register(ws):
    c = _client(ws)
    bid = _upload(c)
    assert c.get(f"/items/{ws['rp']}/documents").status_code == 404
    assert c.post(f"/items/{ws['rp']}/documents", json={"file_blob_id": bid}).status_code == 404


def test_cross_workspace_is_404(ws):
    other = _workspace()
    theirs = _client(other)
    their_blob = _upload(theirs)
    their_doc = theirs.post(f"/items/{other['iid']}/documents",
                            json={"file_blob_id": their_blob}).json()["document_id"]

    c = _client(ws)
    mine = _upload(c)
    # Their item, their blob, their document: all invisible from here.
    assert c.get(f"/items/{other['iid']}/documents").status_code == 404
    assert c.post(f"/items/{other['iid']}/documents",
                  json={"file_blob_id": mine}).status_code == 404
    assert c.post(f"/items/{ws['iid']}/documents",
                  json={"file_blob_id": their_blob}).status_code == 404
    assert c.patch(f"/documents/{their_doc}", json={"label": "x"}).status_code == 404
    assert c.delete(f"/documents/{their_doc}").status_code == 404
    assert len(theirs.get(f"/items/{other['iid']}/documents").json()) == 1


@pytest.mark.parametrize("role,status", [
    ("editor", 201), ("viewer", 403), ("purchase_officer", 403),
])
def test_bind_rbac(ws, role, status):
    bid = _upload(_client(ws))
    c = _client(ws, role)
    assert c.get(f"/items/{ws['iid']}/documents").status_code == 200
    r = c.post(f"/items/{ws['iid']}/documents", json={"file_blob_id": bid})
    assert r.status_code == status, r.text
