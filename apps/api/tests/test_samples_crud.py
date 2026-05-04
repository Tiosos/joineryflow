"""Samples — CRUD route tests (HTTP via TestClient + truncate_all).

Mirrors the lock-isolation pattern from #5b: route tests in their own file,
not mixed with rollback `db` fixture tests.
"""
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


def _seed(client, truncate_all, *, role: str = "drafter") -> dict:
    """Truncate, seed status_options + workspace + user + project, log in.

    Returns ids dict {wid, uid, pid}. NOTE: items.status default 'CLEAR' requires
    status_options seeding; samples don't reference status_options but other tests
    may; we keep the seed for parity with other test files in the repo.
    """
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
            s.execute(text("INSERT INTO status_options(status_key, sort_order) VALUES(:k, :o) ON CONFLICT DO NOTHING"),
                      {"k": key, "o": order})
        wid = s.execute(text("INSERT INTO workspace(slug,name) VALUES('sm','SM') RETURNING id")).scalar()
        uid = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, :e, 'U', :p, :r) RETURNING id
        """), {"w": wid, "e": f"{role}@sm.test", "p": hash_password("pw"), "r": role}).scalar()
        pid = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id)
            VALUES('SM-001', 'SM', :u, :w) RETURNING project_id
        """), {"u": uid, "w": wid}).scalar()
        s.commit()
    finally:
        s.close()
    r = client.post("/auth/login", json={"workspace_slug": "sm", "email": f"{role}@sm.test", "password": "pw"})
    assert r.status_code == 200, r.text
    return {"wid": wid, "uid": uid, "pid": pid}


def test_create_sample_with_valid_hex(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={
        "title": "Oak veneer", "room": "L3 / Reception", "hex_swatch": "#c29075", "supplier": "Briggs",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Oak veneer"
    assert body["status"] == "pending"
    assert body["hex_swatch"] == "#c29075"


def test_create_sample_invalid_hex_returns_422(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={
        "title": "Bad", "hex_swatch": "red",
    })
    assert r.status_code == 422


def test_create_sample_short_hex_returns_422(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={
        "title": "Bad", "hex_swatch": "#fff",
    })
    assert r.status_code == 422


def test_create_sample_missing_title_returns_422(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={
        "hex_swatch": "#aabbcc",
    })
    assert r.status_code == 422


def test_create_sample_with_room_null(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={
        "title": "No room", "hex_swatch": "#aabbcc",
    })
    assert r.status_code == 201
    assert r.json()["room"] is None


def test_list_board_returns_pending_and_approved(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={"title": "T1", "hex_swatch": "#aabbcc"})
    assert r.status_code == 201
    r = client.get(f"/projects/{ids['pid']}/samples?subtab=board")
    assert r.status_code == 200
    body = r.json()
    assert len(body["samples"]) >= 1
    assert body["counts"]["pending"] >= 1


def test_get_single_sample(client, truncate_all):
    ids = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids['pid']}/samples", json={"title": "G", "hex_swatch": "#112233"})
    sid = r.json()["sample_id"]
    r = client.get(f"/samples/{sid}")
    assert r.status_code == 200
    assert r.json()["sample_id"] == sid


def test_patch_by_non_creator_non_manager_returns_403(client, truncate_all):
    """Editor (not creator, not manager) cannot edit a drafter's sample."""
    ids_drafter = _seed(client, truncate_all)
    r = client.post(f"/projects/{ids_drafter['pid']}/samples", json={"title": "Mine", "hex_swatch": "#aabbcc"})
    sid = r.json()["sample_id"]

    # Switch to editor
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'ed@sm.test', 'ED', :p, 'editor')
        """), {"w": ids_drafter["wid"], "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    client.cookies.clear()
    r = client.post("/auth/login", json={"workspace_slug": "sm", "email": "ed@sm.test", "password": "pw"})
    assert r.status_code == 200
    r = client.patch(f"/samples/{sid}", json={"title": "Stolen"})
    assert r.status_code == 403
