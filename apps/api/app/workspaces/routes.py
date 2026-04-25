from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.rbac import current_user
from ..auth.sessions import AuthUser
from ..db import get_db

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("")
def get_workspace(
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        text("SELECT id, slug, name FROM workspace WHERE id = :i"),
        {"i": user.workspace_id},
    ).mappings().first()
    if not row:
        raise HTTPException(404)
    return dict(row)
