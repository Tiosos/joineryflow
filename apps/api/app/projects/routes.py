from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .queries import create_project, get_project, list_projects, patch_project
from .schemas import CreateProjectIn, PatchProjectIn, ProjectListOut, ProjectOut

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListOut)
def list_projects_route(
    fav_only: bool | None = None,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    rows = list_projects(
        db,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
        fav_only=fav_only,
    )
    return {"projects": rows}


@router.get("/{pid}", response_model=ProjectOut)
def get_project_route(
    pid: int,
    user: AuthUser = Depends(require_permission("tracking", "read")),
    db: Session = Depends(get_db),
):
    row = get_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    return row


@router.post("", response_model=ProjectOut, status_code=201)
def create_project_route(
    body: CreateProjectIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")

    # Default pm_id to the caller when not supplied.
    if body.pm_id is None:
        body = body.model_copy(update={"pm_id": user.id})

    try:
        new_id = create_project(
            db,
            workspace_id=user.workspace_id,
            payload=body,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()

    row = get_project(
        db,
        project_id=new_id,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if not row:
        raise HTTPException(status_code=500, detail="project created but not found")
    return row


@router.patch("/{pid}", response_model=ProjectOut)
def patch_project_route(
    pid: int,
    body: PatchProjectIn,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")

    try:
        row = patch_project(
            db,
            project_id=pid,
            workspace_id=user.workspace_id,
            payload=body,
            actor_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    db.commit()
    return row
