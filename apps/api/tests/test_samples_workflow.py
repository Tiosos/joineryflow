"""Samples — workflow state machine tests (approve/reject/archive)."""
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


def _seed_two_users(client, truncate_all) -> dict:
    """Workspace + drafter (creator) + manager (reviewer) + project."""
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wf','WF') RETURNING id")).scalar()
        d_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'd@wf.test', 'D', :p, 'drafter') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        m_id = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'm@wf.test', 'M', :p, 'manager') RETURNING id
        """), {"w": wid, "p": hash_password("pw")}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('WF-001','W',:u,:w) RETURNING project_id
        """), {"u": m_id, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    return {"wid": wid, "drafter": d_id, "manager": m_id, "pid": pid}


def _login(client, who: str):
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "wf", "email": f"{who}@wf.test", "password": "pw"})
    assert r.status_code == 200, r.text


def _create_sample(client, pid: int, title: str = "T") -> int:
    r = client.post(f"/projects/{pid}/samples", json={"title": title, "hex_swatch": "#aabbcc"})
    assert r.status_code == 201, r.text
    return r.json()["sample_id"]


def test_approve_by_non_creator_works(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])

    _login(client, "m")
    r = client.post(f"/samples/{sid}/approve", json={"review_note": "Looks good"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"


def test_approve_own_sample_returns_403(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    r = client.post(f"/samples/{sid}/approve", json={})
    assert r.status_code == 403


def test_reject_without_note_returns_422(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    r = client.post(f"/samples/{sid}/reject", json={"review_note": ""})
    assert r.status_code == 422


def test_reject_with_note_transitions(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    r = client.post(f"/samples/{sid}/reject", json={"review_note": "Too dark"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["review_note"] == "Too dark"


def test_approved_sample_can_be_archived(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    client.post(f"/samples/{sid}/approve", json={})
    r = client.post(f"/samples/{sid}/archive")
    assert r.status_code == 204


def test_archived_sample_stays_out_of_board(client, truncate_all):
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    client.post(f"/samples/{sid}/approve", json={})
    client.post(f"/samples/{sid}/archive")
    r = client.get(f"/projects/{ids['pid']}/samples?subtab=board")
    assert r.status_code == 200
    sids = {s["sample_id"] for s in r.json()["samples"]}
    assert sid not in sids


def test_rejected_sample_auto_shows_in_archive(client, truncate_all):
    """Rejected → automatic Archive subtab membership (no explicit archive needed)."""
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    client.post(f"/samples/{sid}/reject", json={"review_note": "no"})
    r = client.get(f"/projects/{ids['pid']}/samples?subtab=archive")
    assert r.status_code == 200
    sids = {s["sample_id"] for s in r.json()["samples"]}
    assert sid in sids


def test_cannot_approve_already_rejected(client, truncate_all):
    """Once rejected, terminal — no further state transitions."""
    ids = _seed_two_users(client, truncate_all)
    _login(client, "d")
    sid = _create_sample(client, ids["pid"])
    _login(client, "m")
    client.post(f"/samples/{sid}/reject", json={"review_note": "no"})
    r = client.post(f"/samples/{sid}/approve", json={})
    assert r.status_code == 409
