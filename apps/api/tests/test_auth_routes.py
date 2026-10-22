import uuid

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app

from .conftest import truncate_fixture
from .helpers import login


_cleanup = truncate_fixture()


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


def test_me_includes_permissions_matching_the_matrix():
    """The web tier gates navigation off this payload — it must mirror MATRIX."""
    from app.auth.permissions import _ALL_MODULES, has_permission

    for role in ("admin", "viewer", "purchase_officer", "estimator"):
        perms = login(role)[0].get("/auth/me").json()["permissions"]
        assert set(perms) == set(_ALL_MODULES), role
        for module in _ALL_MODULES:
            for action in ("read", "write", "approve", "comment"):
                assert (action in perms[module]) is has_permission(role, module, action)


def test_me_permissions_deny_it_management_for_non_admin():
    assert login("viewer")[0].get("/auth/me").json()["permissions"]["it_management"] == []
    assert "read" in login("admin")[0].get("/auth/me").json()["permissions"]["it_management"]


def _aged_session():
    from datetime import datetime, timedelta, timezone
    from app.config import settings
    slug, email = _seed()
    c = TestClient(app)
    assert c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": "pw"}).status_code == 200
    old = datetime.now(timezone.utc) - timedelta(days=settings.session_sliding_days - 1)
    with SessionLocal() as db:
        db.execute(text("UPDATE session SET last_seen_at=:old"), {"old": old})
        db.commit()
    return c, old


def test_read_only_activity_persists_session_renewal():
    c, old = _aged_session()
    assert c.get("/auth/me").status_code == 200
    with SessionLocal() as db:
        assert db.execute(text("SELECT last_seen_at FROM session")).scalar_one() > old


def test_read_renews_browser_cookie_but_never_past_hard_expiry():
    from datetime import datetime, timedelta, timezone
    from http.cookies import SimpleCookie
    from app.config import settings
    c, _old = _aged_session()
    with SessionLocal() as db:
        db.execute(text("UPDATE session SET hard_expires_at=:hard"), {"hard": datetime.now(timezone.utc) + timedelta(hours=2)})
        db.commit()
    response = c.get("/auth/me")
    assert response.status_code == 200
    cookie = SimpleCookie()
    cookie.load(response.headers.get("set-cookie", ""))
    assert settings.session_cookie_name in cookie
    renewed = cookie[settings.session_cookie_name]
    assert 0 < int(renewed["max-age"]) <= 7200
    assert renewed["httponly"]
    assert renewed["samesite"].lower() == "lax"


def test_session_activity_commits_without_committing_failed_business_write():
    from fastapi import Depends, FastAPI, HTTPException
    from sqlalchemy.orm import Session
    from app.auth.rbac import current_user
    from app.db import get_db
    c, old = _aged_session()
    probe = FastAPI()

    @probe.post("/failing-write")
    def failing_write(user=Depends(current_user), db: Session = Depends(get_db)):
        db.execute(text("UPDATE workspace SET name='must roll back' WHERE id=:w"), {"w": user.workspace_id})
        raise HTTPException(409, "business conflict")

    probe_client = TestClient(probe)
    probe_client.cookies.update(c.cookies)
    failed = probe_client.post("/failing-write")
    assert failed.status_code == 409
    with SessionLocal() as db:
        assert db.execute(text("SELECT name FROM workspace")).scalar_one() == "H"
        assert db.execute(text("SELECT last_seen_at FROM session")).scalar_one() > old


@pytest.mark.parametrize("invalidate", [
    "UPDATE session SET revoked_at=now()",
    "UPDATE session SET hard_expires_at=now()-interval '1 second'",
    "UPDATE session SET last_seen_at=now()-interval '60 days'",
    "UPDATE app_user SET is_active=false",
])
def test_invalid_session_is_not_renewed(invalidate):
    c, _old = _aged_session()
    with SessionLocal() as db:
        db.execute(text(invalidate))
        db.commit()
    response = c.get("/auth/me")
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
