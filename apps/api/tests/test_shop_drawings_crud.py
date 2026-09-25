"""Shop Drawings — CRUD route tests (workflow tests are in Task 11)."""
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
    # Also truncate after — peer test files (e.g. test_shop_drawings_subtab_query.py)
    # use the rollback-only `db` fixture and cannot undo data we committed via
    # SessionLocal in this file.
    truncate_all()
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _setup(client, role: str = "drafter") -> dict:
    """Seed workspace + user + project, log in. Return ids."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hartwood','HW') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@hw.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('ALF-001', 'Alfred', :u, :w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"wid": wid, "uid": uid, "pid": pid}


def _upload_blob(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    return r.json()["file_blob_id"]


def test_create_drawing_creates_rev_1_in_draft(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Kitchen base run", "room": "Kitchen", "file_blob_id": blob_id,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Kitchen base run"
    assert body["room"] == "Kitchen"
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["status"] == "draft"
    assert body["revisions"][0]["rev_no"] == 1


def test_create_drawing_with_submit_immediately_lands_in_pending(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Bath vanity", "room": "Bath", "file_blob_id": blob_id,
        "submit_immediately": True,
    })
    assert r.status_code == 201
    assert r.json()["revisions"][0]["status"] == "pending"


def test_list_subtab_in_review(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "T1", "room": "Kitchen", "file_blob_id": blob_id, "submit_immediately": True,
    })
    r = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"subtab": "in_review"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(d["title"] == "T1" for d in body["drawings"])


def test_patch_drawing_updates_title(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Original", "room": "Kitchen", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    r2 = client.patch(f"/shop-drawings/{did}", json={"title": "Updated"})
    assert r2.status_code == 200
    assert r2.json()["title"] == "Updated"


def test_archive_drawing_moves_it_to_archive_subtab(client):
    ids = _setup(client)
    blob_id = _upload_blob(client)
    r = client.post(f"/projects/{ids['pid']}/shop-drawings", json={
        "title": "Pantry", "room": "Kitchen", "file_blob_id": blob_id,
    })
    did = r.json()["drawing_id"]
    # Need to be manager to archive — re-setup as manager
    client.cookies.clear()
    # Promote the same user to manager via direct DB
    from app.db import SessionLocal
    from sqlalchemy import text
    s = SessionLocal()
    try:
        s.execute(text("UPDATE app_user SET auth_role='manager' WHERE id=:u"), {"u": ids["uid"]})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": "drafter@hw.test", "password": "pw"})
    assert r.status_code == 200
    r3 = client.post(f"/shop-drawings/{did}/archive")
    assert r3.status_code == 204, r3.text
    r4 = client.get(f"/projects/{ids['pid']}/shop-drawings", params={"subtab": "archive"})
    assert r4.status_code == 200
    assert any(d["drawing_id"] == did for d in r4.json()["drawings"])


def test_create_drawing_cross_workspace_blob_rejected(client):
    """Try to create a drawing referencing a file_blob from another workspace → 422."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    # Set up workspace A + login + upload
    ids_a = _setup(client)
    blob_id_a = _upload_blob(client)
    # Set up workspace B + project
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('ws-b','WS B') RETURNING id")).scalar()
        uid_b = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter') RETURNING id
        """), {"w": wid_b, "p": hash_password("pw")}).scalar()
        pid_b = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('B-001','B', :u, :w) RETURNING project_id
        """), {"u": uid_b, "w": wid_b}).scalar()
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    client.post("/auth/login", json={"workspace_slug": "ws-b", "email": "b@b.test", "password": "pw"})
    r = client.post(f"/projects/{pid_b}/shop-drawings", json={
        "title": "X", "room": "Y", "file_blob_id": blob_id_a,
    })
    assert r.status_code == 422


def test_model_files_are_refused_as_drawings(client):
    """/files also stores .skp for attachment slots; the drawing viewer can't render it."""
    ids = _setup(client)
    skp = b"\xFF\xFE\xFF\x0E" + "SketchUp Model".encode("utf-16-le") + b"\x00" * 100
    skp_id = client.post("/files", files={"file": ("m.skp", io.BytesIO(skp), "application/octet-stream")}).json()["file_blob_id"]
    r = client.post(f"/projects/{ids['pid']}/shop-drawings",
                    json={"title": "Model", "room": "Kitchen", "file_blob_id": skp_id})
    assert r.status_code == 422, r.text

    did = client.post(f"/projects/{ids['pid']}/shop-drawings",
                      json={"title": "Run", "room": "Kitchen", "file_blob_id": _upload_blob(client)}).json()["drawing_id"]
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": skp_id})
    assert r.status_code == 422, r.text
