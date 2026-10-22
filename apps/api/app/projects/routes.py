from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.rbac import current_user, require_permission
from ..auth.sessions import AuthUser
from ..db import get_db
from .queries import (
    add_favourite,
    close_out_checks,
    close_out_project,
    create_project,
    get_project,
    list_projects,
    patch_project,
    remove_favourite,
)
from .schemas import CloseOutChecksOut, CloseOutIn, CloseOutOut, CreateProjectIn, PatchProjectIn, ProjectListOut, ProjectOut

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


@router.get("/{pid}/close-out-checks", response_model=CloseOutChecksOut)
def close_out_checks_route(
    pid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """What is still open before a close-out (open QC defects and rework, items not installed,
    open orders). Admin/manager only, like the close-out itself. Advisory: never blocks it."""
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")
    checks = close_out_checks(db, project_id=pid, workspace_id=user.workspace_id)
    if checks is None:
        raise HTTPException(status_code=404, detail="project not found")
    return checks


@router.post("/{pid}/close-out", response_model=CloseOutOut)
def close_out_route(
    pid: int,
    payload: CloseOutIn | None = None,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Close out a project.  Admin/manager only.  409 if already closed.  `reason` (optional) is
    why it is closed with things still open; it goes in the audit row with what was open."""
    if user.auth_role not in ("manager", "admin"):
        raise HTTPException(status_code=403, detail="manager or admin required")

    result = close_out_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        reason=(payload.reason or "").strip() or None if payload else None,
    )
    if result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="project not found")
    if result == "ALREADY_CLOSED":
        raise HTTPException(status_code=409, detail="project already closed")
    db.commit()

    row = get_project(
        db,
        project_id=pid,
        workspace_id=user.workspace_id,
        current_user_id=user.id,
    )
    if row is None:
        raise HTTPException(status_code=500, detail="project not found after close-out")
    return {
        "project_id": pid,
        "closed_at": row["closed_at"],
        "closed_by": row["closed_by"],
        "closed_by_name": row.get("closed_by_name"),
    }


@router.post("/{pid}/favourites", status_code=204)
def add_fav(
    pid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if get_project(db, project_id=pid, workspace_id=user.workspace_id,
                   current_user_id=user.id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    add_favourite(db, project_id=pid, user_id=user.id)
    db.commit()


@router.delete("/{pid}/favourites", status_code=204)
def del_fav(
    pid: int,
    user: AuthUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    if get_project(db, project_id=pid, workspace_id=user.workspace_id,
                   current_user_id=user.id) is None:
        raise HTTPException(status_code=404, detail="project not found")
    remove_favourite(db, project_id=pid, user_id=user.id)
    db.commit()
