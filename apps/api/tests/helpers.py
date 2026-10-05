"""Shared test helpers: one login/bootstrap path instead of a copy per test file.

Reference rows (`status_options`, `stages`) are re-asserted before every test by
the autouse fixture in conftest.py, so nothing here seeds them.
"""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.db import SessionLocal
from app.main import app


def _insert_user(db, *, wid: int, role: str, name: str = "U", email_prefix: str = "u") -> tuple[str, int]:
    email = f"{email_prefix}-{uuid.uuid4().hex[:8]}@example.com"
    uid = db.execute(
        text(
            "INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)"
            " VALUES (:w, :e, :n, :p, :r) RETURNING id"
        ),
        {"w": wid, "e": email, "n": name, "p": hash_password("pw"), "r": role},
    ).scalar()
    return email, uid


def log_in(slug: str, email: str, password: str = "pw", *, raise_server_exceptions: bool = True) -> TestClient:
    """A client logged in as `email`. With `raise_server_exceptions=False` an unhandled
    server error comes back as a 500 response instead of being re-raised in the test."""
    c = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    r = c.post("/auth/login", json={"workspace_slug": slug, "email": email, "password": password})
    assert r.status_code == 200, r.text
    return c


def login(role: str = "manager", *, wid: int | None = None, prefix: str = "h"):
    """A user with `role`, logged in -> (client, workspace_id, user_id).

    Creates a fresh workspace unless `wid` names an existing one.
    """
    db = SessionLocal()
    try:
        if wid is None:
            slug = f"{prefix}-{uuid.uuid4().hex[:8]}"
            wid = db.execute(
                text("INSERT INTO workspace(slug, name) VALUES(:s, :n) RETURNING id"),
                {"s": slug, "n": prefix.upper()},
            ).scalar()
        else:
            slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid}).scalar()
        email, uid = _insert_user(db, wid=wid, role=role)
        db.commit()
    finally:
        db.close()
    return log_in(slug, email), wid, uid


def login_same_workspace(wid: int, role: str, name: str = "U2"):
    """A second user in an existing workspace -> (client, user_id)."""
    db = SessionLocal()
    try:
        slug = db.execute(text("SELECT slug FROM workspace WHERE id = :w"), {"w": wid}).scalar()
        email, uid = _insert_user(db, wid=wid, role=role, name=name, email_prefix="u2")
        db.commit()
    finally:
        db.close()
    return log_in(slug, email), uid


def create_project(db, *, uid: int, code: str = "HJ-001") -> int:
    """Insert a project owned by `uid` (workspace taken from that user) -> project_id."""
    pid = db.execute(
        text(
            "INSERT INTO projects(project_code, name, pm_id, workspace_id)"
            " VALUES (:code, :name, :uid, (SELECT workspace_id FROM app_user WHERE id = :uid))"
            " RETURNING project_id"
        ),
        {"code": code, "name": f"Project {code}", "uid": uid},
    ).scalar()
    db.commit()
    return pid


def set_item(iid: int, sql: str, **params) -> None:
    """`UPDATE items SET <sql> WHERE item_id = :i`, committed."""
    db = SessionLocal()
    try:
        db.execute(text(f"UPDATE items SET {sql} WHERE item_id = :i"), {"i": iid, **params})
        db.commit()
    finally:
        db.close()
