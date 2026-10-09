import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import truncate_fixture
from .helpers import login, log_in


_cleanup = truncate_fixture()


def test_workspace_returns_current():
    c, wid, _ = login("admin", prefix="h")
    with SessionLocal() as db:
        slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid}).scalar()
    r = c.get("/workspace")
    assert r.status_code == 200
    assert r.json()["slug"] == slug


def test_admin_lists_users():
    c, _, _ = login("admin", prefix="h")
    r = c.get("/users")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_admin_lists_users_with_reserved_tld_email():
    """Fixed later. UserOut.email was EmailStr, a response-validation type —
    not just input validation. email-validator >=2.2 rejects `.test` as an
    IANA-reserved special-use TLD (RFC 2606), so this 500'd for every real
    seeded user (`*.hartwood.test`) even though `_login()`'s own
    `@example.com` fixture never touched the bug. Plain str now, matching
    auth/schemas.py's existing "format enforced upstream" stance."""
    suffix = uuid.uuid4().hex[:8]
    slug = f"h-{suffix}"
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
                VALUES (:w, :e, 'Admin', :p, 'admin')
                """
            ),
            {"w": wid, "e": f"admin-{suffix}@hartwood.test", "p": hash_password("pw")},
        )
        db.commit()
    finally:
        db.close()
    c = TestClient(app)
    log_in(slug, f"admin-{suffix}@hartwood.test", client=c)

    r = c.get("/users")
    assert r.status_code == 200, r.text
    assert r.json()[0]["email"] == f"admin-{suffix}@hartwood.test"


def test_editor_cannot_list_users():
    c, _, _ = login("editor", prefix="h")
    r = c.get("/users")
    assert r.status_code == 403


def test_admin_can_patch_user():
    c, _, _ = login("admin", prefix="h")
    me = c.get("/auth/me").json()
    r = c.patch(f"/users/{me['id']}", json={"jtbd_role": "CEO"})
    assert r.status_code == 200
    assert r.json()["jtbd_role"] == "CEO"


def test_patch_rejects_bad_auth_role():
    c, _, _ = login("admin", prefix="h")
    me = c.get("/auth/me").json()
    r = c.patch(f"/users/{me['id']}", json={"auth_role": "godking"})
    assert r.status_code == 400


def test_patch_accepts_drafter_auth_role():
    c, _, _ = login("admin", prefix="h")
    me = c.get("/auth/me").json()
    r = c.patch(f"/users/{me['id']}", json={"auth_role": "drafter"})
    assert r.status_code == 200
    assert r.json()["auth_role"] == "drafter"
