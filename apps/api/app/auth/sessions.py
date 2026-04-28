import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings


class SessionExpired(Exception):
    """Session is revoked, user inactive, or sliding window elapsed."""


class SessionHardCapped(Exception):
    """Session has exceeded the absolute (hard-cap) lifetime."""


@dataclass
class AuthUser:
    id: int
    workspace_id: int
    email: str
    full_name: str
    auth_role: str
    jtbd_role: str | None = None


def _h(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    hard = datetime.now(timezone.utc) + timedelta(days=settings.session_hard_cap_days)
    db.execute(
        text(
            """
            INSERT INTO session(token_hash, user_id, hard_expires_at)
            VALUES (:h, :u, :e)
            """
        ),
        {"h": _h(token), "u": user_id, "e": hard},
    )
    db.flush()
    return token


def lookup_session(db: Session, token: str) -> AuthUser:
    now = datetime.now(timezone.utc)
    sliding = timedelta(days=settings.session_sliding_days)
    h = _h(token)
    row = db.execute(
        text(
            """
            SELECT s.user_id, s.last_seen_at, s.hard_expires_at, s.revoked_at,
                   u.workspace_id, u.email, u.full_name, u.auth_role, u.jtbd_role, u.is_active
            FROM session s
            JOIN app_user u ON u.id = s.user_id
            WHERE s.token_hash = :h
            """
        ),
        {"h": h},
    ).mappings().first()
    if not row or row["revoked_at"] is not None or not row["is_active"]:
        raise SessionExpired()
    if row["hard_expires_at"] <= now:
        raise SessionHardCapped()
    if row["last_seen_at"] + sliding <= now:
        raise SessionExpired()
    db.execute(
        text("UPDATE session SET last_seen_at = :n WHERE token_hash = :h"),
        {"n": now, "h": h},
    )
    db.flush()
    return AuthUser(
        id=row["user_id"],
        workspace_id=row["workspace_id"],
        email=row["email"],
        full_name=row["full_name"],
        auth_role=row["auth_role"],
        jtbd_role=row["jtbd_role"],
    )


def revoke_session(db: Session, token: str) -> None:
    db.execute(
        text("UPDATE session SET revoked_at = now() WHERE token_hash = :h"),
        {"h": _h(token)},
    )
    db.flush()
