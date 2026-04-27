from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.queries import get_project
from .queries import list_catalog
from .schemas import HardwareCatalogOut

router = APIRouter(prefix="", tags=["hardware_lines"])


@router.get("/projects/{pid}/hardware_catalog", response_model=HardwareCatalogOut)
def get_catalog(
    pid: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    if get_project(db, project_id=pid, workspace_id=user.workspace_id,
                   current_user_id=user.id) is None:
        raise HTTPException(404, "project not found")
    rows = list_catalog(db, workspace_id=user.workspace_id, project_id=pid)
    return {"project_id": pid, "rows": rows}
