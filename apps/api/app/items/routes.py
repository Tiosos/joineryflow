from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from ..projects.queries import get_project
from .queries import get_item_detail, list_items_for_project
from .schemas import ItemOut, TrackingGridOut

router = APIRouter(prefix="", tags=["items"])


@router.get("/projects/{pid}/items", response_model=TrackingGridOut)
def get_project_items(
    pid: int,
    status: str | None = None,
    stage: str | None = None,
    q: str | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    proj = get_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if proj is None:
        raise HTTPException(status_code=404, detail="project not found")
    items = list_items_for_project(
        db,
        workspace_id=user.workspace_id,
        project_id=pid,
        status=status,
        stage_key=stage,
        q=q,
    )
    return {"project_id": pid, "items": items}


@router.get("/items/{id}", response_model=ItemOut)
def get_item(
    id: int,
    user: AuthUser = Depends(require_permission("list", "read")),
    db: Session = Depends(get_db),
):
    detail = get_item_detail(
        db,
        item_id=id,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="item not found")
    return detail
