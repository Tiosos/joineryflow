"""RBAC for shop_drawings — viewer denied, editor read+write but no approve, drafter elevated."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    # Also truncate after — peer test files use the rollback-only `db` fixture
    # and cannot undo data we committed via SessionLocal in this file.
    truncate_all()
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _seed(client) -> dict:
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    out = {}
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hw','HW') RETURNING id")).scalar()
        out["wid"] = wid
        for role in ("drafter", "editor", "manager", "viewer"):
            uid = s.execute(text("""
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, :r, :p, :r2) RETURNING id
            """), {"w": wid, "e": f"{role}@hw.test", "r": role, "p": hash_password("pw"), "r2": role}).scalar()
            out[role] = uid
        out["pid"] = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('A','A', :u) RETURNING project_id
        """), {"u": out["manager"]}).scalar()
        s.commit()
    finally:
        s.close()
    return out


def _login(client, role: str):
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "hw", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200


def test_viewer_can_read_but_not_create(client):
    ids = _seed(client)
    _login(client, "viewer")
    r = client.get(f"/projects/{ids['pid']}/shop-drawings")
    assert r.status_code == 200
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 403


def test_editor_can_upload_and_create_but_not_approve(client):
    ids = _seed(client)
    _login(client, "editor")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201
    blob_id = r.json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id, "submit_immediately": True,
    })
    assert r.status_code == 201
    did = r.json()["drawing_id"]
    rid = r.json()["revisions"][0]["revision_id"]
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 403  # editor lacks the 'approve' action on shop_dwgs


def test_drafter_can_approve_others_revision(client):
    """Drafter has approve in the matrix; the not-uploader rule still applies in-handler."""
    ids = _seed(client)
    # Editor uploads + submits.
    _login(client, "editor")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    blob_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id, "submit_immediately": True,
    })
    did = r.json()["drawing_id"]
    rid = r.json()["revisions"][0]["revision_id"]
    # Drafter approves (different uploader → allowed).
    _login(client, "drafter")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 200


def test_manager_can_archive(client):
    ids = _seed(client)
    _login(client, "drafter")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    blob_id = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T", "room": "K", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    _login(client, "manager")
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 204
