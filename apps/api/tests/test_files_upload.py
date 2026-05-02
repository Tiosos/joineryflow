"""POST /files — multipart upload with magic-byte validation + sha256 dedup."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n" + b"x" * 100 + b"\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200


@pytest.fixture(autouse=True)
def reset_db_and_disk(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _login(client, role: str = "editor") -> tuple[int, int]:
    """Create workspace+user, log in via API, return (workspace_id, user_id).

    Default role is `editor`: editor has read+write on shop_dwgs in the matrix
    but lacks `approve`, which is the right baseline for testing upload-only
    paths. Tests that need a no-write role (e.g. 403 cases) pass role='viewer'.
    """
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password

    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('hartwood','HW') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'Test User', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@hw.test", "p": hash_password("pw"), "r": role}).scalar()
        s.commit()
    finally:
        s.close()

    r = client.post("/auth/login", json={"workspace_slug": "hartwood", "email": f"{role}@hw.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return wid, uid


def test_upload_pdf_happy_path(client):
    _login(client)
    files = {"file": ("kitchen.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mime"] == "application/pdf"
    assert body["original_filename"] == "kitchen.pdf"
    assert body["byte_size"] == len(PDF_BYTES)
    assert body["deduped"] is False
    assert "file_blob_id" in body
    assert len(body["sha256"]) == 64


def test_upload_png_happy_path(client):
    _login(client)
    files = {"file": ("photo.png", io.BytesIO(PNG_BYTES), "image/png")}
    r = client.post("/files", files=files)
    assert r.status_code == 201, r.text
    assert r.json()["mime"] == "image/png"


def test_upload_dedup_same_bytes_returns_existing(client):
    _login(client)
    files1 = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r1 = client.post("/files", files=files1)
    assert r1.status_code == 201
    id1 = r1.json()["file_blob_id"]

    files2 = {"file": ("renamed.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r2 = client.post("/files", files=files2)
    assert r2.status_code == 201
    body2 = r2.json()
    assert body2["file_blob_id"] == id1
    assert body2["deduped"] is True


def test_upload_oversize_rejected_413(client):
    _login(client)
    huge = b"%PDF-" + b"x" * (26 * 1024 * 1024)  # 26 MB
    files = {"file": ("big.pdf", io.BytesIO(huge), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 413
    assert "size" in r.json()["detail"].lower()


def test_upload_unknown_mime_rejected_415(client):
    _login(client)
    files = {"file": ("a.svg", io.BytesIO(b"<svg></svg>"), "image/svg+xml")}
    r = client.post("/files", files=files)
    assert r.status_code == 415


def test_upload_extension_mismatch_rejected_415(client):
    _login(client)
    # PDF bytes with a .png filename
    files = {"file": ("a.png", io.BytesIO(PDF_BYTES), "image/png")}
    r = client.post("/files", files=files)
    assert r.status_code == 415


def test_upload_unauthenticated_401(client):
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 401


def test_upload_viewer_forbidden_403(client):
    _login(client, role="viewer")
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 403
