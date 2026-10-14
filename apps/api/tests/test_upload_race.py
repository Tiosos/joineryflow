"""Two identical new uploads at the same moment (POST /files and POST /orders/{id}/attachments).

Both miss the dedup SELECT and both write the same bytes under the same key; the second INSERT
loses the UNIQUE (workspace_id, sha256). It must use the file that won and must NOT delete the
bytes the winner committed (they were the same key), or every download of that file is a 404.

The race is made deterministic: the store inserts and commits the winner's `file_blob` row right
after the loser has written its bytes, which is exactly the interleaving of the two requests.
"""
import hashlib

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.files import routes as files_routes
from app.files.store import LocalDiskStore
from app.main import app
from app.orders import attachments as order_attachments

from .conftest import truncate_fixture
from .helpers import login

_cleanup = truncate_fixture("po_attachments", "file_blob")

PDF = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n" + b"race" * 50 + b"\n%%EOF\n"


class RacingStore(LocalDiskStore):
    """Writes the bytes, then lets 'the other request' commit its file_blob row for them."""

    def __init__(self, root, workspace_id: int):
        super().__init__(root)
        self.workspace_id = workspace_id

    def put(self, workspace_slug, sha256, byte_stream):
        key = super().put(workspace_slug, sha256, byte_stream)
        s = SessionLocal()
        try:
            s.execute(
                text("INSERT INTO file_blob(workspace_id, sha256, mime, byte_size, original_filename, storage_key, uploaded_by)"
                     " VALUES (:w, :s, 'application/pdf', :sz, 'winner.pdf', :k,"
                     " (SELECT id FROM app_user WHERE workspace_id = :w LIMIT 1))"),
                {"w": self.workspace_id, "s": sha256, "sz": len(PDF), "k": key},
            )
            s.commit()
        finally:
            s.close()
        return key


@pytest.fixture
def racing(tmp_path):
    holder = {}

    def install(workspace_id):
        store = RacingStore(tmp_path, workspace_id)
        app.dependency_overrides[files_routes._get_store] = lambda: store
        app.dependency_overrides[order_attachments._get_store] = lambda: store
        holder["store"] = store
        return store

    yield install
    app.dependency_overrides.pop(files_routes._get_store, None)
    app.dependency_overrides.pop(order_attachments._get_store, None)


def _blob_rows(workspace_id: int):
    """This test's file: other tests (and the seed) leave file_blob rows of their own around."""
    s = SessionLocal()
    try:
        return s.execute(
            text("SELECT file_blob_id, storage_key FROM file_blob WHERE workspace_id = :w AND sha256 = :s"),
            {"w": workspace_id, "s": hashlib.sha256(PDF).hexdigest()},
        ).all()
    finally:
        s.close()


def test_post_files_loses_the_race_without_deleting_the_winners_bytes(racing):
    c, wid, _ = login("admin", prefix="rf")
    store = racing(wid)
    r = c.post("/files", files={"file": ("a.pdf", PDF)})
    assert r.status_code in (200, 201), r.text
    [(blob_id, key)] = _blob_rows(wid)
    assert r.json()["file_blob_id"] == blob_id            # the winner's row
    assert store.exists(key)                              # its bytes are still there
    assert c.get(f"/files/{blob_id}").content == PDF


def test_order_attachment_loses_the_race_without_deleting_the_winners_bytes(racing):
    c, wid, _ = login("purchase_officer", prefix="ra")
    s = SessionLocal()
    try:
        v = s.execute(text("INSERT INTO vendors(name, category, workspace_id) VALUES ('V','Board',:w) RETURNING vendor_id"),
                      {"w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    order = c.post("/orders", json={"vendor_id": v, "description": "o"}).json()["po_id"]
    store = racing(wid)
    r = c.post(f"/orders/{order}/attachments", files={"file": ("q.pdf", PDF)}, data={"attachment_type": "PDF"})
    assert r.status_code == 201, r.text
    [(blob_id, key)] = _blob_rows(wid)
    assert store.exists(key)
    [att] = r.json()["attachments"]
    d = c.get(f"/orders/{order}/attachments/{att['attachment_id']}/download")
    assert d.status_code == 200 and d.content == PDF
    assert hashlib.sha256(PDF).hexdigest() in key
