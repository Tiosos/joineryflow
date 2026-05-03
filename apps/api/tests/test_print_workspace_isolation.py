"""Cross-workspace print attempts must return 404 (not 403 — don't leak existence)."""
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


def _seed_two_workspaces_one_item(truncate_all):
    """Workspace A holds an item; workspace B has its own user.

    Note: projects.workspace_id is NOT NULL (per migration 0014); seed sets it.
    Status options must be seeded for items.status default 'CLEAR' to satisfy FK.
    """
    truncate_all()
    from app.db import SessionLocal
    from app.auth.passwords import hash_password
    s = SessionLocal()
    try:
        for key, order in [("CLEAR", 1), ("HOLD", 2), ("LIVE", 3), ("VOID", 4)]:
            s.execute(text("INSERT INTO status_options(status_key, sort_order) VALUES(:k, :o) ON CONFLICT DO NOTHING"),
                      {"k": key, "o": order})
        wid_a = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsa','A') RETURNING id")).scalar()
        uid_a = s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'a@a.test', 'A', :p, 'drafter') RETURNING id
        """), {"w": wid_a, "p": hash_password("pw")}).scalar()
        pid_a = s.execute(text("""
            INSERT INTO projects(project_code, name, pm_id, workspace_id) VALUES('A-001','A',:u,:w) RETURNING project_id
        """), {"u": uid_a, "w": wid_a}).scalar()
        iid_a = s.execute(text("""
            INSERT INTO items(num, project_id, description) VALUES (90400, :p, 'A item') RETURNING item_id
        """), {"p": pid_a}).scalar()

        wid_b = s.execute(text("INSERT INTO workspace(slug,name) VALUES('wsb','B') RETURNING id")).scalar()
        s.execute(text("""
            INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
            VALUES (:w, 'b@b.test', 'B', :p, 'drafter')
        """), {"w": wid_b, "p": hash_password("pw")})
        s.commit()
    finally:
        s.close()
    return iid_a


@pytest.mark.parametrize("path", ["cutlist.pdf", "hardware.pdf", "combined.pdf"])
def test_cross_workspace_print_returns_404(client, truncate_all, path):
    iid = _seed_two_workspaces_one_item(truncate_all)
    r = client.post("/auth/login", json={"workspace_slug": "wsb", "email": "b@b.test", "password": "pw"})
    assert r.status_code == 200
    r = client.get(f"/items/{iid}/{path}")
    assert r.status_code == 404
