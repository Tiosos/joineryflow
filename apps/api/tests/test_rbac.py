import uuid

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.rbac import current_user, require_permission
from app.auth.sessions import create_session
from app.auth.passwords import hash_password
from app.db import SessionLocal


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    s = SessionLocal()
    try:
        s.execute(text("TRUNCATE audit_log, session, app_user, workspace RESTART IDENTITY CASCADE"))
        s.commit()
    finally:
        s.close()


def _seed(role: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        wid = db.execute(
            text("INSERT INTO workspace(slug, name) VALUES(:s, 'T') RETURNING id"),
            {"s": f"t-{suffix}"},
        ).scalar()
        uid = db.execute(
            text(
                """
                INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
                VALUES (:w, :e, 'U', :h, :r) RETURNING id
                """
            ),
            {
                "w": wid,
                "e": f"u-{suffix}@t",
                "h": hash_password("x"),
                "r": role,
            },
        ).scalar()
        tok = create_session(db, uid)
        db.commit()
        return tok
    finally:
        db.close()


def _app() -> FastAPI:
    a = FastAPI()

    @a.get("/me", dependencies=[Depends(current_user)])
    def me():
        return {"ok": True}

    @a.post("/it")
    def it(_=Depends(require_permission("it_management", "write"))):
        return {"ok": True}

    return a


def test_requires_auth():
    c = TestClient(_app())
    assert c.get("/me").status_code == 401


def test_admin_can_it():
    tok = _seed("admin")
    c = TestClient(_app())
    r = c.post("/it", cookies={"jf_session": tok})
    assert r.status_code == 200


def test_editor_cannot_it():
    tok = _seed("editor")
    c = TestClient(_app())
    r = c.post("/it", cookies={"jf_session": tok})
    assert r.status_code == 403
