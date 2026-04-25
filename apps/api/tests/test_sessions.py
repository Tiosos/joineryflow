import hashlib
from datetime import timedelta, datetime, timezone
from sqlalchemy import text
import pytest
from app.auth.sessions import (
    create_session, lookup_session, revoke_session,
    SessionExpired, SessionHardCapped, AuthUser,
)
from app.auth.passwords import hash_password


def _mk_user(db, wid):
    return db.execute(text("""
      INSERT INTO app_user(workspace_id,email,full_name,password_hash,auth_role)
      VALUES (:w,'a@b','A',:h,'admin') RETURNING id
    """), {"w": wid, "h": hash_password("x")}).scalar()


def test_create_lookup(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    u = lookup_session(db, token)
    assert isinstance(u, AuthUser)
    assert u.id == uid


def test_revoke(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    revoke_session(db, token)
    with pytest.raises(SessionExpired):
        lookup_session(db, token)


def test_hard_cap(db, workspace_id):
    uid = _mk_user(db, workspace_id)
    token = create_session(db, uid)
    h = hashlib.sha256(token.encode()).digest()
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.execute(text("UPDATE session SET hard_expires_at=:t WHERE token_hash=:h"),
               {"t": past, "h": h})
    with pytest.raises(SessionHardCapped):
        lookup_session(db, token)
