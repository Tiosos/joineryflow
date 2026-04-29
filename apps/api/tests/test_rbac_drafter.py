import uuid
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth.passwords import hash_password
from app.auth.rbac import require_drafter
from app.auth.sessions import create_session
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
            text("""
              INSERT INTO app_user(workspace_id, email, full_name, password_hash, auth_role)
              VALUES (:w, :e, 'X', :p, :r) RETURNING id
            """),
            {"w": wid, "e": f"u-{suffix}@x", "p": hash_password("pw"), "r": role},
        ).scalar()
        tok = create_session(db, uid)
        db.commit()
        return tok
    finally:
        db.close()


def _app() -> FastAPI:
    a = FastAPI()

    @a.post("/draft")
    def draft(_=Depends(require_drafter())):
        return {"ok": True}

    return a


@pytest.mark.parametrize("role,expected", [
    ("drafter",          200),
    ("manager",          200),
    ("admin",            200),
    ("editor",           403),
    ("purchase_officer", 403),
    ("viewer",           403),
])
def test_require_drafter_matrix(role, expected):
    tok = _seed(role)
    c = TestClient(_app())
    assert c.post("/draft", cookies={"jf_session": tok}).status_code == expected


def test_drafter_matrix_orderbook_write_and_approve():
    from app.auth.permissions import MATRIX
    assert "write"   in MATRIX["drafter"]["orderbook"]
    assert "approve" in MATRIX["drafter"]["orderbook"]
