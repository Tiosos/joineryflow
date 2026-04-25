"""FastAPI auth dependencies.

current_user: extracts session token from the cookie, looks it up, returns
the AuthUser or raises 401.

require_permission(module, action): factory returning a dep that runs
current_user and then enforces the static RBAC matrix, raising 403 on miss.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from .permissions import has_permission
from .sessions import AuthUser, SessionExpired, SessionHardCapped, lookup_session


def current_user(request: Request, db: Session = Depends(get_db)) -> AuthUser:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="no session"
        )
    try:
        return lookup_session(db, token)
    except (SessionExpired, SessionHardCapped):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
        )


def require_permission(module: str, action: str):
    def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        if not has_permission(user.auth_role, module, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        return user

    return _dep
