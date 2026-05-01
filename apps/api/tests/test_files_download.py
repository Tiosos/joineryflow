"""GET /files/{id} — RBAC-gated streaming download."""
import io
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


PDF_BYTES = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n" + b"x" * 100 + b"\n%%EOF\n"


@pytest.fixture(autouse=True)
def reset(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


def _seed_workspace_and_login(client, slug: str, role: str = "editor") -> int:
    from app.db import SessionLocal
    from sqlalchemy import text
    from app.auth.passwords import hash_password

    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'WS') RETURNING id"),
                        {"s": slug}).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r)
        """), {"w": wid, "e": f"u@{slug}.test", "p": hash_password("pw"), "r": role})
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": slug, "email": f"u@{slug}.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return wid


def _upload(client) -> int:
    files = {"file": ("a.pdf", io.BytesIO(PDF_BYTES), "application/pdf")}
    r = client.post("/files", files=files)
    assert r.status_code == 201
    return r.json()["file_blob_id"]


def test_download_streams_bytes(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)

    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 200
    assert r.content == PDF_BYTES
    assert r.headers["content-type"].startswith("application/pdf")
    assert "inline" in r.headers["content-disposition"]
    assert "a.pdf" in r.headers["content-disposition"]


def test_download_missing_id_returns_404(client):
    _seed_workspace_and_login(client, "hartwood")
    r = client.get("/files/999999")
    assert r.status_code == 404


def test_download_cross_workspace_returns_404_not_403(client):
    """Caller in workspace A must not be able to fetch a blob from workspace B,
    and the response must not leak existence (404, not 403)."""
    _seed_workspace_and_login(client, "ws-a")
    blob_id = _upload(client)
    # Switch login to a different workspace
    client.cookies.clear()
    _seed_workspace_and_login(client, "ws-b")
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 404


def test_download_unauthenticated_401(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)
    client.cookies.clear()
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 401


def test_download_content_disposition_filename_present(client):
    _seed_workspace_and_login(client, "hartwood")
    blob_id = _upload(client)
    r = client.get(f"/files/{blob_id}")
    assert r.status_code == 200
    cd = r.headers["content-disposition"]
    assert cd.startswith("inline;")
    assert "filename=" in cd
