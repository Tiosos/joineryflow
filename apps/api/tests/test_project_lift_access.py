"""Project lift access (migration 0036): the sketch is a drawing or photo, never a model file."""
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


@pytest.fixture
def client(truncate_all, tmp_path: Path, monkeypatch):
    truncate_all()
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    slug = f"la-{uuid.uuid4().hex[:8]}"
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES(:s,'LA') RETURNING id"),
                        {"s": slug}).scalar()
        s.execute(text("""INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
                          VALUES(:w,'d@la.test','D',:p,'drafter')"""),
                  {"w": wid, "p": hash_password("pw")})
        pid = s.execute(text("""INSERT INTO projects(project_code,name,workspace_id)
                                VALUES(:s,:s,:w) RETURNING project_id"""),
                        {"s": slug, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    c = TestClient(app)
    assert c.post("/auth/login", json={"workspace_slug": slug, "email": "d@la.test",
                                       "password": "pw"}).status_code == 200
    c.pid = pid
    yield c
    shutil.rmtree(tmp_path, ignore_errors=True)


def _upload(c, name: str, data: bytes) -> int:
    r = c.post("/files", files={"file": (name, io.BytesIO(data), "application/octet-stream")})
    assert r.status_code == 201, r.text
    return r.json()["file_blob_id"]


def test_pdf_sketch_accepted(client):
    pdf = _upload(client, "lift.pdf", b"%PDF-1.4\n" + b"x" * 100)
    r = client.put(f"/projects/{client.pid}/lift-access",
                   json={"notes": "Rear dock", "sketch_file_blob_id": pdf})
    assert r.status_code == 200, r.text
    assert r.json()["sketch_file_blob_id"] == pdf


def test_model_file_sketch_is_415(client):
    cvj = _upload(client, "job.cvj", b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + b"\x00" * 100)
    r = client.put(f"/projects/{client.pid}/lift-access", json={"sketch_file_blob_id": cvj})
    assert r.status_code == 415, r.text
