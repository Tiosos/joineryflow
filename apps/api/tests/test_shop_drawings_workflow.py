"""Revision state machine + not-uploader rule + in-flight 409."""
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


def _seed_two_users(client) -> dict:
    """Create one workspace + drafter (uploader) + manager (reviewer) + project."""
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hw','HW') RETURNING id")).scalar()
        d_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'd@hw.test', 'D', :p, 'drafter') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        m_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'm@hw.test', 'M', :p, 'manager') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id) VALUES('ALF-001','A',:u) RETURNING project_id
        """), {"u": m_id}).scalar()
        s.commit()
    finally:
        s.close()
    return {"wid": wid, "drafter": d_id, "manager": m_id, "pid": pid}


def _login(client, who: str):
    client.cookies.clear()
    r = client.post("/auth/login",
                    json={"workspace_slug": "hw", "email": f"{who}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text


def _upload(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    return r.json()["file_blob_id"]


def _create_drawing(client, pid: int, file_blob_id: int) -> dict:
    r = client.post(f"/projects/{pid}/shop-drawings", json={
        "title": "T", "room": "Kitchen", "file_blob_id": file_blob_id,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_submit_then_approve_makes_it_current(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    drawing = _create_drawing(client, ids["pid"], blob_id)
    rid = drawing["revisions"][0]["revision_id"]
    did = drawing["drawing_id"]

    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"

    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = client.get(f"/shop-drawings/{did}")
    assert r.json()["current_revision_id"] == rid


def test_uploader_cannot_approve_own_revision(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")

    # Drafter is also approve-permitted in matrix, but the in-handler rule blocks self-approval.
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    assert r.status_code == 403
    assert "uploader" in r.json()["detail"].lower()


def test_reject_requires_note(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/reject", json={"review_note": ""})
    assert r.status_code == 422  # pydantic min_length=1


def test_reject_with_note_changes_state_but_not_current(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/reject",
                    json={"review_note": "needs more dimensions"})
    assert r.status_code == 200
    detail = client.get(f"/shop-drawings/{did}").json()
    assert detail["current_revision_id"] is None
    assert detail["revisions"][0]["status"] == "rejected"
    assert detail["revisions"][0]["review_note"] == "needs more dimensions"


def test_withdraw_only_by_uploader(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")

    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/withdraw")
    assert r.status_code == 403


def test_cannot_submit_from_approved(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob_id = _upload(client)
    d = _create_drawing(client, ids["pid"], blob_id)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    _login(client, "m")
    client.post(f"/shop-drawings/{did}/revisions/{rid}/approve")
    _login(client, "d")
    r = client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    assert r.status_code == 409


def test_two_in_flight_revisions_409(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob1 = _upload(client)
    d = _create_drawing(client, ids["pid"], blob1)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    # Upload a second blob (different bytes so dedup doesn't return the same id).
    files = {"file": ("b.pdf", io.BytesIO(PDF_BYTES + b"\nextra"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 409
    assert "in-flight" in r.json()["detail"].lower()


def test_after_withdraw_revision_is_still_in_flight_409(client):
    """Withdraw moves pending → draft, but draft is still in-flight per the partial
    unique index, so a new revision upload is rejected with 409."""
    ids = _seed_two_users(client)
    _login(client, "d")
    blob1 = _upload(client)
    d = _create_drawing(client, ids["pid"], blob1)
    did, rid = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid}/submit")
    client.post(f"/shop-drawings/{did}/revisions/{rid}/withdraw")
    files = {"file": ("c.pdf", io.BytesIO(PDF_BYTES + b"\nx"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    # The previous revision is now back in 'draft' (still in-flight). Cannot upload another.
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 409


def test_after_approve_can_upload_new_revision(client):
    """After a revision is approved (terminal), a new revision can be uploaded."""
    ids = _seed_two_users(client)
    _login(client, "d")
    blob1 = _upload(client)
    d = _create_drawing(client, ids["pid"], blob1)
    did, rid1 = d["drawing_id"], d["revisions"][0]["revision_id"]
    client.post(f"/shop-drawings/{did}/revisions/{rid1}/submit")
    _login(client, "m")
    client.post(f"/shop-drawings/{did}/revisions/{rid1}/approve")

    _login(client, "d")
    files = {"file": ("v2.pdf", io.BytesIO(PDF_BYTES + b"\nv2"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 201
    detail = r.json()
    assert len(detail["revisions"]) == 2
    assert detail["revisions"][0]["status"] == "draft"  # latest first
    assert detail["revisions"][0]["rev_no"] == 2


def test_archive_blocks_no_further_revisions_via_subtab(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob = _upload(client)
    d = _create_drawing(client, ids["pid"], blob)
    did = d["drawing_id"]
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 204
    detail = client.get(f"/shop-drawings/{did}").json()
    assert detail["archived_at"] is not None


def test_archive_already_archived_returns_409(client):
    ids = _seed_two_users(client)
    _login(client, "d")
    blob = _upload(client)
    d = _create_drawing(client, ids["pid"], blob)
    did = d["drawing_id"]
    _login(client, "m")
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 204
    r = client.post(f"/shop-drawings/{did}/archive")
    assert r.status_code == 409
    assert "already archived" in r.json()["detail"].lower()


def test_404_for_drawing_in_other_workspace(client):
    """Cross-workspace drawing fetch returns 404 (not 403)."""
    ids = _seed_two_users(client)
    _login(client, "d")
    blob = _upload(client)
    d = _create_drawing(client, ids["pid"], blob)
    did = d["drawing_id"]

    # Switch to a brand-new workspace
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsb','B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    client.post("/auth/login", json={"workspace_slug": "wsb", "email": "b@b.test", "password": "pw"})
    r = client.get(f"/shop-drawings/{did}")
    assert r.status_code == 404


def test_editor_cannot_add_revision(client):
    """Spec §6.2: editor lacks 'Upload new revision' authority even though
    they hold the write action on shop_dwgs."""
    ids = _seed_two_users(client)
    # Promote a third user to editor and have them try to add a revision.
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'e@hw.test', 'E', :p, 'editor')
        """), {"w": ids["wid"], "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()

    # Drafter creates the drawing.
    _login(client, "d")
    blob_id = _upload(client)
    drawing = _create_drawing(client, ids["pid"], blob_id)
    did = drawing["drawing_id"]

    # Editor logs in and tries to add a revision.
    client.cookies.clear()
    r = client.post("/auth/login",
                    json={"workspace_slug": "hw", "email": "e@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    files = {"file": ("c.pdf", io.BytesIO(PDF_BYTES + b"\nx"), "application/pdf")}
    blob2 = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/shop-drawings/{did}/revisions", json={"file_blob_id": blob2})
    assert r.status_code == 403
    assert "drafters, managers, or admins" in r.json()["detail"].lower()
