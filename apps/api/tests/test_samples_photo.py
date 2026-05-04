"""Samples — photo bind/replace/clear (PNG/JPEG only)."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
PDF_BYTES = b"%PDF-1.4\n%abc\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _setup(client, truncate_all, role: str = "drafter") -> dict:
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('ph','PH') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@ph.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('PH-001','PH',:u,:w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "ph", "email": f"{role}@ph.test", "password": "pw"})
    assert r.status_code == 200, r.text
    # Create one pending sample (viewer cannot POST samples, so skip and let test insert directly)
    sid = None
    if role != "viewer":
        r = client.post(f"/projects/{pid}/samples", json={"title": "P", "hex_swatch": "#aabbcc"})
        sid = r.json()["sample_id"]
    return {"wid": wid, "uid": uid, "pid": pid, "sid": sid}


def test_bind_png_photo(client, truncate_all):
    ids = _setup(client, truncate_all)
    files = {"file": ("p.png", io.BytesIO(PNG_BYTES), "image/png")}
    bid = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/samples/{ids['sid']}/photo", json={"file_blob_id": bid})
    assert r.status_code == 204
    r = client.get(f"/samples/{ids['sid']}")
    assert r.json()["photo_file_blob_id"] == bid


def test_bind_pdf_photo_rejected_415(client, truncate_all):
    ids = _setup(client, truncate_all)
    files = {"file": ("p.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    bid = client.post("/files", files=files).json()["file_blob_id"]
    r = client.post(f"/samples/{ids['sid']}/photo", json={"file_blob_id": bid})
    assert r.status_code == 415


def test_replace_photo_audit_captures_replaced_id(client, truncate_all):
    ids = _setup(client, truncate_all)
    bid1 = client.post("/files", files={"file": ("a.png", io.BytesIO(PNG_BYTES), "image/png")}).json()["file_blob_id"]
    client.post(f"/samples/{ids['sid']}/photo", json={"file_blob_id": bid1})
    # Replace
    bid2 = client.post("/files", files={"file": ("b.png", io.BytesIO(PNG_BYTES + b"\x00"), "image/png")}).json()["file_blob_id"]
    r = client.post(f"/samples/{ids['sid']}/photo", json={"file_blob_id": bid2})
    assert r.status_code == 204
    # Audit row check
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        row = s.execute(text("""
            SELECT payload FROM audit_log
             WHERE event = 'sample.upload_photo' AND target = :t
             ORDER BY id DESC LIMIT 1
        """), {"t": str(ids["sid"])}).scalar()
        assert row.get("replaced_file_blob_id") == bid1
    finally:
        s.close()


def test_clear_photo(client, truncate_all):
    ids = _setup(client, truncate_all)
    bid = client.post("/files", files={"file": ("p.png", io.BytesIO(PNG_BYTES), "image/png")}).json()["file_blob_id"]
    client.post(f"/samples/{ids['sid']}/photo", json={"file_blob_id": bid})
    r = client.delete(f"/samples/{ids['sid']}/photo")
    assert r.status_code == 204
    r = client.get(f"/samples/{ids['sid']}")
    assert r.json()["photo_file_blob_id"] is None


def test_viewer_cannot_upload_photo(client, truncate_all):
    """Viewer lacks isample:write — 403 on POST photo."""
    ids = _setup(client, truncate_all, role="viewer")
    # Viewer also can't even create samples or files; setup sample as drafter via direct DB.
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        sid = s.execute(text("""
            INSERT INTO sample(project_id, title, hex_swatch, created_by)
            VALUES (:p, 'V', '#aabbcc', :u) RETURNING sample_id
        """), {"p": ids["pid"], "u": ids["uid"]}).scalar()
        s.commit()
    finally:
        s.close()
    # Viewer attempts to bind photo (we don't even need a real blob; route should reject before that).
    r = client.post(f"/samples/{sid}/photo", json={"file_blob_id": 1})
    assert r.status_code == 403
