import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE audit_log, session, app_user, workspace RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _login(role: str):
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"u-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :p, :r)
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": role},
        )
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    return c, slug, email


def test_workspace_returns_current():
    c, slug, _ = _login("admin")
    r = c.get("/workspace")
    assert r.status_code == 200
    assert r.json()["slug"] == slug


def test_admin_lists_users():
    c, _, _ = _login("admin")
    r = c.get("/users")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_editor_cannot_list_users():
    c, _, _ = _login("editor")
    r = c.get("/users")
    assert r.status_code == 403


def test_admin_can_patch_user():
    c, _, _ = _login("admin")
    me = c.get("/auth/me").json()
    r = c.patch(f"/users/{me['id']}", json={"jtbd_role": "CEO"})
    assert r.status_code == 200
    assert r.json()["jtbd_role"] == "CEO"


def test_patch_rejects_bad_auth_role():
    c, _, _ = _login("admin")
    me = c.get("/auth/me").json()
    r = c.patch(f"/users/{me['id']}", json={"auth_role": "godking"})
    assert r.status_code == 400
