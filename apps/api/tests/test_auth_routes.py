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


def _seed():
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"x-{suffix}@example.com"
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
                VALUES (:w, :e, 'X', :p, 'admin')
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw")},
        )
        db.commit()
        return slug, email
    finally:
        db.close()


def test_login_me_logout():
    slug, email = _seed()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "pw"},
    )
    assert r.status_code == 200, r.text
    r2 = c.get("/auth/me")
    assert r2.status_code == 200
    assert r2.json()["email"] == email
    r3 = c.post("/auth/logout")
    assert r3.status_code == 200
    # Cookie should be cleared; subsequent /auth/me must 401.
    r4 = c.get("/auth/me")
    assert r4.status_code == 401


def test_login_bad_password():
    slug, email = _seed()
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": slug, "email": email, "password": "nope"},
    )
    assert r.status_code == 401


def test_login_unknown_user():
    c = TestClient(app)
    r = c.post(
        "/auth/login",
        json={"workspace_slug": "nope", "email": "nope@example.com", "password": "x"},
    )
    assert r.status_code == 401


def test_me_includes_jtbd_role():
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"d-{suffix}@example.com"
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'H') RETURNING id"),
            {"s": slug},
        ).scalar()
        db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role, jtbd_role)
                VALUES (:w, :e, 'Drafter User', :p, 'drafter', 'Drafter')
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw")},
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
    r2 = c.get("/auth/me")
    assert r2.status_code == 200
    assert r2.json()["jtbd_role"] == "Drafter"


def _login_as(auth_role: str):
    """Seed a workspace + user with `auth_role`, log in, return the client."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
    email = f"r-{suffix}@example.com"
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
                VALUES (:w, :e, 'Role User', :p, :r)
                """
            ),
            {"w": wid, "e": email, "p": hash_password("pw"), "r": auth_role},
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
    return c


def test_me_includes_permissions_matching_the_matrix():
    """The web tier gates navigation off this payload — it must mirror MATRIX."""
    from app.auth.permissions import _ALL_MODULES, has_permission

    for role in ("admin", "viewer", "purchase_officer", "estimator"):
        perms = _login_as(role).get("/auth/me").json()["permissions"]
        assert set(perms) == set(_ALL_MODULES), role
        for module in _ALL_MODULES:
            for action in ("read", "write", "approve", "comment"):
                assert (action in perms[module]) is has_permission(role, module, action)


def test_me_permissions_deny_it_management_for_non_admin():
    assert _login_as("viewer").get("/auth/me").json()["permissions"]["it_management"] == []
    assert "read" in _login_as("admin").get("/auth/me").json()["permissions"]["it_management"]
