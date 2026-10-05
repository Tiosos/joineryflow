"""Item Document Register (migration 0036, Item & Project Detail 2.0 T06).

What these pin down:

  - list / bind / relabel-reorder / unbind round-trip
  - PDF, PNG and JPEG are accepted; anything else is 415
  - every mutation writes audit_log AND item_edit_log
  - another workspace's item, blob or document is 404, never a leak
  - related parts have no register (same rule as the named attachment slots)
  - RBAC is list:read to list, list:write to mutate — so editors may bind
"""
import uuid

import pytest


from .helpers_documents import PDF_BYTES, PNG_BYTES, _client, _sql, _upload, _workspace, reset_disk  # noqa: F401













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
