"""GET /projects/{pid}/materials — project material rollup endpoint."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ...auth.rbac import require_permission
from ...auth.sessions import AuthUser
from ...db import get_db
from ...projects.queries import get_project
from .queries import project_material_rollup
from .schemas import ProjectMaterialsOut

router = APIRouter(prefix="", tags=["procurement-v1"])


@router.get("/projects/{pid}/materials", response_model=ProjectMaterialsOut)
def get_project_materials(
    pid: int,
    user: AuthUser = Depends(require_permission("orderbook", "read")),
    db: Session = Depends(get_db),
):
    proj = get_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if proj is None:
        raise HTTPException(404, "Project not found")
    rows = project_material_rollup(db, project_id=pid)
    return {"project_id": pid, "rows": rows}
