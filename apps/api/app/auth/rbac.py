"""FastAPI auth dependencies.

current_user: extracts session token from the cookie, looks it up, returns
the AuthUser or raises 401.

require_permission(module, action, project_param=None): factory returning a
dep that runs current_user and then enforces the DB-backed permission engine
(app.auth.rbac_engine), raising 403 on miss. See Q466-473.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from .rbac_engine import effective_actions
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


def require_permission(module: str, action: str, project_param: str | None = None):
    """`project_param` names a path parameter (e.g. "pid") holding a project
    id. When given, the check additionally admits grants from memberships
    scoped to that one project (Q466); when omitted (every pre-0037 call
    site), only workspace-wide memberships apply — the exact behaviour the
    static matrix gave, since migration 0037 backfilled every existing user
    a workspace-wide (project_id IS NULL) membership.
    """

    def _dep(
        request: Request,
        user: AuthUser = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> AuthUser:
        project_id: int | None = None
        if project_param is not None:
            raw = request.path_params.get(project_param)
            if raw is not None:
                try:
                    project_id = int(raw)
                except (TypeError, ValueError):
                    project_id = None
        if action not in effective_actions(db, user, module, project_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="forbidden"
            )
        return user

    return _dep


def require_drafter():
    """Allow only auth_role in {drafter, manager, admin}.

    Use for the spec §2.4 invariant 5 — narrow gate on item / module /
    part / hardware_line / project_hardware_catalog mutations."""

    def _dep(user: AuthUser = Depends(current_user)) -> AuthUser:
        if user.auth_role not in ("drafter", "manager", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="drafter, manager, or admin required",
            )
        return user

    return _dep
