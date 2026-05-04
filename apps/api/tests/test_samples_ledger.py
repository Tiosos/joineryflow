"""Samples — Approval ledger (audit_log filtered)."""
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_disk(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FILE_STORE_ROOT", str(tmp_path))
    yield
    if tmp_path.exists():
        shutil.rmtree(tmp_path, ignore_errors=True)


def _seed(client, truncate_all) -> dict:
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('lg','LG') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'd@lg.test', 'D', :p, 'drafter') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('LG-001','LG',:u,:w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "lg", "email": "d@lg.test", "password": "pw"})
    assert r.status_code == 200
    return {"wid": wid, "uid": uid, "pid": pid}


def test_ledger_returns_audit_rows(client, truncate_all):
    ids = _seed(client, truncate_all)
    # Create 3 samples to generate 3 sample.create audit rows
    for n in range(3):
        client.post(f"/projects/{ids['pid']}/samples", json={"title": f"L{n}", "hex_swatch": "#aabbcc"})
    r = client.get(f"/projects/{ids['pid']}/samples/ledger")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 3
    events = [e["event"] for e in body["entries"]]
    assert all(e.startswith("sample.") for e in events)
    assert "sample.create" in events


def test_ledger_pagination(client, truncate_all):
    ids = _seed(client, truncate_all)
    for n in range(5):
        client.post(f"/projects/{ids['pid']}/samples", json={"title": f"L{n}", "hex_swatch": "#aabbcc"})
    r = client.get(f"/projects/{ids['pid']}/samples/ledger?limit=2&offset=0")
    body = r.json()
    assert len(body["entries"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["total"] >= 5


def test_ledger_cross_project_isolation(client, truncate_all):
    """Ledger only includes samples from the requested project."""
    ids = _seed(client, truncate_all)
    # Create project B in same workspace
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        pid_b = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('LG-002','LG2',:u,:w) RETURNING project_id
        """), {"u": ids["uid"], "w": ids["wid"]}).scalar()
        s.commit()
    finally:
        s.close()
    client.post(f"/projects/{ids['pid']}/samples", json={"title": "A", "hex_swatch": "#aabbcc"})
    client.post(f"/projects/{pid_b}/samples", json={"title": "B", "hex_swatch": "#aabbcc"})
    r = client.get(f"/projects/{ids['pid']}/samples/ledger")
    sample_ids = {e["sample_id"] for e in r.json()["entries"]}
    # Only project A's samples should appear; the project B sample id is excluded.
    # We can't trivially get the exact id, but we know there should be exactly 1 sample.create event.
    create_events = [e for e in r.json()["entries"] if e["event"] == "sample.create"]
    assert len(create_events) == 1
