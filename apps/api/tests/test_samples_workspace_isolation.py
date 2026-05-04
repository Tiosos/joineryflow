"""Cross-workspace sample access must return 404 (not leak existence)."""
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


def _seed_two_workspaces_one_sample(truncate_all):
    """Workspace A has a sample; workspace B has its own user."""
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        wid_a = s.execute(text("INSERT INTO workspace(slug,name) VALUES('isoa','A') RETURNING id")).scalar()
        uid_a = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'a@iso.test', 'A', :p, 'drafter') RETURNING id
        """), {"w": wid_a, "p": hash_password("pw")}).scalar()
        pid_a = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id) VALUES('A-1','A',:u,:w) RETURNING project_id
        """), {"u": uid_a, "w": wid_a}).scalar()
        sid_a = s.execute(text("""
            INSERT INTO sample(project_id, title, hex_swatch, created_by)
            VALUES (:p, 'Hidden', '#aabbcc', :u) RETURNING sample_id
        """), {"p": pid_a, "u": uid_a}).scalar()

        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('isob','B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@iso.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    return {"pid_a": pid_a, "sid_a": sid_a}


def test_get_single_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_sample(truncate_all)
    client.post("/auth/login", json={"workspace_slug": "isob", "email": "b@iso.test", "password": "pw"})
    r = client.get(f"/samples/{ids['sid_a']}")
    assert r.status_code == 404


def test_list_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_sample(truncate_all)
    client.post("/auth/login", json={"workspace_slug": "isob", "email": "b@iso.test", "password": "pw"})
    r = client.get(f"/projects/{ids['pid_a']}/samples?subtab=board")
    assert r.status_code == 404


def test_ledger_cross_workspace_returns_404(client, truncate_all):
    ids = _seed_two_workspaces_one_sample(truncate_all)
    client.post("/auth/login", json={"workspace_slug": "isob", "email": "b@iso.test", "password": "pw"})
    r = client.get(f"/projects/{ids['pid_a']}/samples/ledger")
    assert r.status_code == 404
